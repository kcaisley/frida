"""Typed measurement and analysis data exchanged by FRIDA post-processing."""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass, field, fields
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

import numpy as np

from flow.analysis import calc

if TYPE_CHECKING:
    from flow.adc.sequences import AdcSequence
    from flow.adc.sim import AdcTbParams
    from flow.adc.subckt import AdcParams
    from flow.caparray.sim import CapArrayTbParams
    from flow.caparray.subckt import CapArrayConfig, CapArrayParams
    from flow.comp.sim import CompTbParams
    from flow.comp.subckt import CompParams
    from flow.samp.sim import SampTbParams
    from flow.samp.subckt import SampParams
    from flow.scans.params import AdcScanParams


@dataclass(frozen=True, slots=True)
class Identity:
    """Instance and design identity shared by measurements and their results.

    ``group`` is the physical board number or a Monte Carlo seed. ``index`` is
    the observed ADC channel or a Monte Carlo iteration. Nominal simulations
    use ``None`` for both. ``dut`` holds the design parameters analyzed.
    """

    group: int | None
    index: int | None
    dut: AdcParams | CompParams | CapArrayConfig | SampParams | None


@dataclass(frozen=True, slots=True)
class Analysis:
    """Base of every typed analysis result: identity only, no behavior.

    ``dut`` is ``None`` only for instrument characterizations that involve no
    design under test, such as a raw oscilloscope capture or the diff-amp.
    """

    group: int | None
    index: int | None
    dut: AdcParams | CompParams | CapArrayConfig | SampParams | None

    @property
    def identity(self) -> Identity:
        return Identity(self.group, self.index, self.dut)


def measurement_identity(measurements: Sequence[Meas]) -> Identity:
    """Return the one identity shared by every input measurement, or raise."""

    if not measurements:
        raise ValueError("analysis requires at least one measurement")
    identities = [measurement.identity for measurement in measurements]
    first = identities[0]
    if any(identity != first for identity in identities[1:]):
        raise ValueError("analysis inputs must share one group, index, and DUT parameter set")
    return first


def check_identity(prior: Analysis | Sequence[Analysis], identity: Identity, *, name: str) -> None:
    """Raise unless every prior result has the consumer's group, index, and DUT params."""

    for result in (prior,) if isinstance(prior, Analysis) else prior:
        if result.identity != identity:
            raise ValueError(
                f"{name} ({type(result).__name__}) does not match the analyzed instance: "
                f"group {result.group}/{identity.group}, index {result.index}/{identity.index}, "
                f"DUT params {'equal' if result.dut == identity.dut else 'different'}"
            )


# =============================================================================
# Typed measurements
# =============================================================================
#
# Every measurement derives from :class:`Meas`, which fixes the fields all of
# them carry. A subclass adds only its per-record readback arrays. The HDF5
# reader finds a subclass by its stored type name, so a new measurement class
# needs no registration.


@dataclass(frozen=True, slots=True)
class MeasInfo:
    """Run information shared by every measurement."""

    backend: Literal["physical", "behavioral", "spice"]
    timestamp_utc: datetime
    instruments: dict[str, str] = field(default_factory=dict)
    readbacks: dict[str, str | int | float | bool] = field(default_factory=dict)
    source_path: Path | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class Wave:
    """Records of node voltages and supply currents, read like Cadence's ``v()`` and ``i()``.

    Keys are canonical net names from the circuit's net bundle, such as
    ``comp_out`` or ``comp.latch_p``, whether the source was a simulator or an
    oscilloscope. ``vin_diff`` is the one derived name: a differential probe
    observes no single net. Supply currents use the supply name and are
    positive for current drawn from the source. Every trace has one row per
    record, the measurement row given by ``record_index``, and one column per
    sample of ``time_s``.
    """

    record_index: np.ndarray
    time_s: np.ndarray
    v: dict[str, np.ndarray]
    i: dict[str, np.ndarray] = field(default_factory=dict)

    def __post_init__(self) -> None:
        shape = (len(self.record_index), len(self.time_s))
        if len(self.time_s) < 2 or np.any(np.diff(self.time_s) <= 0):
            raise ValueError("wave.time_s must contain at least two strictly increasing samples")
        if wrong := {name: trace.shape for name, trace in (*self.v.items(), *self.i.items()) if trace.shape != shape}:
            raise ValueError(f"wave traces must have shape {shape}: {wrong}")


