"""
Current-mode logic generator for FRIDA.

Supports, with an NMOS or PMOS input pair on a biased tail and MOS loads of the other type:
- A buffer, a clocked latch, a divide-by-two of two latches, and an XOR of the two input pairs
- Triode loads (biased by vbp, or vbn for a PMOS input) or symmetric loads (a diode-connected
  device beside each biased one), as the row cells draw no resistors
"""

from enum import Enum, auto
from pathlib import Path

import hdl21 as h
from hdl21.primitives import MosType, MosVth

from flow.circuit.devices import mos as _mos
from flow.circuit.devices import write_netlist as _write_netlist
from flow.circuit.ports import module_from_ports


class Function(Enum):
    BUFFER = auto()
    LATCH = auto()  # tracks inp while clkp is high, holds while clkn is high
    DIVIDER = auto()  # two latches on opposite clock phases, the second's output fed back inverted
    XOR = auto()  # outp high where inp and clkp differ (clkp/clkn: the second input)


class Load(Enum):
    TRIODE = auto()  # a biased device of the other type on each output
    SYMMETRIC = auto()  # a biased device and a diode-connected one on each output


@h.paramclass
class CmlParams:
    """Current-mode logic parameters.

    Device sizing uses multiplier-based scaling:
    - w: Width multiplier (w=8 means 8×Wmin)
    - l: Length multiplier (l=1 means 1×Lmin)

    This approach allows the same design to be portable across PDKs.
    """

    # Topology parameters
    function = h.Param(dtype=Function, desc="Logic function", default=Function.BUFFER)
    input_xtors = h.Param(dtype=MosType, desc="Input pair type (NMOS or PMOS)", default=MosType.NMOS)
    load = h.Param(dtype=Load, desc="Load type", default=Load.SYMMETRIC)

    # Device sizing (multipliers of Wmin/Lmin)
    in_w = h.Param(dtype=int, desc="Input pair width multiplier", default=8)
    in_l = h.Param(dtype=int, desc="Input pair length multiplier", default=1)
    tail_w = h.Param(dtype=int, desc="Tail width multiplier", default=8)
    tail_l = h.Param(dtype=int, desc="Tail length multiplier", default=4)
    load_w = h.Param(dtype=int, desc="Load width multiplier", default=4)
    load_l = h.Param(dtype=int, desc="Load length multiplier", default=1)
    vth = h.Param(dtype=MosVth, desc="Device Vth", default=MosVth.LOW)


def is_valid_cml_params(param: CmlParams) -> bool:
    """Check if this gate is valid: every size positive."""
    return min(param.in_w, param.in_l, param.tail_w, param.tail_l, param.load_w, param.load_l) > 0


@h.bundle
class CmlNets:
    inp, inn = h.Input(), h.Input()
    clkp, clkn = h.Input(desc="Clock (latch, divider) or second input (XOR)"), h.Input()
    outp, outn = h.Output(), h.Output()
    vbn = h.Input(desc="NMOS bias: the tail of an NMOS input, the loads of a PMOS input")
    vbp = h.Input(desc="PMOS bias: the loads of an NMOS input, the tail of a PMOS input")
    vdd = h.Power(direction=h.PortDir.INOUT)
    vss = h.Ground(direction=h.PortDir.INOUT)


@h.generator
def Cml(param: CmlParams) -> h.Module:
    """
    Current-mode logic generator.

    Generates CML buffers, latches, dividers and XOR gates with an NMOS or PMOS input pair,
    triode or symmetric MOS loads.

    Uses h.Mos primitives - call pdk.compile() to convert to PDK devices.
    """
    if not is_valid_cml_params(param):
        raise ValueError(f"Invalid CML params: {param}")

    Cml = module_from_ports("Cml", CmlNets.signals)
    if param.function == Function.DIVIDER:
        # the first latch takes the second's output crossed (an inversion), on the clock's other phase
        Cml.mp, Cml.mn = h.Signal(desc="First latch output"), h.Signal()
        _build_latch(Cml, param, "_a", (Cml.outn, Cml.outp), (Cml.clkn, Cml.clkp), (Cml.mp, Cml.mn))
        _build_latch(Cml, param, "_b", (Cml.mp, Cml.mn), (Cml.clkp, Cml.clkn), (Cml.outp, Cml.outn))
    elif param.function == Function.LATCH:
        _build_latch(Cml, param, "", (Cml.inp, Cml.inn), (Cml.clkp, Cml.clkn), (Cml.outp, Cml.outn))
    elif param.function == Function.XOR:
        _build_xor(Cml, param)
    else:
        tail = _build_tail(Cml, param, "")
        _build_pair(Cml, param, "Min", (Cml.inp, Cml.inn), tail, (Cml.outp, Cml.outn))
        _build_loads(Cml, param, "", (Cml.outp, Cml.outn))
    return Cml


