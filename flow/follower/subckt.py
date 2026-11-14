"""The follower's circuit: its nets (``Nets``) and its generator (``netlist``), the module
``Follower`` of the design ``Params``.

With an NMOS or a PMOS input device: the source follower, the input device's drain on the far
rail and a current source on the output; and the flipped voltage follower, the input device's
drain biased by a current source and fed back to a shunt device on the output (a low output
impedance), with an optional output sink. The generator uses h.Mos primitives; the PDK's compile
makes them its devices.
"""

import hdl21 as h
from hdl21.primitives import MosType

from flow.circuit.ports import module_from_ports
from flow.layout.devices.mosfet.netlist import mos
from flow.layout.hdl21align import place, row, rows

from .params import Params, Topology


@h.bundle
class Nets:
    vin = h.Input()
    vout = h.Output()
    vbn = h.Input(desc="NMOS current-source bias")
    vbp = h.Input(desc="PMOS current-source bias")
    vdd = h.Power(direction=h.PortDir.INOUT)
    vss = h.Ground(direction=h.PortDir.INOUT)


# a fresh module every call: the PDK compile rewrites its devices in place, and a run's bench
# and its area each compile one
@h.generator(enable_cache=False)
def netlist(param: Params) -> h.Module:
    """The follower: a source follower or a flipped voltage follower with an NMOS or a PMOS input
    device, every body on its rail."""
    Follower = module_from_ports("Follower", Nets.signals)
    tp = param.input_xtors
    other = MosType.PMOS if tp == MosType.NMOS else MosType.NMOS
    # the input type's rail (its body), the other rail (its drain in a source follower)
    rail, far = (Follower.vss, Follower.vdd) if tp == MosType.NMOS else (Follower.vdd, Follower.vss)
    bias, other_bias = (Follower.vbn, Follower.vbp) if tp == MosType.NMOS else (Follower.vbp, Follower.vbn)
    vth = param.vth

    # where ALIGN puts each device (flow.layout.hdl21align), rows top first: a source follower's
    # input device above its current source; a flipped follower's PMOS devices above its NMOS ones,
    # the input device beside its shunt device, the current source beside the sink
    if param.topology is Topology.SOURCE:
        Follower.Min = mos(tp=tp, vth=vth, w=param.in_w, l=param.in_l)(d=far, g=Follower.vin, s=Follower.vout, b=rail)
        Follower.Mbias = mos(tp=tp, vth=vth, w=param.bias_w, l=param.bias_l)(d=Follower.vout, g=bias, s=rail, b=rail)
        place(Follower, rows(row(Follower.Min), row(Follower.Mbias)), symmetric=False)
        return Follower

    # flipped: a fixed current through the input device sets its gate-source voltage; the shunt
    # device takes whatever else the output draws, driven from the input device's drain
    Follower.fb = h.Signal(desc="Input device drain, the shunt device's gate")
    Follower.Min = mos(tp=tp, vth=vth, w=param.in_w, l=param.in_l)(
        d=Follower.fb, g=Follower.vin, s=Follower.vout, b=rail
    )
    Follower.Mbias = mos(tp=other, vth=vth, w=param.bias_w, l=param.bias_l)(d=Follower.fb, g=other_bias, s=far, b=far)
    Follower.Mfb = mos(tp=tp, vth=vth, w=param.fb_w, l=param.fb_l)(d=Follower.vout, g=Follower.fb, s=rail, b=rail)
    if param.sink:
        Follower.Msink = mos(tp=other, vth=vth, w=param.bias_w, l=param.bias_l)(
            d=Follower.vout, g=other_bias, s=far, b=far
        )
    follows = row(Follower.Min, Follower.Mfb)
    sources = row(Follower.Mbias, getattr(Follower, "Msink", None))
    place(Follower, rows(sources, follows) if tp == MosType.NMOS else rows(follows, sources), symmetric=False)
    return Follower