@dataclass(frozen=True, slots=True, kw_only=True)
class Meas:
    """Base of every measurement: identity, run information, parameters, and waveforms.

    ``group``, ``index``, and ``dut`` match :class:`Analysis`, so results copy
    them across. ``param`` holds the complete scan or testbench parameters
    that produced the data. A subclass adds its readback arrays as fields;
    they share one row per conversion or trial, which is checked here.
    """

    group: int | None
    index: int | None
    dut: AdcParams | CompParams | CapArrayConfig | SampParams | CapArrayParams
    info: MeasInfo
    param: Any
    wave: Wave | None = None

    def __post_init__(self) -> None:
        rows = {
            data_field.name: len(value)
            for data_field in fields(self)
            if isinstance(value := getattr(self, data_field.name), np.ndarray)
        }
        if len(set(rows.values())) > 1:
            raise ValueError(f"{type(self).__name__} readback arrays are not aligned: {rows}")

    @property
    def identity(self) -> Identity:
        return Identity(self.group, self.index, self.dut)

    @property
    def tb(self) -> Any:
        """Return the testbench parameters, nested inside scan parameters for a physical capture."""

        return getattr(self.param, "tb", self.param)


@dataclass(frozen=True, slots=True, kw_only=True)
class MeasAdc(Meas):
    """ADC conversions: one row per conversion.

    ``bout`` holds one column per decision in chronological order: each
    switched capacitor C0..C(n-1) has one decision, and a final terminal
    comparison switches no capacitor. ``dout`` is the normalized output code,
    calculated from all decisions rather than from a BOUT slice.
    """

    dut: AdcParams
    param: AdcScanParams | AdcTbParams
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

        from flow.adc.sequences import AdcSequence

        return float(self.tb.symbol_rate) / AdcSequence.from_tb_params(self.tb).conversion_symbols

    @property
    def logic_phase_delay_symbols(self) -> float:
        """Return the COMP-to-LOGIC delay relative to mid-decision, in symbols."""

        from flow.adc.sequences import AdcSequence

        interval, delay = AdcSequence.from_tb_params(self.tb).logic_timing
        return delay - interval / 2

    @property
    def comparator_time_percent(self) -> float:
        """Return the COMP-to-LOGIC delay as a percentage of the decision interval."""

        from flow.adc.sequences import AdcSequence

        interval, delay = AdcSequence.from_tb_params(self.tb).logic_timing
        return 100.0 * delay / interval

    @property
    def nominal_bout_weights(self) -> np.ndarray:
        """Return the design raw-code weight of each chronological decision.

        Every switched capacitor contributes twice its unit weight (both CDAC
        sides move), and the terminal comparison adds one unit; the decision
        count is therefore the capacitor count plus one.
        """

        from flow.caparray import get_caparray_weights

        return np.asarray([2 * weight for weight in get_caparray_weights(self.dut.cdac)] + [1], dtype=np.int64)

    @property
    def code_max(self) -> int:
        """Return the largest normalized output code."""

        return (1 << self.dut.adc_bits) - 1

    @property
    def symbols_per_decision(self) -> int:
        """Return the symbol spacing of the INIT-relative COMP rises, one per decision."""

        from flow.adc.sequences import AdcSequence

        comp = np.fromiter((bit == "1" for bit in AdcSequence.from_tb_params(self.tb).relative_to_init().comp), bool)
        spacing = np.diff(np.flatnonzero(comp & ~np.roll(comp, 1)))
        decisions = len(self.nominal_bout_weights)
        if len(spacing) != decisions - 1 or np.any(spacing != spacing[0]):
            raise ValueError(f"sequence must contain {decisions} equally spaced COMP rising edges")
        return int(spacing[0])


@dataclass(frozen=True, slots=True, kw_only=True)
class MeasComp(Meas):
    """Comparator trials: one row per trial with its input and binary decision."""

    dut: CompParams
    param: AdcScanParams | AdcTbParams | CompTbParams
    trial_index: np.ndarray
    vin_diff_v: np.ndarray
    vin_cm_v: np.ndarray
    decision: np.ndarray
    fastrx_word: np.ndarray | None = None
    fastrx_frame: np.ndarray | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class MeasCdac(Meas):
    """CDAC trials inferred through the comparator: one row per trial.

    Every DAC-state array has one column per capacitor, C0 first.
    """

    dut: CapArrayConfig
    param: AdcScanParams | AdcTbParams | CapArrayTbParams
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
            flavor = board_map["boards"][self.group]["adc_channels"][self.index]
            topplate_parasitic_weight = float(
                board_map["adc_flavors"][flavor].get("cdac_topplate_parasitic_weight", 0.0)
            )
        if not np.isfinite(topplate_parasitic_weight) or topplate_parasitic_weight < 0.0:
            raise ValueError("CDAC top-plate parasitic expectation must be finite and non-negative")
        return weights / (np.sum(total_weights) + topplate_parasitic_weight)


