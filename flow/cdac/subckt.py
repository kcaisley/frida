"""The CDAC's circuit: its nets (``Nets``) and its generator (``netlist``), both sides' drivers and
plates of the design ``Params``.

Each side has a main and a difference driver (``flow.capdriver``) of the array's stages; its plates
are ideal capacitors at the array's extracted values; its top plate carries the array's other load
to ground. The main plates follow each stage's state through the main drivers (their invert input
``dac_invert``), the difference plates follow it through the difference drivers, inverted where
``dac_diffcaps`` is high, as the ADC's.
"""

from dataclasses import replace

import hdl21 as h
from hdl21.primitives import C

from flow.capdriver.subckt import CapDriver
from flow.circuit.ports import module_from_ports

from .params import Params, valid

# a net with a bit per stage (C0 first), its width the design's; a net a run saves
_STAGES = h.Properties(inner={"stages": True})
_SAVE = h.Properties(inner={"save": True})
_STAGES_SAVE = h.Properties(inner={"stages": True, "save": True})


@h.bundle
class Nets:
    """Both sides' states in, the main plates' invert and the difference plates' select, both top
    plates, both sides' main and difference bottom plates, and the DAC's supply. The states and the
    bottom plates (``stages``) have a bit per stage, C0 first."""

    dac_state_p = h.Input(props=_STAGES_SAVE)
    dac_state_n = h.Input(props=_STAGES)
    dac_invert, dac_diffcaps = h.Input(), h.Input()
    vdac_p = h.Inout(props=_SAVE)
    vdac_n = h.Inout(props=_SAVE)
    dac_botplate_p = h.Output(props=_STAGES_SAVE)
    dac_botplate_n, dac_botplate_p_diff, dac_botplate_n_diff = (h.Output(props=_STAGES) for _ in range(3))
    vdd_dac = h.Power(direction=h.PortDir.INOUT)
    vss_dac = h.Ground(direction=h.PortDir.INOUT)


def _ports(stages: int) -> dict[str, h.Signal]:
    """``Nets`` as the CDAC's ports: its buses a bit per stage."""
    return {name: replace(net, width=stages) if net.props.get("stages") else net for name, net in Nets.signals.items()}


# a fresh module every call: the PDK compile rewrites the drivers' generic cells in place
@h.generator(enable_cache=False)
def netlist(params: Params) -> h.Module:
    """Both sides' drivers and their plates."""

    dac = params.dac
    stages = dac.driver.n_stages
    if not valid(params):
        raise ValueError(
            f"a CDAC needs a main and a difference capacitance, none negative, for each of its {stages} stages"
        )

    Cdac = module_from_ports("Cdac", _ports(stages))
    driver = CapDriver(dac.driver)
    supplies = {"vdd": Cdac.vdd_dac, "vss": Cdac.vss_dac}
    for side in ("p", "n"):
        state, top = getattr(Cdac, f"dac_state_{side}"), getattr(Cdac, f"vdac_{side}")
        for kind, invert, bottom, plates in (
            ("main", Cdac.dac_invert, getattr(Cdac, f"dac_botplate_{side}"), dac.main_f),
            ("diff", Cdac.dac_diffcaps, getattr(Cdac, f"dac_botplate_{side}_diff"), dac.diff_f),
        ):
            Cdac.add(
                driver(dac_state=state, dac_drive=bottom, dac_drive_invert=invert, **supplies),
                name=f"xcapdriver_{side}_{kind}",
            )
            for stage, plate in enumerate(plates):
                # an ideal array has no difference plates: its drivers run unloaded
                if plate > 0:
                    Cdac.add(C(c=plate)(p=bottom[stage], n=top), name=f"c{kind}_{side}_{stage}")
        Cdac.add(C(c=dac.parasitic_f)(p=top, n=Cdac.vss_dac), name=f"cparasitic_{side}")
    return Cdac
