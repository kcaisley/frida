"""Typed measurement and analysis data exchanged by FRIDA post-processing."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Literal

import numpy as np
from numpy.typing import NDArray

from flow.cdac.testbench import CdacTbParams
from flow.comp.testbench import CompTbParams
from flow.samp.testbench import SampTbParams
from flow.scans.params import AdcTbParams

type Backend = Literal["physical", "behavioral", "spice"]
type InfoValue = str | int | float | bool
type FloatArray = NDArray[np.float64]
type IntArray = NDArray[np.int64]
type Uint8Array = NDArray[np.uint8]
type Uint32Array = NDArray[np.uint32]


def _array_1d(values, dtype, name: str, *, finite: bool = False) -> np.ndarray:
    """Return one canonical one-dimensional array."""

    array = np.ascontiguousarray(values, dtype=dtype)
    if array.ndim != 1:
        raise ValueError(f"{name} must be one-dimensional, got shape {array.shape}")
    if finite and not np.all(np.isfinite(array)):
        raise ValueError(f"{name} contains non-finite values")
    return array


def _array_2d(values, dtype, name: str, *, finite: bool = False) -> np.ndarray:
    """Return one canonical two-dimensional array."""

    array = np.ascontiguousarray(values, dtype=dtype)
    if array.ndim != 2:
        raise ValueError(f"{name} must be two-dimensional, got shape {array.shape}")
    if finite and not np.all(np.isfinite(array)):
        raise ValueError(f"{name} contains non-finite values")
    return array


def _aligned_length(fields: dict[str, np.ndarray]) -> int:
    """Validate aligned leading dimensions and return their common length."""

    lengths = {name: len(value) for name, value in fields.items()}
    if len(set(lengths.values())) != 1:
        raise ValueError(f"DAQ fields are not aligned: {lengths}")
    return next(iter(lengths.values()), 0)


def _normalize_wave(
    conversion_index,
    time_s,
    signals: dict[str, np.ndarray],
) -> tuple[IntArray, FloatArray, dict[str, FloatArray]]:
    """Normalize one dense waveform record collection."""

    indices = _array_1d(conversion_index, np.int64, "wave.conversion_index")
    times = _array_1d(time_s, np.float64, "wave.time_s", finite=True)
    if len(indices) == 0:
        raise ValueError("wave must contain at least one record")
    if len(times) < 2 or np.any(np.diff(times) <= 0):
        raise ValueError("wave.time_s must contain at least two strictly increasing samples")

    normalized = {}
    expected_shape = (len(indices), len(times))
    for name, values in signals.items():
        signal = _array_2d(values, np.float64, f"wave.{name}", finite=True)
        if signal.shape != expected_shape:
            raise ValueError(f"wave.{name} has shape {signal.shape}, expected {expected_shape}")
        normalized[name] = signal
    return indices, times, normalized


def _validate_measurement(info: MeasInfo, expected_type: str, daq_indices: IntArray, wave_indices: IntArray) -> None:
    """Validate one measurement's type and waveform-to-DAQ mapping."""

    if info.measurement_type != expected_type:
        raise ValueError(f"{expected_type} requires info.measurement_type={expected_type!r}")
    missing = wave_indices[~np.isin(wave_indices, daq_indices)]
    if len(missing):
        raise ValueError(f"wave references conversion/trial indices absent from DAQ: {np.unique(missing).tolist()}")


