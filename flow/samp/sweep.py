"""The sampling switch's design space (``flow.sweep``): the characterization's four switches at
six sizes (a bootstrapped one at seven), in every PDK.

Each instance as the characterization runs it (``flow.samp.sim``): into 1 pF at a 10 ns clock (5 ns
tracking), its input stepping a twelfth of the supply each period, six periods. Over the input
level (1/12 to 11/12 of the supply) the on-resistance into the load, the track error, the pedestal
and the input's feedthrough while holding; at the nominal point (mid-supply input) those and the
bandwidth and droop; over the supply (90 to 120 % of its own, mid-supply input) the on-resistance
and pedestal. Fourteen Spectre runs, about a minute in all.
"""

from __future__ import annotations

import importlib
import math
from pathlib import Path

import hdl21 as h
import numpy as np
from hdl21.prefix import p

from flow.pipeline import Plot, Record

from .sim import NOMINAL_VIN, VIN_SWEEP, SampTbParams, _run_samp_sim, samp_measurement
from .subckt import CASES, Samp, SampParams, is_valid_samp_params, write_netlist

GENERATOR = Samp
# the characterization's four switches (flow.samp.subckt.CASES): the switch, its dummies, a
# bootstrapped gate
STRUCTURE = ("switch_type", "dummy", "bootstrap")
STRUCTURES = [{key: getattr(case, key) for key in STRUCTURE} for case in CASES.values()]
# every width scaled together (x0.25 to x4: the switch, the bootstrap's helpers and its boost
# capacitor), the switch at twice its length, and the boost capacitor alone doubled (a bootstrap's
# only); no width under 4 units (the finest PDK's minimum width: the 4-unit helpers stay)
BASE = SampParams()
WIDTHS = ("mos_w", "boot_w", "cap_w")
X2 = {name: 2 * getattr(BASE, name) for name in WIDTHS}
X4 = {name: 4 * getattr(BASE, name) for name in WIDTHS}
BOOST_X2 = {"cap_w": 2 * BASE.cap_w}
SIZES = [
    {name: max(4, getattr(BASE, name) // 4) for name in WIDTHS},
    {name: max(4, getattr(BASE, name) // 2) for name in WIDTHS},
    {},
    X2,
    X4,
    {"mos_l": 2 * BASE.mos_l},
    BOOST_X2,
]
SUPPLY_SWEEP = (0.9, 1.0, 1.1, 1.2)
WAVE_VIN = (VIN_SWEEP[0], NOMINAL_VIN, VIN_SWEEP[-1])  # the transients kept


def instances(pdk: str) -> list[SampParams]:
    """Every switch at every size, in every PDK; the boost capacitor sized only where there is one
    (without a bootstrap the same circuit as at its base size)."""
    switches = (
        SampParams(**structure, **sizes)
        for structure in STRUCTURES
        for sizes in SIZES
        if sizes is not BOOST_X2 or structure["bootstrap"]
    )
    return [samp for samp in switches if is_valid_samp_params(samp)]


def characterize(run_dir: Path, pdk: str, samp: SampParams) -> Record:
    from flow.analysis.io import write_measurement
    from flow.samp.analysis import analyze_samp_hold, analyze_samp_track

    supply = importlib.import_module(f"pdk.{pdk}.hdl21.site").install.supply_voltage(h.pdk.Corner.TYP)

    def measure(folder: str, vdd: float, vin: float):
        """One Spectre run of the characterization's bench, as a measurement."""
        tb = SampTbParams(
            pdk=pdk,
            samp=samp,
            vdd=round(vdd, 4),
            input_voltage=round(vin, 4),
            input_step_v=round(vdd / 12, 4),
            cload=1 * p,
            clock_period_s=10e-9,
            clock_high_time_s=5e-9,
            clock_transition_time_s=50e-12,
            waveform_sample_interval_s=5e-12,
            periods=6,
        )
        raw = _run_samp_sim(run_dir / folder, tb)
        measurement = samp_measurement(raw, tb, {"pdk": pdk, "case": run_dir.name, "sweep": folder})
        raw.unlink()  # the measurement keeps the waveforms
        return measurement

    by_vin = {fraction: measure(f"vin_{round(fraction * 12)}", supply, fraction * supply) for fraction in VIN_SWEEP}
    waves = {}
    for fraction in WAVE_VIN:
        path = run_dir / f"vin_{round(fraction * 12)}" / "result.h5"
        write_measurement(path, by_vin[fraction])
        waves[f"input {round(fraction * 12)}/12 of the supply"] = str(
            path.relative_to(Path(__file__).resolve().parents[2])
        )
    by_supply = {
        factor: by_vin[NOMINAL_VIN]
        if factor == 1.0
        else measure(f"supply_{round(factor * 100)}", factor * supply, NOMINAL_VIN * factor * supply)
        for factor in SUPPLY_SWEEP
    }

    track, hold = analyze_samp_track(list(by_vin.values())), analyze_samp_hold(list(by_vin.values()))
    supply_track = analyze_samp_track(list(by_supply.values()))
    supply_hold = analyze_samp_hold(list(by_supply.values()))
    nominal = VIN_SWEEP.index(NOMINAL_VIN)
    settled = np.isfinite(track.on_resistance_ohm)

    def most(values: np.ndarray) -> float:
        """The largest magnitude where the point settled to a value."""
        finite = np.abs(values[np.isfinite(values)])
        return float(finite.max()) if finite.size else math.nan

    feedthrough_db = 20 * np.log10(np.abs(hold.feedthrough))
    return Record(
        metrics={
            "ron_ohm": float(track.on_resistance_ohm[nominal]),
            "ron_max_ohm": most(track.on_resistance_ohm),
            "input_range_v": float(np.ptp(track.vin_v[settled])) if settled.any() else 0.0,
            "bandwidth_hz": float(track.bandwidth_hz[nominal]),
            "track_error_v": float(track.track_error_v[nominal]),
            "pedestal_v": float(hold.pedestal_v[nominal]),
            "pedestal_max_v": most(hold.pedestal_v),
            "droop_v_s": float(hold.droop_v_per_s[nominal]),
            "feedthrough_db": float(feedthrough_db[nominal]),
            "ron_max_supply_ohm": most(supply_track.on_resistance_ohm),
        },
        details=[
            Plot(
                name="ron_vin",
                title="On-resistance into 1 pF over the input level",
                x_label="Input level (V)",
                y_label="On-resistance (ohm)",
                x=list(track.vin_v),
                series={"on-resistance": list(track.on_resistance_ohm)},
                y_log=True,
            ),
            Plot(
                name="track_error_vin",
                title="Track error at the end of tracking over the input level",
                x_label="Input level (V)",
                y_label="Output minus input (V)",
                x=list(track.vin_v),
                series={"track error": list(track.track_error_v)},
            ),
            Plot(
                name="pedestal_vin",
                title="Pedestal over the input level",
                x_label="Input level (V)",
                y_label="Pedestal (V)",
                x=list(hold.vin_v),
                series={"pedestal": list(hold.pedestal_v)},
            ),
            Plot(
                name="feedthrough_vin",
                title="Input feedthrough while holding, over the input level",
                x_label="Input level (V)",
                y_label="Feedthrough (dB)",
                x=list(hold.vin_v),
                series={"feedthrough": list(feedthrough_db)},
            ),
            Plot(
                name="ron_supply",
                title="On-resistance over the supply (mid-supply input)",
                x_label="Supply over nominal",
                y_label="On-resistance (ohm)",
                x=list(SUPPLY_SWEEP),
                series={"on-resistance": list(supply_track.on_resistance_ohm)},
                y_log=True,
            ),
            Plot(
                name="pedestal_supply",
                title="Pedestal over the supply (mid-supply input)",
                x_label="Supply over nominal",
                y_label="Pedestal (V)",
                x=list(SUPPLY_SWEEP),
                series={"pedestal": list(supply_hold.pedestal_v)},
            ),
        ],
        waves=waves,
    )


def layout_netlist(out_dir: Path, pdk: str, samp: SampParams) -> Path:
    """The all-transistor netlist (devices fingered to the row cells) with any library cells it
    contains recognized (``flow.layout.stdcells``), as ``flow.samp.layout`` places a switch, without
    its floorplan."""

    from flow.layout.pdkproc import in_pdk

    logic = importlib.import_module(f"pdk.{pdk}.hdl21").pdk_logic
    transistors = write_netlist(samp, out_dir / "samp_transistors.sp", logic)
    return in_pdk(pdk, "flow.layout.stdcells", "recognize_file", transistors, out_dir / "samp.sp")
