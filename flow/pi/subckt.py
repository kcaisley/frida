"""
Phase interpolator generator for FRIDA.

Supports:
- CMOS: weighted inverter slices from the two clock phases into one mixing node, which an
  output inverter buffers
- CML: two input pairs on weighted tails into one pair of symmetric loads
"""

from enum import Enum, auto
from pathlib import Path

import hdl21 as h
from hdl21.primitives import MosType, MosVth

from flow.circuit.ports import module_from_ports
from flow.circuit.devices import mos as _mos
from flow.circuit.devices import write_netlist as _write_netlist


class Style(Enum):
    CMOS = auto()  # inverter slices on a mixing node (single-ended: ap, bp to outp; the mix is outn)
    CML = auto()  # two differential pairs on weighted tails, shared loads


@h.paramclass
class PiParams:
    """Phase interpolator parameters.

    Device sizing uses multiplier-based scaling:
    - w: Width multiplier (w=4 means 4×Wmin)
    - l: Length multiplier (l=1 means 1×Lmin)

    This approach allows the same design to be portable across PDKs.
    """

    # Topology parameters
    style = h.Param(dtype=Style, desc="Interpolator style", default=Style.CMOS)
    weight_a = h.Param(dtype=int, desc="Slices (CMOS) or tail units (CML) of phase A", default=2)
    weight_b = h.Param(dtype=int, desc="Slices (CMOS) or tail units (CML) of phase B", default=2)

    # Device sizing (multipliers of Wmin/Lmin)
    n_w = h.Param(dtype=int, desc="Slice (or CML input) NMOS width multiplier", default=2)
    p_w = h.Param(dtype=int, desc="Slice PMOS (or CML load) width multiplier", default=4)
    out_n_w = h.Param(dtype=int, desc="Output inverter NMOS width multiplier", default=4)
    out_p_w = h.Param(dtype=int, desc="Output inverter PMOS width multiplier", default=8)
    tail_w = h.Param(dtype=int, desc="CML tail unit width multiplier", default=4)
    tail_l = h.Param(dtype=int, desc="CML tail length multiplier", default=4)
    l = h.Param(dtype=int, desc="Length multiplier", default=1)
    vth = h.Param(dtype=MosVth, desc="Device Vth", default=MosVth.LOW)


def is_valid_pi_params(param: PiParams) -> bool:
    """Check if this interpolator is valid: both weights non-negative, at least one positive;
    every size positive."""
    if param.weight_a < 0 or param.weight_b < 0 or param.weight_a + param.weight_b == 0:
        return False
    return min(param.n_w, param.p_w, param.out_n_w, param.out_p_w, param.tail_w, param.tail_l, param.l) > 0


@h.bundle
class PiNets:
    ap, an = h.Input(desc="Phase A"), h.Input(desc="Phase A complement (CML)")
    bp, bn = h.Input(desc="Phase B"), h.Input(desc="Phase B complement (CML)")
    outp, outn = h.Output(), h.Output()
    vbn = h.Input(desc="CML tail bias")
    vbp = h.Input(desc="CML load bias")
    vdd = h.Power(direction=h.PortDir.INOUT)
    vss = h.Ground(direction=h.PortDir.INOUT)


@h.generator
def Pi(param: PiParams) -> h.Module:
    """
    Phase interpolator generator.

    Generates CMOS (weighted inverter slices) and CML (weighted tails) interpolators between
    two clock phases.

    Uses h.Mos primitives - call pdk.compile() to convert to PDK devices.
    """
    if not is_valid_pi_params(param):
        raise ValueError(f"Invalid phase interpolator params: {param}")

    Pi = module_from_ports("Pi", PiNets.signals)
    vth, l = param.vth, param.l
    if param.style == Style.CMOS:
        # each slice an inverter from its phase onto the mix (outn); the slices' currents add
        for name, phase, count in (("a", Pi.ap, param.weight_a), ("b", Pi.bp, param.weight_b)):
            for k in range(count):
                Pi.add(
                    _mos(tp=MosType.NMOS, vth=vth, w=param.n_w, l=l)(d=Pi.outn, g=phase, s=Pi.vss, b=Pi.vss),
                    name=f"Mslice_{name}{k}_n",
                )
                Pi.add(
                    _mos(tp=MosType.PMOS, vth=vth, w=param.p_w, l=l)(d=Pi.outn, g=phase, s=Pi.vdd, b=Pi.vdd),
                    name=f"Mslice_{name}{k}_p",
                )
        Pi.Mout_n = _mos(tp=MosType.NMOS, vth=vth, w=param.out_n_w, l=l)(d=Pi.outp, g=Pi.outn, s=Pi.vss, b=Pi.vss)
        Pi.Mout_p = _mos(tp=MosType.PMOS, vth=vth, w=param.out_p_w, l=l)(d=Pi.outp, g=Pi.outn, s=Pi.vdd, b=Pi.vdd)
        return Pi

    # CML: each phase's pair on its own tail of weight units; both pairs share the loads
    for name, (p, n), count in (("a", (Pi.ap, Pi.an), param.weight_a), ("b", (Pi.bp, Pi.bn), param.weight_b)):
        if not count:
            continue
        tail = Pi.add(h.Signal(name=f"tail_{name}"))
        for k in range(count):
            Pi.add(
                _mos(tp=MosType.NMOS, vth=vth, w=param.tail_w, l=param.tail_l)(d=tail, g=Pi.vbn, s=Pi.vss, b=Pi.vss),
                name=f"Mtail_{name}{k}",
            )
        Pi.add(_mos(tp=MosType.NMOS, vth=vth, w=param.n_w, l=l)(d=Pi.outn, g=p, s=tail, b=Pi.vss), name=f"Min_{name}_p")
        Pi.add(_mos(tp=MosType.NMOS, vth=vth, w=param.n_w, l=l)(d=Pi.outp, g=n, s=tail, b=Pi.vss), name=f"Min_{name}_n")
    for side, out in (("p", Pi.outp), ("n", Pi.outn)):
        Pi.add(
            _mos(tp=MosType.PMOS, vth=vth, w=param.p_w, l=l)(d=out, g=Pi.vbp, s=Pi.vdd, b=Pi.vdd), name=f"Mload_{side}"
        )
        Pi.add(
            _mos(tp=MosType.PMOS, vth=vth, w=param.p_w, l=l)(d=out, g=out, s=Pi.vdd, b=Pi.vdd), name=f"Mdiode_{side}"
        )
    return Pi


def write_netlist(params: PiParams, path: Path, pdk) -> Path:
    """The interpolator after ``pdk``'s compile, as one flat SPICE subcircuit named after ``path``
    (``flow.circuit.devices.write_netlist``: devices fingered to the row cells in whole unit widths)."""

    return _write_netlist(params, path, pdk, generator=Pi, nets=PiNets)


# ==== Named interpolators ====

CASES = {
    # CMOS, the two phases at equal weight
    "cmos_half": PiParams(),
    # CMOS, three slices of A to one of B
    "cmos_quarter": PiParams(weight_a=3, weight_b=1),
    # CML, equal tails
    "cml_half": PiParams(style=Style.CML),
    # CML, three tail units of A to one of B
    "cml_quarter": PiParams(style=Style.CML, weight_a=3, weight_b=1),
}
