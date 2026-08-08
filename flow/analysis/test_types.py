"""Tests for typed measurement sections and uniform HDF5 persistence."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import h5py
import numpy as np
import pytest

import flow.analysis.io as analysis_io
from flow.analysis.io import interpolate_wave_records, read_measurement, write_measurement
from flow.analysis.types import (
    AdcDaq,
    AdcExtWave,
    AdcIntWave,
    Backend,
    CdacExtDaq,
    CdacExtWave,
    CdacIntDaq,
    CdacIntWave,
    CompDaq,
    CompExtWave,
    CompIntWave,
    MeasAdc,
    MeasAdcExt,
    MeasAdcInt,
    MeasCdacExt,
    MeasCdacInt,
    MeasCompExt,
    MeasCompInt,
    MeasInfo,
    MeasSampInt,
    SampDaq,
    SampIntWave,
)
from flow.cdac.sim import CdacTbParams
from flow.comp.sim import CompTbParams
from flow.samp.sim import SampTbParams
from flow.scans.params import AdcTbParams


def adc_measurement() -> MeasAdcExt:
    """Return one small, fully populated external ADC measurement."""

    time_s = np.linspace(0.0, 10e-9, 8)
    return MeasAdcExt(
        info=MeasInfo(
            schema_version=1,
            measurement_type="MeasAdcExt",
            backend="physical",
            timestamp_utc=datetime(2026, 7, 29, 12, 0, tzinfo=UTC),
            instruments={"scope": "MSO54", "fpga": "BDAQ53"},
            readbacks={"vdd_a_v": 1.199, "locked": True},
        ),
        param=AdcTbParams(
            board_id="00",
            observed_adc=0,
            active_adc_mask=(0,) * 15 + (1,),
            conversions=2,
        ),
        daq=AdcDaq(
            conversion_index=np.array([0, 1]),
            bout=np.array([[0, 1] * 8 + [0], [1, 0] * 8 + [1]]),
            dout_raw=np.array([123, 456]),
            dout=np.array([120, 450]),
            vin_diff_v=np.array([0.01, 0.02]),
            fastrx_word=np.array([0x10000001, 0x10020002]),
        ),
        wave=AdcExtWave(
            conversion_index=np.array([1]),
            time_s=time_s,
            vin_diff_v=np.sin(2 * np.pi * time_s / time_s[-1])[None, :],
            seq_comp_v=np.tile([0.0, 0.0, 1.2, 1.2], 2)[None, :],
            seq_logic_v=np.tile([0.0, 1.2], 4)[None, :],
            comp_out_v=np.tile([0.0, 0.0, 1.2, 1.2], 2)[None, :],
        ),
    )


def info(measurement_type: str, backend: Backend = "spice") -> MeasInfo:
    return MeasInfo(
        schema_version=1,
        measurement_type=measurement_type,
        backend=backend,
        timestamp_utc=datetime(2026, 7, 29, 12, 0, tzinfo=UTC),
    )


def dense_signals(names: tuple[str, ...]) -> dict[str, np.ndarray]:
    return {name: np.arange(8, dtype=float).reshape(1, 8) for name in names}


def all_measurements():
    """Return one minimal instance of every supported measurement type."""

    adc_daq = AdcDaq(
        conversion_index=np.asarray([0], dtype=np.int64),
        bout=np.zeros((1, 17), dtype=np.uint8),
        dout_raw=np.asarray([0], dtype=np.int64),
        dout=np.asarray([0], dtype=np.int64),
        vin_diff_v=np.asarray([0.0], dtype=np.float64),
    )
    adc_int_names = (
        "vin_diff_v",
        "seq_comp_v",
        "seq_logic_v",
        "comp_out_v",
        "vin_p_v",
        "vin_n_v",
        "seq_init_v",
        "seq_samp_v",
        "vdac_p_v",
        "vdac_n_v",
        "clk_samp_p_v",
        "clk_samp_p_b_v",
        "clk_samp_n_v",
        "clk_samp_n_b_v",
        "clk_comp_v",
        "comp_out_p_v",
        "comp_out_n_v",
        "dac_state_p_15_v",
        "dac_state_p_8_v",
        "dac_state_p_0_v",
        "dac_state_n_15_v",
        "dac_state_n_8_v",
        "dac_state_n_0_v",
        "dac_botplate_p_15_v",
        "dac_botplate_p_8_v",
        "dac_botplate_p_0_v",
        "dac_botplate_n_15_v",
        "dac_botplate_n_8_v",
        "dac_botplate_n_0_v",
        "vdd_a_i",
        "vdd_d_i",
        "vdd_dac_i",
    )
    comp_daq = CompDaq(
        trial_index=np.asarray([0], dtype=np.int64),
        vin_diff_v=np.asarray([0.0], dtype=np.float64),
        vin_cm_v=np.asarray([0.6], dtype=np.float64),
        decision=np.asarray([1], dtype=np.uint8),
    )
    comp_ext_daq = CompDaq(
        trial_index=np.asarray([0], dtype=np.int64),
        vin_diff_v=np.asarray([0.0], dtype=np.float64),
        vin_cm_v=np.asarray([0.6], dtype=np.float64),
        decision=np.asarray([1], dtype=np.uint8),
        fastrx_word=np.asarray([0x10000001], dtype=np.uint32),
        fastrx_frame=np.asarray([0], dtype=np.uint32),
    )
    dac_states = np.zeros((1, 16), dtype=np.uint8)
    return (
        MeasAdcInt(
            info=info("MeasAdcInt"),
            param=AdcTbParams(conversions=1),
            daq=adc_daq,
            wave=AdcIntWave(
                conversion_index=np.asarray([0], dtype=np.int64),
                time_s=np.arange(8, dtype=float),
                **dense_signals(adc_int_names),
            ),
        ),
        MeasCompExt(
            info=info("MeasCompExt", "physical"),
            param=AdcTbParams(conversions=1),
            daq=comp_ext_daq,
            wave=CompExtWave(
                trial_index=np.asarray([0], dtype=np.int64),
                time_s=np.arange(8, dtype=float),
                **dense_signals(("vin_diff_v", "seq_comp_v", "comp_out_v")),
            ),
        ),
        MeasCompInt(
            info=info("MeasCompInt"),
            param=CompTbParams(),
            daq=comp_daq,
            wave=CompIntWave(
                trial_index=np.asarray([0], dtype=np.int64),
                time_s=np.arange(8, dtype=float),
                **dense_signals(
                    (
                        "vin_p_v",
                        "vin_n_v",
                        "clock_v",
                        "vout_p_v",
                        "vout_n_v",
                        "comp_p_v",
                        "comp_n_v",
                        "vdd_i",
                    )
                ),
            ),
        ),
        MeasSampInt(
            info=info("MeasSampInt"),
            param=SampTbParams(),
            daq=SampDaq(trial_index=np.asarray([0], dtype=np.int64)),
            wave=SampIntWave(
                trial_index=np.asarray([0], dtype=np.int64),
                time_s=np.arange(8, dtype=float),
                **dense_signals(("vin_v", "sampled_v", "clk_v", "clk_b_v", "vdd_i")),
            ),
        ),
        MeasCdacExt(
            info=info("MeasCdacExt", "physical"),
            param=AdcTbParams(conversions=1),
            daq=CdacExtDaq(
                trial_index=np.asarray([0], dtype=np.int64),
                dac_state_p=dac_states,
                dac_state_n=dac_states,
                vin_diff_v=np.asarray([0.0], dtype=np.float64),
                decision=np.asarray([1], dtype=np.uint8),
                dac_state_before_p=dac_states,
                dac_state_before_n=dac_states,
                vin_cm_v=np.asarray([0.8], dtype=np.float64),
                fastrx_word=np.asarray([0x10000001], dtype=np.uint32),
                fastrx_frame=np.asarray([0], dtype=np.uint32),
            ),
            wave=CdacExtWave(
                trial_index=np.asarray([0], dtype=np.int64),
                time_s=np.arange(8, dtype=float),
                **dense_signals(("vin_diff_v", "seq_comp_v", "comp_out_v", "seq_logic_v")),
            ),
        ),
        MeasCdacInt(
            info=info("MeasCdacInt"),
            param=CdacTbParams(),
            daq=CdacIntDaq(
                trial_index=np.asarray([0], dtype=np.int64),
                dac_state_p=dac_states,
                dac_state_n=dac_states,
            ),
            wave=CdacIntWave(
                trial_index=np.asarray([0], dtype=np.int64),
                time_s=np.arange(8, dtype=float),
                **dense_signals(("vdac_p_v", "vdac_n_v", "update_v", "vdd_i")),
            ),
        ),
    )


def assert_sections_equal(expected, actual) -> None:
    for data_field in expected.__dataclass_fields__:
        expected_value = getattr(expected, data_field)
        actual_value = getattr(actual, data_field)
        if expected_value is None:
            assert actual_value is None
        else:
            assert actual_value.dtype == expected_value.dtype
            np.testing.assert_array_equal(actual_value, expected_value)


def test_adc_internal_wave_is_explicit_external_superset() -> None:
    """Keep shared analyses valid while retaining the important internal nodes."""

    external_fields = set(AdcExtWave.__dataclass_fields__)
    internal_fields = set(AdcIntWave.__dataclass_fields__)
    signal_fields = internal_fields.difference({"conversion_index", "time_s"})

    assert external_fields <= internal_fields
    assert len(signal_fields) >= 30
    assert {
        "clk_samp_p_v",
        "clk_samp_p_b_v",
        "clk_samp_n_v",
        "clk_samp_n_b_v",
        "clk_comp_v",
        "comp_out_p_v",
        "comp_out_n_v",
        "dac_state_p_15_v",
        "dac_state_p_8_v",
        "dac_state_p_0_v",
        "dac_state_n_15_v",
        "dac_state_n_8_v",
        "dac_state_n_0_v",
        "dac_botplate_p_15_v",
        "dac_botplate_p_8_v",
        "dac_botplate_p_0_v",
        "dac_botplate_n_15_v",
        "dac_botplate_n_8_v",
        "dac_botplate_n_0_v",
        "vdd_a_i",
        "vdd_d_i",
        "vdd_dac_i",
    } <= signal_fields


def test_adc_measurement_round_trip_uses_native_hdf5_groups(tmp_path: Path) -> None:
    """Round-trip exact array dtypes, values, parameters, and run information."""

    original = adc_measurement()
    path = write_measurement(tmp_path / "adc.h5", original)
    with h5py.File(path, "r") as stored:
        assert set(stored) == {"info", "param", "daq", "wave"}
        assert "metadata_json" not in stored
        assert stored["daq/bout"].dtype == np.uint8
        assert stored["daq/bout"].shape == (2, 17)
        assert stored["wave/comp_out_v"].chunks == (1, 8)

    loaded = read_measurement(path)
    assert isinstance(loaded, MeasAdcExt)
    assert loaded.info.source_path == path
    assert loaded.info.backend == original.info.backend
    assert loaded.info.instruments == original.info.instruments
    assert loaded.info.readbacks == original.info.readbacks
    assert loaded.param == original.param
    for field in ("conversion_index", "bout", "dout_raw", "dout", "vin_diff_v", "fastrx_word"):
        expected = getattr(original.daq, field)
        actual = getattr(loaded.daq, field)
        assert actual.dtype == expected.dtype
        np.testing.assert_array_equal(actual, expected)
    for field in ("conversion_index", "time_s", "vin_diff_v", "seq_comp_v", "seq_logic_v", "comp_out_v"):
        expected = getattr(original.wave, field)
        actual = getattr(loaded.wave, field)
        assert actual.dtype == expected.dtype
        np.testing.assert_array_equal(actual, expected)


def test_parameter_reader_applies_defaults_added_after_capture(tmp_path: Path) -> None:
    """Keep older HDF5 results readable when parameter classes gain fields."""

    path = write_measurement(tmp_path / "legacy.h5", adc_measurement())
    with h5py.File(path, "a") as stored:
        cdac = stored["param/dut/cdac"]
        del cdac["driver_p_w"]
        del cdac["driver_n_w"]
        del cdac["driver_strengths"]

    loaded = read_measurement(path)
    assert isinstance(loaded, MeasAdcExt)
    assert loaded.param.dut.cdac.driver_p_w == 9
    assert loaded.param.dut.cdac.driver_n_w == 7
    assert loaded.param.dut.cdac.driver_strengths is None


@pytest.mark.parametrize("measurement", all_measurements(), ids=lambda value: type(value).__name__)
def test_every_measurement_type_round_trips(tmp_path: Path, measurement) -> None:
    """Use the same writer and reader for every supported measurement class."""

    path = write_measurement(tmp_path / f"{type(measurement).__name__}.h5", measurement)
    loaded = read_measurement(path)

    assert type(loaded) is type(measurement)
    if isinstance(loaded, (MeasAdcExt, MeasAdcInt)):
        adc: MeasAdc = loaded
        assert adc is loaded
    assert loaded.param == measurement.param
    assert loaded.info.measurement_type == measurement.info.measurement_type
    assert_sections_equal(measurement.daq, loaded.daq)
    assert_sections_equal(measurement.wave, loaded.wave)


@pytest.mark.parametrize("measurement_index", (1, 4), ids=("comparator", "cdac"))
def test_external_decision_measurement_without_scope_waveform_round_trips(
    tmp_path: Path,
    measurement_index: int,
) -> None:
    original = replace(all_measurements()[measurement_index], wave=None)

    loaded = read_measurement(write_measurement(tmp_path / f"no_wave_{measurement_index}.h5", original))

    assert type(loaded) is type(original)
    assert loaded.wave is None
    assert_sections_equal(original.daq, loaded.daq)


@pytest.mark.parametrize("measurement_index", (2, 5), ids=("MeasCompInt-AdcTbParams", "MeasCdacInt-AdcTbParams"))
def test_whole_adc_internal_measurement_parameter_pairings_round_trip(
    tmp_path: Path,
    measurement_index: int,
) -> None:
    """Keep whole-chip and PEX results on their native AdcTbParams stack."""

    original = replace(
        all_measurements()[measurement_index],
        param=AdcTbParams(conversions=1),
    )
    loaded = read_measurement(write_measurement(tmp_path / f"pairing_{measurement_index}.h5", original))

    assert type(loaded) is type(original)
    assert type(loaded.param) is AdcTbParams
    assert loaded.param == original.param


def test_schema_v1_external_cdac_without_switching_fields_remains_readable(tmp_path: Path) -> None:
    """Treat legacy P/N state arrays as the after-update state."""

    current = all_measurements()[4]
    legacy = replace(
        current,
        daq=CdacExtDaq(
            trial_index=current.daq.trial_index,
            dac_state_p=current.daq.dac_state_p,
            dac_state_n=current.daq.dac_state_n,
            vin_diff_v=current.daq.vin_diff_v,
            decision=current.daq.decision,
        ),
    )
    loaded = read_measurement(write_measurement(tmp_path / "legacy_cdac.h5", legacy))

    assert isinstance(loaded, MeasCdacExt)
    assert loaded.daq.dac_state_before_p is None
    assert loaded.daq.dac_state_before_n is None
    assert loaded.daq.vin_cm_v is None
    assert loaded.daq.fastrx_word is None


def test_schema_v2_physical_measurements_require_transport_and_switching_fields() -> None:
    """Require the new acquisition evidence without invalidating schema-v1 files."""

    comp = all_measurements()[1]
    with pytest.raises(ValueError, match="schema-v2 physical MeasCompExt"):
        replace(
            comp,
            info=replace(comp.info, schema_version=2),
            daq=replace(comp.daq, fastrx_word=None, fastrx_frame=None),
        )

    cdac = all_measurements()[4]
    with pytest.raises(ValueError, match="schema-v2 physical MeasCdacExt"):
        replace(
            cdac,
            info=replace(cdac.info, schema_version=2),
            daq=CdacExtDaq(
                trial_index=cdac.daq.trial_index,
                dac_state_p=cdac.daq.dac_state_p,
                dac_state_n=cdac.daq.dac_state_n,
                vin_diff_v=cdac.daq.vin_diff_v,
                decision=cdac.daq.decision,
            ),
        )


def test_reader_rejects_missing_required_dataset(tmp_path: Path) -> None:
    """Reject a structurally incomplete measurement before constructing it."""

    path = write_measurement(tmp_path / "incomplete.h5", adc_measurement())
    with h5py.File(path, "a") as stored:
        del stored["wave/comp_out_v"]

    with pytest.raises(ValueError, match="missing required datasets.*comp_out_v"):
        read_measurement(path)


def test_failed_measurement_write_preserves_existing_file(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Publish HDF5 atomically so readers never observe a partial replacement."""

    path = write_measurement(tmp_path / "measurement.h5", adc_measurement())
    original = path.read_bytes()

    def fail_section(*args, **kwargs) -> None:
        raise RuntimeError("injected persistence failure")

    monkeypatch.setattr(analysis_io, "_write_section", fail_section)
    with pytest.raises(RuntimeError, match="injected persistence failure"):
        write_measurement(path, adc_measurement())

    assert path.read_bytes() == original
    assert not path.with_name(f".{path.name}.tmp").exists()


