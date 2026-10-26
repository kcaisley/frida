"""The ADC arrays' sizing on a synthetic row model: Harpe's full scale, the two constraints, the
split, and the calibration from an extraction (PDK-free)."""

import json
import math
from dataclasses import replace
from pathlib import Path

import pytest

from . import sizing
from .layout import ADC_ARRAYS
from .subckt import CapArrayConfig, RedunStrat, _calc_weight_partitions, get_caparray_weights

REFERENCE = 1.2
IDEAL = sizing.RowModel(
    slope_ff_um=0.5,
    intercept_ff=0.0,
    tail_ff=0.0,
    tail_um=0.5,
    ends_um=0.5,
    grid_nm=5,
    pitch_um=0.4,
    outer_width_um=0.5,
    side_um=2.0,
    bar_um=0.3,
)
# a model with tails, ends and other load, as an extraction corrects it
MODEL = replace(
    IDEAL,
    intercept_ff=0.12,
    tail_ff=0.4,
    scale=0.97,
    binary_offset_ff=0.01,
    unary_ff=0.05,
    other_row_ff=0.1,
    other_row_um_ff=0.02,
)
BINARY_10 = ADC_ARRAYS["10b_binary_x1"]


def test_rows_are_unary_chunks_and_binary_remainders() -> None:
    # 10 bits on 9 steps, split at 16: N_b = 4 binary rows (8, 4, 2, 1) and 2^5 - 1 unary rows
    assert sizing.rows(BINARY_10, 16) == (31, 4, 15)
    assert sizing.rows(BINARY_10, 64) == (7, 6, 63)


@pytest.mark.parametrize("coarse", [8, 16, 32, 64])
def test_ideal_rows_give_harpes_full_scale(coarse: int) -> None:
    # no tails, ends or other load: FS = (2^N - 1) / ((N_b + 2^N_u - 1) 2^N_b) (Harpe, JSSC 2018)
    n, binary = BINARY_10.n_dac, int(math.log2(coarse))
    harpe = (2**n - 1) / ((binary + 2 ** (n - binary) - 1) * 2**binary)
    assert sizing.predict(BINARY_10, coarse, 50e-15, IDEAL, REFERENCE).full_scale == pytest.approx(harpe)


def test_the_least_capacitance_meets_each_constraint_where_it_binds() -> None:
    bits = BINARY_10.n_dac + 1
    for coarse in (8, 16):
        needs = sizing.least_switched_f(BINARY_10, coarse, MODEL, REFERENCE)
        at_full_scale = sizing.predict(BINARY_10, coarse, needs["full_scale"], MODEL, REFERENCE)
        at_noise = sizing.predict(BINARY_10, coarse, needs["noise"], MODEL, REFERENCE)
        assert at_full_scale.full_scale == pytest.approx(sizing.MIN_FULL_SCALE + sizing.MARGIN, rel=1e-6)
        assert at_noise.noise_ratio(bits) == pytest.approx(1 - sizing.MARGIN, rel=1e-6)
    # binary rows beyond a fifth of the weight never reach 80 %: 10 bits split at 32 or more
    assert sizing.least_switched_f(BINARY_10, 32, MODEL, REFERENCE)["full_scale"] == math.inf


def test_the_splits_span_eight_to_512_with_every_power_of_two() -> None:
    assert sizing.COARSE_WEIGHTS[0] == 8 and sizing.COARSE_WEIGHTS[-1] == 512
    assert {8, 16, 32, 64, 128, 256, 512} <= set(sizing.COARSE_WEIGHTS)
    assert all(b / a < 1.2 for a, b in zip(sizing.COARSE_WEIGHTS, sizing.COARSE_WEIGHTS[1:], strict=False))


def test_the_outline_is_the_rows_beside_each_other_and_a_row_tall() -> None:
    drawn = sizing.predict(BINARY_10, 16, 0.0, MODEL, REFERENCE, step_nm=300)
    assert drawn.rows == 35
    assert drawn.width_um == pytest.approx((35 + 1) * 0.4 + 0.5 + 2.0)  # two edge dummies
    assert drawn.height_um == pytest.approx(drawn.row_um + 0.3)
    assert drawn.aspect == pytest.approx(drawn.height_um / drawn.width_um)


