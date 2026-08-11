"""Software-only tests for Spectre NUTASCII and typed ADC HDF5 conversion."""

import dataclasses
from pathlib import Path

import numpy as np
import pytest

from flow.analysis.io import read_measurement
from flow.analysis.types import AdcIntWave, CompIntWave, MeasAdcInt, MeasCompInt
from flow.comp.sim import CompTbParams
from flow.scans.params import AdcTbParams
from flow.spice.io import (
    convert_spectre_adc_raw_to_h5,
    convert_spectre_adc_to_measurement,
    convert_spectre_comp_raw_to_h5,
    read_spectre_nutascii,
)


def test_nutascii_reader_streams_selected_wrapped_signals(tmp_path: Path) -> None:
    raw_path = tmp_path / "spectre.raw"
    raw_path.write_text(
        "Title: test\n"
        "No. Variables: 3\n"
        "No. Points: 3\n"
        "Variables:\t0\ttime\ts\n"
        "\t\t1\tout\tV\n"
        "\t\t2\tunused\tV\n"
        "Values:\n"
        "0 0.0 0.1\n"
        "7.0\n"
        "1 1e-9\n"
        "0.4 8.0\n"
        "2 2e-9 0.9 9.0\n"
    )

    values = read_spectre_nutascii(raw_path, {"time", "out"})

    assert set(values) == {"time", "out"}
    np.testing.assert_allclose(values["time"], [0.0, 1.0e-9, 2.0e-9])
    np.testing.assert_allclose(values["out"], [0.1, 0.4, 0.9])


def test_nutascii_reader_rejects_incomplete_output(tmp_path: Path) -> None:
    raw_path = tmp_path / "incomplete.raw"
    raw_path.write_text("Title: incomplete\nVariables:\n0 time time\n")

    with pytest.raises(ValueError, match="Values"):
        read_spectre_nutascii(raw_path)


