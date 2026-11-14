"""The amplifier's figures as ``Plot`` specs (``flow.pipeline.Plot``), each from analysis results
alone, each marking the values the analysis read on it: the open-loop response, rejections and
noise over frequency at one point (a result's first), the condition sweeps over the input common
mode (its range shaded) and over the supply, and a single-ended amplifier's unity-gain step
response and output spectrum (a record's plots). The viewer draws a record's from its JSON,
``flow.plot.render`` any with matplotlib (the CLI's figures step)."""

from __future__ import annotations

import math

import numpy as np

from flow.pipeline import Band, Marker, Plot, plot

from .params import SPECTRUM_FLOOR_DB, SPECTRUM_HARMONICS
from .types import AnalysisAc, AnalysisDistortion, AnalysisNoise, AnalysisRange, AnalysisSlew


def _values(array: np.ndarray) -> list[float]:
    """An array as a spec's list of floats."""
    return [float(value) for value in array]


def _condition(vin_cm_v: float, vdd_v: float) -> str:
    """A point's condition for a title: its input common mode and supply."""
    return f"input common mode {vin_cm_v:.3g} V, supply {vdd_v:.3g} V"


def _hz(frequency_hz: float) -> str:
    """A frequency for a title in engineering notation: three significant digits under an SI
    prefix from none to tera (``1 MHz``, ``12.6 kHz``)."""
    rounded = float(f"{frequency_hz:.3g}")
    step = min(max(math.floor(math.log10(abs(rounded)) / 3), 0), 4) if rounded else 0
    return f"{rounded / 1000**step:.3g} {('', 'k', 'M', 'G', 'T')[step]}Hz"


def _markers(points: dict[str, float]) -> list[Marker]:
    """Labelled markers at the finite values only."""
    return [Marker(value, label) for label, value in points.items() if math.isfinite(value)]


def _span(span: AnalysisRange) -> list[Band]:
    """The input common-mode range as a shaded band, where there is one."""
    if not (math.isfinite(span.vin_cm_min_v) and math.isfinite(span.vin_cm_max_v)):
        return []
    return [Band(span.vin_cm_min_v, span.vin_cm_max_v, "input common-mode range")]


# [Razavi-Analog] Fig. 6.43, p. 204: gain over frequency, the -3 dB and unity-gain bandwidths marked
@plot
def plot_gain(ac: AnalysisAc) -> Plot:
    """The open-loop differential gain over frequency at the result's first point, its -3 dB and
    unity-gain bandwidths marked."""
    return Plot(
        name="gain",
        title=f"Gain over frequency ({_condition(ac.vin_cm_v[0], ac.vdd_v[0])})",
        x_label="Frequency (Hz)",
        y_label="Gain (dB)",
        x=_values(ac.frequency_hz),
        series={"gain": _values(ac.gain_db[0])},
        x_log=True,
        x_markers=_markers(
            {"-3 dB bandwidth": float(ac.bandwidth_hz[0]), "unity-gain bandwidth": float(ac.unity_gain_bandwidth_hz[0])}
        ),
    )


# [Razavi-Analog] Sec. 10.3, Fig. 10.10, p. 417: phase margin, 180 deg plus the phase at the gain crossover
@plot
def plot_phase(ac: AnalysisAc) -> Plot:
    """The open-loop response's phase over frequency at the result's first point, its polarity
    taken off as the margins read it: -180 deg and the unity-gain bandwidth marked, the phase
    margin the phase there less -180 deg."""
    margin = float(ac.phase_margin_deg[0])
    return Plot(
        name="phase",
        title=f"Phase over frequency ({_condition(ac.vin_cm_v[0], ac.vdd_v[0])})",
        x_label="Frequency (Hz)",
        y_label="Phase (deg)",
        x=_values(ac.frequency_hz),
        series={"phase": _values(ac.phase_deg[0])},
        x_log=True,
        x_markers=_markers({f"phase margin {margin:.3g} deg": float(ac.unity_gain_bandwidth_hz[0])}),
        y_markers=[Marker(-180.0, "-180 deg")],
    )


# [Razavi-Analog] Sec. 9.11, p. 400: power supply rejection ratio
@plot
def plot_psrr(ac: AnalysisAc) -> Plot:
    """A single-ended output's supply rejection over frequency at the result's first point."""
    return Plot(
        name="psrr",
        title=f"Supply rejection at outp ({_condition(ac.vin_cm_v[0], ac.vdd_v[0])})",
        x_label="Frequency (Hz)",
        y_label="PSRR (dB)",
        x=_values(ac.frequency_hz),
        series={"PSRR": _values(ac.psrr_db[0])},
        x_log=True,
    )