@dataclass(frozen=True, slots=True)
class MeasInfo:
    """Small run information shared by every measurement type."""

    schema_version: int
    measurement_type: str
    backend: Backend
    timestamp_utc: datetime
    instruments: dict[str, str] = field(default_factory=dict)
    readbacks: dict[str, InfoValue] = field(default_factory=dict)
    source_path: Path | None = None

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError(f"unsupported measurement schema version {self.schema_version}")
        if not self.measurement_type:
            raise ValueError("measurement_type must not be empty")
        if self.backend not in ("physical", "behavioral", "spice"):
            raise ValueError(f"unsupported backend {self.backend!r}")
        if self.timestamp_utc.tzinfo is None:
            raise ValueError("timestamp_utc must be timezone-aware")
        if any(
            not isinstance(name, str) or not isinstance(identity, str) for name, identity in self.instruments.items()
        ):
            raise ValueError("info.instruments must map strings to strings")
        if any(
            not isinstance(name, str) or not isinstance(value, (str, int, float, bool))
            for name, value in self.readbacks.items()
        ):
            raise ValueError("info.readbacks must contain only scalar strings, numbers, and booleans")
        object.__setattr__(self, "instruments", dict(self.instruments))
        object.__setattr__(self, "readbacks", dict(self.readbacks))
        if self.source_path is not None:
            object.__setattr__(self, "source_path", Path(self.source_path))


@dataclass(frozen=True, slots=True)
class AdcDaq:
    """ADC conversion readback shared by external and internal measurements."""

    conversion_index: IntArray
    bout: Uint8Array
    dout_raw: IntArray
    dout: IntArray
    vin_diff_v: FloatArray
    fastrx_word: Uint32Array | None = None

    def __post_init__(self) -> None:
        conversion_index = _array_1d(self.conversion_index, np.int64, "daq.conversion_index")
        bout = _array_2d(self.bout, np.uint8, "daq.bout")
        dout_raw = _array_1d(self.dout_raw, np.int64, "daq.dout_raw")
        dout = _array_1d(self.dout, np.int64, "daq.dout")
        vin_diff_v = _array_1d(self.vin_diff_v, np.float64, "daq.vin_diff_v", finite=True)
        if bout.shape[1:] != (17,):
            raise ValueError(f"daq.bout must have shape (N, 17), got {bout.shape}")
        if np.any((bout != 0) & (bout != 1)):
            raise ValueError("daq.bout values must be zero or one")
        fields = {
            "conversion_index": conversion_index,
            "bout": bout,
            "dout_raw": dout_raw,
            "dout": dout,
            "vin_diff_v": vin_diff_v,
        }
        fastrx_word = None
        if self.fastrx_word is not None:
            fastrx_word = _array_1d(self.fastrx_word, np.uint32, "daq.fastrx_word")
            fields["fastrx_word"] = fastrx_word
        if _aligned_length(fields) == 0:
            raise ValueError("ADC DAQ must contain at least one conversion")
        object.__setattr__(self, "conversion_index", conversion_index)
        object.__setattr__(self, "bout", bout)
        object.__setattr__(self, "dout_raw", dout_raw)
        object.__setattr__(self, "dout", dout)
        object.__setattr__(self, "vin_diff_v", vin_diff_v)
        object.__setattr__(self, "fastrx_word", fastrx_word)


@dataclass(frozen=True, slots=True)
class AdcExtWave:
    """Externally observable ADC waveforms."""

    conversion_index: IntArray
    time_s: FloatArray
    vin_diff_v: FloatArray
    seq_comp_v: FloatArray
    seq_logic_v: FloatArray
    comp_out_v: FloatArray

    def __post_init__(self) -> None:
        indices, times, signals = _normalize_wave(
            self.conversion_index,
            self.time_s,
            {
                "vin_diff_v": self.vin_diff_v,
                "seq_comp_v": self.seq_comp_v,
                "seq_logic_v": self.seq_logic_v,
                "comp_out_v": self.comp_out_v,
            },
        )
        object.__setattr__(self, "conversion_index", indices)
        object.__setattr__(self, "time_s", times)
        for name, values in signals.items():
            object.__setattr__(self, name, values)


