"""Software-only tests for pure scan helpers; no hardware I/O is performed."""

from __future__ import annotations

from bitarray import bitarray
from types import SimpleNamespace

import numpy as np
import pytest

from flow.adc import AdcParams
from flow.cdac import CdacParams, RedunStrat
from flow.analysis.models import AdcConversion
from flow.scans import scan_adc
from flow.scans.loopback_fastrx import (
    SCOPE_DECISION_SAMPLE_FRACTION,
    extract_scope_decisions,
)
from flow.scans.params import AdcTbParams, load_board_map
from flow.scans.scan_spice import (
    bits_to_word,
    convert_raw_to_adc_conversions,
    nearest_value,
    require_signal,
    rising_edges,
)
from flow.scans.results import write_adc_conversions
from flow.scans.scope import write_scope_csv


def serializer_params(**overrides) -> AdcTbParams:
    """Return a compact four-word parameter set for sequencer packing."""
    config = {
        "dut": AdcParams(
            n_cycles=1,
            cdac=CdacParams(n_dac=1, n_extra=0, redun_strat=RedunStrat.RDX2, weights=(1,)),
        ),
        "seq_init_pattern": "10000001" + "01010101" + "00000000" * 2,
        "seq_samp_pattern": "11110000" + "00000000" * 3,
        "seq_comp_pattern": "00001111" + "11111111" + "00000000" * 2,
        "seq_logic_pattern": "10101010" + "01010101" + "00000000" * 2,
    }
    config.update(overrides)
    return AdcTbParams(**config)


def spi_params(**overrides) -> AdcTbParams:
    """Return physical parameters with independently recognizable SPI fields."""
    config = {
        "board_id": "frida65a_001",
        "observed_adc": 3,
        "active_adc_mask": tuple(int(index in (3, 9)) for index in reversed(range(16))),
        "dac_astate_p": tuple(int(bit) for bit in "1010101010101010"),
        "dac_bstate_p": tuple(int(bit) for bit in "0101010101010101"),
        "dac_astate_n": tuple(int(bit) for bit in "1111000011110000"),
        "dac_bstate_n": tuple(int(bit) for bit in "0000111100001111"),
        "en_init": 1,
        "en_samp_p": 0,
        "en_samp_n": 1,
        "en_comp": 1,
        "en_update": 0,
        "dac_mode": 0,
        "dac_diffcaps": 1,
    }
    config.update(overrides)
    return AdcTbParams(**config)


def unpack_spi_payload(payload: bytes) -> bitarray:
    """Undo wire-order reversal so tests can inspect logical SPI register positions."""
    transmitted = bitarray()
    transmitted.frombytes(payload)
    assert transmitted[180:].to01() == "0000"
    return transmitted[:180][::-1]


def test_write_scope_csv_persists_raw_aligned_acquisition(tmp_path) -> None:
    """Raw acquisition writer preserves time, voltage, and instrument codes."""

    x_scale = SimpleNamespace(offset=-1.0e-9, slope=0.5e-9, unit="s")
    waveforms = {
        1: SimpleNamespace(
            x_scale=x_scale,
            data=np.asarray([0.1, 0.2, 0.3]),
            raw_data=np.asarray([10, 20, 30]),
        ),
        3: SimpleNamespace(
            x_scale=x_scale,
            data=np.asarray([1.0, 0.0, 1.0]),
            raw_data=np.asarray([100, 0, 100]),
        ),
    }
    path = tmp_path / "scope" / "capture.csv"

    assert write_scope_csv(path, waveforms, {1: "input", 3: "logic"}) == path
    assert path.read_text().splitlines() == [
        "time_s,input_v,logic_v,input_raw,logic_raw",
        "-1e-09,0.1,1.0,10,100",
        "-5e-10,0.2,0.0,20,0",
        "0.0,0.3,1.0,30,100",
    ]


def test_write_adc_conversions_persists_and_appends_raw_rows(tmp_path) -> None:
    """Raw ADC writer preserves the shared acquisition schema."""

    first = AdcConversion(0, 0xA1234567, 0xA, 3, 0x12345, "101", 5, 6)
    second = AdcConversion(1, 0xA7654321, 0xA, 4, 0x14321, "010", 7, 8)
    path = tmp_path / "adc" / "conversions.csv"

    assert write_adc_conversions(path, (first,)) == 1
    assert write_adc_conversions(path, (second,), append=True) == 1
    assert path.read_text().splitlines() == [
        "conversion_index,raw_word,identifier,frame,spi,bout,dout_raw,dout",
        "0,2703443303,10,3,74565,101,5,6",
        "1,2808431393,10,4,82721,010,7,8",
    ]


