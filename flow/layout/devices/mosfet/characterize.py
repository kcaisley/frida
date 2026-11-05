"""Characterize a PDK's core transistors in Spectre at the typical corner, 25 C, and write the
mosfet table (``pdk/<pdk>/devices/mosfet.json``).

Each flavor (NMOS and PMOS, standard and low threshold where the PDK has them) is one device of
``UNITS`` unit widths at the minimum length, biased in one operating-point run:

- its switching resistance: the mean of V/I at a drain-source voltage of the supply and of half the
  supply with the gate at the supply, the resistance an inverter shows over its swing;
- its triode resistance: V/I at 50 mV, the one that sets the last of a settling;
- its drain current and transconductance against the gate voltage at half the supply across it.

Every number is per unit width, so a width of k units is a k-th of the resistance.

    python -m flow.layout.devices.mosfet.characterize tsmc65 [tsmc28 ...]
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import hdl21 as h
import hdl21.sim as hs
import numpy as np
from hdl21.primitives import MosType, MosVth, Vdc
from vlsirtools.spice import ResultFormat, SimOptions, SupportedSimulators

from flow.circuit.devices import core_unit, fingers

from ..device import ROOT, write_table
from .geometry import flavor
from .netlist import mos

# the width every flavor is measured at, in unit widths: wide enough that fingering rounds little
_UNITS = 10
_TRIODE_V = 0.05
_VGS_POINTS = 13


def _bench(vdd: float, flavors: list[tuple[MosType, MosVth]]) -> h.Module:
    """One device a bias point: each flavor at the switching, triode and gate-sweep biases."""

    bench = h.Module(name="mosfet_characterization")
    bench.VSS = h.Port()
    bench.vdd = h.Signal()
    bench.vsupply = Vdc(dc=vdd)(p=bench.vdd, n=bench.VSS)

    def device(name: str, tp: MosType, vth: MosVth, vgs: float, vds: float) -> None:
        nmos = tp is MosType.NMOS
        gate, drain = bench.add(h.Signal(), name=f"g_{name}"), bench.add(h.Signal(), name=f"d_{name}")
        rail = bench.VSS if nmos else bench.vdd
        bench.add(Vdc(dc=vgs if nmos else vdd - vgs)(p=gate, n=bench.VSS), name=f"vg_{name}")
        bench.add(Vdc(dc=vds if nmos else vdd - vds)(p=drain, n=bench.VSS), name=f"vd_{name}")
        bench.add(mos(tp=tp, vth=vth, w=_UNITS, l=1)(d=drain, g=gate, s=rail, b=rail), name=f"m_{name}")

    for tp, vth in flavors:
        key = f"{tp.name}_{vth.name}"
        for index, vds in enumerate((vdd, vdd / 2, _TRIODE_V)):
            device(f"{key}_sw{index}", tp, vth, vdd, vds)
        for index, vgs in enumerate(np.linspace(0, vdd, _VGS_POINTS)):
            device(f"{key}_vgs{index}", tp, vth, float(vgs), vdd / 2)
    return bench


def _flavors(pdk_logic) -> list[tuple[MosType, MosVth]]:
    """The flavors the PDK maps: every type at standard and low threshold that compiles."""

    return [(tp, vth) for tp in (MosType.NMOS, MosType.PMOS) for vth in (MosVth.STD, MosVth.LOW) if _compiles(tp, vth)]


def _compiles(tp: MosType, vth: MosVth) -> bool:
    """Whether the active PDK maps a flavor to a device of its own."""
    probe = h.Module(name="probe")
    probe.d, probe.g, probe.s, probe.b = h.Signal(), h.Signal(), h.Signal(), h.Signal()
    probe.m = mos(tp=tp, vth=vth, w=1, l=1)(d=probe.d, g=probe.g, s=probe.s, b=probe.b)
    try:
        h.pdk.compile(probe)
    except (RuntimeError, ValueError, KeyError):
        return False
    return True


def characterize(pdk: str) -> Path:
    """Measure ``pdk``'s flavors and write its mosfet table."""

    logic = importlib.import_module(f"pdk.{pdk}.hdl21.pdk_logic")
    install = importlib.import_module(f"pdk.{pdk}.hdl21.site").install
    h.pdk.set_default(logic)
    vdd = float(install.supply_voltage(h.pdk.Corner.TYP))
    w_unit, l_min = core_unit(logic)
    units, _ = fingers(_UNITS, "analog")  # the width the device is drawn at, in unit widths
    flavors = _flavors(logic)
    bench = _bench(vdd, flavors)
    h.pdk.compile(bench)
    attrs = [
        install.include(h.pdk.Corner.TYP),
        *(getattr(install, name)() for name in ("include_pre_simulation", "include_devices") if hasattr(install, name)),
        hs.Options(name="temp", value=25.0),
        hs.Op(name="op"),
    ]
    run_dir = ROOT / "build" / "devices" / "mosfet" / pdk
    result = hs.Sim(tb=bench, attrs=attrs).run(
        SimOptions(
            simulator=SupportedSimulators.SPECTRE,
            fmt=ResultFormat.SIM_DATA,
            rundir=run_dir,
            simulator_args=("+lqtimeout", "600"),
        )
    )
    data = result.an[0].data
    current = lambda name: abs(float(data[f"xtop.vd_{name}:p"])) / units  # per unit width
    vgs = [float(v) for v in np.linspace(0, vdd, _VGS_POINTS)]
    devices = {}
    for tp, vth in flavors:
        key = f"{tp.name}_{vth.name}"
        full, half, triode = (current(f"{key}_sw{index}") for index in range(3))
        id_a = [current(f"{key}_vgs{index}") for index in range(_VGS_POINTS)]
        devices[flavor(tp, vth)] = {
            "switching_ohm": 0.5 * (vdd / full + vdd / 2 / half),
            "triode_ohm": _TRIODE_V / triode,
            "vgs_v": vgs,
            "vds_v": vdd / 2,
            "id_a": id_a,
            "gm_s": [float(g) for g in np.gradient(id_a, vgs)],
        }
    return write_table(
        "mosfet",
        pdk,
        {"vdd_v": vdd, "unit": {"w_m": w_unit, "l_m": l_min}, "devices": devices},
        method="Spectre operating point",
    )


if __name__ == "__main__":
    for name in sys.argv[1:]:
        print(characterize(name))