@dataclass(frozen=True, slots=True, kw_only=True)
class MeasSamp(Meas):
    """Sampler trials: one row per trial; the observations are all in ``wave``."""

    dut: SampParams
    param: SampTbParams
    trial_index: np.ndarray


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
class AnalysisDiffampNoise(Analysis):
    """Gaussian and spectral characterization of one quiet waveform."""

    mean_v: float
    centered_v: np.ndarray
    sample_rate_hz: float
    measurement_bandwidth_hz: float
    spectrum_frequency_hz: np.ndarray
    spectrum_amplitude_density_v_per_sqrt_hz: np.ndarray

    @property
    def noise_rms_v(self) -> float:
        """Return the time-domain RMS of the centered samples."""

        return calc.rms(self.centered_v)

    @property
    def integrated_fft_noise_rms_v(self) -> float:
        """Return the RMS obtained by integrating the spectral density."""

        return calc.rmsNoise(self.spectrum_amplitude_density_v_per_sqrt_hz, self.spectrum_frequency_hz)


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
class AnalysisAdcTransfer(Analysis):
    """Mean static transfer and dispersion at each differential input."""

    vin_diff_v: np.ndarray
    mean_dout: np.ndarray
    std_dout: np.ndarray
    sample_count: np.ndarray


@dataclass(frozen=True, slots=True)
class AnalysisAdcEndpointNonlinearity(Analysis):
    """Endpoint INL and DNL from code transitions of a stepped static input."""

    code: np.ndarray
    dnl: np.ndarray
    inl: np.ndarray
    transition_vin_diff_v: np.ndarray
    endpoint_lsb_v: float
    missing_codes: int

    @property
    def maximum_abs_dnl(self) -> float:
        return float(np.max(np.abs(self.dnl)))

    @property
    def maximum_abs_inl(self) -> float:
        return float(np.max(np.abs(self.inl)))


@dataclass(frozen=True, slots=True)
class AnalysisAdcCodeDensityNonlinearity(Analysis):
    """Code-density INL and DNL from a uniformly distributed input.

    ``retained_sample_count`` records how many conversions remained after the
    ramp-wrap exclusion supplied by an :class:`AnalysisAdcRamp`, if any. The
    end codes are excluded from ``code`` because a finite ramp clips into them.
    """

    code: np.ndarray
    dnl: np.ndarray
    inl: np.ndarray
    count: np.ndarray
    ideal_count: float
    retained_sample_count: int
    sample_count: int

    @property
    def missing_codes(self) -> int:
        return int(np.count_nonzero(self.count == 0))

    @property
    def maximum_abs_dnl(self) -> float:
        return float(np.max(np.abs(self.dnl)))

    @property
    def maximum_abs_inl(self) -> float:
        return float(np.max(np.abs(self.inl)))


@dataclass(frozen=True, slots=True)
class AnalysisAdcCalibration(Analysis):
    """Common output of each per-decision digital calibration method.

    Coefficients are chronological B0..B(n-1): one per switched capacitor plus
    the terminal decision. All methods normalize these coefficients to the
    inclusive ADC output range, so a corrected fractional code is simply
    ``BOUT @ calibrated_weights``. ``measured_weight_mask`` distinguishes
    directly measured or fitted coefficients from nominally preserved ones.
    """

    method: Literal["calibration1", "calibration2", "calibration3"]
    label: str
    code_max: int
    nominal_weights: np.ndarray
    calibrated_weights: np.ndarray
    measured_weight_mask: np.ndarray
    training_sample_count: int
    validation_sample_count: int
    output_gain: float
    output_offset_lsb: float

    def decode_bout(self, bout: np.ndarray, *, rounded: bool = True) -> np.ndarray:
        """Decode stored BOUT decisions with the calibrated weights, clipped to the code range.

        The stored DAQ codes are never replaced; calibrated codes exist only
        in the analysis that requests them.
        """

        decisions = np.asarray(bout)
        if decisions.ndim != 2 or decisions.shape[1] != len(self.calibrated_weights):
            raise ValueError("calibrated ADC decoding requires one BOUT column per calibrated weight")
        if np.any((decisions != 0) & (decisions != 1)):
            raise ValueError("calibrated ADC decoding requires binary BOUT values")
        fractional = np.clip(decisions.astype(np.float64) @ self.calibrated_weights, 0.0, float(self.code_max))
        return fractional if not rounded else np.rint(fractional).astype(np.int64)


