"""Raw ADC acquisition rows and scan-side CSV persistence."""

from __future__ import annotations

import csv
import dataclasses
from pathlib import Path
from typing import Iterable

from flow.analysis.models import AdcConversion


ADC_CONVERSION_FIELDS = tuple(field.name for field in dataclasses.fields(AdcConversion))


def write_adc_conversions(
    path: Path,
    rows: Iterable[AdcConversion],
    *,
    append: bool = False,
) -> int:
    """Write or append typed raw conversion rows and return the number written."""

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
