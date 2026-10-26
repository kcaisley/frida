"""The sampling switch's parameters: its design (``Params``), one run of its testbench (``TbParams``),
which designs the generator builds (``valid``), and the bench every switch is characterized on.

Every switch is characterized the same way, so that switches compare: into ``LOAD_F`` (about the
CDAC it samples onto) at a ``PERIOD_S`` clock (``TRACK_S`` tracking, ``TRANSITION_S`` edges), its
input stepping a twelfth of the supply once a period, ``PERIODS`` periods, Spectre's output every
``STROBE_S``; over the input level (``VIN_SWEEP``, fractions of the supply) and over the supply
(``SUPPLY_SWEEP``, fractions of its own) at mid-supply input (``NOMINAL_VIN``). ``CASES`` are the
four switches the characterization compares, by their structure (``STRUCTURE``: the parameters
that make the circuit's devices and their wiring), each with a hand-written floorplan.
"""

import math
from dataclasses import dataclass, field
from enum import Enum, auto

import hdl21 as h
from hdl21.primitives import MosVth

from flow import pipeline


class SwitchType(Enum):
    """Sampling switch topology."""

    NMOS = auto()
    PMOS = auto()
    TGATE = auto()


@h.paramclass
class Params:
    """Sampling switch parameters.

    Device sizing uses multiplier-based scaling:
    - mos_w: Width multiplier (the default 32 is approximately 4µm in FRIDA65A)
    - mos_l: Length multiplier (l=1 means 1×Lmin, e.g., 60nm for a 65nm node)

    This approach allows the same design to be portable across PDKs.
    """

    switch_type = h.Param(dtype=SwitchType, desc="Switch topology", default=SwitchType.TGATE)
    mos_w = h.Param(dtype=int, desc="Width multiplier (× Wmin)", default=32)
    mos_l = h.Param(dtype=int, desc="Length multiplier (× Lmin)", default=1)
    mos_vth = h.Param(dtype=MosVth, desc="Threshold voltage flavor", default=MosVth.LOW)
    dummy = h.Param(dtype=bool, desc="Half-size dummies on dout, clocked opposite their switch", default=False)
    bootstrap = h.Param(dtype=bool, desc="Bootstrapped NMOS gate (NMOS switch only)", default=False)
    boot_w = h.Param(dtype=int, desc="Bootstrap helper device width multiplier", default=4)
    cap_w = h.Param(dtype=int, desc="Bootstrap MOS capacitor width multiplier", default=16)
    cap_l = h.Param(dtype=int, desc="Bootstrap MOS capacitor length multiplier", default=8)


pipeline.Params.register(Params)


def valid(param: Params, pdk: str | None = None) -> bool:
    """Whether the switch can be built, in any PDK: every size positive, a bootstrap only on the NMOS
    switch (it boosts one NMOS gate), a dummy only on a switch of at least two width units (it is
    half its switch)."""
    if min(param.mos_w, param.mos_l, param.boot_w, param.cap_w, param.cap_l) <= 0:
        return False
    if param.bootstrap and param.switch_type != SwitchType.NMOS:
        return False
    return not (param.dummy and param.mos_w < 2)


# the parameters that make a switch's devices and their wiring, and the characterization's four
# switches by them: FRIDA-1's transmission gate (the fabricated sampler, 32 units a side at the
# defaults), the same with half-size dummies, the NMOS switch alone, and the bootstrapped NMOS switch
STRUCTURE = ("switch_type", "dummy", "bootstrap")
CASES = {
    "frida1": {"switch_type": SwitchType.TGATE, "dummy": False, "bootstrap": False},
    "tgate_dummy": {"switch_type": SwitchType.TGATE, "dummy": True, "bootstrap": False},
    "nmos": {"switch_type": SwitchType.NMOS, "dummy": False, "bootstrap": False},
    "bootstrap": {"switch_type": SwitchType.NMOS, "dummy": False, "bootstrap": True},
}
FRIDA1 = Params(**CASES["frida1"])  # the fabricated FRIDA-1 sampler: transmission gate, 32 units each

# the bench: 1 pF at a 10 ns clock (5 ns tracking), 50 ps edges, six periods, a sample every 5 ps
LOAD_F = 1e-12
PERIOD_S = 10e-9
TRACK_S = 5e-9
TRANSITION_S = 50e-12
PERIODS = 6
STROBE_S = 5e-12
# the input over 1/12 to 11/12 of the supply, its middle the nominal point, and the transients the
# record keeps for the viewer (the lowest, the middle and the highest input)
VIN_SWEEP = tuple(step / 12 for step in range(1, 12))
NOMINAL_VIN = 0.5
WAVE_VIN = (VIN_SWEEP[0], NOMINAL_VIN, VIN_SWEEP[-1])
# the supply over 90 to 120 % of its own, at mid-supply input
SUPPLY_SWEEP = (0.9, 1.0, 1.1, 1.2)


@dataclass(frozen=True, kw_only=True)
class TbParams(pipeline.TbParams):
    """One run of the sampler's testbench (flow.samp.sim.testbench): the switch ``params`` in ``pdk``
    at supply ``vdd`` into ``cload``, its input at ``input_voltage`` or, with an ``input_step_v``,
    stepping by it once a period in the middle of each hold phase, its clock tracking while high
    (``clock_high_time_s`` of each ``clock_period_s``), ``periods`` periods; on the bench every
    switch is characterized on unless given. Spectre writes its output every
    ``waveform_sample_interval_s`` and steps no further."""

    pdk: str = "tsmc65"
    params: Params = field(default_factory=Params)
    vdd: float = 1.2
    cload: float = LOAD_F
    input_voltage: float = 0.6
    input_step_v: float = 0.1
    clock_period_s: float = PERIOD_S
    clock_high_time_s: float = TRACK_S
    clock_transition_time_s: float = TRANSITION_S
    clock_delay_s: float = 0.0
    periods: int = PERIODS
    waveform_sample_interval_s: float = STROBE_S

    def __post_init__(self) -> None:
        values = (
            self.vdd,
            self.cload,
            self.input_voltage,
            self.input_step_v,
            self.clock_period_s,
            self.clock_high_time_s,
            self.clock_transition_time_s,
            self.clock_delay_s,
            self.waveform_sample_interval_s,
        )
        if not all(math.isfinite(float(value)) for value in values):
            raise ValueError("sampler testbench values must be finite")
        if not 0.0 < float(self.clock_high_time_s) < float(self.clock_period_s):
            raise ValueError("sampler clock high time must lie inside one period")
        if float(self.clock_transition_time_s) <= 0.0 or float(self.clock_delay_s) < 0.0:
            raise ValueError("sampler clock transition must be positive and delay non-negative")
        if float(self.vdd) <= 0 or float(self.cload) <= 0 or float(self.waveform_sample_interval_s) <= 0:
            raise ValueError("sampler supply, load and waveform spacing must be positive")
        if float(self.input_step_v) < 0 or self.periods <= 0:
            raise ValueError("sampler input step must be non-negative and the periods positive")

    @property
    def stop_s(self) -> float:
        """The run's length: every period."""
        return self.periods * float(self.clock_period_s)
