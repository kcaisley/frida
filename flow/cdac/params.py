"""The CDAC's parameters: its design (``Params``: both sides' drivers and plates, and the converter
resolution its settling is measured to), one run of its testbench (``TbParams``), and the testbench
every CDAC is switched on. Every design the parameters admit builds: a main and a difference plate
for each of its drivers' stages, none negative, a weight and a centroid each where given, a positive
resolution, no difference plate where there is no coarse/fine split.

The design is an ADC array with the drivers that switch it, wired as the ADC wires them
(``flow.adc.subckt``): each side's main and difference driver of the array's stages
(``flow.capdriver``), its plates ideal capacitors at the array's extracted values, its top plate's
other load to ground (``Params.dac``); ``adc_bits`` is the converter's resolution, whose half LSB
the settling is measured to.

Every stage switches alone, in its turn, as the SAR loop switches it: its P side's state rises and
its N side's falls a window into its turn (the differential top plate steps up), and back the window
after (it steps down), every other stage held. Each window is long enough for the slowest stage to
settle in its first half, so its end is the step's final value. Half an LSB of a 14-bit converter
is tens of microvolts on steps of up to a volt: the transient runs at a fixed step of a 2000th of
the window (``SAMPLES_PER_WINDOW``) and a tolerance of 1e-4 (``TOLERANCES``), and its steps agree
with the capacitances' within 0.06 LSB. Tighter tolerances (1e-5 and 1e-6, conservative) move no
settling time by more than 1 ps in a 10- and a 14-bit array, at two to three times the run time.
"""

import math
from dataclasses import dataclass

import hdl21 as h
import numpy as np
from pydantic import PositiveInt

from flow import pipeline
from flow.capdriver.subckt import CapDriverParams

# each top plate's DC path in the testbench: to mid-supply, so slow that a window loses nothing
BLEED_OHM = 1e12
# the states' edges
TRANSITION_S = 30e-12
# Spectre's output and its largest step, a fraction of the window, and its tolerances
SAMPLES_PER_WINDOW = 2000
TOLERANCES = {"reltol": 1e-4, "vabstol": 1e-9, "iabstol": 1e-15}
ERRPRESET = "moderate"
# the Monte Carlo of the plates (flow.momcap.subckt.variation), test conditions a chip has one
# realization of: Pelgrom's coefficient from Harpe's unit-length MOM (0.1 %·sqrt(fF), JSSC 2018) to
# about Tripathi and Murmann's lateral MOM (0.85 %, TCAS-I 2014), as fractions, and a process
# gradient of 10 to 100 ppm/mm (oxide-thickness gradients, US5952952), per um; MC_RUNS draws a
# condition from MC_SEED
PELGROMS = (0.001, 0.005, 0.010)
GRADIENTS_PER_UM = (10e-9, 50e-9, 100e-9)
MC_RUNS = 100
MC_SEED = 1
# the converter's two arrays side by side, the N array the P one mirrored, this far apart (um)
PAIR_GAP_UM = 2.0


@h.paramclass
class _Dac:
    """Both sides' drivers and plates (``Params.dac``)."""

    driver = h.Param(
        dtype=CapDriverParams,
        desc="Each side's main and difference drivers: a stage each, its weight",
        default=CapDriverParams(n_stages=3, strengths=(4, 2, 1)),
    )
    main_f = h.Param(
        dtype=tuple[float, ...], desc="C0-first main plate capacitances (F)", default=(400e-15, 200e-15, 100e-15)
    )
    diff_f = h.Param(
        dtype=tuple[float, ...], desc="C0-first difference plate capacitances (F)", default=(0.0, 10e-15, 90e-15)
    )
    parasitic_f = h.Param(dtype=float, desc="Each top plate's other load, to ground (F)", default=250e-15)
    # the coarse/fine split: each stage's weight in coarse units of this weight, its rest in
    # difference fingers (``flow.caparray.layout``); None, no split: every stage in ring units of the
    # array's unit capacitance, no difference plates (``flow.cdac.layout.layout_units``)
    split = h.Param(
        dtype=int | None,
        desc="A coarse unit's weight (0: the array's sized split, its extraction's); None: every stage in "
        "unit capacitors, no difference plates",
        default=0,
    )
    weights = h.Param(
        dtype=tuple[int, ...], desc="C0-first design weights, the decoder's (units); empty: none", default=()
    )
    # each plate's centroid on the die (x, y um), C0 first, for the Monte Carlo's process gradient;
    # empty: every plate at the origin
    main_p_um = h.Param(dtype=tuple[tuple[float, float], ...], desc="P side's main plates' centroids (um)", default=())
    diff_p_um = h.Param(
        dtype=tuple[tuple[float, float], ...], desc="P side's difference plates' centroids (um)", default=()
    )
    main_n_um = h.Param(dtype=tuple[tuple[float, float], ...], desc="N side's main plates' centroids (um)", default=())
    diff_n_um = h.Param(
        dtype=tuple[tuple[float, float], ...], desc="N side's difference plates' centroids (um)", default=()
    )

    def __post_init__(self) -> None:
        stages = self.driver.n_stages
        if not len(self.main_f) == len(self.diff_f) == stages:
            raise ValueError(f"a CDAC needs a main and a difference capacitance for each of its {stages} stages")
        if min(*self.main_f, *self.diff_f, self.parasitic_f) < 0:
            raise ValueError("a CDAC's capacitances must not be negative")
        if self.split is None and any(self.diff_f):
            raise ValueError("a CDAC with no split has no difference plates")
        if self.split is not None and self.split < 0:
            raise ValueError("a CDAC's coarse unit weight must not be negative")
        placed = (self.main_p_um, self.diff_p_um, self.main_n_um, self.diff_n_um, self.weights)
        if any(len(values) not in (0, stages) for values in placed):
            raise ValueError(f"a CDAC's weights and centroids are one a stage ({stages}), or none")


