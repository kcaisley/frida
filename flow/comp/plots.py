"""The comparator's figures as ``Plot`` specs (``flow.pipeline.Plot``), each from analysis results
alone, every quantity in its SI unit: a characterization's condition sweeps (the record's plots),
the lab captures' S-curves, offset and noise (its noise and offset over the common mode the
record's own specs, so a campaign and a characterization overlay as instances), and the comparator
inside a converter: its output's edges in the bench's scope records and a simulation's latches over
each decision. The viewer draws a record's from its JSON, ``flow.plot.render`` any with matplotlib
(the CLI's figures step)."""

from __future__ import annotations

import math
from collections.abc import Sequence

import numpy as np

from flow.pipeline import Band, Heatmap, Marker, Plot, plot

from .params import SUPPLY_SWEEP
from .types import (
    AnalysisCommonMode,
    AnalysisDelay,
    AnalysisEdgeEye,
    AnalysisMetastability,
    AnalysisOffsetNoise,
    AnalysisPower,
    AnalysisResponse,
    AnalysisSamplingNoise,
    AnalysisScopeEdges,
    AnalysisScurve,
)


@plot
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


@plot
def plot_noise_cm(common_mode: AnalysisCommonMode) -> Plot:
    """The input-referred noise over the common mode (NaN where an S-curve gave no valid fit): a
    characterization's S-curves (``sweep.record``), or a lab campaign's captures, each common mode's
    (``python -m flow.plot comp <captures>``)."""
    return Plot(
        name="noise_cm",
        title="Input-referred noise over the common mode",
        x_label="Input common mode (V)",
        y_label="Input-referred noise (V)",
        x=[float(value) for value in common_mode.vin_cm_v],
        series={"noise": _valid(common_mode.noise_sigma_v, common_mode.validity)},
    )


@plot
def plot_offset_cm(common_mode: AnalysisCommonMode) -> Plot:
    """The offset over the common mode (NaN where an S-curve gave no valid fit): a characterization's
    systematic offset alone (no mismatch is simulated), a capture's with its mismatch and its input's
    chain."""
    return Plot(
        name="offset_cm",
        title="Offset over the common mode",
        x_label="Input common mode (V)",
        y_label="Offset (V)",
        x=[float(value) for value in common_mode.vin_cm_v],
        series={"offset": _valid(common_mode.offset_v, common_mode.validity)},
    )


@plot
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


@plot
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


@plot
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


@plot
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


@plot
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


@plot
def plot_offset_noise(offset: AnalysisOffsetNoise) -> Plot:
    """One common mode's S-curve, the probability of a high decision at each input; where its fit is
    valid, its offset marked and its noise shaded about it, a sigma either side (unlabelled: the
    title gives it, and a label centred on the offset would sit on the marker's)."""
    valid = offset.validity == "valid"
    low, high = offset.offset_v - offset.noise_sigma_v, offset.offset_v + offset.noise_sigma_v
    return Plot(
        name="offset_noise",
        title=f"S-curve at {offset.vin_cm_v:.3g} V: offset {offset.offset_v * 1e3:.3g} mV, "
        f"noise {offset.noise_sigma_v * 1e3:.3g} mV ({offset.validity})",
        x_label="Differential input (V)",
        y_label="Decision probability",
        x=[float(value) for value in offset.vin_diff_v],
        series={"P(high)": [float(value) for value in offset.decision_probability]},
        x_markers=[Marker(float(offset.offset_v), "Offset")] if valid else [],
        x_bands=[Band(float(low), float(high))] if valid else [],
    )


@plot
def plot_common_mode_scurves(common_mode: AnalysisCommonMode) -> Plot:
    """Each common mode's S-curve, a row each (the lowest at the bottom, a curve without a valid fit
    named by why): the probability of a high decision at each input of every curve, empty where a
    curve has no point there."""
    return _scurves(
        "common_mode_scurves",
        "S-curves over the common mode",
        "Input common mode",
        [
            _named(f"{cm:.3g} V", validity)
            for cm, validity in zip(common_mode.vin_cm_v, common_mode.validity, strict=True)
        ],
        common_mode.vin_diff_v,
        common_mode.decision_probability,
    )


