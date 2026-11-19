"""The sampler's analysis results (``flow.samp.analysis``), pure data: at each measured point (a run
over the input level, the supply or the corners), its tracking, its holding, its boost, its
devices' stress, its acquisition of a full-scale step, its held sine, its droop over the ADC's hold
(with the DAC's step or without) and its energy."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from flow.pipeline import Analysis


@dataclass(frozen=True, slots=True, kw_only=True)
class AnalysisTrack(Analysis):
    """Sampler tracking at each measured point.

    ``tau_s`` is the time constant of the track phase's settling, from the output's error to the
    input falling to 1/e of its largest (at the clock's rise, or after the closing switch's kick)
    to its falling to 1/e^2, the median over the input's rising steps or
    over the falling ones, the slower; ``ron_ohm`` that over the load capacitance (the switch's own
    capacitance adds to it, so it bounds the resistance from above); ``bandwidth_hz``
    1/(2 pi tau); ``track_error_v`` |output - input| as the clock starts to fall, the median over
    the rising steps or over the falling ones, the larger. NaN where the output never settles that
    far.
    """

    # [Razavi-Analog] Eq. (13.31), p. 552: tau = R_on C_H, the sampler's time constant
    # [Razavi-Analog] Eq. (2.11), p. 15: R_on of a device in deep triode; Eq. (13.31) solved for it
    # [Razavi-ADC] Eq. (3.26), p. 29: the RC sampler's attenuation, -3 dB at R_on C_1 omega = 1
    # [Razavi-ADC] Sec. 3.9.1, p. 53: the error |V_in - V_out| left when acquisition ends
    vdd_v: np.ndarray
    vin_v: np.ndarray
    tau_s: np.ndarray
    ron_ohm: np.ndarray
    bandwidth_hz: np.ndarray
    track_error_v: np.ndarray


@dataclass(frozen=True, slots=True, kw_only=True)
class AnalysisHold(Analysis):
    """Sampler holding at each measured point.

    ``pedestal_v`` is the step the opening switch leaves on the held output: the held output
    halfway to the input step, its droop since the clock fell taken back, minus the output just
    before the clock falls (the charge the opening switch dumps, and its clock feedthrough);
    ``droop_v_per_s`` the held output's slope from there to the step; ``feedthrough`` the held
    output's change over the input's step while the switch is off, its droop taken out (V/V).
    """

    # [Razavi-Analog] Eq. (13.26), p. 550: the pedestal, the voltage error the opening switch leaves on C_H
    # [Pelgrom] Eq. (8.3), p. 387: V_droop = -I_leak T_hold / C_hold, a linear fall over the hold
    # [Pelgrom] Sec. 8.2.3, p. 387: hold-mode feedthrough
    vdd_v: np.ndarray
    vin_v: np.ndarray
    pedestal_v: np.ndarray
    droop_v_per_s: np.ndarray
    feedthrough: np.ndarray


@dataclass(frozen=True, slots=True, kw_only=True)
class AnalysisBoost(Analysis):
    """A bootstrapped switch's boost at each measured point: ``vgs_v`` the switch's V_GS (its
    boosted gate minus the input) as the clock starts to fall, the median over the track phases;
    ``gate_max_v`` the boosted gate's highest voltage over the run. NaN for a switch without a
    boosted gate."""

    # [Razavi-ADC] Sec. 3.8.1, p. 43: the bootstrapped gate holds V_GS = V_b as V_in swings
    # [Razavi-ADC] Eq. (3.72), p. 50: V_P - V_in, its fall with V_in through the top plate's parasitic
    vdd_v: np.ndarray
    vin_v: np.ndarray
    vgs_v: np.ndarray
    gate_max_v: np.ndarray


@dataclass(frozen=True, slots=True, kw_only=True)
class AnalysisStress(Analysis):
    """The devices' voltages at each measured point (a run that saved them), over its operating
    point and its whole transient: ``terminal_v`` the largest |V_GS|, |V_GD| or |V_DS| of any
    transistor, ``gate_bulk_v`` the largest |V_GB| (a kit's reliability rule may bound it; under an inverted
    channel the oxide carries V_GS), ``junction_v`` the largest forward
    bias of any source or drain junction (negative: all reverse biased)."""

    # [Razavi-ADC] Sec. 3.8.2, p. 48: a device whose terminal voltages exceed the technology's is stressed
    # [Razavi-Analog] Sec. 2.1, p. 9: the source and drain junctions to the bulk kept reverse biased
    vdd_v: np.ndarray
    vin_v: np.ndarray
    terminal_v: np.ndarray
    gate_bulk_v: np.ndarray
    junction_v: np.ndarray


@dataclass(frozen=True, slots=True, kw_only=True)
class AnalysisAcquisition(Analysis):
    """The acquisition of a full-scale step at each measured point: ``acquisition_s[point, k]`` the
    time from the clock's rising mid-supply crossing until |V_in - V_out| stays within half an LSB
    of the supply at ``bits[k]`` bits, the slower of the rising and the falling step (NaN where it
    does not by the time the clock starts to fall); ``track_error_v`` the larger |V_in - V_out| either step leaves as the
    clock starts to fall."""

    # [Razavi-ADC] Fig. 3.50, p. 53: the acquisition time and the error left when it ends
    # [Razavi-ADC] Eq. (3.82), p. 54: t_acq to settle within half an LSB
    vdd_v: np.ndarray
    vin_v: np.ndarray
    step_v: np.ndarray
    bits: np.ndarray
    acquisition_s: np.ndarray
    track_error_v: np.ndarray


@dataclass(frozen=True, slots=True, kw_only=True)
class AnalysisSine(Analysis):
    """A sine's held samples at each measured point (a tone): ``frequency_hz`` the tone,
    ``thd_db`` the held samples' harmonic distortion, ``model_error_v`` the largest |held -
    predicted| over the held samples whose input lies inside the input range the level runs settle
    over (where predicted is the behavioral model's, ``flow.samp.model.Model.sample``: the input at
    the clock's fall lagging by R(V_in) C dV_in/dt, plus the pedestal at V_in, both from the level
    runs; outside that range the model holds the previous sample), ``aperture_s`` and
    ``aperture_s_per_v`` the sampling instant the rest of the error over those samples implies,
    a + b V_in later (a least-squares fit of the rest against the slope)."""

    # [Razavi-ADC] Eq. (3.85), p. 55: the harmonics of the held samples
    # [Razavi-ADC] Fig. 3.25(c), p. 37: the switch turns off as CK falls through V_in + V_TH, a signal-dependent instant
    # [Pelgrom] Sec. 8.3.2, p. 390: signal-dependent aperture delay
    vdd_v: np.ndarray
    vin_v: np.ndarray
    frequency_hz: np.ndarray
    thd_db: np.ndarray
    model_error_v: np.ndarray
    aperture_s: np.ndarray
    aperture_s_per_v: np.ndarray


@dataclass(frozen=True, slots=True, kw_only=True)
class AnalysisDroop(Analysis):
    """The held output's droop over the middle half of each hold, at each measured point:
    ``temperature_c`` the run's, ``step_v`` the step the DAC's first decision moves the held output
    by meanwhile (0: none), ``droop_v_per_s`` its slope (the off switch's and its junctions' leakage
    over the load), the median over the holds after the first."""

    # [Pelgrom] Eq. (8.3), p. 387: V_droop = -I_leak T_hold / C_hold
    # [Razavi-ADC] Sec. 16.2.1, p. 346: monotonic switching moves one side's top plate while it is held
    vdd_v: np.ndarray
    vin_v: np.ndarray
    temperature_c: np.ndarray
    step_v: np.ndarray
    droop_v_per_s: np.ndarray


@dataclass(frozen=True, slots=True, kw_only=True)
class AnalysisEnergy(Analysis):
    """The energy a clock period takes at each measured point: ``energy_per_cycle_j`` the supply
    voltage times the charge the supply's and both clocks' sources deliver over a whole period (the
    charge a driver of each would draw from its supply; a clock source's return of the gate charge
    on its falling edge is not counted), the median over the periods after the first."""

    # [Baker] Eq. (11.15), p. 355: P_avg = V_DD I_avg, the current drawn from V_DD; over a clock period, its energy
    vdd_v: np.ndarray
    vin_v: np.ndarray
    energy_per_cycle_j: np.ndarray
