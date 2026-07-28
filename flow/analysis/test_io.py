"""Software-only tests for typed acquisition data and source adapters."""

from types import SimpleNamespace

import numpy as np
import pytest

from flow.analysis.models import (
    AdcConversion,
    BackendKind,
    BlockKind,
    DataColumn,
    DataTable,
    SourceFormat,
    SourceSpec,
)
from flow.scans.params import AdcTbParams
from flow.analysis.io import (
    parameter_digest,
    read_adc_conversions,
    read_run,
)


def test_read_adc_conversions_returns_typed_rows(tmp_path) -> None:
    path = tmp_path / "adc.csv"
    path.write_text(
        "conversion_index,raw_word,identifier,frame,spi,bout,dout_raw,dout\n"
        "0,2703443303,10,3,74565,10101010101010101,1234,2345\n"
    )

    assert read_adc_conversions(path) == [
        AdcConversion(
            conversion_index=0,
            raw_word=0xA1234567,
            identifier=0xA,
            frame=3,
            spi=0x12345,
            bout="10101010101010101",
            dout_raw=1234,
            dout=2345,
        )
    ]


def test_parameter_digest_is_stable_and_sensitive() -> None:
    params = AdcTbParams()
    assert parameter_digest(params) == parameter_digest(params)
    assert parameter_digest(params) != parameter_digest(AdcTbParams(conversions=params.conversions + 1))


def test_data_tables_validate_alignment_and_column_lookup() -> None:
    table = DataTable(
        "waveforms",
        (
            DataColumn("time_s", np.asarray([0.0, 1.0]), "s"),
            DataColumn("signal_v", np.asarray([0.1, 0.2]), "V"),
        ),
    )
    np.testing.assert_allclose(table.column("signal_v"), (0.1, 0.2))
    assert table.unit("signal_v") == "V"
    with pytest.raises(ValueError, match="not aligned"):
        DataTable(
            "invalid",
            (
                DataColumn("a", np.asarray([1])),
                DataColumn("b", np.asarray([1, 2])),
            ),
        )


def test_current_and_historical_adc_csvs_normalize_to_same_columns(tmp_path) -> None:
    current = tmp_path / "current.csv"
    current.write_text("conversion_index,raw_word,identifier,frame,spi,bout,dout_raw,dout\n0,5,1,2,5,00101,3,4\n")
    historical = tmp_path / "historical.csv"
    historical.write_text(
        "conversion_index,raw_word0,id0,frame0,spi0,Bbits,Dout_raw,Dout,vdiff_v\n0,5,1,2,5,00101,3,4,0.1\n"
    )

    current_run = read_run(
        SourceSpec(
            "current",
            BackendKind.MEASUREMENT,
            BlockKind.ADC,
            SourceFormat.ADC_CSV,
            current,
            table_name="conversions",
        )
    )
    historical_run = read_run(
        SourceSpec(
            "historical",
            BackendKind.MEASUREMENT,
            BlockKind.ADC,
            SourceFormat.ADC_CSV,
            historical,
            table_name="conversions",
        )
    )

    for column in ("conversion_index", "raw_word", "identifier", "frame", "spi", "bout", "dout_raw", "dout"):
        np.testing.assert_array_equal(
            current_run.table("conversions").column(column),
            historical_run.table("conversions").column(column),
        )
    assert historical_run.table("conversions").column("bout")[0] == "00101"
    assert historical_run.table("conversions").unit("vdiff_v") == "V"


def test_column_mapping_adapter_normalizes_names_and_units() -> None:
    run = read_run(
        SourceSpec(
            "behavioral",
            BackendKind.BEHAVIORAL,
            BlockKind.COMPARATOR,
            SourceFormat.COLUMN_MAPPING,
            {
                "t": [0.0, 1e-9],
                "out": [0.0, 1.2],
            },
            table_name="waveforms",
            column_map={"time_s": "t", "output_v": "out"},
        )
    )
    assert run.table("waveforms").unit("time_s") == "s"
    assert run.table("waveforms").unit("output_v") == "V"


