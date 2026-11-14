"""The delay line and ring oscillator's figures as ``Plot`` specs (``flow.pipeline.Plot``), each
from analysis results alone: a characterization's condition sweeps, over the supply (at the nominal
control) and over the control voltage (at the PDK's supply). The viewer draws a record's from its
JSON, ``flow.plot.render`` any with matplotlib (the CLI's figures step)."""

from __future__ import annotations

from flow.pipeline import Plot, plot

from .params import SUPPLY_SWEEP
from .types import AnalysisOscillation, AnalysisPropagation


@plot
def plot_oscillation_frequency_supply(oscillation: AnalysisOscillation) -> Plot:
    """A ring's frequency over the supply (``SUPPLY_SWEEP``)."""
    return Plot(
        name="oscillation_frequency_supply",
        title="Ring frequency over the supply (control 8/12 of the core supply)",
        x_label="Supply over nominal",
        y_label="Oscillation frequency (Hz)",
        x=list(SUPPLY_SWEEP),
        series={"oscillation frequency": [float(value) for value in oscillation.oscillation_frequency_hz]},
    )


@plot
def plot_delay_rise_supply(propagation: AnalysisPropagation) -> Plot:
    """A delay line's delay to its rising output over the supply (``SUPPLY_SWEEP``)."""
    return Plot(
        name="delay_rise_supply",
        title="Line delay to the rising output over the supply (control 8/12 of the core supply)",
        x_label="Supply over nominal",
        y_label="Delay (s)",
        x=list(SUPPLY_SWEEP),
        series={"delay": [float(value) for value in propagation.delay_rise_s]},
    )


@plot
def plot_delay_fall_supply(propagation: AnalysisPropagation) -> Plot:
    """A delay line's delay to its falling output over the supply (``SUPPLY_SWEEP``)."""
    return Plot(
        name="delay_fall_supply",
        title="Line delay to the falling output over the supply (control 8/12 of the core supply)",
        x_label="Supply over nominal",
        y_label="Delay (s)",
        x=list(SUPPLY_SWEEP),
        series={"delay": [float(value) for value in propagation.delay_fall_s]},
    )


@plot
def plot_stage_delay_supply(chain: AnalysisOscillation | AnalysisPropagation) -> Plot:
    """The delay per stage over the supply (``SUPPLY_SWEEP``), a ring's or a delay line's."""
    return Plot(
        name="stage_delay_supply",
        title="Delay per stage over the supply",
        x_label="Supply over nominal",
        y_label="Stage delay (s)",
        x=list(SUPPLY_SWEEP),
        series={"stage delay": [float(value) for value in chain.stage_delay_s]},
    )


@plot
def plot_energy_supply(chain: AnalysisOscillation | AnalysisPropagation) -> Plot:
    """The energy per cycle over the supply (``SUPPLY_SWEEP``): a ring's own cycle, a delay line's
    input clock's."""
    ring = isinstance(chain, AnalysisOscillation)
    return Plot(
        name="energy_supply",
        title="Energy per cycle over the supply" if ring else "Energy per input cycle over the supply",
        x_label="Supply over nominal",
        y_label="Energy per cycle (J)",
        x=list(SUPPLY_SWEEP),
        series={"energy per cycle": [float(value) for value in chain.energy_per_cycle_j]},
    )


@plot
def plot_oscillation_frequency_control(oscillation: AnalysisOscillation) -> Plot:
    """A ring's frequency over the control voltage."""
    return Plot(
        name="oscillation_frequency_control",
        title="Ring frequency over the control (core supply)",
        x_label="Control voltage (V)",
        y_label="Oscillation frequency (Hz)",
        x=[float(value) for value in oscillation.vcont_v],
        series={"oscillation frequency": [float(value) for value in oscillation.oscillation_frequency_hz]},
    )


@plot
def plot_kvco_control(oscillation: AnalysisOscillation) -> Plot:
    """A ring's gain, its frequency's slope, over the control voltage."""
    return Plot(
        name="kvco_control",
        title="Ring gain over the control (core supply)",
        x_label="Control voltage (V)",
        y_label="VCO gain (Hz/V)",
        x=[float(value) for value in oscillation.vcont_v],
        series={"vco gain": [float(value) for value in oscillation.kvco_hz_per_v]},
    )


@plot
def plot_delay_rise_control(propagation: AnalysisPropagation) -> Plot:
    """A delay line's delay to its rising output over the control voltage."""
    return Plot(
        name="delay_rise_control",
        title="Line delay to the rising output over the control (core supply)",
        x_label="Control voltage (V)",
        y_label="Delay (s)",
        x=[float(value) for value in propagation.vcont_v],
        series={"delay": [float(value) for value in propagation.delay_rise_s]},
        y_log=True,
    )


@plot
def plot_delay_fall_control(propagation: AnalysisPropagation) -> Plot:
    """A delay line's delay to its falling output over the control voltage."""
    return Plot(
        name="delay_fall_control",
        title="Line delay to the falling output over the control (core supply)",
        x_label="Control voltage (V)",
        y_label="Delay (s)",
        x=[float(value) for value in propagation.vcont_v],
        series={"delay": [float(value) for value in propagation.delay_fall_s]},
        y_log=True,
    )


@plot
def plot_rise_time_control(propagation: AnalysisPropagation) -> Plot:
    """A delay line's output rise time (10 to 90 %) over the control voltage."""
    return Plot(
        name="rise_time_control",
        title="Line output rise time over the control (core supply)",
        x_label="Control voltage (V)",
        y_label="Rise time (s)",
        x=[float(value) for value in propagation.vcont_v],
        series={"rise time": [float(value) for value in propagation.rise_time_s]},
    )


@plot
def plot_fall_time_control(propagation: AnalysisPropagation) -> Plot:
    """A delay line's output fall time (90 to 10 %) over the control voltage."""
    return Plot(
        name="fall_time_control",
        title="Line output fall time over the control (core supply)",
        x_label="Control voltage (V)",
        y_label="Fall time (s)",
        x=[float(value) for value in propagation.vcont_v],
        series={"fall time": [float(value) for value in propagation.fall_time_s]},
    )


@plot
def plot_energy_control(chain: AnalysisOscillation | AnalysisPropagation) -> Plot:
    """The energy per cycle over the control voltage: a ring's own cycle, a delay line's input
    clock's."""
    return Plot(
        name="energy_control",
        title="Energy per cycle over the control (core supply)",
        x_label="Control voltage (V)",
        y_label="Energy per cycle (J)",
        x=[float(value) for value in chain.vcont_v],
        series={"energy per cycle": [float(value) for value in chain.energy_per_cycle_j]},
    )
