"""The amplifier's circuit: its nets (``Nets``) and its generator (``netlist``), the module ``Ota``
of the design ``Params``.

With an NMOS or PMOS input pair:
- The five-transistor amplifier: a tail, the input pair and a current-mirror load (single-ended)
- The telescopic cascode: cascoded input pair and current-source load (differential)
- The folded cascode: the input pair folded into cascoded current sources (differential)
- The self-biased complementary amplifier: NMOS and PMOS pairs whose tails one side's drain drives
- An optional common-source second stage on each output, with a Miller capacitor for simulation

The generator uses h.Mos primitives; the PDK's compile makes them its devices.
"""

import hdl21 as h
from hdl21.primitives import C, MosType

from flow.circuit.ports import module_from_ports
from flow.layout.devices.mosfet.netlist import mos
from flow.layout.hdl21align import place, row, rows

from .params import Params, Topology


@h.bundle
class Nets:
    inp, inn = h.Input(), h.Input()
    outp, outn = h.Output(), h.Output()
    vbn = h.Input(desc="NMOS current-source bias (tail or bottom sources)")
    vbp = h.Input(desc="PMOS current-source bias (load or top sources)")
    vcasn, vcasp = h.Input(desc="NMOS cascode bias"), h.Input(desc="PMOS cascode bias")
    vdd = h.Power(direction=h.PortDir.INOUT)
    vss = h.Ground(direction=h.PortDir.INOUT)
    out1p, out1n = (h.Signal(props=h.Properties(inner={"save": True})) for _ in range(2))


# a fresh module every call: the PDK compile rewrites its devices in place, and a run's bench
# and its area each compile one
@h.generator(enable_cache=False)
def netlist(param: Params) -> h.Module:
    """The amplifier: a five-transistor, telescopic, folded-cascode or self-biased first stage with
    an NMOS or PMOS input pair, and an optional common-source second stage on each output."""
    Ota = module_from_ports("Ota", Nets.signals)
    # the first stage drives the outputs, or the second stage's inputs out1p/out1n
    out1p, out1n = (Ota.out1p, Ota.out1n) if param.two_stage else (Ota.outp, Ota.outn)

    if param.topology == Topology.SELF_BIASED:
        _build_self_biased(Ota, param, out1p)
    else:
        _build_first_stage(Ota, param, out1p, out1n)
    if param.two_stage:
        # a differential first stage (Params): a second stage on each output
        for inp, out, side in ((out1p, Ota.outp, "p"), (out1n, Ota.outn, "n")):
            _build_second_stage(Ota, param, inp, out, side)
    _place(Ota, param)
    return Ota


