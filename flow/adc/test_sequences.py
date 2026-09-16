"""Shared sequence rows preserve simulator, serializer and saved-data timing."""

from dataclasses import fields

import h5py
import pytest

from flow.adc.sequences import BASELINE, DUTY_CYCLE_SEQUENCES, FIXED_INPUT_SEQUENCES, TIMING_SWEEP, AdcSequence
from flow.adc.sim import AdcTb, AdcTbParams
from flow.analysis.adc import _sequence_logic_timing
from flow.analysis.io import _read_native, _write_native
from flow.scans.seqgen import convert_params_to_seqgen_fmt


def test_rows_accept_whitespace_and_validate_lengths():
    row = "00001111 11110000\n01010101"
    sequence = AdcSequence(row, row, row, row)
    assert sequence.comp == "000011111111000001010101"
    assert len(sequence.comp) == 24
    for bad in ("", "0000000", "0000000x", "0000000000000000"):
        with pytest.raises(ValueError):
            AdcSequence("00000000", bad, "00000000", "00000000")


@pytest.mark.parametrize("name,sequence", FIXED_INPUT_SEQUENCES + DUTY_CYCLE_SEQUENCES)
@pytest.mark.parametrize("symbol_rate", (0.32e9, 0.96e9, 1.6e9))
def test_voltage_sources_and_serializer_consume_identical_rows(name, sequence, symbol_rate):
    params = AdcTbParams(
        view="hdl21gen",
        symbol_rate=symbol_rate,
        seq_init_pattern=sequence.init,
        seq_samp_pattern=sequence.samp,
        seq_comp_pattern=sequence.comp,
        seq_logic_pattern=sequence.logic,
    )
    tb = AdcTb(params)
    word_count = len(sequence.init) // 8
    memory = convert_params_to_seqgen_fmt(params, "0" * word_count)
    assert len(memory) == word_count * 8
    assert len(sequence.init) == (
        256 if name in {"original", "extended_comp"} or name.startswith("symbol256_") else 160
    )
    for lane, signal in enumerate(("init", "samp", "comp", "logic")):
        row = getattr(sequence, signal)
        source = getattr(tb, f"vseq_{signal}").of.params
        assert source.data == row
        assert float(source.period) == pytest.approx(1 / symbol_rate)
        assert float(source.delay) == 0
        assert source.rptstart == 1 and source.rpttimes == -1
        recovered = "".join(str((memory[word * 8 + lane] >> bit) & 1) for word in range(word_count) for bit in range(8))
        assert recovered == row
    assert not any("phase" in field.name for field in fields(params))


@pytest.mark.parametrize("symbols,sequence", enumerate(TIMING_SWEEP, start=1))
def test_library_logic_rows_have_explicit_edge_separations(symbols, sequence):
    assert sequence.init == BASELINE.init
    assert sequence.samp == BASELINE.samp
    assert sequence.comp == BASELINE.comp
    assert _sequence_logic_timing(sequence.comp, sequence.logic) == (8, symbols)


@pytest.mark.parametrize("shift", (-3, 0, 2, 3, 258))
def test_old_hdf5_phase_fields_are_folded_into_rows(tmp_path, shift):
    path = tmp_path / "parameters.h5"
    original = AdcTbParams()
    with h5py.File(path, "w") as output:
        _write_native(output, "param", original)
        for signal in ("init", "samp", "comp", "logic"):
            _write_native(output["param"], f"seq_{signal}_phase_delay_symbols", float(shift))
    with h5py.File(path) as source:
        loaded = _read_native(source["param"])
    for signal in ("init", "samp", "comp", "logic"):
        row = getattr(original, f"seq_{signal}_pattern")
        rotation = shift % len(row)
        expected = row[-rotation:] + row[:-rotation] if rotation else row
        assert getattr(loaded, f"seq_{signal}_pattern") == expected
    # Re-saving does not retain old fields or apply the delay twice.
    with h5py.File(path, "w") as output:
        _write_native(output, "param", loaded)
        assert not any("phase" in name for name in output["param"])
    with h5py.File(path) as source:
        assert _read_native(source["param"]) == loaded


