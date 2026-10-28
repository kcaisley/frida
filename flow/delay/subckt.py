"""
Delay line and ring oscillator generator for FRIDA.

Supports chains of:
- CMOS inverter stages, single-ended or as a pseudo-differential pair of chains
- Coupled pseudo-differential stages: weak cross-coupled inverters across each stage's outputs
- Current-starved stages (series devices biased by vbn and vbp) or a shared tail (vctrl)
- An open chain (a delay line) or a closed ring (an oscillator) with an enable and an injection input
"""

from enum import Enum, auto
from pathlib import Path

import hdl21 as h
from hdl21.primitives import MosType, MosVth

from flow.circuit.devices import mos as _mos
from flow.circuit.devices import write_netlist as _write_netlist
from flow.circuit.ports import module_from_ports


class Stage(Enum):
    INVERTER = auto()  # one CMOS inverter per chain and stage
    COUPLED = auto()  # a pseudo-differential stage with weak cross-coupled inverters across its outputs


class Control(Enum):
    NONE = auto()  # the stages' sources on the rails
    STARVED = auto()  # each inverter between an NMOS foot (vbn) and a PMOS head (vbp)
    TAIL = auto()  # every NMOS source on one shared tail, an NMOS gated by vctrl


@h.paramclass
class DelayParams:
    """Delay line and ring oscillator parameters.

    Device sizing uses multiplier-based scaling:
    - w: Width multiplier (w=4 means 4×Wmin)
    - l: Length multiplier (l=1 means 1×Lmin)

    This approach allows the same design to be portable across PDKs.
    """

    # Topology parameters
    stage = h.Param(dtype=Stage, desc="Stage type", default=Stage.INVERTER)
    control = h.Param(dtype=Control, desc="Delay control", default=Control.NONE)
    stages = h.Param(dtype=int, desc="Number of stages", default=5)
    differential = h.Param(dtype=bool, desc="Two chains, inp to outp and inn to outn", default=False)
    ring = h.Param(dtype=bool, desc="The last stage drives the first (an oscillator)", default=False)
    inject = h.Param(dtype=bool, desc="Injection device across the first stage's outputs (ring)", default=False)

    # Device sizing (multipliers of Wmin/Lmin)
    inv_n_w = h.Param(dtype=int, desc="Inverter NMOS width multiplier", default=4)
    inv_p_w = h.Param(dtype=int, desc="Inverter PMOS width multiplier", default=8)
    inv_l = h.Param(dtype=int, desc="Inverter length multiplier", default=1)
    fb_n_w = h.Param(dtype=int, desc="Coupling inverter NMOS width multiplier", default=2)
    fb_p_w = h.Param(dtype=int, desc="Coupling inverter PMOS width multiplier", default=4)
    starve_n_w = h.Param(dtype=int, desc="Starving NMOS width multiplier", default=4)
    starve_p_w = h.Param(dtype=int, desc="Starving PMOS width multiplier", default=8)
    starve_l = h.Param(dtype=int, desc="Starving device length multiplier", default=2)
    tail_w = h.Param(dtype=int, desc="Shared tail width multiplier", default=16)
    tail_l = h.Param(dtype=int, desc="Shared tail length multiplier", default=2)
    en_w = h.Param(dtype=int, desc="Ring enable device width multiplier", default=2)
    inj_w = h.Param(dtype=int, desc="Injection device width multiplier", default=4)
    vth = h.Param(dtype=MosVth, desc="Device Vth", default=MosVth.LOW)


def is_valid_delay_params(param: DelayParams) -> bool:
    """Check if this chain is valid.

    A coupled stage and an injection device need both chains; a ring needs an inversion around
    the loop, so a single-ended ring has an odd number of stages (a differential one crosses its
    chains at the end); an injection device belongs to a ring. Every size is positive.
    """
    sizes = (
        param.inv_n_w,
        param.inv_p_w,
        param.inv_l,
        param.fb_n_w,
        param.fb_p_w,
        param.starve_n_w,
        param.starve_p_w,
        param.starve_l,
        param.tail_w,
        param.tail_l,
        param.en_w,
        param.inj_w,
    )
    if param.stages < 1 or min(sizes) <= 0:
        return False
    if (param.stage == Stage.COUPLED or param.inject) and not param.differential:
        return False
    if param.inject and not param.ring:
        return False
    if param.ring and not param.differential and param.stages % 2 == 0:
        return False
    return not (param.ring and param.stages < 2)


@h.bundle
class DelayNets:
    inp, inn = h.Input(), h.Input()
    outp, outn = h.Output(), h.Output()
    en = h.Input(desc="Ring enable: low stops the ring, its first stage's p output high")
    inj = h.Input(desc="Injection: high shorts the first stage's outputs")
    vbn, vbp = h.Input(desc="Starving NMOS bias"), h.Input(desc="Starving PMOS bias")
    vctrl = h.Input(desc="Shared tail bias")
    vdd = h.Power(direction=h.PortDir.INOUT)
    vss = h.Ground(direction=h.PortDir.INOUT)


