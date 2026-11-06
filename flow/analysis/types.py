"""Typed measurement and analysis data exchanged by FRIDA post-processing."""

from __future__ import annotations

from dataclasses import dataclass
from itertools import pairwise
from typing import TYPE_CHECKING, Literal

import numpy as np

from flow.analysis import calc
from flow.pipeline import (  # the shared base, used here and re-exported for the unmigrated blocks
    Analysis,
    Identity,
    Meas,
    MeasInfo,
    Wave,
    check_identity,
    measurement_identity,
)

__all__ = [
    "Analysis",
    "AnalysisAdcCompOutEdgeEye",
    "AnalysisAdcComparatorEdgeEye",
    "AnalysisAdcComparatorResponse",
    "AnalysisAdcScopeBits",
    "AnalysisCdacCapMismatch",
    "AnalysisCdacTransition",
    "AnalysisScope",
    "Identity",
    "Meas",
    "MeasAdc",
    "MeasCapArray",
    "MeasCdac",
    "MeasInfo",
    "Wave",
    "check_identity",
    "measurement_identity",
]

if TYPE_CHECKING:
    from flow import adc
    from flow.cdac.caparray.sim import CapArrayTbParams
    from flow.cdac.caparray.subckt import CapArrayConfig, CapArrayParams
    from flow.scans.params import AdcScanParams


# =============================================================================
# Typed measurements
# =============================================================================
#
# Every measurement derives from :class:`Meas`, which fixes the fields all of
# them carry. A subclass adds only its per-record readback arrays. The HDF5
# reader finds a subclass by its stored type name, so a new measurement class
# needs no registration.


@dataclass(frozen=True, slots=True, kw_only=True)
class MeasAdc(Meas):
    """ADC conversions: one row per conversion.

    ``bout`` holds one column per decision in chronological order: each
    switched capacitor C0..C(n-1) has one decision, and a final terminal
    comparison switches no capacitor. ``dout`` is the normalized output code,
    calculated from all decisions rather than from a BOUT slice.
    """

    dut: adc.Params
    param: AdcScanParams | adc.TbParams
    conversion_index: np.ndarray
    bout: np.ndarray
    dout_raw: np.ndarray
    dout: np.ndarray
    vin_diff_v: np.ndarray
    fastrx_word: np.ndarray | None = None

    @property
    def sample_rate_hz(self) -> float:
        """Return the true sampling rate including sequencer idle padding."""

        return float(self.tb.symbol_rate) / len(self.tb.seq_init_pattern)

    @property
    def active_conversion_rate_hz(self) -> float:
        """Return the nominal conversion rate excluding idle padding."""

        from flow.adc.sim import AdcSequence

        return float(self.tb.symbol_rate) / AdcSequence.from_tb_params(self.tb).conversion_symbols

    @property
    def logic_phase_delay_symbols(self) -> float:
        """Return the COMP-to-LOGIC delay relative to mid-decision, in symbols."""

        from flow.adc.sim import AdcSequence

        interval, delay = AdcSequence.from_tb_params(self.tb).logic_timing
        return delay - interval / 2

    @property
    def comparator_time_percent(self) -> float:
        """Return the COMP-to-LOGIC delay as a percentage of the decision interval."""

        from flow.adc.sim import AdcSequence

        interval, delay = AdcSequence.from_tb_params(self.tb).logic_timing
        return 100.0 * delay / interval

    @property
    def nominal_bout_weights(self) -> np.ndarray:
        """Return the design raw-code weight of each chronological decision.

        Every switched capacitor contributes twice its unit weight (both CDAC
        sides move), and the terminal comparison adds one unit; the decision
        count is therefore the capacitor count plus one.
        """

        from flow.cdac.caparray import get_caparray_weights

        return np.asarray([2 * weight for weight in get_caparray_weights(self.dut.cdac)] + [1], dtype=np.int64)

    @property
    def code_max(self) -> int:
        """Return the largest normalized output code."""

        return (1 << self.dut.adc_bits) - 1

    @property
    def input_lsb_v(self) -> float:
        """Return the differential input voltage of one output code.

        A behavioral capture carries its CDAC and top-plate load, so its full
        scale is ``2 VREF C_eff / C_tot`` over ``2**adc_bits`` codes. Other
        captures keep the nominal ``VDD_DAC / code_max`` of the noise analysis.
        """

        tb = self.tb
        cdac = getattr(self.param, "cdac", None)
        if cdac is None:
            return float(tb.vdd_dac.dc) / self.code_max
        from flow.adc.subckt import calc_side_capacitances

        main_f, diff_f = calc_side_capacitances(cdac, tb, "p")
        effective_f = np.sum(main_f) + (-1 if tb.dac_diffcaps else 1) * np.sum(diff_f)
        total_f = np.sum(main_f) + np.sum(diff_f) + cdac.parasitic_f
        return float(2 * float(tb.vdd_dac.dc) * effective_f / total_f / (1 << self.dut.adc_bits))

    @property
    def symbols_per_decision(self) -> int:
        """Return the symbol spacing of the INIT-relative COMP rises, one per decision."""

        from flow.adc.sim import AdcSequence

        comp = np.fromiter((bit == "1" for bit in AdcSequence.from_tb_params(self.tb).relative_to_init().comp), bool)
        spacing = np.diff(np.flatnonzero(comp & ~np.roll(comp, 1)))
        decisions = len(self.nominal_bout_weights)
        if len(spacing) != decisions - 1 or np.any(spacing != spacing[0]):
            raise ValueError(f"sequence must contain {decisions} equally spaced COMP rising edges")
        return int(spacing[0])


