"""The capacitive DAC's parameters: the array an N-bit SAR converter switches, its capacitance, how
its stages' weights are built and how fast its stages settle. The netlist (``subckt.py``) makes the
array from them: its stages' weights, each side's capacitance and each stage's drivers.

The defaults are FRIDA-1's fabricated array: 12 bits in 16 stages, MSB redistribution with 5 extra
cycles, at twice the minimum capacitance.
"""

import math
from dataclasses import dataclass
from enum import Enum, auto
from itertools import pairwise
from typing import Annotated

import hdl21 as h
import numpy as np
from hdl21.primitives import MosType, MosVth
from pydantic import Field, NonNegativeInt, PositiveInt
from scipy.constants import Boltzmann

from flow import pipeline
from flow.layout.devices.mosfet.geometry import flavor
from flow.layout.devices.mosfet.netlist import DriverRequest, least_inverter, shared_fanin
from flow.layout.devices.mosfet.table import mosfet_table


class Redundancy(Enum):
    """How an array spends its extra conversion cycles on the binary weight."""

    BINARY = auto()  # no extra cycles
    MSB_SPLIT = auto()  # the heaviest binary weights each split into two halves
    LSB_SPLIT = auto()  # the lightest binary weights of at least 2 each split into two halves
    MSB_REDIST = auto()  # FRIDA's paired overlay: weight moved from the MSB to the later stages


class WeightImpl(Enum):
    """How each stage's weight is built from capacitors. A weight splits at ``coarse_weight`` (64):
    its coarse part whole increments of it, its fine remainder below it. How long a strip or a unit
    capacitor is drawn in a technology is the PDK compile's to find, its geometry the layout's."""

    # Long strips, all one length, each a main and a difference capacitor in line whose bottom
    # plates switch opposite. A fine increment (below 64) is the difference of the two in a single
    # strip; a coarse increment is a whole strip at its longest, its difference capacitor only a
    # minimum-length stub.
    DIFFERENCE_CAPS = auto()
    # Unit capacitors: a coarse increment is one coarse unit capacitor, a fine remainder one smaller
    # unit of its own weight, ever smaller down the stages.
    UNIT_CAPS = auto()


class WellTies(Enum):
    """Whether the side's band rows hold the kit's well-tie cells among their drivers."""

    NONE = auto()  # the simulations' side: its drivers and capacitors alone
    # the layout's: where the kit's rails carry no taps and the side is wider than twice its tie
    # cells' reach, a tie cell abutting each band-row driver (the row ends' alone leave some beyond it)
    ROWS = auto()


