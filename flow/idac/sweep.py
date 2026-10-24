"""The current source's design space (``flow.sweep``): the characterization's four units at seven
sizings, in every PDK.

Each instance on the characterization's bench (``flow.idac.sim``: the reference current into the
unit's own diode or a diode-connected copy of its source device, a cascode's gate a third of the
supply off the far rail, out and dump held at mid-supply and the output swept from ground to the
supply) at its own supply and 10 µA of reference, enabled: the current and its error from the
units' share, the output resistance at mid-supply, the compliance (where the current stays within
5 %) and from it the headroom the unit needs from its rail, the bias voltage; disabled too where
it switches, its on-off ratio and, where it steers, how much of the current the two states lose.
Over the reference (1 to 50 µA) and the supply (90 to 120 % of its own), enabled, the current,
output resistance and headroom. Nine or ten Spectre DC sweeps, well under a minute.
"""

from __future__ import annotations

import importlib
import math
from datetime import UTC, datetime
from pathlib import Path

import hdl21 as h
import numpy as np
from hdl21.primitives import MosType

from flow.pipeline import Plot, Record

from .sim import IREF_SWEEP_A, NOMINAL_IREF_A, IdacTbParams, _run_idac_sim
from .subckt import CASES, Idac, IdacParams, Switch, is_valid_idac_params, write_netlist