def test_physical_behavioral_and_spice_adapters_normalize_equivalent_data(
    tmp_path,
) -> None:
    expected_time = np.asarray([0.0, 1.0e-9, 2.0e-9])
    expected_output = np.asarray([0.1, 0.4, 0.9])

    csv_path = tmp_path / "measurement.csv"
    csv_path.write_text("scope_time,scope_output\n0,0.1\n1e-9,0.4\n2e-9,0.9\n")
    physical = read_run(
        SourceSpec(
            "physical",
            BackendKind.MEASUREMENT,
            BlockKind.COMPARATOR,
            SourceFormat.CSV,
            csv_path,
            table_name="waveforms",
            column_map={"time_s": "scope_time", "output_v": "scope_output"},
        )
    )
    behavioral = read_run(
        SourceSpec(
            "behavioral",
            BackendKind.BEHAVIORAL,
            BlockKind.COMPARATOR,
            SourceFormat.COLUMN_MAPPING,
            {"t": expected_time, "out": expected_output},
            table_name="waveforms",
            column_map={"time_s": "t", "output_v": "out"},
        )
    )
    sim_result = SimpleNamespace(an=(SimpleNamespace(data={"sim_time": expected_time, "sim_output": expected_output}),))
    spice = read_run(
        SourceSpec(
            "spice",
            BackendKind.SPICE,
            BlockKind.COMPARATOR,
            SourceFormat.SIM_RESULT,
            sim_result,
            table_name="waveforms",
            column_map={"time_s": "sim_time", "output_v": "sim_output"},
        )
    )

    for run in (physical, behavioral, spice):
        np.testing.assert_allclose(run.table("waveforms").column("time_s"), expected_time)
        np.testing.assert_allclose(run.table("waveforms").column("output_v"), expected_output)
        assert run.table("waveforms").unit("time_s") == "s"
        assert run.table("waveforms").unit("output_v") == "V"


def test_scope_and_spectre_adapters_preserve_provenance_and_parameters(tmp_path) -> None:
    scale = SimpleNamespace(offset=-1.0e-9, slope=1.0e-9)
    waveforms = {
        2: SimpleNamespace(
            x_scale=scale,
            data=np.asarray([0.0, 0.6, 1.2]),
            raw_data=np.asarray([0, 127, 255]),
        )
    }
    scope = read_run(
        SourceSpec(
            "scope",
            BackendKind.MEASUREMENT,
            BlockKind.GENERIC,
            SourceFormat.SCOPE_WAVEFORMS,
            (waveforms, {2: "comp"}),
            table_name="waveforms",
            parameters={"supply": AdcTbParams().vdd_a},
        )
    )
    np.testing.assert_allclose(
        scope.table("waveforms").column("time_s"),
        (-1.0e-9, 0.0, 1.0e-9),
    )
    np.testing.assert_allclose(
        scope.table("waveforms").column("comp_v"),
        (0.0, 0.6, 1.2),
    )
    supply_parameters = scope.parameters["supply"]
    assert isinstance(supply_parameters, dict)
    assert supply_parameters["type"] == "DcVoltageSourceParams"

    raw_path = tmp_path / "spectre.raw"
    raw_path.write_text(
        "Title: test\nVariables:\n0 time time\n1 out voltage\nValues:\n0 0.0 0.1\n1 1e-9 0.4\n2 2e-9 0.9\n"
    )
    spice = read_run(
        SourceSpec(
            "spectre",
            BackendKind.SPICE,
            BlockKind.COMPARATOR,
            SourceFormat.SPECTRE_NUTASCII,
            raw_path,
            table_name="waveforms",
            column_map={"time_s": "time", "output_v": "out"},
        )
    )
    assert spice.source_paths == (raw_path,)
    np.testing.assert_allclose(
        spice.table("waveforms").column("output_v"),
        (0.1, 0.4, 0.9),
    )


def test_numeric_columns_reject_nonfinite_values() -> None:
    with pytest.raises(ValueError, match="non-finite"):
        DataColumn("voltage_v", np.asarray([0.0, np.nan]), "V")