@dataclass(frozen=True, slots=True)
class AnalysisAdcRamp(Analysis):
    """One DOUT decoding of a repeated ramp capture, reconstructed against the ramp phase.

    The ramp period in conversions comes from the PWL source and the sample
    rate; only the wrap phase is fitted, from the stored nominal DOUT, so every
    decoding of the same capture shares it. ``retained`` is the single
    definition of which conversions are far enough from a wrap to be used;
    calibrations and code-density nonlinearity reuse it. ``decoding`` is the
    nominal DOUT or the calibration whose weights decoded the stored BOUT.
    """

    decoding: Literal["uncalibrated_dout", "calibration1", "calibration2", "calibration3"]
    label: str
    weights: np.ndarray
    sample_rate_hz: float
    period_conversions: float
    first_wrap_conversion: float
    retained: np.ndarray
    vin_diff_min_v: float
    vin_diff_max_v: float
    transfer_vin_diff_v: np.ndarray
    transfer_mean_dout: np.ndarray
    transfer_sample_count: np.ndarray
    code: np.ndarray
    count: np.ndarray
    linearity_code: np.ndarray
    dnl: np.ndarray
    inl: np.ndarray
    ideal_count: float

    @property
    def maximum_abs_dnl(self) -> float:
        """Return the largest absolute differential nonlinearity."""

        return float(np.max(np.abs(self.dnl)))

    @property
    def maximum_abs_inl(self) -> float:
        """Return the largest absolute integral nonlinearity."""

        return float(np.max(np.abs(self.inl)))

    @property
    def missing_codes(self) -> int:
        """Return the number of unpopulated codes in the linearity interval."""

        histogram_indices = np.searchsorted(self.code, self.linearity_code)
        return int(np.count_nonzero(self.count[histogram_indices] == 0))

    @property
    def maximum_transfer_reversal_dout(self) -> float:
        """Return the largest backwards step in the reconstructed transfer."""

        differences = np.diff(self.transfer_mean_dout)
        return max(0.0, float(-np.min(differences))) if len(differences) else 0.0

    @property
    def sample_count(self) -> int:
        return len(self.retained)

    @property
    def retained_sample_count(self) -> int:
        return int(np.count_nonzero(self.retained))

    @property
    def reset_excluded_sample_count(self) -> int:
        """Return the number of samples removed around ramp wraps."""

        return self.sample_count - self.retained_sample_count

    @property
    def ramp_frequency_hz(self) -> float:
        return self.sample_rate_hz / self.period_conversions

    @property
    def ramp_phase_cycles(self) -> float:
        return float(np.mod(-self.first_wrap_conversion / self.period_conversions, 1.0))

    @property
    def conversion_phase(self) -> np.ndarray:
        """Return each conversion's position within its ramp period, in [0, 1)."""

        sample = np.arange(self.sample_count, dtype=np.float64)
        return np.mod((sample - self.first_wrap_conversion) / self.period_conversions, 1.0)

    @property
    def cycle_index(self) -> np.ndarray:
        """Return each conversion's ramp cycle; -1 precedes the first wrap."""

        sample = np.arange(self.sample_count, dtype=np.float64)
        return np.floor((sample - self.first_wrap_conversion) / self.period_conversions).astype(np.int64)

    @property
    def complete_cycle(self) -> np.ndarray:
        """Return conversions that lie in a ramp cycle captured from wrap to wrap."""

        cycles = self.cycle_index
        last_complete = int(np.floor((self.sample_count - self.first_wrap_conversion) / self.period_conversions)) - 1
        return (cycles >= 0) & (cycles <= last_complete)

    @property
    def reset_conversion_index(self) -> np.ndarray:
        """Return the first conversion after each wrap inside the capture."""

        wraps = self.first_wrap_conversion + self.period_conversions * np.arange(
            math.ceil((self.sample_count - self.first_wrap_conversion) / self.period_conversions)
        )
        return np.ceil(wraps).astype(np.int64)