def test_convert_params_to_seqgen_fmt_packs_serializer_lanes() -> None:
    """Verify critical 64-bit lane ordering, control placement, and zero padding."""
    memory = scan_adc.convert_params_to_seqgen_fmt(serializer_params(), rx_sen_start_word=1)

    assert list(memory) == [
        0x81,
        0x0F,
        0xF0,
        0x55,
        0x00,
        0x00,
        0x00,
        0x00,
        0xAA,
        0x00,
        0xFF,
        0xAA,
        0x01,
        0x00,
        0x00,
        0x00,
        0x00,
        0x00,
        0x00,
        0x00,
        0x01,
        0x00,
        0x00,
        0x00,
        0x00,
        0x00,
        0x00,
        0x00,
        0x00,
        0x00,
        0x00,
        0x00,
    ]


def test_convert_params_to_seqgen_fmt_rejects_invalid_capture_and_phase() -> None:
    with pytest.raises(ValueError, match="must leave a low word"):
        scan_adc.convert_params_to_seqgen_fmt(serializer_params(), rx_sen_start_word=2)

    with pytest.raises(ValueError, match="whole number"):
        scan_adc.convert_params_to_seqgen_fmt(
            serializer_params(seq_comp_phase_delay_symbols=0.5),
            rx_sen_start_word=1,
        )


def test_convert_vdiff_input_to_awg_supply_applies_empirical_calibration() -> None:
    """Check the software-only amplitude, center, and supply calibration."""
    negative_awg, supply_v = scan_adc.convert_vdiff_input_to_awg_supply(
        1.0,
        0.600,
    )
    positive_awg, negative_peak_supply_v = scan_adc.convert_vdiff_input_to_awg_supply(-1.0, 0.600)
    assert negative_awg == pytest.approx(-2.1858357372806774)
    assert positive_awg == pytest.approx(2.158798860988882)
    assert supply_v == pytest.approx(0.5848020214285712)
    assert negative_peak_supply_v == pytest.approx(supply_v)

    # The endpoint midpoint is the fitted AWG center, while their separation
    # supplies the requested sine amplitude. Both depend on |Vdiff| and Vin_cm.
    assert (negative_awg + positive_awg) / 2.0 == pytest.approx(-0.013518438145897704)
    assert positive_awg - negative_awg == pytest.approx(4.344634598269559)

    zero_awg, low_common_mode_supply_v = scan_adc.convert_vdiff_input_to_awg_supply(0.0, 0.400)
    assert zero_awg == pytest.approx(-0.03581525052269288)
    assert low_common_mode_supply_v == pytest.approx(0.38509593392857114)


def test_convert_dac_caps_to_adc_weights_adds_terminal_decision() -> None:
    assert scan_adc.convert_dac_caps_to_adc_weights([8, 4, 2, 1]) == [16, 8, 4, 2, 1]
    with pytest.raises(ValueError, match="positive integers"):
        scan_adc.convert_dac_caps_to_adc_weights([8, 0, 1])


def test_convert_params_to_spi_fmt_places_fields_and_reverses_for_transmission(capsys) -> None:
    """Verify the critical 180-bit field map, ADC selection, and wire-order reversal."""
    params = spi_params()
    payload = scan_adc.convert_params_to_spi_fmt(params)
    logical = unpack_spi_payload(payload)

    assert len(payload) == 23
    assert logical[48:64][::-1].to01() == "".join(str(bit) for bit in params.dac_astate_p)
    assert logical[32:48][::-1].to01() == "".join(str(bit) for bit in params.dac_bstate_p)
    assert logical[16:32][::-1].to01() == "".join(str(bit) for bit in params.dac_astate_n)
    assert logical[0:16][::-1].to01() == "".join(str(bit) for bit in params.dac_bstate_n)

    for adc in range(16):
        base = 64 + 7 * adc
        expected = "1011001" if adc in (3, 9) else "0000000"
        assert logical[base : base + 7].to01() == expected

    assert logical[176:180][::-1].to01() == "0011"
    assert "MUX_SEL spi_bits[179:176]" in capsys.readouterr().out