def test_the_split_is_the_one_nearest_the_outline_that_keeps_both_constraints() -> None:
    names = ("12b_binary_x2", "12b_lsb_split6_x2", "14b_binary_x1", "14b_lsb_split6_x1", "14b_binary_x2")
    arrays = {name: ADC_ARRAYS[name] for name in names}
    models = dict.fromkeys(arrays, MODEL)
    minimums = sizing.resolution_minimums(arrays, models, REFERENCE)
    for cdac in arrays.values():
        bits = cdac.n_dac + 1
        least = minimums[bits]["switched_f"]
        choice, drawn = sizing.design(cdac, least, MODEL, REFERENCE)
        assert drawn.full_scale >= sizing.MIN_FULL_SCALE and drawn.noise_ratio(bits) * cdac.cap_scale <= 1
        assert drawn.switched_f == pytest.approx(cdac.cap_scale * least, rel=0.03)
        assert choice.coarse_weight in sizing.splits(cdac)
        for coarse in sizing.splits(cdac):  # no split that keeps both is nearer the outline
            other = sizing.predict(cdac, coarse, cdac.cap_scale * least, MODEL, REFERENCE)
            if (
                other.full_scale >= sizing.MIN_FULL_SCALE + sizing.MARGIN
                and other.noise_ratio(bits) * cdac.cap_scale <= 0.99
            ):
                assert abs(math.log(other.aspect / 2)) >= abs(math.log(drawn.aspect / 2)) - 0.05
        if sizing.exact_unary(cdac):
            assert choice.unary_length == 0  # two fingers: no length of its own
        else:
            # the unary finger is the coarse weight in units: scale * slope * L + unary_ff
            unit = MODEL.unit_ff(choice.weight_step)
            unary = MODEL.scale * MODEL.slope_ff_um * choice.unary_length / 1000 + MODEL.unary_ff
            assert unary == pytest.approx(choice.coarse_weight * unit, abs=MODEL.scale * MODEL.slope_ff_um * 0.005)
    # twice the capacitance: longer rows for the same split
    one = sizing.design(arrays["14b_binary_x1"], minimums[14]["switched_f"], MODEL, REFERENCE)[1]
    two = sizing.design(arrays["14b_binary_x2"], minimums[14]["switched_f"], MODEL, REFERENCE)[1]
    assert two.row_um > one.row_um


def test_no_design_draws_a_row_shorter_than_the_cell_does() -> None:
    # a cell whose shortest finger is longer than the free design's rows: the rows reach it
    least = sizing.array_minimum(BINARY_10, MODEL, REFERENCE)["switched_f"]
    free = sizing.design(BINARY_10, least, MODEL, REFERENCE)
    assert free is not None
    choice, _ = free
    shortest = MODEL.tail_um + choice.coarse_weight * choice.weight_step / 1000 + 1.0
    model = replace(MODEL, nominal_min_um=shortest)
    for coarse in (8, 16):
        needs = sizing.least_switched_f(BINARY_10, coarse, model, REFERENCE)
        at_row = sizing.predict(BINARY_10, coarse, needs["row"], model, REFERENCE)
        assert model.tail_um + coarse * at_row.step_nm / 1000 == pytest.approx(shortest, rel=1e-6)
    bound = sizing.design(BINARY_10, sizing.array_minimum(BINARY_10, model, REFERENCE)["switched_f"], model, REFERENCE)
    assert bound is not None
    choice, _ = bound
    assert model.tail_um + choice.coarse_weight * choice.weight_step / 1000 >= shortest