def test_adc_sections_reject_invalid_bits_shapes_and_wave_mapping() -> None:
    """Reject malformed ADC decisions and wave records before persistence."""

    measurement = adc_measurement()
    with pytest.raises(ValueError, match=r"shape \(N, 17\)"):
        AdcDaq(
            conversion_index=np.asarray([0], dtype=np.int64),
            bout=np.zeros((1, 16), dtype=np.uint8),
            dout_raw=np.asarray([0], dtype=np.int64),
            dout=np.asarray([0], dtype=np.int64),
            vin_diff_v=np.asarray([0.0], dtype=np.float64),
        )
    invalid_bits = np.zeros((1, 17), dtype=int)
    invalid_bits[0, 4] = 2
    with pytest.raises(ValueError, match="zero or one"):
        AdcDaq(
            conversion_index=np.asarray([0], dtype=np.int64),
            bout=invalid_bits,
            dout_raw=np.asarray([0], dtype=np.int64),
            dout=np.asarray([0], dtype=np.int64),
            vin_diff_v=np.asarray([0.0], dtype=np.float64),
        )
    with pytest.raises(ValueError, match="absent from DAQ"):
        MeasAdcExt(
            info=measurement.info,
            param=measurement.param,
            daq=measurement.daq,
            wave=AdcExtWave(
                conversion_index=np.asarray([99], dtype=np.int64),
                time_s=measurement.wave.time_s,
                vin_diff_v=measurement.wave.vin_diff_v,
                seq_comp_v=measurement.wave.seq_comp_v,
                seq_logic_v=measurement.wave.seq_logic_v,
                comp_out_v=measurement.wave.comp_out_v,
            ),
        )


def test_adaptive_simulation_waveforms_interpolate_to_dense_records() -> None:
    """Slice adaptive simulation output into dense equal-length wave records."""

    time_s = np.array([0.0, 0.4, 1.0, 1.6, 2.0])
    relative_time, records = interpolate_wave_records(
        time_s,
        {"signal_v": 2.0 * time_s},
        [(0.0, 1.0), (1.0, 2.0)],
        sample_interval_s=0.5,
    )

    np.testing.assert_allclose(relative_time, [0.0, 0.5])
    np.testing.assert_allclose(records["signal_v"], [[0.0, 1.0], [2.0, 3.0]])
