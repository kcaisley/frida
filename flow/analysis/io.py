"""Typed HDF5 measurement I/O and raw simulator/ scope adapters."""

from __future__ import annotations

import dataclasses
import importlib
import math
import sys
from collections.abc import Iterable, Mapping, Sequence
from datetime import datetime
from decimal import Decimal
from enum import Enum
from pathlib import Path
from typing import Any, cast

import h5py
import numpy as np
from hdl21.prefix import Prefix, Prefixed

from flow.analysis.types import (
    MEASUREMENT_TYPES,
    AdcDaq,
    AdcExtWave,
    AdcIntWave,
    Backend,
    CompDaq,
    CompExtWave,
    CompIntWave,
    DacExtDaq,
    DacExtWave,
    DacIntDaq,
    DacIntWave,
    MeasAdcExt,
    MeasAdcInt,
    MeasCompExt,
    MeasCompInt,
    MeasDacExt,
    MeasDacInt,
    MeasInfo,
    MeasSampInt,
    Measurement,
    SampDaq,
    SampIntWave,
)


def _dataclass_fields(value) -> tuple[Any, ...]:
    """Return fields for standard dataclasses and HDL21 parameter classes."""

    return tuple(value.__dataclass_fields__.values())


def _spectre_variable_names(header_lines: Sequence[str], path: Path) -> list[str]:
    """Extract the ordered NUTASCII variable list from its header."""

    variable_names: list[str] = []
    in_variables = False
    for line in header_lines:
        parts = line.strip().split()
        if not parts:
            continue
        if parts[0] == "Variables:":
            in_variables = True
            if len(parts) >= 4 and parts[1].isdigit():
                variable_names.append(parts[2])
            continue
        if in_variables:
            if parts[0].isdigit() and len(parts) >= 3:
                variable_names.append(parts[1])
            elif not parts[0].isdigit():
                in_variables = False
    if not variable_names:
        raise ValueError(f"could not parse variable list from {path}")
    return variable_names


def _spectre_values(
    lines: Iterable[str],
    variable_names: Sequence[str],
    selected_signals: set[str] | None,
    path: Path,
) -> dict[str, np.ndarray]:
    """Parse the NUTASCII value section for selected variables."""

    selected = selected_signals or set(variable_names)
    selected_indices = {index: name for index, name in enumerate(variable_names) if name in selected}
    parsed: dict[str, list[float]] = {name: [] for name in selected_indices.values()}
    stride = len(variable_names) + 1
    tokens: list[str] = []
    point_count = 0
    for line in lines:
        tokens.extend(line.split())
        while len(tokens) >= stride:
            point_tokens = tokens[:stride]
            del tokens[:stride]
            for index, name in selected_indices.items():
                parsed[name].append(float(point_tokens[1 + index]))
            point_count += 1
    if point_count == 0:
        raise ValueError(f"no raw data points parsed from {path}")
    if tokens:
        print(
            f"warning: ignoring {len(tokens)} trailing NUTASCII tokens in {path}",
            file=sys.stderr,
        )
    return {name: np.asarray(values, dtype=np.float64) for name, values in parsed.items()}


def parse_spectre_nutascii(
    path: Path,
    selected_signals: set[str] | None = None,
) -> dict[str, np.ndarray]:
    """Parse a Spectre NUTASCII raw file into named one-dimensional arrays."""

    header_lines: list[str] = []
    with path.open(errors="replace") as input_file:
        for line in input_file:
            if line.strip() == "Values:":
                break
            header_lines.append(line)
        else:
            raise ValueError(f"{path} does not look like complete NUTASCII output: missing 'Values:' section")
        variable_names = _spectre_variable_names(header_lines, path)
        return _spectre_values(
            input_file,
            variable_names,
            selected_signals,
            path,
        )


# =============================================================================
# Typed HDF5 measurement format
# =============================================================================


