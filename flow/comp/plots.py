"""The comparator's figures as ``Plot`` specs (``flow.pipeline.Plot``), each from analysis results
alone: a characterization's condition sweeps (the record's plots) and the lab captures' S-curves,
offset and noise. The viewer draws a record's from its JSON, ``flow.plot.render`` any with
matplotlib (``python -m flow plot comp``)."""

from __future__ import annotations

import math
from collections.abc import Sequence

import numpy as np
from scipy.special import ndtr

from flow.pipeline import Plot

from .params import SUPPLY_SWEEP
from .types import (
    AnalysisCommonMode,
    AnalysisDelay,
    AnalysisMetastability,
    AnalysisOffsetNoise,
    AnalysisPower,
    AnalysisSamplingNoise,
    AnalysisScurve,
)


def plot_metastability(metastability: AnalysisMetastability) -> Plot:
    """The delay over the input near metastability."""
    return Plot(
        name="metastability",
        title="Delay over the input (nominal common mode)",
        x_label="Differential input (V)",
        y_label="Clock-to-decision delay (s)",
        x=[float(value) for value in metastability.input_v],
        series={"delay": [float(value) for value in metastability.delay_s]},
        x_log=True,
    )


def plot_noise_cm(offsets: Sequence[AnalysisOffsetNoise]) -> Plot:
    """The input-referred noise over the common mode (NaN where an S-curve gave no valid fit)."""
    return Plot(
        name="noise_cm",
        title="Input-referred noise over the common mode",
        x_label="Input common mode (V)",
        y_label="Input-referred noise (V)",
        x=[fit.vin_cm_v for fit in offsets],
        series={"noise": [fit.noise_sigma_v if fit.validity == "valid" else math.nan for fit in offsets]},
    )


def plot_offset_cm(offsets: Sequence[AnalysisOffsetNoise]) -> Plot:
    """The systematic offset over the common mode (no mismatch is simulated)."""
    return Plot(
        name="offset_cm",
        title="Offset over the common mode (no mismatch: systematic)",
        x_label="Input common mode (V)",
        y_label="Offset (V)",
        x=[fit.vin_cm_v for fit in offsets],
        series={"offset": [fit.offset_v if fit.validity == "valid" else math.nan for fit in offsets]},
    )


def plot_delay_supply_small(delays: Sequence[AnalysisDelay]) -> Plot:
    """The delay at the small input over the supply (``SUPPLY_SWEEP``)."""
    return Plot(
        name="delay_supply_0p5mv",
        title="Delay at 0.5 mV over the supply",
        x_label="Supply over nominal",
        y_label="Clock-to-decision delay (s)",
        x=list(SUPPLY_SWEEP),
        series={"delay": [float(delay.delay_s[0, 0]) for delay in delays]},
    )


def plot_delay_supply_large(delays: Sequence[AnalysisDelay]) -> Plot:
    """The delay at the large input over the supply (``SUPPLY_SWEEP``)."""
    return Plot(
        name="delay_supply_100mv",
        title="Delay at 100 mV over the supply",
        x_label="Supply over nominal",
        y_label="Clock-to-decision delay (s)",
        x=list(SUPPLY_SWEEP),
        series={"delay": [float(delay.delay_s[0, -1]) for delay in delays]},
    )


def plot_energy_supply(power: AnalysisPower) -> Plot:
    """The energy per decision over the supply (``SUPPLY_SWEEP``, one run each)."""
    return Plot(
        name="energy_supply",
        title="Energy per decision over the supply",
        x_label="Supply over nominal",
        y_label="Energy per decision (J)",
        x=list(SUPPLY_SWEEP),
        series={"energy": [float(value) for value in power.energy_per_decision_j]},
    )


def plot_scurve(scurve: AnalysisScurve) -> Plot:
    """P(high) of the resolved decisions at each input of the nominal S-curve."""
    return Plot(
        name="scurve",
        title="Decision probability (nominal common mode, transient noise)",
        x_label="Differential input (V)",
        y_label="P(high) of the resolved decisions",
        x=[float(value) for value in scurve.vin_diff_v],
        series={"P(high)": [float(value) for value in scurve.probability]},
    )


def plot_scurve_unresolved(scurve: AnalysisScurve) -> Plot:
    """The fraction of the nominal S-curve's decisions unresolved at each input."""
    return Plot(
        name="scurve_unresolved",
        title="Unresolved decisions (nominal common mode, transient noise)",
        x_label="Differential input (V)",
        y_label="Fraction unresolved",
        x=[float(value) for value in scurve.vin_diff_v],
        series={"unresolved": [float(value) for value in scurve.unresolved_fraction]},
    )


