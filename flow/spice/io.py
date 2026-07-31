"""Read Spectre NUTASCII results and write typed FRIDA measurements.

Spectre is configured with ``rawfmt=nutascii`` in the current ADC PEX decks.
The raw reader streams text tokens and only retains requested signals, so it
does not duplicate the complete raw file in memory. The HDF5 representation is
written by :func:`flow.analysis.io.write_measurement`.
"""

from __future__ import annotations

import dataclasses
import re
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path

import numpy as np

from flow.analysis.io import interpolate_wave_records, write_measurement
from flow.analysis.types import AdcDaq, AdcExtWave, MeasAdcExt, MeasInfo
from flow.cdac import get_cdac_weights
from flow.scans.params import AdcTbParams

ADC_PEX_SIGNALS = {
    "comp_out_v": "comp_out",
    "seq_comp_v": "seq_comp",
    "seq_logic_v": "seq_update",
    "vin_p_v": "vin_p",
    "vin_n_v": "vin_n",
}


def read_spectre_nutascii(
    path: Path,
    selected_signals: set[str] | None = None,
) -> dict[str, np.ndarray]:
    """Read selected one-dimensional signals from Spectre NUTASCII output.

    Point records may span arbitrary text lines. When Spectre declares
    ``No. Points`` in the header, arrays are allocated once at their final
    length; this is important for multi-gigabyte transient results.
    """

    path = Path(path)
    variable_names: list[str] = []
    declared_points: int | None = None
    in_variables = False
    with path.open(errors="replace") as input_file:
        for line in input_file:
            stripped = line.strip()
            points_match = re.fullmatch(r"No\. Points:\s*(\d+)", stripped)
            if points_match is not None:
                declared_points = int(points_match.group(1))
            if stripped.startswith("Variables:"):
                in_variables = True
                stripped = stripped.removeprefix("Variables:").strip()
            elif stripped == "Values:":
                break
            elif in_variables and stripped and not stripped[0].isdigit():
                in_variables = False
            if in_variables and stripped:
                parts = stripped.split()
                if len(parts) >= 3 and parts[0].isdigit():
                    variable_names.append(parts[1])
        else:
            raise ValueError(f"{path} is missing the Spectre NUTASCII 'Values:' section")

        if not variable_names:
            raise ValueError(f"{path} has no Spectre NUTASCII variable list")
        selected = set(variable_names) if selected_signals is None else set(selected_signals)
        missing = sorted(selected.difference(variable_names))
        if missing:
            raise KeyError(f"{path} does not contain requested signals {missing}")
        selected_indices = {index: name for index, name in enumerate(variable_names) if name in selected}
        if declared_points is None:
            dynamic_values: dict[str, list[float]] | None = {name: [] for name in selected_indices.values()}
            arrays: dict[str, np.ndarray] | None = None
        else:
            dynamic_values = None
            arrays = {name: np.empty(declared_points, dtype=np.float64) for name in selected_indices.values()}

        tokens = (token for line in input_file for token in line.split())
        point_count = 0
        while True:
            try:
                point_token = next(tokens)
            except StopIteration:
                break
            try:
                point_index = int(point_token)
            except ValueError as exc:
                raise ValueError(f"{path} has invalid NUTASCII point index {point_token!r}") from exc
            if point_index != point_count:
                raise ValueError(f"{path} has NUTASCII point index {point_index}, expected {point_count}")
            if declared_points is not None and point_count >= declared_points:
                raise ValueError(f"{path} contains more points than its declared {declared_points}")
            for variable_index in range(len(variable_names)):
                try:
                    value_token = next(tokens)
                except StopIteration as exc:
                    raise ValueError(f"{path} ends partway through NUTASCII point {point_index}") from exc
                if variable_index not in selected_indices:
                    continue
                name = selected_indices[variable_index]
                try:
                    value = float(value_token)
                except ValueError as exc:
                    raise ValueError(
                        f"{path} has invalid value {value_token!r} for signal {name!r} at point {point_index}"
                    ) from exc
                if arrays is not None:
                    arrays[name][point_count] = value
                else:
                    assert dynamic_values is not None
                    dynamic_values[name].append(value)
            point_count += 1

    if point_count == 0:
        raise ValueError(f"{path} contains no NUTASCII data points")
    if declared_points is not None:
        if point_count != declared_points:
            raise ValueError(f"{path} contains {point_count} points, expected {declared_points}")
        assert arrays is not None
        return arrays
    assert dynamic_values is not None
    return {name: np.asarray(values, dtype=np.float64) for name, values in dynamic_values.items()}


