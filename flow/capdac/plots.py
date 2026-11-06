"""The capacitive DAC's figures as ``Plot`` specs (``flow.pipeline.Plot``), each from analysis
results alone: a characterization's settling and the behavioral model's step by stage (the record's
plots, which ``flow.capdac.model`` reads back), the plates' Monte Carlo: the 95th percentile of the
converter's INL, of what no calibration recovers and of the DAC's INL over Pelgrom's coefficient,
and the DAC's INL and DNL by code at the middle condition; and the bench's capacitance of each stage
from its switching curves (``analyze_cap_mismatch``), one curve a quantity, so compared converters
overlay as instances. The viewer draws them from their JSON, ``flow.plot.render`` with matplotlib."""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np

from flow.pipeline import Plot, plot

from .types import AnalysisCapMismatch, AnalysisMismatch, AnalysisSettling


@plot
def plot_settling_stage(settling: AnalysisSettling) -> Plot:
    """Each stage's settling to half an LSB, its slower direction's."""
    return Plot(
        name="settling_stage",
        title="Settling to half an LSB by stage (the slower direction)",
        x_label="Stage (C0, the MSB, first)",
        y_label="Settling time (s)",
        x=list(range(len(settling.settling_s))),
        series={"settling": list(map(float, settling.settling_s))},
    )


@plot
def plot_model_stage(settling: AnalysisSettling) -> Plot:
    """Each stage's step as the behavioral model starts and settles it: its driver's delay and its
    time constant."""
    return Plot(
        name="model_stage",
        title="The behavioral model's step by stage: its start and time constant",
        x_label="Stage (C0, the MSB, first)",
        y_label="Time (s)",
        x=list(range(len(settling.settling_s))),
        series={"delay": list(map(float, settling.delay_s)), "time constant": list(map(float, settling.tau_s))},
    )


@plot
def plot_mismatch_inl(mismatch: Sequence[AnalysisMismatch]) -> Plot:
    """The converter's worst INL with its design weights, 95th percentile over the runs, over
    Pelgrom's coefficient."""
    chosen = sorted(mismatch, key=lambda r: r.pelgrom)
    return Plot(
        name="mismatch_inl",
        title="Worst INL with the design weights (95th percentile) over Pelgrom's coefficient",
        x_label="Pelgrom coefficient (%·sqrt(fF))",
        y_label="Max |INL| (LSB)",
        x=[r.pelgrom * 100 for r in chosen],
        series={"95th percentile": [r.inl_p95_lsb for r in chosen]},
    )


@plot
def plot_mismatch_gap(mismatch: Sequence[AnalysisMismatch]) -> Plot:
    """What no calibration recovers, 95th percentile over the runs, over Pelgrom's coefficient."""
    chosen = sorted(mismatch, key=lambda r: r.pelgrom)
    return Plot(
        name="mismatch_gap",
        title="Unrecoverable code width after ideal calibration (95th percentile)",
        x_label="Pelgrom coefficient (%·sqrt(fF))",
        y_label="Widest code less one (LSB)",
        x=[r.pelgrom * 100 for r in chosen],
        series={"95th percentile": [r.gap_p95_lsb for r in chosen]},
    )


@plot
def plot_mismatch_dac_inl(mismatch: Sequence[AnalysisMismatch]) -> Plot:
    """The DAC's worst INL (the worse side), 95th percentile over the runs, over Pelgrom's
    coefficient."""
    chosen = sorted(mismatch, key=lambda r: r.pelgrom)
    return Plot(
        name="mismatch_dac_inl",
        title="DAC's worst INL (95th percentile) over Pelgrom's coefficient",
        x_label="Pelgrom coefficient (%·sqrt(fF))",
        y_label="Max |INL| (DAC LSB)",
        x=[r.pelgrom * 100 for r in chosen],
        series={"95th percentile": [r.dac_inl_p95_lsb for r in chosen]},
    )