def test_adc_raw_conversion_writes_shared_hdf5(tmp_path: Path) -> None:
    expected_bout = "10110100101100101"
    time_step_s = 0.05e-9
    conversion_offsets_s = np.asarray([0.0, 170.0e-9])
    times_s = np.arange(0.0, 340.0e-9 + time_step_s / 2, time_step_s)
    comp_edge_times_s = np.concatenate(
        [offset_s + 5.0e-9 + np.arange(17) * 8.0e-9 for offset_s in conversion_offsets_s]
    )
    logic_edge_times_s = np.concatenate(
        [offset_s + 5.0e-9 + np.arange(16) * 8.0e-9 + 3.0e-9 for offset_s in conversion_offsets_s]
    )

    # The ADC has 17 comparator decisions but only 16 DAC-update/ LOGIC edges:
    # its final decision does not update the CDAC. Put each decision transition
    # at 97% of the COMP-to-LOGIC interval. The production 98% sampling point
    # must decode the new bit, whereas an earlier 95% sample still sees the
    # preceding decision. This also checks extrapolation of the final interval.
    seq_comp_v = np.zeros_like(times_s)
    seq_logic_v = np.zeros_like(times_s)
    for edge_s in comp_edge_times_s:
        seq_comp_v[(times_s >= edge_s) & (times_s < edge_s + 0.5e-9)] = 1.2
    for edge_s in logic_edge_times_s:
        seq_logic_v[(times_s >= edge_s) & (times_s < edge_s + 0.5e-9)] = 1.2

    comp_out_v = np.zeros_like(times_s)
    repeated_bout = expected_bout * len(conversion_offsets_s)
    for decision_index, bit in enumerate(repeated_bout):
        transition_s = comp_edge_times_s[decision_index] + 0.97 * 3.0e-9
        stop_s = (
            comp_edge_times_s[decision_index + 1] + 0.97 * 3.0e-9
            if decision_index + 1 < len(repeated_bout)
            else times_s[-1] + time_step_s
        )
        comp_out_v[(times_s >= transition_s) & (times_s < stop_s)] = 1.2 * int(bit)

    raw_wave_names = tuple(
        field.name
        for field in dataclasses.fields(AdcIntWave)
        if field.name not in {"conversion_index", "time_s", "vin_diff_v"}
    )
    values = {name: np.zeros_like(times_s) for name in raw_wave_names}
    values.update(
        {
            "vin_p_v": np.full_like(times_s, 0.650),
            "vin_n_v": np.full_like(times_s, 0.600),
            "seq_init_v": np.where(
                ((times_s >= 1.0e-9) & (times_s < 2.0e-9)) | ((times_s >= 171.0e-9) & (times_s < 172.0e-9)),
                1.2,
                0.0,
            ),
            "seq_comp_v": seq_comp_v,
            "seq_logic_v": seq_logic_v,
            "comp_out_v": comp_out_v,
            # Spectre voltage-source current is into the source positive
            # terminal, hence negative while each rail delivers current.
            "vdd_a_i": np.full_like(times_s, -2.0e-6),
            "vdd_d_i": np.full_like(times_s, -40.0e-6),
            "vdd_dac_i": np.full_like(times_s, -20.0e-6),
        }
    )
    values = {
        "time": times_s,
        **values,
    }
    signal_names = {"time_s": "time", **{name: name for name in raw_wave_names}}
    raw_path = tmp_path / "adc.raw"
    names = tuple(values)
    lines = [
        "Title: synthetic ADC",
        f"No. Variables: {len(names)}",
        f"No. Points: {len(times_s)}",
        "Variables:",
    ]
    lines.extend(
        f"{index} {name} {'s' if name == 'time' else 'A' if name.endswith('_i') else 'V'}"
        for index, name in enumerate(names)
    )
    lines.append("Values:")
    for point_index in range(len(times_s)):
        lines.append(" ".join([str(point_index)] + [f"{values[name][point_index]:.16g}" for name in names]))
    raw_path.write_text("\n".join(lines) + "\n")

    params = AdcTbParams(conversions=2)
    early_measurement = convert_spectre_adc_to_measurement(
        values,
        params=params,
        raw_path=raw_path,
        signal_names=signal_names,
        decision_sample_fraction=0.95,
        maximum_waveform_records=1,
    )
    assert "".join(str(bit) for bit in early_measurement.daq.bout[0]) != expected_bout

    h5_path = tmp_path / "adc.h5"
    convert_spectre_adc_raw_to_h5(
        raw_path,
        h5_path,
        params=params,
        signal_names=signal_names,
    )
    measurement = read_measurement(h5_path)

    assert isinstance(measurement, MeasAdcInt)
    assert measurement.info.backend == "spice"
    assert measurement.info.readbacks["raw_format"] == "spectre_nutascii"
    assert measurement.info.readbacks["raw_max_timestep_s"] == pytest.approx(time_step_s)
    assert measurement.info.readbacks["waveform_sample_interval_s"] == pytest.approx(25e-12)
    assert measurement.info.readbacks["waveform_interpolated_from_coarser_raw"] is True
    assert measurement.info.readbacks["decision_sample_fraction"] == pytest.approx(0.98)
    assert measurement.info.readbacks["supply_power_available"] is True
    assert measurement.info.readbacks["supply_current_convention"] == "positive_current_draw"
    assert measurement.info.readbacks["vdd_d_active_average_power_w"] == pytest.approx(48.0e-6)
    assert len(measurement.daq.conversion_index) == 2
    assert all("".join(str(bit) for bit in row) == expected_bout for row in measurement.daq.bout)
    np.testing.assert_array_equal(measurement.daq.bout[0, -2:], [0, 1])
    assert measurement.daq.dout_raw[0] > 0
    assert measurement.daq.dout[0] > 0
    assert measurement.daq.vin_diff_v[0] == pytest.approx(0.050)
    np.testing.assert_array_equal(measurement.wave.conversion_index, [0, 1])
    assert measurement.wave.comp_out_v.shape == (2, 6_800)
    np.testing.assert_allclose(np.diff(measurement.wave.time_s), 25e-12)
    assert measurement.wave.seq_init_v[0, 0] == pytest.approx(0.0)
    np.testing.assert_allclose(measurement.wave.vdd_a_i, 2.0e-6)
    np.testing.assert_allclose(measurement.wave.vdd_d_i, 40.0e-6)
    np.testing.assert_allclose(measurement.wave.vdd_dac_i, 20.0e-6)