@dataclass(frozen=True, slots=True)
class AdcIntWave:
    """Internally observable ADC waveforms from simulation."""

    conversion_index: IntArray
    time_s: FloatArray
    vin_p_v: FloatArray
    vin_n_v: FloatArray
    seq_init_v: FloatArray
    seq_samp_v: FloatArray
    seq_comp_v: FloatArray
    seq_logic_v: FloatArray
    comp_out_v: FloatArray
    vdac_p_v: FloatArray
    vdac_n_v: FloatArray
    clk_samp_p_v: FloatArray
    clk_samp_n_v: FloatArray
    clk_comp_v: FloatArray
    comp_out_p_v: FloatArray
    comp_out_n_v: FloatArray
    vdd_a_i: FloatArray
    vdd_d_i: FloatArray
    vdd_dac_i: FloatArray

    def __post_init__(self) -> None:
        signal_names = tuple(
            field_name for field_name in self.__dataclass_fields__ if field_name not in {"conversion_index", "time_s"}
        )
        indices, times, signals = _normalize_wave(
            self.conversion_index,
            self.time_s,
            {name: getattr(self, name) for name in signal_names},
        )
        object.__setattr__(self, "conversion_index", indices)
        object.__setattr__(self, "time_s", times)
        for name, values in signals.items():
            object.__setattr__(self, name, values)


@dataclass(frozen=True, slots=True)
class MeasAdcExt:
    """ADC measurement through its external stimulus and digital readout."""

    info: MeasInfo
    param: AdcTbParams
    daq: AdcDaq
    wave: AdcExtWave

    def __post_init__(self) -> None:
        if self.param.conversions != len(self.daq.conversion_index):
            raise ValueError(
                f"param.conversions={self.param.conversions} does not match {len(self.daq.conversion_index)} ADC rows"
            )
        _validate_measurement(self.info, type(self).__name__, self.daq.conversion_index, self.wave.conversion_index)


@dataclass(frozen=True, slots=True)
class MeasAdcInt:
    """ADC measurement with internal simulation waveforms."""

    info: MeasInfo
    param: AdcTbParams
    daq: AdcDaq
    wave: AdcIntWave

    def __post_init__(self) -> None:
        if self.daq.fastrx_word is not None:
            raise ValueError("MeasAdcInt must not invent FastRX words")
        if self.param.conversions != len(self.daq.conversion_index):
            raise ValueError(
                f"param.conversions={self.param.conversions} does not match {len(self.daq.conversion_index)} ADC rows"
            )
        _validate_measurement(self.info, type(self).__name__, self.daq.conversion_index, self.wave.conversion_index)


@dataclass(frozen=True, slots=True)
class CompDaq:
    """Comparator trial conditions and binary decisions."""

    trial_index: IntArray
    vin_diff_v: FloatArray
    vin_cm_v: FloatArray
    decision: Uint8Array

    def __post_init__(self) -> None:
        trial_index = _array_1d(self.trial_index, np.int64, "daq.trial_index")
        vin_diff_v = _array_1d(self.vin_diff_v, np.float64, "daq.vin_diff_v", finite=True)
        vin_cm_v = _array_1d(self.vin_cm_v, np.float64, "daq.vin_cm_v", finite=True)
        decision = _array_1d(self.decision, np.uint8, "daq.decision")
        if np.any((decision != 0) & (decision != 1)):
            raise ValueError("daq.decision values must be zero or one")
        if (
            _aligned_length(
                {
                    "trial_index": trial_index,
                    "vin_diff_v": vin_diff_v,
                    "vin_cm_v": vin_cm_v,
                    "decision": decision,
                }
            )
            == 0
        ):
            raise ValueError("comparator DAQ must contain at least one trial")
        object.__setattr__(self, "trial_index", trial_index)
        object.__setattr__(self, "vin_diff_v", vin_diff_v)
        object.__setattr__(self, "vin_cm_v", vin_cm_v)
        object.__setattr__(self, "decision", decision)


