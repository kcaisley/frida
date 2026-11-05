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
from pydantic import Field, NonNegativeInt, PositiveInt
from scipy.constants import Boltzmann

from flow import pipeline


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


@h.paramclass
class Params:
    """An array: its converter's resolution and extra cycles, its capacitance, how its weights
    are built, and the time each stage has to settle.

    ``bits`` N gives the DAC's N - 1 binary steps (the converter compares once before any capacitor
    switches) and each side's minimum capacitance, at which the sampled noise of both sides, 2 kT/C,
    equals the quantization noise; ``scale`` multiplies it. ``extra`` cycles redistribute the binary
    weight by ``redundancy``, never adding capacitance. ``settle_ps`` is the time a stage's drivers
    have to settle its step to half an LSB, which sizes them, ``settle_margin`` times faster at the
    typical corner the device tables hold."""

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
        desc="How much faster than settle_ps the drivers are sized, for the corners the typical tables leave out",
        default=2.0,
    )

    def __post_init__(self) -> None:
        # the extra cycles each scheme can spend, as building every array finds (subckt.py): binary
        # none, a split one for each binary weight of at least 2, the overlay bits - 4; a redundant
        # scheme at least one, as with none it is the binary array
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


pipeline.Params.register(Params)


# ---- the array's arithmetic: its stages' weights and plates (subckt.py builds them; a run's
# TbParams reads their design capacitances)


def _binary(steps: int) -> list[int]:
    return [2**k for k in range(steps - 1, -1, -1)]


def _split(steps: int, split: range) -> list[int]:
    """The binary weights, those at the indices ``split`` each as two halves."""
    return [
        half for k, weight in enumerate(_binary(steps)) for half in ((weight // 2,) * 2 if k in split else (weight,))
    ]


def _msb_redist(steps: int, extra: int) -> list[int]:
    """FRIDA's paired overlay: weight taken from the MSB and laid over the stages from C2 on, in
    pairs of powers of two ending in a fixed tail."""
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
    falls below the reference; the analysis measures what the plates give."""
    lsb_v = 2 * reference_v / 2**params.bits
    return params.scale * 24 * Boltzmann * temperature_k / lsb_v**2


def _pieces(params: Params, weight: int) -> tuple[int, ...]:
    """A stage's pieces' weights: its whole coarse increments, then its fine remainder."""
    whole, fine = divmod(weight, params.coarse_weight)
    return (params.coarse_weight,) * whole + ((fine,) if fine else ())


def _plates(params: Params, piece: int) -> tuple[float, float]:
    """A piece's main and difference plates in units, as drawn without the stub: a strip's two
    share its whole weight, differing by its own; a unit capacitor is all main."""
    if params.weight_impl is WeightImpl.UNIT_CAPS:
        return float(piece), 0.0
    return (params.coarse_weight + piece) / 2, (params.coarse_weight - piece) / 2


@dataclass(frozen=True, kw_only=True)
class TbParams(pipeline.TbParams):
    """One run of the capacitive DAC's testbench (``flow.capdac.sim.testbench``): the array ``params``
    in ``pdk`` at supply ``vdd`` (its reference), each stage switched up a window into its turn and
    back down the window after (``window_start_s``), its states' edges ``transition_time_s`` long,
    both top plates bled to mid-supply through ``bleed_ohm``. Spectre writes its output every
    ``waveform_sample_interval_s`` and steps no further, at the tolerances ``reltol``, ``vabstol``
    and ``iabstol`` (a 14-bit converter's half LSB is tens of microvolts on steps of up to a volt).
    With ``mc_runs``, the run is instead a Monte Carlo of the plates' mismatch (Pelgrom's
    coefficient ``pelgrom``, a fraction: 0.001 is 0.1 %·sqrt(fF)), from ``mc_seed``: each run's
    drawn plates."""

    pdk: str = "tsmc65"
    params: Params
    window_s: float
    waveform_sample_interval_s: float
    vdd: float = 1.2
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
        return (2 * self.stages + 1) * self.window_s

    @property
    def astate(self) -> tuple[int, ...]:
        """Each stage's state before it switches: the converter's A state, alternating from 0
        (``flow.adc.model.AdcModel.tb``)."""
        return tuple(stage % 2 for stage in range(self.stages))

    def _plate_f(self, which: int) -> np.ndarray:
        unit_f = _switched_f(self.params, self.vdd) / sum(self.weights)
        return np.asarray(
            [
                unit_f * sum(_plates(self.params, piece)[which] for piece in _pieces(self.params, weight))
                for weight in self.weights
            ]
        )

    @property
    def main_f(self) -> np.ndarray:
        """Each stage's main plates as designed (F, C0 first): its pieces' units of the unit
        capacitance (each side's switched capacitance over the total weight)."""
        return self._plate_f(0)

    @property
    def diff_f(self) -> np.ndarray:
        """Each stage's difference plates as designed (F, C0 first); none of unit capacitors."""
        return self._plate_f(1)

    @property
    def load_f(self) -> float:
        """Each top plate's load as designed: every plate (its drawn units' capacitance to their
        shield is the layout's, which the simulation holds and the design leaves out)."""
        return float(self.main_f.sum() + self.diff_f.sum())

    @property
    def full_scale_v(self) -> float:
        """The differential full scale (+-): the reference across the switched plates' share of the
        top plate, main less difference (as ``AdcModel.full_scale_v``)."""
        return self.vdd * float(self.main_f.sum() - self.diff_f.sum()) / self.load_f

    @property
    def lsb_v(self) -> float:
        """The converter's LSB: twice the full scale over its codes."""
        return 2 * self.full_scale_v / 2**self.params.bits

    @property
    def ideal_step_v(self) -> np.ndarray:
        """Each stage's differential step as its P side rises and its N side falls: twice its main
        less difference plate's share of the top plate, times the reference."""
        return 2 * self.vdd * (self.main_f - self.diff_f) / self.load_f

    def window_start_s(self, stage: int, rising: bool) -> float:
        """When the stage's state starts to switch: up a window in, down the window after."""
        return (2 * stage + (1 if rising else 2)) * self.window_s