def test_comp_raw_conversion_reuses_shared_typed_hdf5_path(tmp_path: Path) -> None:
    params = CompTbParams(
        sweep_min_v=-100e-6,
        sweep_max_v=100e-6,
        sweep_step_v=100e-6,
        conversions=2,
    )
    time_step_s = 0.5e-9
    cycle_s = 40e-9
    trial_count = 6
    times_s = np.arange(0.0, trial_count * cycle_s + time_step_s / 2.0, time_step_s)
    decisions = np.asarray([0, 0, 0, 1, 1, 1], dtype=np.uint8)
    clock = np.zeros_like(times_s)
    comp_difference = np.zeros_like(times_s)
    output_difference = np.zeros_like(times_s)
    previous_sign = -1.0
    for trial, decision in enumerate(decisions):
        start_s = trial * cycle_s
        eval_start_s = start_s + 10e-9
        stop_s = start_s + cycle_s
        active = (times_s >= eval_start_s) & (times_s < stop_s)
        clock[active] = 1.2
        sign = 1.0 if decision else -1.0
        resolved = (times_s >= eval_start_s + 2e-9) & (times_s < stop_s)
        comp_difference[resolved] = sign
        output_difference[(times_s >= start_s) & (times_s < eval_start_s + 2e-9)] = previous_sign
        output_difference[resolved] = sign
        previous_sign = sign

    values = {
        "time": times_s,
        "vin_p": np.full_like(times_s, 0.8),
        "vin_n": np.full_like(times_s, 0.8),
        "clock": clock,
        "vout_p": 0.6 + output_difference / 2.0,
        "vout_n": 0.6 - output_difference / 2.0,
        "comp_p": 0.6 + comp_difference / 2.0,
        "comp_n": 0.6 - comp_difference / 2.0,
        "vdd_i": np.full_like(times_s, -10e-6),
    }
    signal_names = {
        "time_s": "time",
        "vin_p_v": "vin_p",
        "vin_n_v": "vin_n",
        "clock_v": "clock",
        "vout_p_v": "vout_p",
        "vout_n_v": "vout_n",
        "comp_p_v": "comp_p",
        "comp_n_v": "comp_n",
        "vdd_i": "vdd_i",
    }
    raw_path = tmp_path / "comp.raw"
    names = tuple(values)
    lines = [
        "Title: synthetic comparator",
        f"No. Variables: {len(names)}",
        f"No. Points: {len(times_s)}",
        "Variables:",
    ]
    lines.extend(
        f"{index} {name} {'s' if name == 'time' else 'A' if name == 'vdd_i' else 'V'}"
        for index, name in enumerate(names)
    )
    lines.append("Values:")
    for point_index in range(len(times_s)):
        lines.append(" ".join([str(point_index)] + [f"{values[name][point_index]:.16g}" for name in names]))
    raw_path.write_text("\n".join(lines) + "\n")

    h5_path = tmp_path / "comp.h5"
    convert_spectre_comp_raw_to_h5(
        raw_path,
        h5_path,
        params=params,
        signal_names=signal_names,
        candidate_id="synthetic",
        candidate_label="Synthetic comparator",
        topology_index=0,
        size_profile="fabricated",
        total_width_units=100,
        device_width_signature=(("M0", 40), ("M1", 60)),
        total_active_area_units=160,
        total_active_area_um2=1.152,
        device_geometry_signature=(("M0", 40, 1), ("M1", 60, 2)),
    )
    measurement = read_measurement(h5_path)

    assert isinstance(measurement, MeasCompInt)
    assert isinstance(measurement.wave, CompIntWave)
    assert measurement.param == params
    assert measurement.info.readbacks["candidate_id"] == "synthetic"
    assert measurement.info.readbacks["total_active_area_units"] == 160
    assert measurement.info.readbacks["total_active_area_um2"] == pytest.approx(1.152)
    assert measurement.info.readbacks["raw_format"] == "spectre_nutascii"
    assert measurement.info.readbacks["vdd_active_average_power_w"] == pytest.approx(12e-6)
    assert measurement.info.readbacks["energy_per_decision_j"] == pytest.approx(480e-15)
    np.testing.assert_allclose(measurement.daq.vin_diff_v, [-100e-6, -100e-6, 0.0, 0.0, 100e-6, 100e-6])
    np.testing.assert_array_equal(measurement.daq.decision, decisions)
    np.testing.assert_array_equal(measurement.wave.trial_index, np.arange(6))
    assert measurement.wave.clock_v.shape == (6, 80)
    np.testing.assert_allclose(measurement.wave.vdd_i, 10e-6)