def plot_offset_noise(offset: AnalysisOffsetNoise) -> Plot:
    """One common mode's S-curve: the measured probability and, where valid, the fitted Gaussian."""
    x = offset.vin_diff_v
    series = {"measured": [float(value) for value in offset.decision_probability]}
    if offset.validity == "valid":
        fitted = ndtr(offset.decision_polarity * (x - offset.offset_v) / offset.noise_sigma_v)
        series["fit"] = [float(value) for value in fitted]
    return Plot(
        name="offset_noise",
        title=f"S-curve at {offset.vin_cm_v:.3g} V: offset {offset.offset_v * 1e3:.3g} mV, "
        f"noise {offset.noise_sigma_v * 1e3:.3g} mV ({offset.validity})",
        x_label="Differential input (mV)",
        y_label="Decision probability",
        x=[float(value) * 1e3 for value in x],
        series=series,
    )


def plot_common_mode_scurves(common_mode: AnalysisCommonMode) -> Plot:
    """Each common mode's S-curve over the inputs of every curve (NaN where a curve has no point)."""
    x = np.unique(common_mode.vin_diff_v[np.isfinite(common_mode.vin_diff_v)])
    return Plot(
        name="common_mode_scurves",
        title="S-curves over the common mode",
        x_label="Differential input (mV)",
        y_label="Decision probability",
        x=[float(value) * 1e3 for value in x],
        series={
            f"{cm:.3g} V ({validity})": [
                float(probability[inputs == value][0]) if np.any(inputs == value) else math.nan for value in x
            ]
            for cm, validity, inputs, probability in zip(
                common_mode.vin_cm_v,
                common_mode.validity,
                common_mode.vin_diff_v,
                common_mode.decision_probability,
                strict=True,
            )
        },
        legend_title="Common mode",
    )


def plot_common_mode(common_mode: AnalysisCommonMode) -> Plot:
    """The offset and the noise over the common mode (NaN where a curve gave no valid fit)."""
    valid = np.asarray(common_mode.validity) == "valid"
    return Plot(
        name="common_mode",
        title="Offset and input-referred noise over the common mode",
        x_label="Input common mode (V)",
        y_label="Offset, noise (mV)",
        x=[float(value) for value in common_mode.vin_cm_v],
        series={
            "offset": [
                float(value) * 1e3 if ok else math.nan for value, ok in zip(common_mode.offset_v, valid, strict=True)
            ],
            "noise": [
                float(value) * 1e3 if ok else math.nan
                for value, ok in zip(common_mode.noise_sigma_v, valid, strict=True)
            ],
        },
    )


def plot_sampling_noise_scurves(sampling: AnalysisSamplingNoise) -> Plot:
    """Each curve's S-curve, by coupling (P/N % of VDD_DAC) and sampling mode."""
    x = np.unique(sampling.vin_diff_v[np.isfinite(sampling.vin_diff_v)])
    return Plot(
        name="sampling_noise_scurves",
        title="S-curves over the DAC's coupling",
        x_label="Differential input (mV)",
        y_label="Decision probability",
        x=[float(value) * 1e3 for value in x],
        series={
            f"{coupling:g}/{100 - coupling:g} % {mode}": [
                float(probability[inputs == value][0]) if np.any(inputs == value) else math.nan for value in x
            ]
            for coupling, mode, inputs, probability in zip(
                sampling.coupling_percent,
                sampling.sampling_mode,
                sampling.vin_diff_v,
                sampling.decision_probability,
                strict=True,
            )
        },
        legend_title="Coupling P/N, mode",
    )


def plot_sampling_noise(sampling: AnalysisSamplingNoise) -> Plot:
    """Offset and noise over the coupling, one curve each per sampling mode (NaN where invalid)."""
    couplings = np.unique(sampling.coupling_percent)
    series = {}
    for mode in sorted(set(sampling.sampling_mode)):
        for quantity, values in (("offset", sampling.offset_v), ("noise", sampling.noise_sigma_v)):
            series[f"{mode} {quantity}"] = [
                next(
                    (
                        float(value) * 1e3 if validity == "valid" else math.nan
                        for value, coupling_at, mode_at, validity in zip(
                            values, sampling.coupling_percent, sampling.sampling_mode, sampling.validity, strict=True
                        )
                        if coupling_at == coupling and mode_at == mode
                    ),
                    math.nan,
                )
                for coupling in couplings
            ]
    return Plot(
        name="sampling_noise",
        title="Offset and input-referred noise over the DAC's coupling",
        x_label="P-side coupling (% of VDD_DAC)",
        y_label="Offset, noise (mV)",
        x=[float(value) for value in couplings],
        series=series,
    )