ROOT = Path(__file__).resolve().parents[2]
GENERATOR = Idac
# the characterization's units (flow.idac.subckt.CASES): source type, unit count, cascode,
# switching, diode
STRUCTURE = ("source_xtors", "units", "cascode", "switch", "diode")
STRUCTURES = [{name: getattr(idac, name) for name in STRUCTURE} for idac in CASES.values()]
# every width scaled together (x0.5 to x4), the source device twice as wide and long (its W/L
# kept), the switches four times as wide (switched units only), the cascode twice as long
# (cascoded units only)
DEFAULT = IdacParams()
WIDTHS = ("src_w", "cas_w", "sw_w")
SIZES = [
    {name: getattr(DEFAULT, name) // 2 for name in WIDTHS},
    {},
    {name: 2 * getattr(DEFAULT, name) for name in WIDTHS},
    {name: 4 * getattr(DEFAULT, name) for name in WIDTHS},
    {"src_w": 2 * DEFAULT.src_w, "src_l": 2 * DEFAULT.src_l},
    {"sw_w": 4 * DEFAULT.sw_w},
    {"cas_l": 2 * DEFAULT.cas_l},
]
SUPPLY_SWEEP = (0.9, 1.0, 1.1, 1.2)


def _absent(structure: dict) -> set[str]:
    """The sizes of devices a unit of this structure does not have."""
    cascode = set() if structure["cascode"] else {"cas_w", "cas_l"}
    return cascode | ({"sw_w"} if structure["switch"] == Switch.NONE else set())


def instances(pdk: str) -> list[IdacParams]:
    """Every unit at every size it has devices for (only devices it lacks resized: the base unit
    again), in every PDK."""
    idacs = (
        IdacParams(**structure, **sizes)
        for structure in STRUCTURES
        for sizes in SIZES
        if not (sizes and set(sizes) <= _absent(structure))
    )
    return [idac for idac in idacs if is_valid_idac_params(idac)]


def _measure(run_dir: Path, tb: IdacTbParams):
    """One Spectre run of the bench as ``idac_characterization`` converts it, a ``MeasIdac``."""

    from vlsirtools.spice.spectre import parse_nutbin

    from flow.analysis.types import MeasInfo

    from .analysis import MeasIdac

    raw = _run_idac_sim(run_dir, tb)
    with raw.open("rb") as stream:
        sweep = parse_nutbin(stream)["sweep_vout"].data
    info = MeasInfo(
        backend="spice",
        timestamp_utc=datetime.fromtimestamp(raw.stat().st_mtime, tz=UTC),
        instruments={"simulator": "Spectre"},
        readbacks={"pdk": tb.pdk, "raw_file": raw.name, "current_convention": "positive_into_the_unit"},
    )
    raw.unlink()
    # every current as drawn out of its source: positive into the unit's pin
    return MeasIdac(
        group=None,
        index=None,
        dut=tb.idac,
        info=info,
        param=tb,
        vout_v=np.real(np.asarray(sweep["xtop.out"])).astype(np.float64),
        out_current_a=-np.real(np.asarray(sweep["xtop.vout:p"])).astype(np.float64),
        dump_current_a=-np.real(np.asarray(sweep["xtop.vdump:p"])).astype(np.float64),
        supply_current_a=-np.real(np.asarray(sweep["xtop.vvdd:p"])).astype(np.float64),
        vbias_v=np.real(np.asarray(sweep["xtop.vbias"])).astype(np.float64),
    )


def characterize(run_dir: Path, pdk: str, idac: IdacParams) -> Record:
    from .analysis import analyze_idac_output, analyze_idac_steering

    supply = importlib.import_module(f"pdk.{pdk}.hdl21.site").install.supply_voltage(h.pdk.Corner.TYP)
    pmos = idac.source_xtors == MosType.PMOS

    def bench(vdd: float, iref: float, en: bool = True) -> IdacTbParams:
        return IdacTbParams(
            pdk=pdk,
            idac=idac,
            vdd=round(vdd, 4),
            vout=round(vdd / 2, 4),
            vout_step_v=round(vdd / 48, 6),
            en=en,
            vcas=round(vdd / 3 if pmos else 2 * vdd / 3, 4),
            iref=iref,
        )

    def headroom(result, row: int, vdd: float) -> float:
        """The output voltage the unit needs from its rail: an NMOS sink's from ground, a PMOS
        source's from the supply."""
        return vdd - float(result.compliance_high_v[row]) if pmos else float(result.compliance_low_v[row])

    # over the reference, enabled; the nominal one disabled too where the unit switches
    enabled = [_measure(run_dir / f"on_iref{round(iref * 1e9)}na", bench(supply, iref)) for iref in IREF_SWEEP_A]
    on, nominal = analyze_idac_output(enabled), IREF_SWEEP_A.index(NOMINAL_IREF_A)
    off = steering = None
    if idac.switch != Switch.NONE:
        disabled = _measure(run_dir / f"off_iref{round(NOMINAL_IREF_A * 1e9)}na", bench(supply, NOMINAL_IREF_A, False))
        off = analyze_idac_output([disabled])
        steering = analyze_idac_steering([disabled], on=analyze_idac_output([enabled[nominal]]))

    # over the supply, enabled at the nominal reference, the 100 % point the nominal one: each
    # point's result and its row
    supply_points = {}
    for factor in SUPPLY_SWEEP:
        if factor == 1.0:
            supply_points[factor] = (on, nominal)
            continue
        measurement = _measure(run_dir / f"supply_{round(factor * 100)}", bench(factor * supply, NOMINAL_IREF_A))
        supply_points[factor] = (analyze_idac_output([measurement]), 0)
    currents = [float(result.current_a[row]) for result, row in supply_points.values()]
    share = idac.units * np.asarray(IREF_SWEEP_A)  # the current the units' mirror ratio gives
    headrooms = [headroom(on, row, supply) for row in range(len(IREF_SWEEP_A))]
    current = float(on.current_a[nominal])
    return Record(
        metrics={
            "current_a": current,
            "mirror_error_ratio": current / (idac.units * NOMINAL_IREF_A) - 1,
            "output_resistance_ohm": float(on.output_resistance_ohm[nominal]),
            "compliance_low_v": float(on.compliance_low_v[nominal]),
            "compliance_high_v": float(on.compliance_high_v[nominal]),
            "headroom_v": headrooms[nominal],
            "vbias_v": float(on.vbias_v[nominal]),
            "on_off_ratio": float(steering.on_off_ratio[0]) if steering is not None else math.nan,
            # a single switch drops the current when off: steering's loss belongs to a steered unit
            "steering_loss_ratio": float(steering.total_change[0]) if idac.switch == Switch.STEER else math.nan,
            "headroom_max_iref_v": float(np.max(headrooms)),
            "current_change_supply_ratio": (max(currents) - min(currents)) / current,
        },
        details=[
            Plot(
                name="iv",
                title="Output current over the output voltage (10 µA reference)",
                x_label="Output voltage (V)",
                y_label="Output current (A)",
                x=on.vout_v.tolist(),
                series={
                    "enabled": on.iv_current_a[nominal].tolist(),
                    **({"disabled": off.iv_current_a[0].tolist()} if off is not None else {}),
                },
            ),
            Plot(
                name="rout_vout",
                title="Output resistance over the output voltage (10 µA reference)",
                x_label="Output voltage (V)",
                y_label="Output resistance (Ω)",
                x=on.vout_v.tolist(),
                series={"enabled": on.iv_resistance_ohm[nominal].tolist()},
                y_log=True,
            ),
            Plot(
                name="ratio_iref",
                title="Output current over the units' share of the reference",
                x_label="Reference current (A)",
                y_label="Output over units x reference",
                x=list(IREF_SWEEP_A),
                series={"ratio": (on.current_a / share).tolist()},
                x_log=True,
            ),
            Plot(
                name="rout_iref",
                title="Output resistance over the reference current",
                x_label="Reference current (A)",
                y_label="Output resistance (Ω)",
                x=list(IREF_SWEEP_A),
                series={"output resistance": on.output_resistance_ohm.tolist()},
                x_log=True,
                y_log=True,
            ),
            Plot(
                name="headroom_iref",
                title="Headroom from the rail over the reference current",
                x_label="Reference current (A)",
                y_label="Headroom (V)",
                x=list(IREF_SWEEP_A),
                series={"headroom": headrooms},
                x_log=True,
            ),
            Plot(
                name="current_supply",
                title="Output current over the supply (10 µA reference)",
                x_label="Supply over nominal",
                y_label="Output current (A)",
                x=list(SUPPLY_SWEEP),
                series={"current": currents},
            ),
            Plot(
                name="rout_supply",
                title="Output resistance over the supply",
                x_label="Supply over nominal",
                y_label="Output resistance (Ω)",
                x=list(SUPPLY_SWEEP),
                series={
                    "output resistance": [float(r.output_resistance_ohm[row]) for r, row in supply_points.values()]
                },
                y_log=True,
            ),
            Plot(
                name="headroom_supply",
                title="Headroom from the rail over the supply",
                x_label="Supply over nominal",
                y_label="Headroom (V)",
                x=list(SUPPLY_SWEEP),
                series={
                    "headroom": [
                        headroom(result, row, factor * supply) for factor, (result, row) in supply_points.items()
                    ]
                },
            ),
        ],
    )


def layout_netlist(out_dir: Path, pdk: str, idac: IdacParams) -> Path:
    """The transistor netlist ``flow.idac.layout`` places, with the PDK's library cells it contains
    recognized (``flow.layout.stdcells``), for ALIGN to lay out without a floorplan."""

    from flow.layout.pdkproc import in_pdk

    logic = importlib.import_module(f"pdk.{pdk}.hdl21").pdk_logic
    transistors = write_netlist(idac, out_dir / "idac_transistors.sp", logic)
    return in_pdk(pdk, "flow.layout.stdcells", "recognize_file", transistors, out_dir / "idac.sp")
