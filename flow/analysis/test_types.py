"""Tests for the typed measurement base classes and their uniform HDF5 persistence."""

from __future__ import annotations

from dataclasses import MISSING, dataclass, fields, replace
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path

import h5py
import hdl21 as h
import hdl21.sim as hs
import numpy as np
import pytest

import flow.analysis.io as analysis_io
from flow.adc.sim import AdcTbParams
from flow.analysis.io import interpolate_wave_records, read_measurement, write_measurement
from flow.analysis.types import (
    Analysis,
    AnalysisAdcTransfer,
    Identity,
    Meas,
    MeasAdc,
    MeasCdac,
    MeasComp,
    MeasInfo,
    MeasSamp,
    Wave,
    check_identity,
    measurement_identity,
)
from flow.comp.sim import CompTbParams
from flow.samp.sim import SampTbParams
from flow.scans.params import AdcScanParams


class PersistenceMode(Enum):
    """Small enum used to exercise native HDF5 enum persistence."""

    NOMINAL = "nominal"


@dataclass(frozen=True, slots=True, kw_only=True)
class MeasExample(Meas):
    """A measurement type that exists only in this test module."""

    trial_index: np.ndarray
    reading_v: np.ndarray


def info(backend="spice") -> MeasInfo:
    return MeasInfo(backend=backend, timestamp_utc=datetime(2026, 7, 29, 12, 0, tzinfo=UTC), readbacks={"note": "x"})


def wave(names: tuple[str, ...], currents: tuple[str, ...] = (), records: int = 1) -> Wave:
    traces = np.arange(records * 8, dtype=np.float64).reshape(records, 8)
    return Wave(
        record_index=np.arange(records),
        time_s=np.arange(8, dtype=np.float64) * 1e-9,
        v={name: traces + offset for offset, name in enumerate(names)},
        i={name: traces * 1e-6 for name in currents},
    )


def physical_scan_params() -> AdcScanParams:
    return AdcScanParams(
        tb=AdcTbParams(conversions=2),
        board_id=4,
        observed_adc=9,
        active_adc_mask=tuple(int(index == 9) for index in reversed(range(16))),
    )


def adc_physical() -> MeasAdc:
    params = physical_scan_params()
    return MeasAdc(
        group=params.board_id,
        index=params.observed_adc,
        dut=params.tb.dut,
        info=info("physical"),
        param=params,
        conversion_index=np.arange(2),
        bout=np.zeros((2, 17), dtype=np.uint8),
        dout_raw=np.asarray([10, 20]),
        dout=np.asarray([11, 21]),
        vin_diff_v=np.asarray([0.0, 1e-3]),
        fastrx_word=np.asarray([1, 2], dtype=np.uint32),
        wave=wave(("vin_diff", "seq_comp", "seq_logic", "comp_out")),
    )


def adc_spice() -> MeasAdc:
    params = AdcTbParams(conversions=1, mc_seed=11, mc_index=2)
    return MeasAdc(
        group=params.mc_seed,
        index=params.mc_index,
        dut=params.dut,
        info=info(),
        param=params,
        conversion_index=np.arange(1),
        bout=np.ones((1, 17), dtype=np.uint8),
        dout_raw=np.asarray([5]),
        dout=np.asarray([5]),
        vin_diff_v=np.asarray([0.0]),
        wave=wave(("vin_p", "vin_n", "dac_state_p[0]", "comp.latch_p"), ("vdd_a", "vdd_d")),
    )


def comp_physical() -> MeasComp:
    params = physical_scan_params()
    return MeasComp(
        group=params.board_id,
        index=params.observed_adc,
        dut=params.tb.dut.comp,
        info=info("physical"),
        param=params,
        trial_index=np.arange(2),
        vin_diff_v=np.asarray([0.0, 1e-3]),
        vin_cm_v=np.asarray([0.8, 0.8]),
        decision=np.asarray([0, 1], dtype=np.uint8),
        fastrx_word=np.asarray([1, 2], dtype=np.uint32),
        fastrx_frame=np.asarray([0, 1], dtype=np.uint32),
    )


def comp_spice() -> MeasComp:
    params = CompTbParams()
    return MeasComp(
        group=None,
        index=None,
        dut=params.comp,
        info=info(),
        param=params,
        trial_index=np.arange(1),
        vin_diff_v=np.asarray([0.0]),
        vin_cm_v=np.asarray([0.6]),
        decision=np.asarray([1], dtype=np.uint8),
        wave=wave(("inp", "inn", "clk", "latch_p", "latch_n"), ("vdd",)),
    )