@h.paramclass
class Params:
    """An array: its converter's resolution and extra cycles, its capacitance, how its weights
    are built, and the time each stage has to settle.

    ``bits`` N gives the DAC's N - 1 binary steps (the converter compares once before any capacitor
    switches) and each side's minimum switched capacitance C_sw, at which both sides' sampled noise,
    2 kT / C_sw, equals the quantization noise of an LSB of the whole reference, 2 V_REF / 2^N
    (``_switched_f``); ``scale`` multiplies it. The reference's basis: a side samples kT over its
    whole top plate C_top and quantizes to its own LSB, 2 FS / 2^N with FS = V_REF C_sw / C_top, so
    at ``scale`` 1 its sampled noise is C_top / C_sw times its own quantization noise (unit
    capacitors without parasitic: once; FRIDA-1's strips: 1.28 times; the drawn array's parasitic
    more), the record's ``ktc_noise_ratio``. ``extra`` cycles redistribute the binary weight by
    ``redundancy``, never adding capacitance. ``settle_ps`` is the time a stage's drivers have to
    settle its step to half an LSB, at every corner: they are sized ``settle_margin`` times faster
    at the typical corner the device tables hold, and the slow and fast corner runs
    (``flow.capdac.runs.testbenches``) judge the rest."""

    bits = h.Param(
        dtype=Annotated[int, Field(ge=8, le=14)],
        desc="The converter's resolution N, 8 to 14 bits: its DAC has N - 1 binary steps",
        default=12,
    )
    redundancy = h.Param(
        dtype=Redundancy, desc="The scheme that spends the extra cycles", default=Redundancy.MSB_REDIST
    )
    extra = h.Param(dtype=NonNegativeInt, desc="Extra conversion cycles (none for BINARY)", default=5)
    weights = h.Param(
        dtype=tuple[PositiveInt, ...] | None,
        desc="Each stage's weight in units, C0 first, where an array's are its own (a fabricated one's); None: its redundancy's",
        default=None,
    )
    scale = h.Param(dtype=PositiveInt, desc="Each side's capacitance in kT/C minimums", default=2)
    weight_impl = h.Param(dtype=WeightImpl, desc="How each stage's weight is built", default=WeightImpl.DIFFERENCE_CAPS)
    coarse_weight = h.Param(dtype=PositiveInt, desc="The weight of a coarse increment, in units", default=64)
    settle_ps = h.Param(
        dtype=Annotated[float, Field(ge=100, le=5000)],
        desc="Each stage's settling time to half an LSB, 100 to 5000 ps",
        default=1000.0,
    )
    settle_margin = h.Param(
        dtype=Annotated[float, Field(ge=1)],
        desc="How much faster than settle_ps the drivers are sized at the typical corner, for the corners its tables leave out",
        default=2.0,
    )
    well_ties = h.Param(
        dtype=WellTies,
        desc="The kit's well-tie cells among the band rows' drivers (the layout's)",
        default=WellTies.NONE,
    )

    def __post_init__(self) -> None:
        # not in the reference texts: the extra cycles each scheme can spend, as building every array
        #   finds (``_split``, ``_msb_redist``): binary none, a split one for each binary weight of at
        #   least 2 (1 to N - 2), the overlay 1 to N - 4; a redundant scheme at least one, as with none
        #   it is the binary array
        # Terms: N ``bits``; ``steps`` N - 1; ``extra`` the cycles spent.
        # Holds for: 8 to 14 bits; an array's own ``weights`` checked by ``_weights``.
        steps = self.bits - 1
        most = {
            Redundancy.BINARY: 0,
            Redundancy.MSB_SPLIT: steps - 1,
            Redundancy.LSB_SPLIT: steps - 1,
            Redundancy.MSB_REDIST: steps - 3,
        }[self.redundancy]
        least = 0 if self.redundancy is Redundancy.BINARY else 1
        if not least <= self.extra <= most:
            raise ValueError(
                f"a {self.redundancy.name} array of {self.bits} bits spends {least} to {most} extra cycles"
            )
        if self.weights is not None:
            _weights(self)  # an array's own weights checked as it is made


def layout_view(params: Params) -> Params:
    """The side as laid out: its band rows with the kit's well-tie cells where it needs them
    (``WellTies.ROWS``; the simulations draw none)."""
    return Params(**{**params.__dict__, "well_ties": WellTies.ROWS})


pipeline.Params.register(Params)


# ---- the array's arithmetic: its stages' weights and plates (subckt.py builds them; a run's
# TbParams and the model, model.py, read their design capacitances)


def _binary(steps: int) -> list[int]:
    # [Razavi-ADC] Sec. 11.2, p. 212: a binary-weighted CDAC, here C0 the heaviest, 2^(N-2) ... 1 units
    # Terms: N - 1 = ``steps``; each weight a stage's main less difference plates in units.
    # Ours against the source: an N-bit converter's first decision switches nothing, so its DAC has
    #   N - 1 binary steps; the source's binary array carries a grounded dummy unit beside them (Fig.
    #   11.6(b), p. 213; Fig. 11.8(a), p. 214), ours none: the decoder's final decision weighs 1 in its
    #   place (``Model.weights``), so a unit's step is 2^(N-1) / (2^(N-1) - 1) of the source's LSB.
    # Holds for: every array without redundancy (BINARY) and as the base the schemes respread.
    return [2**k for k in range(steps - 1, -1, -1)]


