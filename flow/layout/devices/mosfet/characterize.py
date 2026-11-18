"""Characterize a PDK's core transistors in Spectre at the typical corner, 25 C, and write the
mosfet table (``pdk/<pdk>/devices/mosfet.json``).

Each flavor (NMOS and PMOS, standard and low threshold where the PDK has them) is one device of
``UNITS`` unit widths at the minimum length, biased in one operating-point run:

- its switching resistance: the mean of V/I at a drain-source voltage of the supply and of half the
  supply with the gate at the supply, the resistance an inverter shows over its swing;
- its triode resistance: V/I at 50 mV, the one that sets the last of a settling;
- its drain current and transconductance against the gate voltage at half the supply across it.

Every number is per unit width, so a width of k units is a k-th of the resistance. Beside them, at
each threshold, an inverter's delay at a fan-out of four (``fo4_delay_s``, a transient run): a chain
of inverters each four times the one before it (NMOS two unit widths, PMOS as many more as its
switching resistance asks), the delay of one inside it from its input's mid-supply crossing to its
output's, the mean of its rising and falling output: what each inner inverter of a driver's chain
adds (``flow.layout.devices.mosfet.netlist``: a chain tapers at FO4).

    python -m flow.layout.devices.mosfet.characterize tsmc65 [tsmc28 ...]
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import hdl21 as h
import hdl21.sim as hs
import numpy as np
from hdl21.primitives import MosType, MosVth, Vdc, Vpulse
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


# the FO4 chain: its first inverter's NMOS in unit widths, its inverters (the one measured the second,
# loaded by the third, as large as a driver chain's inner inverters) and the input's edge (s)
_FO4_UNITS = 2
_FO4_STAGES = 5
_FO4_MEASURED = 1
_FO4_EDGE_S = 50e-12


def _fo4_bench(vdd: float, ratio: dict[MosVth, float], period_s: float) -> h.Module:
    """At each threshold a chain of ``_FO4_STAGES`` inverters, each four times the one before it,
    from one pulse: its PMOS ``ratio`` times its NMOS."""

    bench = h.Module(name="fo4_characterization")
    bench.VSS = h.Port()
    bench.vdd, bench.vin = h.Signal(), h.Signal()
    bench.vsupply = Vdc(dc=vdd)(p=bench.vdd, n=bench.VSS)
    pulse = {"delay": period_s / 4, "rise": _FO4_EDGE_S, "fall": _FO4_EDGE_S, "width": period_s / 2, "period": period_s}
    bench.vpulse = Vpulse(v1=0.0, v2=vdd, **pulse)(p=bench.vin, n=bench.VSS)
    for vth, p_over_n in ratio.items():
        node = bench.vin
        for stage in range(_FO4_STAGES):
            out = bench.add(h.Signal(), name=f"n_{vth.name}_{stage}")
            n = _FO4_UNITS * 4**stage
            bench.add(
                mos(tp=MosType.NMOS, vth=vth, w=n, l=1)(d=out, g=node, s=bench.VSS, b=bench.VSS),
                name=f"mn_{vth.name}_{stage}",
            )
            bench.add(
                mos(tp=MosType.PMOS, vth=vth, w=max(1, round(n * p_over_n)), l=1)(
                    d=out, g=node, s=bench.vdd, b=bench.vdd
                ),
                name=f"mp_{vth.name}_{stage}",
            )
            node = out
    return bench


def _crossings(time_s: np.ndarray, v: np.ndarray, level: float) -> np.ndarray:
    """Each time ``v`` crosses ``level``, interpolated."""
    above = v > level
    index = np.nonzero(above[1:] != above[:-1])[0]
    return time_s[index] + (level - v[index]) * (time_s[index + 1] - time_s[index]) / (v[index + 1] - v[index])


def _fo4_delay(attrs: list, vdd: float, ratio: dict[MosVth, float], run_dir: Path) -> dict[str, float]:
    """Each threshold's FO4 inverter delay (s, ``_fo4_bench``): the measured inverter's from its
    input's mid-supply crossing to its output's, the mean over its rising and falling outputs."""

    # not in the reference texts: an inverter's delay at a fan-out of four, the logic designers' unit
    # of gate delay; a propagation delay is [Baker] Fig. 10.9, p. 333, the mid-supply to mid-supply
    period = 4e-9
    bench = _fo4_bench(vdd, ratio, period)
    h.pdk.compile(bench)
    result = hs.Sim(tb=bench, attrs=[*attrs, hs.Tran(tstop=period, tstep=1e-12, name="tran")]).run(
        SimOptions(
            simulator=SupportedSimulators.SPECTRE,
            fmt=ResultFormat.SIM_DATA,
            rundir=run_dir,
            simulator_args=("+lqtimeout", "600"),
        )
    )
    data = result.an[0].data
    time_s = np.asarray(data["time"])
    found = {}
    for vth in ratio:
        into = _crossings(time_s, np.asarray(data[f"xtop.n_{vth.name}_{_FO4_MEASURED - 1}"]), vdd / 2)
        out = _crossings(time_s, np.asarray(data[f"xtop.n_{vth.name}_{_FO4_MEASURED}"]), vdd / 2)
        found[vth.name] = float(np.mean([min(o for o in out if o > i) - i for i in into]))
    return found


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
    # each threshold's inverter at its own switching resistances' ratio, as a driver's chain draws it
    ratio = {
        vth: devices[flavor(MosType.PMOS, vth)]["switching_ohm"] / devices[flavor(MosType.NMOS, vth)]["switching_ohm"]
        for vth in (MosVth.STD, MosVth.LOW)
        if (MosType.NMOS, vth) in flavors and (MosType.PMOS, vth) in flavors
    }
    fo4 = _fo4_delay([a for a in attrs if not isinstance(a, hs.Op)], vdd, ratio, run_dir / "fo4")
    return write_table(
        "mosfet",
        pdk,
        {"vdd_v": vdd, "unit": {"w_m": w_unit, "l_m": l_min}, "devices": devices, "fo4_delay_s": fo4},
        method="Spectre operating point; FO4 inverter chain transient",
    )


if __name__ == "__main__":
    for name in sys.argv[1:]:
        print(characterize(name))