def test_from_14_bits_the_splits_are_powers_of_two_and_the_unary_rows_exact() -> None:
    assert sizing.EXACT_UNARY_BITS == 14
    assert sizing.splits(ADC_ARRAYS["14b_binary_x1"]) == (8, 16, 32, 64, 128, 256, 512)
    assert sizing.splits(ADC_ARRAYS["12b_binary_x1"]) == sizing.COARSE_WEIGHTS
    # an exact unary row loads the top plate with its two tails besides its weight
    cdac = ADC_ARRAYS["14b_binary_x1"]
    unary, binary, _weight = sizing.rows(cdac, 64)
    exact = sizing.predict(cdac, 64, 0.0, MODEL, REFERENCE, step_nm=600)
    one_finger = sizing.predict(replace(cdac, n_dac=12), 64, 0.0, MODEL, REFERENCE, step_nm=600)  # 13 bits
    assert unary == 127 and binary == 6
    unit, row_um = MODEL.unit_ff(600), MODEL.row_um(64, 600)
    other = (133 + 2) * (MODEL.other_row_ff + MODEL.other_row_um_ff * row_um)
    assert exact.total_f * 1e15 == pytest.approx(133 * 64 * unit + 133 * 2 * MODEL.tail_ff + other)
    assert sizing.exact_unary(cdac) and not sizing.exact_unary(replace(cdac, n_dac=12))
    assert one_finger.rows == 63 + 6  # a 13-bit array: fewer rows of the same split


def _extraction(tmp_path: Path, cdac: CapArrayConfig, model: sizing.RowModel, choice: sizing.Design) -> Path:
    """The manifest and capacitance table an extraction of ``cdac`` at ``choice`` would write, were
    the array ``model``."""
    coarse, step = choice.coarse_weight, choice.weight_step
    unit = model.unit_ff(step)
    scale, unary_offset = model.unary_fit(coarse)
    unary_ff = scale * model.slope_ff_um * choice.unary_length / 1000 + unary_offset
    partitions = _calc_weight_partitions(get_caparray_weights(cdac), coarse)
    main, diff = [], []
    for stage in partitions:
        unary = sum(chunk == coarse for chunk in stage)
        binary = [chunk for chunk in stage if chunk != coarse]
        fingers = len(binary) * (coarse * unit + 2 * model.tail_ff)
        effective = sum(binary) * unit + len(binary) * model.binary_offset_ff
        main.append(unary * unary_ff + (fingers + effective) / 2)
        diff.append((fingers - effective) / 2)
    count = sum(len(stage) for stage in partitions)
    row_um = model.row_um(coarse, step)
    other = (count + 2) * (model.other_row_ff + model.other_row_um_ff * row_um)
    work = tmp_path / f"split{coarse}_step{step}"
    work.mkdir()
    (work / "geometry_manifest.json").write_text(
        json.dumps(
            {
                "unit_family": {
                    "coarse_weight": coarse,
                    "weight_step": step,
                    "unary_length": choice.unary_length,
                    "tied_dummies": True,
                },
                "derived_geometry_nm": {"weight_step": step, "outer_height": round(row_um * 1000)},
                "weights_by_stage": get_caparray_weights(cdac),
                "partitioned_weights_by_stage": partitions,
                "physical_chunk_count": count,
                "placed_unit_count": count + 2,
            }
        )
    )
    (work / "capacitance_table.json").write_text(
        json.dumps(
            {
                "main_by_stage_ff": main,
                "diff_by_stage_ff": diff,
                "main_ff": sum(main),
                "diff_ff": sum(diff),
                "effective_ff": sum(main) - sum(diff),
                "topplate_shield_ff": other,
                "topplate_ground_ff": 0.0,
            }
        )
    )
    return work