SECTION_TYPES = {
    MeasAdcExt.__name__: (AdcDaq, AdcExtWave),
    MeasAdcInt.__name__: (AdcDaq, AdcIntWave),
    MeasCompExt.__name__: (CompDaq, CompExtWave),
    MeasCompInt.__name__: (CompDaq, CompIntWave),
    MeasSampInt.__name__: (SampDaq, SampIntWave),
    MeasDacExt.__name__: (DacExtDaq, DacExtWave),
    MeasDacInt.__name__: (DacIntDaq, DacIntWave),
}


def _qualified_type(value_type: type) -> str:
    return f"{value_type.__module__}:{value_type.__qualname__}"


def _resolve_type(name: str) -> type:
    module_name, qualname = name.split(":", 1)
    value = importlib.import_module(module_name)
    for part in qualname.split("."):
        value = getattr(value, part)
    if not isinstance(value, type):
        raise TypeError(f"{name!r} does not resolve to a type")
    return value


def _decode_string(value):
    if isinstance(value, bytes):
        return value.decode()
    return value


def _create_dataset(parent: h5py.Group, name: str, value, *, wave: bool = False) -> h5py.Dataset:
    """Create one scalar or array dataset with useful waveform chunking."""

    array = np.asarray(value)
    kwargs = {}
    if array.ndim and array.size:
        kwargs["compression"] = "gzip"
        if wave and array.ndim >= 2:
            kwargs["chunks"] = (1, *array.shape[1:])
    if array.dtype.kind in {"U", "O"}:
        string_dtype = h5py.string_dtype("utf-8")
        return parent.create_dataset(name, data=np.asarray(value, dtype=object), dtype=string_dtype, **kwargs)
    return parent.create_dataset(name, data=value, **kwargs)


def _write_native(parent: h5py.Group, name: str, value) -> None:
    """Write one nested parameter or run-information value natively to HDF5."""

    if value is None:
        group = parent.create_group(name)
        group.attrs["_kind"] = "none"
        return
    if isinstance(value, Prefixed):
        dataset = _create_dataset(parent, name, str(value.number))
        dataset.attrs["_kind"] = "prefixed"
        dataset.attrs["_prefix"] = value.prefix.name
        return
    if isinstance(value, Enum):
        dataset = _create_dataset(parent, name, value.name)
        dataset.attrs["_kind"] = "enum"
        dataset.attrs["_type"] = _qualified_type(type(value))
        return
    if isinstance(value, Path):
        dataset = _create_dataset(parent, name, str(value))
        dataset.attrs["_kind"] = "path"
        return
    if isinstance(value, datetime):
        dataset = _create_dataset(parent, name, value.isoformat())
        dataset.attrs["_kind"] = "datetime"
        return
    if dataclasses.is_dataclass(value):
        group = parent.create_group(name)
        group.attrs["_kind"] = "dataclass"
        group.attrs["_type"] = _qualified_type(type(value))
        for data_field in dataclasses.fields(value):
            _write_native(group, data_field.name, getattr(value, data_field.name))
        return
    if isinstance(value, Mapping):
        group = parent.create_group(name)
        group.attrs["_kind"] = "mapping"
        for key, item in value.items():
            _write_native(group, str(key), item)
        return
    if isinstance(value, (tuple, list)):
        array = np.asarray(value)
        if array.ndim == 1 and array.dtype.kind != "O":
            dataset = _create_dataset(parent, name, array)
            dataset.attrs["_kind"] = "tuple" if isinstance(value, tuple) else "list"
            return
        group = parent.create_group(name)
        group.attrs["_kind"] = "tuple" if isinstance(value, tuple) else "list"
        for index, item in enumerate(value):
            _write_native(group, str(index), item)
        return
    if isinstance(value, np.generic):
        value = value.item()
    if isinstance(value, (bool, int, float, str, np.ndarray)):
        if isinstance(value, float) and not math.isfinite(value):
            raise ValueError(f"cannot persist non-finite scalar {value!r}")
        _create_dataset(parent, name, value)
        return
    raise TypeError(f"cannot persist {type(value).__name__} in measurement HDF5")


