"""The CDAC layout's channel planning, which needs no PDK: each net a track, a net whose column
from the array stands over another's column from the bank given the track nearer the array, and
the spacing test between two shapes."""

import pytest
from klayout import db

from .layout import _gap, _tracks

G = {"clearance": 600, "track": 200, "column": 300}


def test_a_column_over_another_nets_takes_the_track_nearer_the_array():
    # a's column from the array (x 1000) over b's column from the bank (x 1100): b nearer the bank
    nets = [{"name": "a", "near_x": 1000, "far_x": 5000}, {"name": "b", "near_x": 3000, "far_x": 1100}]
    tracks, far = _tracks(nets, 0, -1, G)
    assert tracks["a"] > tracks["b"]  # below the array: a's track higher, nearer it
    assert far == -(2 * 600 + 200)
    # apart, the nets keep their order across the channel by their columns from the array
    apart = [{"name": "a", "near_x": 1000, "far_x": 9000}, {"name": "b", "near_x": 3000, "far_x": 7000}]
    assert len(set(_tracks(apart, 0, 1, G)[0].values())) == 2


def test_two_nets_each_over_the_others_column_have_no_track_order():
    nets = [{"name": "a", "near_x": 1000, "far_x": 3000}, {"name": "b", "near_x": 3000, "far_x": 1000}]
    with pytest.raises(RuntimeError, match="no track order"):
        _tracks(nets, 0, -1, G)


def test_shapes_within_a_space_vertically_must_be_a_space_apart_across():
    a = db.Box(0, 0, 100, 1000)
    assert _gap(a, db.Box(120, 1050, 220, 2000), 100) == 20  # corner to corner, 50 apart in y
    assert _gap(a, db.Box(120, 1100, 220, 2000), 100) == 10**6  # a space apart in y
    assert _gap(a, db.Box(300, 0, 400, 1000), 100) == 200