@plot
def plot_sampling_noise_scurves(sampling: AnalysisSamplingNoise) -> Plot:
    """Each curve's S-curve over the DAC's coupling (P/N % of VDD_DAC) and sampling mode, a row each
    (a curve without a valid fit named by why), as ``plot_common_mode_scurves`` draws them."""
    return _scurves(
        "sampling_noise_scurves",
        "S-curves over the DAC's coupling",
        "Coupling P/N, mode",
        _couplings(sampling),
        sampling.vin_diff_v,
        sampling.decision_probability,
    )


@plot
def plot_sampling_offset(sampling: AnalysisSamplingNoise) -> Plot:
    """The offset of each curve over the DAC's coupling and sampling mode, a category each (NaN
    where its fit is not valid)."""
    return _by_coupling(
        "sampling_offset", "Offset over the DAC's coupling", "Offset (V)", {"offset": sampling.offset_v}, sampling
    )


@plot
def plot_sampling_noise(sampling: AnalysisSamplingNoise) -> Plot:
    """The input-referred noise of each curve over the DAC's coupling and sampling mode, a category
    each (NaN where its fit is not valid)."""
    return _by_coupling(
        "sampling_noise",
        "Input-referred noise over the DAC's coupling",
        "Input-referred noise (V)",
        {"noise": sampling.noise_sigma_v},
        sampling,
    )


@plot
def plot_scope_eye(edges: AnalysisScopeEdges) -> Plot:
    """The comparator's output at the bench's scope, every decision of every record folded at its
    COMP rise (``analyze_scope_edges``): each cell's share of them, by decade; where COMP is high
    shaded."""
    return Plot(
        name="scope_eye",
        title=f"Measured decision eye: {edges.records} records × {edges.decision_count} decisions",
        x_label="Time from each COMP rise (s)",
        y_label="COMP_OUT at the scope (V)",
        x=[],
        series={},
        x_bands=[Band(0.0, _six(edges.clock_high_s), "COMP high")],
        heatmap=_map(edges.eye_time_s, edges.voltage_v, edges.eye_share, "Share of decisions", log=True),
    )


@plot
def plot_scope_timing(edges: AnalysisScopeEdges) -> Plot:
    """The comparator's output at the bench's scope over the conversion, every record from its B0
    COMP rise: each cell's share of them, by decade; where COMP is high shaded (``_decisions``)."""
    return Plot(
        name="scope_timing",
        title=f"Measured comparator over the conversion: {edges.records} records",
        x_label="Time from B0's COMP rise (s)",
        y_label="COMP_OUT at the scope (V)",
        x=[],
        series={},
        x_bands=_decisions(edges.rise_s, edges.fall_s),
        heatmap=_map(edges.timing_time_s, edges.voltage_v, edges.timing_share, "Share of records", log=True),
    )


@plot
def plot_scope_response(edges: AnalysisScopeEdges) -> Plot:
    """The time from each decision's COMP rise to COMP_OUT's midpoint at the bench's scope (the
    pads, the board and the probes in it): each decision's delays as a column of the map, each
    cell's share of its timed transitions, and their median."""
    return _response(
        "scope_response",
        f"COMP_OUT's response at {edges.conversion_rate_hz / 1e6:g} MS/s (measured)",
        "Time from COMP rise to COMP_OUT's midpoint (s)",
        edges.response_s,
        edges.response_share,
        edges.response_median_s,
        "Share of the decision's transitions",
    )


@plot
def plot_sr_eye(eye: AnalysisEdgeEye) -> Plot:
    """A simulated converter's SR latch output (positive), every decision of every conversion folded
    at its clock's rise (``analyze_edge_eye``): each cell's share of them, by decade; where the clock
    is high shaded."""
    return _eye("sr_eye", "SR latch", "SR latch P (V)", eye, eye.sr_eye)


@plot
def plot_xc_eye(eye: AnalysisEdgeEye) -> Plot:
    """A simulated converter's regenerative latch, |P - N| of its XC nodes, every decision of every
    conversion folded at its clock's rise, as ``plot_sr_eye`` draws the SR latch's."""
    return _eye("xc_eye", "XC latch", "XC latch |P − N| (V)", eye, eye.xc_eye)


@plot
def plot_sr_timing(eye: AnalysisEdgeEye) -> Plot:
    """A simulated converter's SR latch output (positive) over the conversion, every conversion from
    B0's clock rise: each cell's share of them, by decade; where the clock is high shaded
    (``_decisions``)."""
    return _timing("sr_timing", "SR latch", "SR latch P (V)", eye, eye.sr_timing)