@dataclass(frozen=True, slots=True)
class CompExtWave:
    """Externally observable comparator waveforms."""

    trial_index: IntArray
    time_s: FloatArray
    vin_diff_v: FloatArray
    seq_comp_v: FloatArray
    comp_out_v: FloatArray

    def __post_init__(self) -> None:
        indices, times, signals = _normalize_wave(
            self.trial_index,
            self.time_s,
            {
                "vin_diff_v": self.vin_diff_v,
                "seq_comp_v": self.seq_comp_v,
                "comp_out_v": self.comp_out_v,
            },
        )
        object.__setattr__(self, "trial_index", indices)
        object.__setattr__(self, "time_s", times)
        for name, values in signals.items():
            object.__setattr__(self, name, values)


@dataclass(frozen=True, slots=True)
class CompIntWave:
    """Internally observable comparator waveforms."""

    trial_index: IntArray
    time_s: FloatArray
    vin_p_v: FloatArray
    vin_n_v: FloatArray
    clock_v: FloatArray
    vout_p_v: FloatArray
    vout_n_v: FloatArray
    comp_p_v: FloatArray
    comp_n_v: FloatArray
    vdd_i: FloatArray

    def __post_init__(self) -> None:
        signal_names = tuple(
            field_name for field_name in self.__dataclass_fields__ if field_name not in {"trial_index", "time_s"}
        )
        indices, times, signals = _normalize_wave(
            self.trial_index,
            self.time_s,
            {name: getattr(self, name) for name in signal_names},
        )
        object.__setattr__(self, "trial_index", indices)
        object.__setattr__(self, "time_s", times)
        for name, values in signals.items():
            object.__setattr__(self, name, values)


@dataclass(frozen=True, slots=True)
class MeasCompExt:
    """Comparator measurement through external stimulus and decisions."""

    info: MeasInfo
    param: CompTbParams
    daq: CompDaq
    wave: CompExtWave

    def __post_init__(self) -> None:
        _validate_measurement(self.info, type(self).__name__, self.daq.trial_index, self.wave.trial_index)


@dataclass(frozen=True, slots=True)
class MeasCompInt:
    """Comparator measurement with internal simulation waveforms."""

    info: MeasInfo
    param: CompTbParams
    daq: CompDaq
    wave: CompIntWave

    def __post_init__(self) -> None:
        _validate_measurement(self.info, type(self).__name__, self.daq.trial_index, self.wave.trial_index)


@dataclass(frozen=True, slots=True)
class SampDaq:
    """Sampler trial identifiers."""

    trial_index: IntArray

    def __post_init__(self) -> None:
        trial_index = _array_1d(self.trial_index, np.int64, "daq.trial_index")
        if len(trial_index) == 0:
            raise ValueError("sampler DAQ must contain at least one trial")
        object.__setattr__(self, "trial_index", trial_index)


@dataclass(frozen=True, slots=True)
class SampIntWave:
    """Internally observable sampler waveforms."""

    trial_index: IntArray
    time_s: FloatArray
    vin_v: FloatArray
    sampled_v: FloatArray
    clk_v: FloatArray
    clk_b_v: FloatArray
    vdd_i: FloatArray

    def __post_init__(self) -> None:
        signal_names = tuple(
            field_name for field_name in self.__dataclass_fields__ if field_name not in {"trial_index", "time_s"}
        )
        indices, times, signals = _normalize_wave(
            self.trial_index,
            self.time_s,
            {name: getattr(self, name) for name in signal_names},
        )
        object.__setattr__(self, "trial_index", indices)
        object.__setattr__(self, "time_s", times)
        for name, values in signals.items():
            object.__setattr__(self, name, values)


@dataclass(frozen=True, slots=True)
class MeasSampInt:
    """Sampler measurement with internal simulation waveforms."""

    info: MeasInfo
    param: SampTbParams
    daq: SampDaq
    wave: SampIntWave

    def __post_init__(self) -> None:
        _validate_measurement(self.info, type(self).__name__, self.daq.trial_index, self.wave.trial_index)


