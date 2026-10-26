"""The CDAC's parameters: its design (``Params``: both sides' drivers and plates, and the converter
resolution its settling is measured to), one run of its testbench (``TbParams``), which designs the
generator builds (``valid``), and the testbench every CDAC is switched on.

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


@h.paramclass
class _Dac:
    """Both sides' drivers and plates (``Params.dac``)."""

    driver = h.Param(dtype=CapDriverParams, desc="Each side's main and difference drivers: a stage each, its weight")
    main_f = h.Param(dtype=tuple[float, ...], desc="C0-first main plate capacitances (F)")
    diff_f = h.Param(dtype=tuple[float, ...], desc="C0-first difference plate capacitances (F)")
    parasitic_f = h.Param(dtype=float, desc="Each top plate's other load, to ground (F)")


@h.paramclass
class Params:
    """A CDAC and the converter's resolution its settling is measured to."""

    dac = h.Param(dtype=_Dac, desc="Both sides' drivers and plates")
    adc_bits = h.Param(dtype=int, desc="The converter's resolution: settling is to half its LSB")


def valid(params: Params, pdk: str | None = None) -> bool:
    """Whether the CDAC can be built: a main and a difference plate for each of its drivers' stages,
    no negative capacitance, a positive resolution. It builds in any PDK its plates are given in."""
    dac = params.dac
    return (
        len(dac.main_f) == len(dac.diff_f) == dac.driver.n_stages
        and min(*dac.main_f, *dac.diff_f, dac.parasitic_f) >= 0
        and params.adc_bits > 0
    )


pipeline.Params.register(Params)


@dataclass(frozen=True, kw_only=True)
class TbParams(pipeline.TbParams):
    """One run of the CDAC's testbench (``flow.cdac.sim.testbench``): the CDAC ``params`` in ``pdk``
    at supply ``vdd`` (the DAC's reference), each stage switched up a window into its turn and back
    down the window after (``window_start_s``), its states' edges ``transition_time_s`` long.
    Spectre writes its output every ``waveform_sample_interval_s`` and steps no further."""

    pdk: str = "tsmc65"
    params: Params
    window_s: float
    waveform_sample_interval_s: float
    vdd: float = 1.2
    transition_time_s: float = TRANSITION_S

    def __post_init__(self) -> None:
        if not math.isfinite(float(self.vdd)) or float(self.vdd) <= 0.0:
            raise ValueError("the CDAC testbench's vdd must be finite and positive")
        if self.window_s <= 4 * self.transition_time_s or self.waveform_sample_interval_s <= 0:
            raise ValueError("the CDAC testbench's window must hold its edges, and its sample interval be positive")

    @property
    def stages(self) -> int:
        return self.params.dac.driver.n_stages

    @property
    def stop_s(self) -> float:
        """The run: a window before the first stage, two windows a stage."""
        return (2 * self.stages + 1) * self.window_s

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