def test_saved_fractional_delay_is_not_silently_rounded(tmp_path):
    with h5py.File(tmp_path / "parameters.h5", "w") as output:
        _write_native(output, "param", AdcTbParams())
        _write_native(output["param"], "seq_comp_phase_delay_symbols", 0.5)
        with pytest.raises(ValueError, match="fractional"):
            _read_native(output["param"])


@pytest.mark.parametrize("name,sequence", DUTY_CYCLE_SEQUENCES)
def test_duty_rows_preserve_conversion_boundaries_and_pulse_edges(name, sequence):
    import numpy as np

    comp_word, logic_word = name.split("_comp")[1].split("_logic")
    symbols = int(name.split("_")[0].removeprefix("symbol"))
    assert sequence.init == "1111" + "0" * (symbols - 4)
    assert sequence.samp == "0000" + "1" * 20 + "0" * (symbols - 24)
    assert sequence.comp == "0" * 24 + comp_word * 17 + "0" * (symbols - 160)
    start = next(i for i in range(8) if logic_word[i] == "1" and logic_word[i - 1] == "0")
    width = logic_word.count("1")
    bits = np.array([int(bit) for bit in sequence.logic])
    rises = np.flatnonzero((bits == 1) & (np.roll(bits, 1) == 0))
    falls = np.flatnonzero((bits == 0) & (np.roll(bits, 1) == 1))
    assert rises.tolist() == [3] + [24 + 8 * bit + start for bit in range(16)]
    assert falls.tolist() == [4] + [24 + 8 * bit + start + width for bit in range(16)]
    assert _sequence_logic_timing(sequence.comp, sequence.logic) == (8, start)


def test_duty_matrix_covers_every_pair_and_preserves_pause_only_changes():
    recipes = dict(DUTY_CYCLE_SEQUENCES)
    assert len(recipes) == len(DUTY_CYCLE_SEQUENCES) == 56
    assert set(recipes) == {
        f"symbol{symbols}_init4_samp20_comp{comp}_logic{logic}"
        for symbols in (160, 256)
        for comp in ("11110000", "11111000", "11111100", "11111110")
        for logic in ("00001111", "00000111", "00000011", "00000001", "10000111", "11000011", "11100001")
    }
    for name, short in DUTY_CYCLE_SEQUENCES[:28]:
        long = recipes[name.replace("symbol160_", "symbol256_")]
        for signal in ("init", "samp", "comp", "logic"):
            assert getattr(long, signal) == getattr(short, signal) + "0" * 96


@pytest.mark.parametrize("name,sequence", FIXED_INPUT_SEQUENCES + DUTY_CYCLE_SEQUENCES)
def test_conversion_duration_uses_comp_word_and_survives_phase_advance(name, sequence):
    expected = 168 if name == "extended_comp" else 160
    assert sequence.conversion_symbols == expected
    for shift in range(len(sequence.init)):
        advanced = sequence.advance(shift)
        assert advanced.conversion_symbols == expected
        assert advanced.relative_to_init() == sequence.relative_to_init()
        assert advanced.advance(-shift) == sequence
    params = AdcTbParams(**sequence.as_tb_fields())
    assert AdcSequence.from_tb_params(params) == sequence


def test_conversion_rate_ignores_logic_and_idle_padding():
    assert {sequence.conversion_symbols for sequence in TIMING_SWEEP} == {160}
    for _, sequence in DUTY_CYCLE_SEQUENCES:
        assert 1.6e9 / sequence.conversion_symbols == 10e6
        assert len(sequence.init) / 1.6e9 == pytest.approx(100e-9 if len(sequence.init) == 160 else 160e-9)
