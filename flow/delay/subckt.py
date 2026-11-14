"""The delay line and ring oscillator's circuit: its nets (``Nets``) and its generator (``netlist``),
the module ``Delay`` of the design ``Params``.

Chains of:
- CMOS inverter stages, single-ended or as a pseudo-differential pair of chains
- Coupled pseudo-differential stages: weak cross-coupled inverters across each stage's outputs
- Current-starved stages (series devices biased by vbn and vbp) or a shared tail (vctrl)
- An open chain (a delay line) or a closed ring (an oscillator) with an enable and an injection input:
  a ring's first stage a NAND with en (its p output held high while en is low) and, in a
  differential ring, the n chain's first stage a NOR with en's complement (its n output held low),
  so a disabled differential ring rests in a differential state, each stage's outputs complementary

The generator uses h.Mos primitives; the PDK's compile makes them its devices.
"""

import hdl21 as h
from hdl21.primitives import MosType

from flow.circuit.ports import module_from_ports
from flow.layout.devices.mosfet.netlist import mos
from flow.layout.hdl21align import place, row, rows

from .params import Control, Params, Stage


@h.bundle
class Nets:
    inp, inn = h.Input(), h.Input()
    outp, outn = h.Output(), h.Output()
    en = h.Input(desc="Ring enable: low stops the ring, its first stage's p output high and n output low")
    inj = h.Input(desc="Injection: high shorts the first stage's outputs")
    vbn, vbp = h.Input(desc="Starving NMOS bias"), h.Input(desc="Starving PMOS bias")
    vctrl = h.Input(desc="Shared tail bias")
    vdd = h.Power(direction=h.PortDir.INOUT)
    vss = h.Ground(direction=h.PortDir.INOUT)


# a fresh module every call: the PDK compile rewrites its devices in place, and a run's bench
# and its area each compile one
@h.generator(enable_cache=False)
def netlist(param: Params) -> h.Module:
    """The delay line or ring oscillator: chains of inverter or coupled stages, open or closed
    into a ring, their delay set by sizing, starving devices or a shared tail."""
    Delay = module_from_ports("Delay", Nets.signals)
    sides = ("p", "n") if param.differential else ("p",)
    n = param.stages

    # Stage k (1..n) drives node <side><k>; the last stage drives the outputs. A ring's first
    # stage takes the last stage's outputs, crossed between the chains (one more inversion).
    nodes = {}
    for side in sides:
        for k in range(1, n):
            nodes[side, k] = Delay.add(h.Signal(name=f"{side}{k}"))
        nodes[side, n] = Delay.outp if side == "p" else Delay.outn
    for side in sides:
        if not param.ring:
            nodes[side, 0] = Delay.inp if side == "p" else Delay.inn
        elif param.differential:
            nodes[side, 0] = nodes["n" if side == "p" else "p", n]
        else:
            nodes[side, 0] = nodes[side, n]

    if param.control == Control.TAIL:
        Delay.tail = h.Signal(desc="Shared NMOS source of every stage")
        Delay.Mtail = mos(tp=MosType.NMOS, vth=param.vth, w=param.tail_w, l=param.tail_l)(
            d=Delay.tail, g=Delay.vctrl, s=Delay.vss, b=Delay.vss
        )

    if param.ring and param.differential:
        # en's complement, for the n chain's first stage
        Delay.enb = h.Signal(desc="The enable's complement")
        _build_inverter(Delay, param, "Menb", Delay.en, Delay.enb, param.en_w, param.en_w)

    for k in range(1, n + 1):
        for side in sides:
            # a ring's first stage is gated by the enable: the p chain's through a series NMOS on en
            # (a NAND), the n chain's through a series PMOS on its complement (a NOR), so the gated
            # transitions, p1 falling and n1 rising, slow together
            gate = None if not (param.ring and k == 1) else (MosType.NMOS if side == "p" else MosType.PMOS)
            _build_stage(Delay, param, f"{k}_{side}", nodes[side, k - 1], nodes[side, k], gate)
        if param.stage == Stage.COUPLED:
            # weak inverters across the stage's outputs: each holds the other at its complement
            for side, other in (("p", "n"), ("n", "p")):
                _build_inverter(
                    Delay, param, f"Mfb{k}_{side}", nodes[other, k], nodes[side, k], param.fb_n_w, param.fb_p_w
                )

    if param.ring:
        # enable: with en low the first stage's series NMOS is off and this PMOS holds its p output
        # high; in a differential ring the n chain's series PMOS is off and an NMOS holds its n output
        # low, so the coupling inverters agree with the chains and every stage rests complementary,
        # not in the state of equal chains ([Razavi-PLL] Sec. 4.9.3, Fig. 4.36, p. 130: a loop of an
        # even number of inverters latches). The ring starts from that state when en rises
        Delay.Men1_p_p = mos(tp=MosType.PMOS, vth=param.vth, w=param.en_w, l=1)(
            d=nodes["p", 1], g=Delay.en, s=Delay.vdd, b=Delay.vdd
        )
        if param.differential:
            Delay.Men1_n_n = mos(tp=MosType.NMOS, vth=param.vth, w=param.en_w, l=1)(
                d=nodes["n", 1], g=Delay.enb, s=Delay.vss, b=Delay.vss
            )
        if param.inject:
            # injection locking: an NMOS shorts the first stage's outputs while inj is high
            Delay.Minj = mos(tp=MosType.NMOS, vth=param.vth, w=param.inj_w, l=1)(
                d=nodes["p", 1], g=Delay.inj, s=nodes["n", 1], b=Delay.vss
            )

    _place(Delay, param)
    return Delay


