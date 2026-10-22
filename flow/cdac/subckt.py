"""The CDAC: a capacitor array and the drivers that switch it, both sides, wired as the ADC wires
them (``flow.adc.subckt``), so that its settling is its drivers' on their real loads.

Each side has a main and a difference driver (``flow.capdriver``) of the array's stages; its
plates are ideal capacitors at the array's extracted values (``CapArrayModel.of``: an ADC variant's
3D extraction) or, for an ideal array (``CapArrayConfig.parasitic_cap``), its nominal ones; its top
plate carries the array's other load to ground. The main plates follow each stage's state through
the main drivers (their invert input ``dac_invert``), the difference plates follow it through the
difference drivers, inverted where ``dac_diffcaps`` is high, as the ADC's.

    params = cdac_params("tsmc65", ADC_VARIANTS["12b_plus3"])
    module = Cdac(params)
"""

import hdl21 as h
from hdl21.primitives import C

from flow.caparray.model import CapArrayModel
from flow.caparray.subckt import CapArrayConfig
from flow.capdriver.subckt import CapDriver, CapDriverParams, Cells
from flow.circuit.ports import module_from_ports


def cdac_ports(n_stages: int) -> dict[str, h.Signal]:
    """The C0-first CDAC interface: both sides' states in, their top and bottom plates out."""

    @h.bundle
    class Ports:
        dac_state_p, dac_state_n = (h.Input(width=n_stages) for _ in range(2))
        dac_invert, dac_diffcaps = h.Input(), h.Input()
        vdac_p, vdac_n = h.Inout(), h.Inout()
        dac_botplate_p, dac_botplate_n, dac_botplate_p_diff, dac_botplate_n_diff = (
            h.Output(width=n_stages) for _ in range(4)
        )
        vdd_dac = h.Power(direction=h.PortDir.INOUT)
        vss_dac = h.Ground(direction=h.PortDir.INOUT)

    return Ports.signals


@h.paramclass
class CdacParams:
    """Both sides' drivers and plates."""

    driver = h.Param(dtype=CapDriverParams, desc="Each side's main and difference drivers: a stage each, its weight")
    main_f = h.Param(dtype=tuple[float, ...], desc="C0-first main plate capacitances (F)")
    diff_f = h.Param(dtype=tuple[float, ...], desc="C0-first difference plate capacitances (F)")
    parasitic_f = h.Param(dtype=float, desc="Each top plate's other load, to ground (F)")


def cdac_params(pdk: str, config: CapArrayConfig, *, cells: Cells = Cells.GENERIC) -> CdacParams:
    """The CDAC of ``config`` in ``pdk``: its plates and parasitic as ``CapArrayModel.of`` gives
    them, its drivers of ``config.driver_strengths`` (the ADC model's generic cells by default)."""
    array = CapArrayModel.of(pdk, config)
    return CdacParams(
        driver=CapDriverParams(n_stages=len(array.main_f), strengths=config.driver_strengths, cells=cells),
        main_f=tuple(float(c) for c in array.main_f),
        diff_f=tuple(float(c) for c in array.diff_f),
        parasitic_f=float(array.parasitic_f),
    )


# a fresh module every call: the PDK compile rewrites the drivers' generic cells in place
@h.generator(enable_cache=False)
def Cdac(params: CdacParams) -> h.Module:
    """Generate both sides' drivers and their plates."""

    stages = params.driver.n_stages
    if not len(params.main_f) == len(params.diff_f) == stages:
        raise ValueError(f"Cdac needs a main and a difference capacitance for each of its {stages} stages")
    if min(*params.main_f, *params.diff_f, params.parasitic_f) < 0:
        raise ValueError("Cdac capacitances cannot be negative")

    Cdac = module_from_ports("Cdac", cdac_ports(stages))
    driver = CapDriver(params.driver)
    supplies = {"vdd": Cdac.vdd_dac, "vss": Cdac.vss_dac}
    for side in ("p", "n"):
        state, top = getattr(Cdac, f"dac_state_{side}"), getattr(Cdac, f"vdac_{side}")
        for kind, invert, bottom, plates in (
            ("main", Cdac.dac_invert, getattr(Cdac, f"dac_botplate_{side}"), params.main_f),
            ("diff", Cdac.dac_diffcaps, getattr(Cdac, f"dac_botplate_{side}_diff"), params.diff_f),
        ):
            Cdac.add(
                driver(dac_state=state, dac_drive=bottom, dac_drive_invert=invert, **supplies),
                name=f"xcapdriver_{side}_{kind}",
            )
            for stage, plate in enumerate(plates):
                # an ideal array has no difference plates: its drivers run unloaded
                if plate > 0:
                    Cdac.add(C(c=plate)(p=bottom[stage], n=top), name=f"c{kind}_{side}_{stage}")
        Cdac.add(C(c=params.parasitic_f)(p=top, n=Cdac.vss_dac), name=f"cparasitic_{side}")
    return Cdac