@dataclass(frozen=True, slots=True)
class AnalysisAdcCodeDistribution(Analysis):
    """Code statistics and histograms for one or more static input points."""

    vin_diff_v: np.ndarray
    code: np.ndarray
    count: np.ndarray

    @property
    def sample_count(self) -> np.ndarray:
        """Return the sample count at each input point."""

        return np.sum(self.count, axis=1, dtype=np.int64)

    @property
    def mean_dout(self) -> np.ndarray:
        """Return the histogram-weighted mean output code."""

        return np.sum(self.count * self.code, axis=1) / self.sample_count

    @property
    def std_dout(self) -> np.ndarray:
        """Return the histogram-weighted output-code standard deviation."""

        deviation = self.code - self.mean_dout[:, None]
        return np.sqrt(np.sum(self.count * deviation**2, axis=1) / self.sample_count)

    @property
    def minimum_dout(self) -> np.ndarray:
        """Return the lowest populated output code at each input point."""

        return self.code[np.argmax(self.count > 0, axis=1)]

    @property
    def maximum_dout(self) -> np.ndarray:
        """Return the highest populated output code at each input point."""

        reverse_index = np.argmax(self.count[:, ::-1] > 0, axis=1)
        return self.code[len(self.code) - 1 - reverse_index]


@dataclass(frozen=True, slots=True)
class AnalysisAdcNoise(Analysis):
    """Fixed-input output variation of one capture, with its timing coordinates.

    ``code`` spans every output code of the ADC, so its length fixes the
    resolution. ``readout_valid`` is the judgment that the digital readout is
    trustworthy: simulations always are; a physical capture needs a valid
    scope/FastRX comparison with no bit mismatches and no lost frames.
    """

    sequence: AdcSequence
    symbol_rate_hz: float
    sample_rate_hz: float
    active_conversion_rate_hz: float
    logic_phase_delay_symbols: float
    comparator_time_percent: float
    input_lsb_v: float
    pretrigger_vin_diff_mean_v: float
    pretrigger_vin_diff_noise_rms_v: float
    bit_mismatches: int
    readout_valid: bool
    code: np.ndarray
    count: np.ndarray

    @property
    def code_max(self) -> int:
        return len(self.code) - 1

    @property
    def sample_count(self) -> int:
        return int(np.sum(self.count))

    @property
    def mean_dout(self) -> float:
        return float(np.sum(self.count * self.code) / self.sample_count)

    @property
    def std_dout(self) -> float:
        return float(np.sqrt(np.sum(self.count * (self.code - self.mean_dout) ** 2) / self.sample_count))

    @property
    def minimum_dout(self) -> int:
        return int(self.code[np.argmax(self.count > 0)])

    @property
    def maximum_dout(self) -> int:
        return int(self.code[len(self.code) - 1 - np.argmax(self.count[::-1] > 0)])

    @property
    def modal_fraction(self) -> float:
        return float(np.max(self.count) / self.sample_count)

    @property
    def distinct_code_count(self) -> int:
        return int(np.count_nonzero(self.count))

    @property
    def noise_valid(self) -> bool:
        """A constant code only bounds the noise below the code-variance resolution."""

        return self.std_dout > 0.0

    @property
    def input_referred_noise_rms_v(self) -> float:
        """Return code dispersion converted through the nominal input LSB."""

        return self.std_dout * self.input_lsb_v if self.noise_valid else math.nan

    @property
    def enob_bits(self) -> float:
        """Return the noise-equivalent resolution for a full-scale sine."""

        if not self.noise_valid:
            return math.nan
        full_scale_rms_lsb = self.code_max / (2.0 * math.sqrt(2.0))
        return (20.0 * math.log10(full_scale_rms_lsb / self.std_dout) - 1.76) / 6.02


@dataclass(frozen=True, slots=True)
class AnalysisAdcOperatingConditions(Analysis):
    """Plausibility of one ADC's fixed-input captures over sequence and rate.

    Each capture is one row. ``reference_mean_dout`` is the median mean code
    over every sequence at the lowest symbol rate. A row is plausible when its
    code is not constant, its mean stays within the shift limit of that
    reference, its readout is valid, and its noise-equivalent ENOB is finite.
    """

    sequence: tuple[AdcSequence, ...]
    symbol_rate_hz: np.ndarray
    enob_bits: np.ndarray
    mean_shift_dout: np.ndarray
    reference_mean_dout: float
    shift_limit_dout: float
    constant: np.ndarray
    shifted: np.ndarray
    readout_valid: np.ndarray

    @property
    def plausible(self) -> np.ndarray:
        return ~self.constant & ~self.shifted & self.readout_valid & np.isfinite(self.enob_bits)


