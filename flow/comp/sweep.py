"""The comparator's design space (``flow.sweep``): the characterization's six topologies at ten
sizings (seven around the short-channel base, three around FRIDA-1's long-channel comparator), in
every PDK.

Each instance at the nominal common mode (13/24 of its supply): the clock-to-decision delay and
energy per decision at 0.5 mV and 100 mV of input (the slowest and fastest response), the delay
over the input from 0.1 mV to 100 mV (its metastability), and the offset and input-referred noise
from a transient-noise S-curve (+-2 mV, 21 points, 40 decisions each). Over the common mode (3/8
to 5/8 of the supply) the S-curve again; over the supply (90 to 120 % of its own) the delay and
energy at both inputs. Clock: 1 ns reset, 2 ns evaluation. Eleven Spectre runs, two to four
minutes in all.
"""

from __future__ import annotations

import importlib
import math
from dataclasses import replace
from pathlib import Path

import hdl21 as h
import numpy as np

from flow.sweep import Detail, Record

from .sim import TOPOLOGIES, TOPOLOGY_SIZES, CompTbParams, _run_comp_sim, comp_signal_names
from .subckt import Comp, CompParams, OutputStage, is_valid_comp_params, write_netlist

GENERATOR = Comp
# the key devices' widths scaled together (x0.5 to x4), the input pair or the latch alone
# doubled, and the input pair and tail at twice their length
WIDTHS = ("diffpair_w", "tail_w", "rst_w", "latch_on_w", "latch_init_w", "srlatch_n_w", "srlatch_p_w")
SIZINGS = {
    # no width under 4 units: half of the 4-unit output latch would fall below TSMC28's 90 nm minimum
    "x0.5": {name: max(4, TOPOLOGY_SIZES[name] // 2) for name in WIDTHS},
    "x1": {},
    "x2": {name: 2 * TOPOLOGY_SIZES[name] for name in WIDTHS},
    "x4": {name: 4 * TOPOLOGY_SIZES[name] for name in WIDTHS},
    "pair_x2": {"diffpair_w": 2 * TOPOLOGY_SIZES["diffpair_w"]},
    "latch_x2": {name: 2 * TOPOLOGY_SIZES[name] for name in ("latch_on_w", "latch_init_w")},
    "long": {"diffpair_l": 2 * TOPOLOGY_SIZES["diffpair_l"], "tail_l": 2 * TOPOLOGY_SIZES["tail_l"]},
}
# near FRIDA-1's hand-sized comparator (flow.comp.subckt.FRIDA1: a long, weak tail and long latch
# devices) in round multiples of the minimum, with its widths doubled and its lengths doubled, so
# every FRIDA-1 size falls inside the sweep's range
FRIDA1_LIKE = {
    "diffpair_w": 32,
    "diffpair_l": 4,
    "tail_w": 4,
    "tail_l": 16,
    "rst_w": 8,
    "rst_l": 1,
    "latch_on_w": 24,
    "latch_on_l": 6,
    "latch_init_w": 32,
    "latch_init_l": 16,
    "srlatch_n_w": 4,
    "srlatch_p_w": 8,
}
LENGTHS = ("diffpair_l", "tail_l", "rst_l", "latch_on_l", "latch_init_l")
SIZINGS |= {
    "frida1_like": FRIDA1_LIKE,
    "frida1_like_x2": {**FRIDA1_LIKE, **{name: 2 * FRIDA1_LIKE[name] for name in WIDTHS}},
    "frida1_like_long": {**FRIDA1_LIKE, **{name: 2 * FRIDA1_LIKE[name] for name in LENGTHS}},
}
NOMINAL_CM = 13 / 24
CM_SWEEP = (9 / 24, 11 / 24, 13 / 24, 15 / 24)
SUPPLY_SWEEP = (0.9, 1.0, 1.1, 1.2)
SMALL_V, LARGE_V = 0.5e-3, 100e-3
METASTABILITY_V = (0.1e-3, 0.3e-3, 1e-3, 3e-3, 10e-3, 30e-3, 100e-3)
SCURVE_V = tuple(round(step * 0.2e-3, 6) for step in range(-10, 11))


def params(pdk: str, topology: str, sizing: str) -> CompParams | None:
    comp = CompParams(**TOPOLOGIES[topology], **{**TOPOLOGY_SIZES, **SIZINGS[sizing]})
    return comp if is_valid_comp_params(comp) else None


def _measure(run_dir: Path, tb: CompTbParams, *, noise: bool):
    """One Spectre run of the comparator testbench, as a measurement."""

    from flow.circuit.results import convert_raw_comp_to_measurement, read_raw_transient

    raw, tb, readbacks = _run_comp_sim(
        run_dir,
        tb,
        candidate_id=run_dir.name,
        candidate_label=run_dir.name,
        topology_index=0,
        size_profile="sweep",
        noise=noise,
    )
    measurement = convert_raw_comp_to_measurement(
        read_raw_transient(raw), params=tb, raw_path=raw, signal_names=comp_signal_names()
    )
    raw.unlink()  # the measurement keeps the waveforms; a noise run's raw file is tens of MB
    return replace(measurement, info=replace(measurement.info, readbacks={**measurement.info.readbacks, **readbacks}))


def characterize(run_dir: Path, pdk: str, comp: CompParams) -> Record:
    from flow.analysis.comp import analyze_comp_offset_noise
    from flow.analysis.io import write_measurement
    from flow.comp.analysis import analyze_comp_delay, analyze_comp_power, analyze_comp_timing

    supply = importlib.import_module(f"pdk.{pdk}.hdl21.site").install.supply_voltage(h.pdk.Corner.TYP)
    timing = {"pdk": pdk, "reset_time_s": 1e-9, "evaluation_time_s": 2e-9, "transition_time_s": 20e-12}

    def bench(
        vdd: float, cm: float, inputs: tuple[float, ...], conversions: int, spacing: float = 2e-12
    ) -> CompTbParams:
        return CompTbParams(
            comp=comp,
            vdd=round(vdd, 4),
            vin_cm_values_v=(round(cm, 4),),
            vin_diff_values_v=inputs,
            conversions=conversions,
            waveform_sample_interval_s=spacing,
            **timing,
        )

    def delay_energy(measurement) -> tuple[float, float]:
        delay = analyze_comp_delay([measurement], timing=analyze_comp_timing([measurement])).delay_s
        return float(np.nanmax(delay)), float(analyze_comp_power([measurement]).energy_per_decision_j[0])

    cm = NOMINAL_CM * supply
    waves = {}
    small = _measure(run_dir / "small", bench(supply, cm, (SMALL_V,), 3), noise=False)
    large = _measure(run_dir / "large", bench(supply, cm, (LARGE_V,), 3), noise=False)
    meta = _measure(run_dir / "metastability", bench(supply, cm, METASTABILITY_V, 2), noise=False)
    for name, folder, measurement in (
        ("0.5 mV input", "small", small),
        ("100 mV input", "large", large),
        ("metastability", "metastability", meta),
    ):
        path = run_dir / folder / "result.h5"
        write_measurement(path, measurement)
        waves[name] = str(path.relative_to(Path(__file__).resolve().parents[2]))
    delay_small, energy_small = delay_energy(small)
    delay_large, energy_large = delay_energy(large)
    meta_delay = analyze_comp_delay([meta], timing=analyze_comp_timing([meta]))

    scurves = {}
    for fraction in CM_SWEEP:
        measurement = _measure(
            run_dir / f"scurve_cm{round(fraction * 24)}",
            bench(supply, fraction * supply, SCURVE_V, 40, 10e-12),
            noise=True,
        )
        scurves[fraction] = analyze_comp_offset_noise([measurement])

    supply_points = {}
    for factor in SUPPLY_SWEEP:
        vdd = factor * supply
        measurement = _measure(
            run_dir / f"supply_{round(factor * 100)}", bench(vdd, NOMINAL_CM * vdd, (SMALL_V, LARGE_V), 2), noise=False
        )
        delay = analyze_comp_delay([measurement], timing=analyze_comp_timing([measurement]))
        supply_points[factor] = (
            float(delay.delay_s[0, 0]),
            float(delay.delay_s[0, -1]),
            float(analyze_comp_power([measurement]).energy_per_decision_j[0]),
        )

    nominal = scurves[NOMINAL_CM]

    def valid(result) -> bool:
        return result.validity == "valid"

    return Record(
        metrics={
            "delay_0p5mv_s": delay_small,
            "delay_100mv_s": delay_large,
            "energy_0p5mv_j": energy_small,
            "energy_100mv_j": energy_large,
            "noise_v": nominal.noise_sigma_v if valid(nominal) else math.nan,
            "offset_v": nominal.offset_v if valid(nominal) else math.nan,
            "noise_max_v": max((r.noise_sigma_v for r in scurves.values() if valid(r)), default=math.nan),
            "delay_max_supply_s": max(point[0] for point in supply_points.values()),
        },
        details=[
            Detail(
                name="metastability",
                title="Delay over the input (nominal common mode)",
                x_label="Differential input (V)",
                y_label="Clock-to-decision delay (s)",
                x=list(meta_delay.vin_diff_v),
                series={"delay": list(meta_delay.delay_s[0])},
                x_log=True,
            ),
            Detail(
                name="noise_cm",
                title="Input-referred noise over the common mode",
                x_label="Input common mode (V)",
                y_label="Input-referred noise (V)",
                x=[fraction * supply for fraction in CM_SWEEP],
                series={"noise": [r.noise_sigma_v if valid(r) else math.nan for r in scurves.values()]},
            ),
            Detail(
                name="offset_cm",
                title="Offset over the common mode (no mismatch: systematic)",
                x_label="Input common mode (V)",
                y_label="Offset (V)",
                x=[fraction * supply for fraction in CM_SWEEP],
                series={"offset": [r.offset_v if valid(r) else math.nan for r in scurves.values()]},
            ),
            Detail(
                name="delay_supply",
                title="Delay over the supply",
                x_label="Supply over nominal",
                y_label="Clock-to-decision delay (s)",
                x=list(SUPPLY_SWEEP),
                series={
                    "0.5 mV": [point[0] for point in supply_points.values()],
                    "100 mV": [point[1] for point in supply_points.values()],
                },
            ),
            Detail(
                name="energy_supply",
                title="Energy per decision over the supply",
                x_label="Supply over nominal",
                y_label="Energy per decision (J)",
                x=list(SUPPLY_SWEEP),
                series={"energy": [point[2] for point in supply_points.values()]},
            ),
            Detail(
                name="scurve",
                title="Decision probability (nominal common mode, transient noise)",
                x_label="Differential input (V)",
                y_label="P(high)",
                x=list(nominal.vin_diff_v),
                series={"P(high)": list(nominal.decision_probability)},
            ),
        ],
        waves=waves,
    )


def layout_netlist(out_dir: Path, pdk: str, comp: CompParams) -> Path:
    """The all-transistor netlist with the PDK's library cells it contains recognized
    (``flow.layout.stdcells``), as ``flow.comp.layout`` lays out a comparator without a floorplan."""

    from flow.layout.pdkproc import in_pdk

    logic = importlib.import_module(f"pdk.{pdk}.hdl21").pdk_logic
    transistors = write_netlist(
        CompParams(**{**comp.__dict__, "output_stage": OutputStage.TRANSISTORS}), out_dir / "comp_transistors.sp", logic
    )
    return in_pdk(pdk, "flow.layout.stdcells", "recognize_file", transistors, out_dir / "comp.sp")


def layout_floorplan(out_dir: Path, pdk: str, topology: str, comp: CompParams) -> tuple[Path, Path]:
    """The topology's hand-written floorplan (``design/layout/comp_<topology>.json``) with the
    netlist it places, the standard-cell output stage's (``flow.comp.layout``)."""

    from flow.comp.layout import FLOORPLANS

    logic = importlib.import_module(f"pdk.{pdk}.hdl21").pdk_logic
    name = f"comp_{topology}"
    stdcells = CompParams(**{**comp.__dict__, "output_stage": OutputStage.STDCELLS})
    return write_netlist(stdcells, out_dir / f"{name}.sp", logic), FLOORPLANS / f"{name}.json"