def _types(module, param: CmlParams):
    """The input type, the load type, the input type's rail and its bias, the loads' rail and bias."""
    tp = param.input_xtors
    if tp == MosType.NMOS:
        return tp, MosType.PMOS, module.vss, module.vbn, module.vdd, module.vbp
    return tp, MosType.NMOS, module.vdd, module.vbp, module.vss, module.vbn


def _build_tail(module, param: CmlParams, name: str):
    """The biased tail ``Mtail<name>``; returns its drain."""
    tp, _, rail, bias, _, _ = _types(module, param)
    tail = module.add(h.Signal(name=f"tail{name}"))
    module.add(
        _mos(tp=tp, vth=param.vth, w=param.tail_w, l=param.tail_l)(d=tail, g=bias, s=rail, b=rail),
        name=f"Mtail{name}",
    )
    return tail


def _build_pair(module, param: CmlParams, name: str, gates, source, drains, w: int | None = None):
    """A pair ``<name>_p``, ``<name>_n`` on ``source``: the positive gate pulls the negative drain."""
    tp, _, rail, _, _, _ = _types(module, param)
    for side, gate, drain in (("p", gates[0], drains[1]), ("n", gates[1], drains[0])):
        module.add(
            _mos(tp=tp, vth=param.vth, w=w or param.in_w, l=param.in_l)(d=drain, g=gate, s=source, b=rail),
            name=f"{name}_{side}",
        )


def _build_loads(module, param: CmlParams, name: str, outs):
    """A load on each output: a biased device, and with ``Load.SYMMETRIC`` a diode-connected one."""
    _, tp, _, _, rail, bias = _types(module, param)
    for side, out in (("p", outs[0]), ("n", outs[1])):
        module.add(
            _mos(tp=tp, vth=param.vth, w=param.load_w, l=param.load_l)(d=out, g=bias, s=rail, b=rail),
            name=f"Mload{name}_{side}",
        )
        if param.load == Load.SYMMETRIC:
            module.add(
                _mos(tp=tp, vth=param.vth, w=param.load_w, l=param.load_l)(d=out, g=out, s=rail, b=rail),
                name=f"Mdiode{name}_{side}",
            )


def _build_latch(module, param: CmlParams, name: str, data, clock, outs):
    """A CML latch: the clock pair splits the tail current between the input pair (tracking while
    clock[0] is high) and the cross-coupled pair (holding while clock[1] is high)."""
    tail = _build_tail(module, param, name)
    track = module.add(h.Signal(name=f"track{name}"))
    hold = module.add(h.Signal(name=f"hold{name}"))
    _build_pair(module, param, f"Mclk{name}", clock, tail, (hold, track))
    _build_pair(module, param, f"Min{name}", data, track, outs)
    _build_pair(module, param, f"Mhold{name}", outs, hold, outs)
    _build_loads(module, param, name, outs)


def _build_xor(module, param: CmlParams):
    """A CML XOR: each input pair's devices steer the tail current into a top device of the other
    input, so outp is low where the inputs agree and high where they differ."""
    tp, _, rail, _, _, _ = _types(module, param)
    tail = _build_tail(module, param, "")
    a, b = (module.inp, module.inn), (module.clkp, module.clkn)
    # where the inputs agree (inp and clkp, or inn and clkn) the current pulls outp low; where they
    # differ, outn
    branches = (("ap", a[0], b[0], module.outp), ("an", a[1], b[1], module.outp), ("bp", b[0], a[1], module.outn))
    branches += (("bn", b[1], a[0], module.outn),)
    for name, bottom, top, out in branches:
        mid = module.add(h.Signal(name=f"x{name}"))
        module.add(
            _mos(tp=tp, vth=param.vth, w=param.in_w, l=param.in_l)(d=mid, g=bottom, s=tail, b=rail),
            name=f"Mbot_{name}",
        )
        module.add(
            _mos(tp=tp, vth=param.vth, w=param.in_w, l=param.in_l)(d=out, g=top, s=mid, b=rail),
            name=f"Mtop_{name}",
        )
    _build_loads(module, param, "", (module.outp, module.outn))


def write_netlist(params: CmlParams, path: Path, pdk) -> Path:
    """The gate after ``pdk``'s compile, as one flat SPICE subcircuit named after ``path``
    (``flow.circuit.devices.write_netlist``: devices fingered to the row cells in whole unit widths)."""

    return _write_netlist(params, path, pdk, generator=Cml, nets=CmlNets)


# ==== Named gates ====

CASES = {
    # NMOS-input buffer with symmetric loads (loads without resistors)
    "buffer": CmlParams(),
    # PMOS-input buffer with NMOS symmetric loads
    "buffer_pmos": CmlParams(input_xtors=MosType.PMOS),
    # clocked latch with triode loads
    "latch": CmlParams(function=Function.LATCH, load=Load.TRIODE),
    # divide-by-two of two latches
    "divider": CmlParams(function=Function.DIVIDER, load=Load.TRIODE),
    # XOR of the two input pairs
    "xor": CmlParams(function=Function.XOR),
}