def test_an_extraction_corrects_the_model_and_its_measurement_meets_the_prediction(tmp_path: Path) -> None:
    cdac = CapArrayConfig(n_dac=9, n_extra=4, redun_strat=RedunStrat.MSB_REDIST)
    true = MODEL
    first = sizing.Design(16, 200, true.unary_length_nm(16, 200))
    second = sizing.Design(16, 320, true.unary_length_nm(16, 320))
    works = [_extraction(tmp_path, cdac, true, choice) for choice in (first, second)]
    # the other load's shape over both (as over every array's), each extraction scaling it
    shape = sizing.other_load_shape(works)
    assert shape == pytest.approx((true.other_row_ff, true.other_row_um_ff), rel=1e-3)
    learned = sizing.calibrated(IDEAL, works[-1], shape)
    for field in ("scale", "binary_offset_ff", "tail_ff", "unary_ff", "other_row_ff", "other_row_um_ff"):
        assert getattr(learned, field) == pytest.approx(getattr(true, field), rel=1e-3, abs=1e-6), field
    measured = sizing.measured(works[-1], cdac, REFERENCE)
    predicted = sizing.predict(cdac, 16, 0.0, learned, REFERENCE, step_nm=320)
    assert measured["full_scale"] == pytest.approx(predicted.full_scale, rel=1e-3)
    assert measured["noise_over_quantization"] == pytest.approx(predicted.noise_ratio(10), rel=1e-3)
    assert abs(measured["unary_error_lsb"]) < sizing.UNARY_TOLERANCE
    # the array's own extractions at the same split, rows of different lengths: its own fit
    own = sizing.calibrated(IDEAL, works[-1], None, works[:-1])
    assert (own.other_row_ff, own.other_row_um_ff) == pytest.approx((true.other_row_ff, true.other_row_um_ff), rel=1e-3)
    # no shape: the extraction's other load split evenly between the rows and their length
    single = sizing.calibrated(IDEAL, works[0])
    rows = sum(len(stage) for stage in _calc_weight_partitions(get_caparray_weights(cdac), 16)) + 2
    row_um = true.row_um(16, 200)
    assert rows * (single.other_row_ff + single.other_row_um_ff * row_um) == pytest.approx(
        rows * (true.other_row_ff + true.other_row_um_ff * row_um), rel=1e-3
    )
    assert single.other_row_ff == pytest.approx(single.other_row_um_ff * row_um, rel=1e-3)


def test_each_split_draws_its_unary_rows_by_its_own_extraction(tmp_path: Path) -> None:
    """Another split's scale and unary finger (a fraction of a percent apart) miss a unary row by a
    tenth of a unit or more: each split keeps its own."""
    cdac = CapArrayConfig(n_dac=9, n_extra=4, redun_strat=RedunStrat.MSB_REDIST)
    at16 = MODEL
    at8 = replace(MODEL, scale=0.99, unary_ff=0.15)
    eight = _extraction(tmp_path, cdac, at8, sizing.Design(8, 200, at8.unary_length_nm(8, 200)))
    sixteen = _extraction(tmp_path, cdac, at16, sizing.Design(16, 200, at16.unary_length_nm(16, 200)))
    learned = sizing.calibrated(IDEAL, sixteen, None, [eight])
    assert learned.unary_fit(16) == pytest.approx((at16.scale, at16.unary_ff), rel=1e-3)
    assert learned.unary_fit(8) == pytest.approx((at8.scale, at8.unary_ff), rel=1e-3)
    assert learned.unary_length_nm(8, 240) == at8.unary_length_nm(8, 240)
    assert abs(at8.unary_error_lsb(8, 240, learned.unary_length_nm(8, 240))) < 0.05
    # the newest model's alone would miss it
    alone = sizing.calibrated(IDEAL, sixteen)
    assert abs(at8.unary_error_lsb(8, 240, alone.unary_length_nm(8, 240))) > 0.1


def test_an_extraction_holds_where_the_next_design_barely_moves() -> None:
    cdac = BINARY_10
    met = {"full_scale": 0.85, "noise_over_quantization": 0.2, "unary_error_lsb": 0.1}
    drawn = [(sizing.Design(16, 200, 6000), Path("a"), met)]
    assert sizing._holding(drawn, sizing.Design(16, 204, 6100), cdac) == drawn[0]
    assert sizing._holding(drawn, sizing.Design(16, 220, 6600), cdac) is None
    assert sizing._holding(drawn, sizing.Design(8, 200, 3000), cdac) is None
    failed = [(sizing.Design(16, 200, 6000), Path("a"), {**met, "full_scale": 0.79})]
    assert sizing._holding(failed, sizing.Design(16, 200, 6000), cdac) is None
    # two designs alternating: the earlier extraction of the same design holds
    alternating = [*drawn, (sizing.Design(16, 240, 7000), Path("b"), {**met, "full_scale": 0.9})]
    assert sizing._holding(alternating, sizing.Design(16, 200, 6000), cdac) == drawn[0]
