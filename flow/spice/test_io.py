"""Software-only tests for Spectre NUTASCII and typed ADC HDF5 conversion."""

from pathlib import Path

import numpy as np
import pytest

from flow.analysis.io import read_measurement
from flow.analysis.types import MeasAdcExt
from flow.scans.params import AdcTbParams
from flow.spice.io import (
    convert_spectre_adc_raw_to_h5,
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
    times_s = np.arange(0.0, 370.0e-9, 1.0e-9)
    phase_s = np.mod(times_s, 20.0e-9)
    seq_comp_v = np.where(phase_s >= 10.0e-9, 1.2, 0.0)
    comp_out_v = np.zeros_like(times_s)
    for decision_index, bit in enumerate(expected_bout):
        start_s = 10.0e-9 + decision_index * 20.0e-9
        stop_s = start_s + 20.0e-9
        comp_out_v[(times_s >= start_s) & (times_s < stop_s)] = 1.2 * int(bit)
    values = {
        "time": times_s,
        "comp_out": comp_out_v,
        "seq_comp": seq_comp_v,
        "seq_update": np.zeros_like(times_s),
        "vin_p": np.full_like(times_s, 0.650),
        "vin_n": np.full_like(times_s, 0.600),
        "ivdd_a": np.full_like(times_s, -2.0e-6),
        "ivdd_d": np.full_like(times_s, -40.0e-6),
        "ivdd_dac": np.full_like(times_s, -20.0e-6),
    }
    raw_path = tmp_path / "adc.raw"
    names = tuple(values)
    lines = [
        "Title: synthetic ADC",
        f"No. Variables: {len(names)}",
        f"No. Points: {len(times_s)}",
        "Variables:",
    ]
    lines.extend(f"{index} {name} {'s' if name == 'time' else 'V'}" for index, name in enumerate(names))
    lines.append("Values:")
    for point_index in range(len(times_s)):
        lines.append(" ".join([str(point_index)] + [f"{values[name][point_index]:.16g}" for name in names]))
    raw_path.write_text("\n".join(lines) + "\n")

    h5_path = tmp_path / "adc.h5"
    convert_spectre_adc_raw_to_h5(
        raw_path,
        h5_path,
        params=AdcTbParams(conversions=1),
        rail_current_signals={
            "vdd_a": "ivdd_a",
            "vdd_d": "ivdd_d",
            "vdd_dac": "ivdd_dac",
        },
        maximum_waveform_records=1,
    )
    measurement = read_measurement(h5_path)

    assert isinstance(measurement, MeasAdcExt)
    assert measurement.info.backend == "spice"
    assert measurement.info.readbacks["raw_format"] == "spectre_nutascii"
    assert measurement.info.readbacks["supply_power_available"] is True
    assert measurement.info.readbacks["vdd_d_active_average_power_w"] == pytest.approx(48.0e-6)
    assert "".join(str(bit) for bit in measurement.daq.bout[0]) == expected_bout
    assert measurement.daq.dout_raw[0] > 0
    assert measurement.daq.dout[0] > 0
    assert measurement.daq.vin_diff_v[0] == pytest.approx(0.050)
    assert measurement.wave.comp_out_v.shape == (1, 2_000)
