"""Parse lumped Calibre xACT capacitance netlists for FRIDA CDACs."""

from __future__ import annotations

import csv
import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal

_CAPACITOR = re.compile(
    r"^\s*\S+\s+\(\s*(\S+)\s+(\S+)\s*\)\s+capacitor\s+c="
    r"([+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?)([a-zA-Z]*)\s*$",
    re.MULTILINE | re.IGNORECASE,
)
_BOTTOM = re.compile(
    r"^(?:N_)?CAP_BOTPLATE_(MAIN|DIFF)<(\d+)>(?:[_:].*)?$",
    re.IGNORECASE,
)
_FF_SCALE = {"": 1e15, "f": 1.0, "p": 1e3, "n": 1e6, "u": 1e9, "m": 1e12}
type PinOrder = Literal["stage", "frida1_legacy"]


@dataclass(frozen=True)
class CdacPexCapacitance:
    """C0-first capacitance components for one physical CDAC array."""

    main_by_stage_ff: tuple[float, ...]
    diff_by_stage_ff: tuple[float, ...]
    main_ff: float
    diff_ff: float
    effective_ff: float
    topplate_shield_ff: float
    topplate_ground_ff: float
    shield_ground_ff: float
    topplate_total_ff: float
    shield_total_ff: float


def _node(value: str) -> str:
    return value.replace("\\", "").upper()


def _logical_node(value: str) -> str | tuple[str, int] | None:
    if value == "0":
        return "ground"
    if value == "CAP_TOPPLATE" or value.startswith(("CAP_TOPPLATE_", "N_CAP_TOPPLATE_")):
        return "topplate"
    if value == "CAP_SHIELDPLATE" or value.startswith(("CAP_SHIELDPLATE_", "N_CAP_SHIELDPLATE_")):
        return "shield"
    if match := _BOTTOM.match(value):
        return match.group(1).lower(), int(match.group(2))
    return None


def _value_ff(number: str, suffix: str) -> float:
    try:
        scale = _FF_SCALE[suffix.lower()]
    except KeyError as error:
        raise ValueError(f"unsupported capacitance suffix {suffix!r}") from error
    return float(number) * scale


def _stage_for_pin(pin: int, stage_count: int, pin_order: PinOrder) -> int:
    if not 0 <= pin < stage_count:
        raise ValueError(f"PEX contains out-of-range bottom-plate pin {pin}")
    if pin_order == "stage":
        return pin
    if pin_order == "frida1_legacy":
        return stage_count - 1 - pin
    raise ValueError(f"unsupported CDAC pin order {pin_order!r}")


def parse_cdac_pex(
    path: Path,
    *,
    stage_count: int,
    pin_order: PinOrder = "stage",
) -> CdacPexCapacitance:
    """Sum logical top/bottom couplings and return C0-first stage order."""

    if stage_count < 1:
        raise ValueError("stage_count must be positive")
    # Calibre uses a trailing backslash for wrapped Spectre statements.
    text = path.read_text(encoding="utf-8").replace("\\\n", " ")
    main = [0.0] * stage_count
    diff = [0.0] * stage_count
    topplate_shield = 0.0
    topplate_ground = 0.0
    shield_ground = 0.0
    topplate_total = 0.0
    shield_total = 0.0

    for raw_a, raw_b, number, suffix in _CAPACITOR.findall(text):
        a, b = _node(raw_a), _node(raw_b)
        logical_a, logical_b = _logical_node(a), _logical_node(b)
        value_ff = _value_ff(number, suffix)
        terminals = {logical_a, logical_b}
        if "topplate" in terminals and logical_a != logical_b:
            topplate_total += value_ff
            other = logical_b if logical_a == "topplate" else logical_a
            if isinstance(other, tuple):
                kind, pin = other
                stage = _stage_for_pin(pin, stage_count, pin_order)
                target = main if kind == "main" else diff
                target[stage] += value_ff
            elif other == "shield":
                topplate_shield += value_ff
            elif other == "ground":
                topplate_ground += value_ff
        if "shield" in terminals and logical_a != logical_b:
            shield_total += value_ff
            other = logical_b if logical_a == "shield" else logical_a
            if other == "ground":
                shield_ground += value_ff

    main_total = sum(main)
    diff_total = sum(diff)
    if main_total == 0.0 or diff_total == 0.0:
        raise ValueError(f"{path} contains no complete FRIDA top/bottom capacitance set")
    return CdacPexCapacitance(
        main_by_stage_ff=tuple(main),
        diff_by_stage_ff=tuple(diff),
        main_ff=main_total,
        diff_ff=diff_total,
        effective_ff=main_total - diff_total,
        topplate_shield_ff=topplate_shield,
        topplate_ground_ff=topplate_ground,
        shield_ground_ff=shield_ground,
        topplate_total_ff=topplate_total,
        shield_total_ff=shield_total,
    )


