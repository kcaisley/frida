"""The sampling switch's circuit: its nets (``Nets``) and its generator (``netlist``), the module
``Samp`` of the design ``Params``.

An NMOS, PMOS or transmission-gate switch with configurable device sizing and threshold voltage,
half-size charge-injection dummies, and a bootstrapped NMOS gate. The generator uses h.Mos
primitives; the PDK's compile makes them its devices.
"""

import hdl21 as h
from hdl21.primitives import MosType

from flow.circuit.devices import mos
from flow.circuit.ports import module_from_ports

from .params import Params, SwitchType


@h.bundle
class Nets:
    din = h.Input(desc="Data input")
    dout = h.Output(desc="Data output")
    clk, clk_b = h.Clock(), h.Clock()
    vdd = h.Power(direction=h.PortDir.INOUT)
    vss = h.Ground(direction=h.PortDir.INOUT)


# a fresh module every call: the PDK compile rewrites its devices in place, and a run's bench
# and its area each compile one
@h.generator(enable_cache=False)
def netlist(param: Params) -> h.Module:
    """The sampling switch: an NMOS, a PMOS or both (a transmission gate) between ``din`` and
    ``dout``, tracking while ``clk`` is high; a bootstrap drives the NMOS gate from its boosted node,
    half-size dummies on ``dout`` absorb the charge their switch's channel releases at turn-off."""
    Samp = module_from_ports("Samp", Nets.signals)
    bootstrap = param.switch_type is SwitchType.BOOTSTRAP
    nmos = param.switch_type in (SwitchType.NMOS, SwitchType.TGATE, SwitchType.BOOTSTRAP)
    pmos = param.switch_type in (SwitchType.PMOS, SwitchType.TGATE)

    # The boosted gate of the NMOS switch (a bootstrap). During hold (clk low) the capacitor's bottom
    # plate ``boot_bot`` is pulled to vss and its top plate ``boot_top`` charged to vdd, while a
    # stacked pull-down holds ``gate`` low. During sampling a transmission gate puts din on the
    # bottom plate and a PMOS joins ``gate`` to the top plate, which then sits one supply above din:
    # the switch's gate-source voltage stays near vdd whatever the input. The PMOS bodies sit on vdd,
    # so the boosted node's junctions leak toward vdd while sampling.
    if bootstrap:
        Samp.gate = h.Signal(desc="Boosted switch gate")
        Samp.boot_top, Samp.boot_bot, Samp.gate_off = h.Signal(), h.Signal(), h.Signal()
        aux = {"vth": param.mos_vth, "w": param.boot_w, "l": 1}
        # Transmission gate: the bottom plate follows din while sampling
        Samp.Mtg_n = mos(tp=MosType.NMOS, **aux)(d=Samp.boot_bot, g=Samp.clk, s=Samp.din, b=Samp.vss)
        Samp.Mtg_p = mos(tp=MosType.PMOS, **aux)(d=Samp.boot_bot, g=Samp.clk_b, s=Samp.din, b=Samp.vdd)
        # Bottom plate to vss during hold
        Samp.Mbot = mos(tp=MosType.NMOS, **aux)(d=Samp.boot_bot, g=Samp.clk_b, s=Samp.vss, b=Samp.vss)
        # Gate pull-down during hold: a stack of two, so the boosted gate splits over two off devices
        # (the references cascode with a device gated by vdd; a gate on a rail has no route here)
        Samp.Mgate_cas = mos(tp=MosType.NMOS, **aux)(d=Samp.gate, g=Samp.clk_b, s=Samp.gate_off, b=Samp.vss)
        Samp.Mgate_off = mos(tp=MosType.NMOS, **aux)(d=Samp.gate_off, g=Samp.clk_b, s=Samp.vss, b=Samp.vss)
        # Top plate to the gate while sampling
        Samp.Mgate = mos(tp=MosType.PMOS, **aux)(d=Samp.boot_top, g=Samp.clk_b, s=Samp.gate, b=Samp.vdd)
        # Top plate to vdd while the gate is low (hold)
        Samp.Mpre = mos(tp=MosType.PMOS, **aux)(d=Samp.vdd, g=Samp.gate, s=Samp.boot_top, b=Samp.vdd)
        # The boost capacitor: an NMOS whose channel (drain and source on the bottom plate) faces its gate
        Samp.Mcap = mos(tp=MosType.NMOS, vth=param.mos_vth, w=param.cap_w, l=param.cap_l)(
            d=Samp.boot_bot, g=Samp.boot_top, s=Samp.boot_bot, b=Samp.vss
        )
    if nmos:
        Samp.MN = mos(tp=MosType.NMOS, vth=param.mos_vth, w=param.mos_w, l=param.mos_l)(
            d=Samp.dout, g=Samp.gate if bootstrap else Samp.clk, s=Samp.din, b=Samp.vss
        )
    if pmos:
        Samp.MP = mos(tp=MosType.PMOS, vth=param.mos_vth, w=param.mos_w, l=param.mos_l)(
            d=Samp.dout, g=Samp.clk_b, s=Samp.din, b=Samp.vdd
        )

    # Half-size dummies with drain and source on dout absorb the charge their switch's channel
    # releases at turn-off: each is clocked opposite its switch
    if param.dummy:
        half = param.mos_w // 2
        if nmos:
            Samp.MN_dummy = mos(tp=MosType.NMOS, vth=param.mos_vth, w=half, l=param.mos_l)(
                d=Samp.dout, g=Samp.clk_b, s=Samp.dout, b=Samp.vss
            )
        if pmos:
            Samp.MP_dummy = mos(tp=MosType.PMOS, vth=param.mos_vth, w=half, l=param.mos_l)(
                d=Samp.dout, g=Samp.clk, s=Samp.dout, b=Samp.vdd
            )

    return Samp
