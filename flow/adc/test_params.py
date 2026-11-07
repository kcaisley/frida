"""The ADC's parameters: FRIDA-1's four fabricated converters and where they are designs; a run's
sequencer lines, which play a recipe's rows (``Recipe``), and the run's own checks; the recipes'
rows, as reviewed."""

import hashlib
from dataclasses import replace

import numpy as np
import pytest

from flow import capdac, comp, samp
from flow.sweep.runner import digest, select

from .params import Extraction, Fabricated, Params, Quiet, Recipe, Simulator, TbParams, valid

# the recipes of the catalogue (the historical samp24 one, which it left out, last)
CATALOGUE = tuple(Recipe)[:-1]
TIMING = tuple(recipe for recipe in Recipe if recipe.name.startswith("SYMBOL256_INIT8_SAMP16_COMP11110000_"))
DUTY = tuple(
    recipe
    for recipe in CATALOGUE
    if recipe.name.startswith(("SYMBOL160_INIT4_SAMP20_", "SYMBOL256_INIT4_SAMP20_"))
    and recipe is not Recipe.SYMBOL160_INIT4_SAMP20_COMP11111100_LOGIC00000010
)


def _tb(params: Params | None = None, **fields) -> TbParams:
    return TbParams(pdk="tsmc65", params=Params() if params is None else params, **fields)


# FRIDA-1's fabricated converters


def test_each_fabricated_converter_is_one_design_of_its_own():
    designs = [member.params for member in Fabricated]
    assert len({digest(params) for params in [*designs, Params()]}) == 5
    for member, params in zip(Fabricated, designs, strict=True):
        assert params.fabricated is member
        assert (params.adc_bits, params.samp, params.comp) == (12, samp.FRIDA1, comp.FRIDA1)
        assert member.name.lower() == f"frida1_{member.layers}layer_radix{member.radix}"
    # radix 17 is capdac's own array, its weights capdac's; radix 20 is weighted
    assert (
        Fabricated.FRIDA1_1LAYER_RADIX17.params.cdac == Fabricated.FRIDA1_2LAYER_RADIX17.params.cdac == capdac.Params()
    )
    assert sum(capdac.Model.weights(Fabricated.FRIDA1_1LAYER_RADIX20.params.cdac)) == 2303
    assert sum(capdac.Model.weights(Fabricated.FRIDA1_1LAYER_RADIX17.params.cdac)) == 2047


@pytest.mark.parametrize(
    "parts",
    (
        {"cdac": capdac.Params(weights=Fabricated.FRIDA1_1LAYER_RADIX20.weights)},
        {"samp": replace(samp.FRIDA1, mos_w=64)},
        {"comp": replace(comp.FRIDA1, diffpair_w=comp.FRIDA1.diffpair_w + 1)},
        {"adc_bits": 10, "cdac": capdac.Params(bits=10, extra=3)},
    ),
)
def test_a_fabricated_converter_with_any_other_part_is_refused(parts):
    with pytest.raises(ValueError, match="FRIDA1_1LAYER_RADIX17"):
        Params(**{"fabricated": Fabricated.FRIDA1_1LAYER_RADIX17, **parts})


def test_a_fabricated_converter_is_a_design_in_its_tape_outs_process_alone():
    assert all(valid(member.params, "tsmc65") for member in Fabricated)
    assert not any(valid(member.params, pdk) for member in Fabricated for pdk in ("ihp130", "tsmc28"))
    assert valid(Params(), "ihp130")
    picked = select("adc", "tsmc65", ["frida1_2layer_radix20"])
    assert [(label, params) for label, params in picked.values()] == [
        ("frida1_2layer_radix20", Fabricated.FRIDA1_2LAYER_RADIX20.params)
    ]
    assert select("adc", "ihp130", ["frida1_2layer_radix20"]) == {}


# a run: what simulates it, its lines and its checks


def test_the_default_rows_are_the_default_recipe():
    tb = _tb()
    assert tb.rows == Recipe.SYMBOL256_INIT8_SAMP16_COMP11110000_LOGIC00001111.rows
    # written out exactly, with no whitespace to strip
    assert all(" " not in row for row in tb.rows)