@dataclass(frozen=True, slots=True)
class AnalysisAdcDynamic(Analysis):
    """Sine-fit, residual, spectrum, and dynamic ADC figures of merit.

    The residual tail limit is a multiple of the fitted residual RMS, and the
    expected tail count is the matching two-sided Gaussian tail probability.
    """

    sample_rate_hz: float
    active_conversion_rate_hz: float
    logic_phase_delay_symbols: float
    input_frequency_hz: float
    fitted_frequency_hz: float
    adc_bits: int
    offset_dout: float
    amplitude_dout: float
    phase_rad: float
    input_referred_noise_rms_v: float
    input_referred_residual_rms_v: float
    spectral_sndr_db: float
    spectral_snr_db: float
    spectral_thd_db: float
    spectral_sfdr_db: float
    spectral_enob_bits: float
    residual_tail_limit_dout: float
    expected_residual_tail_count: float
    time_s: np.ndarray
    measured_dout: np.ndarray
    fitted_dout: np.ndarray
    residual_dout: np.ndarray
    spectrum_frequency_hz: np.ndarray
    spectrum_dbfs: np.ndarray

    @property
    def sample_count(self) -> int:
        """Return the number of analyzed conversion samples."""

        return len(self.measured_dout)

    @property
    def amplitude_dbfs(self) -> float:
        """Return fitted sine amplitude relative to the ADC full-scale peak."""

        if self.amplitude_dout == 0.0:
            return -math.inf
        full_scale_peak_dout = ((1 << self.adc_bits) - 1) / 2.0
        return 20.0 * math.log10(self.amplitude_dout / full_scale_peak_dout)

    @property
    def signal_rms_dout(self) -> float:
        """Return RMS amplitude of the fitted sine."""

        return self.amplitude_dout / math.sqrt(2.0)

    @property
    def residual_rms_dout(self) -> float:
        """Return RMS of the time-domain fit residual."""

        return calc.rms(self.residual_dout)

    @property
    def sinad_db(self) -> float:
        """Return time-domain signal-to-noise-and-distortion ratio."""

        if self.signal_rms_dout == 0.0:
            return -math.inf
        if self.residual_rms_dout == 0.0:
            return math.inf
        return 20.0 * math.log10(self.signal_rms_dout / self.residual_rms_dout)

    @property
    def enob_bits(self) -> float:
        """Return time-domain effective number of bits."""

        return (self.sinad_db - 1.76) / 6.02

    @property
    def negative_residual_tail_count(self) -> int:
        """Return residuals below the negative tail limit."""

        return int(np.count_nonzero(self.residual_dout < -self.residual_tail_limit_dout))

    @property
    def positive_residual_tail_count(self) -> int:
        """Return residuals above the positive tail limit."""

        return int(np.count_nonzero(self.residual_dout > self.residual_tail_limit_dout))

    @property
    def maximum_abs_residual_dout(self) -> float:
        """Return the largest absolute fit residual."""

        return float(np.max(np.abs(self.residual_dout)))


@dataclass(frozen=True, slots=True)
class AnalysisAdcPower(Analysis):
    """Static-baseline and incremental supply power of one capture."""

    sample_rate_hz: float
    active_conversion_rate_hz: float
    vdd_a_static_power_w: float
    vdd_d_static_power_w: float
    vdd_dac_static_power_w: float
    vdd_a_dynamic_power_w: float
    vdd_d_dynamic_power_w: float
    vdd_dac_dynamic_power_w: float

    @property
    def total_static_power_w(self) -> float:
        """Return total idle power across all three supply rails."""

        return self.vdd_a_static_power_w + self.vdd_d_static_power_w + self.vdd_dac_static_power_w

    @property
    def total_dynamic_power_w(self) -> float:
        """Return incremental conversion power across all three rails."""

        return self.vdd_a_dynamic_power_w + self.vdd_d_dynamic_power_w + self.vdd_dac_dynamic_power_w

    @property
    def total_power_w(self) -> float:
        """Return complete active power across all three supply rails."""

        return self.total_static_power_w + self.total_dynamic_power_w