@h.generator
def Delay(param: DelayParams) -> h.Module:
    """
    Delay line and ring oscillator generator.

    Generates chains of inverter or coupled stages, open or closed into a ring, with
    their delay set by sizing, starving devices or a shared tail.

    Uses h.Mos primitives - call pdk.compile() to convert to PDK devices.
    """
    if not is_valid_delay_params(param):
        raise ValueError(f"Invalid delay params: {param}")

    Delay = module_from_ports("Delay", DelayNets.signals)
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
        Delay.Mtail = _mos(tp=MosType.NMOS, vth=param.vth, w=param.tail_w, l=param.tail_l)(
            d=Delay.tail, g=Delay.vctrl, s=Delay.vss, b=Delay.vss
        )

    for k in range(1, n + 1):
        for side in sides:
            # a ring's first stage is a NAND with en (both chains: their delays match)
            gated = param.ring and k == 1
            _build_stage(Delay, param, f"{k}_{side}", nodes[side, k - 1], nodes[side, k], gated)
        if param.stage == Stage.COUPLED:
            # weak inverters across the stage's outputs: each holds the other at its complement
            for side, other in (("p", "n"), ("n", "p")):
                _build_inverter(
                    Delay, param, f"Mfb{k}_{side}", nodes[other, k], nodes[side, k], param.fb_n_w, param.fb_p_w
                )

    if param.ring:
        # enable: with en low the first stage's series NMOS is off and this PMOS holds its p output
        # high (the ring stops there); it starts from that state when en rises
        Delay.Men1_p_p = _mos(tp=MosType.PMOS, vth=param.vth, w=param.en_w, l=1)(
            d=nodes["p", 1], g=Delay.en, s=Delay.vdd, b=Delay.vdd
        )
        if param.inject:
            # injection locking: an NMOS shorts the first stage's outputs while inj is high
            Delay.Minj = _mos(tp=MosType.NMOS, vth=param.vth, w=param.inj_w, l=1)(
                d=nodes["p", 1], g=Delay.inj, s=nodes["n", 1], b=Delay.vss
            )

    return Delay


def _build_stage(module, param: DelayParams, name: str, inp, out, gated: bool = False):
    """One stage of one chain: an inverter from ``inp`` to ``out``, its sources on the rails, on
    starving devices or on the shared tail; ``gated``: its NMOS source through a series NMOS
    gated by en (``Men<name>_n``)."""

    nsrc, psrc = module.vss, module.vdd
    if param.control == Control.STARVED:
        nsrc = module.add(h.Signal(name=f"foot{name}"))
        psrc = module.add(h.Signal(name=f"head{name}"))
        module.add(
            _mos(tp=MosType.NMOS, vth=param.vth, w=param.starve_n_w, l=param.starve_l)(
                d=nsrc, g=module.vbn, s=module.vss, b=module.vss
            ),
            name=f"Mstarve{name}_n",
        )
        module.add(
            _mos(tp=MosType.PMOS, vth=param.vth, w=param.starve_p_w, l=param.starve_l)(
                d=psrc, g=module.vbp, s=module.vdd, b=module.vdd
            ),
            name=f"Mstarve{name}_p",
        )
    elif param.control == Control.TAIL:
        nsrc = module.tail
    if gated:
        series = module.add(h.Signal(name=f"en{name}"))
        module.add(
            _mos(tp=MosType.NMOS, vth=param.vth, w=param.inv_n_w, l=param.inv_l)(
                d=series, g=module.en, s=nsrc, b=module.vss
            ),
            name=f"Men{name}_n",
        )
        nsrc = series
    _build_inverter(module, param, f"Minv{name}", inp, out, param.inv_n_w, param.inv_p_w, nsrc, psrc)


def _build_inverter(module, param: DelayParams, name: str, inp, out, n_w: int, p_w: int, nsrc=None, psrc=None):
    """A CMOS inverter ``<name>_n``, ``<name>_p`` from ``inp`` to ``out``; its sources on ``nsrc`` and
    ``psrc`` (the rails by default)."""

    module.add(
        _mos(tp=MosType.NMOS, vth=param.vth, w=n_w, l=param.inv_l)(
            d=out, g=inp, s=module.vss if nsrc is None else nsrc, b=module.vss
        ),
        name=f"{name}_n",
    )
    module.add(
        _mos(tp=MosType.PMOS, vth=param.vth, w=p_w, l=param.inv_l)(
            d=out, g=inp, s=module.vdd if psrc is None else psrc, b=module.vdd
        ),
        name=f"{name}_p",
    )


def write_netlist(params: DelayParams, path: Path, pdk) -> Path:
    """The delay line or ring after ``pdk``'s compile, as one flat SPICE subcircuit named after
    ``path`` (``flow.circuit.devices.write_netlist``: devices fingered to the row cells in whole unit
    widths)."""

    return _write_netlist(params, path, pdk, generator=Delay, nets=DelayNets)


# ==== Named chains ====

CASES = {
    # five-stage inverter ring oscillator, enabled
    "ring5": DelayParams(stages=5, ring=True),
    # current-starved five-stage ring VCO
    "ring5_starved": DelayParams(stages=5, ring=True, control=Control.STARVED),
    # four-stage pseudo-differential coupled ring, injection locked
    "ring4_coupled": DelayParams(stages=4, ring=True, differential=True, stage=Stage.COUPLED, inject=True),
    # four-stage coupled ring on a shared tail
    "ring4_tail": DelayParams(stages=4, ring=True, differential=True, stage=Stage.COUPLED, control=Control.TAIL),
    # four-stage inverter delay line
    "chain4": DelayParams(stages=4),
    # two-stage coupled differential buffer
    "chain2_coupled": DelayParams(stages=2, differential=True, stage=Stage.COUPLED),
    # four-stage current-starved delay line
    "chain4_starved": DelayParams(stages=4, control=Control.STARVED),
}