@dataclass(frozen=True, slots=True, kw_only=True)
class MeasCdac(Meas):
    """CDAC trials inferred through the comparator: one row per trial.

    Every DAC-state array has one column per capacitor, C0 first.
    """

    dut: CapArrayConfig
    param: AdcScanParams | adc.TbParams | CapArrayTbParams
    trial_index: np.ndarray
    dac_state_p: np.ndarray
    dac_state_n: np.ndarray
    vin_diff_v: np.ndarray
    decision: np.ndarray
    dac_state_before_p: np.ndarray | None = None
    dac_state_before_n: np.ndarray | None = None
    vin_cm_v: np.ndarray | None = None
    fastrx_word: np.ndarray | None = None
    fastrx_frame: np.ndarray | None = None

    @property
    def expected_effective_fraction(self) -> np.ndarray:
        """Return the flavor-aware normalized main-minus-diff PEX expectation, for display.

        This is the design reference drawn beside a measured result, not part
        of an analysis. New captures record the extracted top-plate parasitic
        weight. Older ones take it from the board inventory's flavor table,
        the design record of the fabricated CDAC flavor on that channel.
        """

        weights = np.asarray(self.dut.weights, dtype=np.float64)
        total_weights = 65.0 * np.ceil(weights / 64.0)
        if "cdac_topplate_parasitic_weight" in self.info.readbacks:
            topplate_parasitic_weight = float(self.info.readbacks["cdac_topplate_parasitic_weight"])
        elif self.info.backend != "physical" or self.group is None or self.index is None:
            topplate_parasitic_weight = 0.0
        else:
            from flow.scans.params import load_board_map

            board_map = load_board_map()
            flavor = board_map["adc_channels"][self.index]
            topplate_parasitic_weight = float(
                board_map["adc_flavors"][flavor].get("cdac_topplate_parasitic_weight", 0.0)
            )
        if not np.isfinite(topplate_parasitic_weight) or topplate_parasitic_weight < 0.0:
            raise ValueError("CDAC top-plate parasitic expectation must be finite and non-negative")
        return weights / (np.sum(total_weights) + topplate_parasitic_weight)


@dataclass(frozen=True, slots=True, kw_only=True)
class MeasCapArray(Meas):
    """Reserved capacitance-extraction result; its data payload is not defined yet.

    The converter remains unimplemented until nominal/extracted and Monte
    Carlo capacitance fields are specified.
    """

    dut: CapArrayParams
    param: CapArrayParams