def _split(steps: int, split: range) -> list[int]:
    """The binary weights, those at the indices ``split`` each as two halves."""
    # not in the reference texts: an extra cycle spent by splitting a binary weight into two equal
    #   halves (a redundant SAR scheme of the papers; MSB_SPLIT the heaviest, LSB_SPLIT the lightest
    #   of at least 2), which keeps the sum and makes each half's error recoverable later
    # Terms: ``split`` the stage indices split, one an extra cycle.
    # Holds for: weights of at least 2 (``Params.__post_init__`` admits no more extra cycles).
    return [
        half for k, weight in enumerate(_binary(steps)) for half in ((weight // 2,) * 2 if k in split else (weight,))
    ]


def _msb_redist(steps: int, extra: int) -> list[int]:
    """FRIDA's paired overlay: weight taken from the MSB and laid over the stages from C2 on, in
    pairs of powers of two ending in a fixed tail."""
    # not in the reference texts: FRIDA's paired overlay (its fabricated array's rule): the
    #   binary weights, the MSB less an overlay of paired powers of two ending in the tail
    #   (4, 4, 4, 2, 1, 1 or 4, 4, 2, 2, 2, 1, 1 by parity) laid over the stages from C2 on
    # Terms: ``steps`` N - 1, ``extra`` the extra cycles; the result's sum the binary 2^(N-1) - 1.
    # Holds for: 1 to N - 4 extra cycles (``Params.__post_init__``); ``_weights`` checks the result
    #   is redundant.
    length = steps + extra - 2
    pairs = [weight for power in range(steps + 1, 2, -1) for weight in (2**power, 2**power)]
    overlay = (pairs + ([4, 4, 4, 2, 1, 1] if length % 2 == 0 else [4, 4, 2, 2, 2, 1, 1]))[-length:]
    weights = _binary(steps) + [0] * extra
    weights[0] -= sum(overlay)
    for stage, weight in enumerate(overlay, start=2):
        weights[stage] += weight
    return weights


def _weights(params: Params) -> tuple[int, ...]:
    """Each stage's weight in units, C0 first: one a binary step and an extra cycle, summing to the
    binary array's 2^(N-1) - 1, never rising, and redundant: no stage outweighs the stages after it
    by more than a unit, so each decision's error is recovered later. ``Params`` admits only the
    arrays that build so; this checks they do. An array's own ``weights`` (a fabricated one's) may
    spend more than the binary total."""
    steps = params.bits - 1
    match params.redundancy:
        case _ if params.weights is not None:
            weights = list(params.weights)
        case Redundancy.BINARY:
            weights = _binary(steps)
        case Redundancy.MSB_SPLIT:
            weights = _split(steps, range(params.extra))
        case Redundancy.LSB_SPLIT:
            weights = _split(steps, range(steps - 1 - params.extra, steps - 1))
        case Redundancy.MSB_REDIST:
            weights = _msb_redist(steps, params.extra)
    # not in the reference texts: the redundancy rule of a SAR array (the papers'): w_k <= sum of
    #   the later weights + 1, so a decision wrong by up to the excess is recovered by the later
    #   ones; with the binary sum 2^(N-1) - 1 and the weights never rising
    # Terms: w_k ``weights[stage]``, the later ones ``later[stage]``.
    # Holds for: every scheme's weights and a fabricated array's own (which may spend more).
    later = [sum(weights[stage + 1 :]) for stage in range(len(weights))]
    if (
        len(weights) != steps + params.extra
        or (params.weights is None and sum(weights) != 2**steps - 1)
        or min(weights) < 1
        or any(a < b for a, b in pairwise(weights))
        or any(weight > rest + 1 for weight, rest in zip(weights, later, strict=True))
    ):
        raise ValueError(f"{params} builds no redundant array: {weights}")
    return tuple(weights)


def _switched_f(params: Params, reference_v: float, temperature_k: float = 300.0) -> float:
    """Each side's switched capacitance (F): ``scale`` times the least at which both sides' sampled
    noise, 2 kT/C, equals the quantization noise LSB^2 / 12, LSB = 2 FS / 2^N at a full scale of
    +-``reference_v``: scale 24 kT / LSB^2 = scale 6 kT 4^N / FS^2 (26 fF at 10 bits and 1 V, 6.7
    pF at 14). The difference plates add to the top plate without switching it, so the full scale
    falls below the reference; the analysis measures what the plates give.

    The basis is the reference's full scale, not the side's own (``Params``): a side samples kT over
    its whole top plate, so its own sampled noise over its own quantization noise is C_top / C_sw
    times ``1 / scale``, the record's ``ktc_noise_ratio``."""
    # [Razavi-ADC] Eq. (11.52), p. 230: the kT/C noise the reset leaves on the array; Eq. (12.6),
    #   p. 239: the quantization noise Delta^2 / 12
    # own criterion, from the two: both sides' sampled noise equal to the quantization noise,
    #   2 kT / C = Delta^2 / 12, so C = 24 kT / Delta^2 at ``scale`` 1. The source's own rule, Eq.
    #   (11.53), p. 230, keeps the rms noise near 0.2 LSB; ``scale`` 2 gives sqrt(1 / 24) = 0.204 LSB
    #   of the reference's.
    # Terms: C = C_sw, the side's switched capacitance (main less difference plates, ``Model.plates``);
    #   Delta = ``lsb_v`` = 2 V_REF / 2^N, V_REF = ``reference_v`` the DAC's reference, the kit's supply;
    #   2 the two sides' noise, uncorrelated; T = ``temperature_k``.
    # Ours against the source: the source's C is the whole array on the top plate and its Delta the
    #   converter's own; here C is the switched share and Delta the reference's (the side's own full
    #   scale, V_REF C_sw / C_top, is below V_REF), so at scale 1 the sampled noise exceeds the
    #   quantization noise by C_top / C_sw: stated in ``Params``, reported as ``ktc_noise_ratio``.
    # Holds for: 300 K; ``scale`` minimums; every array and kit.
    lsb_v = 2 * reference_v / 2**params.bits
    return params.scale * 24 * Boltzmann * temperature_k / lsb_v**2


def _pieces(params: Params, weight: int) -> tuple[int, ...]:
    """A stage's pieces' weights: its whole coarse increments, then its fine remainder."""
    # not in the reference texts: a weight w = q c + r cut into q whole increments of the coarse
    #   weight c and a fine remainder r < c (frida's own build of a stage)
    # Terms: c ``coarse_weight``; q, r ``divmod(weight, c)``.
    # Holds for: both builds (WeightImpl).
    whole, fine = divmod(weight, params.coarse_weight)
    return (params.coarse_weight,) * whole + ((fine,) if fine else ())


def _plates(params: Params, piece: int) -> tuple[float, float]:
    """A piece's main and difference plates in units, as drawn without the stub: a strip's two
    share its whole weight, differing by its own; a unit capacitor is all main."""
    # not in the reference texts: a difference strip of c units in all, its main and difference
    #   plates (c + w) / 2 and (c - w) / 2, so they switch opposite to a net w (frida's own build)
    # Terms: c ``coarse_weight``, w ``piece``; a unit capacitor's w units all main.
    # Ours against the source: none (own build); the drawn stub of a whole piece's difference plate
    #   is the PDK's least, which the design leaves out and the analysis measures.
    # Holds for: 0 < w <= c.
    if params.weight_impl is WeightImpl.UNIT_CAPS:
        return float(piece), 0.0
    return (params.coarse_weight + piece) / 2, (params.coarse_weight - piece) / 2


def _design_plates(params: Params, reference_v: float) -> tuple[np.ndarray, np.ndarray]:
    """Each stage's main and difference plates as designed (F, C0 first) at the reference
    ``reference_v``: its pieces' units of the unit capacitance, each side's switched capacitance
    over the total weight; a unit capacitor's all main."""
    weights = _weights(params)
    # [Razavi-ADC] Sec. 11.8, p. 229: the unit capacitance C_0, here the side's switched capacitance
    #   shared over its total weight, C_0 = C_sw / W
    # Terms: C_0 ``unit_f``; C_sw ``_switched_f``; W the sum of the weights.
    # Ours against the source: the source chooses C_0 from matching and noise; here the noise rule
    #   alone sets it (the Monte Carlo grades the matching).
    # Holds for: the design's plates (no stub, no parasitic) at the reference ``reference_v``.
    unit_f = _switched_f(params, reference_v) / sum(weights)
    plates = [[_plates(params, piece) for piece in _pieces(params, weight)] for weight in weights]
    main_f = np.asarray([unit_f * sum(main for main, _ in stage) for stage in plates])
    diff_f = np.asarray([unit_f * sum(diff for _, diff in stage) for stage in plates])
    return main_f, diff_f


def valid(params: Params, pdk: str, drawn: float = 2.2) -> bool:
    """Whether ``params`` is a design in ``pdk``, as far as its heaviest stage's main driver tells:
    whether it can be sized within its budget (``settle_ps`` over ``settle_margin``), the chain of
    inverters that tapers at FO4 from a minimum flip-flop to it leaving time to settle its step.
    The netlist (``flow.capdac.subckt``) sizes it for the plate's load as drawn and raises where the
    chain's FO4 delays take the whole budget; here the same sizing at the design's load times
    ``drawn``, a bound fitted on GF180's 14-bit arrays. It does not check what only the netlist
    finds: a drawn load beyond ``drawn`` times the design's (a 10-bit array's small MSB, other kits'
    stubs and shields), the drivers and the arrangement standing still, a difference driver sized
    for its own plate's step (``subckt._keys``), a light stage's driver, the chain of the request as
    drawn (the netlist lowers a request to its drawn on-resistance and counts that one's chain, which
    can be two inverters longer than the one counted here), or a unit below the kit's smallest
    (drawn at that, its weights then not the design's). An array it admits may still fail
    to build (the run records it so), and one it refuses may build."""
    import importlib

    table = mosfet_table(pdk)
    budget_s = params.settle_ps * 1e-12 / params.settle_margin
    weights = _weights(params)
    supply_v = importlib.import_module(f"pdk.{pdk}.hdl21.site").install.supply_voltage(h.pdk.Corner.TYP)
    main_f, diff_f = _design_plates(params, supply_v)
    top_f = float(main_f.sum() + diff_f.sum())
    # [Razavi-ADC] Eq. (11.10), p. 215: the heaviest plate's load, its capacitance in series with
    #   the rest of the top plate (the series capacitance alone, as ``subckt._plate_load``: the
    #   source's resistance of the rest's switches left to the fitted DRIVER_TAU_SCALE), its stage's
    #   difference plate stepping the other way; [Razavi-ADC] Eq. (8.14), p. 151: ln(step / half an
    #   LSB) time constants; [Baker] Eq. (10.19), p. 334: the half swing at the switching resistance
    # Terms: k C_0 main_f[0], its difference plate diff_f[0], m C_0 ``top_f``; the step 2^(N+1) w_0 / W
    #   LSB (both sides', as ``_drive_r_ohm``); rho the kit's switching over triode resistance; the
    #   kit's DRIVER_TAU_SCALE.
    # Ours against the source: as ``_drive_r_ohm``, the drawn load bounded by the design's times
    #   ``drawn``.
    # Holds for: the heaviest stage (C0), the slowest to size where the budget binds (12 and 14
    #   bits); the kit's typical tables; a drawn load within ``drawn`` times the design's.
    load_f = drawn * float(main_f[0]) * (top_f - float(main_f[0]) + float(diff_f[0])) / top_f
    # fitted, not derived: ``drawn``, the most the drawn MSB load exceeded the design's series load
    #   over GF180's 14-bit grid arrays (stubs, shields and the sense inverter's input), assumed for
    #   every kit and resolution
    # as ``subckt._drive_r_ohm`` (its citations): k time constants, rho, the kit's scale, the FO4 delay
    constants = math.log(2 ** (params.bits + 1) * weights[0] / sum(weights))
    rho = max(
        table.switching_ohm[flavor(tp, MosVth.LOW)] / table.triode_ohm[flavor(tp, MosVth.LOW)]
        for tp in (MosType.NMOS, MosType.PMOS)
    )
    scale = getattr(importlib.import_module(f"pdk.{pdk}.layout.tech"), "DRIVER_TAU_SCALE", 1.0)
    per_ohm = load_f * (constants - math.log(2) + math.log(2) * rho) * scale
    gate_s = table.fo4(MosVth.LOW)
    # the chain's inverters are the kit's row cells: drawn with the kit bound, as the netlist is
    bound = h.pdk.default()
    h.pdk.set_default(importlib.import_module(f"pdk.{pdk}").pdk_logic)
    try:
        # a strip side's difference driver, the least inverter, shares the flip-flop (``_keys``)
        beside = [least_inverter(pdk)] if params.weight_impl is WeightImpl.DIFFERENCE_CAPS else []
        fanin = shared_fanin(pdk, beside)
        r_ohm, chain = budget_s / per_ohm, 0
        while (count := len(DriverRequest(r_ohm, False, fanin=fanin).stages(pdk))) != chain:
            chain = count
            # [Baker] Sec. 11.4, Eqs. (11.17)-(11.21), pp. 359-360: a chain tapered by A, each
            #   inverter the same delay (A = 4 here, FO4, the code's): its inner inverters' delays
            #   first, the chain of the request as asked (the netlist's is the drawn request's)
            if budget_s <= (chain - 1) * gate_s:
                return False
            r_ohm = (budget_s - (chain - 1) * gate_s) / per_ohm
    finally:
        if bound is not None:
            h.pdk.set_default(bound)
    return True


@dataclass(frozen=True, kw_only=True)
class TbParams(pipeline.TbParams):
    """One run of the capacitive DAC's testbench (``flow.capdac.sim.testbench``): the array ``params``
    in ``pdk`` at supply ``vdd`` (its reference), each stage switched up a window into its turn and
    back down the window after (``window_start_s``), its states' edges ``transition_time_s`` long,
    both top plates bled to mid-supply through ``bleed_ohm``. Spectre writes its output every
    ``waveform_sample_interval_s`` and steps no further, at the tolerances ``reltol``, ``vabstol``
    and ``iabstol`` (a 14-bit converter's half LSB is tens of microvolts on steps of up to a volt).
    With ``mc_runs``, the run is instead a Monte Carlo of the plates' mismatch (Pelgrom's
    coefficient ``pelgrom``, a fraction: 0.001 is 0.1 %·sqrt(fF), one capacitor's: each plate is
    drawn at sigma_C = pelgrom sqrt(C 1 fF), so a pair of like plates differs by sqrt(2) times that,
    and Pelgrom's own A_C, a pair's, is sqrt(2) times ``pelgrom``), from ``mc_seed``: each run's
    drawn plates. ``corner`` and ``temperature_c`` are the kit's process corner and the
    temperature; the plates are drawn at the kit's nominal supply ``nominal_vdd`` (None: ``vdd``),
    whatever ``vdd`` a corner run takes."""

    pdk: str = "tsmc65"
    params: Params
    window_s: float
    waveform_sample_interval_s: float
    vdd: float = 1.2
    nominal_vdd: float | None = None
    corner: h.pdk.Corner = h.pdk.Corner.TYP
    temperature_c: float = 25.0
    # not in the reference texts: the bench's own constants: 30 ps state edges (an ideal flip-flop's,
    #   faster than any driver chain), a 1 TOhm bleed (a time constant of seconds on the top plate),
    #   and Spectre's tolerances (vabstol 1 nV against a 14-bit half LSB of tens of uV)
    # Terms: ``transition_time_s`` each state's rise and fall (the flip-flops' outputs, ideal sources);
    #   ``bleed_ohm`` the top plate's resistance to ground (its DC path, vdac to vss); ``reltol``,
    #   ``vabstol``, ``iabstol`` Spectre's relative, voltage and current tolerances.
    # Holds for: a chain's first inverter, slower than a 30 ps edge; a window far shorter than the
    #   bleed's time constant on the top plate; 8 to 14 bits at a supply of about a volt (a half
    #   LSB tens of uV or more).
    transition_time_s: float = 30e-12
    bleed_ohm: float = 1e12
    reltol: float = 1e-4
    vabstol: float = 1e-9
    iabstol: float = 1e-15
    pelgrom: float = 0.0
    mc_runs: int = 0
    mc_seed: int = 1

    def __post_init__(self) -> None:
        if not math.isfinite(float(self.vdd)) or float(self.vdd) <= 0.0:
            raise ValueError("the capacitive DAC testbench's vdd must be finite and positive")
        if self.window_s <= 4 * self.transition_time_s or self.waveform_sample_interval_s <= 0:
            raise ValueError("the testbench's window must hold its edges, and its sample interval be positive")
        if min(self.pelgrom, self.mc_runs) < 0:
            raise ValueError("the testbench's mismatch and Monte Carlo runs must not be negative")

    @property
    def weights(self) -> tuple[int, ...]:
        """Each stage's design weight in units, C0 first (the decoder's, halved)."""
        return _weights(self.params)

    @property
    def stages(self) -> int:
        return len(self.weights)

    @property
    def stop_s(self) -> float:
        """The run: a window before the first stage, two windows a stage."""
        # not in the reference texts: the bench's schedule (``window_start_s``), a window of rest
        #   before the first stage and each stage up and back down in two windows
        return (2 * self.stages + 1) * self.window_s

    @property
    def reference_v(self) -> float:
        """The supply the plates are drawn at: the kit's nominal (``nominal_vdd``), else ``vdd``."""
        return float(self.vdd if self.nominal_vdd is None else self.nominal_vdd)

    @property
    def astate(self) -> tuple[int, ...]:
        """Each stage's state before it switches: the converter's A state, alternating from 0
        (``flow.adc.sim._Converter.tb``)."""
        # [Razavi-ADC] Sec. 16.2.1, p. 346: from equal A states the converter switches one side a
        #   decision (monotonic switching)
        # not in the reference texts: the A state itself, 0 and 1 by turns from C0, so that a stage of
        #   A 0 rises on the side that switches and of A 1 falls (flow.adc's own; the source's scheme
        #   only lowers a side's plates)
        # Holds for: flow.adc's converter (``_Converter.tb``), every array.
        return tuple(stage % 2 for stage in range(self.stages))

    @property
    def main_f(self) -> np.ndarray:
        """Each stage's main plates as designed (F, C0 first): its pieces' units of the unit
        capacitance (each side's switched capacitance over the total weight), at ``reference_v``."""
        return _design_plates(self.params, self.reference_v)[0]

    @property
    def diff_f(self) -> np.ndarray:
        """Each stage's difference plates as designed (F, C0 first); none of unit capacitors."""
        return _design_plates(self.params, self.reference_v)[1]

    @property
    def load_f(self) -> float:
        """Each top plate's load as designed: every plate (its drawn units' capacitance to their
        shield is the layout's, which the simulation holds and the design leaves out)."""
        # not in the reference texts: C_top = sum of every main and difference plate, the plates
        #   being all the design puts on the top plate (the drawn array adds its parasitic: the gain)
        return float(self.main_f.sum() + self.diff_f.sum())

    @property
    def full_scale_v(self) -> float:
        """The differential full scale (+-): the reference across the switched plates' share of the
        top plate, main less difference (as ``flow.adc.sim._Converter.full_scale_v``)."""
        # [Razavi-ADC] Eq. (11.3), p. 211: a CDAC's output k C_0 / (m C_0 + C_L) V_REF, the switched
        #   plates over the top plate's whole load
        # Terms: m C_0 + C_L the top plate's load, ``load_f``: every main and difference plate; k C_0
        #   the main less the difference plates (main_f - diff_f): the difference plates switch the
        #   other way, -V_REF, so by superposition of (11.3) they subtract from the main plates' step;
        #   V_REF ``vdd``, the bench's supply (the DAC's reference).
        # Ours against the source: every stage switched is the full scale, +- as a side's half of the
        #   differential range; the difference plates switch against the main ones (diffcaps 1).
        # Holds for: the design's plates (no parasitic: gain 1); the drawn array's is the analysis's.
        return self.vdd * float(self.main_f.sum() - self.diff_f.sum()) / self.load_f

    @property
    def lsb_v(self) -> float:
        """The converter's LSB: twice the full scale over its codes."""
        # [Razavi-ADC] Sec. 12.2.1, p. 237: Delta = 1 LSB, here the differential range 2 V_FS over 2^N
        # Terms: V_FS ``full_scale_v`` (+-); N ``params.bits``.
        # Holds for: the design's full scale; the drawn array's LSB is ``AnalysisSettling.lsb_v``.
        return 2 * self.full_scale_v / 2**self.params.bits

    @property
    def ideal_step_v(self) -> np.ndarray:
        """Each stage's differential step as its P side rises and its N side falls: twice its main
        less difference plate's share of the top plate, times the reference."""
        # [Razavi-ADC] Eq. (11.3), p. 211: a stage's step, its switched plates over the top plate's
        #   load times V_REF; twice for the two sides the bench switches together
        # Terms: k C_0 a stage's main less difference plates (main_f - diff_f); m C_0 + C_L ``load_f``;
        #   V_REF ``vdd``.
        # Ours against the source: the bench switches both sides, P up and N down (2^N w / W LSB); the
        #   converter switches one side a decision ([Razavi-ADC] Sec. 16.2.1, p. 346), half the step.
        # Holds for: the design's plates; the analysis fits the drawn array's gain to it.
        return 2 * self.vdd * (self.main_f - self.diff_f) / self.load_f

    def window_start_s(self, stage: int, rising: bool) -> float:
        """When the stage's state starts to switch: up a window in, down the window after."""
        # not in the reference texts: the bench's schedule, stage k up at (2k + 1) W and down at (2k + 2) W
        return (2 * stage + (1 if rising else 2)) * self.window_s
