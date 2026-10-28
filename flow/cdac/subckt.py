"""The CDAC's circuit: its nets (``Nets``) and its generator (``netlist``), both sides' drivers and
plates of the design ``Params``.

Each stage of each side drives its main plate with a buffer of its state and its difference plate
with the complement: a chain of the generic inverters (``flow.circuit.cells``) whose last stage has
the stage's drive (``dac.driver.strengths``: 1 to 16, or k inverters of 16 in parallel after a
pre-driver for 16 k), one inverter before it on the main side, none on the difference side (two
where a pre-driver is needed). Its plates are FMOM capacitors (``flow.momcap``) at the array's
extracted values, varying with a run's Monte Carlo (``flow.momcap.subckt.variation``) at their
centroids on the die, ``cmain_<side>_<stage>`` and ``cdiff_<side>_<stage>`` (each one's probe
``drawn`` reads its value back); its top plate carries the array's other load to ground. A CDAC
with no difference plates (no coarse/fine split, ``Params.dac.split``) has main drivers only.
"""

from dataclasses import replace

import hdl21 as h
from hdl21.primitives import C

from flow.cdac.capdriver.subckt import PARALLEL_DRIVE, pre_driver, stage_strengths
from flow.circuit.cells import cell
from flow.circuit.ports import module_from_ports
from flow.momcap.subckt import mom_cap

from .params import Params

# a net with a bit per stage (C0 first), its width the design's; a net a run saves
_STAGES = h.Properties(inner={"stages": True})
_SAVE = h.Properties(inner={"save": True})
_STAGES_SAVE = h.Properties(inner={"stages": True, "save": True})


@h.bundle
class Nets:
    """Both sides' states in, both top plates, both sides' main and difference bottom plates, and the
    DAC's supply. The states and the bottom plates (``stages``) have a bit per stage, C0 first."""

    dac_state_p = h.Input(props=_STAGES_SAVE)
    dac_state_n = h.Input(props=_STAGES)
    vdac_p = h.Inout(props=_SAVE)
    vdac_n = h.Inout(props=_SAVE)
    dac_botplate_p = h.Output(props=_STAGES_SAVE)
    dac_botplate_n, dac_botplate_p_diff, dac_botplate_n_diff = (h.Output(props=_STAGES) for _ in range(3))
    vdd_dac = h.Power(direction=h.PortDir.INOUT)
    vss_dac = h.Ground(direction=h.PortDir.INOUT)


def _ports(stages: int, diff: bool) -> dict[str, h.Signal]:
    """``Nets`` as the CDAC's ports: its buses a bit per stage; without difference plates (``diff``),
    no difference bottom plates."""
    return {
        name: replace(net, width=stages) if net.props.get("stages") else net
        for name, net in Nets.signals.items()
        if diff or not name.endswith("_diff")
    }


def _drive(module: h.Module, name: str, state: h.Signal, out: h.Signal, strength: int, invert: bool) -> None:
    """A plate's driver: ``state`` (or its complement, ``invert``) onto ``out`` at the stage's drive,
    the last stage one inverter of it (or k of 16 in parallel), the inverters before it as many as
    the polarity and a pre-driver need."""
    supplies = {"VDD": module.vdd_dac, "VSS": module.vss_dac}
    copies = strength // PARALLEL_DRIVE if strength > PARALLEL_DRIVE else 1
    final = PARALLEL_DRIVE if copies > 1 else strength
    chain = [pre_driver(strength)] if copies > 1 else []
    # the inverters before the last: an odd count for the state, an even one for its complement
    if (len(chain) % 2 == 0) != invert:
        chain.insert(0, 1)
    node = state
    for index, drive in enumerate(chain):
        nxt = module.add(h.Signal(), name=f"{name}_n{index}")
        module.add(cell("inv", drive)(A=node, Y=nxt, **supplies), name=f"{name}_pre{index}")
        node = nxt
    for copy in range(copies):
        module.add(cell("inv", final)(A=node, Y=out, **supplies), name=f"{name}_out{copy}")


# a fresh module every call: the PDK compile rewrites the drivers' generic cells in place
@h.generator(enable_cache=False)
def netlist(params: Params) -> h.Module:
    """Both sides' drivers and their plates."""

    dac = params.dac
    stages = dac.driver.n_stages
    strengths = stage_strengths(dac.driver)

    # a CDAC with no difference plates (no split: every stage in unit capacitors) has no
    # difference drivers
    diff = any(dac.diff_f)
    Cdac = module_from_ports("Cdac", _ports(stages, diff))
    for side in ("p", "n"):
        state, top = getattr(Cdac, f"dac_state_{side}"), getattr(Cdac, f"vdac_{side}")
        kinds = [("main", getattr(Cdac, f"dac_botplate_{side}"), dac.main_f, getattr(dac, f"main_{side}_um"))]
        if diff:
            kinds.append(
                ("diff", getattr(Cdac, f"dac_botplate_{side}_diff"), dac.diff_f, getattr(dac, f"diff_{side}_um"))
            )
        for kind, bottom, plates, placed in kinds:
            for stage, plate in enumerate(plates):
                _drive(Cdac, f"x{kind}_{side}_{stage}", state[stage], bottom[stage], strengths[stage], kind == "diff")
                # an ideal array has no difference plates: its drivers run unloaded
                if plate > 0:
                    x_um, y_um = placed[stage] if placed else (0.0, 0.0)
                    leaf = mom_cap(plate, varies=True, x_um=x_um, y_um=y_um)
                    Cdac.add(leaf(PLUS=bottom[stage], MINUS=top, BULK=Cdac.vss_dac), name=f"c{kind}_{side}_{stage}")
        Cdac.add(C(c=dac.parasitic_f)(p=top, n=Cdac.vss_dac), name=f"cparasitic_{side}")
    return Cdac