@plot
def plot_dac_inl(mismatch: AnalysisMismatch) -> Plot:
    """The DAC's INL by code (each code's worst control word) of the run at the 95th percentile."""
    return Plot(
        name="dac_inl",
        title="DAC INL by code, the 95th-percentile run at the middle condition",
        x_label="Code (the control word by its design weights)",
        y_label="INL (DAC LSB)",
        x=list(range(len(mismatch.dac_inl_curve_lsb))),
        series={"INL": [float(v) for v in mismatch.dac_inl_curve_lsb]},
        x_ticks="code",
    )


@plot
def plot_dac_dnl(mismatch: AnalysisMismatch) -> Plot:
    """The DAC's DNL by code (its words' mean output) of the run at the 95th percentile."""
    return Plot(
        name="dac_dnl",
        title="DAC DNL by code, the 95th-percentile run at the middle condition",
        x_label="Code (the control word by its design weights)",
        y_label="DNL (DAC LSB)",
        x=list(range(len(mismatch.dac_dnl_curve_lsb))),
        series={"DNL": [float(v) for v in mismatch.dac_dnl_curve_lsb]},
        x_ticks="code",
    )


@plot
def plot_fraction_stage(cap_mismatch: AnalysisCapMismatch) -> Plot:
    """Each stage's effective fraction of its side's capacitance, P's and N's mean, from its
    switching curves (``analyze_cap_mismatch``)."""
    return _by_stage(
        "fraction_stage", "Effective fraction by stage (P and N mean)", "Effective fraction", cap_mismatch.fraction
    )


@plot
def plot_fraction_error_stage(cap_mismatch: AnalysisCapMismatch) -> Plot:
    """Each stage's effective fraction (P's and N's mean) less the design's expectation (its weights
    over its total and the top plate's parasitic)."""
    return _by_stage(
        "fraction_error_stage",
        "Effective fraction less the design's by stage",
        "Effective fraction less the design's",
        cap_mismatch.fraction_error,
    )


@plot
def plot_asymmetry_stage(cap_mismatch: AnalysisCapMismatch) -> Plot:
    """Each stage's effective fraction, P's less N's."""
    return _by_stage(
        "asymmetry_stage",
        "Effective fraction, P less N, by stage",
        "P less N effective fraction",
        cap_mismatch.asymmetry,
    )


@plot
def plot_separation_stage(cap_mismatch: AnalysisCapMismatch) -> Plot:
    """Each stage's difference plates, P's and N's together (twice their fraction's mean): how far
    apart its two modes put its weight."""
    return _by_stage(
        "separation_stage",
        "Difference plates by stage (P and N together)",
        "Difference fraction, P plus N",
        cap_mismatch.separation,
    )


@plot
def plot_main_stage(cap_mismatch: AnalysisCapMismatch) -> Plot:
    """Each stage's main plate's fraction, P's and N's mean."""
    return _by_stage("main_stage", "Main plate's fraction by stage (P and N mean)", "Main fraction", cap_mismatch.main)


@plot
def plot_bias_stage(cap_mismatch: AnalysisCapMismatch) -> Plot:
    """Each stage's switching-direction bias as the converter switches it (main and difference
    plates against each other): half its 1-to-0 less its 0-to-1 fraction, P's and N's mean."""
    return _by_stage(
        "bias_stage", "Switching-direction bias by stage (P and N mean)", "Direction bias (fraction)", cap_mismatch.bias
    )


def _by_stage(name: str, title: str, y_label: str, values: np.ndarray) -> Plot:
    """One fraction of each stage (C0, the MSB, first), NaN where its curves gave none."""
    return Plot(
        name=name,
        title=title,
        x_label="Stage (C0, the MSB, first)",
        y_label=y_label,
        x=[float(stage) for stage in range(len(values))],
        series={y_label: [float(value) for value in values]},
        x_ticks="step",
    )