def _build_stage(module, param: Params, name: str, inp, out, gate: MosType | None = None):
    """One stage of one chain: an inverter from ``inp`` to ``out``, its sources on the rails, on
    starving devices or on the shared tail; ``gate`` NMOS: its NMOS source through a series NMOS on
    en (``Men<name>_n``), PMOS: its PMOS source through a series PMOS on en's complement
    (``Men<name>_p``)."""

    nsrc, psrc = module.vss, module.vdd
    if param.control == Control.STARVED:
        nsrc = module.add(h.Signal(name=f"foot{name}"))
        psrc = module.add(h.Signal(name=f"head{name}"))
        module.add(
            mos(tp=MosType.NMOS, vth=param.vth, w=param.starve_n_w, l=param.starve_l)(
                d=nsrc, g=module.vbn, s=module.vss, b=module.vss
            ),
            name=f"Mstarve{name}_n",
        )
        module.add(
            mos(tp=MosType.PMOS, vth=param.vth, w=param.starve_p_w, l=param.starve_l)(
                d=psrc, g=module.vbp, s=module.vdd, b=module.vdd
            ),
            name=f"Mstarve{name}_p",
        )
    elif param.control == Control.TAIL:
        nsrc = module.tail
    if gate is MosType.NMOS:
        series = module.add(h.Signal(name=f"en{name}"))
        module.add(
            mos(tp=MosType.NMOS, vth=param.vth, w=param.inv_n_w, l=param.inv_l)(
                d=series, g=module.en, s=nsrc, b=module.vss
            ),
            name=f"Men{name}_n",
        )
        nsrc = series
    elif gate is MosType.PMOS:
        series = module.add(h.Signal(name=f"en{name}"))
        module.add(
            mos(tp=MosType.PMOS, vth=param.vth, w=param.inv_p_w, l=param.inv_l)(
                d=series, g=module.enb, s=psrc, b=module.vdd
            ),
            name=f"Men{name}_p",
        )
        psrc = series
    _build_inverter(module, param, f"Minv{name}", inp, out, param.inv_n_w, param.inv_p_w, nsrc, psrc)


def _build_inverter(module, param: Params, name: str, inp, out, n_w: int, p_w: int, nsrc=None, psrc=None):
    """A CMOS inverter ``<name>_n``, ``<name>_p`` from ``inp`` to ``out``; its sources on ``nsrc`` and
    ``psrc`` (the rails by default)."""

    module.add(
        mos(tp=MosType.NMOS, vth=param.vth, w=n_w, l=param.inv_l)(
            d=out, g=inp, s=module.vss if nsrc is None else nsrc, b=module.vss
        ),
        name=f"{name}_n",
    )
    module.add(
        mos(tp=MosType.PMOS, vth=param.vth, w=p_w, l=param.inv_l)(
            d=out, g=inp, s=module.vdd if psrc is None else psrc, b=module.vdd
        ),
        name=f"{name}_p",
    )


def _place(module: h.Module, param: Params) -> None:
    """Where ALIGN puts each device (flow.layout.hdl21align), rows top first: the starving PMOS
    heads, the inverters' PMOS, the coupling PMOS, the coupling NMOS, the inverters' NMOS, the
    starving NMOS feet. A ring's stages go in its folded order (1, n, 2, n - 1, ...: every
    connection, the loop's too, spans at most two places), each stage's p-chain device beside its
    n-chain twin, the enable devices outside the first stage and the injection device between its
    chains, the enable's inverter at the rows' left end; a delay line's in their own order, a
    differential one's rows mirrored about their centre, a p-chain device left and its n-chain
    twin right. The shared tail sits in the middle of the inverters' NMOS row."""
    n = param.stages
    folded = [k for pair in zip(range(1, n + 1), range(n, 0, -1), strict=True) for k in pair][:n]
    order = folded if param.ring else list(range(1, n + 1))
    mirrored = param.differential and not param.ring
    if mirrored:
        places = [(k, "p") for k in order] + [(k, "n") for k in reversed(order)]
    else:
        places = [(k, side) for k in order for side in (("p", "n") if param.differential else ("p",))]
    # each first-stage enable device outside its inverter: left of the p chain's, right of the n chain's
    pmos, nmos = ["Menb_p"], ["Menb_n"]
    for index, (k, side) in enumerate(places):
        if index == len(places) // 2:
            nmos.append("Mtail")
        for devices, kind in ((pmos, "p"), (nmos, "n")):
            enable = [f"Men{k}_{side}_{kind}"] if k == 1 else []
            inverter = f"Minv{k}_{side}_{kind}"
            devices += [inverter, *enable] if side == "n" else [*enable, inverter]
        if k == 1 and side == "p":
            nmos.append("Minj")
    named = [
        [f"Mstarve{k}_{side}_p" for k, side in places],
        pmos,
        [f"Mfb{k}_{side}_p" for k, side in places],
        [f"Mfb{k}_{side}_n" for k, side in places],
        nmos,
        [f"Mstarve{k}_{side}_n" for k, side in places],
    ]
    place(module, rows(*(row(*(module.instances.get(name) for name in names)) for names in named)), symmetric=mirrored)
