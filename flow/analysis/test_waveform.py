"""Plot preparation from the single stored waveform representation."""

from dataclasses import replace

import h5py
import numpy as np
import pytest

from flow.analysis.io import read_measurement, write_measurement
from flow.analysis.test_adc import adc_cdac_settling_measurement
from flow.analysis.waveform import analyze_measurement_waveforms


def test_waveform_reference_and_hdf5_preserve_internal_samples(tmp_path):
    measurement = adc_cdac_settling_measurement()
    path = write_measurement(tmp_path / "measurement.h5", measurement)
    with h5py.File(path) as stored:
        assert "native_wave" not in stored
        assert "comp.latch_p" in stored["wave/voltage"]
        assert "dac_botplate_p[15]" in stored["wave/voltage"]
    restored = read_measurement(path)
    result = analyze_measurement_waveforms(
        restored,
        signal_names=("comp.latch_p", "seq_comp"),
        reference_signal="seq_comp",
        threshold_v=0.6,
    )
    assert result.signal_units == ("V", "V")
    np.testing.assert_array_equal(result.signal_values[0], measurement.wave.voltage["comp.latch_p"][0])
    np.testing.assert_allclose(result.time_s + result.time_origin_s, measurement.wave.time_s, rtol=0, atol=1e-24)


def test_waveform_canonical_current_names():
    measurement = adc_cdac_settling_measurement()
    result = analyze_measurement_waveforms(measurement, signal_names=("i(vdd_a)",))
    assert result.signal_units == ("A",)


@pytest.mark.parametrize("settings", ({"record_index": 4}, {"signal_names": ("typo",)}, {"window_s": (-1.0, 1.0)}))
def test_waveform_rejects_unavailable_data(settings):
    with pytest.raises((ValueError, IndexError)):
        analyze_measurement_waveforms(adc_cdac_settling_measurement(), **settings)


def test_waveform_rejects_misspelled_canonical_net():
    wave = adc_cdac_settling_measurement().wave
    with pytest.raises(ValueError, match="Unknown canonical"):
        replace(wave, voltage={**wave.voltage, "vdca_p": wave.voltage["vdac_p"]})


def test_plot_context_uses_current_conversion_definition_and_reports_repetition():
    from flow.adc.sequences import ORIGINAL
    from flow.analysis.waveform import style_measurement_text

    measurement = adc_cdac_settling_measurement()
    measurement = replace(
        measurement,
        param=replace(measurement.param, symbol_rate=1.6e9, **ORIGINAL.as_tb_fields()),
        info=replace(measurement.info, readbacks={"active_conversion_rate_hz": 123}),
    )
    lines = style_measurement_text(measurement)
    assert "Conversion: 10 MSPS" in lines
    assert "Repetition: 160 ns" in lines
