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
from flow.analysis.types import AdcDaq, AdcIntWave, MeasAdcInt, MeasInfo
from flow.cdac import get_cdac_weights
from flow.scans.params import AdcTbParams


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
    signal_names: Mapping[str, str],
    threshold_v: float = 0.6,
    decision_sample_fraction: float = 0.98,
    waveform_samples: int = 2_000,
    maximum_waveform_records: int = 128,
) -> MeasAdcInt:
    """Decode one Spectre ADC result into the typed internal contract.

    ``signal_names`` maps canonical :class:`AdcIntWave` fields to Spectre
    variable names. Spectre reports voltage-source current into the source's
    positive terminal; the stored supply currents reverse that sign so that
    positive values mean current drawn by the ADC.
    """

    raw_wave_names = tuple(
        field.name
        for field in dataclasses.fields(AdcIntWave)
        if field.name not in {"conversion_index", "time_s", "vin_diff_v"}
    )
    expected_names = {"time_s", *raw_wave_names}
    missing_names = sorted(expected_names.difference(signal_names))
    unexpected_names = sorted(set(signal_names).difference(expected_names))
    if missing_names or unexpected_names:
        raise ValueError(
            "signal_names must map exactly the raw AdcIntWave signals; "
            f"missing={missing_names}, unexpected={unexpected_names}"
        )
    raw_names = tuple(signal_names.values())
    if any(not isinstance(name, str) or not name for name in raw_names):
        raise ValueError("signal_names values must be non-empty raw variable names")
    if len(set(raw_names)) != len(raw_names):
        raise ValueError("signal_names raw variable names must be unique")
    missing = sorted(set(raw_names).difference(data))
    if missing:
        raise KeyError(f"Spectre data is missing mapped signals {missing}")
    if not 0.0 < decision_sample_fraction < 1.0:
        raise ValueError("decision_sample_fraction must lie strictly between zero and one")
    if waveform_samples < 2:
        raise ValueError("waveform_samples must be at least two")
    if maximum_waveform_records <= 0:
        raise ValueError("maximum_waveform_records must be positive")

    times_s = np.asarray(data[signal_names["time_s"]], dtype=np.float64)
    signals = {
        name: np.asarray(data[signal_names[name]], dtype=np.float64)
        for name in raw_wave_names
    }
    for name in ("vdd_a_i", "vdd_d_i", "vdd_dac_i"):
        signals[name] = -signals[name]
    signals["vin_diff_v"] = signals["vin_p_v"] - signals["vin_n_v"]
    if times_s.ndim != 1 or len(times_s) < 2 or np.any(np.diff(times_s) <= 0):
        raise ValueError("Spectre time must be one-dimensional and strictly increasing")
    if any(values.shape != times_s.shape for values in signals.values()):
        raise ValueError("all mapped Spectre signals must align with Spectre time")
    if not np.all(np.isfinite(times_s)) or any(
        not np.all(np.isfinite(values)) for values in signals.values()
    ):
        raise ValueError("Spectre time and mapped signals must contain only finite values")

    code_weights = np.asarray(
        [2 * weight for weight in get_cdac_weights(params.dut.cdac)] + [1],
        dtype=np.int64,
    )
    if len(code_weights) != 17:
        raise ValueError(f"ADC measurement format requires 17 decisions, got {len(code_weights)}")

    edge_indices: dict[str, np.ndarray] = {}
    for name in ("seq_init_v", "seq_comp_v", "seq_logic_v"):
        high = signals[name] > threshold_v
        edge_indices[name] = np.flatnonzero(
            high & np.concatenate((np.asarray([True]), ~high[:-1]))
        )
    conversion_start_indices = edge_indices["seq_init_v"]
    if len(conversion_start_indices) == 0:
        raise ValueError("Spectre result contains no SEQ_INIT rising edge")

    comp_edges_by_conversion = []
    logic_times_by_conversion = []
    for conversion_number, start_index in enumerate(conversion_start_indices):
        stop_index = (
            conversion_start_indices[conversion_number + 1]
            if conversion_number + 1 < len(conversion_start_indices)
            else len(times_s)
        )
        comp_edges = edge_indices["seq_comp_v"]
        comp_edges = comp_edges[(comp_edges >= start_index) & (comp_edges < stop_index)]
        if len(comp_edges) != len(code_weights):
            raise ValueError(
                f"conversion {conversion_number} contains {len(comp_edges)} COMP rising edges; "
                f"expected exactly {len(code_weights)}"
            )
        logic_edges = edge_indices["seq_logic_v"]
        logic_edges = logic_edges[(logic_edges > comp_edges[0]) & (logic_edges < stop_index)]
        logic_positions = np.searchsorted(logic_edges, comp_edges, side="right")
        matched = logic_positions < len(logic_edges)
        if np.count_nonzero(matched) != len(code_weights) - 1 or not np.all(matched[:-1]) or matched[-1]:
            raise ValueError(
                f"conversion {conversion_number} must have following LOGIC edges "
                "for its first 16 COMP edges and no update after its final decision"
            )
        matched_logic_edges = logic_edges[logic_positions[:-1]]
        if len(np.unique(matched_logic_edges)) != len(code_weights) - 1:
            raise ValueError(
                f"conversion {conversion_number} does not pair each COMP edge "
                "with a unique following LOGIC edge"
            )
        comp_edges_by_conversion.append(comp_edges)
        comp_times = times_s[comp_edges]
        logic_times = times_s[matched_logic_edges]
        final_interval_s = float(np.median(logic_times - comp_times[:-1]))
        logic_times_by_conversion.append(
            np.concatenate((logic_times, [comp_times[-1] + final_interval_s]))
        )

    comp_edge_indices = np.stack(comp_edges_by_conversion)
    comp_edge_times_s = times_s[comp_edge_indices]
    logic_edge_times_s = np.stack(logic_times_by_conversion)
    sample_times_s = comp_edge_times_s + decision_sample_fraction * (
        logic_edge_times_s - comp_edge_times_s
    )
    bout = (
        np.interp(sample_times_s.ravel(), times_s, signals["comp_out_v"])
        .reshape(sample_times_s.shape)
        > threshold_v
    ).astype(np.uint8)
    dout_raw = bout @ code_weights
    dout = np.rint(dout_raw * ((1 << params.dut.adc_bits) - 1) / np.sum(code_weights)).astype(np.int64)
    conversion_starts_s = times_s[conversion_start_indices]
    vin_diff_v = np.interp(comp_edge_times_s[:, 0], times_s, signals["vin_diff_v"])
    complete_conversions = len(conversion_start_indices)
    # HDL21 paramclasses are runtime dataclasses, although their decorator's
    # typing stub does not currently expose that fact to ty.
    params = dataclasses.replace(
        params,  # ty: ignore[invalid-argument-type]
        conversions=complete_conversions,
    )

    # Align waveform records to the repeated sequencer-pattern boundary, not
    # to SEQ_INIT's rising edge inside that pattern. This retains the pre-INIT
    # portion of each conversion and lets the final complete pattern fit in a
    # simulation which stops after exactly ``conversions * pattern_period``.
    waveform_starts_s = conversion_starts_s - (conversion_starts_s[0] - times_s[0])
    if complete_conversions > 1:
        record_duration_s = float(np.median(np.diff(waveform_starts_s)))
        final_record_stop_s = waveform_starts_s[-1] + record_duration_s
        if final_record_stop_s > times_s[-1] and np.isclose(
            final_record_stop_s,
            times_s[-1],
            rtol=1e-9,
            atol=0.0,
        ):
            record_duration_s = float(times_s[-1] - waveform_starts_s[-1])
    else:
        record_duration_s = min(
            float(times_s[-1] - waveform_starts_s[0]),
            len(params.seq_init_pattern) / float(params.symbol_rate),
        )
    eligible_indices = np.flatnonzero(waveform_starts_s + record_duration_s <= times_s[-1])
    if len(eligible_indices) > maximum_waveform_records:
        selected_positions = np.unique(
            np.rint(np.linspace(0, len(eligible_indices) - 1, maximum_waveform_records)).astype(np.int64)
        )
        eligible_indices = eligible_indices[selected_positions]
    waveform_conversion_indices = eligible_indices
    waveform_starts_s = waveform_starts_s[waveform_conversion_indices]
    relative_time_s, waveform_records = interpolate_wave_records(
        times_s,
        signals,
        [(float(start_s), float(start_s + record_duration_s)) for start_s in waveform_starts_s],
        waveform_samples,
    )

    readbacks: dict[str, str | int | float | bool] = {
        "raw_file": Path(raw_path).name,
        "raw_format": "spectre_nutascii",
        "raw_points": len(times_s),
        "decision_sample_fraction": decision_sample_fraction,
        "supply_power_available": True,
        "supply_current_convention": "positive_current_draw",
    }
    rail_voltages = {
        "vdd_a": float(params.vdd_a.dc),
        "vdd_d": float(params.vdd_d.dc),
        "vdd_dac": float(params.vdd_dac.dc),
    }
    for rail, voltage_v in rail_voltages.items():
        current_draw_a = signals[f"{rail}_i"]
        duration_s = float(times_s[-1] - times_s[0])
        average_current_a = float(
            np.trapezoid(current_draw_a, times_s) / duration_s
        )
        readbacks[f"{rail}_active_average_current_a"] = average_current_a
        readbacks[f"{rail}_active_average_power_w"] = voltage_v * average_current_a

    return MeasAdcInt(
        info=MeasInfo(
            schema_version=1,
            measurement_type="MeasAdcInt",
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
        wave=AdcIntWave(
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
    signal_names: Mapping[str, str],
    maximum_waveform_records: int = 128,
) -> Path:
    """Read one Spectre ADC raw file and write the shared typed HDF5 format."""

    selected_signals = set(signal_names.values())
    data = read_spectre_nutascii(raw_path, selected_signals)
    measurement = convert_spectre_adc_to_measurement(
        data,
        params=params,
        raw_path=raw_path,
        signal_names=signal_names,
        maximum_waveform_records=maximum_waveform_records,
    )
    return write_measurement(h5_path, measurement)