@plot
def plot_xc_timing(eye: AnalysisEdgeEye) -> Plot:
    """A simulated converter's regenerative latch, |P - N| of its XC nodes, over the conversion, as
    ``plot_sr_timing`` draws the SR latch's."""
    return _timing("xc_timing", "XC latch", "XC latch |P − N| (V)", eye, eye.xc_timing)


@plot
def plot_sr_response(response: AnalysisResponse) -> Plot:
    """A simulated converter's SR latch output: the time from each decision's clock rise until it is
    in the half of the rail its decision asks for (``analyze_response``; an output already there is
    held, not timed), each decision's as a column of the map, and their median."""
    return _response(
        "sr_response",
        f"SR latch response at {response.conversion_rate_hz / 1e6:.3g} MS/s (simulated, 50% VDD)",
        "Time from the clock's rise to the SR output's midpoint (s)",
        response.sr_s,
        response.sr_share,
        response.sr_median_s,
        "Share of the decision's responses",
    )


@plot
def plot_xc_response(response: AnalysisResponse) -> Plot:
    """A simulated converter's regenerative latch: the time from each decision's clock rise until
    both of its XC nodes are past half the supply, each its own way, before the clock resets, as
    ``plot_sr_response`` draws the SR latch's."""
    return _response(
        "xc_response",
        f"XC latch response at {response.conversion_rate_hz / 1e6:.3g} MS/s (simulated, both rails at 50% VDD)",
        "Time from the clock's rise to both XC rails' midpoint (s)",
        response.xc_s,
        response.xc_share,
        response.xc_median_s,
        "Share of the decision's responses",
    )


def _valid(values: np.ndarray, validity: Sequence[str]) -> list[float]:
    """``values`` where their fit is valid, NaN elsewhere."""
    return [float(value) if ok == "valid" else math.nan for value, ok in zip(values, validity, strict=True)]


def _named(name: str, validity: str) -> str:
    """A curve's name, with why its fit is not valid where it is not."""
    return name if validity == "valid" else f"{name} ({validity})"


def _couplings(sampling: AnalysisSamplingNoise) -> list[str]:
    """Each curve of a sampling campaign by its coupling (P/N % of VDD_DAC) and mode, and why its
    fit is not valid where it is not."""
    return [
        _named(f"{coupling:g}/{100 - coupling:g} % {mode}", validity)
        for coupling, mode, validity in zip(
            sampling.coupling_percent, sampling.sampling_mode, sampling.validity, strict=True
        )
    ]


def _by_coupling(
    name: str, title: str, y_label: str, quantity: dict[str, np.ndarray], sampling: AnalysisSamplingNoise
) -> Plot:
    """One fitted quantity of each curve of a sampling campaign (``quantity``: its name and values), a
    category each, NaN where the fit is not valid."""
    return Plot(
        name=name,
        title=title,
        x_label="Coupling P/N (% of VDD_DAC), mode",
        y_label=y_label,
        x=[float(index) for index in range(len(sampling.validity))],
        series={label: _valid(values, sampling.validity) for label, values in quantity.items()},
        x_labels=_couplings(sampling),
    )


def _scurves(
    name: str, title: str, y_label: str, rows: list[str], inputs_v: np.ndarray, probability: np.ndarray
) -> Plot:
    """S-curves as a map: a row a curve (``rows``, the first at the bottom; ``inputs_v`` a row a
    curve's ascending inputs, NaN past them), each curve's probability of a high decision in its own
    cells, halfway to its neighbouring inputs (``_edges``): the map's columns are cut at every
    curve's cell edges, so curves on different inputs each keep their own; empty where a curve has
    no point."""
    own = [np.asarray(_edges(row[np.isfinite(row)])) for row in inputs_v]
    # the edges of every curve's cells, to a picovolt (as the analyses round their inputs)
    edges = np.unique(np.round(np.concatenate(own), 12))
    centres = (edges[:-1] + edges[1:]) / 2
    z = []
    for cells, probability_row in zip(own, probability, strict=True):
        cell = np.searchsorted(cells, centres, side="right") - 1
        inside = (cell >= 0) & (cell < len(cells) - 1)
        z.append([_six(probability_row[index]) if ok else math.nan for index, ok in zip(cell, inside, strict=True)])
    return Plot(
        name=name,
        title=title,
        x_label="Differential input (V)",
        y_label=y_label,
        x=[],
        series={},
        y_labels=rows,
        heatmap=Heatmap(
            x=[_six(edge) for edge in edges],
            y=[index - 0.5 for index in range(len(rows) + 1)],
            z=z,
            label="P(high)",
        ),
    )


