"""The ADC's analysis results (``flow.adc.analysis``), pure data: a capture's transfer and
linearity, its ramp and code statistics, its noise and the noise's spectrum, an interferer and the
operating conditions, its dynamic performance and power, its internal waveforms and timing closure,
the weights a calibration gives (``AnalysisCalibration``, the extracted weights' type; each
calibration's own type a subclass of it), the noise over the input, Hsu's integrated error over the
rate, and an array's predicted mismatch.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal

import numpy as np

from flow.analysis import calc
from flow.pipeline import Analysis

from .sim import AdcSequence


@dataclass(frozen=True, slots=True)
class AnalysisTransfer(Analysis):
    """Mean static transfer and dispersion at each differential input."""

    vin_diff_v: np.ndarray
    mean_dout: np.ndarray
    std_dout: np.ndarray
    sample_count: np.ndarray


@dataclass(frozen=True, slots=True)
class AnalysisEndpointNonlinearity(Analysis):
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
class AnalysisCodeDensityNonlinearity(Analysis):
    """Code-density INL and DNL from a uniformly distributed input.

    ``retained_sample_count`` records how many conversions remained after the
    ramp-wrap exclusion supplied by an :class:`AnalysisRamp`, if any. The
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
class AnalysisCalibration(Analysis):
    """Common output of each per-decision digital calibration method: the extracted weights' type,
    and each calibration's own (``AnalysisCalibration1`` to ``AnalysisCalibration3``) a subclass.

    Coefficients are chronological B0..B(n-1): one per switched capacitor plus
    the terminal decision. All methods normalize these coefficients to the
    inclusive ADC output range, so a corrected fractional code is simply
    ``BOUT @ calibrated_weights``. ``measured_weight_mask`` distinguishes
    directly measured or fitted coefficients from nominally preserved ones.
    """

    method: Literal["extracted", "calibration1", "calibration2", "calibration3"]
    label: str
    code_max: int
    nominal_weights: np.ndarray
    calibrated_weights: np.ndarray
    measured_weight_mask: np.ndarray
    training_sample_count: int
    validation_sample_count: int
    output_gain: float
    output_offset_lsb: float


@dataclass(frozen=True, slots=True)
class AnalysisCalibration1(AnalysisCalibration):
    """Calibration 1's weights: the CDAC S-curves' capacitor movements (``analyze_calibration1``)."""


@dataclass(frozen=True, slots=True)
class AnalysisCalibration2(AnalysisCalibration):
    """Calibration 2's weights: a least-squares fit to a known ramp (``analyze_calibration2``)."""


@dataclass(frozen=True, slots=True)
class AnalysisCalibration3(AnalysisCalibration):
    """Calibration 3's weights: Hsu's slow-ramp decision thresholds (``analyze_calibration3``)."""


