"""
MOS capacitor generator for FRIDA.

Supports:
- Decoupling capacitors between the rails: an NMOS with its gate on vdd and its channel on vss,
  a PMOS with its gate on vss and its channel on vdd, or both side by side
- Capacitors between two nets: the gate on top, the channel (drain and source) on bot
- Any number of parallel units
"""

from enum import Enum, auto
from pathlib import Path

import hdl21 as h
from hdl21.primitives import MosType, MosVth

from flow.circuit.ports import module_from_ports
from flow.circuit.devices import mos as _mos
from flow.circuit.devices import write_netlist as _write_netlist


class Mode(Enum):
    DECAP = auto()  # between the rails
    CAP = auto()  # between top (the gate) and bot (the channel)


class Devices(Enum):
    NMOS = auto()
    PMOS = auto()
    BOTH = auto()  # an NMOS and a PMOS per unit


@h.paramclass
class MosCapParams:
    """MOS capacitor parameters.

    Device sizing uses multiplier-based scaling:
    - w: Width multiplier (w=8 means 8×Wmin)
    - l: Length multiplier (l=4 means 4×Lmin)

    This approach allows the same design to be portable across PDKs.
    """

    mode = h.Param(dtype=Mode, desc="Decoupling or two-net capacitor", default=Mode.DECAP)
    devices = h.Param(dtype=Devices, desc="NMOS, PMOS or both per unit", default=Devices.NMOS)
    units = h.Param(dtype=int, desc="Parallel units", default=1)
    w = h.Param(dtype=int, desc="Width multiplier", default=16)
    l = h.Param(dtype=int, desc="Length multiplier", default=8)
    vth = h.Param(dtype=MosVth, desc="Device Vth (the row cells draw the low-Vth devices)", default=MosVth.LOW)


def is_valid_moscap_params(param: MosCapParams) -> bool:
    """Check if this capacitor is valid: every size and the unit count positive."""
    return min(param.units, param.w, param.l) > 0


@h.bundle
class MosCapNets:
    top = h.Input(desc="Gate plate (two-net capacitor)")
    bot = h.Input(desc="Channel plate (two-net capacitor)")
    vdd = h.Power(direction=h.PortDir.INOUT)
    vss = h.Ground(direction=h.PortDir.INOUT)


@h.generator
def MosCap(param: MosCapParams) -> h.Module:
    """
    MOS capacitor generator.

    Generates decoupling capacitors between the rails or capacitors between two nets of
    parallel NMOS, PMOS or complementary units, every body on its rail.

    Uses h.Mos primitives - call pdk.compile() to convert to PDK devices.
    """
    if not is_valid_moscap_params(param):
        raise ValueError(f"Invalid MOS capacitor params: {param}")

    MosCap = module_from_ports("MosCap", MosCapNets.signals)
    kinds = {Devices.NMOS: (MosType.NMOS,), Devices.PMOS: (MosType.PMOS,), Devices.BOTH: (MosType.NMOS, MosType.PMOS)}
    for k in range(param.units):
        for tp in kinds[param.devices]:
            rail = MosCap.vss if tp == MosType.NMOS else MosCap.vdd
            if param.mode == Mode.DECAP:  # the gate on the other rail, the channel on its own
                gate, channel = (MosCap.vdd if tp == MosType.NMOS else MosCap.vss), rail
            else:
                gate, channel = MosCap.top, MosCap.bot
            pol = "n" if tp == MosType.NMOS else "p"
            MosCap.add(
                _mos(tp=tp, vth=param.vth, w=param.w, l=param.l)(d=channel, g=gate, s=channel, b=rail),
                name=f"Mcap{k}_{pol}",
            )
    return MosCap


def write_netlist(params: MosCapParams, path: Path, pdk) -> Path:
    """The capacitor after ``pdk``'s compile, as one flat SPICE subcircuit named after ``path``
    (``flow.circuit.devices.write_netlist``: devices fingered to the row cells in whole unit widths)."""

    return _write_netlist(params, path, pdk, generator=MosCap, nets=MosCapNets)


# ==== Named capacitors ====

CASES = {
    # two NMOS decap units
    "decap_n": MosCapParams(units=2),
    # complementary decap: an NMOS and a PMOS
    "decap_np": MosCapParams(devices=Devices.BOTH),
    # two-net NMOS capacitor, two units (the sampler's boost capacitor)
    "cap_n": MosCapParams(mode=Mode.CAP, units=2),
    # two-net PMOS capacitor, two units
    "cap_p": MosCapParams(mode=Mode.CAP, devices=Devices.PMOS, units=2),
}