def convert_spectre_adc_to_measurement(
    data: Mapping[str, Sequence[float] | np.ndarray],
    *,
    params: AdcTbParams,
    raw_path: Path,
    threshold_v: float = 0.6,
    comparator_sample_delay_s: float = 10e-9,
    waveform_samples: int = 2_000,
    maximum_waveform_records: int = 128,
    rail_current_signals: Mapping[str, str] | None = None,
) -> MeasAdcExt:
    """Decode comparator decisions and dense interface waves from ADC PEX data."""

    required_signals = {"time", *ADC_PEX_SIGNALS.values()}
    missing = sorted(required_signals.difference(data))
    if missing:
        raise KeyError(f"ADC PEX data is missing required signals {missing}")
    if waveform_samples < 2:
        raise ValueError("waveform_samples must be at least two")
    if maximum_waveform_records <= 0:
        raise ValueError("maximum_waveform_records must be positive")

    times_s = np.asarray(data["time"], dtype=np.float64)
    signals = {name: np.asarray(data[raw_name], dtype=np.float64) for name, raw_name in ADC_PEX_SIGNALS.items()}
    if times_s.ndim != 1 or len(times_s) < 2 or np.any(np.diff(times_s) <= 0):
        raise ValueError("Spectre time must be one-dimensional and strictly increasing")
    if any(values.shape != times_s.shape for values in signals.values()):
        raise ValueError("all ADC PEX signals must align with Spectre time")

    code_weights = np.asarray(
        [2 * weight for weight in get_cdac_weights(params.dut.cdac)] + [1],
        dtype=np.int64,
    )
    if len(code_weights) != 17:
        raise ValueError(f"ADC measurement format requires 17 decisions, got {len(code_weights)}")
    clock_high = signals["seq_comp_v"] > threshold_v
    edge_indices = np.flatnonzero(clock_high[1:] & ~clock_high[:-1]) + 1
    complete_conversions = len(edge_indices) // len(code_weights)
    if complete_conversions == 0:
        raise ValueError("Spectre result contains no complete ADC conversion")
    used_edges = edge_indices[: complete_conversions * len(code_weights)]
    edge_times_s = times_s[used_edges].reshape(complete_conversions, len(code_weights))
    sample_times_s = edge_times_s + comparator_sample_delay_s

    right_indices = np.searchsorted(times_s, sample_times_s)
    right_indices = np.clip(right_indices, 1, len(times_s) - 1)
    left_indices = right_indices - 1
    choose_right = np.abs(times_s[right_indices] - sample_times_s) < np.abs(sample_times_s - times_s[left_indices])
    sample_indices = np.where(choose_right, right_indices, left_indices)
    bout = (signals["comp_out_v"][sample_indices] > threshold_v).astype(np.uint8)
    dout_raw = bout @ code_weights
    dout = np.rint(dout_raw * ((1 << params.dut.adc_bits) - 1) / np.sum(code_weights)).astype(np.int64)
    vin_diff = signals["vin_p_v"] - signals["vin_n_v"]
    conversion_starts_s = edge_times_s[:, 0]
    vin_diff_v = np.interp(conversion_starts_s, times_s, vin_diff)
    # HDL21 paramclasses are runtime dataclasses, although their decorator's
    # typing stub does not currently expose that fact to ty.
    params = dataclasses.replace(
        params,  # ty: ignore[invalid-argument-type]
        conversions=complete_conversions,
    )

    if complete_conversions > 1:
        record_duration_s = float(np.median(np.diff(conversion_starts_s)))
    else:
        record_duration_s = min(
            float(times_s[-1] - conversion_starts_s[0]),
            len(params.seq_init_pattern) / float(params.symbol_rate),
        )
    eligible_indices = np.flatnonzero(conversion_starts_s + record_duration_s <= times_s[-1])
    if len(eligible_indices) > maximum_waveform_records:
        selected_positions = np.unique(
            np.rint(np.linspace(0, len(eligible_indices) - 1, maximum_waveform_records)).astype(np.int64)
        )
        eligible_indices = eligible_indices[selected_positions]
    waveform_conversion_indices = eligible_indices
    waveform_starts_s = conversion_starts_s[waveform_conversion_indices]
    relative_time_s, waveform_records = interpolate_wave_records(
        times_s,
        {
            "vin_diff_v": vin_diff,
            "seq_comp_v": signals["seq_comp_v"],
            "seq_logic_v": signals["seq_logic_v"],
            "comp_out_v": signals["comp_out_v"],
        },
        [(float(start_s), float(start_s + record_duration_s)) for start_s in waveform_starts_s],
        waveform_samples,
    )

    readbacks: dict[str, str | int | float | bool] = {
        "raw_file": Path(raw_path).name,
        "raw_format": "spectre_nutascii",
        "raw_points": len(times_s),
        "ignored_trailing_comparator_edges": len(edge_indices) - complete_conversions * len(code_weights),
        "supply_power_available": bool(rail_current_signals),
    }
    if rail_current_signals:
        required_rails = {"vdd_a", "vdd_d", "vdd_dac"}
        if set(rail_current_signals) != required_rails:
            raise ValueError(f"rail current signals must map exactly {sorted(required_rails)}")
        rail_voltages = {
            "vdd_a": float(params.vdd_a.dc),
            "vdd_d": float(params.vdd_d.dc),
            "vdd_dac": float(params.vdd_dac.dc),
        }
        for rail, signal_name in rail_current_signals.items():
            if rail not in rail_voltages:
                raise ValueError(f"unsupported ADC supply rail {rail!r}")
            if signal_name not in data:
                raise KeyError(f"ADC PEX data does not contain current signal {signal_name!r}")
            current_a = np.asarray(data[signal_name], dtype=np.float64)
            if current_a.shape != times_s.shape:
                raise ValueError(f"current signal {signal_name!r} is not aligned")
            average_current_a = float(np.mean(np.abs(current_a)))
            readbacks[f"{rail}_active_average_current_a"] = average_current_a
            readbacks[f"{rail}_active_average_power_w"] = rail_voltages[rail] * average_current_a

    return MeasAdcExt(
        info=MeasInfo(
            schema_version=1,
            measurement_type="MeasAdcExt",
            backend="spice",
            timestamp_utc=datetime.fromtimestamp(
                Path(raw_path).stat().st_mtime,
                tz=UTC,
            ),
            instruments={"simulator": "Spectre"},
            readbacks=readbacks,
        ),
        param=params,
        daq=AdcDaq(
            conversion_index=np.arange(complete_conversions, dtype=np.int64),
            bout=bout,
            dout_raw=dout_raw,
            dout=dout,
            vin_diff_v=vin_diff_v,
        ),
        wave=AdcExtWave(
            conversion_index=waveform_conversion_indices,
            time_s=relative_time_s,
            **waveform_records,
        ),
    )


def convert_spectre_adc_raw_to_h5(
    raw_path: Path,
    h5_path: Path,
    *,
    params: AdcTbParams,
    rail_current_signals: Mapping[str, str] | None = None,
    maximum_waveform_records: int = 128,
) -> Path:
    """Read one ADC PEX raw file and write the shared typed HDF5 format."""

    selected_signals = {"time", *ADC_PEX_SIGNALS.values()}
    if rail_current_signals:
        selected_signals.update(rail_current_signals.values())
    data = read_spectre_nutascii(raw_path, selected_signals)
    measurement = convert_spectre_adc_to_measurement(
        data,
        params=params,
        raw_path=raw_path,
        rail_current_signals=rail_current_signals,
        maximum_waveform_records=maximum_waveform_records,
    )
    return write_measurement(h5_path, measurement)