@dataclass(frozen=True, slots=True)
class AnalysisRamp(Analysis):
    """One DOUT decoding of a repeated ramp capture, reconstructed against the ramp phase.

    The ramp period in conversions comes from the PWL source and the sample
    rate; only the wrap phase is fitted, from the stored nominal DOUT, so every
    decoding of the same capture shares it. ``retained`` is the single
    definition of which conversions are far enough from a wrap to be used;
    calibrations and code-density nonlinearity reuse it. ``decoding`` is the
    nominal DOUT or the calibration whose weights decoded the stored BOUT.
    """

    decoding: Literal["uncalibrated_dout", "extracted", "calibration1", "calibration2", "calibration3"]
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
class AnalysisCodeDistribution(Analysis):
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
class AnalysisNoise(Analysis):
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
class AnalysisCodeSpectrum(Analysis):
    """Noise spectrum of one fixed-input capture's output codes, sampled at the conversion rate.

    ``psd_lsb2_per_hz`` is the one-sided Welch density of the codes about
    ``mean_dout``. ``white_floor_lsb2_per_hz`` is its median above DC, a robust
    estimate of the broadband level that narrow interference lines do not
    move. ``line_mask`` marks the bins that stand clearly above that floor.
    The variance splits into the narrowband excess above the floor in those
    bins and the broadband remainder: total² = narrowband² + broadband².
    ``narrowband_dout`` is the capture's code sequence with only the line
    frequencies kept, the interference as it appears in the codes.
    ``input_lsb_v`` refers the spectrum to the ADC input, so it compares
    directly with probe spectra in V/√Hz. ``decoding`` records which weights
    produced the codes: the stored DOUT, or a calibration's decoded BOUT.
    """

    decoding: Literal["uncalibrated_dout", "extracted", "calibration1", "calibration2", "calibration3"]
    sequence: AdcSequence
    symbol_rate_hz: float
    sample_rate_hz: float
    input_lsb_v: float
    mean_dout: float
    frequency_hz: np.ndarray
    psd_lsb2_per_hz: np.ndarray
    white_floor_lsb2_per_hz: float
    line_mask: np.ndarray
    narrowband_dout: np.ndarray

    @property
    def asd_lsb_per_sqrt_hz(self) -> np.ndarray:
        return np.sqrt(self.psd_lsb2_per_hz)

    @property
    def asd_v_per_sqrt_hz(self) -> np.ndarray:
        """Return the code spectrum referred to the ADC input through the nominal LSB."""

        return self.asd_lsb_per_sqrt_hz * self.input_lsb_v

    @property
    def spectrum_valid(self) -> bool:
        """A stuck capture repeats one code and has no measurable floor."""

        return self.white_floor_lsb2_per_hz > 0.0

    @property
    def bin_hz(self) -> float:
        return float(self.frequency_hz[1] - self.frequency_hz[0])

    @property
    def cumulative_rms_lsb(self) -> np.ndarray:
        """Return the RMS code noise integrated from DC up to each frequency."""

        return np.sqrt(np.cumsum(self.psd_lsb2_per_hz) * self.bin_hz)

    @property
    def total_rms_lsb(self) -> float:
        return float(self.cumulative_rms_lsb[-1])

    @property
    def narrowband_rms_lsb(self) -> float:
        excess = np.clip(self.psd_lsb2_per_hz - self.white_floor_lsb2_per_hz, 0.0, None)
        return math.sqrt(float(np.sum(excess[self.line_mask])) * self.bin_hz)

    @property
    def broadband_rms_lsb(self) -> float:
        return math.sqrt(max(self.total_rms_lsb**2 - self.narrowband_rms_lsb**2, 0.0))

    @property
    def peak_frequency_hz(self) -> float:
        """Return the frequency of the strongest bin above DC."""

        return float(self.frequency_hz[1:][np.argmax(self.psd_lsb2_per_hz[1:])])

    @property
    def peak_to_floor(self) -> float:
        if not self.spectrum_valid:
            return math.nan
        return float(np.max(self.psd_lsb2_per_hz[1:]) / self.white_floor_lsb2_per_hz)


@dataclass(frozen=True, slots=True)
class AnalysisInterferer(Analysis):
    """True frequency of one periodic interferer seen in one ADC's codes at several rates.

    Each conversion rate folds the interferer to a different apparent
    frequency. ``score_db`` rates every candidate true frequency by how far the
    code spectra stand above their floors at that candidate's aliases: per
    rate, the mean over its captures; then summed over rates. Candidates span
    zero to half the rates' common period in frequency, beyond which the
    aliases repeat or mirror. ``observed_peak_hz`` is the median strongest
    line per rate. Stuck captures without a floor are excluded and counted.
    """

    sample_rate_hz: np.ndarray
    observed_peak_hz: np.ndarray
    candidate_frequency_hz: np.ndarray
    score_db: np.ndarray
    excluded_capture_count: int

    @property
    def frequency_hz(self) -> float:
        return float(self.candidate_frequency_hz[np.argmax(self.score_db)])

    @property
    def folded_frequency_hz(self) -> np.ndarray:
        """Return the apparent frequency of every candidate at every rate (rate × candidate)."""

        rate = self.sample_rate_hz[:, None]
        return np.abs((self.candidate_frequency_hz[None, :] + rate / 2.0) % rate - rate / 2.0)


