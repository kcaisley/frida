"""Typed ADC acquisition rows and their CSV representation."""

from __future__ import annotations

import csv
import dataclasses
import hashlib
import json
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Iterable

from hdl21.prefix import Prefixed


@dataclass(frozen=True, slots=True)
class AdcConversion:
    """One raw FastRX conversion plus deterministic ideal-weight decoding."""

    conversion_index: int
    raw_word: int
    identifier: int
    frame: int
    spi: int
    bout: str
    dout_raw: int
    dout: int

    @classmethod
    def from_csv_row(cls, row: dict[str, str]) -> AdcConversion:
        """Parse one row produced by :func:`write_adc_conversions`."""

        return cls(
            conversion_index=int(row["conversion_index"]),
            raw_word=int(row["raw_word"]),
            identifier=int(row["identifier"]),
            frame=int(row["frame"]),
            spi=int(row["spi"]),
            bout=row["bout"],
            dout_raw=int(row["dout_raw"]),
            dout=int(row["dout"]),
        )


ADC_CONVERSION_FIELDS = tuple(field.name for field in dataclasses.fields(AdcConversion))


def write_adc_conversions(
    path: Path,
    rows: Iterable[AdcConversion],
    *,
    append: bool = False,
) -> int:
    """Write or append typed conversion rows and return the number written."""

    path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with path.open("a" if append else "w", newline="") as output:
        writer = csv.DictWriter(output, fieldnames=ADC_CONVERSION_FIELDS)
        if not append:
            writer.writeheader()
        for row in rows:
            writer.writerow(dataclasses.asdict(row))
            count += 1
    return count


def read_adc_conversions(path: Path) -> list[AdcConversion]:
    """Read one acquisition CSV into typed conversion rows."""

    with path.open(newline="") as input_file:
        return [AdcConversion.from_csv_row(row) for row in csv.DictReader(input_file)]


def to_json_data(value: Any) -> Any:
    """Convert nested HDL21 parameters and scan metadata to JSON data."""

    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, Prefixed):
        return float(value)
    if isinstance(value, Enum):
        return value.name
    if isinstance(value, Path):
        return str(value)
    if dataclasses.is_dataclass(value):
        data = {field.name: to_json_data(getattr(value, field.name)) for field in dataclasses.fields(value)}
        data["type"] = type(value).__name__
        return data
    if isinstance(value, dict):
        return {str(key): to_json_data(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [to_json_data(item) for item in value]
    raise TypeError(f"cannot serialize {type(value).__name__} to manifest JSON")


def parameter_digest(params: Any) -> str:
    """Return a short stable identifier for one complete parameter object."""

    encoded = json.dumps(to_json_data(params), sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()[:8]