# [Razavi-Analog] Eq. (5.42), p. 157: common-mode rejection ratio of a single output
@plot
def plot_cmrr(ac: AnalysisAc) -> Plot:
    """A single-ended output's common-mode rejection over frequency at the result's first point."""
    return Plot(
        name="cmrr",
        title=f"Common-mode rejection at outp ({_condition(ac.vin_cm_v[0], ac.vdd_v[0])})",
        x_label="Frequency (Hz)",
        y_label="CMRR (dB)",
        x=_values(ac.frequency_hz),
        series={"CMRR": _values(ac.cmrr_db[0])},
        x_log=True,
    )


# [Razavi-Analog] Sec. 7.2.2, Fig. 7.27, p. 235: a noise density over frequency
@plot
def plot_noise_density(noise: AnalysisNoise) -> Plot:
    """The input-referred noise density over frequency at the result's first point, its spot
    frequency marked."""
    return Plot(
        name="noise_density",
        title=f"Input-referred noise density ({_condition(noise.vin_cm_v[0], noise.vdd_v[0])})",
        x_label="Frequency (Hz)",
        y_label="Input-referred noise (V/sqrt(Hz))",
        x=_values(noise.frequency_hz),
        series={"input-referred noise": _values(noise.noise_in_v_per_rthz[0])},
        x_log=True,
        y_log=True,
        x_markers=_markers({"spot": noise.spot_frequency_hz}),
    )


# [Razavi-Analog] Example 4.2, Fig. 4.10, p. 105: gain over the input common mode
@plot
def plot_gain_cm(ac: AnalysisAc, span: AnalysisRange) -> Plot:
    """The low-frequency gain over the input common mode, its range shaded."""
    return Plot(
        name="gain_cm",
        title=f"Low-frequency gain over the input common mode (supply {ac.vdd_v[0]:.3g} V)",
        x_label="Input common mode (V)",
        y_label="Low-frequency gain (dB)",
        x=_values(ac.vin_cm_v),
        series={"low-frequency gain": _values(ac.gain_dc_db)},
        x_bands=_span(span),
    )


# [Razavi-Analog] Example 2.2, p. 18: V_D,sat, the least V_DS of saturation
# [Razavi-Analog] Eq. (4.1), p. 105: the input common-mode range, the tail and input pair saturated
@plot
def plot_saturation_margin_cm(ac: AnalysisAc, span: AnalysisRange) -> Plot:
    """The tail's and the input pair's least V_DS - V_D,sat over the input common mode, zero and
    the range it bounds marked."""
    return Plot(
        name="saturation_margin_cm",
        title=f"Saturation margin of the tail and input pair (supply {ac.vdd_v[0]:.3g} V)",
        x_label="Input common mode (V)",
        y_label="Drain-source voltage less saturation voltage (V)",
        x=_values(ac.vin_cm_v),
        series={"saturation margin": _values(ac.saturation_margin_pair_v)},
        x_bands=_span(span),
        y_markers=[Marker(0.0, "saturation edge")],
    )


# [Razavi-Analog] Sec. 9.8, p. 389: the transconductance, so the speed, varies with the input common mode
@plot
def plot_unity_gain_bandwidth_cm(ac: AnalysisAc, span: AnalysisRange) -> Plot:
    """The unity-gain bandwidth over the input common mode, its range shaded."""
    return Plot(
        name="unity_gain_bandwidth_cm",
        title=f"Unity-gain bandwidth over the input common mode (supply {ac.vdd_v[0]:.3g} V)",
        x_label="Input common mode (V)",
        y_label="Unity-gain bandwidth (Hz)",
        x=_values(ac.vin_cm_v),
        series={"unity-gain bandwidth": _values(ac.unity_gain_bandwidth_hz)},
        y_log=True,
        x_bands=_span(span),
    )


# [Razavi-Analog] Example 7.11, Eq. (7.45), p. 238: input-referred noise density
# not in the reference texts: its value at the sweep point nearest 1 MHz, over the input common mode
@plot
def plot_noise_in_1mhz_cm(noise: AnalysisNoise, span: AnalysisRange) -> Plot:
    """The input-referred noise density at 1 MHz over the input common mode, its range shaded."""
    return Plot(
        name="noise_in_1mhz_cm",
        title=f"Input-referred noise at {_hz(noise.spot_frequency_hz)} over the input common mode",
        x_label="Input common mode (V)",
        y_label="Input-referred noise (V/sqrt(Hz))",
        x=_values(noise.vin_cm_v),
        series={"input-referred noise": _values(noise.noise_in_1mhz_v_per_rthz)},
        y_log=True,
        x_bands=_span(span),
    )


