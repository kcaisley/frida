"""The charge-sensitive amplifier's design space (``flow.sweep``): the characterization's four
cases at seven sizes, in every PDK.

Each instance on the characterization's bench (``flow.csa.sim``: 100 fF of detector, the charge
through 1 fF, 10 fF of load, a 4 µA load, 10 nA of discharge, the Krummenacher reference at 45 %
of the supply) at its own supply: the response to 0.25, 0.5, 1 and 2 fC (gain, peaking and rise
time at the smallest, the gain's linearity to the largest, its time over threshold and return to
the baseline) and, but for the reset amplifier, the output noise from 1 Hz to 1 GHz without
charge (rms, and over the smallest charge's gain the ENC). Over the supply (90 to 120 % of its
own) the smallest charge's response and the noise again. Seven to eleven Spectre runs, under a
minute.
"""

from __future__ import annotations

import dataclasses
import importlib
import math
import shutil
from datetime import UTC, datetime
from pathlib import Path

import hdl21 as h
import numpy as np
from hdl21.prefix import f

from flow.pipeline import Plot, Record

from .sim import CHARGES_C, VREF, CsaTbParams, _run_csa_sim, csa_signal_names
from .subckt import CASES, Csa, CsaParams, Feedback, is_valid_csa_params, write_netlist

