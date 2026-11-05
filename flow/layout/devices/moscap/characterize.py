"""Characterize a PDK's MOS capacitors in Spectre at the typical corner, 25 C, and write the moscap
table (``pdk/<pdk>/devices/moscap.json``).

An NMOS and a PMOS of each threshold flavor (standard and low) of ``_UNITS`` unit widths at
``CAP_L`` minimum lengths in inversion, the gate an AC stimulus whose source's current over 2 pi f
is the capacitance: the mean over five gate biases across the last ``_SWING_V`` of the supply above
the channel and bulk (a MOS capacitor's node swings there). Per unit device and per um^2 of gate.

    python -m flow.layout.devices.moscap.characterize tsmc65 [tsmc28 ...]
"""

from __future__ import annotations

import importlib
import math
import sys
from pathlib import Path

import hdl21 as h
import hdl21.sim as hs
from hdl21.primitives import MosType, MosVth, Vdc
from vlsirtools.spice import ResultFormat, SimOptions, SupportedSimulators

from flow.circuit.devices import core_unit, fingers

from ..device import ROOT, write_table
from ..mosfet.netlist import mos
from .geometry import CAP_L

_UNITS = 10
_FREQUENCY_HZ = 1e6
_SWING_V = 0.5
_BIASES = 5


def characterize(pdk: str) -> Path:
    """Measure ``pdk``'s MOS capacitors and write its moscap table."""

    logic = importlib.import_module(f"pdk.{pdk}.hdl21.pdk_logic")
    install = importlib.import_module(f"pdk.{pdk}.hdl21.site").install
    h.pdk.set_default(logic)
    vdd = float(install.supply_voltage(h.pdk.Corner.TYP))
    w_unit, l_min = core_unit(logic)
    units, _ = fingers(_UNITS, "analog")
    bench = h.Module(name="moscap_characterization")
    bench.VSS = h.Port()
    bench.vdd = h.Signal()
    bench.vsupply = Vdc(dc=vdd)(p=bench.vdd, n=bench.VSS)
    flavors = [(tp, vth) for tp in (MosType.NMOS, MosType.PMOS) for vth in (MosVth.STD, MosVth.LOW)]
    swing = [vdd - _SWING_V * k / (_BIASES - 1) for k in range(_BIASES)]  # the gate above the channel
    for tp, vth in flavors:
        nmos = tp is MosType.NMOS
        rail = bench.VSS if nmos else bench.vdd
        for index, over in enumerate(swing):
            key = f"{tp.name}_{vth.name}_{index}"
            gate = bench.add(h.Signal(), name=f"g_{key}")
            bench.add(Vdc(dc=over if nmos else vdd - over, ac=1.0)(p=gate, n=bench.VSS), name=f"v_{key}")
            bench.add(mos(tp=tp, vth=vth, w=_UNITS, l=CAP_L)(d=rail, g=gate, s=rail, b=rail), name=f"m_{key}")
    h.pdk.compile(bench)
    attrs = [
        install.include(h.pdk.Corner.TYP),
        *(getattr(install, name)() for name in ("include_pre_simulation", "include_devices") if hasattr(install, name)),
        hs.Options(name="temp", value=25.0),
        hs.Ac(sweep=hs.LogSweep(start=_FREQUENCY_HZ, stop=10 * _FREQUENCY_HZ, npts=1), name="ac"),
    ]
    result = hs.Sim(tb=bench, attrs=attrs).run(
        SimOptions(
            simulator=SupportedSimulators.SPECTRE,
            fmt=ResultFormat.SIM_DATA,
            rundir=ROOT / "build" / "devices" / "moscap" / pdk,
            simulator_args=("+lqtimeout", "600"),
        )
    )
    data = result.an[0].data
    gate_um2 = w_unit * CAP_L * l_min * 1e12  # one unit device's gate
    devices = {}
    for tp, vth in flavors:
        currents = [complex(data[f"xtop.v_{tp.name}_{vth.name}_{k}:p"][0]) for k in range(_BIASES)]
        c_f = sum(abs(i.imag) for i in currents) / _BIASES / (2 * math.pi * _FREQUENCY_HZ)
        per_unit = c_f / units
        devices[f"{tp.name}/{vth.name}"] = {"ff_per_unit": per_unit * 1e15, "ff_per_um2": per_unit * 1e15 / gate_um2}
    return write_table(
        "moscap",
        pdk,
        {"vdd_v": vdd, "swing_v": _SWING_V, "cap_l": CAP_L, "unit": {"w_m": w_unit, "l_m": l_min}, "devices": devices},
        method="Spectre AC in inversion",
    )


if __name__ == "__main__":
    for name in sys.argv[1:]:
        print(characterize(name))
