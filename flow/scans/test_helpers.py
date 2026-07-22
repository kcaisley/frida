"""Software-only tests for pure scan helpers; no hardware I/O is performed."""

from __future__ import annotations

from bitarray import bitarray
import pytest

from flow.scans import scan_adc
from flow.scans.plot import decision_path_from_bbits, filter_decision_path_rows, transfer_points
from flow.scans.scan_spice import bits_to_word, nearest_value, require_signal, rising_edges


def serializer_patterns() -> dict[str, str]:
    """Return a compact two-word pattern covering every serializer and control lane."""
    return {
        "INIT": "10000001 01010101",
        "SAMP": "11110000 00000000",
        "COMP": "00001111 11111111",
        "LOGIC": "10101010 01010101",
        "RX_SEN": "1 0",
        "RX_TEST": "0 1",
    }


def spi_config(**overrides) -> dict:
    """Return a complete SPI configuration with independently recognizable fields."""
    config = {
        "dac_astate_p": "1010101010101010",
        "dac_bstate_p": "0101010101010101",
        "dac_astate_n": "1111000011110000",
        "dac_bstate_n": "0000111100001111",
        "en_init": 1,
        "en_samp_p": 0,
        "en_samp_n": 1,
        "en_comp": 1,
        "en_update": 0,
        "dac_mode": 0,
        "dac_diffcaps": 1,
        "selected_adc_cfg": "1011010",
        "other_adc_cfg": "0100101",
        "config_adc": 3,
        "mux_sel": 9,
    }
    config.update(overrides)
    return config


def unpack_spi_payload(payload: bytes) -> bitarray:
    """Undo wire-order reversal so tests can inspect logical SPI register positions."""
    transmitted = bitarray()
    transmitted.frombytes(payload)
    assert transmitted[180:].to01() == "0000"
    return transmitted[:180][::-1]


def test_convert_dict_to_seqgen_fmt_packs_serializer_lanes() -> None:
    """Verify critical 64-bit lane ordering, control placement, and zero padding."""
    memory = scan_adc.convert_dict_to_seqgen_fmt(
        serializer_patterns(),
        serdes_ratio=8,
        seq_gen_lanes=8,
    )

    assert list(memory) == [
        0x81,
        0x0F,
        0xF0,
        0x55,
        0x01,
        0x00,
        0x00,
        0x00,
        0xAA,
        0x00,
        0xFF,
        0xAA,
        0x02,
        0x00,
        0x00,
        0x00,
    ]

    minimum_width_memory = scan_adc.convert_dict_to_seqgen_fmt(
        serializer_patterns(),
        serdes_ratio=8,
        seq_gen_lanes=5,
    )
    assert list(minimum_width_memory) == [
        0x81,
        0x0F,
        0xF0,
        0x55,
        0x01,
        0xAA,
        0x00,
        0xFF,
        0xAA,
        0x02,
    ]