# =============================================================================
# Typed analysis results
# =============================================================================
#
# Every result derives from :class:`Analysis` and belongs to exactly one
# instance (``group``, ``index``) and DUT parameter set. Results never contain
# other results; comparisons across instances pass several results to one
# plotter.


# Shared waveform and instrument analyses


@dataclass(frozen=True, slots=True)
class AnalysisScope(Analysis):
    """One oscilloscope capture with its traces, spectra, and per-trace statistics.

    Trace names are the probed signal names plus any math traces such as
    ``vin_p_adc-vin_n_adc``. Every mapping is keyed like ``wave.v``, whose one
    record holds the physical and math traces. ``spectrum_v_per_sqrt_hz`` is
    the one-sided amplitude density about each trace's mean.
    ``bandwidth_hz`` is the -3 dB acquisition bandwidth: the bandwidth-limit
    filter, or a narrower acquisition-mode filter such as High Res.
    """

    name: str
    wave: Wave
    bandwidth_hz: float
    spectrum_frequency_hz: np.ndarray
    spectrum_v_per_sqrt_hz: dict[str, np.ndarray]
    mean_v: dict[str, float]
    ac_rms_v: dict[str, float]

    @property
    def sample_rate_hz(self) -> float:
        """Return the uniform sample rate of the captured record."""

        return 1.0 / float(self.wave.time_s[1] - self.wave.time_s[0])

    @property
    def spectrum_rms_v(self) -> dict[str, float]:
        """Return each trace's RMS obtained by integrating its spectral density."""

        return {
            name: calc.rmsNoise(density, self.spectrum_frequency_hz)
            for name, density in self.spectrum_v_per_sqrt_hz.items()
        }

    @property
    def decade_edges_hz(self) -> np.ndarray:
        """Return the band edges of the decade split, from the first bin to the acquisition bandwidth.

        Inner edges are powers of ten; the outer edges are the lowest
        nonzero frequency and the bandwidth, so the end bands may be partial.
        """

        lowest_hz = float(self.spectrum_frequency_hz[1])
        highest_hz = min(self.bandwidth_hz, float(self.spectrum_frequency_hz[-1]))
        inner = 10.0 ** np.arange(np.floor(np.log10(lowest_hz)) + 1.0, np.ceil(np.log10(highest_hz)))
        return np.concatenate(([lowest_hz], inner[(inner > lowest_hz) & (inner < highest_hz)], [highest_hz]))

    @property
    def decade_rms_v(self) -> dict[str, np.ndarray]:
        """Return each trace's RMS within every band of ``decade_edges_hz``.

        The bands add in quadrature to the RMS over the acquisition bandwidth.
        """

        edges = self.decade_edges_hz
        frequency = self.spectrum_frequency_hz
        return {
            name: np.asarray(
                [
                    calc.rmsNoise(
                        np.interp(band, frequency, density),
                        band,
                    )
                    for band in (
                        np.concatenate(([low], frequency[(frequency > low) & (frequency < high)], [high]))
                        for low, high in pairwise(edges)
                    )
                ]
            )
            for name, density in self.spectrum_v_per_sqrt_hz.items()
        }

    @property
    def band_rms_v(self) -> dict[str, float]:
        """Return each trace's total RMS from its lowest bin to the acquisition bandwidth."""

        return {name: float(np.sqrt(np.sum(np.square(rms_v)))) for name, rms_v in self.decade_rms_v.items()}


# ADC analyses


@dataclass(frozen=True, slots=True)
class AnalysisAdcScopeBits(Analysis):
    """One scope-decoded conversion aligned with its corresponding FastRX word."""

    scope_bits: np.ndarray
    fastrx_bits: np.ndarray
    comp_threshold_v: float
    comp_out_threshold_v: float
    comp_edge_times_s: np.ndarray
    sample_times_s: np.ndarray
    sample_values_v: np.ndarray

    @property
    def mismatch_mask(self) -> np.ndarray:
        """Return one flag for each disagreement between both decoders."""

        return self.scope_bits != self.fastrx_bits

    @property
    def mismatch_count(self) -> int:
        """Return the number of scope/FastRX bit disagreements."""

        return int(np.count_nonzero(self.mismatch_mask))

    @property
    def scope_bit_string(self) -> str:
        """Return the scope decisions in acquisition order."""

        return "".join("1" if bit else "0" for bit in self.scope_bits)

    @property
    def fastrx_bit_string(self) -> str:
        """Return the FastRX decisions in acquisition order."""

        return "".join("1" if bit else "0" for bit in self.fastrx_bits)