def test_the_lines_play_their_rows_a_symbol_a_period_between_ground_and_the_digital_supply():
    tb = _tb(vdd_d=TbParams(pdk="tsmc65", params=Params()).vdd_d).sequenced(
        Recipe.SYMBOL160_INIT4_SAMP20_COMP11110000_LOGIC10000111.rows, symbol_rate=0.96e9
    )
    for line, row in zip((tb.seq_init, tb.seq_samp, tb.seq_comp, tb.seq_logic), tb.rows, strict=True):
        assert line.data == row and float(line.period) == 1 / 0.96e9
        assert (float(line.val0), float(line.val1), float(line.delay)) == (0.0, 1.2, 0.0)
        assert float(line.rise) == float(line.fall) == pytest.approx(1 / 0.96e9 / 20)
        assert (line.rptstart, line.rpttimes) == (1, -1)
    assert tb.sample_rate_hz == 0.96e9 / 160 and tb.stages == 16 and tb.decisions == 17


def test_the_run_knows_which_extraction_keeps_the_historical_disconnect():
    signoff = {
        member: TbParams(
            pdk="tsmc65", params=member.params, simulator=Simulator.SPECTRE, extraction=Extraction.SIGNOFF
        ).expected_disconnect
        for member in Fabricated
    }
    assert signoff == {member: member.layers == 2 for member in Fabricated}
    tapeout = TbParams(
        pdk="tsmc65",
        params=Fabricated.FRIDA1_2LAYER_RADIX17.params,
        simulator=Simulator.SPECTRE,
        extraction=Extraction.TAPEOUT,
    )
    assert not tapeout.expected_disconnect and not _tb().expected_disconnect


def test_the_behavioral_knobs_are_a_behavioral_runs():
    knobs = _tb(mismatch_seed=3, unit_mismatch=0.01, quiet=frozenset({Quiet.SAMPLING}), tau_scale=0.0)
    assert knobs.simulator is Simulator.BEHAVIORAL
    with pytest.raises(ValueError, match="behavioral run"):
        replace(knobs, simulator=Simulator.SPECTRE)
    with pytest.raises(ValueError, match="Quiet members"):
        _tb(quiet=frozenset({"sampling"}))


def test_continuous_rows_are_the_catalogues_recipe_at_sixteen_stages():
    assert _tb().continuous(16).rows == Recipe.SYMBOL160_INIT4_SAMP20_COMP11110000_LOGIC00001111.rows
    ten = _tb(params=Params(adc_bits=10, cdac=capdac.Params(bits=10, extra=3)), **_states(12)).continuous(12)
    assert len(ten.rows[0]) == 24 + 8 * 13 and ten.conversion_symbols == len(ten.rows[0])


def _states(stages: int) -> dict:
    return {name: (0,) * stages for name in ("dac_astate_p", "dac_bstate_p", "dac_astate_n", "dac_bstate_n")}


def test_rows_drop_whitespace_and_validate_lengths():
    row = "00001111 11110000\n01010101"
    tb = _tb().sequenced((row,) * 4)
    assert tb.seq_comp.data == "000011111111000001010101"
    for bad in ("", "0000000", "0000000x", "0000000000000000"):
        with pytest.raises(ValueError):
            _tb().sequenced(("00000000", bad, "00000000", "00000000"))


# the recipes' rows


@pytest.mark.parametrize("symbols,recipe", enumerate(TIMING, start=1))
def test_library_logic_rows_have_explicit_edge_separations(symbols, recipe):
    default = Recipe.SYMBOL256_INIT8_SAMP16_COMP11110000_LOGIC00001111.rows
    assert recipe.rows[:3] == default[:3]
    assert _tb().sequenced(recipe.rows).logic_timing == (8, symbols)


@pytest.mark.parametrize("recipe", DUTY, ids=lambda recipe: recipe.name.lower())
def test_duty_rows_preserve_conversion_boundaries_and_pulse_edges(recipe):
    name = recipe.name.lower()
    comp_word, logic_word = name.split("_comp")[1].split("_logic")
    symbols = int(name.split("_")[0].removeprefix("symbol"))
    init, samp_row, comp_row, logic = recipe.rows
    assert init == "1111" + "0" * (symbols - 4)
    assert samp_row == "0000" + "1" * 20 + "0" * (symbols - 24)
    assert comp_row == "0" * 24 + comp_word * 17 + "0" * (symbols - 160)
    start = next(i for i in range(8) if logic_word[i] == "1" and logic_word[i - 1] == "0")
    width = logic_word.count("1")
    bits = np.array([int(bit) for bit in logic])
    rises = np.flatnonzero((bits == 1) & (np.roll(bits, 1) == 0))
    falls = np.flatnonzero((bits == 0) & (np.roll(bits, 1) == 1))
    init_logic_rise, init_logic_fall = (2, 6) if symbols == 160 else (3, 4)
    assert rises.tolist() == [init_logic_rise] + [24 + 8 * bit + start for bit in range(16)]
    assert falls.tolist() == [init_logic_fall] + [24 + 8 * bit + start + width for bit in range(16)]
    assert _tb().sequenced(recipe.rows).logic_timing == (8, start)


