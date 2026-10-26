"""The sampler's figures as ``Plot`` specs (``flow.pipeline.Plot``), each from analysis results alone:
a characterization's condition sweeps, over the input level and over the supply (the record's
plots). The viewer draws a record's from its JSON, ``flow.plot.render`` any with matplotlib
(``python -m flow plot samp``)."""

from __future__ import annotations

import numpy as np

from flow.pipeline import Plot, plot

from .params import SUPPLY_SWEEP
from .types import AnalysisHold, AnalysisTrack


@plot
def plot_ron_vin(track: AnalysisTrack) -> Plot:
    """The on-resistance into the load over the input level."""
    return Plot(
        name="ron_vin",
        title="On-resistance into 1 pF over the input level",
        x_label="Input level (V)",
        y_label="On-resistance (ohm)",
        x=[float(value) for value in track.vin_v],
        series={"on-resistance": [float(value) for value in track.on_resistance_ohm]},
        y_log=True,
    )


@plot
def plot_track_error_vin(track: AnalysisTrack) -> Plot:
    """What is left of the step at the end of tracking, over the input level."""
    return Plot(
        name="track_error_vin",
        title="Track error at the end of tracking over the input level",
        x_label="Input level (V)",
        y_label="Output minus input (V)",
        x=[float(value) for value in track.vin_v],
        series={"track error": [float(value) for value in track.track_error_v]},
    )


@plot
def plot_pedestal_vin(hold: AnalysisHold) -> Plot:
    """The pedestal the opening switch leaves, over the input level."""
    return Plot(
        name="pedestal_vin",
        title="Pedestal over the input level",
        x_label="Input level (V)",
        y_label="Pedestal (V)",
        x=[float(value) for value in hold.vin_v],
        series={"pedestal": [float(value) for value in hold.pedestal_v]},
    )


@plot
def plot_feedthrough_vin(hold: AnalysisHold) -> Plot:
    """The input's feedthrough to the held output, in dB, over the input level."""
    return Plot(
        name="feedthrough_vin",
        title="Input feedthrough while holding, over the input level",
        x_label="Input level (V)",
        y_label="Feedthrough (dB)",
        x=[float(value) for value in hold.vin_v],
        series={"feedthrough": [float(value) for value in 20 * np.log10(np.abs(hold.feedthrough))]},
    )


@plot
def plot_ron_supply(supply: AnalysisTrack) -> Plot:
    """The on-resistance over the supply (``SUPPLY_SWEEP``), at mid-supply input."""
    return Plot(
        name="ron_supply",
        title="On-resistance over the supply (mid-supply input)",
        x_label="Supply over nominal",
        y_label="On-resistance (ohm)",
        x=list(SUPPLY_SWEEP),
        series={"on-resistance": [float(value) for value in supply.on_resistance_ohm]},
        y_log=True,
    )


@plot
def plot_pedestal_supply(supply: AnalysisHold) -> Plot:
    """The pedestal over the supply (``SUPPLY_SWEEP``), at mid-supply input."""
    return Plot(
        name="pedestal_supply",
        title="Pedestal over the supply (mid-supply input)",
        x_label="Supply over nominal",
        y_label="Pedestal (V)",
        x=list(SUPPLY_SWEEP),
        series={"pedestal": [float(value) for value in supply.pedestal_v]},
    )