def cdac_physical() -> MeasCdac:
    params = physical_scan_params()
    states = np.zeros((2, 16), dtype=np.uint8)
    return MeasCdac(
        group=params.board_id,
        index=params.observed_adc,
        dut=params.tb.dut.cdac,
        info=info("physical"),
        param=params,
        trial_index=np.arange(2),
        dac_state_p=states,
        dac_state_n=states,
        vin_diff_v=np.asarray([0.0, 1e-3]),
        decision=np.asarray([0, 1], dtype=np.uint8),
        dac_state_before_p=states,
        dac_state_before_n=states,
        vin_cm_v=np.asarray([0.8, 0.8]),
    )


def samp_spice() -> MeasSamp:
    params = SampTbParams()
    return MeasSamp(
        group=None,
        index=None,
        dut=params.samp,
        info=info(),
        param=params,
        trial_index=np.arange(1),
        wave=wave(("din", "dout", "clk", "clk_b"), ("vdd",)),
    )


def example() -> MeasExample:
    params = CompTbParams()
    return MeasExample(
        group=None,
        index=None,
        dut=params.comp,
        info=info(),
        param=params,
        trial_index=np.arange(3),
        reading_v=np.asarray([0.1, 0.2, 0.3]),
    )


MEASUREMENTS = (adc_physical, adc_spice, comp_physical, comp_spice, cdac_physical, samp_spice, example)


def assert_same_measurement(loaded: Meas, original: Meas) -> None:
    assert type(loaded) is type(original)
    assert loaded.identity == original.identity
    assert loaded.param == original.param
    assert replace(loaded.info, source_path=None) == original.info
    for data_field in fields(original):
        value = getattr(original, data_field.name)
        if isinstance(value, np.ndarray):
            stored = getattr(loaded, data_field.name)
            assert stored.dtype == value.dtype
            np.testing.assert_array_equal(stored, value)
    if original.wave is None:
        assert loaded.wave is None
    else:
        assert loaded.wave is not None
        np.testing.assert_array_equal(loaded.wave.time_s, original.wave.time_s)
        np.testing.assert_array_equal(loaded.wave.record_index, original.wave.record_index)
        for name in ("v", "i"):
            stored, expected = getattr(loaded.wave, name), getattr(original.wave, name)
            assert stored.keys() == expected.keys()
            for key in expected:
                np.testing.assert_array_equal(stored[key], expected[key])


@pytest.mark.parametrize("build", MEASUREMENTS, ids=lambda build: build.__name__)
def test_every_measurement_type_round_trips(tmp_path: Path, build) -> None:
    original = build()
    path = write_measurement(tmp_path / "measurement.h5", original)

    loaded = read_measurement(path)

    assert_same_measurement(loaded, original)
    assert loaded.info.source_path == path
    with h5py.File(path, "r") as stored:
        assert stored.attrs["_content"] == "measurement"
        assert stored["measurement"].attrs["_type"] == f"{type(original).__module__}:{type(original).__qualname__}"


def test_a_new_measurement_class_needs_no_registration(tmp_path: Path) -> None:
    """The reader rebuilds any importable Meas subclass from its stored type name."""

    loaded = read_measurement(write_measurement(tmp_path / "example.h5", example()))
    assert isinstance(loaded, MeasExample)


def test_every_measurement_carries_the_base_fields() -> None:
    base = [data_field.name for data_field in fields(Meas)]
    assert base == ["group", "index", "dut", "info", "param", "wave"]
    assert [data_field.name for data_field in fields(Meas) if data_field.default is not MISSING] == ["wave"]
    for build in MEASUREMENTS:
        assert [data_field.name for data_field in fields(type(build()))][: len(base)] == base


def test_measurement_readback_arrays_must_share_one_row_per_record() -> None:
    with pytest.raises(ValueError, match="readback arrays are not aligned"):
        replace(comp_physical(), decision=np.asarray([1], dtype=np.uint8))


def test_wave_rejects_misaligned_traces_and_a_nonincreasing_axis() -> None:
    valid = wave(("comp_out",), records=2)
    with pytest.raises(ValueError, match="must have shape"):
        replace(valid, v={"comp_out": valid.v["comp_out"][:1]})
    with pytest.raises(ValueError, match="strictly increasing"):
        replace(valid, time_s=valid.time_s[::-1])


def test_measurement_without_waveform_round_trips(tmp_path: Path) -> None:
    original = replace(adc_physical(), wave=None)
    assert_same_measurement(read_measurement(write_measurement(tmp_path / "plain.h5", original)), original)


def test_typed_pwl_and_linear_sweep_parameters_round_trip(tmp_path: Path) -> None:
    original = adc_physical()
    for source in (
        h.Vpwl.Params(wave=h.Pwl.ramp(start=-0.1, stop=0.1, duration=1e-6)),
        hs.LinearSweep(start=-0.75, stop=0.75, step=0.01),
    ):
        measurement = replace(original, param=replace(original.param, tb=replace(original.param.tb, vin_diff=source)))
        loaded = read_measurement(write_measurement(tmp_path / "source.h5", measurement))
        assert loaded.param == measurement.param
        assert type(loaded.param.tb.vin_diff) is type(source)