@dataclass(frozen=True, slots=True)
class DacExtDaq:
    """External CDAC trial conditions and comparator decisions."""

    trial_index: IntArray
    dac_state_p: Uint8Array
    dac_state_n: Uint8Array
    vin_diff_v: FloatArray
    decision: Uint8Array

    def __post_init__(self) -> None:
        trial_index = _array_1d(self.trial_index, np.int64, "daq.trial_index")
        dac_state_p = _array_2d(self.dac_state_p, np.uint8, "daq.dac_state_p")
        dac_state_n = _array_2d(self.dac_state_n, np.uint8, "daq.dac_state_n")
        vin_diff_v = _array_1d(self.vin_diff_v, np.float64, "daq.vin_diff_v", finite=True)
        decision = _array_1d(self.decision, np.uint8, "daq.decision")
        for name, state in (("dac_state_p", dac_state_p), ("dac_state_n", dac_state_n)):
            if state.shape[1:] != (16,) or np.any((state != 0) & (state != 1)):
                raise ValueError(f"daq.{name} must have shape (N, 16) and contain only zero or one")
        if np.any((decision != 0) & (decision != 1)):
            raise ValueError("daq.decision values must be zero or one")
        if (
            _aligned_length(
                {
                    "trial_index": trial_index,
                    "dac_state_p": dac_state_p,
                    "dac_state_n": dac_state_n,
                    "vin_diff_v": vin_diff_v,
                    "decision": decision,
                }
            )
            == 0
        ):
            raise ValueError("external CDAC DAQ must contain at least one trial")
        object.__setattr__(self, "trial_index", trial_index)
        object.__setattr__(self, "dac_state_p", dac_state_p)
        object.__setattr__(self, "dac_state_n", dac_state_n)
        object.__setattr__(self, "vin_diff_v", vin_diff_v)
        object.__setattr__(self, "decision", decision)


@dataclass(frozen=True, slots=True)
class DacIntDaq:
    """Internal CDAC trial identifiers and input states."""

    trial_index: IntArray
    dac_state_p: Uint8Array
    dac_state_n: Uint8Array

    def __post_init__(self) -> None:
        trial_index = _array_1d(self.trial_index, np.int64, "daq.trial_index")
        dac_state_p = _array_2d(self.dac_state_p, np.uint8, "daq.dac_state_p")
        dac_state_n = _array_2d(self.dac_state_n, np.uint8, "daq.dac_state_n")
        for name, state in (("dac_state_p", dac_state_p), ("dac_state_n", dac_state_n)):
            if state.shape[1:] != (16,) or np.any((state != 0) & (state != 1)):
                raise ValueError(f"daq.{name} must have shape (N, 16) and contain only zero or one")
        if _aligned_length({"trial_index": trial_index, "dac_state_p": dac_state_p, "dac_state_n": dac_state_n}) == 0:
            raise ValueError("internal CDAC DAQ must contain at least one trial")
        object.__setattr__(self, "trial_index", trial_index)
        object.__setattr__(self, "dac_state_p", dac_state_p)
        object.__setattr__(self, "dac_state_n", dac_state_n)


@dataclass(frozen=True, slots=True)
class DacExtWave:
    """Externally observable CDAC comparator-path waveforms."""

    trial_index: IntArray
    time_s: FloatArray
    vin_diff_v: FloatArray
    seq_comp_v: FloatArray
    comp_out_v: FloatArray

    def __post_init__(self) -> None:
        indices, times, signals = _normalize_wave(
            self.trial_index,
            self.time_s,
            {
                "vin_diff_v": self.vin_diff_v,
                "seq_comp_v": self.seq_comp_v,
                "comp_out_v": self.comp_out_v,
            },
        )
        object.__setattr__(self, "trial_index", indices)
        object.__setattr__(self, "time_s", times)
        for name, values in signals.items():
            object.__setattr__(self, name, values)


