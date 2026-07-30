"""Software-only tests for raw-source adapters used by typed measurements."""

from types import SimpleNamespace

import numpy as np
import pytest

from flow.analysis.io import (
    build_adc_interface_wave,
    parse_spectre_nutascii,
    scope_records_to_adc_wave,
)
from flow.scans.params import AdcTbParams


def test_spectre_nutascii_parser_selects_named_signals(tmp_path) -> None:
    raw_path = tmp_path / "spectre.raw"
    raw_path.write_text(
        "Title: test\n"
        "Variables:\n"
        "0 time time\n"
        "1 out voltage\n"
        "2 unused voltage\n"
        "Values:\n"
        "0 0.0 0.1 7.0\n"
        "1 1e-9 0.4 8.0\n"
        "2 2e-9 0.9 9.0\n"
    )

    values = parse_spectre_nutascii(raw_path, {"time", "out"})

    assert set(values) == {"time", "out"}
    np.testing.assert_allclose(values["time"], [0.0, 1.0e-9, 2.0e-9])
    np.testing.assert_allclose(values["out"], [0.1, 0.4, 0.9])


def test_spectre_nutascii_parser_rejects_incomplete_output(tmp_path) -> None:
    raw_path = tmp_path / "incomplete.raw"
    raw_path.write_text("Title: incomplete\nVariables:\n0 time time\n")

    with pytest.raises(ValueError, match="missing 'Values:'"):
        parse_spectre_nutascii(raw_path)


def test_scope_records_build_dense_adc_external_wave() -> None:
    scale = SimpleNamespace(offset=-1.0e-9, slope=1.0e-9)

    def waveform(values):
        return SimpleNamespace(x_scale=scale, data=np.asarray(values))

    records = [
        {
            1: waveform([0.0, 0.1, 0.2]),
            2: waveform([0.0, 1.2, 0.0]),
            3: waveform([1.2, 0.0, 1.2]),
            4: waveform([0.0, 0.0, 1.2]),
        },
        {
            1: waveform([0.2, 0.1, 0.0]),
            2: waveform([1.2, 0.0, 1.2]),
            3: waveform([0.0, 1.2, 0.0]),
            4: waveform([1.2, 1.2, 0.0]),
        },
    ]
    wave = scope_records_to_adc_wave(
        records,
        [3, 9],
        {
            "vin_diff_v": 1,
            "seq_comp_v": 2,
            "seq_logic_v": 3,
            "comp_out_v": 4,
        },
    )

    np.testing.assert_array_equal(wave.conversion_index, [3, 9])
    np.testing.assert_allclose(wave.time_s, [-1.0e-9, 0.0, 1.0e-9])
    assert wave.vin_diff_v.shape == (2, 3)
    np.testing.assert_allclose(wave.comp_out_v[1], [1.2, 1.2, 0.0])


def test_behavioral_adapter_builds_one_complete_interface_record() -> None:
    params = AdcTbParams(conversions=1)
    wave = build_adc_interface_wave(params, [1] * 17, samples_per_symbol=2)

    assert wave.conversion_index.tolist() == [0]
    assert wave.vin_diff_v.shape == (1, 2 * len(params.seq_init_pattern))
    assert wave.seq_comp_v.shape == wave.vin_diff_v.shape
    assert np.count_nonzero(np.diff(wave.comp_out_v[0])) <= 1
