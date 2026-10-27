"""The MOS capacitor's design space (``flow.sweep``): the characterization's four capacitors at six
sizings, in every PDK.

Each instance as the characterization runs it (``flow.moscap.sim``): an operating point and the AC
response from 1 MHz to 100 GHz with the stimulus on the capacitor's own net, over its bias (a
decap's supply from 1/12 to 13/12 of the PDK's own, a two-net capacitor's gate plate over its
channel plate between minus and plus the supply). At the nominal bias (a decap at the supply, an
NMOS capacitor that far above its channel plate, a PMOS one that far below) the capacitance, its
density over the gate area, the series resistance near 1 GHz, the quality corner and the leakage;
over the bias the C-V, the leakage and the quality factor; over frequency the capacitance and the
quality factor. Thirteen or twenty-five Spectre runs, under a minute.
"""

from __future__ import annotations

import importlib
import math
from pathlib import Path

import hdl21 as h
import numpy as np

from flow.pipeline import Plot, Record

from .sim import BIAS_SWEEP, SUPPLY_SWEEP, MosCapTbParams, _run_moscap_sim, moscap_measurement
from .subckt import CASES, Devices, Mode, MosCap, MosCapParams, is_valid_moscap_params, write_netlist

GENERATOR = MosCap
# the characterization's capacitors (flow.moscap.subckt.CASES): a decap of NMOS units or of an
# NMOS and a PMOS, a two-net NMOS or PMOS
STRUCTURE = ("mode", "devices", "units")
STRUCTURES = [{key: getattr(case, key) for key in STRUCTURE} for case in CASES.values()]
# the width scaled (x0.5 to x4: the capacitance), and the length halved or doubled (the
# channel's series resistance, so the quality factor, against the capacitance per width)
BASE = MosCapParams()
SIZES = [
    {"w": BASE.w // 2},
    {},
    {"w": 2 * BASE.w},
    {"w": 4 * BASE.w},
    {"l": BASE.l // 2},
    {"l": 2 * BASE.l},
]


def instances(pdk: str) -> list[MosCapParams]:
    """Every capacitor at every size, in every PDK."""
    moscaps = (MosCapParams(**structure, **sizes) for structure in STRUCTURES for sizes in SIZES)
    return [moscap for moscap in moscaps if is_valid_moscap_params(moscap)]


def characterize(run_dir: Path, pdk: str, moscap: MosCapParams) -> Record:
    from flow.moscap.analysis import analyze_moscap_cv
    from flow.sweep import geometry

    supply = importlib.import_module(f"pdk.{pdk}.hdl21.site").install.supply_voltage(h.pdk.Corner.TYP)
    decap = moscap.mode == Mode.DECAP
    nominal = -1.0 if moscap.devices == Devices.PMOS and not decap else 1.0
    measurements = []
    for step in SUPPLY_SWEEP if decap else BIAS_SWEEP:
        bias = round(step * supply, 4)
        # a decap's bias is its supply (its unused plates on vss); a two-net capacitor's the gate
        # plate above the channel plate, either on vss
        tb = (
            MosCapTbParams(pdk=pdk, moscap=moscap, vdd=bias, vtop=0.0)
            if decap
            else MosCapTbParams(pdk=pdk, moscap=moscap, vdd=supply, vtop=max(bias, 0.0), vbot=max(-bias, 0.0))
        )
        folder = f"bias{round(bias * 1e3)}"
        raw = _run_moscap_sim(run_dir / folder, tb)
        measurements.append(
            moscap_measurement(
                raw,
                tb,
                {"pdk": pdk, "case": run_dir.name, "nominal": step == nominal, "bias_mv": round(bias * 1e3)},
            )
        )
        raw.unlink()  # the measurement keeps the admittance

    cv = analyze_moscap_cv(measurements)
    at = (SUPPLY_SWEEP if decap else BIAS_SWEEP).index(nominal)
    area = geometry(MosCap(moscap), pdk)["device_area_um2"]
    bias_label = "Supply (V)" if decap else "Gate plate over channel plate (V)"
    return Record(
        metrics={
            "c_f": float(cv.capacitance_f[at]),
            "c_density_f_um2": float(cv.capacitance_f[at]) / area,
            "c_min_f": float(np.min(cv.capacitance_f)),
            "esr_ohm": float(cv.series_resistance_ohm[at]),
            "q_corner_hz": float(cv.corner_hz[at]),
            "leakage_a": abs(float(cv.leakage_a[at])),
        },
        details=[
            Plot(
                name="cv",
                title="Capacitance over the bias (C-V, at 1 MHz)",
                x_label=bias_label,
                y_label="Capacitance (F)",
                x=list(cv.bias_v),
                series={"capacitance": list(cv.capacitance_f)},
            ),
            Plot(
                name="leakage_bias",
                title="Leakage over the bias",
                x_label=bias_label,
                y_label="|Leakage| (A)",
                x=list(cv.bias_v),
                series={"leakage": list(np.abs(cv.leakage_a))},
                y_log=True,
            ),
            Plot(
                name="quality_bias",
                title=f"Quality factor over the bias (at {cv.loss_frequency_hz / 1e9:.2g} GHz)",
                x_label=bias_label,
                y_label="Quality factor",
                x=list(cv.bias_v),
                series={"quality": [q if math.isfinite(q) else math.nan for q in cv.quality]},
                y_log=True,
            ),
            Plot(
                name="c_frequency",
                title="Capacitance over frequency (nominal bias)",
                x_label="Frequency (Hz)",
                y_label="Capacitance (F)",
                x=list(cv.frequency_hz),
                series={"capacitance": list(cv.capacitance_spectrum_f[at])},
                x_log=True,
            ),
            Plot(
                name="quality_frequency",
                title="Quality factor over frequency (nominal bias)",
                x_label="Frequency (Hz)",
                y_label="Quality factor",
                x=list(cv.frequency_hz),
                series={"quality": [q if math.isfinite(q) else math.nan for q in cv.quality_spectrum[at]]},
                x_log=True,
                y_log=True,
            ),
        ],
    )


def layout_netlist(out_dir: Path, pdk: str, moscap: MosCapParams) -> Path:
    """The all-transistor netlist (devices fingered to the row cells) with any library cells it
    contains recognized (``flow.layout.stdcells``), as ``flow.moscap.layout`` places a capacitor,
    without its floorplan."""

    from flow.layout.pdkproc import in_pdk

    logic = importlib.import_module(f"pdk.{pdk}.hdl21").pdk_logic
    transistors = write_netlist(moscap, out_dir / "moscap_transistors.sp", logic)
    return in_pdk(pdk, "flow.layout.stdcells", "recognize_file", transistors, out_dir / "moscap.sp")