def _eye(name: str, latch: str, y_label: str, eye: AnalysisEdgeEye, share: np.ndarray) -> Plot:
    """A simulated latch's decision eye (``share`` on the eye's cells), where the clock is high
    shaded."""
    return Plot(
        name=name,
        title=f"Simulated decision eye of the {latch}: {eye.records} conversions × {len(eye.decision_edge_s)} decisions",
        x_label="Time from each clock rise (s)",
        y_label=y_label,
        x=[],
        series={},
        x_bands=[Band(0.0, _six(eye.clock_high_s), "Clock high")],
        heatmap=_map(eye.eye_time_s, eye.voltage_v, share, "Share of decisions", log=True),
    )


def _timing(name: str, latch: str, y_label: str, eye: AnalysisEdgeEye, share: np.ndarray) -> Plot:
    """A simulated latch over the conversion (``share`` on the conversion's cells), where the clock
    is high shaded (``_decisions``)."""
    return Plot(
        name=name,
        title=f"Simulated {latch} over the conversion: {eye.records} conversions",
        x_label="Time from B0's clock rise (s)",
        y_label=y_label,
        x=[],
        series={},
        x_bands=_decisions(eye.decision_edge_s, eye.fall_s),
        heatmap=_map(eye.timing_time_s, eye.voltage_v, share, "Share of conversions", log=True),
    )


def _response(
    name: str,
    title: str,
    y_label: str,
    edges_s: np.ndarray,
    share: np.ndarray,
    median_s: np.ndarray,
    label: str,
) -> Plot:
    """Each decision's response times as a column of a map (``share`` on the cells ``edges_s``) and
    their median as the curve over it; the median alone, and the title saying so, where none was
    timed."""
    decisions = len(median_s)
    timed = len(edges_s) > 1
    return Plot(
        name=name,
        title=title if timed else f"{title}: none timed",
        x_label="Decision (B0 first)",
        y_label=y_label,
        x=[float(index) for index in range(decisions)],
        series={"Median": [_six(value) for value in median_s]},
        x_ticks="step",
        heatmap=_map(np.arange(decisions + 1) - 0.5, edges_s, share, label) if timed else None,
    )


def _decisions(rise_s: np.ndarray, fall_s: np.ndarray) -> list[Band]:
    """Where the clock is high in each decision, from its rise to its fall; every fourth named by
    its decision (``B0``, ``B4``, ...), so that the names fit a narrow plot."""
    return [
        Band(_six(rise), _six(fall), f"B{decision}" if decision % 4 == 0 else "")
        for decision, (rise, fall) in enumerate(zip(rise_s, fall_s, strict=True))
    ]


def _map(x: np.ndarray, y: np.ndarray, z: np.ndarray, label: str, *, log: bool = False) -> Heatmap:
    """A map's cells (their edges ``x`` and ``y``, a row of ``z`` a row of cells), its numbers to six
    significant digits."""
    return Heatmap(
        x=[_six(value) for value in x],
        y=[_six(value) for value in y],
        z=[[_six(value) for value in row] for row in np.asarray(z, dtype=np.float64)],
        label=label,
        log=log,
    )


def _edges(centres: np.ndarray) -> list[float]:
    """The edges of cells around the ascending ``centres``: halfway between neighbours, the outer
    ones as far out as their inner half-gap (0.1 mV either side of a lone one)."""
    if len(centres) == 1:
        return [float(centres[0]) - 1e-4, float(centres[0]) + 1e-4]
    middles = (centres[1:] + centres[:-1]) / 2
    return [float(2 * centres[0] - middles[0]), *middles.tolist(), float(2 * centres[-1] - middles[-1])]


def _six(value: float) -> float:
    """``value`` to six significant digits (NaN as it is), as the viewer's other exports."""
    value = float(value)
    return float(f"{value:.6g}") if math.isfinite(value) else math.nan
