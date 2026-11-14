"""The charge-sensitive amplifier's figures as ``Plot`` specs (``flow.pipeline.Plot``), each from
analysis results alone: its responses to each charge, its amplitude, gain and time over threshold
over the charge, its output noise density, and its gain, peaking time, ENC and power over the
supply (the record's plots). The viewer draws a record's from its JSON, ``flow.plot.render`` any
with matplotlib (the CLI's figures step)."""

from __future__ import annotations

import numpy as np

from flow.pipeline import Plot, plot

from .params import PULSE_STEP_S, SUPPLY_SWEEP
from .types import AnalysisNoise, AnalysisPulse, AnalysisSupply


def _stride(time_s: np.ndarray) -> int:
    """Every how many samples of a response the figure keeps one: about every ``PULSE_STEP_S``."""
    step = float(np.median(np.diff(time_s))) if len(time_s) > 1 else PULSE_STEP_S
    return max(1, round(PULSE_STEP_S / step))


@plot
def plot_pulse(pulse: AnalysisPulse) -> Plot:
    """Each charge's response: the output's excursion from its baseline, from the injection on."""
    stride = _stride(pulse.time_s)
    return Plot(
        name="pulse",
        title="Response to each charge, from the injection",
        x_label="Time from the injection (s)",
        y_label="Output excursion (V)",
        x=[float(value) for value in pulse.time_s[::stride]],
        series={
            f"{charge * 1e15:g} fC": [float(value) for value in row[::stride]]
            for charge, row in zip(pulse.charge_c, pulse.pulse_v, strict=True)
        },
    )


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


@plot
def plot_gain_supply(supply: AnalysisSupply) -> Plot:
    """The smallest charge's gain over the supply (``SUPPLY_SWEEP``)."""
    return Plot(
        name="gain_supply",
        title="Charge gain over the supply (0.25 fC)",
        x_label="Supply over nominal",
        y_label="Charge gain (V/C)",
        x=list(SUPPLY_SWEEP),
        series={"charge gain": [float(value) for value in supply.charge_gain_v_per_c]},
    )


@plot
def plot_peaking_supply(supply: AnalysisSupply) -> Plot:
    """The smallest charge's peaking time over the supply (``SUPPLY_SWEEP``)."""
    return Plot(
        name="peaking_supply",
        title="Peaking time over the supply (0.25 fC)",
        x_label="Supply over nominal",
        y_label="Peaking time (s)",
        x=list(SUPPLY_SWEEP),
        series={"peaking time": [float(value) for value in supply.peaking_time_s]},
    )


@plot
def plot_enc_supply(supply: AnalysisSupply) -> Plot:
    """The equivalent noise charge over the supply (``SUPPLY_SWEEP``)."""
    return Plot(
        name="enc_supply",
        title="Equivalent noise charge over the supply",
        x_label="Supply over nominal",
        y_label="ENC (electrons)",
        x=list(SUPPLY_SWEEP),
        series={"ENC": [float(value) for value in supply.enc_electrons]},
    )


@plot
def plot_power_supply(supply: AnalysisSupply) -> Plot:
    """The power the supply delivers before the charge, over the supply (``SUPPLY_SWEEP``)."""
    return Plot(
        name="power_supply",
        title="Power over the supply",
        x_label="Supply over nominal",
        y_label="Power (W)",
        x=list(SUPPLY_SWEEP),
        series={"power": [float(value) for value in supply.power_w]},
    )