def parse_adc_cdac_pex(
    path: Path,
    *,
    stage_count: int,
    pin_order: PinOrder = "stage",
) -> CdacPexCapacitance:
    """Extract and average P/N CDACs, returning C0-first stage order."""

    if stage_count < 1:
        raise ValueError("stage_count must be positive")
    text = path.read_text(encoding="utf-8").replace("\\\n", " ")
    main = {side: [0.0] * stage_count for side in ("p", "n")}
    diff = {side: [0.0] * stage_count for side in ("p", "n")}
    top_total = {side: 0.0 for side in ("p", "n")}
    top_shield = {side: 0.0 for side in ("p", "n")}
    top_ground = {side: 0.0 for side in ("p", "n")}

    def classify(raw: str) -> str | tuple[str, str, int] | tuple[str, str] | None:
        node = _node(raw)
        for side in ("P", "N"):
            if node == f"VDAC_{side}" or node.startswith((f"VDAC_{side}:", f"N_VDAC_{side}_")):
                return "top", side.lower()
            match = re.match(
                rf"^(?:N_)?DAC_DRIVE_BOTPLATE_(MAIN|DIFF)_{side}<([0-9]+)>(?:[_:].*)?$",
                node,
            )
            if match:
                return match.group(1).lower(), side.lower(), int(match.group(2))
        if node == "0":
            return "ground"
        if node in ("VSS_A", "VSS_DAC") or node.startswith(("N_VSS_A_", "N_VSS_DAC_")):
            return "shield"
        return None

    for raw_a, raw_b, number, suffix in _CAPACITOR.findall(text):
        logical_a, logical_b = classify(raw_a), classify(raw_b)
        value_ff = _value_ff(number, suffix)
        for side in ("p", "n"):
            top = ("top", side)
            if top not in (logical_a, logical_b) or logical_a == logical_b:
                continue
            top_total[side] += value_ff
            other = logical_b if logical_a == top else logical_a
            if isinstance(other, tuple) and len(other) == 3 and other[1] == side:
                kind, _side, pin = other
                stage = _stage_for_pin(pin, stage_count, pin_order)
                (main if kind == "main" else diff)[side][stage] += value_ff
            elif other == "shield":
                top_shield[side] += value_ff
            elif other == "ground":
                top_ground[side] += value_ff

    main_average = tuple((a + b) / 2 for a, b in zip(main["p"], main["n"], strict=True))
    diff_average = tuple((a + b) / 2 for a, b in zip(diff["p"], diff["n"], strict=True))
    if not sum(main_average) or not sum(diff_average):
        raise ValueError(f"{path} contains no complete differential FRIDA CDAC")
    return CdacPexCapacitance(
        main_by_stage_ff=main_average,
        diff_by_stage_ff=diff_average,
        main_ff=sum(main_average),
        diff_ff=sum(diff_average),
        effective_ff=sum(main_average) - sum(diff_average),
        topplate_shield_ff=(top_shield["p"] + top_shield["n"]) / 2,
        topplate_ground_ff=(top_ground["p"] + top_ground["n"]) / 2,
        shield_ground_ff=0.0,
        topplate_total_ff=(top_total["p"] + top_total["n"]) / 2,
        shield_total_ff=0.0,
    )


def write_comparison_table(
    output_dir: Path,
    designs: dict[str, CdacPexCapacitance],
) -> tuple[Path, Path]:
    """Write the requested 34-row main/diff/sampling/shunt comparison."""

    if not designs:
        raise ValueError("comparison requires at least one design")
    stage_count = len(next(iter(designs.values())).main_by_stage_ff)
    if any(
        len(result.main_by_stage_ff) != stage_count or len(result.diff_by_stage_ff) != stage_count
        for result in designs.values()
    ):
        raise ValueError("comparison designs must have equal stage counts")
    rows: list[tuple[str, dict[str, float]]] = []
    for kind in ("main", "diff"):
        for stage in range(stage_count):
            rows.append(
                (
                    f"{kind}[{stage}]_ff",
                    {
                        name: (result.main_by_stage_ff if kind == "main" else result.diff_by_stage_ff)[stage]
                        for name, result in designs.items()
                    },
                )
            )
    rows.append(
        (
            "main_plus_diff_total_ff",
            {name: result.main_ff + result.diff_ff for name, result in designs.items()},
        )
    )
    rows.append(
        (
            "shunt_dc_ff",
            {name: result.topplate_total_ff - result.main_ff - result.diff_ff for name, result in designs.items()},
        )
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    csv_path = output_dir / "five_design_capacitance.csv"
    json_path = output_dir / "five_design_capacitance.json"
    with csv_path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(("quantity", *designs))
        for quantity, values in rows:
            writer.writerow((quantity, *(values[name] for name in designs)))
    json_path.write_text(
        json.dumps({quantity: values for quantity, values in rows}, indent=2) + "\n",
        encoding="utf-8",
    )
    return csv_path, json_path


def write_capacitance_table(output_dir: Path, result: CdacPexCapacitance) -> tuple[Path, Path]:
    """Write machine-readable per-stage and aggregate extraction results."""

    json_path = output_dir / "capacitance_table.json"
    csv_path = output_dir / "capacitance_table.csv"
    json_path.write_text(json.dumps(asdict(result), indent=2) + "\n", encoding="utf-8")
    with csv_path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(("stage", "main_ff", "diff_ff", "effective_ff"))
        for stage, (main, diff) in enumerate(zip(result.main_by_stage_ff, result.diff_by_stage_ff, strict=True)):
            writer.writerow((stage, main, diff, main - diff))
    return json_path, csv_path
