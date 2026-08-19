"""Tests for calibration 1 from mechanistic CDAC measurements."""

from __future__ import annotations

from types import SimpleNamespace
from typing import cast

import numpy as np
import pytest

from flow.analysis import calibration1
from flow.analysis.calibration1 import (
    analyze,
    audit_measured_weights,
    cdac_endpoint_action,
    cdac_endpoint_action_truth_table,
    extract_endpoint_separation_weights,
)
from flow.analysis.types import MeasCdacExt
from flow.cdac import get_cdac_weights
from flow.scans.params import AdcTbParams


@pytest.mark.parametrize(
    ("a_p", "a_n", "bout", "final_p", "final_n", "p_direction", "n_direction", "changed_sides"),
    (
        (0, 0, 0, 1, 0, "0to1", None, ("p",)),
        (0, 0, 1, 0, 1, None, "0to1", ("n",)),
        (0, 1, 0, 1, 0, "0to1", "1to0", ("p", "n")),
        (0, 1, 1, 0, 1, None, None, ()),
        (1, 0, 0, 1, 0, None, None, ()),
        (1, 0, 1, 0, 1, "1to0", "0to1", ("p", "n")),
        (1, 1, 0, 1, 0, None, "1to0", ("n",)),
        (1, 1, 1, 0, 1, "1to0", None, ("p",)),
    ),
)
def test_cdac_endpoint_action_covers_all_a_and_b_states(
    a_p: int,
    a_n: int,
    bout: int,
    final_p: int,
    final_n: int,
    p_direction: str | None,
    n_direction: str | None,
    changed_sides: tuple[str, ...],
) -> None:
    action = cdac_endpoint_action(a_p, a_n, bout)

    assert (action.final_p, action.final_n) == (final_p, final_n)
    assert action.p_direction == p_direction
    assert action.n_direction == n_direction
    assert action.changed_sides == changed_sides


def test_cdac_endpoint_action_truth_table_contains_all_combinations() -> None:
    table = cdac_endpoint_action_truth_table()

    assert len(table) == 8
    assert {(row.initial_p, row.initial_n, row.bout) for row in table} == {
        (a_p, a_n, bout) for a_p in (0, 1) for a_n in (0, 1) for bout in (0, 1)
    }


def test_extract_endpoint_separation_selects_p_and_n_directions_independently() -> None:
    a_p = np.asarray([0, 0, 1, 1], dtype=np.uint8)
    a_n = np.asarray([0, 1, 0, 1], dtype=np.uint8)
    measured = np.empty((2, 4, 2), dtype=np.float64)
    measured[0, :, 0] = (10.0, 11.0, 12.0, 13.0)  # P 1-to-0
    measured[0, :, 1] = (20.0, 21.0, 22.0, 23.0)  # P 0-to-1
    measured[1, :, 0] = (30.0, 31.0, 32.0, 33.0)  # N 1-to-0
    measured[1, :, 1] = (40.0, 41.0, 42.0, 43.0)  # N 0-to-1

    result = extract_endpoint_separation_weights(a_p, a_n, measured)

    np.testing.assert_array_equal(result.p_direction_index, (1, 1, 0, 0))
    np.testing.assert_array_equal(result.n_direction_index, (1, 0, 1, 0))
    np.testing.assert_allclose(result.p_movement, (20.0, 21.0, 12.0, 13.0))
    np.testing.assert_allclose(result.n_movement, (40.0, 31.0, 42.0, 33.0))
    np.testing.assert_allclose(result.weight, (60.0, 52.0, 54.0, 46.0))


@pytest.mark.parametrize(("a_p", "a_n"), ((0, 0), (0, 1), (1, 0), (1, 1)))
def test_endpoint_separation_is_direction_selected_p_plus_n(a_p: int, a_n: int) -> None:
    measured = np.asarray(
        [
            [[2.0, 3.0]],  # P: 1-to-0, 0-to-1
            [[5.0, 7.0]],  # N: 1-to-0, 0-to-1
        ],
        dtype=np.float64,
    )

    result = extract_endpoint_separation_weights((a_p,), (a_n,), measured)

    expected_p = measured[0, 0, 1 - a_p]
    expected_n = measured[1, 0, 1 - a_n]
    assert result.weight[0] == pytest.approx(expected_p + expected_n)


