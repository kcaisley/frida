"""The charge-sensitive amplifier's figures as ``Plot`` specs (``flow.pipeline.Plot``), each from
analysis results alone: its response to each charge (a figure a charge), its amplitude, gain and
time over threshold over the charge, its output noise density, and its gain, peaking time, ENC and
power over the supply (the record's plots). The viewer draws a record's from its JSON,
``flow.plot.render`` any with matplotlib (the CLI's figures step)."""

from __future__ import annotations

import numpy as np

from flow.pipeline import Plot, plot

from .params import CHARGES_C, PULSE_STEP_S
from .types import AnalysisNoise, AnalysisPulse, AnalysisSupply


def _pulse(pulse: AnalysisPulse, charge_c: float) -> Plot:
    """The response to ``charge_c``, one of ``pulse``'s charges: the output's excursion from its
    baseline, from the injection on, about every ``PULSE_STEP_S``."""
    rows = np.flatnonzero(np.isclose(pulse.charge_c, charge_c, rtol=1e-9, atol=0.0))
    if not len(rows):
        raise ValueError(f"the pulse result holds no response to {charge_c:g} C")
    step = float(np.median(np.diff(pulse.time_s))) if len(pulse.time_s) > 1 else PULSE_STEP_S
    stride = max(1, round(PULSE_STEP_S / step))
    return Plot(
        name=f"pulse_q{round(charge_c * 1e18)}",
        title=f"Response to {charge_c * 1e15:g} fC, from the injection",
        x_label="Time from the injection (s)",
        y_label="Output excursion (V)",
        x=[float(value) for value in pulse.time_s[::stride]],
        series={"output excursion": [float(value) for value in pulse.pulse_v[rows[0]][::stride]]},
    )


# not in the reference texts: the output's excursion from its baseline after a charge injection
# (detector read-out), one figure a charge
@plot
def plot_pulse_q250(pulse: AnalysisPulse) -> Plot:
    """The response to the smallest charge, 0.25 fC."""
    return _pulse(pulse, CHARGES_C[0])


# not in the reference texts: as plot_pulse_q250, at 0.5 fC
@plot
def plot_pulse_q500(pulse: AnalysisPulse) -> Plot:
    """The response to 0.5 fC."""
    return _pulse(pulse, CHARGES_C[1])


# not in the reference texts: as plot_pulse_q250, at 1 fC
@plot
def plot_pulse_q1000(pulse: AnalysisPulse) -> Plot:
    """The response to 1 fC."""
    return _pulse(pulse, CHARGES_C[2])


# not in the reference texts: as plot_pulse_q250, at the largest charge, 2 fC
@plot
def plot_pulse_q2000(pulse: AnalysisPulse) -> Plot:
    """The response to the largest charge, 2 fC."""
    return _pulse(pulse, CHARGES_C[3])


# [Razavi-Analog] Fig. 14.4, p. 578: the input/output characteristic over the input's range, the
# input on x; here the injected charge and the pulse's amplitude
@plot
def plot_amplitude_charge(pulse: AnalysisPulse) -> Plot:
    """The response's amplitude over the injected charge."""
    return Plot(
        name="amplitude_charge",
        title="Amplitude over the injected charge",
        x_label="Injected charge (C)",
        y_label="Amplitude (V)",
        x=[float(value) for value in pulse.charge_c],
        series={"amplitude": [float(value) for value in pulse.amplitude_v]},
        x_log=True,
        y_log=True,
    )


# not in the reference texts: the charge gain, the amplitude over the injected charge (detector
# read-out), over the charge
@plot
def plot_gain_charge(pulse: AnalysisPulse) -> Plot:
    """The charge gain over the injected charge."""
    return Plot(
        name="gain_charge",
        title="Charge gain over the injected charge",
        x_label="Injected charge (C)",
        y_label="Charge gain (V/C)",
        x=[float(value) for value in pulse.charge_c],
        series={"charge gain": [float(value) for value in pulse.charge_gain_v_per_c]},
        x_log=True,
    )


# not in the reference texts: the time over threshold (detector read-out) over the charge, the
# threshold half the smallest charge's amplitude
@plot
def plot_tot_charge(pulse: AnalysisPulse) -> Plot:
    """The time over threshold (half the smallest charge's amplitude) over the injected charge."""
    return Plot(
        name="tot_charge",
        title="Time over threshold (half the smallest charge's amplitude) over the charge",
        x_label="Injected charge (C)",
        y_label="Time over threshold (s)",
        x=[float(value) for value in pulse.charge_c],
        series={"time over threshold": [float(value) for value in pulse.tot_s]},
        x_log=True,
    )


# [Razavi-Analog] Fig. 7.26, p. 234: a noise spectrum over log f; Sec. 7.1.1, pp. 221-223: the
# density's square root in V/sqrt(Hz)
@plot
def plot_noise_density(noise: AnalysisNoise) -> Plot:
    """The output noise density without charge, over frequency."""
    return Plot(
        name="noise_density",
        title="Output noise density without charge",
        x_label="Frequency (Hz)",
        y_label="Output noise (V/sqrt(Hz))",
        x=[float(value) for value in noise.frequency_hz],
        series={"output noise": [float(value) for value in noise.noise_out_v_per_rthz[0]]},
        x_log=True,
        y_log=True,
    )


# not in the reference texts: the charge gain (detector read-out) over the supply V_DD
@plot
def plot_gain_supply(supply: AnalysisSupply) -> Plot:
    """The smallest charge's gain over the supply."""
    return Plot(
        name="gain_supply",
        title="Charge gain over the supply (0.25 fC)",
        x_label="Supply (V)",
        y_label="Charge gain (V/C)",
        x=[float(value) for value in supply.vdd_v],
        series={"charge gain": [float(value) for value in supply.charge_gain_v_per_c]},
    )


# not in the reference texts: the peaking time (detector read-out) over the supply V_DD
@plot
def plot_peaking_supply(supply: AnalysisSupply) -> Plot:
    """The smallest charge's peaking time over the supply."""
    return Plot(
        name="peaking_supply",
        title="Peaking time over the supply (0.25 fC)",
        x_label="Supply (V)",
        y_label="Peaking time (s)",
        x=[float(value) for value in supply.vdd_v],
        series={"peaking time": [float(value) for value in supply.peaking_time_s]},
    )


# not in the reference texts: the equivalent noise charge (detector read-out) over the supply V_DD
@plot
def plot_enc_supply(supply: AnalysisSupply) -> Plot:
    """The equivalent noise charge over the supply."""
    return Plot(
        name="enc_supply",
        title="Equivalent noise charge over the supply (unshaped, 0.25 fC gain)",
        x_label="Supply (V)",
        y_label="ENC (electrons)",
        x=[float(value) for value in supply.vdd_v],
        series={"ENC": [float(value) for value in supply.enc_electrons]},
    )


# [Razavi-PLL] Sec. 3.3.3, p. 74: power, the supply current times V_DD; over the supply
@plot
def plot_power_supply(supply: AnalysisSupply) -> Plot:
    """The power the supply delivers before the charge, over the supply."""
    return Plot(
        name="power_supply",
        title="Power over the supply",
        x_label="Supply (V)",
        y_label="Power (W)",
        x=[float(value) for value in supply.vdd_v],
        series={"power": [float(value) for value in supply.power_w]},
    )