# [Razavi-Analog] Sec. 7.9, Eq. (7.147), p. 265: total input-referred noise, over the input common mode
@plot
def plot_noise_in_cm(noise: AnalysisNoise, span: AnalysisRange) -> Plot:
    """The output noise integrated over the sweep and referred to the input by the low-frequency
    gain, over the input common mode, its range shaded."""
    return Plot(
        name="noise_in_cm",
        title="Total input-referred noise over the input common mode",
        x_label="Input common mode (V)",
        y_label="Input-referred noise (V)",
        x=_values(noise.vin_cm_v),
        series={"input-referred noise": _values(noise.noise_in_v)},
        x_bands=_span(span),
    )


# not in the reference texts: the low-frequency gain over the 90, 100 and 110 % supplies
@plot
def plot_gain_supply(supply: AnalysisAc) -> Plot:
    """The low-frequency gain over the supply, at each supply's nominal input common mode."""
    return Plot(
        name="gain_supply",
        title="Low-frequency gain over the supply",
        x_label="Supply (V)",
        y_label="Low-frequency gain (dB)",
        x=_values(supply.vdd_v),
        series={"low-frequency gain": _values(supply.gain_dc_db)},
    )


# not in the reference texts: the unity-gain bandwidth over the 90, 100 and 110 % supplies
@plot
def plot_unity_gain_bandwidth_supply(supply: AnalysisAc) -> Plot:
    """The unity-gain bandwidth over the supply, at each supply's nominal input common mode."""
    return Plot(
        name="unity_gain_bandwidth_supply",
        title="Unity-gain bandwidth over the supply",
        x_label="Supply (V)",
        y_label="Unity-gain bandwidth (Hz)",
        x=_values(supply.vdd_v),
        series={"unity-gain bandwidth": _values(supply.unity_gain_bandwidth_hz)},
    )


# [Baker] Sec. 24.1, p. 805: power dissipation, VDD times the amplifier's current
@plot
def plot_power_supply(supply: AnalysisAc) -> Plot:
    """The amplifier's own supply power over the supply (the bias network's left out), at each
    supply's nominal input common mode."""
    return Plot(
        name="power_supply",
        title="Amplifier power over the supply (bias network excluded)",
        x_label="Supply (V)",
        y_label="Power (W)",
        x=_values(supply.vdd_v),
        series={"power": _values(supply.power_w)},
    )


# [Razavi-Analog] Sec. 9.9, Fig. 9.70, p. 391: the step response, slewing and then settling
@plot
def plot_step_response(slew: AnalysisSlew) -> Plot:
    """The unity-gain step response, ``outp`` over time at the result's first point: the 1 %
    band about each level and the instants each edge settles marked."""
    low, high = float(slew.vout_low_v[0]), float(slew.vout_high_v[0])
    band = abs(high - low) / 100
    settled = {
        "rise settled": float(slew.vin_rise_s[0] + slew.settling_rise_s[0]),
        "fall settled": float(slew.vin_fall_s[0] + slew.settling_fall_s[0]),
    }
    levels = [Marker(high + band, "1 % band"), Marker(high - band), Marker(low + band, "1 % band"), Marker(low - band)]
    return Plot(
        name="step_response",
        title=f"Unity-gain step response (input {slew.vin_low_v[0]:.3g} V to {slew.vin_high_v[0]:.3g} V)",
        x_label="Time (s)",
        y_label="Output (V)",
        x=_values(slew.time_s),
        series={"output": _values(slew.vout_v[0])},
        x_markers=_markers(settled),
        y_markers=[level for level in levels if math.isfinite(level.at)],
    )


# [Razavi-ADC] Fig. 4.4, p. 63: an output spectrum on a linear frequency axis down to a floor
@plot
def plot_spectrum(distortion: AnalysisDistortion) -> Plot:
    """The unity-gain output spectrum on the input sine, relative to the input's amplitude, at the
    result's first point: the bins above DC to the seventh harmonic, clipped at a floor, the
    second to seventh harmonics (those THD counts) marked."""
    tone = float(distortion.vin_frequency_hz[0])
    shown = (distortion.frequency_hz > 0) & (distortion.frequency_hz <= (SPECTRUM_HARMONICS + 0.5) * tone)
    return Plot(
        name="spectrum",
        title=f"Unity-gain output spectrum on a {_hz(tone)} sine of {distortion.vin_amplitude_v[0]:.3g} V",
        x_label="Frequency (Hz)",
        y_label="Output over the input amplitude (dB)",
        x=_values(distortion.frequency_hz[shown]),
        series={"output": _values(np.maximum(distortion.spectrum_db[0][shown], SPECTRUM_FLOOR_DB))},
        x_markers=[Marker(order * tone, f"{order} f") for order in range(2, SPECTRUM_HARMONICS + 1)],
    )