def test_extract_endpoint_separation_rejects_invalid_inputs() -> None:
    measured = np.ones((2, 2, 2), dtype=np.float64)

    with pytest.raises(ValueError, match="only zero or one"):
        extract_endpoint_separation_weights((0, 2), (0, 1), measured)
    with pytest.raises(ValueError, match="same shape"):
        extract_endpoint_separation_weights((0, 1), (0,), measured)
    with pytest.raises(ValueError, match="expected"):
        extract_endpoint_separation_weights((0, 1), (0, 1), np.ones((2, 3, 2)))
    measured[0, 0, 1] = np.nan
    with pytest.raises(ValueError, match="finite and positive"):
        extract_endpoint_separation_weights((0, 1), (0, 1), measured)


def test_extract_endpoint_separation_ignores_unselected_invalid_directions() -> None:
    measured = np.ones((2, 2, 2), dtype=np.float64)
    measured[0, 0, 0] = np.nan  # P element 0 starts low, so only 0-to-1 is used.
    measured[1, 1, 1] = np.nan  # N element 1 starts high, so only 1-to-0 is used.

    result = extract_endpoint_separation_weights((0, 1), (0, 1), measured)

    np.testing.assert_allclose(result.weight, (2.0, 2.0))


def test_audit_measured_weights_normalizes_total_and_bounds_binary_paths() -> None:
    result = audit_measured_weights((8.0, 4.0, 2.0, 1.0), (9.0, 3.0, 2.0, 1.0))

    np.testing.assert_allclose(result.normalized_measured_weight, (9.0, 3.0, 2.0, 1.0))
    np.testing.assert_allclose(result.weight_error, (1.0, -1.0, 0.0, 0.0))
    assert result.minimum_binary_path_shift == pytest.approx(-1.0)
    assert result.maximum_binary_path_shift == pytest.approx(1.0)
    assert result.maximum_absolute_weight_error == pytest.approx(1.0)


def test_calibration1_public_analysis_returns_common_weights(monkeypatch: pytest.MonkeyPatch) -> None:
    params = AdcTbParams(
        board_id="test_board",
        observed_adc=0,
        active_adc_mask=tuple(int(index == 0) for index in reversed(range(16))),
    )
    nominal_cap_weight = 2.0 * np.asarray(get_cdac_weights(params.dut.cdac), dtype=np.float64)
    measured = np.repeat((nominal_cap_weight / 2.0)[None, :, None], 2, axis=0)
    measured = np.repeat(measured, 2, axis=2)
    monkeypatch.setattr(
        calibration1,
        "analyze_cdac_cap_mismatch",
        lambda _measurements, *, comparator_offset_v: SimpleNamespace(
            effective_fraction_by_direction=measured,
            comparator_offset_v=comparator_offset_v,
        ),
    )
    measurement = cast(
        MeasCdacExt,
        SimpleNamespace(
            param=params,
            daq=SimpleNamespace(trial_index=np.arange(100)),
        ),
    )

    result = analyze((measurement,), comparator_offset_v=0.0)

    assert result.method == "calibration1"
    assert result.adc_index == 0
    np.testing.assert_allclose(result.calibrated_weights, result.nominal_weights)
    np.testing.assert_array_equal(result.measured_weight_mask, [True] * 16 + [False])
    assert result.training_sample_count == 100

    measured[0, 5, :] = np.nan
    hybrid = analyze((measurement,), comparator_offset_v=0.0)
    assert not hybrid.measured_weight_mask[5]
    assert np.all(np.isfinite(hybrid.calibrated_weights))
    assert np.sum(hybrid.calibrated_weights) == pytest.approx(4095.0)