def _read_native(node: h5py.Group | h5py.Dataset):
    """Read one value written by :func:`_write_native`."""

    kind = _decode_string(node.attrs.get("_kind", ""))
    if isinstance(node, h5py.Dataset):
        value = node[()]
        if isinstance(value, np.ndarray) and value.dtype.kind in {"S", "O"}:
            value = value.astype(str)
        elif isinstance(value, bytes):
            value = value.decode()
        elif isinstance(value, np.generic):
            value = value.item()
        if kind == "enum":
            enum_type = _resolve_type(_decode_string(node.attrs["_type"]))
            return enum_type[value]
        if kind == "path":
            return Path(value)
        if kind == "datetime":
            return datetime.fromisoformat(value)
        if kind == "prefixed":
            return Prefixed.new(
                Decimal(value),
                Prefix[_decode_string(node.attrs["_prefix"])],
            )
        if kind == "tuple":
            return tuple(value.tolist())
        if kind == "list":
            return value.tolist()
        return value

    if kind == "none":
        return None
    if kind in {"tuple", "list"}:
        values = [_read_native(node[key]) for key in sorted(node, key=int)]
        return tuple(values) if kind == "tuple" else values
    if kind == "mapping":
        return {key: _read_native(node[key]) for key in node}
    if kind == "dataclass":
        value_type = _resolve_type(_decode_string(node.attrs["_type"]))
        return value_type(
            **{data_field.name: _read_native(node[data_field.name]) for data_field in _dataclass_fields(value_type)}
        )
    raise ValueError(f"unsupported HDF5 value kind {kind!r} at {node.name}")


def _write_section(parent: h5py.File, name: str, section) -> None:
    group = parent.create_group(name)
    group.attrs["_type"] = _qualified_type(type(section))
    for data_field in dataclasses.fields(section):
        value = getattr(section, data_field.name)
        if value is None:
            continue
        _create_dataset(group, data_field.name, value, wave=name == "wave")


def _read_section(group: h5py.Group, section_type: type):
    values = {}
    missing = []
    for data_field in _dataclass_fields(section_type):
        if data_field.name in group:
            values[data_field.name] = np.asarray(group[data_field.name][()])
        elif data_field.default is dataclasses.MISSING and data_field.default_factory is dataclasses.MISSING:
            missing.append(data_field.name)
    if missing:
        raise ValueError(f"{group.name} is missing required datasets {missing}")
    return section_type(**values)


def write_measurement(path: Path, msmt: Measurement) -> Path:
    """Write one typed physical, behavioral, or SPICE measurement."""

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with h5py.File(path, "w") as output:
        info = output.create_group("info")
        _write_native(info, "schema_version", msmt.info.schema_version)
        _write_native(info, "measurement_type", msmt.info.measurement_type)
        _write_native(info, "backend", msmt.info.backend)
        _write_native(info, "timestamp_utc", msmt.info.timestamp_utc)
        _write_native(info, "instruments", msmt.info.instruments)
        _write_native(info, "readbacks", msmt.info.readbacks)
        param = output.create_group("param")
        param.attrs["_kind"] = "dataclass"
        param.attrs["_type"] = _qualified_type(type(msmt.param))
        for data_field in _dataclass_fields(msmt.param):
            _write_native(param, data_field.name, getattr(msmt.param, data_field.name))
        _write_section(output, "daq", msmt.daq)
        _write_section(output, "wave", msmt.wave)
    return path