@h.paramclass
class Params:
    """A CDAC and the converter's resolution its settling is measured to. The defaults are a reference
    of three stages, independent of any PDK: 400, 200 and 100 fF main plates less 0, 10 and 90 fF
    difference plates, 250 fF more on each top plate, at 10 bits."""

    dac = h.Param(dtype=_Dac, desc="Both sides' drivers and plates", default=_Dac())
    adc_bits = h.Param(dtype=PositiveInt, desc="The converter's resolution: settling is to half its LSB", default=10)


pipeline.Params.register(Params)


@dataclass(frozen=True, kw_only=True)
class TbParams(pipeline.TbParams):
    """One run of the CDAC's testbench (``flow.cdac.sim.testbench``): the CDAC ``params`` in ``pdk``
    at supply ``vdd`` (the DAC's reference), each stage switched up a window into its turn and back
    down the window after (``window_start_s``), its states' edges ``transition_time_s`` long.
    Spectre writes its output every ``waveform_sample_interval_s`` and steps no further. With
    ``mc_runs``, the run is instead a Monte Carlo of the plates' variation (``pelgrom``,
    ``gradient_per_um``): each run's operating point, the drawn plates read back."""

    pdk: str = "tsmc65"
    params: Params
    window_s: float
    waveform_sample_interval_s: float
    vdd: float = 1.2
    transition_time_s: float = TRANSITION_S
    # the plates' variation: Pelgrom's coefficient (a fraction) and the process gradient per um; with
    # mc_runs, a Monte Carlo of operating points that reads each run's drawn plates instead of the
    # settling transient
    pelgrom: float = 0.0
    gradient_per_um: float = 0.0
    mc_runs: int = 0
    mc_seed: int = MC_SEED

    def __post_init__(self) -> None:
        if not math.isfinite(float(self.vdd)) or float(self.vdd) <= 0.0:
            raise ValueError("the CDAC testbench's vdd must be finite and positive")
        if self.window_s <= 4 * self.transition_time_s or self.waveform_sample_interval_s <= 0:
            raise ValueError("the CDAC testbench's window must hold its edges, and its sample interval be positive")
        if min(self.pelgrom, self.gradient_per_um, self.mc_runs) < 0:
            raise ValueError("the CDAC testbench's variation and Monte Carlo runs must not be negative")

    @property
    def stages(self) -> int:
        return self.params.dac.driver.n_stages

    @property
    def stop_s(self) -> float:
        """The run: a window before the first stage, two windows a stage."""
        return (2 * self.stages + 1) * self.window_s

    @property
    def astate(self) -> tuple[int, ...]:
        """Each stage's state before it switches: the converter's A state, alternating from 0
        (``flow.adc.model.AdcModel.tb``)."""
        return tuple(stage % 2 for stage in range(self.stages))

    @property
    def load_f(self) -> float:
        """Each top plate's whole load: every plate and the other load."""
        dac = self.params.dac
        return sum(dac.main_f) + sum(dac.diff_f) + dac.parasitic_f

    @property
    def full_scale_v(self) -> float:
        """The differential full scale (+-): the reference across the switched plates' share of the
        top plate, main less difference (as ``AdcModel.full_scale_v``)."""
        dac = self.params.dac
        return self.vdd * (sum(dac.main_f) - sum(dac.diff_f)) / self.load_f

    @property
    def lsb_v(self) -> float:
        """The converter's LSB: twice the full scale over its codes."""
        return 2 * self.full_scale_v / 2**self.params.adc_bits

    @property
    def ideal_step_v(self) -> np.ndarray:
        """Each stage's differential step as its P side rises and its N side falls: twice its main
        less difference plate's share of the top plate, times the reference."""
        dac = self.params.dac
        return 2 * self.vdd * (np.asarray(dac.main_f) - np.asarray(dac.diff_f)) / self.load_f

    def window_start_s(self, stage: int, rising: bool) -> float:
        """When the stage's state starts to switch: up a window in, down the window after."""
        return (2 * stage + (1 if rising else 2)) * self.window_s
