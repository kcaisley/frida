"""The CDAC's figures as ``Plot`` specs (``flow.pipeline.Plot``), each from analysis results alone:
a characterization's settling and the behavioral model's step by stage (the record's plots, which
``flow.cdac.model`` reads back). The viewer draws them from their JSON, ``flow.plot.render`` with
matplotlib."""

from __future__ import annotations

from flow.pipeline import Plot, plot

from .types import AnalysisSettling


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