def test_convert_dict_to_seqgen_fmt_rejects_invalid_patterns() -> None:
    """Reject mismatched lengths, invalid widths, and undersized sequencer words."""
    mismatched = serializer_patterns()
    mismatched["INIT"] = "10000001"
    with pytest.raises(ValueError, match="expected 1 words, got 2"):
        scan_adc.convert_dict_to_seqgen_fmt(
            mismatched,
            serdes_ratio=8,
            seq_gen_lanes=8,
        )

    invalid_width = serializer_patterns()
    invalid_width["LOGIC"] = "1010101 01010101"
    with pytest.raises(ValueError, match=r"expected 8 bit\(s\)"):
        scan_adc.convert_dict_to_seqgen_fmt(
            invalid_width,
            serdes_ratio=8,
            seq_gen_lanes=8,
        )

    with pytest.raises(ValueError, match="needs at least five"):
        scan_adc.convert_dict_to_seqgen_fmt(
            serializer_patterns(),
            serdes_ratio=8,
            seq_gen_lanes=4,
        )

    invalid_control = serializer_patterns()
    invalid_control["RX_SEN"] = "10 0"
    with pytest.raises(ValueError, match=r"expected 1 bit\(s\)"):
        scan_adc.convert_dict_to_seqgen_fmt(
            invalid_control,
            serdes_ratio=8,
            seq_gen_lanes=8,
        )

    missing_track = serializer_patterns()
    del missing_track["COMP"]
    with pytest.raises(ValueError, match=r"missing=\['COMP'\]"):
        scan_adc.convert_dict_to_seqgen_fmt(
            missing_track,
            serdes_ratio=8,
            seq_gen_lanes=8,
        )

    unexpected_track = serializer_patterns()
    unexpected_track["SPARE"] = "0 0"
    with pytest.raises(ValueError, match=r"unexpected=\['SPARE'\]"):
        scan_adc.convert_dict_to_seqgen_fmt(
            unexpected_track,
            serdes_ratio=8,
            seq_gen_lanes=8,
        )

    empty_patterns = {name: "" for name in serializer_patterns()}
    with pytest.raises(ValueError, match="must not be empty"):
        scan_adc.convert_dict_to_seqgen_fmt(
            empty_patterns,
            serdes_ratio=8,
            seq_gen_lanes=8,
        )

    with pytest.raises(ValueError, match="serdes_ratio must be an integer in 1..8"):
        scan_adc.convert_dict_to_seqgen_fmt(
            serializer_patterns(),
            serdes_ratio=9,
            seq_gen_lanes=8,
        )


def test_default_input_mode_is_manual() -> None:
    assert scan_adc.INPUT_MODE == "manual"


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


def test_convert_sample_rate_to_baud_maps_nominal_adc_rates() -> None:
    """Map 1--10 MSPS active conversions onto 160--1600 MBd."""
    assert tuple(scan_adc.convert_sample_rate_to_baud(rate) for rate in scan_adc.NOMINAL_ADC_SAMPLE_RATES_HZ) == tuple(
        rate_mbd * 1e6 for rate_mbd in range(160, 1601, 160)
    )
    with pytest.raises(ValueError, match="must be positive"):
        scan_adc.convert_sample_rate_to_baud(0)


def test_add_fastrx_capture_window_captures_exactly_17_bits() -> None:
    for rate_hz in scan_adc.NOMINAL_ADC_SAMPLE_RATES_HZ:
        start_word = scan_adc.RX_SEN_START_WORD_BY_RATE_HZ[round(rate_hz)]
        words = scan_adc.add_fastrx_capture_window(start_word)["RX_SEN"].split()
        assert len(words) == scan_adc.SEQUENCE_STEPS
        assert words.count("1") == scan_adc.NUM_CAPTURE_BITS
        assert words[start_word : start_word + scan_adc.NUM_CAPTURE_BITS] == ["1"] * scan_adc.NUM_CAPTURE_BITS
        assert words[-1] == "0"
        patterns = scan_adc.add_fastrx_capture_window(start_word)
        assert all(
            patterns[name] == original_pattern
            for name, original_pattern in scan_adc.SEQ_PATTERNS.items()
            if name != "RX_SEN"
        )

    for invalid_start in (-1, 15):
        with pytest.raises(ValueError, match="must leave a low word"):
            scan_adc.add_fastrx_capture_window(invalid_start)


def test_spi_config_to_bytes_places_fields_and_reverses_for_transmission(capsys) -> None:
    """Verify the critical 180-bit field map, ADC selection, and wire-order reversal."""
    config = spi_config()
    payload = scan_adc.spi_config_to_bytes(config)
    logical = unpack_spi_payload(payload)

    assert len(payload) == 23
    assert logical[48:64][::-1].to01() == config["dac_astate_p"]
    assert logical[32:48][::-1].to01() == config["dac_bstate_p"]
    assert logical[16:32][::-1].to01() == config["dac_astate_n"]
    assert logical[0:16][::-1].to01() == config["dac_bstate_n"]

    for adc in range(16):
        base = 64 + 7 * adc
        expected = config["selected_adc_cfg"] if adc == config["config_adc"] else config["other_adc_cfg"]
        assert logical[base : base + 7].to01() == expected

    assert logical[176:180][::-1].to01() == f"{config['mux_sel']:04b}"
    assert "MUX_SEL spi_bits[179:176]" in capsys.readouterr().out