def read_measurement(path: Path) -> Measurement:
    """Read one HDF5 file into its concrete typed in-memory measurement."""

    path = Path(path)
    with h5py.File(path, "r") as input_file:
        required_groups = {"info", "param", "daq", "wave"}
        missing = sorted(required_groups.difference(input_file))
        if missing:
            raise ValueError(f"{path} is missing required HDF5 groups {missing}")
        info_group = input_file["info"]
        required_info = {
            "schema_version",
            "measurement_type",
            "backend",
            "timestamp_utc",
            "instruments",
            "readbacks",
        }
        missing_info = sorted(required_info.difference(info_group))
        if missing_info:
            raise ValueError(f"{path} is missing required /info datasets {missing_info}")
        measurement_type = str(_read_native(info_group["measurement_type"]))
        try:
            measurement_class = MEASUREMENT_TYPES[measurement_type]
            daq_type, wave_type = SECTION_TYPES[measurement_type]
        except KeyError:
            raise ValueError(f"unsupported measurement type {measurement_type!r}") from None
        info = MeasInfo(
            schema_version=int(_read_native(info_group["schema_version"])),
            measurement_type=measurement_type,
            backend=cast(Backend, str(_read_native(info_group["backend"]))),
            timestamp_utc=_read_native(info_group["timestamp_utc"]),
            instruments=_read_native(info_group["instruments"]),
            readbacks=_read_native(info_group["readbacks"]),
            source_path=path,
        )
        param = _read_native(input_file["param"])
        daq = _read_section(input_file["daq"], daq_type)
        wave = _read_section(input_file["wave"], wave_type)
    return measurement_class(info=info, param=param, daq=daq, wave=wave)


def scope_records_to_adc_wave(
    records: Sequence[Mapping[int, Any]],
    conversion_index: Sequence[int],
    channels: Mapping[str, int],
) -> AdcExtWave:
    """Convert aligned triggered scope records into an external ADC wave section."""

    required = {"vin_diff_v", "seq_comp_v", "seq_logic_v", "comp_out_v"}
    if set(channels) != required:
        raise ValueError(f"scope channels must map exactly {sorted(required)}")
    if len(records) != len(conversion_index):
        raise ValueError("scope record count must match waveform conversion indices")

    time_s = None
    signals = {name: [] for name in required}
    for record_number, record in enumerate(records):
        missing_channels = sorted(set(channels.values()).difference(record))
        if missing_channels:
            raise ValueError(f"scope record {record_number} is missing channels {missing_channels}")
        reference = record[next(iter(channels.values()))]
        record_time = reference.x_scale.offset + np.arange(len(reference.data)) * reference.x_scale.slope
        if time_s is None:
            time_s = record_time
        elif not np.array_equal(record_time, time_s):
            raise ValueError(f"scope record {record_number} has a different time axis")
        for name, channel in channels.items():
            values = np.asarray(record[channel].data, dtype=np.float64)
            if len(values) != len(record_time):
                raise ValueError(f"scope record {record_number} channel {channel} is not aligned")
            signals[name].append(values)
    if time_s is None:
        raise ValueError("at least one scope record is required")
    return AdcExtWave(
        conversion_index=np.asarray(conversion_index),
        time_s=time_s,
        **{name: np.stack(values) for name, values in signals.items()},
    )


def interpolate_wave_records(
    time_s: Sequence[float] | np.ndarray,
    signals: Mapping[str, Sequence[float] | np.ndarray],
    windows_s: Sequence[tuple[float, float]],
    samples_per_record: int,
) -> tuple[np.ndarray, dict[str, np.ndarray]]:
    """Interpolate adaptive-time simulation data onto dense relative records."""

    source_time = np.asarray(time_s, dtype=np.float64)
    if source_time.ndim != 1 or len(source_time) < 2 or np.any(np.diff(source_time) <= 0):
        raise ValueError("source time must be one-dimensional and strictly increasing")
    if samples_per_record < 2:
        raise ValueError("samples_per_record must be at least two")
    normalized_signals = {name: np.asarray(values, dtype=np.float64) for name, values in signals.items()}
    if any(values.shape != source_time.shape for values in normalized_signals.values()):
        raise ValueError("all adaptive-time signals must align with source time")
    durations = np.asarray([stop - start for start, stop in windows_s], dtype=np.float64)
    if len(durations) == 0 or np.any(durations <= 0) or not np.allclose(durations, durations[0]):
        raise ValueError("waveform windows must be non-empty and have equal positive duration")
    relative_time = np.linspace(0.0, durations[0], samples_per_record)
    records = {name: [] for name in normalized_signals}
    for start, stop in windows_s:
        if start < source_time[0] or stop > source_time[-1]:
            raise ValueError(f"waveform window {(start, stop)} lies outside source time")
        sample_times = start + relative_time
        for name, values in normalized_signals.items():
            records[name].append(np.interp(sample_times, source_time, values))
    return relative_time, {name: np.stack(values) for name, values in records.items()}