@dataclass(frozen=True, slots=True)
class DacIntWave:
    """Internally observable CDAC waveforms."""

    trial_index: IntArray
    time_s: FloatArray
    vdac_p_v: FloatArray
    vdac_n_v: FloatArray
    update_v: FloatArray
    vdd_i: FloatArray

    def __post_init__(self) -> None:
        signal_names = tuple(
            field_name for field_name in self.__dataclass_fields__ if field_name not in {"trial_index", "time_s"}
        )
        indices, times, signals = _normalize_wave(
            self.trial_index,
            self.time_s,
            {name: getattr(self, name) for name in signal_names},
        )
        object.__setattr__(self, "trial_index", indices)
        object.__setattr__(self, "time_s", times)
        for name, values in signals.items():
            object.__setattr__(self, name, values)


@dataclass(frozen=True, slots=True)
class MeasDacExt:
    """CDAC measurement inferred through the external comparator path."""

    info: MeasInfo
    param: CdacTbParams
    daq: DacExtDaq
    wave: DacExtWave

    def __post_init__(self) -> None:
        _validate_measurement(self.info, type(self).__name__, self.daq.trial_index, self.wave.trial_index)


@dataclass(frozen=True, slots=True)
class MeasDacInt:
    """CDAC measurement with internal simulation waveforms."""

    info: MeasInfo
    param: CdacTbParams
    daq: DacIntDaq
    wave: DacIntWave

    def __post_init__(self) -> None:
        _validate_measurement(self.info, type(self).__name__, self.daq.trial_index, self.wave.trial_index)


type Measurement = MeasAdcExt | MeasAdcInt | MeasCompExt | MeasCompInt | MeasSampInt | MeasDacExt | MeasDacInt


# =============================================================================
# Typed analysis results
# =============================================================================


@dataclass(frozen=True, slots=True)
class AnalysisAdcTransfer:
    """Mean static transfer and dispersion at each differential input."""

    vin_diff_v: FloatArray
    mean_dout: FloatArray
    std_dout: FloatArray
    sample_count: IntArray


@dataclass(frozen=True, slots=True)
class AnalysisAdcNonlin:
    """Endpoint or code-density ADC nonlinearity."""

    method: Literal["endpoint", "code_density"]
    code: IntArray
    dnl: FloatArray
    inl: FloatArray
    count: IntArray | None
    transition_vin_diff_v: FloatArray | None
    ideal_count: float | None
    endpoint_lsb_v: float | None
    maximum_abs_dnl: float
    maximum_abs_inl: float
    missing_codes: int


@dataclass(frozen=True, slots=True)
class AnalysisAdcNoise:
    """Code statistics and histograms for one or more static input points."""

    vin_diff_v: FloatArray
    sample_count: IntArray
    mean_dout: FloatArray
    std_dout: FloatArray
    minimum_dout: IntArray
    maximum_dout: IntArray
    code: IntArray
    count: IntArray


@dataclass(frozen=True, slots=True)
class AnalysisAdcNoiseSweep:
    """Fixed-input output variation across conversion timing settings."""

    sample_rate_hz: FloatArray
    logic_phase_delay_symbols: FloatArray
    comparator_time_percent: FloatArray
    input_lsb_v: float
    input_referred_noise_rms_v: FloatArray
    mean_dout: FloatArray
    std_dout: FloatArray
    minimum_dout: IntArray
    maximum_dout: IntArray
    bit_mismatches: IntArray


