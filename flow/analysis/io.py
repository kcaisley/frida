"""Typed HDF5 measurement I/O and acquisition-wave adapters."""

from __future__ import annotations

import dataclasses
import importlib
import math
import sys
from collections.abc import Mapping, Sequence
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
    CdacExtDaq,
    CdacExtWave,
    CdacIntDaq,
    CdacIntWave,
    CompDaq,
    CompExtWave,
    CompIntWave,
    MeasAdcExt,
    MeasAdcInt,
    MeasCdacExt,
    MeasCdacInt,
    MeasCompExt,
    MeasCompInt,
    MeasInfo,
    MeasSampInt,
    Measurement,
    SampDaq,
    SampIntWave,
)


def _dataclass_fields(value) -> tuple[Any, ...]:
    """Return fields for standard dataclasses and HDL21 parameter classes."""

    return tuple(value.__dataclass_fields__.values())


# =============================================================================
# Typed HDF5 measurement format
# =============================================================================


SECTION_TYPES = {
    MeasAdcExt.__name__: (AdcDaq, AdcExtWave),
    MeasAdcInt.__name__: (AdcDaq, AdcIntWave),
    MeasCompExt.__name__: (CompDaq, CompExtWave),
    MeasCompInt.__name__: (CompDaq, CompIntWave),
    MeasSampInt.__name__: (SampDaq, SampIntWave),
    MeasCdacExt.__name__: (CdacExtDaq, CdacExtWave),
    MeasCdacInt.__name__: (CdacIntDaq, CdacIntWave),
}


def _qualified_type(value_type: type) -> str:
    module_name = value_type.__module__
    if module_name in {"__main__", "__mp_main__"}:
        module_spec = getattr(sys.modules.get(module_name), "__spec__", None)
        if module_spec is None or not module_spec.name:
            raise ValueError("persisted parameter types must be defined in an importable module")
        module_name = module_spec.name
    return f"{module_name}:{value_type.__qualname__}"


def _resolve_type(name: str) -> type:
    module_name, qualname = name.split(":", 1)
    # Stored captures predate the cdac -> caparray module/API rename. Keep
    # migration at the persistence boundary, not via legacy Python imports.
    if module_name in {"flow.cdac.subckt", "flow.cdac.sim", "flow.cdac.laygen"}:
        module_name = module_name.replace("flow.cdac", "flow.caparray", 1)
        qualname = {
            "CdacParams": "CapArrayConfig",
            "CdacArrayParams": "CapArrayParams",
            "CdacLayoutParams": "CapArrayLayoutParams",
            "CdacTbParams": "CapArrayTbParams",
        }.get(qualname, qualname)
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
            if not issubclass(enum_type, Enum):
                raise TypeError(f"persisted enum type {enum_type.__name__!r} is not an Enum")
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
        values = {}
        missing = []
        for data_field in _dataclass_fields(value_type):
            if data_field.name in node:
                values[data_field.name] = _read_native(node[data_field.name])
            elif data_field.default is not dataclasses.MISSING:
                values[data_field.name] = data_field.default
            elif data_field.default_factory is not dataclasses.MISSING:
                values[data_field.name] = data_field.default_factory()
            else:
                missing.append(data_field.name)
        if missing:
            raise ValueError(f"{node.name} is missing required parameter fields {missing}")
        if value_type.__module__ == "flow.adc.sim" and value_type.__name__ == "AdcTbParams":
            for signal in ("init", "samp", "comp", "logic"):
                old_field = f"seq_{signal}_phase_delay_symbols"
                if old_field not in node:
                    continue
                phase = float(_read_native(node[old_field]))
                if not math.isfinite(phase) or not phase.is_integer():
                    raise ValueError("saved fractional sequencer delays cannot be represented by binary rows")
                field = f"seq_{signal}_pattern"
                row = values[field]
                shift = int(phase) % len(row)
                values[field] = row[-shift:] + row[:-shift] if shift else row
        return value_type(**values)
    raise ValueError(f"unsupported HDF5 value kind {kind!r} at {node.name}")


