"""The amplifier's figures as ``Plot`` specs (``flow.pipeline.Plot``), each from analysis results
alone: the open-loop response, rejections and noise over frequency at one point (a result's
first), the condition sweeps over the input common mode and over the supply, and a single-ended
amplifier's unity-gain step response and output spectrum (a record's plots). The viewer draws a
record's from its JSON, ``flow.plot.render`` any with matplotlib (the CLI's figures step)."""

from __future__ import annotations

from flow.pipeline import Plot, plot

from .params import SUPPLY_SWEEP
from .types import AnalysisAc, AnalysisDistortion, AnalysisNoise, AnalysisSlew


@plot
def plot_gain(ac: AnalysisAc) -> Plot:
    """The open-loop differential gain over frequency, at the result's first point."""
    return Plot(
        name="gain",
        title="Gain over frequency (mid-supply input)",
        x_label="Frequency (Hz)",
        y_label="Gain (dB)",
        x=[float(value) for value in ac.frequency_hz],
        series={"gain": [float(value) for value in ac.gain_db[0]]},
        x_log=True,
    )


@plot
def plot_phase(ac: AnalysisAc) -> Plot:
    """The open-loop response's phase over frequency, at the result's first point."""
    return Plot(
        name="phase",
        title="Phase over frequency (mid-supply input)",
        x_label="Frequency (Hz)",
        y_label="Phase (deg)",
        x=[float(value) for value in ac.frequency_hz],
        series={"phase": [float(value) for value in ac.phase_deg[0]]},
        x_log=True,
    )


@plot
def plot_psrr(ac: AnalysisAc) -> Plot:
    """The supply rejection at ``outp`` over frequency, at the result's first point."""
    return Plot(
        name="psrr",
        title="Supply rejection at outp (mid-supply input)",
        x_label="Frequency (Hz)",
        y_label="PSRR (dB)",
        x=[float(value) for value in ac.frequency_hz],
        series={"PSRR": [float(value) for value in ac.psrr_db[0]]},
        x_log=True,
    )


@plot
def plot_cmrr(ac: AnalysisAc) -> Plot:
    """The common-mode rejection at ``outp`` over frequency, at the result's first point."""
    return Plot(
        name="cmrr",
        title="Common-mode rejection at outp (mid-supply input)",
        x_label="Frequency (Hz)",
        y_label="CMRR (dB)",
        x=[float(value) for value in ac.frequency_hz],
        series={"CMRR": [float(value) for value in ac.cmrr_db[0]]},
        x_log=True,
    )


@plot
def plot_noise_density(noise: AnalysisNoise) -> Plot:
    """The input-referred noise density over frequency, at the result's first point."""
    return Plot(
        name="noise_density",
        title="Input-referred noise density (mid-supply input)",
        x_label="Frequency (Hz)",
        y_label="Input-referred noise (V/sqrt(Hz))",
        x=[float(value) for value in noise.frequency_hz],
        series={"input-referred noise": [float(value) for value in noise.noise_in_v_per_rthz[0]]},
        x_log=True,
        y_log=True,
    )


@plot
def plot_gain_cm(ac: AnalysisAc) -> Plot:
    """The low-frequency gain over the input common mode."""
    return Plot(
        name="gain_cm",
        title="Low-frequency gain over the input common mode",
        x_label="Input common mode (V)",
        y_label="Low-frequency gain (dB)",
        x=[float(value) for value in ac.vin_cm_v],
        series={"low-frequency gain": [float(value) for value in ac.gain_dc_db]},
    )


@plot
def plot_unity_gain_bandwidth_cm(ac: AnalysisAc) -> Plot:
    """The unity-gain bandwidth over the input common mode."""
    return Plot(
        name="unity_gain_bandwidth_cm",
        title="Unity-gain bandwidth over the input common mode",
        x_label="Input common mode (V)",
        y_label="Unity-gain bandwidth (Hz)",
        x=[float(value) for value in ac.vin_cm_v],
        series={"unity-gain bandwidth": [float(value) for value in ac.unity_gain_bandwidth_hz]},
        y_log=True,
    )


@plot
def plot_noise_in_1mhz_cm(noise: AnalysisNoise) -> Plot:
    """The input-referred noise density at 1 MHz over the input common mode."""
    return Plot(
        name="noise_in_1mhz_cm",
        title="Input-referred noise at 1 MHz over the input common mode",
        x_label="Input common mode (V)",
        y_label="Input-referred noise (V/sqrt(Hz))",
        x=[float(value) for value in noise.vin_cm_v],
        series={"input-referred noise": [float(value) for value in noise.noise_in_1mhz_v_per_rthz]},
        y_log=True,
    )


@plot
def plot_noise_in_cm(noise: AnalysisNoise) -> Plot:
    """The input-referred noise, RMS to the unity-gain bandwidth, over the input common mode."""
    return Plot(
        name="noise_in_cm",
        title="Input-referred noise to the unity-gain bandwidth over the input common mode",
        x_label="Input common mode (V)",
        y_label="Input-referred noise (V)",
        x=[float(value) for value in noise.vin_cm_v],
        series={"input-referred noise": [float(value) for value in noise.noise_in_v]},
    )


@plot
def plot_gain_supply(supply: AnalysisAc) -> Plot:
    """The low-frequency gain over the supply (``SUPPLY_SWEEP``), the common modes at mid-supply."""
    return Plot(
        name="gain_supply",
        title="Low-frequency gain over the supply",
        x_label="Supply over nominal",
        y_label="Low-frequency gain (dB)",
        x=list(SUPPLY_SWEEP),
        series={"low-frequency gain": [float(value) for value in supply.gain_dc_db]},
    )


@plot
def plot_unity_gain_bandwidth_supply(supply: AnalysisAc) -> Plot:
    """The unity-gain bandwidth over the supply (``SUPPLY_SWEEP``), the common modes at mid-supply."""
    return Plot(
        name="unity_gain_bandwidth_supply",
        title="Unity-gain bandwidth over the supply",
        x_label="Supply over nominal",
        y_label="Unity-gain bandwidth (Hz)",
        x=list(SUPPLY_SWEEP),
        series={"unity-gain bandwidth": [float(value) for value in supply.unity_gain_bandwidth_hz]},
        y_log=True,
    )


@plot
def plot_power_supply(supply: AnalysisAc) -> Plot:
    """The supply power over the supply (``SUPPLY_SWEEP``), the common modes at mid-supply."""
    return Plot(
        name="power_supply",
        title="Power over the supply",
        x_label="Supply over nominal",
        y_label="Power (W)",
        x=list(SUPPLY_SWEEP),
        series={"power": [float(value) for value in supply.power_w]},
    )


@plot
def plot_step_response(slew: AnalysisSlew) -> Plot:
    """The unity-gain step response: ``outp`` over time, at the result's first point."""
    return Plot(
        name="step_response",
        title="Unity-gain step response (mid-supply input)",
        x_label="Time (s)",
        y_label="Output (V)",
        x=[float(value) for value in slew.time_s],
        series={"output": [float(value) for value in slew.vout_v[0]]},
    )


@plot
def plot_spectrum(distortion: AnalysisDistortion) -> Plot:
    """The unity-gain output spectrum on the input sine, relative to the input's amplitude, at
    the result's first point (the bins above DC)."""
    return Plot(
        name="spectrum",
        title="Unity-gain output spectrum on the input sine",
        x_label="Frequency (Hz)",
        y_label="Output over the input amplitude (dB)",
        x=[float(value) for value in distortion.frequency_hz[1:]],
        series={"output": [float(value) for value in distortion.spectrum_db[0][1:]]},
        x_log=True,
    )
