"""The sampler's analysis results (``flow.samp.analysis``), pure data: at each measured point (a run
over the input level or the supply), its tracking and its holding."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from flow.pipeline import Analysis


@dataclass(frozen=True, slots=True, kw_only=True)
class AnalysisTrack(Analysis):
    """Sampler tracking at each measured point.

    ``time_constant_s`` is the time constant of the track phase's settling, from the output's error
    to the input falling to 1/e of its start to its falling to 1/e^2; ``on_resistance_ohm`` that over
    the load capacitance (the switch's own capacitance adds to it, so it bounds the resistance from
    above); ``bandwidth_hz`` 1/(2 pi tau); ``track_error_v`` the output minus the input as the
    clock starts to fall. NaN where the output never settles that far.
    """

    vdd_v: np.ndarray
    vin_v: np.ndarray
    time_constant_s: np.ndarray
    on_resistance_ohm: np.ndarray
    bandwidth_hz: np.ndarray
    track_error_v: np.ndarray


@dataclass(frozen=True, slots=True, kw_only=True)
class AnalysisHold(Analysis):
    """Sampler holding at each measured point.

    ``pedestal_v`` is the held output halfway to the input step minus the output just before
    the clock falls (the charge the opening switch dumps, and its clock feedthrough);
    ``droop_v_per_s`` the held output's slope from there to the step; ``feedthrough`` the held
    output's change over the input's step while the switch is off (V/V).
    """

    vdd_v: np.ndarray
    vin_v: np.ndarray
    pedestal_v: np.ndarray
    droop_v_per_s: np.ndarray
    feedthrough: np.ndarray