@dataclass(frozen=True, slots=True)
class AnalysisAdcDynamic:
    """Sine-fit, residual, spectrum, and dynamic ADC figures of merit."""

    sample_rate_hz: float
    input_frequency_hz: float
    fitted_frequency_hz: float
    sample_count: int
    adc_bits: int
    offset_dout: float
    amplitude_dout: float
    phase_rad: float
    amplitude_dbfs: float
    signal_rms_dout: float
    residual_rms_dout: float
    input_referred_noise_rms_v: float
    input_referred_residual_rms_v: float
    sinad_db: float
    enob_bits: float
    spectral_sndr_db: float
    spectral_snr_db: float
    spectral_thd_db: float
    spectral_sfdr_db: float
    spectral_enob_bits: float
    residual_tail_limit_dout: float
    expected_residual_tail_count: float
    negative_residual_tail_count: int
    positive_residual_tail_count: int
    maximum_abs_residual_dout: float
    time_s: FloatArray
    measured_dout: FloatArray
    fitted_dout: FloatArray
    residual_dout: FloatArray
    spectrum_frequency_hz: FloatArray
    spectrum_dbfs: FloatArray


@dataclass(frozen=True, slots=True)
class AnalysisAdcDynamicSweep:
    """Dynamic ADC figures of merit across input and conversion rates."""

    input_frequency_hz: FloatArray
    sample_rate_hz: FloatArray
    active_conversion_rate_hz: FloatArray
    observed_adc: IntArray
    logic_phase_delay_symbols: FloatArray
    input_referred_noise_rms_v: FloatArray
    input_referred_residual_rms_v: FloatArray
    spectral_enob_bits: FloatArray
    spectral_sndr_db: FloatArray
    spectral_snr_db: FloatArray
    spectral_thd_db: FloatArray
    spectral_sfdr_db: FloatArray
    residual_tail_limit_dout: float
    expected_residual_tail_count: FloatArray
    negative_residual_tail_count: IntArray
    positive_residual_tail_count: IntArray
    maximum_abs_residual_dout: FloatArray


@dataclass(frozen=True, slots=True)
class AnalysisAdcPowerSweep:
    """Active ADC supply power across conversion rates."""

    sample_rate_hz: FloatArray
    active_conversion_rate_hz: FloatArray
    observed_adc: IntArray
    vdd_a_power_w: FloatArray
    vdd_d_power_w: FloatArray
    vdd_dac_power_w: FloatArray
    total_power_w: FloatArray


@dataclass(frozen=True, slots=True)
class AnalysisAdcDecisionPaths:
    """Running SAR estimates reconstructed from selected decision records."""

    selection: Literal["single", "same_dout", "all"]
    conversion_index: IntArray
    final_dout: IntArray
    bout: Uint8Array
    weights: FloatArray
    estimate_dout: FloatArray


@dataclass(frozen=True, slots=True)
class AnalysisCompOffsetNoise:
    """Comparator decision probability, offset, and input-referred noise."""

    vin_diff_v: FloatArray
    decision_probability: FloatArray
    trial_count: IntArray
    offset_v: float
    noise_sigma_v: float


@dataclass(frozen=True, slots=True)
class AnalysisCompTiming:
    """Comparator timing and metastability results across measurements."""

    source_index: IntArray
    trial_index: IntArray
    clock_to_decision_s: FloatArray
    settling_s: FloatArray
    unresolved: Uint8Array


@dataclass(frozen=True, slots=True)
class AnalysisCompPower:
    """Comparator average consumed power per measurement."""

    source_index: IntArray
    supply_v: FloatArray
    average_power_w: FloatArray


MEASUREMENT_TYPES = {
    cls.__name__: cls for cls in (MeasAdcExt, MeasAdcInt, MeasCompExt, MeasCompInt, MeasSampInt, MeasDacExt, MeasDacInt)
}


PARAMETER_TYPES = {
    MeasAdcExt.__name__: AdcTbParams,
    MeasAdcInt.__name__: AdcTbParams,
    MeasCompExt.__name__: CompTbParams,
    MeasCompInt.__name__: CompTbParams,
    MeasSampInt.__name__: SampTbParams,
    MeasDacExt.__name__: CdacTbParams,
    MeasDacInt.__name__: CdacTbParams,
}
