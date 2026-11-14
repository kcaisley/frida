"""The follower's figures as ``Plot`` specs (``flow.pipeline.Plot``), each from analysis results
alone: a characterization's condition sweeps over the input level and over the supply, and its
responses over frequency at one input level (the record's plots). The viewer draws a record's from
its JSON, ``flow.plot.render`` any with matplotlib (the CLI's figures step)."""

from __future__ import annotations

from flow.pipeline import Plot, plot

from .params import SUPPLY_SWEEP
from .types import AnalysisImpedance, AnalysisTransfer


@plot
def plot_vout_vin(transfer: AnalysisTransfer) -> Plot:
    """The operating-point output level over the input level."""
    return Plot(
        name="vout_vin",
        title="Output level over the input level",
        x_label="Input level (V)",
        y_label="Output (V)",
        x=[float(value) for value in transfer.vin_v],
        series={"output": [float(value) for value in transfer.vout_v]},
    )


@plot
def plot_gain_vin(transfer: AnalysisTransfer) -> Plot:
    """The small-signal gain at the lowest frequency over the input level."""
    return Plot(
        name="gain_vin",
        title="Small-signal gain over the input level",
        x_label="Input level (V)",
        y_label="Gain (V/V)",
        x=[float(value) for value in transfer.vin_v],
        series={"gain": [float(value) for value in transfer.gain_dc]},
    )


@plot
def plot_bandwidth_vin(transfer: AnalysisTransfer) -> Plot:
    """The -3 dB bandwidth over the input level."""
    return Plot(
        name="bandwidth_vin",
        title="-3 dB bandwidth over the input level",
        x_label="Input level (V)",
        y_label="-3 dB bandwidth (Hz)",
        x=[float(value) for value in transfer.vin_v],
        series={"bandwidth": [float(value) for value in transfer.bandwidth_hz]},
        y_log=True,
    )


@plot
def plot_zout_vin(impedance: AnalysisImpedance) -> Plot:
    """The output impedance at the lowest frequency over the input level."""
    return Plot(
        name="zout_vin",
        title="Output impedance over the input level",
        x_label="Input level (V)",
        y_label="Output impedance (ohm)",
        x=[float(value) for value in impedance.vin_v],
        series={"output impedance": [float(value) for value in impedance.zout_dc_ohm]},
        y_log=True,
    )


@plot
def plot_psrr_vin(transfer: AnalysisTransfer) -> Plot:
    """The PSRR at the lowest frequency over the input level."""
    return Plot(
        name="psrr_vin",
        title="PSRR over the input level",
        x_label="Input level (V)",
        y_label="PSRR (dB)",
        x=[float(value) for value in transfer.vin_v],
        series={"PSRR": [float(value) for value in transfer.psrr_dc_db]},
    )


@plot
def plot_gain_frequency(transfer: AnalysisTransfer) -> Plot:
    """The response over frequency at one input level (the result's first point: the record's,
    the nominal input's run)."""
    return Plot(
        name="gain_frequency",
        title="Response over frequency at the nominal input",
        x_label="Frequency (Hz)",
        y_label="Gain (dB)",
        x=[float(value) for value in transfer.frequency_hz],
        series={"gain": [float(value) for value in transfer.gain_db[0]]},
        x_log=True,
    )


@plot
def plot_zout_frequency(impedance: AnalysisImpedance) -> Plot:
    """The output impedance over frequency at one input level (the result's first point: the
    record's, the nominal input's run)."""
    return Plot(
        name="zout_frequency",
        title="Output impedance over frequency at the nominal input",
        x_label="Frequency (Hz)",
        y_label="Output impedance (ohm)",
        x=[float(value) for value in impedance.frequency_hz],
        series={"output impedance": [float(value) for value in impedance.zout_ohm[0]]},
        x_log=True,
        y_log=True,
    )


@plot
def plot_gain_supply(supply: AnalysisTransfer) -> Plot:
    """The small-signal gain over the supply (``SUPPLY_SWEEP``), the input at its share of it."""
    return Plot(
        name="gain_supply",
        title="Small-signal gain over the supply (the input at its share of it)",
        x_label="Supply over nominal",
        y_label="Gain (V/V)",
        x=list(SUPPLY_SWEEP),
        series={"gain": [float(value) for value in supply.gain_dc]},
    )


@plot
def plot_bandwidth_supply(supply: AnalysisTransfer) -> Plot:
    """The -3 dB bandwidth over the supply (``SUPPLY_SWEEP``), the input at its share of it."""
    return Plot(
        name="bandwidth_supply",
        title="-3 dB bandwidth over the supply (the input at its share of it)",
        x_label="Supply over nominal",
        y_label="-3 dB bandwidth (Hz)",
        x=list(SUPPLY_SWEEP),
        series={"bandwidth": [float(value) for value in supply.bandwidth_hz]},
        y_log=True,
    )


@plot
def plot_psrr_supply(supply: AnalysisTransfer) -> Plot:
    """The PSRR at the lowest frequency over the supply (``SUPPLY_SWEEP``), the input at its
    share of it."""
    return Plot(
        name="psrr_supply",
        title="PSRR over the supply (the input at its share of it)",
        x_label="Supply over nominal",
        y_label="PSRR (dB)",
        x=list(SUPPLY_SWEEP),
        series={"PSRR": [float(value) for value in supply.psrr_dc_db]},
    )