def _build_first_stage(module, param: Params, outp, outn):
    """The input pair on its tail and the topology's load. For an NMOS input everything sits as
    drawn below; a PMOS input mirrors it between the rails (types and bias nets swap)."""

    #  FIVE_T                 TELESCOPIC              FOLDED
    #  load ─┬─ load          load    load             top ──┬── top
    #   (mirror)              cas_p   cas_p            fold  │  fold ── cas_p ── out
    #  in_p  │  in_n          cas_n   cas_n          in_p/in_n         cas_n ── out
    #     tail                    tail                  tail            bottom

    diff = param.input_xtors
    other = MosType.PMOS if diff == MosType.NMOS else MosType.NMOS
    on_rail, load_rail = (module.vss, module.vdd) if diff == MosType.NMOS else (module.vdd, module.vss)
    tail_bias, load_bias = (module.vbn, module.vbp) if diff == MosType.NMOS else (module.vbp, module.vbn)
    cas_in, cas_load = (module.vcasn, module.vcasp) if diff == MosType.NMOS else (module.vcasp, module.vcasn)
    vth = param.vth
    module.tail = h.Signal()

    module.Mtail = mos(tp=diff, vth=vth, w=param.tail_w, l=param.tail_l)(
        d=module.tail, g=tail_bias, s=on_rail, b=on_rail
    )

    if param.topology == Topology.FIVE_T:
        # inp's drain is the mirror's diode side, so outp (on inn's drain) follows inp
        module.mirror = h.Signal()
        module.Min_p = mos(tp=diff, vth=vth, w=param.in_w, l=param.in_l)(
            d=module.mirror, g=module.inp, s=module.tail, b=on_rail
        )
        module.Min_n = mos(tp=diff, vth=vth, w=param.in_w, l=param.in_l)(d=outp, g=module.inn, s=module.tail, b=on_rail)
        module.Mload_d = mos(tp=other, vth=vth, w=param.load_w, l=param.load_l)(
            d=module.mirror, g=module.mirror, s=load_rail, b=load_rail
        )
        module.Mload = mos(tp=other, vth=vth, w=param.load_w, l=param.load_l)(
            d=outp, g=module.mirror, s=load_rail, b=load_rail
        )
        return

    if param.topology == Topology.TELESCOPIC:
        # inp's side drives outn and inn's outp (each input inverts to its own side's output)
        for side, gate, out in (("p", module.inp, outn), ("n", module.inn, outp)):
            drain = module.add(h.Signal(name=f"in_{side}_drain"))
            load = module.add(h.Signal(name=f"load_{side}"))
            module.add(
                mos(tp=diff, vth=vth, w=param.in_w, l=param.in_l)(d=drain, g=gate, s=module.tail, b=on_rail),
                name=f"Min_{side}",
            )
            module.add(
                mos(tp=diff, vth=vth, w=param.cas_w, l=param.cas_l)(d=out, g=cas_in, s=drain, b=on_rail),
                name=f"Mcas_in_{side}",
            )
            module.add(
                mos(tp=other, vth=vth, w=param.cas_w, l=param.cas_l)(d=out, g=cas_load, s=load, b=load_rail),
                name=f"Mcas_load_{side}",
            )
            module.add(
                mos(tp=other, vth=vth, w=param.load_w, l=param.load_l)(d=load, g=load_bias, s=load_rail, b=load_rail),
                name=f"Mload_{side}",
            )
        return

    # FOLDED: each input drain folds into a current source from the load rail; its cascode (the
    # load's type) carries the difference to the output, over a cascoded source to the input rail
    for side, gate, out in (("p", module.inp, outn), ("n", module.inn, outp)):
        fold = module.add(h.Signal(name=f"fold_{side}"))
        bottom = module.add(h.Signal(name=f"bottom_{side}"))
        module.add(
            mos(tp=diff, vth=vth, w=param.in_w, l=param.in_l)(d=fold, g=gate, s=module.tail, b=on_rail),
            name=f"Min_{side}",
        )
        module.add(
            mos(tp=other, vth=vth, w=param.load_w, l=param.load_l)(d=fold, g=load_bias, s=load_rail, b=load_rail),
            name=f"Mtop_{side}",
        )
        module.add(
            mos(tp=other, vth=vth, w=param.cas_w, l=param.cas_l)(d=out, g=cas_load, s=fold, b=load_rail),
            name=f"Mcas_fold_{side}",
        )
        module.add(
            mos(tp=diff, vth=vth, w=param.cas_w, l=param.cas_l)(d=out, g=cas_in, s=bottom, b=on_rail),
            name=f"Mcas_bottom_{side}",
        )
        module.add(
            mos(tp=diff, vth=vth, w=param.load_w, l=param.load_l)(d=bottom, g=tail_bias, s=on_rail, b=on_rail),
            name=f"Mbottom_{side}",
        )


