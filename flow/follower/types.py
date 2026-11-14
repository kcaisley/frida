"""The follower's analysis results (``flow.follower.analysis``), pure data: at each measured point
(a run over the input level or the supply) its transfer and its output impedance, at each step its
large-signal response; and the record's metrics (``Metrics``)."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from flow import pipeline
from flow.pipeline import Analysis, metric


@dataclass(frozen=True, slots=True, kw_only=True)
class AnalysisTransfer(Analysis):
    """Follower transfer at each measured point (a run with the AC stimulus on the input).

    ``vout_v`` is the operating-point output, ``gain_dc`` the response at the lowest frequency,
    ``bandwidth_hz`` where it has fallen 3 dB (``bandwidth``, NaN beyond the sweep),
    ``psrr_dc_db`` that gain over the supply's to the output there, ``idd_a`` the operating
    point's supply current, ``gain_db`` the whole response, one row per point and one column per
    ``frequency_hz``.
    """

    # [Razavi-Analog] Fig. 3.4, p. 48: input and output voltage
    vin_v: np.ndarray
    vout_v: np.ndarray
    # [Razavi-Analog] Eq. (3.8), p. 48: voltage gain
    gain_dc: np.ndarray
    # [Razavi-Analog] Fig. 6.43, p. 204: -3-dB bandwidth
    bandwidth_hz: np.ndarray
    # [Razavi-Analog] Sec. 9.11, p. 400: power supply rejection ratio
    psrr_dc_db: np.ndarray
    # [Razavi-PLL] Example 3.5, p. 70: supply current
    idd_a: np.ndarray
    frequency_hz: np.ndarray
    gain_db: np.ndarray

    @property
    def level_shift_v(self) -> np.ndarray:
        # [Razavi-Analog] Sec. 3.4, p. 68: level shift of a follower
        return self.vin_v - self.vout_v


@dataclass(frozen=True, slots=True, kw_only=True)
class AnalysisImpedance(Analysis):
    """Follower output impedance at each measured point (a run with the AC stimulus on the output
    test current): its magnitude ``zout_ohm`` over ``frequency_hz``, one row per point, and
    ``zout_dc_ohm`` that at the lowest frequency."""

    vin_v: np.ndarray
    # [Razavi-Analog] Eq. (6.63), p. 192: output impedance over frequency
    zout_dc_ohm: np.ndarray
    frequency_hz: np.ndarray
    zout_ohm: np.ndarray


@dataclass(frozen=True, slots=True, kw_only=True)
class AnalysisSlew(Analysis):
    """Follower large-signal step response at each step run (the nominal input).

    ``vout_low_v`` and ``vout_high_v`` are the output's settled levels before the rising and
    falling input steps, ``slew_rate_rise_v_per_s`` and ``slew_rate_fall_v_per_s`` the output's
    10-90 % slopes between them (``slewrate``; the fall's negative), ``settling_rise_s`` and
    ``settling_fall_s`` the time from each input edge until the output stays within 1 % of the step
    (``settlingTime``), ``overshoot_rise`` and ``overshoot_fall`` how far it passes the final
    level, a fraction of the step (``overshoot``), ``idd_a`` the supply current's average over the
    period. The edges are NaN where the output moves less than a tenth of the step.
    """

    vin_v: np.ndarray
    step_v: np.ndarray
    vout_low_v: np.ndarray
    vout_high_v: np.ndarray
    # [Razavi-Analog] Sec. 9.9, p. 391: slew rate
    slew_rate_rise_v_per_s: np.ndarray
    slew_rate_fall_v_per_s: np.ndarray
    # [Razavi-ADC] Sec. 8.2.2, p. 150: settling time
    settling_rise_s: np.ndarray
    settling_fall_s: np.ndarray
    # not in the reference texts: how far a step response passes its final level, a fraction of the
    # step (the calculator's overshoot)
    overshoot_rise: np.ndarray
    overshoot_fall: np.ndarray
    idd_a: np.ndarray


@dataclass(frozen=True, kw_only=True)
class Metrics(pipeline.Metrics):
    """A follower's numbers (``analysis.metrics``), at its nominal input unless said: the output
    level and the level shift, the small-signal gain, bandwidth and PSRR, the supply current, the
    output impedance, the input range over which the gain holds, the step's slew rates, settling
    and overshoot on each edge, and the smallest bandwidth over the supply."""

    vout_v: float = metric("Output level", "none")
    level_shift_v: float = metric("Input minus output level", "none")
    gain_dc: float = metric("Small-signal gain at the lowest frequency", "higher")
    bandwidth_hz: float = metric("-3 dB bandwidth", "higher")
    psrr_dc_db: float = metric("Gain over the supply's gain to the output, at the lowest frequency", "higher")
    idd_a: float = metric("Supply current at the operating point", "lower")
    zout_dc_ohm: float = metric("Output impedance at the lowest frequency", "lower")
    # not in the reference texts: the width of the run of input levels around the nominal one over
    # which the small-signal gain stays within a tenth of its value there (calc.compliance_range)
    input_range_v: float = metric("Input range over which the gain stays within 10 % of the nominal input's", "higher")
    slew_rate_rise_v_per_s: float = metric("Output slope on the rising step", "higher")
    slew_rate_fall_v_per_s: float = metric("Output slope on the falling step (negative)", "lower")
    settling_rise_s: float = metric("Settling to 1 % of the rising step", "lower")
    settling_fall_s: float = metric("Settling to 1 % of the falling step", "lower")
    overshoot_rise: float = metric("Overshoot of the rising step, a fraction of it", "lower")
    overshoot_fall: float = metric("Overshoot of the falling step, a fraction of it", "lower")
    bandwidth_min_supply_hz: float = metric("Smallest -3 dB bandwidth over the supply", "higher")
