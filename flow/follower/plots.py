"""The follower's figures as ``Plot`` specs (``flow.pipeline.Plot``), each from analysis results
alone: a characterization's condition sweeps over the input level and over the supply, and its
responses over frequency at one input level (the record's plots). The viewer draws a record's from
its JSON, ``flow.plot.render`` any with matplotlib (the CLI's figures step)."""

from __future__ import annotations

import math

import numpy as np
from hdl21.primitives import MosType

from flow.pipeline import Band, Plot, plot

from .types import AnalysisCharacteristic, AnalysisImpedance, AnalysisTransfer


def _at(value: float, unit: str = "Hz") -> str:
    """A value as a title states it (a title's condition, not an axis): a frequency or a
    capacitance with the largest SI prefix it is at least one of ("1 kHz", "100 fF"), a voltage in
    volts ("0.6 V")."""
    if unit == "V" or not value:
        return f"{value:.4g} {unit}"
    exponent = next((exponent for exponent in range(9, -18, -3) if abs(value) >= 10.0**exponent), -15)
    prefix = {9: "G", 6: "M", 3: "k", 0: "", -3: "m", -6: "u", -9: "n", -12: "p", -15: "f"}[exponent]
    return f"{value / 10.0**exponent:.4g} {prefix}{unit}"


def _source(transfer_or_impedance: AnalysisTransfer | AnalysisImpedance) -> str:
    """The bench's source and load as a title states them: "from an ideal source (R_S = 0) into
    100 fF"."""
    return f"from an ideal source (R_S = 0) into {_at(transfer_or_impedance.cload_f, 'F')}"


def _held(supply: AnalysisTransfer) -> str:
    """Where the supply sweep holds the input, as a title states it: at its level for an NMOS
    input, its distance below the supply for a PMOS one (runs.testbenches)."""
    if supply.dut.input_xtors == MosType.NMOS:
        return f"the input held at {_at(float(supply.vin_v[0]), 'V')}"
    return f"the input held {_at(float(supply.vdd_v[0] - supply.vin_v[0]), 'V')} below the supply"


# not in the reference texts: the input range (the block's: the gain within 10 %) as a shaded band
def _range(characteristic: AnalysisCharacteristic) -> list[Band]:
    """The input range (``AnalysisCharacteristic.vin_min_v`` to ``vin_max_v``) as a band shaded
    behind a plot over the input level."""
    return [Band(low=characteristic.vin_min_v, high=characteristic.vin_max_v, label="input range")]


# not in the reference texts: a display rule, values outside the input range drawn as gaps
def _inside(values: np.ndarray, vin_v: np.ndarray, characteristic: AnalysisCharacteristic) -> list[float]:
    """``values`` at the input levels ``vin_v`` inside the input range, NaN (a gap) outside it,
    where the follower does not follow and its value is the circuit's, of no follower's meaning."""
    inside = (vin_v >= characteristic.vin_min_v) & (vin_v <= characteristic.vin_max_v)
    return [float(value) if within else math.nan for value, within in zip(values, inside, strict=True)]


# [Razavi-Analog] Fig. 3.34(c), p. 68: the source follower's input-output characteristic, V_out over
# V_in; for Topology.FLIPPED not in the reference texts
@plot
def plot_vout_vin(characteristic: AnalysisCharacteristic) -> Plot:
    """The output level over the input level from the input's DC sweep, the input range shaded."""
    return Plot(
        name="vout_vin",
        title="Output level over the input level (DC sweep), the input range shaded",
        x_label="Input level (V)",
        y_label="Output (V)",
        x=[float(value) for value in characteristic.vin_v],
        series={"output": [float(value) for value in characteristic.vout_v]},
        x_bands=_range(characteristic),
    )


# [Razavi-Analog] Fig. 3.36, p. 69: the source follower's voltage gain A_v over V_in; for
# Topology.FLIPPED not in the reference texts
@plot
def plot_gain_vin(characteristic: AnalysisCharacteristic) -> Plot:
    """The gain dVout/dVin of the input's DC sweep over the input level, the input range
    shaded."""
    return Plot(
        name="gain_vin",
        title="Gain dVout/dVin over the input level (DC sweep), the input range shaded",
        x_label="Input level (V)",
        y_label="Gain (V/V)",
        x=[float(value) for value in characteristic.vin_v],
        series={"gain": [float(value) for value in characteristic.gain]},
        x_bands=_range(characteristic),
    )


# [Razavi-Analog] Fig. 6.43, p. 204: the -3-dB bandwidth; not in the reference texts: its sweep over
# the input level
@plot
def plot_bandwidth_vin(transfer: AnalysisTransfer, characteristic: AnalysisCharacteristic) -> Plot:
    """The -3 dB bandwidth over the input level inside the input range (shaded), a gap outside
    it, from an ideal source into the bench's load."""
    return Plot(
        name="bandwidth_vin",
        title=f"-3 dB bandwidth over the input level, inside the input range, {_source(transfer)}",
        x_label="Input level (V)",
        y_label="-3 dB bandwidth (Hz)",
        x=[float(value) for value in transfer.vin_v],
        series={"bandwidth": _inside(transfer.bandwidth_hz, transfer.vin_v, characteristic)},
        y_log=True,
        x_bands=_range(characteristic),
    )


