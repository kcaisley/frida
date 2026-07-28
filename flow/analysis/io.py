"""Typed acquisition rows plus backend-neutral result adapters."""

from __future__ import annotations

import csv
import dataclasses
import hashlib
import json
import math
import sys
from enum import Enum
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from hdl21.prefix import Prefixed
import numpy as np

from flow.analysis.models import (
    AdcConversion,
    DataColumn,
    DataTable,
    RunData,
    SourceFormat,
    SourceSpec,
)


def read_adc_conversions(path: Path) -> list[AdcConversion]:
    """Read one acquisition CSV into typed conversion rows."""

    with path.open(newline="") as input_file:
        return [AdcConversion.from_csv_row(row) for row in csv.DictReader(input_file)]


def to_json_data(value: Any) -> Any:
    """Convert nested HDL21 parameters and scan metadata to JSON data."""

    if value is None or isinstance(value, (bool, int, str)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError(f"cannot serialize non-finite value {value!r}")
        return value
    if isinstance(value, Prefixed):
        return to_json_data(float(value))
    if isinstance(value, np.generic):
        return to_json_data(value.item())
    if isinstance(value, np.ndarray):
        return [to_json_data(item) for item in value.tolist()]
    if isinstance(value, Enum):
        return value.name
    if isinstance(value, Path):
        return str(value)
    if dataclasses.is_dataclass(value):
        data = {field.name: to_json_data(getattr(value, field.name)) for field in dataclasses.fields(value)}
        data["type"] = type(value).__name__
        return data
    if isinstance(value, Mapping):
        return {str(key): to_json_data(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [to_json_data(item) for item in value]
    raise TypeError(f"cannot serialize {type(value).__name__} to manifest JSON")


def parameter_digest(params: Any) -> str:
    """Return a short stable identifier for one complete parameter object."""

    encoded = json.dumps(to_json_data(params), sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()[:8]


ADC_COLUMN_ALIASES = {
    "Bbits": "bout",
    "Dout": "dout",
    "Dout_raw": "dout_raw",
    "raw_word0": "raw_word",
    "id0": "identifier",
    "frame0": "frame",
    "spi0": "spi",
}


def _column_unit(name: str) -> str:
    """Infer SI display units from one canonical column name."""

    suffix_units = {
        "_s": "s",
        "_hz": "Hz",
        "_v": "V",
        "_a": "A",
        "_w": "W",
        "_f": "F",
        "_ohm": "Ω",
        "_codes": "LSB",
        "_db": "dB",
        "_dbfs": "dBFS",
        "_bits": "bit",
    }
    for suffix, unit in suffix_units.items():
        if name.lower().endswith(suffix):
            return unit
    return ""


def _values_to_array(values: Sequence[Any], name: str) -> np.ndarray:
    """Convert one raw column to the narrowest useful NumPy dtype."""

    strings = [str(value).strip() for value in values]
    if name.lower() in {"bout", "bbits", "bits", "pattern"}:
        return np.asarray(strings, dtype=np.str_)
    try:
        return np.asarray([int(value, 0) for value in strings], dtype=np.int64)
    except ValueError:
        pass
    try:
        return np.asarray([float(value) for value in strings], dtype=np.float64)
    except ValueError:
        return np.asarray(strings, dtype=np.str_)


def _table_from_columns(
    name: str,
    columns: Mapping[str, Sequence[Any] | np.ndarray],
    units: Mapping[str, str],
) -> DataTable:
    """Normalize column mappings into one aligned table."""

    return DataTable(
        name=name,
        columns=tuple(
            DataColumn(
                column_name,
                np.asarray(values) if isinstance(values, np.ndarray) else _values_to_array(values, column_name),
                units.get(column_name, _column_unit(column_name)),
            )
            for column_name, values in columns.items()
        ),
    )


def _read_csv_columns(path: Path) -> tuple[tuple[str, ...], dict[str, list[str]]]:
    """Read one CSV without imposing an ADC- or waveform-specific schema."""

    with path.open(newline="") as input_file:
        reader = csv.DictReader(input_file)
        fieldnames = tuple(reader.fieldnames or ())
        if not fieldnames:
            raise ValueError(f"{path} has no CSV header")
        columns = {field: [] for field in fieldnames}
        for row in reader:
            for field in fieldnames:
                columns[field].append(row[field])
    return fieldnames, columns


def _select_columns(
    raw_columns: Mapping[str, Sequence[Any] | np.ndarray],
    column_map: Mapping[str, str],
) -> dict[str, Sequence[Any] | np.ndarray]:
    """Map canonical names to raw names, retaining every column by default."""

    if not column_map:
        return dict(raw_columns)
    missing = sorted(set(column_map.values()).difference(raw_columns))
    if missing:
        raise ValueError(f"raw result is missing selected columns: {', '.join(missing)}")
    return {canonical: raw_columns[raw] for canonical, raw in column_map.items()}


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


RawColumns = Mapping[str, Sequence[Any] | np.ndarray]


def _read_csv_source(spec: SourceSpec) -> tuple[RawColumns, tuple[Path, ...]]:
    path = Path(spec.source)
    _fieldnames, loaded_columns = _read_csv_columns(path)
    if spec.format is not SourceFormat.ADC_CSV:
        return loaded_columns, (path,)
    canonical_columns: dict[str, Sequence[Any] | np.ndarray] = {}
    for raw_name, values in loaded_columns.items():
        canonical_name = ADC_COLUMN_ALIASES.get(raw_name, raw_name)
        if canonical_name not in canonical_columns:
            canonical_columns[canonical_name] = values
    return canonical_columns, (path,)


def _read_mapping_source(spec: SourceSpec) -> tuple[RawColumns, tuple[Path, ...]]:
    if not isinstance(spec.source, Mapping):
        raise TypeError("COLUMN_MAPPING source must implement Mapping")
    return spec.source, ()


def _read_scope_source(spec: SourceSpec) -> tuple[RawColumns, tuple[Path, ...]]:
    if not isinstance(spec.source, tuple) or len(spec.source) != 2:
        raise TypeError("SCOPE_WAVEFORMS source must be (waveforms, track_names)")
    waveforms, track_names = spec.source
    channels = tuple(track_names)
    if not channels:
        raise ValueError("at least one scope track is required")
    if len(set(track_names.values())) != len(track_names):
        raise ValueError("scope track names must be unique")
    missing_channels = sorted(set(channels).difference(waveforms))
    if missing_channels:
        raise ValueError(f"scope did not return channels {missing_channels}")
    reference_scale = waveforms[channels[0]].x_scale
    sample_counts = {channel: len(waveforms[channel].data) for channel in channels}
    if len(set(sample_counts.values())) != 1:
        raise ValueError(f"scope channels have different sample counts: {sample_counts}")
    for channel in channels:
        waveform = waveforms[channel]
        if waveform.x_scale != reference_scale:
            raise ValueError(f"scope channel {channel} has a different horizontal scale")
        if len(waveform.data) != len(waveform.raw_data):
            raise ValueError(f"scope channel {channel} voltage and raw data are not aligned")
    sample_count = next(iter(sample_counts.values()))
    return (
        {
            "time_s": reference_scale.offset + np.arange(sample_count) * reference_scale.slope,
            **{f"{track_names[channel]}_v": np.asarray(waveforms[channel].data) for channel in channels},
            **{f"{track_names[channel]}_raw": np.asarray(waveforms[channel].raw_data) for channel in channels},
        },
        (),
    )


def _read_sim_result_source(spec: SourceSpec) -> tuple[RawColumns, tuple[Path, ...]]:
    analyses = getattr(spec.source, "an", None)
    if not analyses:
        raise ValueError("SIM_RESULT source contains no analyses")
    if not 0 <= spec.analysis_index < len(analyses):
        raise IndexError(f"SIM_RESULT analysis_index={spec.analysis_index} is outside 0..{len(analyses) - 1}")
    return analyses[spec.analysis_index].data, ()


def _read_spectre_source(spec: SourceSpec) -> tuple[RawColumns, tuple[Path, ...]]:
    path = Path(spec.source)
    selected_signals = set(spec.column_map.values()) if spec.column_map else None
    return parse_spectre_nutascii(path, selected_signals), (path,)


def read_run(spec: SourceSpec) -> RunData:
    """Normalize one raw physical, behavioral, or SPICE source."""

    readers = {
        SourceFormat.CSV: _read_csv_source,
        SourceFormat.SCOPE_CSV: _read_csv_source,
        SourceFormat.ADC_CSV: _read_csv_source,
        SourceFormat.COLUMN_MAPPING: _read_mapping_source,
        SourceFormat.SCOPE_WAVEFORMS: _read_scope_source,
        SourceFormat.SIM_RESULT: _read_sim_result_source,
        SourceFormat.SPECTRE_NUTASCII: _read_spectre_source,
    }
    try:
        reader = readers[spec.format]
    except KeyError:
        raise ValueError(f"unsupported source format {spec.format.value!r}") from None
    raw_columns, source_paths = reader(spec)

    selected_columns = _select_columns(raw_columns, spec.column_map)
    table = _table_from_columns(spec.table_name, selected_columns, spec.units)
    parameters = to_json_data(spec.parameters)
    if not isinstance(parameters, dict):
        raise TypeError("source parameters must normalize to a JSON object")
    return RunData(
        run_id=spec.run_id,
        backend=spec.backend,
        block=spec.block,
        tables=(table,),
        parameters=parameters,
        source_paths=source_paths,
    )
