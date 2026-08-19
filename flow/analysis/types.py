"""Typed measurement and analysis data exchanged by FRIDA post-processing."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Literal

import numpy as np
from numpy.typing import NDArray

from flow.cdac.sim import CdacTbParams
from flow.comp.sim import CompTbParams
from flow.samp.sim import SampTbParams
from flow.scans.params import AdcTbParams

type Backend = Literal["physical", "behavioral", "spice"]
type InfoValue = str | int | float | bool
type AdcCalibrationMethod = Literal["calibration1", "calibration2", "calibration3"]
type AdcDecoding = Literal["uncalibrated_dout", "calibration1", "calibration2", "calibration3"]
type FloatArray = NDArray[np.float64]
type IntArray = NDArray[np.int64]
type Uint8Array = NDArray[np.uint8]
type Uint32Array = NDArray[np.uint32]
type BoolArray = NDArray[np.bool_]


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
        if self.schema_version not in (1, 2):
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
    """External and internal ADC waveforms from simulation."""

    conversion_index: IntArray
    time_s: FloatArray
    vin_diff_v: FloatArray
    seq_comp_v: FloatArray
    seq_logic_v: FloatArray
    comp_out_v: FloatArray
    vin_p_v: FloatArray
    vin_n_v: FloatArray
    seq_init_v: FloatArray
    seq_samp_v: FloatArray
    vdac_p_v: FloatArray
    vdac_n_v: FloatArray
    clk_samp_p_v: FloatArray
    clk_samp_p_b_v: FloatArray
    clk_samp_n_v: FloatArray
    clk_samp_n_b_v: FloatArray
    clk_comp_v: FloatArray
    comp_out_p_v: FloatArray
    comp_out_n_v: FloatArray
    dac_state_p_15_v: FloatArray
    dac_state_p_8_v: FloatArray
    dac_state_p_0_v: FloatArray
    dac_state_n_15_v: FloatArray
    dac_state_n_8_v: FloatArray
    dac_state_n_0_v: FloatArray
    dac_botplate_p_15_v: FloatArray
    dac_botplate_p_8_v: FloatArray
    dac_botplate_p_0_v: FloatArray
    dac_botplate_n_15_v: FloatArray
    dac_botplate_n_8_v: FloatArray
    dac_botplate_n_0_v: FloatArray
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


type MeasAdc = MeasAdcExt | MeasAdcInt


@dataclass(frozen=True, slots=True)
class CompDaq:
    """Comparator trial conditions and binary decisions."""

    trial_index: IntArray
    vin_diff_v: FloatArray
    vin_cm_v: FloatArray
    decision: Uint8Array
    fastrx_word: Uint32Array | None = None
    fastrx_frame: Uint32Array | None = None

    def __post_init__(self) -> None:
        trial_index = _array_1d(self.trial_index, np.int64, "daq.trial_index")
        vin_diff_v = _array_1d(self.vin_diff_v, np.float64, "daq.vin_diff_v", finite=True)
        vin_cm_v = _array_1d(self.vin_cm_v, np.float64, "daq.vin_cm_v", finite=True)
        decision = _array_1d(self.decision, np.uint8, "daq.decision")
        if np.any((decision != 0) & (decision != 1)):
            raise ValueError("daq.decision values must be zero or one")
        fields = {
            "trial_index": trial_index,
            "vin_diff_v": vin_diff_v,
            "vin_cm_v": vin_cm_v,
            "decision": decision,
        }
        fastrx_word = None
        fastrx_frame = None
        if self.fastrx_word is not None:
            fastrx_word = _array_1d(self.fastrx_word, np.uint32, "daq.fastrx_word")
            fields["fastrx_word"] = fastrx_word
        if self.fastrx_frame is not None:
            fastrx_frame = _array_1d(self.fastrx_frame, np.uint32, "daq.fastrx_frame")
            fields["fastrx_frame"] = fastrx_frame
        if (fastrx_word is None) != (fastrx_frame is None):
            raise ValueError("daq.fastrx_word and daq.fastrx_frame must be provided together")
        if _aligned_length(fields) == 0:
            raise ValueError("comparator DAQ must contain at least one trial")
        object.__setattr__(self, "trial_index", trial_index)
        object.__setattr__(self, "vin_diff_v", vin_diff_v)
        object.__setattr__(self, "vin_cm_v", vin_cm_v)
        object.__setattr__(self, "decision", decision)
        object.__setattr__(self, "fastrx_word", fastrx_word)
        object.__setattr__(self, "fastrx_frame", fastrx_frame)


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
    param: AdcTbParams
    daq: CompDaq
    wave: CompExtWave | None

    def __post_init__(self) -> None:
        if not isinstance(self.param, AdcTbParams):
            raise TypeError("MeasCompExt requires AdcTbParams")
        if self.info.backend == "physical" and self.info.schema_version >= 2 and self.daq.fastrx_word is None:
            raise ValueError("schema-v2 physical MeasCompExt requires FastRX words and frames")
        wave_indices = np.asarray([], dtype=np.int64) if self.wave is None else self.wave.trial_index
        _validate_measurement(self.info, type(self).__name__, self.daq.trial_index, wave_indices)


@dataclass(frozen=True, slots=True)
class MeasCompInt:
    """Comparator measurement with internal simulation waveforms."""

    info: MeasInfo
    param: CompTbParams | AdcTbParams
    daq: CompDaq
    wave: CompIntWave

    def __post_init__(self) -> None:
        if not isinstance(self.param, (CompTbParams, AdcTbParams)):
            raise TypeError("MeasCompInt requires CompTbParams or AdcTbParams")
        if self.daq.fastrx_word is not None:
            raise ValueError("MeasCompInt must not invent FastRX words")
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
class CdacExtDaq:
    """External CDAC trial conditions and comparator decisions."""

    trial_index: IntArray
    dac_state_p: Uint8Array
    dac_state_n: Uint8Array
    vin_diff_v: FloatArray
    decision: Uint8Array
    dac_state_before_p: Uint8Array | None = None
    dac_state_before_n: Uint8Array | None = None
    vin_cm_v: FloatArray | None = None
    fastrx_word: Uint32Array | None = None
    fastrx_frame: Uint32Array | None = None

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
        fields = {
            "trial_index": trial_index,
            "dac_state_p": dac_state_p,
            "dac_state_n": dac_state_n,
            "vin_diff_v": vin_diff_v,
            "decision": decision,
        }
        optional_arrays = {}
        for name, values, dtype, finite in (
            ("dac_state_before_p", self.dac_state_before_p, np.uint8, False),
            ("dac_state_before_n", self.dac_state_before_n, np.uint8, False),
            ("vin_cm_v", self.vin_cm_v, np.float64, True),
            ("fastrx_word", self.fastrx_word, np.uint32, False),
            ("fastrx_frame", self.fastrx_frame, np.uint32, False),
        ):
            if values is not None:
                array = (
                    _array_2d(values, dtype, f"daq.{name}")
                    if name.startswith("dac_state")
                    else _array_1d(
                        values,
                        dtype,
                        f"daq.{name}",
                        finite=finite,
                    )
                )
                optional_arrays[name] = array
                fields[name] = array
        if (self.dac_state_before_p is None) != (self.dac_state_before_n is None):
            raise ValueError("both before-update CDAC states must be provided together")
        if (self.fastrx_word is None) != (self.fastrx_frame is None):
            raise ValueError("daq.fastrx_word and daq.fastrx_frame must be provided together")
        for name in ("dac_state_before_p", "dac_state_before_n"):
            state = optional_arrays.get(name)
            if state is not None and (state.shape[1:] != (16,) or np.any((state != 0) & (state != 1))):
                raise ValueError(f"daq.{name} must have shape (N, 16) and contain only zero or one")
        if _aligned_length(fields) == 0:
            raise ValueError("external CDAC DAQ must contain at least one trial")
        object.__setattr__(self, "trial_index", trial_index)
        object.__setattr__(self, "dac_state_p", dac_state_p)
        object.__setattr__(self, "dac_state_n", dac_state_n)
        object.__setattr__(self, "vin_diff_v", vin_diff_v)
        object.__setattr__(self, "decision", decision)
        for name in ("dac_state_before_p", "dac_state_before_n", "vin_cm_v", "fastrx_word", "fastrx_frame"):
            object.__setattr__(self, name, optional_arrays.get(name))


@dataclass(frozen=True, slots=True)
class CdacIntDaq:
    """Internal CDAC trial identifiers and input states."""

    trial_index: IntArray
    dac_state_p: Uint8Array
    dac_state_n: Uint8Array
    dac_state_before_p: Uint8Array | None = None
    dac_state_before_n: Uint8Array | None = None
    vin_diff_v: FloatArray | None = None
    vin_cm_v: FloatArray | None = None
    decision: Uint8Array | None = None

    def __post_init__(self) -> None:
        trial_index = _array_1d(self.trial_index, np.int64, "daq.trial_index")
        dac_state_p = _array_2d(self.dac_state_p, np.uint8, "daq.dac_state_p")
        dac_state_n = _array_2d(self.dac_state_n, np.uint8, "daq.dac_state_n")
        for name, state in (("dac_state_p", dac_state_p), ("dac_state_n", dac_state_n)):
            if state.shape[1:] != (16,) or np.any((state != 0) & (state != 1)):
                raise ValueError(f"daq.{name} must have shape (N, 16) and contain only zero or one")
        fields = {"trial_index": trial_index, "dac_state_p": dac_state_p, "dac_state_n": dac_state_n}
        optional_arrays = {}
        for name, values, dtype, finite in (
            ("dac_state_before_p", self.dac_state_before_p, np.uint8, False),
            ("dac_state_before_n", self.dac_state_before_n, np.uint8, False),
            ("vin_diff_v", self.vin_diff_v, np.float64, True),
            ("vin_cm_v", self.vin_cm_v, np.float64, True),
            ("decision", self.decision, np.uint8, False),
        ):
            if values is not None:
                array = (
                    _array_2d(values, dtype, f"daq.{name}")
                    if name.startswith("dac_state")
                    else _array_1d(
                        values,
                        dtype,
                        f"daq.{name}",
                        finite=finite,
                    )
                )
                optional_arrays[name] = array
                fields[name] = array
        if (self.dac_state_before_p is None) != (self.dac_state_before_n is None):
            raise ValueError("both before-update CDAC states must be provided together")
        for name in ("dac_state_before_p", "dac_state_before_n"):
            state = optional_arrays.get(name)
            if state is not None and (state.shape[1:] != (16,) or np.any((state != 0) & (state != 1))):
                raise ValueError(f"daq.{name} must have shape (N, 16) and contain only zero or one")
        decision = optional_arrays.get("decision")
        if decision is not None and np.any((decision != 0) & (decision != 1)):
            raise ValueError("daq.decision values must be zero or one")
        if _aligned_length(fields) == 0:
            raise ValueError("internal CDAC DAQ must contain at least one trial")
        object.__setattr__(self, "trial_index", trial_index)
        object.__setattr__(self, "dac_state_p", dac_state_p)
        object.__setattr__(self, "dac_state_n", dac_state_n)
        for name in ("dac_state_before_p", "dac_state_before_n", "vin_diff_v", "vin_cm_v", "decision"):
            object.__setattr__(self, name, optional_arrays.get(name))


@dataclass(frozen=True, slots=True)
class CdacExtWave:
    """Externally observable CDAC comparator-path waveforms."""

    trial_index: IntArray
    time_s: FloatArray
    vin_diff_v: FloatArray
    seq_comp_v: FloatArray
    comp_out_v: FloatArray
    seq_logic_v: FloatArray | None = None

    def __post_init__(self) -> None:
        wave_signals = {
            "vin_diff_v": self.vin_diff_v,
            "seq_comp_v": self.seq_comp_v,
            "comp_out_v": self.comp_out_v,
        }
        if self.seq_logic_v is not None:
            wave_signals["seq_logic_v"] = self.seq_logic_v
        indices, times, signals = _normalize_wave(
            self.trial_index,
            self.time_s,
            wave_signals,
        )
        object.__setattr__(self, "trial_index", indices)
        object.__setattr__(self, "time_s", times)
        for name, values in signals.items():
            object.__setattr__(self, name, values)
        object.__setattr__(self, "seq_logic_v", signals.get("seq_logic_v"))


@dataclass(frozen=True, slots=True)
class CdacIntWave:
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
class MeasCdacExt:
    """CDAC measurement inferred through the external comparator path."""

    info: MeasInfo
    param: AdcTbParams
    daq: CdacExtDaq
    wave: CdacExtWave | None

    def __post_init__(self) -> None:
        if not isinstance(self.param, AdcTbParams):
            raise TypeError("MeasCdacExt requires AdcTbParams")
        if (
            self.info.backend == "physical"
            and self.info.schema_version >= 2
            and (self.daq.dac_state_before_p is None or self.daq.vin_cm_v is None or self.daq.fastrx_word is None)
        ):
            raise ValueError("schema-v2 physical MeasCdacExt requires before states, Vin_cm, and FastRX words/ frames")
        wave_indices = np.asarray([], dtype=np.int64) if self.wave is None else self.wave.trial_index
        _validate_measurement(self.info, type(self).__name__, self.daq.trial_index, wave_indices)


@dataclass(frozen=True, slots=True)
class MeasCdacInt:
    """CDAC measurement with internal simulation waveforms."""

    info: MeasInfo
    param: CdacTbParams | AdcTbParams
    daq: CdacIntDaq
    wave: CdacIntWave

    def __post_init__(self) -> None:
        if not isinstance(self.param, (CdacTbParams, AdcTbParams)):
            raise TypeError("MeasCdacInt requires CdacTbParams or AdcTbParams")
        _validate_measurement(self.info, type(self).__name__, self.daq.trial_index, self.wave.trial_index)


type Measurement = MeasAdc | MeasCompExt | MeasCompInt | MeasSampInt | MeasCdacExt | MeasCdacInt


# =============================================================================
# Typed analysis results
# =============================================================================


@dataclass(frozen=True, slots=True)
class AnalysisWaveforms:
    """One selected, aligned waveform record ready for rendering."""

    title: str
    time_s: FloatArray
    signal_names: tuple[str, ...]
    signal_units: tuple[str, ...]
    signal_values: FloatArray
    setup_lines: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        time_s = _array_1d(self.time_s, np.float64, "time_s", finite=True)
        signal_values = _array_2d(self.signal_values, np.float64, "signal_values", finite=True)
        if not self.title.strip():
            raise ValueError("waveform analysis title must not be empty")
        if len(time_s) < 2 or np.any(np.diff(time_s) <= 0.0):
            raise ValueError("waveform time_s must contain at least two increasing samples")
        if not 1 <= len(self.signal_names) <= 4:
            raise ValueError("waveform analysis requires one to four signals")
        if any(not name.strip() for name in self.signal_names) or len(set(self.signal_names)) != len(self.signal_names):
            raise ValueError("waveform signal names must be nonempty and unique")
        expected_shape = (len(self.signal_names), len(time_s))
        if signal_values.shape != expected_shape:
            raise ValueError(f"waveform signal_values has shape {signal_values.shape}, expected {expected_shape}")
        if len(self.signal_units) != len(self.signal_names) or any(
            not isinstance(unit, str) for unit in self.signal_units
        ):
            raise ValueError("waveform signal units must align with signal names")
        if any(not isinstance(line, str) or not line.strip() for line in self.setup_lines):
            raise ValueError("waveform setup lines must be nonempty strings")
        object.__setattr__(self, "time_s", time_s)
        object.__setattr__(self, "signal_values", signal_values)
        object.__setattr__(self, "signal_names", tuple(self.signal_names))
        object.__setattr__(self, "signal_units", tuple(self.signal_units))
        object.__setattr__(self, "setup_lines", tuple(self.setup_lines))


@dataclass(frozen=True, slots=True)
class AnalysisDiffampNoise:
    """Gaussian and spectral characterization of one quiet waveform."""

    mean_v: float
    centered_v: FloatArray
    noise_rms_v: float
    sample_rate_hz: float
    measurement_bandwidth_hz: float
    frequency_hz: FloatArray
    amplitude_spectral_density_v_per_sqrt_hz: FloatArray
    integrated_fft_noise_rms_v: float

    def __post_init__(self) -> None:
        centered_v = _array_1d(self.centered_v, np.float64, "centered_v", finite=True)
        frequency_hz = _array_1d(self.frequency_hz, np.float64, "frequency_hz", finite=True)
        density = _array_1d(
            self.amplitude_spectral_density_v_per_sqrt_hz,
            np.float64,
            "amplitude_spectral_density_v_per_sqrt_hz",
            finite=True,
        )
        if len(centered_v) < 256:
            raise ValueError("diff-amp noise analysis requires at least 256 samples")
        if len(frequency_hz) != len(density) or len(frequency_hz) < 2:
            raise ValueError("diff-amp spectrum frequency and density must be aligned")
        if np.any(np.diff(frequency_hz) <= 0.0) or frequency_hz[0] < 0.0 or np.any(density < 0.0):
            raise ValueError("diff-amp spectrum must have increasing frequencies and nonnegative density")
        scalars = (
            self.mean_v,
            self.noise_rms_v,
            self.sample_rate_hz,
            self.measurement_bandwidth_hz,
            self.integrated_fft_noise_rms_v,
        )
        if not all(math.isfinite(value) for value in scalars):
            raise ValueError("diff-amp noise scalar results must be finite")
        if (
            self.noise_rms_v <= 0.0
            or self.integrated_fft_noise_rms_v < 0.0
            or self.sample_rate_hz <= 0.0
            or self.measurement_bandwidth_hz <= 0.0
            or self.measurement_bandwidth_hz > self.sample_rate_hz / 2.0
            or frequency_hz[-1] > self.sample_rate_hz / 2.0
        ):
            raise ValueError("diff-amp noise scale, sample rate, and bandwidth must be positive")
        object.__setattr__(self, "centered_v", centered_v)
        object.__setattr__(self, "frequency_hz", frequency_hz)
        object.__setattr__(self, "amplitude_spectral_density_v_per_sqrt_hz", density)


@dataclass(frozen=True, slots=True)
class AnalysisAdcScopeBits:
    """One 17-decision scope decode aligned with the first FastRX word."""

    scope_bits: BoolArray
    fastrx_bits: BoolArray
    comp_threshold_v: float
    comp_out_threshold_v: float
    comp_edge_times_s: FloatArray
    sample_times_s: FloatArray
    sample_values_v: FloatArray
    mismatch_mask: BoolArray = field(init=False)

    def __post_init__(self) -> None:
        scope_bits = _array_1d(self.scope_bits, np.bool_, "scope_bits")
        fastrx_bits = _array_1d(self.fastrx_bits, np.bool_, "fastrx_bits")
        edge_times = _array_1d(self.comp_edge_times_s, np.float64, "comp_edge_times_s", finite=True)
        sample_times = _array_1d(self.sample_times_s, np.float64, "sample_times_s", finite=True)
        sample_values = _array_1d(self.sample_values_v, np.float64, "sample_values_v", finite=True)
        expected_shape = (17,)
        if any(
            values.shape != expected_shape
            for values in (scope_bits, fastrx_bits, edge_times, sample_times, sample_values)
        ):
            raise ValueError("scope/FastRX analysis requires exactly 17 aligned decisions")
        if (
            np.any(np.diff(edge_times) <= 0.0)
            or np.any(np.diff(sample_times) <= 0.0)
            or np.any(sample_times <= edge_times)
        ):
            raise ValueError("scope decision edges and samples must increase and remain ordered")
        if not all(math.isfinite(value) for value in (self.comp_threshold_v, self.comp_out_threshold_v)):
            raise ValueError("scope decision thresholds must be finite")
        object.__setattr__(self, "scope_bits", scope_bits)
        object.__setattr__(self, "fastrx_bits", fastrx_bits)
        object.__setattr__(self, "comp_edge_times_s", edge_times)
        object.__setattr__(self, "sample_times_s", sample_times)
        object.__setattr__(self, "sample_values_v", sample_values)
        object.__setattr__(self, "mismatch_mask", scope_bits != fastrx_bits)

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
class AnalysisAdcTransfer:
    """Mean static transfer and dispersion at each differential input."""

    vin_diff_v: FloatArray
    mean_dout: FloatArray
    std_dout: FloatArray
    sample_count: IntArray

    def __post_init__(self) -> None:
        values = {
            "vin_diff_v": _array_1d(self.vin_diff_v, np.float64, "vin_diff_v", finite=True),
            "mean_dout": _array_1d(self.mean_dout, np.float64, "mean_dout", finite=True),
            "std_dout": _array_1d(self.std_dout, np.float64, "std_dout", finite=True),
            "sample_count": _array_1d(self.sample_count, np.int64, "sample_count"),
        }
        if _aligned_length(values) == 0:
            raise ValueError("ADC transfer analysis requires at least one input point")
        if np.any(np.diff(values["vin_diff_v"]) <= 0.0):
            raise ValueError("ADC transfer inputs must be strictly increasing")
        if np.any(values["std_dout"] < 0.0) or np.any(values["sample_count"] <= 0):
            raise ValueError("ADC transfer deviations and sample counts are outside their valid ranges")
        for name, value in values.items():
            object.__setattr__(self, name, value)


@dataclass(frozen=True, slots=True)
class AnalysisAdcNonlinearity:
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

    def __post_init__(self) -> None:
        if self.method not in ("endpoint", "code_density"):
            raise ValueError(f"unknown ADC nonlinearity method {self.method!r}")
        values = {
            "code": _array_1d(self.code, np.int64, "code"),
            "dnl": _array_1d(self.dnl, np.float64, "dnl", finite=True),
            "inl": _array_1d(self.inl, np.float64, "inl", finite=True),
        }
        if _aligned_length(values) == 0:
            raise ValueError("ADC nonlinearity analysis requires at least one code")
        if values["code"][0] < 0 or np.any(np.diff(values["code"]) <= 0):
            raise ValueError("ADC nonlinearity codes must be nonnegative and strictly increasing")
        count = None if self.count is None else _array_1d(self.count, np.int64, "count")
        transition = (
            None
            if self.transition_vin_diff_v is None
            else _array_1d(self.transition_vin_diff_v, np.float64, "transition_vin_diff_v", finite=True)
        )
        if count is not None and (len(count) != len(values["code"]) or np.any(count < 0)):
            raise ValueError("ADC nonlinearity counts must align with codes and be nonnegative")
        if transition is not None and (len(transition) != len(values["code"]) or np.any(np.diff(transition) <= 0.0)):
            raise ValueError("ADC endpoint transitions must align with codes and increase")
        if self.method == "endpoint" and (
            transition is None
            or count is not None
            or self.ideal_count is not None
            or self.endpoint_lsb_v is None
            or not math.isfinite(self.endpoint_lsb_v)
            or self.endpoint_lsb_v <= 0.0
        ):
            raise ValueError("endpoint nonlinearity requires transitions and a positive endpoint LSB")
        if self.method == "code_density" and (
            count is None
            or transition is not None
            or self.endpoint_lsb_v is not None
            or self.ideal_count is None
            or not math.isfinite(self.ideal_count)
            or self.ideal_count <= 0.0
        ):
            raise ValueError("code-density nonlinearity requires counts and a positive ideal count")
        if (
            not math.isfinite(self.maximum_abs_dnl)
            or self.maximum_abs_dnl < 0.0
            or not math.isfinite(self.maximum_abs_inl)
            or self.maximum_abs_inl < 0.0
            or not np.isclose(self.maximum_abs_dnl, np.max(np.abs(values["dnl"])))
            or not np.isclose(self.maximum_abs_inl, np.max(np.abs(values["inl"])))
            or self.missing_codes < 0
        ):
            raise ValueError("ADC nonlinearity metrics are outside their valid ranges")
        if self.method == "code_density" and count is not None:
            if self.missing_codes != np.count_nonzero(count == 0):
                raise ValueError("ADC code-density missing-code total does not match its histogram")
        elif self.missing_codes > len(values["code"]) + 2:
            raise ValueError("ADC endpoint missing-code total exceeds its analyzed range")
        for name, value in values.items():
            object.__setattr__(self, name, value)
        object.__setattr__(self, "count", count)
        object.__setattr__(self, "transition_vin_diff_v", transition)


@dataclass(frozen=True, slots=True)
class AnalysisAdcCalibration:
    """Common output of each 17-decision digital calibration method.

    All three calibration analyses normalize their BOUT coefficients to the
    inclusive ADC output range, so a corrected fractional code is simply
    ``BOUT @ calibrated_weight``. ``weight_from_measurement`` distinguishes
    directly measured or fitted coefficients from nominally preserved ones.
    In calibration 1 the terminal half-step is inferred, and in calibration 3
    the unresolved noise-limited tail keeps its nominal ratios.
    """

    adc_index: int
    method: AdcCalibrationMethod
    label: str
    code_max: int
    nominal_weight: FloatArray
    calibrated_weight: FloatArray
    weight_from_measurement: NDArray[np.bool_]
    training_sample_count: int
    validation_sample_count: int
    output_gain: float
    output_offset_lsb: float

    def __post_init__(self) -> None:
        if not -1 <= self.adc_index < 16:
            raise ValueError("ADC calibration index must be -1 or in 0..15")
        if self.method not in ("calibration1", "calibration2", "calibration3"):
            raise ValueError(f"unknown ADC calibration method {self.method!r}")
        if not self.label.strip():
            raise ValueError("ADC calibration label must not be empty")
        if not isinstance(self.code_max, int) or self.code_max <= 0:
            raise ValueError("ADC calibration code_max must be a positive integer")
        nominal = _array_1d(self.nominal_weight, np.float64, "nominal_weight", finite=True)
        calibrated = _array_1d(self.calibrated_weight, np.float64, "calibrated_weight", finite=True)
        measured = _array_1d(
            self.weight_from_measurement,
            np.bool_,
            "weight_from_measurement",
        )
        expected_shape = (17,)
        if nominal.shape != expected_shape or calibrated.shape != expected_shape or measured.shape != expected_shape:
            raise ValueError("ADC calibration requires exactly 17 aligned BOUT weights")
        if np.any(nominal <= 0.0) or np.any(calibrated <= 0.0):
            raise ValueError("ADC calibration weights must be positive")
        tolerance = max(1.0e-10, self.code_max * 1.0e-12)
        if not np.isclose(np.sum(nominal), self.code_max, rtol=0.0, atol=tolerance):
            raise ValueError("nominal ADC calibration weights must sum to code_max")
        if not np.isclose(np.sum(calibrated), self.code_max, rtol=0.0, atol=tolerance):
            raise ValueError("calibrated ADC calibration weights must sum to code_max")
        if self.training_sample_count < 0 or self.validation_sample_count < 0:
            raise ValueError("ADC calibration sample counts must be nonnegative")
        if not math.isfinite(self.output_gain) or self.output_gain <= 0.0:
            raise ValueError("ADC calibration output_gain must be finite and positive")
        if not math.isfinite(self.output_offset_lsb):
            raise ValueError("ADC calibration output_offset_lsb must be finite")
        object.__setattr__(self, "nominal_weight", nominal)
        object.__setattr__(self, "calibrated_weight", calibrated)
        object.__setattr__(self, "weight_from_measurement", measured)


@dataclass(frozen=True, slots=True)
class AnalysisAdcRampCurve:
    """Per-decoding results derived from one shared ramp capture.

    One instance represents nominal DOUT or one calibrated interpretation of
    the stored BOUT decisions. Capture timing and inferred input phase live on
    the containing :class:`AnalysisAdcRamp` and are not repeated here.
    """

    decoding: AdcDecoding
    label: str
    weights: FloatArray
    transfer_vin_diff_v: FloatArray
    transfer_mean_dout: FloatArray
    transfer_sample_count: IntArray
    code: IntArray
    count: IntArray
    linearity_code: IntArray
    dnl: FloatArray
    inl: FloatArray
    ideal_count: float
    maximum_abs_dnl: float
    maximum_abs_inl: float
    missing_codes: int
    maximum_transfer_reversal_dout: float

    def __post_init__(self) -> None:
        if self.decoding not in ("uncalibrated_dout", "calibration1", "calibration2", "calibration3"):
            raise ValueError(f"unknown ADC ramp decoding {self.decoding!r}")
        if not self.label.strip():
            raise ValueError("ADC ramp curve label must not be empty")
        weights = _array_1d(self.weights, np.float64, "weights", finite=True)
        transfer = {
            "transfer_vin_diff_v": _array_1d(
                self.transfer_vin_diff_v,
                np.float64,
                "transfer_vin_diff_v",
                finite=True,
            ),
            "transfer_mean_dout": _array_1d(
                self.transfer_mean_dout,
                np.float64,
                "transfer_mean_dout",
                finite=True,
            ),
            "transfer_sample_count": _array_1d(
                self.transfer_sample_count,
                np.int64,
                "transfer_sample_count",
            ),
        }
        density = {
            "linearity_code": _array_1d(self.linearity_code, np.int64, "linearity_code"),
            "dnl": _array_1d(self.dnl, np.float64, "dnl", finite=True),
            "inl": _array_1d(self.inl, np.float64, "inl", finite=True),
        }
        code = _array_1d(self.code, np.int64, "code")
        count = _array_1d(self.count, np.int64, "count")
        if len(weights) != 17 or np.any(weights <= 0.0):
            raise ValueError("ADC ramp curves require 17 positive decision weights")
        if _aligned_length(transfer) == 0 or np.any(transfer["transfer_sample_count"] <= 0):
            raise ValueError("ADC ramp transfer requires populated aligned bins")
        if np.any(np.diff(transfer["transfer_vin_diff_v"]) <= 0.0):
            raise ValueError("ADC ramp transfer inputs must be strictly increasing")
        if _aligned_length({"code": code, "count": count}) == 0 or np.any(count < 0):
            raise ValueError("ADC ramp histogram requires nonnegative aligned counts")
        if _aligned_length(density) == 0:
            raise ValueError("ADC ramp linearity requires at least one code")
        if (
            code[0] < 0
            or density["linearity_code"][0] < 0
            or np.any(np.diff(code) <= 0)
            or np.any(np.diff(density["linearity_code"]) <= 0)
            or not np.all(np.isin(density["linearity_code"], code))
        ):
            raise ValueError("ADC ramp histogram and linearity codes must be nonnegative, increasing, and aligned")
        if (
            not math.isfinite(self.ideal_count)
            or self.ideal_count <= 0.0
            or not math.isfinite(self.maximum_abs_dnl)
            or self.maximum_abs_dnl < 0.0
            or not math.isfinite(self.maximum_abs_inl)
            or self.maximum_abs_inl < 0.0
            or not np.isclose(self.maximum_abs_dnl, np.max(np.abs(density["dnl"])))
            or not np.isclose(self.maximum_abs_inl, np.max(np.abs(density["inl"])))
            or not 0 <= self.missing_codes <= len(density["linearity_code"])
            or not math.isfinite(self.maximum_transfer_reversal_dout)
            or self.maximum_transfer_reversal_dout < 0.0
        ):
            raise ValueError("ADC ramp curve metrics are outside their valid ranges")
        object.__setattr__(self, "weights", weights)
        object.__setattr__(self, "code", code)
        object.__setattr__(self, "count", count)
        for name, value in {**transfer, **density}.items():
            object.__setattr__(self, name, value)


@dataclass(frozen=True, slots=True)
class AnalysisAdcRamp:
    """Shared ramp reconstruction containing one curve per DOUT decoding."""

    adc_index: int
    sample_count: int
    retained_sample_count: int
    reset_excluded_sample_count: int
    sample_rate_hz: float
    ramp_frequency_hz: float
    ramp_phase_cycles: float
    reset_conversion_index: IntArray
    vin_diff_min_v: float
    vin_diff_max_v: float
    curves: tuple[AnalysisAdcRampCurve, ...]

    def __post_init__(self) -> None:
        reset_indices = _array_1d(self.reset_conversion_index, np.int64, "reset_conversion_index")
        curves = tuple(self.curves)
        if not -1 <= self.adc_index < 16:
            raise ValueError("ADC ramp index must be -1 or in 0..15")
        if (
            self.sample_count <= 0
            or self.retained_sample_count <= 0
            or self.reset_excluded_sample_count < 0
            or self.retained_sample_count + self.reset_excluded_sample_count != self.sample_count
        ):
            raise ValueError("ADC ramp sample counts are inconsistent")
        if (
            not math.isfinite(self.sample_rate_hz)
            or self.sample_rate_hz <= 0.0
            or not math.isfinite(self.ramp_frequency_hz)
            or self.ramp_frequency_hz <= 0.0
            or not math.isfinite(self.ramp_phase_cycles)
            or not 0.0 <= self.ramp_phase_cycles < 1.0
            or not math.isfinite(self.vin_diff_min_v)
            or not math.isfinite(self.vin_diff_max_v)
            or self.vin_diff_min_v >= self.vin_diff_max_v
        ):
            raise ValueError("ADC ramp timing and input range are invalid")
        if (
            len(reset_indices) == 0
            or reset_indices[0] < 0
            or reset_indices[-1] >= self.sample_count
            or np.any(np.diff(reset_indices) <= 0)
        ):
            raise ValueError("ADC ramp reset indices must be in-range, nonempty, and increasing")
        if not curves or len({curve.decoding for curve in curves}) != len(curves):
            raise ValueError("ADC ramp requires uniquely decoded curves")
        if any(
            np.sum(curve.count) != self.retained_sample_count
            or np.sum(curve.transfer_sample_count) != self.retained_sample_count
            for curve in curves
        ):
            raise ValueError("ADC ramp curve sample totals must match the retained capture")
        object.__setattr__(self, "reset_conversion_index", reset_indices)
        object.__setattr__(self, "curves", curves)


@dataclass(frozen=True, slots=True)
class AnalysisAdcCodeDistribution:
    """Code statistics and histograms for one or more static input points."""

    vin_diff_v: FloatArray
    sample_count: IntArray
    mean_dout: FloatArray
    std_dout: FloatArray
    minimum_dout: IntArray
    maximum_dout: IntArray
    code: IntArray
    count: IntArray

    def __post_init__(self) -> None:
        points = {
            "vin_diff_v": _array_1d(self.vin_diff_v, np.float64, "vin_diff_v", finite=True),
            "sample_count": _array_1d(self.sample_count, np.int64, "sample_count"),
            "mean_dout": _array_1d(self.mean_dout, np.float64, "mean_dout", finite=True),
            "std_dout": _array_1d(self.std_dout, np.float64, "std_dout", finite=True),
            "minimum_dout": _array_1d(self.minimum_dout, np.int64, "minimum_dout"),
            "maximum_dout": _array_1d(self.maximum_dout, np.int64, "maximum_dout"),
        }
        code = _array_1d(self.code, np.int64, "code")
        count = _array_2d(self.count, np.int64, "count")
        point_count = _aligned_length(points)
        if point_count == 0 or len(code) == 0:
            raise ValueError("ADC code distribution requires input points and output codes")
        if count.shape != (point_count, len(code)):
            raise ValueError("ADC code distribution counts must align with input points and codes")
        if np.any(np.diff(points["vin_diff_v"]) <= 0.0) or code[0] < 0 or np.any(np.diff(code) <= 0):
            raise ValueError("ADC code-distribution inputs and codes must increase")
        if (
            np.any(points["sample_count"] <= 0)
            or np.any(points["std_dout"] < 0.0)
            or np.any(points["minimum_dout"] > points["maximum_dout"])
            or np.any(count < 0)
        ):
            raise ValueError("ADC code-distribution statistics are outside their valid ranges")
        if not np.array_equal(np.sum(count, axis=1), points["sample_count"]):
            raise ValueError("ADC code-distribution histogram totals must match sample counts")
        populated = count > 0
        expected_minimum = code[np.argmax(populated, axis=1)]
        expected_maximum = code[len(code) - 1 - np.argmax(populated[:, ::-1], axis=1)]
        if (
            not np.array_equal(points["minimum_dout"], expected_minimum)
            or not np.array_equal(points["maximum_dout"], expected_maximum)
            or np.any(points["mean_dout"] < points["minimum_dout"])
            or np.any(points["mean_dout"] > points["maximum_dout"])
        ):
            raise ValueError("ADC code-distribution summary statistics do not match its histograms")
        for name, value in points.items():
            object.__setattr__(self, name, value)
        object.__setattr__(self, "code", code)
        object.__setattr__(self, "count", count)


@dataclass(frozen=True, slots=True)
class AnalysisAdcNoiseSweep:
    """Fixed-input output variation across conversion timing settings."""

    sample_rate_hz: FloatArray
    logic_phase_delay_symbols: FloatArray
    comparator_time_percent: FloatArray
    input_lsb_v: float
    input_referred_noise_rms_v: FloatArray
    pretrigger_vin_diff_mean_v: FloatArray
    pretrigger_vin_diff_noise_rms_v: FloatArray
    mean_dout: FloatArray
    std_dout: FloatArray
    minimum_dout: IntArray
    maximum_dout: IntArray
    bit_mismatches: IntArray
    noise_valid: BoolArray
    code: IntArray | None = None
    count: IntArray | None = None
    series_labels: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        float_fields = {
            name: _array_1d(getattr(self, name), np.float64, name)
            for name in (
                "sample_rate_hz",
                "logic_phase_delay_symbols",
                "comparator_time_percent",
                "input_referred_noise_rms_v",
                "pretrigger_vin_diff_mean_v",
                "pretrigger_vin_diff_noise_rms_v",
                "mean_dout",
                "std_dout",
            )
        }
        int_fields = {
            name: _array_1d(getattr(self, name), np.int64, name)
            for name in ("minimum_dout", "maximum_dout", "bit_mismatches")
        }
        noise_valid = _array_1d(self.noise_valid, np.bool_, "noise_valid")
        sample_count = _aligned_length({**float_fields, **int_fields, "noise_valid": noise_valid})
        if sample_count == 0:
            raise ValueError("ADC noise sweep requires at least one point")
        if not math.isfinite(self.input_lsb_v) or self.input_lsb_v <= 0.0:
            raise ValueError("ADC noise sweep input_lsb_v must be finite and positive")
        if (
            not np.all(np.isfinite(float_fields["sample_rate_hz"]))
            or np.any(float_fields["sample_rate_hz"] <= 0.0)
            or not np.all(np.isfinite(float_fields["logic_phase_delay_symbols"]))
            or not np.all(np.isfinite(float_fields["comparator_time_percent"]))
            or any(np.any(np.isinf(values)) for values in float_fields.values())
            or np.any(float_fields["std_dout"][np.isfinite(float_fields["std_dout"])] < 0.0)
            or np.any(
                float_fields["pretrigger_vin_diff_noise_rms_v"][
                    np.isfinite(float_fields["pretrigger_vin_diff_noise_rms_v"])
                ]
                < 0.0
            )
            or np.any(int_fields["minimum_dout"] > int_fields["maximum_dout"])
            or np.any(int_fields["bit_mismatches"] < 0)
        ):
            raise ValueError("ADC noise sweep values are outside their valid ranges")
        if np.any(
            ~np.isfinite(float_fields["input_referred_noise_rms_v"][noise_valid])
            | (float_fields["input_referred_noise_rms_v"][noise_valid] <= 0.0)
        ):
            raise ValueError("valid ADC noise points require finite positive input-referred noise")
        code = None if self.code is None else _array_1d(self.code, np.int64, "code")
        count = None if self.count is None else _array_2d(self.count, np.int64, "count")
        if (code is None) != (count is None):
            raise ValueError("ADC noise sweep code and count must be present together")
        if (
            code is not None
            and count is not None
            and (
                not len(code)
                or code[0] < 0
                or np.any(np.diff(code) <= 0)
                or count.shape != (sample_count, len(code))
                or np.any(count < 0)
            )
        ):
            raise ValueError("ADC noise sweep histograms must be nonnegative and align with increasing codes")
        labels = tuple(self.series_labels)
        if labels and (len(labels) != sample_count or any(not label.strip() for label in labels)):
            raise ValueError("ADC noise sweep series labels must align with its points")
        for name, values in {**float_fields, **int_fields}.items():
            object.__setattr__(self, name, values)
        object.__setattr__(self, "code", code)
        object.__setattr__(self, "count", count)
        object.__setattr__(self, "noise_valid", noise_valid)
        object.__setattr__(self, "series_labels", labels)


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

    def __post_init__(self) -> None:
        waveform = {
            "time_s": _array_1d(self.time_s, np.float64, "time_s", finite=True),
            "measured_dout": _array_1d(self.measured_dout, np.float64, "measured_dout", finite=True),
            "fitted_dout": _array_1d(self.fitted_dout, np.float64, "fitted_dout", finite=True),
            "residual_dout": _array_1d(self.residual_dout, np.float64, "residual_dout", finite=True),
        }
        spectrum = {
            "spectrum_frequency_hz": _array_1d(
                self.spectrum_frequency_hz,
                np.float64,
                "spectrum_frequency_hz",
                finite=True,
            ),
            "spectrum_dbfs": _array_1d(self.spectrum_dbfs, np.float64, "spectrum_dbfs"),
        }
        if _aligned_length(waveform) != self.sample_count or self.sample_count < 2:
            raise ValueError("ADC dynamic waveform must align with its sample count")
        if _aligned_length(spectrum) == 0:
            raise ValueError("ADC dynamic spectrum requires at least one bin")
        if np.any(np.diff(waveform["time_s"]) <= 0.0) or np.any(np.diff(spectrum["spectrum_frequency_hz"]) <= 0.0):
            raise ValueError("ADC dynamic time and frequency axes must increase")
        if np.any(np.isnan(spectrum["spectrum_dbfs"])) or np.any(np.isposinf(spectrum["spectrum_dbfs"])):
            raise ValueError("ADC dynamic spectrum contains invalid values")
        if (
            spectrum["spectrum_frequency_hz"][0] < 0.0
            or spectrum["spectrum_frequency_hz"][-1] > self.sample_rate_hz / 2.0
        ):
            raise ValueError("ADC dynamic spectrum must remain within the Nyquist interval")
        positive_scalars = (
            self.sample_rate_hz,
            self.input_frequency_hz,
            self.fitted_frequency_hz,
            self.signal_rms_dout,
            self.residual_tail_limit_dout,
        )
        finite_scalars = (
            self.offset_dout,
            self.amplitude_dout,
            self.phase_rad,
            self.amplitude_dbfs,
            self.residual_rms_dout,
            self.input_referred_noise_rms_v,
            self.input_referred_residual_rms_v,
            self.sinad_db,
            self.enob_bits,
            self.spectral_sndr_db,
            self.spectral_snr_db,
            self.spectral_thd_db,
            self.spectral_sfdr_db,
            self.spectral_enob_bits,
            self.expected_residual_tail_count,
            self.maximum_abs_residual_dout,
        )
        if self.adc_bits <= 0 or any(not math.isfinite(value) or value <= 0.0 for value in positive_scalars):
            raise ValueError("ADC dynamic rates, scales, and bit depth must be positive")
        if any(not math.isfinite(value) for value in finite_scalars):
            raise ValueError("ADC dynamic metrics must be finite")
        if (
            self.amplitude_dout < 0.0
            or self.residual_rms_dout < 0.0
            or self.input_referred_noise_rms_v < 0.0
            or self.input_referred_residual_rms_v < 0.0
            or self.expected_residual_tail_count < 0.0
            or self.negative_residual_tail_count < 0
            or self.positive_residual_tail_count < 0
            or self.maximum_abs_residual_dout < 0.0
            or self.negative_residual_tail_count + self.positive_residual_tail_count > self.sample_count
            or not np.isclose(self.maximum_abs_residual_dout, np.max(np.abs(waveform["residual_dout"])))
        ):
            raise ValueError("ADC dynamic magnitudes and counts must be nonnegative")
        for name, value in {**waveform, **spectrum}.items():
            object.__setattr__(self, name, value)


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

    def __post_init__(self) -> None:
        float_fields = {
            name: _array_1d(getattr(self, name), np.float64, name, finite=True)
            for name in (
                "input_frequency_hz",
                "sample_rate_hz",
                "active_conversion_rate_hz",
                "logic_phase_delay_symbols",
                "input_referred_noise_rms_v",
                "input_referred_residual_rms_v",
                "spectral_enob_bits",
                "spectral_sndr_db",
                "spectral_snr_db",
                "spectral_thd_db",
                "spectral_sfdr_db",
                "expected_residual_tail_count",
                "maximum_abs_residual_dout",
            )
        }
        int_fields = {
            name: _array_1d(getattr(self, name), np.int64, name)
            for name in ("observed_adc", "negative_residual_tail_count", "positive_residual_tail_count")
        }
        if _aligned_length({**float_fields, **int_fields}) == 0:
            raise ValueError("ADC dynamic sweep requires at least one point")
        if (
            np.any(float_fields["input_frequency_hz"] <= 0.0)
            or np.any(float_fields["sample_rate_hz"] <= 0.0)
            or np.any(float_fields["active_conversion_rate_hz"] <= 0.0)
            or np.any(float_fields["input_referred_noise_rms_v"] < 0.0)
            or np.any(float_fields["input_referred_residual_rms_v"] < 0.0)
            or np.any(float_fields["expected_residual_tail_count"] < 0.0)
            or np.any(float_fields["maximum_abs_residual_dout"] < 0.0)
            or np.any((int_fields["observed_adc"] < -1) | (int_fields["observed_adc"] >= 16))
            or np.any(int_fields["negative_residual_tail_count"] < 0)
            or np.any(int_fields["positive_residual_tail_count"] < 0)
            or not math.isfinite(self.residual_tail_limit_dout)
            or self.residual_tail_limit_dout <= 0.0
        ):
            raise ValueError("ADC dynamic sweep values are outside their valid ranges")
        for name, value in {**float_fields, **int_fields}.items():
            object.__setattr__(self, name, value)


@dataclass(frozen=True, slots=True)
class AnalysisAdcPowerSweep:
    """Static-baseline and incremental ADC supply power across conversion rates."""

    sample_rate_hz: FloatArray
    active_conversion_rate_hz: FloatArray
    observed_adc: IntArray
    vdd_a_static_power_w: FloatArray
    vdd_d_static_power_w: FloatArray
    vdd_dac_static_power_w: FloatArray
    vdd_a_dynamic_power_w: FloatArray
    vdd_d_dynamic_power_w: FloatArray
    vdd_dac_dynamic_power_w: FloatArray
    total_static_power_w: FloatArray
    total_dynamic_power_w: FloatArray
    total_power_w: FloatArray

    def __post_init__(self) -> None:
        float_fields = {
            name: _array_1d(getattr(self, name), np.float64, name, finite=True)
            for name in (
                "sample_rate_hz",
                "active_conversion_rate_hz",
                "vdd_a_static_power_w",
                "vdd_d_static_power_w",
                "vdd_dac_static_power_w",
                "vdd_a_dynamic_power_w",
                "vdd_d_dynamic_power_w",
                "vdd_dac_dynamic_power_w",
                "total_static_power_w",
                "total_dynamic_power_w",
                "total_power_w",
            )
        }
        observed_adc = _array_1d(self.observed_adc, np.int64, "observed_adc")
        if _aligned_length({**float_fields, "observed_adc": observed_adc}) == 0:
            raise ValueError("ADC power sweep requires at least one point")
        if (
            np.any(float_fields["sample_rate_hz"] <= 0.0)
            or np.any(float_fields["active_conversion_rate_hz"] <= 0.0)
            or any(np.any(values < 0.0) for name, values in float_fields.items() if not name.endswith("rate_hz"))
            or np.any((observed_adc < -1) | (observed_adc >= 16))
        ):
            raise ValueError("ADC power sweep rates, powers, and indices are outside their valid ranges")
        static_sum = (
            float_fields["vdd_a_static_power_w"]
            + float_fields["vdd_d_static_power_w"]
            + float_fields["vdd_dac_static_power_w"]
        )
        dynamic_sum = (
            float_fields["vdd_a_dynamic_power_w"]
            + float_fields["vdd_d_dynamic_power_w"]
            + float_fields["vdd_dac_dynamic_power_w"]
        )
        if (
            not np.allclose(float_fields["total_static_power_w"], static_sum)
            or not np.allclose(float_fields["total_dynamic_power_w"], dynamic_sum)
            or not np.allclose(float_fields["total_power_w"], static_sum + dynamic_sum)
        ):
            raise ValueError("ADC power sweep totals do not match their rail components")
        for name, value in float_fields.items():
            object.__setattr__(self, name, value)
        object.__setattr__(self, "observed_adc", observed_adc)


@dataclass(frozen=True, slots=True)
class AnalysisAdcPowerWaveform:
    """One aligned simulated conversion with rail power and timing context."""

    backend: Backend
    adc_index: int
    active_conversion_rate_hz: float
    active_duration_s: float
    time_s: FloatArray
    rail_power_w: FloatArray
    static_power_w: FloatArray
    active_power_w: FloatArray
    timing_high: BoolArray

    def __post_init__(self) -> None:
        time_s = _array_1d(self.time_s, np.float64, "time_s", finite=True)
        rail_power_w = _array_2d(self.rail_power_w, np.float64, "rail_power_w", finite=True)
        static_power_w = _array_1d(self.static_power_w, np.float64, "static_power_w", finite=True)
        active_power_w = _array_1d(self.active_power_w, np.float64, "active_power_w", finite=True)
        timing_high = _array_2d(self.timing_high, np.bool_, "timing_high")
        if rail_power_w.shape != (3, len(time_s)):
            raise ValueError("ADC power waveform requires three rail traces aligned with time")
        if static_power_w.shape != (3,) or active_power_w.shape != (3,):
            raise ValueError("ADC power waveform requires three static and active rail averages")
        if timing_high.shape != (4, len(time_s)):
            raise ValueError("ADC power waveform requires four timing traces aligned with time")
        if len(time_s) < 2 or np.any(np.diff(time_s) <= 0.0):
            raise ValueError("ADC power waveform time must contain at least two increasing samples")
        if self.backend not in ("physical", "behavioral", "spice"):
            raise ValueError(f"unsupported ADC power waveform backend {self.backend!r}")
        if (
            not -1 <= self.adc_index < 16
            or not math.isfinite(self.active_conversion_rate_hz)
            or self.active_conversion_rate_hz <= 0.0
            or not math.isfinite(self.active_duration_s)
            or self.active_duration_s <= 0.0
        ):
            raise ValueError("ADC power waveform rate and duration must be positive")
        if (
            np.any(static_power_w < 0.0)
            or np.any(active_power_w < static_power_w)
            or not np.isclose(self.active_duration_s * self.active_conversion_rate_hz, 1.0)
            or time_s[0] > 0.0
            or time_s[-1] < self.active_duration_s
        ):
            raise ValueError("ADC power waveform averages and displayed interval are inconsistent")
        object.__setattr__(self, "time_s", time_s)
        object.__setattr__(self, "rail_power_w", rail_power_w)
        object.__setattr__(self, "static_power_w", static_power_w)
        object.__setattr__(self, "active_power_w", active_power_w)
        object.__setattr__(self, "timing_high", timing_high)


@dataclass(frozen=True, slots=True)
class AnalysisAdcDecisionPaths:
    """Running SAR estimates reconstructed from selected decision records."""

    selection: Literal["single", "same_dout", "all"]
    conversion_index: IntArray
    final_dout: IntArray
    bout: Uint8Array
    weights: FloatArray
    estimate_dout: FloatArray

    def __post_init__(self) -> None:
        if self.selection not in ("single", "same_dout", "all"):
            raise ValueError(f"unknown decision-path selection {self.selection!r}")
        conversion_index = _array_1d(self.conversion_index, np.int64, "conversion_index")
        final_dout = _array_1d(self.final_dout, np.int64, "final_dout")
        bout = _array_2d(self.bout, np.uint8, "bout")
        weights = _array_1d(self.weights, np.float64, "weights", finite=True)
        estimate_dout = _array_2d(self.estimate_dout, np.float64, "estimate_dout", finite=True)
        if _aligned_length({"conversion_index": conversion_index, "final_dout": final_dout, "bout": bout}) == 0:
            raise ValueError("ADC decision paths require at least one conversion")
        if (
            len(weights) != 17
            or bout.shape[1] != len(weights)
            or np.any(weights <= 0.0)
            or np.any((bout != 0) & (bout != 1))
        ):
            raise ValueError("ADC decision paths require 17 positive weights and aligned binary decisions")
        if estimate_dout.shape != (len(conversion_index), len(weights) + 1):
            raise ValueError("ADC running estimates must align with conversions and decisions")
        if np.any(conversion_index < 0) or np.any(np.diff(conversion_index) <= 0) or np.any(final_dout < 0):
            raise ValueError("ADC decision-path indices and final codes must be nonnegative and ordered")
        object.__setattr__(self, "conversion_index", conversion_index)
        object.__setattr__(self, "final_dout", final_dout)
        object.__setattr__(self, "bout", bout)
        object.__setattr__(self, "weights", weights)
        object.__setattr__(self, "estimate_dout", estimate_dout)


@dataclass(frozen=True, slots=True)
class AnalysisCompOffsetNoise:
    """Comparator decision probability, offset, and input-referred noise."""

    vin_diff_v: FloatArray
    decision_probability: FloatArray
    trial_count: IntArray
    offset_v: float
    noise_sigma_v: float
    decision_polarity: Literal[-1, 1] = 1
    validity: Literal["valid", "unbracketed", "non_monotonic", "stuck-low", "stuck-high"] = "valid"

    def __post_init__(self) -> None:
        vin_diff_v = _array_1d(self.vin_diff_v, np.float64, "vin_diff_v", finite=True)
        probability = _array_1d(self.decision_probability, np.float64, "decision_probability", finite=True)
        trial_count = _array_1d(self.trial_count, np.int64, "trial_count")
        if (
            _aligned_length({"vin_diff_v": vin_diff_v, "decision_probability": probability, "trial_count": trial_count})
            == 0
        ):
            raise ValueError("comparator offset/noise analysis requires at least one input point")
        if np.any(np.diff(vin_diff_v) <= 0.0):
            raise ValueError("comparator differential inputs must be strictly increasing")
        if np.any((probability < 0.0) | (probability > 1.0)) or np.any(trial_count <= 0):
            raise ValueError("comparator probabilities and trial counts are outside their valid ranges")
        if self.decision_polarity not in (-1, 1):
            raise ValueError("comparator decision polarity must be -1 or 1")
        if self.validity not in ("valid", "unbracketed", "non_monotonic", "stuck-low", "stuck-high"):
            raise ValueError(f"unknown comparator fit validity {self.validity!r}")
        if self.validity == "valid" and (
            not math.isfinite(self.offset_v) or not math.isfinite(self.noise_sigma_v) or self.noise_sigma_v <= 0.0
        ):
            raise ValueError("a valid comparator fit requires finite offset and positive noise")
        if self.validity != "valid" and (math.isinf(self.offset_v) or math.isinf(self.noise_sigma_v)):
            raise ValueError("invalid comparator fits may use NaN but not infinite results")
        if math.isfinite(self.noise_sigma_v) and self.noise_sigma_v <= 0.0:
            raise ValueError("finite comparator noise must be positive")
        object.__setattr__(self, "vin_diff_v", vin_diff_v)
        object.__setattr__(self, "decision_probability", probability)
        object.__setattr__(self, "trial_count", trial_count)


@dataclass(frozen=True, slots=True)
class AnalysisCdacCapMismatch:
    """A-to-B transition fits and normalized main/difference capacitances."""

    adc_index: int
    expected_effective_fraction: FloatArray
    curve_element: IntArray
    curve_side: Uint8Array
    curve_direction: Uint8Array
    curve_diffcaps: Uint8Array
    transition_v: FloatArray
    normalized_step: FloatArray
    curve_valid: Uint8Array
    main_fraction: FloatArray
    diff_fraction: FloatArray
    effective_fraction: FloatArray
    effective_fraction_by_direction: FloatArray
    direction_bias: FloatArray

    def __post_init__(self) -> None:
        expected = _array_1d(
            self.expected_effective_fraction,
            np.float64,
            "expected_effective_fraction",
            finite=True,
        )
        curves = {
            "curve_element": _array_1d(self.curve_element, np.int64, "curve_element"),
            "curve_side": _array_1d(self.curve_side, np.uint8, "curve_side"),
            "curve_direction": _array_1d(self.curve_direction, np.uint8, "curve_direction"),
            "curve_diffcaps": _array_1d(self.curve_diffcaps, np.uint8, "curve_diffcaps"),
            "transition_v": _array_1d(self.transition_v, np.float64, "transition_v"),
            "normalized_step": _array_1d(self.normalized_step, np.float64, "normalized_step"),
            "curve_valid": _array_1d(self.curve_valid, np.uint8, "curve_valid"),
        }
        if _aligned_length(curves) == 0:
            raise ValueError("CDAC mismatch analysis requires at least one fitted curve")
        matrices = {
            name: _array_2d(getattr(self, name), np.float64, name)
            for name in ("main_fraction", "diff_fraction", "effective_fraction")
        }
        element_count = len(expected)
        if not element_count or any(values.shape != (2, element_count) for values in matrices.values()):
            raise ValueError("CDAC mismatch matrices must contain two sides and all expected elements")
        effective_by_direction = np.ascontiguousarray(self.effective_fraction_by_direction, dtype=np.float64)
        direction_bias = np.ascontiguousarray(self.direction_bias, dtype=np.float64)
        if effective_by_direction.shape != (2, element_count, 2) or direction_bias.shape != (2, element_count, 2):
            raise ValueError("CDAC direction results must contain two directions per side and element")
        if not 0 <= self.adc_index < 16:
            raise ValueError("CDAC mismatch ADC index must be in 0..15")
        if np.any(expected <= 0.0):
            raise ValueError("expected CDAC effective fractions must be positive")
        if np.any(curves["curve_element"] < 0) or np.any(curves["curve_element"] >= element_count):
            raise ValueError("CDAC curve element is outside the analyzed array")
        for name in ("curve_side", "curve_direction", "curve_diffcaps", "curve_valid"):
            if np.any((curves[name] != 0) & (curves[name] != 1)):
                raise ValueError(f"{name} must be binary")
        floating_results = (
            curves["transition_v"],
            curves["normalized_step"],
            *matrices.values(),
            effective_by_direction,
            direction_bias,
        )
        if any(np.any(np.isinf(values)) for values in floating_results):
            raise ValueError("CDAC mismatch results may use NaN but not infinity")
        valid_curves = curves["curve_valid"].astype(bool)
        if not np.all(np.isfinite(curves["transition_v"][valid_curves])) or not np.all(
            np.isfinite(curves["normalized_step"][valid_curves])
        ):
            raise ValueError("valid CDAC mismatch curves require finite fit results")
        object.__setattr__(self, "expected_effective_fraction", expected)
        for name, values in curves.items():
            object.__setattr__(self, name, values)
        for name, values in matrices.items():
            object.__setattr__(self, name, values)
        object.__setattr__(self, "effective_fraction_by_direction", effective_by_direction)
        object.__setattr__(self, "direction_bias", direction_bias)


@dataclass(frozen=True, slots=True)
class AnalysisCompTiming:
    """Comparator timing and metastability results across measurements."""

    source_index: IntArray
    trial_index: IntArray
    clock_to_decision_s: FloatArray
    settling_s: FloatArray
    unresolved: Uint8Array

    def __post_init__(self) -> None:
        values = {
            "source_index": _array_1d(self.source_index, np.int64, "source_index"),
            "trial_index": _array_1d(self.trial_index, np.int64, "trial_index"),
            "clock_to_decision_s": _array_1d(self.clock_to_decision_s, np.float64, "clock_to_decision_s"),
            "settling_s": _array_1d(self.settling_s, np.float64, "settling_s"),
            "unresolved": _array_1d(self.unresolved, np.uint8, "unresolved"),
        }
        if _aligned_length(values) == 0:
            raise ValueError("comparator timing analysis requires at least one trial")
        if np.any((values["unresolved"] != 0) & (values["unresolved"] != 1)):
            raise ValueError("comparator unresolved flags must be binary")
        timing_values = (values["clock_to_decision_s"], values["settling_s"])
        if (
            np.any(values["source_index"] < 0)
            or np.any(values["trial_index"] < 0)
            or any(np.any(np.isinf(result)) for result in timing_values)
            or any(np.any(result[np.isfinite(result)] < 0.0) for result in timing_values)
        ):
            raise ValueError("comparator timing indices and finite durations must be nonnegative")
        for name, value in values.items():
            object.__setattr__(self, name, value)


@dataclass(frozen=True, slots=True)
class AnalysisCompPower:
    """Comparator average consumed power per measurement."""

    source_index: IntArray
    supply_v: FloatArray
    average_power_w: FloatArray
    energy_per_decision_j: FloatArray

    def __post_init__(self) -> None:
        values = {
            "source_index": _array_1d(self.source_index, np.int64, "source_index"),
            "supply_v": _array_1d(self.supply_v, np.float64, "supply_v", finite=True),
            "average_power_w": _array_1d(self.average_power_w, np.float64, "average_power_w", finite=True),
            "energy_per_decision_j": _array_1d(
                self.energy_per_decision_j,
                np.float64,
                "energy_per_decision_j",
            ),
        }
        if _aligned_length(values) == 0:
            raise ValueError("comparator power analysis requires at least one measurement")
        energy = values["energy_per_decision_j"]
        if (
            np.any(values["source_index"] < 0)
            or np.any(values["supply_v"] <= 0.0)
            or np.any(values["average_power_w"] < 0.0)
            or np.any(np.isinf(energy))
            or np.any(energy[np.isfinite(energy)] < 0.0)
        ):
            raise ValueError("comparator power indices, supplies, powers, and finite energies are invalid")
        for name, value in values.items():
            object.__setattr__(self, name, value)


@dataclass(frozen=True, slots=True)
class AnalysisCompCandidateSweep:
    """Aligned candidate-level noise, power, and settling metrics."""

    candidate_id: tuple[str, ...]
    candidate_label: tuple[str, ...]
    size_profile: tuple[str, ...]
    validity: tuple[str, ...]
    topology_index: IntArray
    total_width_units: IntArray
    total_active_area_units: IntArray
    total_active_area_um2: FloatArray
    device_count: IntArray
    offset_v: FloatArray
    noise_sigma_v: FloatArray
    average_power_w: FloatArray
    energy_per_decision_j: FloatArray
    maximum_clock_to_decision_s: FloatArray
    maximum_settling_s: FloatArray
    unresolved_fraction: FloatArray

    def __post_init__(self) -> None:
        integer_fields = {
            name: _array_1d(getattr(self, name), np.int64, name)
            for name in (
                "topology_index",
                "total_width_units",
                "total_active_area_units",
                "device_count",
            )
        }
        float_fields = {
            name: _array_1d(getattr(self, name), np.float64, name)
            for name in (
                "total_active_area_um2",
                "offset_v",
                "noise_sigma_v",
                "average_power_w",
                "energy_per_decision_j",
                "maximum_clock_to_decision_s",
                "maximum_settling_s",
                "unresolved_fraction",
            )
        }
        candidate_count = _aligned_length({**integer_fields, **float_fields})
        text_fields = {
            name: tuple(getattr(self, name)) for name in ("candidate_id", "candidate_label", "size_profile", "validity")
        }
        if not candidate_count or any(len(values) != candidate_count for values in text_fields.values()):
            raise ValueError("comparator candidate fields must be nonempty and aligned")
        if (
            any(not isinstance(value, str) or not value.strip() for values in text_fields.values() for value in values)
            or len(set(text_fields["candidate_id"])) != candidate_count
        ):
            raise ValueError("comparator candidate text fields must be nonempty and IDs must be unique")
        if any(profile not in ("half", "double", "fabricated") for profile in text_fields["size_profile"]):
            raise ValueError("comparator candidate size profile is unknown")
        validities = {"valid", "unbracketed", "non_monotonic", "stuck-low", "stuck-high"}
        if any(validity not in validities for validity in text_fields["validity"]):
            raise ValueError("comparator candidate fit validity is unknown")
        if np.any(np.diff(integer_fields["total_active_area_units"]) < 0):
            raise ValueError("comparator candidates must be ordered by active transistor area")
        if (
            np.any(integer_fields["topology_index"] < 0)
            or np.any(integer_fields["total_width_units"] <= 0)
            or np.any(integer_fields["total_active_area_units"] <= 0)
            or np.any(integer_fields["device_count"] <= 0)
            or not np.all(np.isfinite(float_fields["total_active_area_um2"]))
            or np.any(float_fields["total_active_area_um2"] <= 0.0)
        ):
            raise ValueError("comparator candidate area and device counts must be positive")
        nullable_nonnegative = (
            "noise_sigma_v",
            "average_power_w",
            "energy_per_decision_j",
            "maximum_clock_to_decision_s",
            "maximum_settling_s",
        )
        if any(np.any(np.isinf(values)) for values in float_fields.values()) or any(
            np.any(float_fields[name][np.isfinite(float_fields[name])] < 0.0) for name in nullable_nonnegative
        ):
            raise ValueError("comparator candidate metrics may use NaN but finite magnitudes must be nonnegative")
        unresolved = float_fields["unresolved_fraction"]
        if not np.all(np.isfinite(unresolved)) or np.any((unresolved < 0.0) | (unresolved > 1.0)):
            raise ValueError("comparator unresolved fractions must be finite probabilities")
        for name, values in {**integer_fields, **float_fields, **text_fields}.items():
            object.__setattr__(self, name, values)


MEASUREMENT_TYPES = {
    cls.__name__: cls
    for cls in (MeasAdcExt, MeasAdcInt, MeasCompExt, MeasCompInt, MeasSampInt, MeasCdacExt, MeasCdacInt)
}