# [Razavi-Analog] Eq. (3.93), Fig. 3.39, p. 71: the source follower's output resistance (r_O1 || r_O2
# beside it, Fig. 3.42, p. 72); a flipped follower's, and the sweep over the input level, not in the
# reference texts
@plot
def plot_rout_vin(impedance: AnalysisImpedance, characteristic: AnalysisCharacteristic) -> Plot:
    """The output resistance (the output impedance at the lowest frequency) over the input level
    inside the input range (shaded), a gap outside it."""
    return Plot(
        name="rout_vin",
        title=f"Output resistance at {_at(impedance.frequency_hz[0])} over the input level, inside the input range",
        x_label="Input level (V)",
        y_label="Output resistance (ohm)",
        x=[float(value) for value in impedance.vin_v],
        series={"output resistance": _inside(impedance.rout_ohm, impedance.vin_v, characteristic)},
        y_log=True,
        x_bands=_range(characteristic),
    )


# [Razavi-Analog] Sec. 9.11, p. 400: PSRR at low frequencies; not in the reference texts: its sweep
# over the input level
@plot
def plot_psrr_vin(transfer: AnalysisTransfer, characteristic: AnalysisCharacteristic) -> Plot:
    """The PSRR at the lowest frequency over the input level inside the input range (shaded), a
    gap outside it."""
    return Plot(
        name="psrr_vin",
        title=f"PSRR at {_at(transfer.frequency_hz[0])} over the input level, inside the input range",
        x_label="Input level (V)",
        y_label="PSRR (dB)",
        x=[float(value) for value in transfer.vin_v],
        series={"PSRR": _inside(transfer.psrr_dc_db, transfer.vin_v, characteristic)},
        x_bands=_range(characteristic),
    )


# [Razavi-Analog] Fig. 6.43, p. 204: the frequency response, 20 log |Vout / Vin| over log frequency
@plot
def plot_gain_frequency(transfer: AnalysisTransfer) -> Plot:
    """The response over frequency at one input level (the result's first point: the record's,
    the nominal input's run), from an ideal source into the bench's load."""
    return Plot(
        name="gain_frequency",
        title=f"Response over frequency at the nominal input, {_at(float(transfer.vin_v[0]), 'V')}, {_source(transfer)}",
        x_label="Frequency (Hz)",
        y_label="Gain (dB)",
        x=[float(value) for value in transfer.frequency_hz],
        series={"gain": [float(value) for value in transfer.gain_db[0]]},
        x_log=True,
    )


# [Razavi-Analog] Fig. 6.28(b), p. 192: the source follower's |Z_out| (R_S = 0 here); for
# Topology.FLIPPED not in the reference texts
@plot
def plot_zout_frequency(impedance: AnalysisImpedance) -> Plot:
    """The follower's output impedance over frequency, its load set aside, at one input level
    (the result's first point: the record's, the nominal input's run), driven from an ideal
    source."""
    at = _at(float(impedance.vin_v[0]), "V")
    return Plot(
        name="zout_frequency",
        title=f"Output impedance over frequency at the nominal input, {at}, {_source(impedance)}, the load set aside",
        x_label="Frequency (Hz)",
        y_label="Output impedance (ohm)",
        x=[float(value) for value in impedance.frequency_hz],
        series={"output impedance": [float(value) for value in impedance.zout_ohm[0]]},
        x_log=True,
        y_log=True,
    )


# [Razavi-Analog] Eq. (3.8), p. 48: the voltage gain; not in the reference texts: its sweep over the
# supply V_DD (Fig. 3.4, p. 48), the input held relative to the rail its input device's source rides
@plot
def plot_gain_supply(supply: AnalysisTransfer) -> Plot:
    """The small-signal gain over the supply, the input held relative to the rail its input
    device's source rides."""
    return Plot(
        name="gain_supply",
        title=f"Small-signal gain at {_at(supply.frequency_hz[0])} over the supply, {_held(supply)}",
        x_label="Supply (V)",
        y_label="Gain (V/V)",
        x=[float(value) for value in supply.vdd_v],
        series={"gain": [float(value) for value in supply.gain_dc]},
    )


# [Razavi-Analog] Fig. 6.43, p. 204: the -3-dB bandwidth; not in the reference texts: its sweep over
# the supply, the input held relative to the rail its input device's source rides
@plot
def plot_bandwidth_supply(supply: AnalysisTransfer) -> Plot:
    """The -3 dB bandwidth over the supply, the input held relative to the rail its input device's
    source rides, from an ideal source into the bench's load."""
    return Plot(
        name="bandwidth_supply",
        title=f"-3 dB bandwidth over the supply, {_held(supply)}, {_source(supply)}",
        x_label="Supply (V)",
        y_label="-3 dB bandwidth (Hz)",
        x=[float(value) for value in supply.vdd_v],
        series={"bandwidth": [float(value) for value in supply.bandwidth_hz]},
        y_log=True,
    )


# [Razavi-Analog] Sec. 9.11, p. 400: PSRR at low frequencies; not in the reference texts: its sweep
# over the supply, the input held relative to the rail its input device's source rides
@plot
def plot_psrr_supply(supply: AnalysisTransfer) -> Plot:
    """The PSRR at the lowest frequency over the supply, the input held relative to the rail its
    input device's source rides."""
    return Plot(
        name="psrr_supply",
        title=f"PSRR at {_at(supply.frequency_hz[0])} over the supply, {_held(supply)}",
        x_label="Supply (V)",
        y_label="PSRR (dB)",
        x=[float(value) for value in supply.vdd_v],
        series={"PSRR": [float(value) for value in supply.psrr_dc_db]},
    )