def _build_self_biased(module, param: Params, out):
    """A complementary amplifier biasing itself: NMOS and PMOS input pairs on their own tails,
    inp's drains (``tail_g``) driving both tails' gates; the output on inn's drains."""

    module.tail_n, module.tail_p, module.tail_g = h.Signal(), h.Signal(), h.Signal()
    vth = param.vth
    module.Mtail_n = mos(tp=MosType.NMOS, vth=vth, w=param.tail_w, l=param.tail_l)(
        d=module.tail_n, g=module.tail_g, s=module.vss, b=module.vss
    )
    module.Mtail_p = mos(tp=MosType.PMOS, vth=vth, w=2 * param.tail_w, l=param.tail_l)(
        d=module.tail_p, g=module.tail_g, s=module.vdd, b=module.vdd
    )
    for tp, tail, rail, w in (
        (MosType.NMOS, module.tail_n, module.vss, param.in_w),
        (MosType.PMOS, module.tail_p, module.vdd, 2 * param.in_w),
    ):
        pol = "n" if tp == MosType.NMOS else "p"
        module.add(
            mos(tp=tp, vth=vth, w=w, l=param.in_l)(d=module.tail_g, g=module.inp, s=tail, b=rail),
            name=f"Min_p_{pol}",
        )
        module.add(mos(tp=tp, vth=vth, w=w, l=param.in_l)(d=out, g=module.inn, s=tail, b=rail), name=f"Min_n_{pol}")


def _build_second_stage(module, param: Params, inp, out, side: str):
    """A common-source stage from a first-stage output: the input pair's type gains (its gate on
    the first stage's load side), a current source of the other type from vbn or vbp, and the
    Miller capacitor across it."""

    # [Razavi-Analog] Fig. 9.23, p. 361: two-stage op amp, its second stage a common-source stage
    # the first stage's output sits near its load rail: the second stage's gain device is the load's type
    gain = MosType.PMOS if param.input_xtors == MosType.NMOS else MosType.NMOS
    source = MosType.NMOS if gain == MosType.PMOS else MosType.PMOS
    gain_rail, source_rail = (module.vdd, module.vss) if gain == MosType.PMOS else (module.vss, module.vdd)
    bias = module.vbn if source == MosType.NMOS else module.vbp
    module.add(
        mos(tp=gain, vth=param.vth, w=param.stage2_w, l=param.stage2_l)(d=out, g=inp, s=gain_rail, b=gain_rail),
        name=f"Mstage2_{side}",
    )
    module.add(
        mos(tp=source, vth=param.vth, w=param.stage2_w, l=param.load_l)(d=out, g=bias, s=source_rail, b=source_rail),
        name=f"Mstage2_src_{side}",
    )
    if float(param.miller) > 0:
        # [Razavi-Analog] Sec. 10.5, p. 426: compensation of two-stage op amps
        module.add(C(c=param.miller)(p=out, n=inp), name=f"Cmiller_{side}")


def _place(module: h.Module, param: Params) -> None:
    """The amplifier's rows for ALIGN (``flow.layout.hdl21align``), top first, each mirrored about
    its centre (a pair's two devices at mirrored places, a tail in the middle): the loads above the
    cascodes above the input pair and its tail, a second stage's gain devices beside the loads and
    its current sources beside the input pair; a PMOS input's rows the other way up, its pair on
    top. A device in no row (a folded cascode's second stage, a Miller capacitor) states nothing:
    ALIGN places the amplifier on its own."""
    order = {
        Topology.FIVE_T: [["Mload_d", "Mload"], ["Min_p", "Mtail", "Min_n"]],
        Topology.TELESCOPIC: [
            ["Mstage2_p", "Mload_p", "Mload_n", "Mstage2_n"],
            ["Mcas_load_p", "Mcas_load_n"],
            ["Mcas_in_p", "Mcas_in_n"],
            ["Mstage2_src_p", "Min_p", "Mtail", "Min_n", "Mstage2_src_n"],
        ],
        Topology.FOLDED: [
            ["Mtop_p", "Mtop_n"],
            ["Mcas_fold_p", "Mcas_fold_n"],
            ["Mcas_bottom_p", "Mcas_bottom_n"],
            ["Mbottom_p", "Min_p", "Mtail", "Min_n", "Mbottom_n"],
        ],
        Topology.SELF_BIASED: [["Min_p_p", "Mtail_p", "Min_n_p"], ["Min_p_n", "Mtail_n", "Min_n_n"]],
    }[param.topology]
    if param.input_xtors is MosType.PMOS:
        order = order[::-1]
    placed = rows(*(row(*(module.instances.get(name) for name in names)) for names in order))
    covered = {id(instance) for r in placed.rows for instance in r.instances}
    if all(id(instance) in covered for instance in module.instances.values()):
        place(module, placed)
