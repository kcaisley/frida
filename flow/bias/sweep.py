"""The cascode bias generator's design space (``flow.sweep``): the characterization's two cases at
eight sizes, in every PDK.

Each instance on the characterization's bench (``flow.bias.sim``: the reference current into
``vbn``, cascoded NMOS and PMOS test mirrors on the four gates, their outputs swept from ground to
the supply) at its own supply and 10 µA: each test mirror's current over the reference at
mid-supply, its output resistance, compliance (from its rail, where its current stays within 5 %)
and mirror device's drain-source voltage, the four gate voltages and the generator's power. Over
the reference (1 to 50 µA) and the supply (90 to 120 % of its own) the mirrors' ratios and the
gate voltages again. Nine Spectre DC sweeps, well under a minute.
"""

from __future__ import annotations

import dataclasses
import importlib
from datetime import UTC, datetime
from pathlib import Path

import hdl21 as h
import numpy as np

from flow.pipeline import Plot, Record

from .sim import IREF_SWEEP_A, NOMINAL_IREF_A, BiasTbParams, _run_bias_sim, bias_signal_names
from .subckt import CASES, Bias, BiasParams, is_valid_bias_params, write_netlist

ROOT = Path(__file__).resolve().parents[2]
GENERATOR = Bias
# the characterization's cases (flow.bias.subckt.CASES): one circuit, the cascode-gate diodes' sizes
# setting their W/L
STRUCTURE = ()
# factors on each case's sizes, so the diodes keep their fraction of the mirror devices' W/L: every
# W/L x0.5 to x4, every mirror and diode device twice as wide and long (its W/L kept), the
# cascodes twice as long, the cascode-gate diodes at half their W/L, the start-up follower four
# times as wide. A width that cannot shrink so far keeps its size and its length grows instead.
WL = ("n_w", "p_w", "casn_w", "casp_w")
FACTORS = [
    dict.fromkeys(WL, 0.5),
    {},
    dict.fromkeys(WL, 2),
    dict.fromkeys(WL, 4),
    dict.fromkeys(("n_w", "n_l", "p_w", "p_l", "casn_w", "casn_l", "casp_w", "casp_l"), 2),
    {"cas_l": 2},
    dict.fromkeys(("casn_w", "casp_w"), 0.5),
    {"start_w": 4},
]
SUPPLY_SWEEP = (0.9, 1.0, 1.1, 1.2)
GATES = ("vbn", "vcasn", "vbp", "vcasp")


def scaled(case: BiasParams, factors: dict[str, float]) -> BiasParams:
    """``case`` with its sizes scaled by ``factors``."""
    sizes = {}
    for name, factor in factors.items():
        value = getattr(case, name) * factor
        if value >= 1 and value == int(value):
            sizes[name] = int(value)
        else:  # a width under one unit: its length grows instead, for the same W/L
            length = f"{name[:-2]}_l"
            sizes[length] = round(sizes.get(length, getattr(case, length)) / factor)
    return dataclasses.replace(case, **sizes)


def instances(pdk: str) -> list[BiasParams]:
    """Every case at every scaling, in every PDK."""
    biases = (scaled(case, factors) for case in CASES.values() for factors in FACTORS)
    return [bias for bias in biases if is_valid_bias_params(bias)]


def _measure(run_dir: Path, tb: BiasTbParams):
    """One Spectre run of the bench as ``bias_characterization`` converts it, a ``MeasBias``."""

    from vlsirtools.spice.spectre import parse_nutbin

    from flow.analysis.types import MeasInfo

    from .analysis import MeasBias

    raw = _run_bias_sim(run_dir, tb)
    with raw.open("rb") as stream:
        analyses = parse_nutbin(stream)
    names = bias_signal_names()
    op = {names[key]: float(np.real(value[0])) for key, value in analyses["op"].data.items() if key in names}
    sweep_n, sweep_p = analyses["sweep_n"].data, analyses["sweep_p"].data
    info = MeasInfo(
        backend="spice",
        timestamp_utc=datetime.fromtimestamp(raw.stat().st_mtime, tz=UTC),
        instruments={"simulator": "Spectre"},
        readbacks={
            "pdk": tb.pdk,
            "raw_file": raw.name,
            **{f"op_{key}_v": value for key, value in op.items() if not key.startswith("i(")},
            "op_supply_current_a": -op["i(vdd)"],
        },
    )
    raw.unlink()
    # a source's current flows into its positive pin: the NMOS mirror's out of its source, the
    # PMOS one's into its source
    return MeasBias(
        group=None,
        index=None,
        dut=tb.bias,
        info=info,
        param=tb,
        vout_v=np.real(np.asarray(sweep_n["xtop.outn"])).astype(np.float64),
        n_current_a=np.abs(np.real(np.asarray(sweep_n["xtop.voutn:p"]))).astype(np.float64),
        p_current_a=np.abs(np.real(np.asarray(sweep_p["xtop.voutp:p"]))).astype(np.float64),
    )


