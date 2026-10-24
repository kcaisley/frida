"""The CDAC: a capacitor array and the drivers that switch it, both sides, wired as the ADC wires
them (``flow.adc.subckt``), so that its settling is its drivers' on their real loads.

Each side has a main and a difference driver (``flow.capdriver``) of the array's stages; its
plates are ideal capacitors at the array's extracted values (``CapArrayModel.of``: an ADC array's
3D extraction at its unit capacitance); its top plate carries the array's other load to ground.
The main plates follow each stage's state through the main drivers (their invert input
``dac_invert``), the difference plates follow it through the difference drivers, inverted where
``dac_diffcaps`` is high, as the ADC's.

The drivers are the array's, not a parameter of their own (``driver_strengths``): each stage's,
main and difference alike, is the weakest generic drive (an XOR, a buffer of 2 to 16 after it, or
k buffers of 16 in parallel) whose RC estimate (``flow.capdriver.model``: its drive resistance
through the stage's plate in series with the rest of the top plate, after its intrinsic delay)
settles the plate's step to half the converter's LSB within ``SETTLING_TARGET_S``. So a stage's
drive scales with its plate and with the log of its step over the LSB, and every stage settles in
about the same time at every resolution and capacitance. Only FRIDA-1's fabricated arrays set
``CapArrayConfig.driver_strengths`` (their clocked XORs' bands).

    params = cdac_params("tsmc65", ADC_ARRAYS["12b_msb_redist3_x2"])
    module = Cdac(params)
"""

import importlib
import math

import hdl21 as h
from hdl21.primitives import C

from flow.caparray.model import CapArrayModel
from flow.caparray.subckt import CapArrayConfig
from flow.capdriver.subckt import GENERIC_STRENGTHS, PARALLEL_DRIVE, CapDriver, CapDriverParams, Cells
from flow.circuit.ports import module_from_ports

# every stage's step within half the converter's LSB this long after its state's edge, by the
# drivers' RC estimate: about a third of a decision's window at 10 MS/s
SETTLING_TARGET_S = 1e-9
# the drives a stage may take, weakest first: one cell, then up to 16 buffers of 16 in parallel
STRENGTHS = (*GENERIC_STRENGTHS, *range(2 * PARALLEL_DRIVE, 16 * PARALLEL_DRIVE + 1, PARALLEL_DRIVE))


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


def supply_v(pdk: str) -> float:
    """The PDK's typical core supply: the DAC's reference."""
    return round(importlib.import_module(f"pdk.{pdk}.hdl21.site").install.supply_voltage(h.pdk.Corner.TYP), 4)


def settling_estimate_s(
    pdk: str, strength: int, main_f: float, diff_f: float, load_f: float, vdd: float, tolerance_v: float, *, simulate
) -> float:
    """A stage's RC settling at a drive: each plate's driver's intrinsic delay and its time
    constant (its resistance through the plate in series with the rest of the top plate) over the
    log of the plate's share of the differential step over the tolerance, the slower plate's."""
    from flow.capdriver.model import CapDriverModel

    slowest = 0.0
    for plate in (main_f, diff_f):
        if plate <= 0:
            continue
        driver = CapDriverModel.of(pdk, strength, load_f=plate, simulate=simulate)
        tau = driver.resistance_ohm * plate * (load_f - plate) / load_f
        step = 2 * vdd * plate / load_f
        slowest = max(slowest, driver.intrinsic_delay_s + tau * math.log(max(1.0, step / tolerance_v)))
    return slowest


def derive_strengths(
    pdk: str, main_f, diff_f, parasitic_f: float, adc_bits: int, *, simulate: bool = False
) -> tuple[int, ...]:
    """Each stage's drive, C0 first: the weakest of ``STRENGTHS`` whose estimate
    (``settling_estimate_s``) settles the stage within ``SETTLING_TARGET_S`` to half the LSB of an
    ``adc_bits`` converter on these plates; the strongest where none does."""
    load = sum(main_f) + sum(diff_f) + parasitic_f
    vdd = supply_v(pdk)
    tolerance = vdd * (sum(main_f) - sum(diff_f)) / load / 2**adc_bits
    return tuple(
        next(
            (
                strength
                for strength in STRENGTHS
                if settling_estimate_s(pdk, strength, main, diff, load, vdd, tolerance, simulate=simulate)
                <= SETTLING_TARGET_S
            ),
            STRENGTHS[-1],
        )
        for main, diff in zip(main_f, diff_f, strict=True)
    )


def driver_strengths(
    pdk: str,
    config: CapArrayConfig,
    array: CapArrayModel | None = None,
    *,
    cells: Cells = Cells.GENERIC,
    simulate: bool = False,
) -> tuple[int, ...] | None:
    """The drives of ``config``'s stages: FRIDA-1's fabricated bands where it sets them, the clocked
    XORs' defaults (None) for those cells, else derived from its extracted plates
    (``derive_strengths``) for its n_dac + 1 bit converter."""
    if config.driver_strengths is not None or cells != Cells.GENERIC:
        return config.driver_strengths
    array = CapArrayModel.of(pdk, config) if array is None else array
    return derive_strengths(pdk, array.main_f, array.diff_f, array.parasitic_f, config.n_dac + 1, simulate=simulate)


def cdac_params(pdk: str, config: CapArrayConfig, *, cells: Cells = Cells.GENERIC) -> CdacParams:
    """The CDAC of ``config`` in ``pdk``: its plates and parasitic as ``CapArrayModel.of`` gives
    them, its drivers derived from them (``driver_strengths``; the ADC model's generic cells by
    default)."""
    array = CapArrayModel.of(pdk, config)
    strengths = driver_strengths(pdk, config, array, cells=cells)
    return CdacParams(
        driver=CapDriverParams(n_stages=len(array.main_f), strengths=strengths, cells=cells),
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