ROOT = Path(__file__).resolve().parents[2]
GENERATOR = Csa
# the characterization's amplifiers (flow.csa.subckt.CASES): input type, feedback, and the
# feedback capacitor and device's length
STRUCTURE = ("input_xtors", "feedback")
STRUCTURES = [{name: getattr(csa, name) for name in (*STRUCTURE, "cf", "fb_l")} for csa in CASES.values()]
# the amplifier's widths (input device, cascode, load) scaled together (x0.5 to x4), the input
# device alone twice as wide or long, and the load at twice its length; the feedback as it is
DEFAULT = CsaParams()
WIDTHS = ("in_w", "cas_w", "load_w")
SIZES = [
    {name: getattr(DEFAULT, name) // 2 for name in WIDTHS},
    {},
    {name: 2 * getattr(DEFAULT, name) for name in WIDTHS},
    {name: 4 * getattr(DEFAULT, name) for name in WIDTHS},
    {"in_w": 2 * DEFAULT.in_w},
    {"in_l": 2 * DEFAULT.in_l},
    {"load_l": 2 * DEFAULT.load_l},
]
SUPPLY_SWEEP = (0.9, 1.0, 1.1, 1.2)
SMALL_C, LARGE_C = min(CHARGES_C), max(CHARGES_C)
PULSE_STEP_S = 1e-9  # the responses' detail, sampled from the record


def instances(pdk: str) -> list[CsaParams]:
    """Every amplifier at every size, in every PDK."""
    csas = (CsaParams(**structure, **sizes) for structure in STRUCTURES for sizes in SIZES)
    return [csa for csa in csas if is_valid_csa_params(csa)]


def _measure(run_dir: Path, tb: CsaTbParams):
    """One Spectre run of the bench as ``csa_characterization`` converts it: a ``MeasCsa``, or
    without charge a ``MeasCsaNoise``."""

    from vlsirtools.spice.spectre import parse_psfascii

    from flow.analysis.types import MeasInfo
    from flow.circuit.results import read_transient_wave

    from .analysis import MeasCsa, MeasCsaNoise

    raw = _run_csa_sim(run_dir, tb)
    info = MeasInfo(
        backend="spice",
        timestamp_utc=datetime.fromtimestamp(raw.stat().st_mtime, tz=UTC),
        instruments={"simulator": "Spectre"},
        readbacks={"pdk": tb.pdk, "raw_file": raw.name, "supply_current_convention": "positive_current_draw"},
    )
    common = {"group": None, "index": None, "dut": tb.csa, "info": info, "param": tb}
    if not float(tb.charge_c):
        analyses = parse_psfascii(raw)
        shutil.rmtree(raw)  # PSF ASCII: a directory of every analysis, read
        op, noise = analyses["op"].data, analyses["noise"].data
        info.readbacks.update(
            {
                "op_supply_current_a": -float(np.real(op["xtop.vvdd:p"][0])),
                "op_out_v": float(np.real(op["xtop.out"][0])),
                "op_inp_v": float(np.real(op["xtop.inp"][0])),
            }
        )
        return MeasCsaNoise(
            **common,
            frequency_hz=np.real(np.asarray(noise["freq"])).astype(np.float64),
            output_noise_v_rthz=np.asarray(noise["out"], dtype=np.float64),
        )
    interval = tb.waveform_sample_interval_s
    wave, points = read_transient_wave(raw, csa_signal_names(), interval, supply_rails=("vdd",))
    raw.unlink()  # the measurement keeps the waveforms
    info.readbacks.update({"waveform_sample_interval_s": interval, "raw_points": points})
    return MeasCsa(**common, trial_index=np.arange(1, dtype=np.int64), wave=wave)


def characterize(run_dir: Path, pdk: str, csa: CsaParams) -> Record:
    from flow.analysis.io import write_measurement

    from .analysis import analyze_csa_noise, analyze_csa_pulse

    supply = importlib.import_module(f"pdk.{pdk}.hdl21.site").install.supply_voltage(h.pdk.Corner.TYP)

    def bench(vdd: float, charge: float) -> CsaTbParams:
        return CsaTbParams(pdk=pdk, csa=csa, vdd=round(vdd, 4), vref=round(VREF * vdd, 4), charge_c=charge)

    # a reset amplifier holds no operating point at rest: no noise bench
    has_noise = csa.feedback != Feedback.RESET
    responses = {charge: _measure(run_dir / f"q{round(charge * 1e18)}", bench(supply, charge)) for charge in CHARGES_C}
    pulse = analyze_csa_pulse(list(responses.values()))
    noise = analyze_csa_noise([_measure(run_dir / "noise", bench(supply, 0.0))], pulse=pulse) if has_noise else None
    waves = {}
    for name, charge in (("0.25 fC", SMALL_C), ("2 fC", LARGE_C)):
        path = run_dir / f"q{round(charge * 1e18)}" / "result.h5"
        write_measurement(path, responses[charge])
        waves[name] = str(path.relative_to(ROOT))

    # over the supply: the smallest charge's response and the noise, the 100 % point the nominal one
    supply_points = {}
    for factor in SUPPLY_SWEEP:
        if factor == 1.0:
            supply_points[factor] = (pulse, noise)
            continue
        folder = run_dir / f"supply_{round(factor * 100)}"
        point = analyze_csa_pulse([_measure(folder / "pulse", bench(factor * supply, SMALL_C))])
        point_noise = (
            analyze_csa_noise([_measure(folder / "noise", bench(factor * supply, 0.0))], pulse=point)
            if has_noise
            else None
        )
        supply_points[factor] = (point, point_noise)

    def enc(result) -> float:
        return float(result.enc_electrons[0]) if result is not None else math.nan

    # the pulse results' rows by charge: the smallest first, each supply point's only one
    small, large = 0, len(CHARGES_C) - 1
    gains = [float(point.gain_v_per_c[small]) for point, _ in supply_points.values()]
    peakings = [float(point.peaking_time_s[small]) for point, _ in supply_points.values()]
    encs = [enc(point_noise) for _, point_noise in supply_points.values()]
    powers = [factor * supply * float(point.supply_current_a[small]) for factor, (point, _) in supply_points.items()]
    stride = max(1, round(PULSE_STEP_S / bench(supply, SMALL_C).waveform_sample_interval_s))
    charges = pulse.charge_c.tolist()
    return Record(
        metrics={
            "gain_v_per_c": float(pulse.gain_v_per_c[small]),
            "peaking_time_s": float(pulse.peaking_time_s[small]),
            "rise_time_s": float(pulse.rise_time_s[small]),
            "baseline_v": float(pulse.baseline_v[small]),
            "linearity_ratio": float(pulse.gain_v_per_c[large] / pulse.gain_v_per_c[small]),
            "tot_2fc_s": float(pulse.tot_s[large]),
            "return_2fc_s": float(pulse.return_time_s[large]),
            "power_w": supply * float(pulse.supply_current_a[small]),
            "noise_rms_v": float(noise.noise_rms_v[0]) if noise is not None else math.nan,
            "enc_electrons": enc(noise),
            "gain_min_supply_v_per_c": float(np.min(gains)),
            "peaking_max_supply_s": float(np.max(peakings)),  # NaN for a reset amplifier
            "enc_max_supply_electrons": float(np.max(encs)),
        },
        details=[
            Plot(
                name="pulse",
                title="Response to each charge, from the injection",
                x_label="Time from the injection (s)",
                y_label="Output excursion (V)",
                x=pulse.time_s[::stride].tolist(),
                series={f"{charge * 1e15:g} fC": row[::stride].tolist() for charge, row in zip(charges, pulse.pulse_v)},
            ),
            Plot(
                name="amplitude_charge",
                title="Amplitude over the injected charge",
                x_label="Injected charge (C)",
                y_label="Amplitude (V)",
                x=charges,
                series={"amplitude": pulse.amplitude_v.tolist()},
                x_log=True,
                y_log=True,
            ),
            Plot(
                name="gain_charge",
                title="Gain over the injected charge",
                x_label="Injected charge (C)",
                y_label="Gain (V/C)",
                x=charges,
                series={"gain": pulse.gain_v_per_c.tolist()},
                x_log=True,
            ),
            Plot(
                name="tot_charge",
                title="Time over threshold (half the smallest charge's amplitude) over the charge",
                x_label="Injected charge (C)",
                y_label="Time over threshold (s)",
                x=charges,
                series={"time over threshold": pulse.tot_s.tolist()},
                x_log=True,
            ),
            *(
                [
                    Plot(
                        name="noise_density",
                        title="Output noise density without charge",
                        x_label="Frequency (Hz)",
                        y_label="Output noise (V/√Hz)",
                        x=noise.frequency_hz.tolist(),
                        series={"noise": noise.output_noise_v_rthz[0].tolist()},
                        x_log=True,
                        y_log=True,
                    )
                ]
                if noise is not None
                else []
            ),
            Plot(
                name="gain_supply",
                title="Gain over the supply (0.25 fC)",
                x_label="Supply over nominal",
                y_label="Gain (V/C)",
                x=list(SUPPLY_SWEEP),
                series={"gain": gains},
            ),
            Plot(
                name="peaking_supply",
                title="Peaking time over the supply (0.25 fC)",
                x_label="Supply over nominal",
                y_label="Peaking time (s)",
                x=list(SUPPLY_SWEEP),
                series={"peaking time": peakings},
            ),
            Plot(
                name="enc_supply",
                title="Equivalent noise charge over the supply",
                x_label="Supply over nominal",
                y_label="ENC (electrons)",
                x=list(SUPPLY_SWEEP),
                series={"ENC": encs},
            ),
            Plot(
                name="power_supply",
                title="Power over the supply",
                x_label="Supply over nominal",
                y_label="Power (W)",
                x=list(SUPPLY_SWEEP),
                series={"power": powers},
            ),
        ],
        waves=waves,
    )


def layout_netlist(out_dir: Path, pdk: str, csa: CsaParams) -> Path:
    """The transistor netlist ``flow.csa.layout`` places (without the feedback capacitor, which the
    row cells do not draw), with the PDK's library cells it contains recognized
    (``flow.layout.stdcells``), for ALIGN to lay out without a floorplan."""

    from flow.layout.pdkproc import in_pdk

    logic = importlib.import_module(f"pdk.{pdk}.hdl21").pdk_logic
    transistors = write_netlist(dataclasses.replace(csa, cf=0 * f), out_dir / "csa_transistors.sp", logic)
    return in_pdk(pdk, "flow.layout.stdcells", "recognize_file", transistors, out_dir / "csa.sp")