def test_duty_matrix_covers_every_pair_and_preserves_pause_only_changes():
    recipes = {recipe.name.lower(): recipe.rows for recipe in DUTY}
    assert len(recipes) == len(DUTY) == 56
    assert set(recipes) == {
        f"symbol{symbols}_init4_samp20_comp{comp_word}_logic{logic}"
        for symbols in (160, 256)
        for comp_word in ("11110000", "11111000", "11111100", "11111110")
        for logic in ("00001111", "00000111", "00000011", "00000001", "10000111", "11000011", "11100001")
    }
    for recipe in DUTY[:28]:
        short = recipe.rows
        long = recipes[recipe.name.lower().replace("symbol160_", "symbol256_")]
        for index in range(3):
            assert long[index] == short[index] + "0" * 96
        assert short[3][:8] == "00111100"
        assert long[3] == "00010000" + short[3][8:] + "0" * 96


def test_all_160_symbol_init_logic_pulses_span_symbols_two_through_five():
    short = tuple(recipe for recipe in Recipe if recipe.name.startswith("SYMBOL160_INIT4_"))
    assert len(short) == 30
    for recipe in short:
        assert recipe.rows[0][:8] == "11110000"
        assert recipe.rows[3][:8] == "00111100"


@pytest.mark.parametrize("recipe", CATALOGUE, ids=lambda recipe: recipe.name.lower())
def test_conversion_duration_uses_comp_word_and_survives_phase_advance(recipe):
    expected = 168 if recipe is Recipe.SYMBOL256_INIT8_SAMP16_COMP11111100_LOGIC00000010 else 160
    tb = _tb().sequenced(recipe.rows)
    assert recipe.conversion_symbols == tb.conversion_symbols == expected
    for shift in range(len(recipe.rows[0])):
        advanced = tb.advance(shift)
        assert advanced.conversion_symbols == expected
        assert advanced.rows_from_init == tb.rows_from_init
        assert advanced.advance(-shift) == tb


def test_conversion_rate_ignores_logic_and_idle_padding():
    assert {recipe.conversion_symbols for recipe in TIMING} == {160}
    for recipe in DUTY:
        assert 1.6e9 / recipe.conversion_symbols == 10e6
        assert len(recipe.rows[0]) / 1.6e9 == pytest.approx(100e-9 if len(recipe.rows[0]) == 160 else 160e-9)


def test_the_recipes_preserve_all_reviewed_channel_rows():
    assert len(Recipe) == len({recipe.rows for recipe in Recipe}) == 66
    for recipe in Recipe:
        assert recipe.rows[0][0] == "1" and recipe.rows[0][-1] == "0"
    # Fingerprint of the catalogue's reviewed relative timings, normalized to INIT rising.
    rows = "\n".join(
        recipe.name.lower() + ":" + ":".join(TbParams.from_init(recipe.rows))
        for recipe in sorted(CATALOGUE, key=lambda recipe: recipe.name.lower())
    )
    assert (
        hashlib.sha256(rows.encode()).hexdigest() == "785b4bb014a0bbf5955edcef7dc7900e7fea4158c74d776a9eac6c7c687ba957"
    )


def test_continuous_catalogue_keeps_complete_terminal_comp_word():
    continuous = tuple(recipe for recipe in CATALOGUE if recipe.name.startswith("SYMBOL160_INIT4_SAMP20_"))
    assert len(continuous) == 29
    repaired = continuous[-1]
    assert repaired is Recipe.SYMBOL160_INIT4_SAMP20_COMP11111100_LOGIC00000010
    assert repaired.rows[1:3] == CATALOGUE[21].rows[1:3]
    logic = repaired.rows[3]
    assert [index for index, bit in enumerate(logic) if bit == "1" and logic[index - 1] == "0"] == [
        2,
        *(30 + 8 * index for index in range(16)),
    ]
    for recipe in continuous:
        comp_row = recipe.rows[2]
        last_rise = max(index for index, bit in enumerate(comp_row) if bit == "1" and comp_row[index - 1] == "0")
        assert last_rise == 152
        assert comp_row[-8:] in {"11110000", "11111000", "11111100", "11111110"}