@pytest.mark.parametrize(
    ("override", "message"),
    [
        ({"dac_astate_p": (0,) * 15}, "exactly 16 bits"),
        ({"observed_adc": 16}, "observed_adc must be in 0..15"),
        ({"active_adc_mask": (0,) * 16}, "must include observed_adc"),
    ],
)
def test_convert_params_to_spi_fmt_rejects_invalid_fields(override: dict[str, object], message: str) -> None:
    """Reject malformed DAC, ADC, and mux fields before generating an SPI payload."""
    with pytest.raises(ValueError, match=message):
        scan_adc.convert_params_to_spi_fmt(spi_params(**override))


def test_convert_fastrx_to_bout_and_dout_uses_msb_first_samples_and_weights() -> None:
    """Verify FastRX temporal bit order, weighted recombination, and size validation."""
    assert scan_adc.convert_fastrx_to_bout_and_dout(
        0b101101,
        data_size=6,
        code_weights=[8, 4, 2, 1],
    ) == ("1011", 11)

    with pytest.raises(ValueError, match="smaller than 5 ADC code bits"):
        scan_adc.convert_fastrx_to_bout_and_dout(
            0b1011,
            data_size=4,
            code_weights=[16, 8, 4, 2, 1],
        )


def test_convert_dout_to_normalized_dout_scales_to_twelve_bits() -> None:
    """Pin down ADC normalization endpoints and Python rounding behavior."""
    assert scan_adc.convert_dout_to_normalized_dout(0, [1, 1], adc_bits=12) == 0
    assert scan_adc.convert_dout_to_normalized_dout(2, [1, 1], adc_bits=12) == 4095
    assert scan_adc.convert_dout_to_normalized_dout(1, [1, 1], adc_bits=12) == 2048


def test_calculate_fastrx_capture_alignment_uses_pattern_and_path_delays() -> None:
    """Software-only: reproduce validated word/tap points from the timing model."""

    timing = load_board_map()["boards"]["frida65a_001"]["capture_timing_model"]
    expected_points = {
        80.0e6: (6, 0),
        240.0e6: (7, 31),
        720.0e6: (8, 31),
        1.6e9: (9, 0),
    }
    for symbol_rate_bps, expected in expected_points.items():
        alignment = scan_adc.calculate_fastrx_capture_alignment(
            AdcTbParams(symbol_rate=symbol_rate_bps),
            **timing,
        )
        sequencer_period_s = 8.0 / symbol_rate_bps
        assert alignment.first_comp_transition_symbol == 36
        assert (
            alignment.rx_sen_start_word,
            alignment.comp_idelay_taps,
        ) == expected
        assert alignment.capture_edge_s >= alignment.data_arrival_s
        assert alignment.setup_margin_s >= timing["minimum_setup_s"]
        assert alignment.hold_margin_s >= 0.0
        assert alignment.setup_margin_s + alignment.hold_margin_s == pytest.approx(sequencer_period_s)


def test_extract_scope_decisions_samples_at_98_percent_of_each_cycle() -> None:
    """Decode late-settling COMP_OUT values immediately before the next decision."""

    symbol_rate_bps = 800.0e6
    decision_period_s = 8.0 / symbol_rate_bps
    times_s = np.arange(0.0, 36.0e-9, 0.01e-9)
    comp_v = np.where(
        np.mod(times_s, decision_period_s) < 0.5 * decision_period_s,
        1.2,
        0.0,
    )

    # Each output changes 95% of a cycle after its COMP falling edge. Sampling
    # at 90% would decode the old value; the validated 98% rule decodes 101.
    comp_out_v = np.zeros_like(times_s)
    comp_out_v[times_s >= 14.5e-9] = 1.2
    comp_out_v[times_s >= 24.5e-9] = 0.0
    comp_out_v[times_s >= 34.5e-9] = 1.2

    result = extract_scope_decisions(
        times_s,
        comp_v,
        comp_out_v,
        symbol_rate_bps=symbol_rate_bps,
        decision_count=3,
        output_inverted=False,
    )

    assert result.bits == "101"
    assert np.asarray(result.sample_times_s) - np.asarray(result.comp_edge_times_s) == pytest.approx(
        SCOPE_DECISION_SAMPLE_FRACTION * decision_period_s
    )
    inverted = extract_scope_decisions(
        times_s,
        comp_v,
        comp_out_v,
        symbol_rate_bps=symbol_rate_bps,
        decision_count=3,
        output_inverted=True,
    )
    assert inverted.bits == "010"


