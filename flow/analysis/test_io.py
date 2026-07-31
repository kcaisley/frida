"""Software-only tests for HDF5 and acquisition-wave adapters."""

from types import SimpleNamespace

import numpy as np

from flow.analysis.io import (
    build_adc_interface_wave,
    scope_records_to_adc_wave,
)
from flow.scans.params import AdcTbParams


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