@pytest.mark.parametrize(
    ("override", "message"),
    [
        ({"dac_astate_p": "0" * 15}, "dac_astate_p must be 16 bits"),
        ({"selected_adc_cfg": "0" * 6}, "selected_adc_cfg must be 7 bits"),
        ({"other_adc_cfg": "0" * 8}, "other_adc_cfg must be 7 bits"),
        ({"config_adc": 16}, "config_adc must be in 0..15"),
        ({"mux_sel": -1}, "mux_sel must be in 0..15"),
        ({"mux_bits": "0" * 3}, "mux_bits must be 4 bits"),
    ],
)
def test_spi_config_to_bytes_rejects_invalid_fields(override: dict, message: str) -> None:
    """Reject malformed DAC, ADC, and mux fields before generating an SPI payload."""
    with pytest.raises(ValueError, match=message):
        scan_adc.spi_config_to_bytes(spi_config(**override))


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
    assert scan_adc.convert_dout_to_normalized_dout(0, [1, 1]) == 0
    assert scan_adc.convert_dout_to_normalized_dout(2, [1, 1]) == 4095
    assert scan_adc.convert_dout_to_normalized_dout(1, [1, 1]) == 2048


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


def test_decision_path_from_bbits_tracks_decided_and_undecided_weights() -> None:
    """Convert ADC decisions and weights into a validated running code estimate."""
    assert decision_path_from_bbits("101", [8, 4, 2], initial_estimate=10.0) == [10.0, 11.0, 9.0, 10.0]

    with pytest.raises(ValueError, match="3 bits, expected 2"):
        decision_path_from_bbits("101", [2, 1])


def test_transfer_points_groups_averages_and_sorts_rows() -> None:
    """Group repeated conversions and return sorted mean transfer points in millivolts."""
    rows = [
        {"vdiff_v": "0.2", "Dout": "10"},
        {"vdiff_v": "-0.1", "Dout": "1"},
        {"vdiff_v": "-0.1", "Dout": "3"},
    ]

    assert transfer_points(rows) == ([-100.0, 200.0], [2.0, 10.0])


def test_filter_decision_path_rows_supports_all_modes() -> None:
    """Verify deterministic row selection and labels for every supported filter mode."""
    rows = [
        {"Dout": "10", "conversion_index": 0},
        {"Dout": "11", "conversion_index": 1},
        {"Dout": "10", "conversion_index": 2},
    ]

    selected, label = filter_decision_path_rows(rows, "single", row_index=1)
    assert selected == [rows[1]]
    assert label == "single_row0001_dout11"

    selected, label = filter_decision_path_rows(rows, "same_dout")
    assert selected == [rows[0], rows[2]]
    assert label == "same_dout10"

    selected, label = filter_decision_path_rows(rows, "same_dout", dout=11)
    assert selected == [rows[1]]
    assert label == "same_dout11"

    selected, label = filter_decision_path_rows(rows, "all")
    assert selected is rows
    assert label == "all"


def test_filter_decision_path_rows_handles_empty_and_invalid_modes() -> None:
    """Handle empty selections and reject unknown decision-path filter modes."""
    assert filter_decision_path_rows([], "single") == ([], "single_empty")
    assert filter_decision_path_rows([], "same_dout") == ([], "same_dout_empty")
    with pytest.raises(ValueError, match="unknown decision-path filter mode"):
        filter_decision_path_rows([], "invalid")