def build_adc_interface_wave(
    params,
    bout: Sequence[int],
    *,
    conversion_index: int = 0,
    samples_per_symbol: int = 4,
) -> AdcExtWave:
    """Build one dense behavioral ADC-interface waveform from test parameters."""

    if samples_per_symbol <= 0:
        raise ValueError("samples_per_symbol must be positive")
    bout = np.asarray(bout, dtype=np.uint8)
    if bout.ndim != 1 or np.any((bout != 0) & (bout != 1)):
        raise ValueError("Bout must be one binary decision vector")

    sequence_length = len(params.seq_init_pattern)

    def shifted_pattern(name: str) -> np.ndarray:
        pattern = getattr(params, f"seq_{name}_pattern")
        phase = float(getattr(params, f"seq_{name}_phase_delay_symbols"))
        if not phase.is_integer():
            raise ValueError("behavioral interface wave requires whole-symbol phase offsets")
        shift = int(phase) % sequence_length
        if shift:
            pattern = pattern[-shift:] + pattern[:-shift]
        return np.repeat(
            np.fromiter((int(bit) for bit in pattern), dtype=np.uint8),
            samples_per_symbol,
        )

    seq_comp = shifted_pattern("comp")
    seq_logic = shifted_pattern("logic")
    comp_symbols = seq_comp.reshape(sequence_length, samples_per_symbol)[:, 0]
    falling_symbols = np.flatnonzero((comp_symbols[:-1] == 1) & (comp_symbols[1:] == 0)) + 1
    if len(falling_symbols) < len(bout):
        raise ValueError(
            f"sequencer has {len(falling_symbols)} comparator decisions, but Bout contains {len(bout)} bits"
        )
    comp_out_symbols = np.zeros(sequence_length, dtype=np.uint8)
    state = 0
    decision_index = 0
    for symbol in range(sequence_length):
        if decision_index < len(bout) and symbol == falling_symbols[decision_index]:
            state = int(bout[decision_index])
            decision_index += 1
        comp_out_symbols[symbol] = state

    symbol_period_s = 1.0 / float(params.symbol_rate)
    time_s = np.arange(sequence_length * samples_per_symbol, dtype=np.float64)
    time_s *= symbol_period_s / samples_per_symbol
    source = params.vin_diff
    if hasattr(source, "dc") and source.dc is not None:
        vin_diff_v = np.full_like(time_s, float(source.dc))
    elif hasattr(source, "voff") and source.voff is not None:
        vin_diff_v = np.full_like(time_s, float(source.voff))
        vin_diff_v += float(source.vamp) * np.sin(
            2.0 * np.pi * float(source.freq) * time_s + np.deg2rad(float(source.phase or 0.0))
        )
    else:
        vin_diff_v = np.zeros_like(time_s)
    logic_high_v = float(params.vdd_d.dc)
    return AdcExtWave(
        conversion_index=np.asarray([conversion_index], dtype=np.int64),
        time_s=time_s,
        vin_diff_v=vin_diff_v[None, :],
        seq_comp_v=(logic_high_v * seq_comp)[None, :],
        seq_logic_v=(logic_high_v * seq_logic)[None, :],
        comp_out_v=(logic_high_v * np.repeat(comp_out_symbols, samples_per_symbol))[None, :],
    )
