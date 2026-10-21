"""
Ring amplifier generator for FRIDA.

A single-ended ring amplifier (after BAG's ringamp_se): an input inverter on common-mode-biased
tails, split by the enable switches into the two halves that drive the dead-zone stage, whose
bias devices set the dead zone between ctrlp and ctrln, and an output inverter of the two ctrl
nodes. With en low the amplifier is off: the dead-zone nodes go to the rails and the output
stage turns off.
"""

from pathlib import Path

import hdl21 as h
from hdl21.primitives import MosType, MosVth

from flow.circuit.ports import module_from_ports
from flow.comp.subckt import _mos
from flow.comp.subckt import write_netlist as _write_netlist


@h.paramclass
class RingampParams:
    """Ring amplifier parameters.

    Device sizing uses multiplier-based scaling:
    - w: Width multiplier (w=8 means 8×Wmin)
    - l: Length multiplier (l=1 means 1×Lmin)

    This approach allows the same design to be portable across PDKs.
    """

    in_w = h.Param(dtype=int, desc="Input inverter width multiplier (PMOS twice)", default=4)
    tail_w = h.Param(dtype=int, desc="Common-mode tail width multiplier", default=8)
    tail_l = h.Param(dtype=int, desc="Tail length multiplier", default=2)
    mid_w = h.Param(dtype=int, desc="Second-stage width multiplier", default=4)
    bias_w = h.Param(dtype=int, desc="Dead-zone bias device width multiplier", default=2)
    bias_l = h.Param(dtype=int, desc="Dead-zone bias device length multiplier", default=2)
    out_w = h.Param(dtype=int, desc="Output stage width multiplier (PMOS twice)", default=16)
    en_w = h.Param(dtype=int, desc="Enable switch width multiplier", default=2)
    vth = h.Param(dtype=MosVth, desc="Device Vth", default=MosVth.LOW)


def is_valid_ringamp_params(param: RingampParams) -> bool:
    """Check if this amplifier is valid: every size positive."""
    sizes = (param.in_w, param.tail_w, param.tail_l, param.mid_w, param.bias_w, param.bias_l, param.out_w, param.en_w)
    return min(sizes) > 0


@h.bundle
class RingampNets:
    inp = h.Input()
    out = h.Output()
    en, enb = h.Input(desc="Amplifier enable"), h.Input()
    biasn, biasp = h.Input(desc="Dead-zone NMOS bias"), h.Input(desc="Dead-zone PMOS bias")
    vcmfb = h.Input(desc="Common-mode bias of both tails")
    vdd = h.Power(direction=h.PortDir.INOUT)
    vss = h.Ground(direction=h.PortDir.INOUT)
    ctrlp, ctrln = (h.Signal(props=h.Properties(inner={"save": True})) for _ in range(2))


@h.generator
def Ringamp(param: RingampParams) -> h.Module:
    """
    Ring amplifier generator.

    Generates a single-ended ring amplifier with its dead-zone stage and enable.

    Uses h.Mos primitives - call pdk.compile() to convert to PDK devices.
    """
    if not is_valid_ringamp_params(param):
        raise ValueError(f"Invalid ring amplifier params: {param}")

    R = module_from_ports("Ringamp", RingampNets.signals)
    vth = param.vth
    nmos = lambda w, l=1: _mos(tp=MosType.NMOS, vth=vth, w=w, l=l)
    pmos = lambda w, l=1: _mos(tp=MosType.PMOS, vth=vth, w=w, l=l)
    R.vtop, R.vbot, R.midp, R.midn, R.dzp, R.dzn = (h.Signal() for _ in range(6))

    # first stage: the input inverter on its common-mode tails, the NMOS feedback on vbot
    R.Mtail_p = pmos(param.tail_w, param.tail_l)(d=R.vtop, g=R.vcmfb, s=R.vdd, b=R.vdd)
    R.Mtail_n = nmos(param.tail_w, param.tail_l)(d=R.vbot, g=R.vcmfb, s=R.vss, b=R.vss)
    R.Min_p = pmos(2 * param.in_w)(d=R.midn, g=R.inp, s=R.vtop, b=R.vdd)
    R.Min_n = nmos(param.in_w)(d=R.midp, g=R.inp, s=R.vbot, b=R.vss)
    R.Mfb = nmos(param.in_w)(d=R.vbot, g=R.midn, s=R.vss, b=R.vss)
    # enable: a transmission gate joins the halves midp, midn
    R.Mbe_n = nmos(param.en_w)(d=R.midn, g=R.en, s=R.midp, b=R.vss)
    R.Mbe_p = pmos(param.en_w)(d=R.midp, g=R.enb, s=R.midn, b=R.vdd)
    # second stage: each half drives its ctrl node, the dead-zone devices bias between them
    R.Mmid_p = pmos(2 * param.mid_w)(d=R.ctrlp, g=R.midp, s=R.vdd, b=R.vdd)
    R.Mmid_n = nmos(param.mid_w)(d=R.ctrln, g=R.midn, s=R.vss, b=R.vss)
    R.Mbias_p = pmos(param.bias_w, param.bias_l)(d=R.ctrln, g=R.dzp, s=R.ctrlp, b=R.vdd)
    R.Mbias_n = nmos(param.bias_w, param.bias_l)(d=R.ctrlp, g=R.dzn, s=R.ctrln, b=R.vss)
    # dead-zone gates: the biases while enabled, the rails (devices off) while disabled
    R.Men_p0 = pmos(param.en_w)(d=R.dzn, g=R.enb, s=R.biasn, b=R.vdd)
    R.Men_n0 = nmos(param.en_w)(d=R.dzn, g=R.enb, s=R.vss, b=R.vss)
    R.Men_p1 = pmos(param.en_w)(d=R.dzp, g=R.en, s=R.vdd, b=R.vdd)
    R.Men_n1 = nmos(param.en_w)(d=R.dzp, g=R.en, s=R.biasp, b=R.vss)
    R.Mcharge_p = pmos(param.en_w)(d=R.biasn, g=R.en, s=R.vdd, b=R.vdd)
    R.Mcharge_n = nmos(param.en_w)(d=R.biasp, g=R.enb, s=R.vss, b=R.vss)
    # output stage
    R.Mout_p = pmos(2 * param.out_w)(d=R.out, g=R.ctrlp, s=R.vdd, b=R.vdd)
    R.Mout_n = nmos(param.out_w)(d=R.out, g=R.ctrln, s=R.vss, b=R.vss)
    return R


def write_netlist(params: RingampParams, path: Path, pdk) -> Path:
    """The ring amplifier after ``pdk``'s compile, as one flat SPICE subcircuit named after
    ``path`` (``flow.comp.subckt.write_netlist``: devices fingered to the row cells in whole unit widths)."""

    return _write_netlist(params, path, pdk, generator=Ringamp, nets=RingampNets)


# ==== Named ring amplifiers ====

CASES = {
    # single-ended ring amplifier (BAG ringamp_se)
    "se": RingampParams(),
    # with a twice-as-strong output stage
    "se_strong": RingampParams(out_w=32),
}