def characterize(run_dir: Path, pdk: str, bias: BiasParams) -> Record:
    from .analysis import analyze_bias_mirror

    supply = importlib.import_module(f"pdk.{pdk}.hdl21.site").install.supply_voltage(h.pdk.Corner.TYP)

    def bench(vdd: float, iref: float) -> BiasTbParams:
        return BiasTbParams(pdk=pdk, bias=bias, vdd=round(vdd, 4), iref=iref, vout_step_v=round(vdd / 48, 6))

    # over the reference at the supply, then over the supply but its 100 % at the nominal reference
    points = [(f"iref{round(iref * 1e9)}na", bench(supply, iref)) for iref in IREF_SWEEP_A]
    points += [
        (f"supply_{round(factor * 100)}", bench(factor * supply, NOMINAL_IREF_A))
        for factor in SUPPLY_SWEEP
        if factor != 1.0
    ]
    mirror = analyze_bias_mirror([_measure(run_dir / folder, tb) for folder, tb in points])
    iref_rows = list(range(len(IREF_SWEEP_A)))
    nominal = IREF_SWEEP_A.index(NOMINAL_IREF_A)
    supply_rows, extra = [], len(IREF_SWEEP_A)
    for factor in SUPPLY_SWEEP:
        supply_rows.append(nominal if factor == 1.0 else extra)
        extra += factor != 1.0

    # each mirror's compliance from its own rail: the NMOS one's from ground, the PMOS one's from the supply
    p_compliance = mirror.vdd_v - mirror.p_compliance_v
    errors = np.abs(np.stack([mirror.n_ratio, mirror.p_ratio]) - 1)
    power = mirror.vdd_v * mirror.supply_current_a
    return Record(
        metrics={
            "n_ratio": float(mirror.n_ratio[nominal]),
            "p_ratio": float(mirror.p_ratio[nominal]),
            "n_output_resistance_ohm": float(mirror.n_output_resistance_ohm[nominal]),
            "p_output_resistance_ohm": float(mirror.p_output_resistance_ohm[nominal]),
            "n_compliance_v": float(mirror.n_compliance_v[nominal]),
            "p_compliance_v": float(p_compliance[nominal]),
            "n_headroom_v": float(mirror.n_headroom_v[nominal]),
            "p_headroom_v": float(mirror.p_headroom_v[nominal]),
            **{f"{gate}_v": float(getattr(mirror, f"{gate}_v")[nominal]) for gate in GATES},
            "power_w": float(power[nominal]),
            "mirror_error_max_iref_ratio": float(np.max(errors[:, iref_rows])),
            "mirror_error_max_supply_ratio": float(np.max(errors[:, supply_rows])),
        },
        details=[
            Plot(
                name="iv",
                title="Test mirrors' current over the reference across the output (10 µA)",
                x_label="Output voltage (V)",
                y_label="Output over reference",
                x=mirror.vout_v[nominal].tolist(),
                series={"NMOS": mirror.n_iv_ratio[nominal].tolist(), "PMOS": mirror.p_iv_ratio[nominal].tolist()},
            ),
            Plot(
                name="ratio_iref",
                title="Test mirrors' current over the reference current",
                x_label="Reference current (A)",
                y_label="Output over reference",
                x=list(IREF_SWEEP_A),
                series={"NMOS": mirror.n_ratio[iref_rows].tolist(), "PMOS": mirror.p_ratio[iref_rows].tolist()},
                x_log=True,
            ),
            Plot(
                name="compliance_iref",
                title="Test mirrors' compliance from their rail over the reference current",
                x_label="Reference current (A)",
                y_label="Compliance (V)",
                x=list(IREF_SWEEP_A),
                series={"NMOS": mirror.n_compliance_v[iref_rows].tolist(), "PMOS": p_compliance[iref_rows].tolist()},
                x_log=True,
            ),
            Plot(
                name="gates_iref",
                title="Gate voltages over the reference current",
                x_label="Reference current (A)",
                y_label="Voltage (V)",
                x=list(IREF_SWEEP_A),
                series={gate: getattr(mirror, f"{gate}_v")[iref_rows].tolist() for gate in GATES},
                x_log=True,
            ),
            Plot(
                name="ratio_supply",
                title="Test mirrors' current over the reference over the supply (10 µA)",
                x_label="Supply over nominal",
                y_label="Output over reference",
                x=list(SUPPLY_SWEEP),
                series={"NMOS": mirror.n_ratio[supply_rows].tolist(), "PMOS": mirror.p_ratio[supply_rows].tolist()},
            ),
            Plot(
                name="gates_supply",
                title="Gate voltages over the supply (10 µA)",
                x_label="Supply over nominal",
                y_label="Voltage (V)",
                x=list(SUPPLY_SWEEP),
                series={gate: getattr(mirror, f"{gate}_v")[supply_rows].tolist() for gate in GATES},
            ),
            Plot(
                name="power_supply",
                title="Generator power over the supply (10 µA)",
                x_label="Supply over nominal",
                y_label="Power (W)",
                x=list(SUPPLY_SWEEP),
                series={"power": power[supply_rows].tolist()},
            ),
        ],
    )


def layout_netlist(out_dir: Path, pdk: str, bias: BiasParams) -> Path:
    """The transistor netlist ``flow.bias.layout`` places, with the PDK's library cells it contains
    recognized (``flow.layout.stdcells``), for ALIGN to lay out without a floorplan."""

    from flow.layout.pdkproc import in_pdk

    logic = importlib.import_module(f"pdk.{pdk}.hdl21").pdk_logic
    transistors = write_netlist(bias, out_dir / "bias_transistors.sp", logic)
    return in_pdk(pdk, "flow.layout.stdcells", "recognize_file", transistors, out_dir / "bias.sp")