@dataclass(frozen=True, slots=True)
class AnalysisAdcPowerWaveform(Analysis):
    """One aligned simulated conversion with rail power and timing context."""

    active_conversion_rate_hz: float
    time_s: np.ndarray
    rail_power_w: np.ndarray
    static_power_w: np.ndarray
    active_power_w: np.ndarray
    timing_high: np.ndarray

    @property
    def active_duration_s(self) -> float:
        """Return the duration of one active conversion."""

        return 1.0 / self.active_conversion_rate_hz

    @property
    def analog_power_w(self) -> np.ndarray:
        return self.rail_power_w[0]

    @property
    def digital_power_w(self) -> np.ndarray:
        return self.rail_power_w[1]

    @property
    def dac_power_w(self) -> np.ndarray:
        return self.rail_power_w[2]

    @property
    def init_high(self) -> np.ndarray:
        return self.timing_high[0]

    @property
    def samp_high(self) -> np.ndarray:
        return self.timing_high[1]

    @property
    def comp_high(self) -> np.ndarray:
        return self.timing_high[2]

    @property
    def logic_high(self) -> np.ndarray:
        return self.timing_high[3]


@dataclass(frozen=True, slots=True)
class AnalysisAdcSamplingNoise(Analysis):
    """One P/N voltage observation per conversion at a recorded time or window.

    Equal window bounds denote an interpolated instantaneous observation.
    The current ADC analysis samples 1 ns after SAMP falls, including possible
    comparator activity; this is not source-isolated kT/C or final code noise.
    """

    conversion_index: np.ndarray
    window_start_s: np.ndarray
    window_stop_s: np.ndarray
    held_p_v: np.ndarray
    held_n_v: np.ndarray
    input_diff_v: np.ndarray

    @property
    def held_diff_v(self) -> np.ndarray:
        return self.held_p_v - self.held_n_v

    @property
    def sigma_v(self) -> float:
        return calc.stddev(self.held_diff_v, sample=True)


@dataclass(frozen=True, slots=True)
class AnalysisAdcCdacSettling(Analysis):
    """Aligned representative C0-first SAR stages and CDAC settling."""

    active_conversion_rate_hz: float
    stage_index: np.ndarray
    cycle_index: np.ndarray
    conversion_index: np.ndarray
    time_s: np.ndarray
    clk_comp_v: np.ndarray
    comp_out_p_v: np.ndarray
    comp_out_n_v: np.ndarray
    seq_logic_v: np.ndarray
    dac_state_p_v: np.ndarray
    dac_state_n_v: np.ndarray
    dac_botplate_p_v: np.ndarray
    dac_botplate_n_v: np.ndarray
    vdac_p_settling_error_v: np.ndarray
    vdac_n_settling_error_v: np.ndarray
    static_vdac_p_v: np.ndarray
    static_vdac_n_v: np.ndarray
    vdac_p_settling_s: np.ndarray
    vdac_n_settling_s: np.ndarray
    comp_latch_p_v: np.ndarray | None = None
    comp_latch_n_v: np.ndarray | None = None


@dataclass(frozen=True, slots=True)
class AnalysisAdcDecisionPaths(Analysis):
    """Running SAR estimates reconstructed from every captured decision record."""

    conversion_index: np.ndarray
    final_dout: np.ndarray
    bout: np.ndarray
    weights: np.ndarray
    estimate_dout: np.ndarray


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