def test_parse_pwl_wave_accepts_spice_suffixes_and_rejects_time_reversal() -> None:
    points = scan_adc.parse_pwl_wave("0 -100m 500n 100m 1u -100m")
    assert [time_s for time_s, _ in points] == pytest.approx([0.0, 500e-9, 1e-6])
    assert [voltage_v for _, voltage_v in points] == pytest.approx([-0.1, 0.1, -0.1])
    with pytest.raises(ValueError, match="increase strictly"):
        scan_adc.parse_pwl_wave("1u 0 0 1")


def test_rising_edges_detects_strict_threshold_crossings() -> None:
    """Detect only low-to-high threshold crossings and reject mismatched traces."""
    times = [0.0, 1.0, 2.0, 3.0, 4.0, 5.0]
    values = [0.0, 0.5, 0.6, 1.0, 0.4, 0.9]

    assert rising_edges(times, values, threshold=0.5) == [2.0, 5.0]
    with pytest.raises(ValueError):
        rising_edges(times, values[:-1], threshold=0.5)


def test_nearest_value_handles_endpoints_nearest_samples_and_ties() -> None:
    """Verify endpoint clamping, nearest-sample lookup, and deterministic ties."""
    times = [0.0, 1.0, 2.0]
    values = [10.0, 20.0, 30.0]

    assert nearest_value(times, values, -1.0) == 10.0
    assert nearest_value(times, values, 3.0) == 30.0
    assert nearest_value(times, values, 1.6) == 30.0
    assert nearest_value(times, values, 1.5) == 20.0


def test_bits_to_word_packs_msb_first() -> None:
    """Verify deterministic MSB-first packing for empty, integer, and Boolean bits."""
    assert bits_to_word([]) == 0
    assert bits_to_word([1, 0, 1, 1]) == 0b1011
    assert bits_to_word([True, False, True]) == 0b101


def test_convert_raw_to_adc_conversions_writes_typed_and_plot_views() -> None:
    """Decode one synthetic Spectre conversion into the shared result schema."""

    expected_bout = "10110100101100101"
    times_s = np.arange(0.0, 350.0e-9, 1.0e-9)
    phase_s = np.mod(times_s, 20.0e-9)
    clock_v = np.where(phase_s >= 10.0e-9, 1.2, 0.0)
    comp_out_v = np.zeros_like(times_s)
    for decision_index, bit in enumerate(expected_bout):
        start_s = 10.0e-9 + decision_index * 20.0e-9
        stop_s = start_s + 20.0e-9
        comp_out_v[(times_s >= start_s) & (times_s < stop_s)] = 1.2 * int(bit)

    conversions, analysis_columns = convert_raw_to_adc_conversions(
        {
            "time": times_s.tolist(),
            "seq_comp": clock_v.tolist(),
            "comp_out": comp_out_v.tolist(),
            "vin_p": np.full_like(times_s, 0.650).tolist(),
            "vin_n": np.full_like(times_s, 0.600).tolist(),
        },
        threshold=0.6,
        sample_delay=10.0e-9,
        comp_signal="comp_out",
        clock_signal="seq_comp",
        vinp_signal="vin_p",
        vinn_signal="vin_n",
    )

    assert len(conversions) == 1
    assert conversions[0].bout == expected_bout
    assert conversions[0].spi == int(expected_bout, 2)
    assert conversions[0].dout_raw == conversions[0].dout
    assert analysis_columns["bout"][0] == expected_bout
    assert analysis_columns["dout"][0] == conversions[0].dout
    assert analysis_columns["vin_diff_v"][0] == pytest.approx(0.050)


def test_require_signal_resolves_exact_and_unique_suffix_matches() -> None:
    """Resolve exact signal names first and unique hierarchical suffixes second."""
    exact = [1.0]
    suffix = [2.0]
    data = {"time": exact, "top.i_adc.comp": suffix}

    assert require_signal(data, "time") is exact
    assert require_signal(data, "comp") is suffix


def test_require_signal_rejects_ambiguous_and_missing_names() -> None:
    """Report ambiguous suffix matches and missing signal names clearly."""
    data = {"a.comp": [1.0], "b.comp": [2.0]}

    with pytest.raises(KeyError, match="ambiguous"):
        require_signal(data, "comp")
    with pytest.raises(KeyError, match="not found"):
        require_signal(data, "clock")