def test_native_enum_round_trip(tmp_path: Path) -> None:
    path = tmp_path / "enum.h5"
    with h5py.File(path, "w") as stored:
        analysis_io._write_native(stored, "mode", PersistenceMode.NOMINAL)
    with h5py.File(path, "r") as stored:
        assert analysis_io._read_native(stored["mode"]) is PersistenceMode.NOMINAL


def test_native_enum_reader_rejects_non_enum_type(tmp_path: Path) -> None:
    path = tmp_path / "invalid_enum.h5"
    with h5py.File(path, "w") as stored:
        dataset = stored.create_dataset("mode", data="NOMINAL")
        dataset.attrs["_kind"] = "enum"
        dataset.attrs["_type"] = "builtins:str"
    with h5py.File(path, "r") as stored, pytest.raises(TypeError, match="is not an Enum"):
        analysis_io._read_native(stored["mode"])


def test_parameter_reader_applies_defaults_added_after_capture(tmp_path: Path) -> None:
    """Keep files readable when parameter classes gain fields with defaults."""

    path = write_measurement(tmp_path / "older.h5", adc_physical())
    with h5py.File(path, "a") as stored:
        for cdac in (stored["measurement/param/tb/dut/cdac"], stored["measurement/dut/cdac"]):
            for name in ("driver_p_w", "driver_n_w", "driver_strengths"):
                del cdac[name]

    loaded = read_measurement(path)
    assert loaded.dut.cdac.driver_p_w == 9
    assert loaded.dut.cdac.driver_n_w == 7
    assert loaded.dut.cdac.driver_strengths is None


def test_reader_rejects_a_missing_required_field(tmp_path: Path) -> None:
    path = write_measurement(tmp_path / "incomplete.h5", adc_physical())
    with h5py.File(path, "a") as stored:
        del stored["measurement/bout"]

    with pytest.raises(ValueError, match="missing required parameter fields.*bout"):
        read_measurement(path)


def test_failed_measurement_write_preserves_existing_file(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Publish HDF5 atomically so readers never observe a partial replacement."""

    path = write_measurement(tmp_path / "measurement.h5", adc_physical())
    original = path.read_bytes()

    def fail(*args, **kwargs) -> None:
        raise RuntimeError("injected persistence failure")

    monkeypatch.setattr(analysis_io, "_write_native", fail)
    with pytest.raises(RuntimeError, match="injected persistence failure"):
        write_measurement(path, adc_physical())

    assert path.read_bytes() == original
    assert not path.with_name(f".{path.name}.tmp").exists()


def test_adaptive_simulation_waveforms_interpolate_to_dense_records() -> None:
    time_s = np.array([0.0, 0.4, 1.0, 1.6, 2.0])
    relative_time, records = interpolate_wave_records(
        time_s, {"signal": 2.0 * time_s}, [(0.0, 1.0), (1.0, 2.0)], sample_interval_s=0.5
    )

    np.testing.assert_allclose(relative_time, [0.0, 0.5])
    np.testing.assert_allclose(records["signal"], [[0.0, 1.0], [2.0, 3.0]])


def test_analysis_base_holds_only_identity_fields_without_defaults() -> None:
    assert [data_field.name for data_field in fields(Analysis)] == ["group", "index", "dut"]
    assert all(
        data_field.default is MISSING and data_field.default_factory is MISSING for data_field in fields(Analysis)
    )


def test_monte_carlo_parameters_default_to_nominal() -> None:
    assert (AdcTbParams().mc_seed, AdcTbParams().mc_index) == (None, None)
    assert (CompTbParams().mc_seed, CompTbParams().mc_index) == (None, None)


def test_identity_helpers_reject_mixed_inputs_and_mismatched_priors() -> None:
    nominal = adc_spice()
    other = replace(nominal, group=1, index=0)
    assert measurement_identity([nominal, nominal]) == Identity(11, 2, nominal.dut)
    with pytest.raises(ValueError, match="share one group, index, and DUT"):
        measurement_identity([nominal, other])
    result = AnalysisAdcTransfer(
        group=1,
        index=0,
        dut=nominal.dut,
        vin_diff_v=np.asarray([0.0]),
        mean_dout=np.asarray([0.0]),
        std_dout=np.asarray([0.0]),
        sample_count=np.asarray([1]),
    )
    check_identity(result, other.identity, name="prior")
    with pytest.raises(ValueError, match="group 1/11"):
        check_identity(result, nominal.identity, name="prior")
    with pytest.raises(ValueError, match="DUT params different"):
        check_identity(result, Identity(1, 0, replace(nominal.dut, adc_bits=10)), name="prior")