@dataclass(frozen=True, slots=True)
class AnalysisAdcTimingClosure(Analysis):
    """One row per saved decision, with times relative to its waveform record.

    NaN means a required observation was missing or never became stable.
    The final decision has no CDAC update: its CDAC times are NaN and that
    check is inapplicable. CDAC settling is relative to the observed end of
    the update window, not a separately measured DC solution. The setup
    requirements and tolerances used are recorded with the result.
    """

    conversion_index: np.ndarray
    decision_index: np.ndarray
    comp_rise_s: np.ndarray
    comp_reset_s: np.ndarray
    logic_rise_s: np.ndarray
    next_comp_s: np.ndarray
    internal_final_diff_v: np.ndarray
    internal_stable_s: np.ndarray
    sr_stable_s: np.ndarray
    sr_matches_at_logic: np.ndarray
    cdac_stable_s: np.ndarray
    capacitor_count: int
    required_logic_setup_s: float
    required_cdac_setup_s: float
    internal_differential_v: float
    cdac_tolerance_v: float
    sample_interval_s: float

    @property
    def internal_resolution_s(self) -> np.ndarray:
        return self.internal_stable_s - self.comp_rise_s

    @property
    def sr_response_s(self) -> np.ndarray:
        return self.sr_stable_s - self.comp_rise_s

    @property
    def logic_to_cdac_s(self) -> np.ndarray:
        return self.cdac_stable_s - self.logic_rise_s

    @property
    def logic_setup_s(self) -> np.ndarray:
        return self.logic_rise_s - np.maximum(self.internal_stable_s, self.sr_stable_s)

    @property
    def cdac_setup_s(self) -> np.ndarray:
        return self.next_comp_s - self.cdac_stable_s

    @property
    def logic_ready(self) -> np.ndarray:
        return self.sr_matches_at_logic & (self.logic_setup_s >= self.required_logic_setup_s)

    @property
    def cdac_applicable(self) -> np.ndarray:
        return self.decision_index < self.capacitor_count

    @property
    def cdac_ready(self) -> np.ndarray:
        return self.cdac_applicable & (self.cdac_setup_s >= self.required_cdac_setup_s)

    @property
    def passed(self) -> np.ndarray:
        return self.logic_ready & (~self.cdac_applicable | self.cdac_ready)


@dataclass(frozen=True, slots=True)
class AnalysisAdcTimingSummary(Analysis):
    """Setup and comparator-reset margins of one PEX case's timing closure."""

    sequence: AdcSequence
    symbol_rate_hz: float
    decisions: int
    cdac_decisions: int
    reset_edges_observed: int
    ordinary_reset_gaps_observed: int
    minimum_reset_gap_s: float
    resolved_before_reset: int
    sr_matches_at_logic: int
    logic_ready: int
    cdac_ready: int
    timing_passed: int
    minimum_logic_setup_s: float
    minimum_cdac_setup_s: float


# Comparator analyses


@dataclass(frozen=True, slots=True)
class AnalysisCompOffsetNoise(Analysis):
    """Comparator decision probability, offset, and input-referred noise at one common mode."""

    vin_cm_v: float
    vin_diff_v: np.ndarray
    decision_probability: np.ndarray
    trial_count: np.ndarray
    offset_v: float
    noise_sigma_v: float
    decision_polarity: Literal[-1, 1]
    validity: Literal["valid", "unbracketed", "non_monotonic"]


@dataclass(frozen=True, slots=True)
class AnalysisCompCommonMode(Analysis):
    """Comparator offset, noise, and validity across input common modes.

    ``stuck-low`` and ``stuck-high`` mark a curve pinned below 0.1 or above 0.9
    probability whose expected transition, given by a valid neighboring common
    mode's offset, lies inside its swept input range.
    """

    vin_cm_v: np.ndarray
    offset_v: np.ndarray
    noise_sigma_v: np.ndarray
    validity: tuple[Literal["valid", "unbracketed", "non_monotonic", "stuck-low", "stuck-high"], ...]


@dataclass(frozen=True, slots=True)
class AnalysisCompTiming(Analysis):
    """Comparator timing and metastability results across measurements."""

    source_index: np.ndarray
    trial_index: np.ndarray
    clock_to_decision_s: np.ndarray
    settling_s: np.ndarray
    unresolved: np.ndarray


@dataclass(frozen=True, slots=True)
class AnalysisCompPower(Analysis):
    """Comparator average consumed power per measurement."""

    source_index: np.ndarray
    supply_v: np.ndarray
    average_power_w: np.ndarray
    energy_per_decision_j: np.ndarray


@dataclass(frozen=True, slots=True)
class AnalysisCompCandidate(Analysis):
    """Noise, power, and settling summary of one generated comparator candidate."""

    candidate_id: str
    candidate_label: str
    size_profile: Literal["half", "double", "fabricated"]
    validity: Literal["valid", "unbracketed", "non_monotonic"]
    topology_index: int
    total_width_units: int
    total_active_area_units: int
    total_active_area_um2: float
    device_count: int
    geometry_signature: str
    offset_v: float
    noise_sigma_v: float
    average_power_w: float
    energy_per_decision_j: float
    maximum_clock_to_decision_s: float
    maximum_settling_s: float
    unresolved_fraction: float


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
