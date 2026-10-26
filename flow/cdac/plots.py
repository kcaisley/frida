"""The CDAC's figures as ``Plot`` specs (``flow.pipeline.Plot``), each from analysis results alone:
a characterization's settling and the behavioral model's step by stage (the record's plots, which
``flow.cdac.model`` reads back), and the plates' Monte Carlo: the 95th percentile of the converter's
INL, of what no calibration recovers and of the DAC's INL over Pelgrom's coefficient, of the
converter's INL over the gradient, and the DAC's INL and DNL by code at the middle condition. The
viewer draws them from their JSON, ``flow.plot.render`` with matplotlib."""

from __future__ import annotations

from collections.abc import Sequence

from flow.pipeline import Plot, plot

from .types import AnalysisMismatch, AnalysisSettling


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
    Pelgrom's coefficient at the middle gradient."""
    gradients = sorted({result.gradient_per_um for result in mismatch})
    chosen = sorted(
        (r for r in mismatch if r.gradient_per_um == gradients[len(gradients) // 2]), key=lambda r: r.pelgrom
    )
    return Plot(
        name="mismatch_inl",
        title="Worst INL with the design weights (95th percentile) over Pelgrom's coefficient, middle gradient",
        x_label="Pelgrom coefficient (%·sqrt(fF))",
        y_label="Max |INL| (LSB)",
        x=[r.pelgrom * 100 for r in chosen],
        series={"95th percentile": [r.inl_p95_lsb for r in chosen]},
    )


@plot
def plot_mismatch_gap(mismatch: Sequence[AnalysisMismatch]) -> Plot:
    """What no calibration recovers, 95th percentile over the runs, over Pelgrom's coefficient at
    the middle gradient."""
    gradients = sorted({result.gradient_per_um for result in mismatch})
    chosen = sorted(
        (r for r in mismatch if r.gradient_per_um == gradients[len(gradients) // 2]), key=lambda r: r.pelgrom
    )
    return Plot(
        name="mismatch_gap",
        title="Unrecoverable code width after ideal calibration (95th percentile), middle gradient",
        x_label="Pelgrom coefficient (%·sqrt(fF))",
        y_label="Widest code less one (LSB)",
        x=[r.pelgrom * 100 for r in chosen],
        series={"95th percentile": [r.gap_p95_lsb for r in chosen]},
    )


@plot
def plot_mismatch_dac_inl(mismatch: Sequence[AnalysisMismatch]) -> Plot:
    """The DAC's worst INL (the worse side), 95th percentile over the runs, over Pelgrom's
    coefficient at the middle gradient."""
    gradients = sorted({result.gradient_per_um for result in mismatch})
    chosen = sorted(
        (r for r in mismatch if r.gradient_per_um == gradients[len(gradients) // 2]), key=lambda r: r.pelgrom
    )
    return Plot(
        name="mismatch_dac_inl",
        title="DAC's worst INL (95th percentile) over Pelgrom's coefficient, middle gradient",
        x_label="Pelgrom coefficient (%·sqrt(fF))",
        y_label="Max |INL| (DAC LSB)",
        x=[r.pelgrom * 100 for r in chosen],
        series={"95th percentile": [r.dac_inl_p95_lsb for r in chosen]},
    )


@plot
def plot_mismatch_gradient(mismatch: Sequence[AnalysisMismatch]) -> Plot:
    """The converter's worst INL with its design weights, 95th percentile over the runs, over the
    gradient at the middle Pelgrom coefficient."""
    pelgroms = sorted({result.pelgrom for result in mismatch})
    chosen = sorted((r for r in mismatch if r.pelgrom == pelgroms[len(pelgroms) // 2]), key=lambda r: r.gradient_per_um)
    return Plot(
        name="mismatch_gradient",
        title="Worst INL with the design weights (95th percentile) over the gradient, middle Pelgrom coefficient",
        x_label="Process gradient (ppm/mm)",
        y_label="Max |INL| (LSB)",
        x=[r.gradient_per_um * 1e9 for r in chosen],
        series={"95th percentile": [r.inl_p95_lsb for r in chosen]},
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