def _write_section(parent: h5py.File, name: str, section) -> None:
    group = parent.create_group(name)
    if section is None:
        group.attrs["_kind"] = "none"
        return
    group.attrs["_type"] = _qualified_type(type(section))
    for data_field in dataclasses.fields(section):
        value = getattr(section, data_field.name)
        if value is None:
            continue
        if isinstance(value, Mapping):
            traces = group.create_group(data_field.name)
            for key, trace in value.items():
                _create_dataset(traces, key, trace, wave=name == "wave")
        else:
            _create_dataset(group, data_field.name, value, wave=name == "wave")


def _read_section(group: h5py.Group, section_type: type):
    if group.attrs.get("_kind") == "none":
        return None
    values = {}
    missing = []
    for data_field in _dataclass_fields(section_type):
        if data_field.name in group:
            node = group[data_field.name]
            values[data_field.name] = (
                {key: np.asarray(node[key][()]) for key in node}
                if isinstance(node, h5py.Group)
                else np.asarray(node[()])
            )
        elif data_field.default is dataclasses.MISSING and data_field.default_factory is dataclasses.MISSING:
            missing.append(data_field.name)
    if missing:
        raise ValueError(f"{group.name} is missing required datasets {missing}")
    return section_type(**values)


def write_measurement(path: Path, msmt: Measurement) -> Path:
    """Write one typed physical, behavioral, or SPICE measurement."""

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_name(f".{path.name}.tmp")
    temporary_path.unlink(missing_ok=True)
    try:
        with h5py.File(temporary_path, "w") as output:
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
        temporary_path.replace(path)
    finally:
        temporary_path.unlink(missing_ok=True)
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
        waveform_source = info.readbacks.get("waveform_source_h5")
        if isinstance(waveform_source, str) and not Path(waveform_source).is_file():
            raise FileNotFoundError(f"linked waveform source is unavailable: {waveform_source}")
        wave = _read_section(input_file["wave"], wave_type)
    return measurement_class(info=info, param=param, daq=daq, wave=wave)


def interpolate_wave_records(
    time_s: Sequence[float] | np.ndarray,
    signals: Mapping[str, Sequence[float] | np.ndarray],
    windows_s: Sequence[tuple[float, float]],
    sample_interval_s: float,
) -> tuple[np.ndarray, dict[str, np.ndarray]]:
    """Interpolate adaptive-time simulation data onto uniform relative records."""

    source_time = np.asarray(time_s, dtype=np.float64)
    if source_time.ndim != 1 or len(source_time) < 2 or np.any(np.diff(source_time) <= 0):
        raise ValueError("source time must be one-dimensional and strictly increasing")
    if not np.isfinite(sample_interval_s) or sample_interval_s <= 0:
        raise ValueError("sample_interval_s must be finite and positive")
    normalized_signals = {name: np.asarray(values, dtype=np.float64) for name, values in signals.items()}
    if any(values.shape != source_time.shape for values in normalized_signals.values()):
        raise ValueError("all adaptive-time signals must align with source time")
    durations = np.asarray([stop - start for start, stop in windows_s], dtype=np.float64)
    if len(durations) == 0 or np.any(durations <= 0) or not np.allclose(durations, durations[0]):
        raise ValueError("waveform windows must be non-empty and have equal positive duration")
    # Use a half-open [0, duration) grid so adjacent waveform records do not
    # duplicate their shared boundary sample.
    sample_count = int(np.ceil(durations[0] / sample_interval_s))
    if sample_count < 2:
        raise ValueError("sample_interval_s must provide at least two samples per record")
    relative_time = np.arange(sample_count, dtype=np.float64) * sample_interval_s
    records = {name: [] for name in normalized_signals}
    for start, stop in windows_s:
        if start < source_time[0] or stop > source_time[-1]:
            raise ValueError(f"waveform window {(start, stop)} lies outside source time")
        sample_times = start + relative_time
        for name, values in normalized_signals.items():
            records[name].append(np.interp(sample_times, source_time, values))
    return relative_time, {name: np.stack(values) for name, values in records.items()}
