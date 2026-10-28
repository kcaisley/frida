"""
Source follower generator for FRIDA.

Supports, with an NMOS or PMOS input device:
- The source follower: the input device's drain on the far rail, a current source on the output
- The flipped voltage follower: the input device's drain biased by a current source and fed back
  to a shunt device on the output (low output impedance), with an optional output sink
"""

from enum import Enum, auto
from pathlib import Path

import hdl21 as h
from hdl21.primitives import MosType, MosVth

from flow.circuit.devices import mos as _mos
from flow.circuit.devices import write_netlist as _write_netlist
from flow.circuit.ports import module_from_ports


class Topology(Enum):
    SOURCE = auto()  # input device and a current source on the output
    FLIPPED = auto()  # input device, a current source into its drain, a shunt device it drives


@h.paramclass
class FollowerParams:
    """Follower parameters.

    Device sizing uses multiplier-based scaling:
    - w: Width multiplier (w=8 means 8×Wmin)
    - l: Length multiplier (l=1 means 1×Lmin)

    This approach allows the same design to be portable across PDKs.
    """

    # Topology parameters
    topology = h.Param(dtype=Topology, desc="Follower topology", default=Topology.SOURCE)
    input_xtors = h.Param(dtype=MosType, desc="Input device type (NMOS or PMOS)", default=MosType.NMOS)
    sink = h.Param(dtype=bool, desc="An extra current source on the output (flipped follower)", default=False)

    # Device sizing (multipliers of Wmin/Lmin)
    in_w = h.Param(dtype=int, desc="Input device width multiplier", default=16)
    in_l = h.Param(dtype=int, desc="Input device length multiplier", default=1)
    bias_w = h.Param(dtype=int, desc="Current source width multiplier", default=8)
    bias_l = h.Param(dtype=int, desc="Current source length multiplier", default=4)
    fb_w = h.Param(dtype=int, desc="Shunt device width multiplier", default=16)
    fb_l = h.Param(dtype=int, desc="Shunt device length multiplier", default=1)
    vth = h.Param(dtype=MosVth, desc="Device Vth", default=MosVth.LOW)


def is_valid_follower_params(param: FollowerParams) -> bool:
    """Check if this follower is valid: an output sink belongs to a flipped follower; every
    size is positive."""
    if min(param.in_w, param.in_l, param.bias_w, param.bias_l, param.fb_w, param.fb_l) <= 0:
        return False
    return not (param.sink and param.topology != Topology.FLIPPED)


@h.bundle
class FollowerNets:
    vin = h.Input()
    vout = h.Output()
    vbn = h.Input(desc="NMOS current-source bias")
    vbp = h.Input(desc="PMOS current-source bias")
    vdd = h.Power(direction=h.PortDir.INOUT)
    vss = h.Ground(direction=h.PortDir.INOUT)


@h.generator
def Follower(param: FollowerParams) -> h.Module:
    """
    Follower generator.

    Generates source followers and flipped voltage followers with an NMOS or PMOS input
    device, every body on its rail.

    Uses h.Mos primitives - call pdk.compile() to convert to PDK devices.
    """
    if not is_valid_follower_params(param):
        raise ValueError(f"Invalid follower params: {param}")

    Follower = module_from_ports("Follower", FollowerNets.signals)
    tp = param.input_xtors
    other = MosType.PMOS if tp == MosType.NMOS else MosType.NMOS
    # the input type's rail (its body), the other rail (its drain in a source follower)
    rail, far = (Follower.vss, Follower.vdd) if tp == MosType.NMOS else (Follower.vdd, Follower.vss)
    bias, other_bias = (Follower.vbn, Follower.vbp) if tp == MosType.NMOS else (Follower.vbp, Follower.vbn)
    vth = param.vth

    if param.topology == Topology.SOURCE:
        Follower.Min = _mos(tp=tp, vth=vth, w=param.in_w, l=param.in_l)(d=far, g=Follower.vin, s=Follower.vout, b=rail)
        Follower.Mbias = _mos(tp=tp, vth=vth, w=param.bias_w, l=param.bias_l)(d=Follower.vout, g=bias, s=rail, b=rail)
        return Follower

    # flipped: a fixed current through the input device sets its gate-source voltage; the shunt
    # device takes whatever else the output draws, driven from the input device's drain
    Follower.fb = h.Signal(desc="Input device drain, the shunt device's gate")
    Follower.Min = _mos(tp=tp, vth=vth, w=param.in_w, l=param.in_l)(
        d=Follower.fb, g=Follower.vin, s=Follower.vout, b=rail
    )
    Follower.Mbias = _mos(tp=other, vth=vth, w=param.bias_w, l=param.bias_l)(d=Follower.fb, g=other_bias, s=far, b=far)
    Follower.Mfb = _mos(tp=tp, vth=vth, w=param.fb_w, l=param.fb_l)(d=Follower.vout, g=Follower.fb, s=rail, b=rail)
    if param.sink:
        Follower.Msink = _mos(tp=other, vth=vth, w=param.bias_w, l=param.bias_l)(
            d=Follower.vout, g=other_bias, s=far, b=far
        )
    return Follower


def write_netlist(params: FollowerParams, path: Path, pdk) -> Path:
    """The follower after ``pdk``'s compile, as one flat SPICE subcircuit named after ``path``
    (``flow.circuit.devices.write_netlist``: devices fingered to the row cells in whole unit widths)."""

    return _write_netlist(params, path, pdk, generator=Follower, nets=FollowerNets)


# ==== Named followers ====

CASES = {
    # NMOS source follower with an NMOS current source, output-buffer sized
    "source": FollowerParams(in_w=32, bias_w=16),
    # PMOS source follower with a PMOS current source, output-buffer sized
    "source_pmos": FollowerParams(input_xtors=MosType.PMOS, in_w=32, bias_w=16),
    # NMOS flipped voltage follower
    "flipped": FollowerParams(topology=Topology.FLIPPED),
    # PMOS flipped voltage follower with an output sink
    "flipped_pmos": FollowerParams(topology=Topology.FLIPPED, input_xtors=MosType.PMOS, sink=True),
}