@dataclass(frozen=True, slots=True)
class AnalysisAdcComparatorResponse(Analysis):
    """Per-decision rail-valid response times relative to COMP rising edges.

    NaN marks a response that did not settle in the observed window. An SR
    output that remained valid from the clock edge is marked as held instead
    of being assigned a zero response time. The final XC rail polarity sets
    the target SR state, including decisions where the XC rails did not settle
    across the midpoint before COMP reset.
    """

    conversion_index: np.ndarray
    decision_index: np.ndarray
    internal_response_s: np.ndarray
    sr_response_s: np.ndarray
    sr_held: np.ndarray
    sample_interval_s: float
    conversion_rate_hz: float


@dataclass(frozen=True, slots=True)
class AnalysisAdcComparatorEdgeEye(Analysis):
    """Simulated comparator traces aligned per conversion and folded per decision.

    The first axis of ``aligned_v`` and ``eye_v`` is the trace: comparator
    clock, positive SR-latch output, and XC-latch ``|P-N|``. ``aligned_v``
    rows are conversions on ``aligned_time_s``, relative to B0's COMP rise;
    ``eye_v`` rows are every conversion's decisions in order on ``eye_phase``,
    in decision periods. ``decision_edge_s`` is each decision's median COMP
    rise after B0. NaN lies outside a record.
    """

    decision_period_s: float
    decision_edge_s: np.ndarray
    supply_v: float
    aligned_time_s: np.ndarray
    aligned_v: np.ndarray
    eye_phase: np.ndarray
    eye_v: np.ndarray


@dataclass(frozen=True, slots=True)
class AnalysisAdcCompOutEdgeEye(Analysis):
    """Scope waveforms and measured COMP-to-COMP_OUT timing for one sequence.

    Rows of ``clock_edges_s``, ``delays_s``, and ``jitter_s`` are captures;
    columns are the decisions of one conversion. ``aligned_*`` rows are
    captures on ``aligned_time_s``, relative to each capture's B0 COMP rise.
    ``eye_*`` rows are every capture's decisions in order, folded on
    ``eye_phase``, in decision periods from each COMP rise. NaN lies outside
    a capture.
    """

    aligned_time_s: np.ndarray
    aligned_comp_v: np.ndarray
    aligned_comp_out_v: np.ndarray
    eye_phase: np.ndarray
    eye_comp_v: np.ndarray
    eye_comp_out_v: np.ndarray
    clock_edges_s: np.ndarray
    delays_s: np.ndarray
    jitter_s: np.ndarray
    unchanged: np.ndarray
    multiple: np.ndarray
    unsettled: np.ndarray
    decision_period_s: float
    conversion_rate_hz: float

    @property
    def decision_count(self) -> int:
        return self.clock_edges_s.shape[1]

    @property
    def delay_bounds_s(self) -> tuple[float, float]:
        valid = self.delays_s[np.isfinite(self.delays_s)]
        return float(valid.min()), float(valid.max())


# CDAC analyses


@dataclass(frozen=True, slots=True)
class AnalysisCdacTransition(Analysis):
    """Comparator decision transition of one CDAC element switching curve."""

    side: Literal["p", "n"]
    element: int
    direction: Literal["1to0", "0to1"]
    diffcaps: int
    vin_diff_v: np.ndarray
    decision_probability: np.ndarray
    trial_count: np.ndarray
    transition_v: float
    valid: bool


@dataclass(frozen=True, slots=True)
class AnalysisCdacCapMismatch(Analysis):
    """Normalized main, difference, and effective capacitance of every CDAC element."""

    main_fraction: np.ndarray
    diff_fraction: np.ndarray
    effective_fraction: np.ndarray
    effective_fraction_by_direction: np.ndarray
    direction_bias: np.ndarray