@dataclass(frozen=True, slots=True)
class AnalysisOperatingConditions(Analysis):
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
class AnalysisDynamic(Analysis):
    """Sine-fit, residual, spectrum, and dynamic ADC figures of merit.

    The residual tail limit is a multiple of the fitted residual RMS, and the
    expected tail count is the matching two-sided Gaussian tail probability.

    Three ENOBs: ``spectral_enob_bits`` is (SNDR - 1.76) / 6.02 at the test
    sine's own amplitude, as Virtuoso's spectrumMeas reports it, so an ideal
    N-bit quantizer reads N - |amplitude_dbfs| / 6.02 there (N - 0.08 for a
    -0.5 dBFS sine). ``spectral_enob_fs_bits`` refers the same SNDR to a
    full-scale sine and reads N for it. ``enob_bits`` is the time-domain
    ENOB of the fit residual, at the test amplitude like the first.
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
    def spectral_enob_fs_bits(self) -> float:
        """Return the spectral ENOB referred to full scale.

        This is the spectral SNDR plus the fitted sine's distance below full
        scale (the code range, ``amplitude_dbfs``), so (SNDR - amplitude_dbfs
        - 1.76) / 6.02: the noise and distortion against a full-scale sine,
        IEEE Std 1241's ENOB. A converter whose gain fell is not penalized
        here; ``amplitude_dbfs`` shows that. Without a fitted sine it is -inf.
        """

        if self.amplitude_dout == 0.0:
            return -math.inf
        return (self.spectral_sndr_db - self.amplitude_dbfs - 1.76) / 6.02

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
class AnalysisPower(Analysis):
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
class AnalysisPowerWaveform(Analysis):
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
class AnalysisSamplingNoise(Analysis):
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
class AnalysisCdacSettling(Analysis):
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
class AnalysisDecisionPaths(Analysis):
    """Running SAR estimates reconstructed from every captured decision record."""

    conversion_index: np.ndarray
    final_dout: np.ndarray
    bout: np.ndarray
    weights: np.ndarray
    estimate_dout: np.ndarray


@dataclass(frozen=True, slots=True)
class AnalysisTimingClosure(Analysis):
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
class AnalysisTimingSummary(Analysis):
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


@dataclass(frozen=True, slots=True, kw_only=True)
class AnalysisInputNoise(Analysis):
    """The output code's noise over the input: a staircase capture's DC levels (V, differential) and
    the output code's standard deviation at each (LSB)."""

    level_v: np.ndarray
    sigma_lsb: np.ndarray


@dataclass(frozen=True, slots=True, kw_only=True)
class AnalysisHsu(Analysis):
    """Hsu's study: at each conversion rate (Hz) the integrated error sum_k |code_k - reference_k|
    (LSB) of a ramp through every code centre against the same inputs at ideal timing."""

    rate_hz: np.ndarray
    integrated_error_lsb: np.ndarray


@dataclass(frozen=True, slots=True, kw_only=True)
class AnalysisMismatch(Analysis):
    """An array's mismatch statistics at a Pelgrom coefficient of 1 (every sigma scales with A):
    by stage (C0 first) and by code (1 to code_max - 1), and the distinct code widths the worst
    DNL and the missing codes are over. ``analyze_mismatch`` derives them from a capture's nominal
    array; ``flow.adc.analysis`` predicts from them the worst DNL and INL, the missing codes and
    each stage's margin over its sigma at a coefficient A (a fraction: 0.001 is 0.1 %·sqrt(fF))."""

    weight_sigma: np.ndarray  # each stage's step on one side (LSB)
    transition_sigma: np.ndarray  # the largest DNL sigma of a code that stage's decision bounds (LSB)
    margin_lsb: np.ndarray  # each stage's redundancy margin (Ogawa et al.), at the design weights
    margin_sigma: np.ndarray  # the margin's own sigma: stage k's step and every later one's (LSB)
    gamma_error: np.ndarray  # each stage's step on both sides less its decoder weight, gain off (LSB)
    gamma_sigma: np.ndarray  # and its sigma
    dnl_mean: np.ndarray  # the nominal array's DNL by code (its own error against the design weights)
    dnl_sigma: np.ndarray
    inl_mean: np.ndarray
    inl_sigma: np.ndarray
    width_mean: np.ndarray  # by distinct width: its nominal width (LSB), sigma and how many codes
    width_sigma: np.ndarray
    width_dnl_sigma: np.ndarray  # the same as DNL: the mean width and the gain taken off
    width_codes: np.ndarray
