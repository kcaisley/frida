"""The sampler's figures as ``Plot`` specs (``flow.pipeline.Plot``), each from analysis results alone:
a characterization's condition sweeps, over the input level and over the supply (the record's
plots). The viewer draws a record's from its JSON, ``flow.plot.render`` any with matplotlib
(the CLI's figures step)."""

from __future__ import annotations

import numpy as np

from flow.pipeline import Plot, plot

from .types import AnalysisBoost, AnalysisHold, AnalysisTrack


def _over_nominal(vdd_v: np.ndarray) -> list[float]:
    """Each run's supply over the nominal one: the supply sweep lies symmetric about its nominal
    (``params.SUPPLY_SWEEP``), so the nominal is the middle of its extremes."""
    # not in the reference texts: V_DD,nominal = (min V_DD + max V_DD) / 2 of the supply runs
    # Terms: the supplies ``vdd_v`` of the supply runs (flow.samp.runs.results).
    # Holds for: a sweep symmetric about the nominal supply (90, 100 and 110 % of it).
    nominal = (float(np.min(vdd_v)) + float(np.max(vdd_v))) / 2
    return [float(value) / nominal for value in vdd_v]


@plot
def plot_ron_vin(track: AnalysisTrack) -> Plot:
    """The on-resistance into the load over the input level."""
    # [Razavi-Analog] Eq. (13.22), p. 547: R_on over the input level
    return Plot(
        name="ron_vin",
        title="On-resistance into the load over the input level",
        x_label="Input level (V)",
        y_label="On-resistance (ohm)",
        x=[float(value) for value in track.vin_v],
        series={"on-resistance": [float(value) for value in track.ron_ohm]},
        y_log=True,
    )


@plot
def plot_track_error_vin(track: AnalysisTrack) -> Plot:
    """What is left of the step at the end of tracking, over the input level."""
    # [Razavi-ADC] Sec. 3.9.1, p. 53: the error |V_in - V_out| left when acquisition ends
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
    # [Razavi-Analog] Eq. (13.26), p. 550: the pedestal the opening switch leaves on C_H
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
    # [Pelgrom] Sec. 8.2.3, p. 387: hold-mode feedthrough, in dB: 20 log10 |Delta V_out / Delta V_in|
    # Terms: the ratio ``hold.feedthrough`` at each level (flow.samp.analysis.analyze_hold).
    # Holds for: a feedthrough above the simulator's resolution.
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
    """The on-resistance over the supply, at the nominal input."""
    # [Razavi-Analog] Eq. (2.11), p. 15: R_on falls as the gate's overdrive grows with the supply
    return Plot(
        name="ron_supply",
        title="On-resistance over the supply (nominal input)",
        x_label="Supply over nominal",
        y_label="On-resistance (ohm)",
        x=_over_nominal(supply.vdd_v),
        series={"on-resistance": [float(value) for value in supply.ron_ohm]},
        y_log=True,
    )


@plot
def plot_pedestal_supply(supply: AnalysisHold) -> Plot:
    """The pedestal over the supply, at the nominal input."""
    # [Razavi-Analog] Eq. (13.26), p. 550: the pedestal the opening switch leaves on C_H
    return Plot(
        name="pedestal_supply",
        title="Pedestal over the supply (nominal input)",
        x_label="Supply over nominal",
        y_label="Pedestal (V)",
        x=_over_nominal(supply.vdd_v),
        series={"pedestal": [float(value) for value in supply.pedestal_v]},
    )


@plot
def plot_vgs_vin(boost: AnalysisBoost) -> Plot:
    """A bootstrapped switch's V_GS while tracking, over the input level."""
    # [Razavi-ADC] Eq. (3.72), p. 50: V_P - V_in, the boosted V_GS, over V_in
    return Plot(
        name="vgs_vin",
        title="Boosted gate-source voltage while tracking, over the input level",
        x_label="Input level (V)",
        y_label="Gate-source voltage (V)",
        x=[float(value) for value in boost.vin_v],
        series={"gate-source voltage": [float(value) for value in boost.vgs_v]},
    )
