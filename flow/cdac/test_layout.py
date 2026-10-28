"""The CDAC layout's planning, which needs no PDK: each net its own track, in the order of its
columns from the channel's start; the spacing test between two shapes; the unit grid's rows; a
supply's pin jogging off its strap."""

from itertools import pairwise

from klayout import db

from .layout import _clearance, _gap, _rows, _supply_pin, _tracks

G = {"clearance": 600, "track": 200}
# a thin M4 under a thick top via (its column metal's width and space, its cut's enclosures)
RULE = {
    "M4": {"width": 100, "space": 100, "length": 500},
    "M5": {"width": 400, "space": 400},
    "V3": {"cut": 100, "space": 100, "along": 50, "across": 0},
    "V4": {"cut": 360, "space": 340, "along": 80, "across": 20},
}
GEO = {"grid": 5, "end_V3": 100, "end_V4": 260}


def test_each_net_has_its_track_in_the_order_of_its_columns():
    nets = [{"name": "b", "near_x": 3000, "far_x": 1100}, {"name": "a", "near_x": 1000, "far_x": 5000}]
    tracks, far = _tracks(nets, 0, -1, G)
    # below the array: the first column's track nearest it, a track pitch between
    assert tracks == {"a": -600, "b": -800}
    assert far == -(2 * 600 + 200)
    tracks, far = _tracks(nets, 1000, 1, G)
    assert tracks == {"a": 1600, "b": 1800} and far == 2400


def test_shapes_within_a_space_vertically_must_be_a_space_apart_across():
    a = db.Box(0, 0, 100, 1000)
    assert _gap(a, db.Box(120, 1050, 220, 2000), 100) == 20  # corner to corner, 50 apart in y
    assert _gap(a, db.Box(120, 1100, 220, 2000), 100) == 10**6  # a space apart in y
    assert _gap(a, db.Box(300, 0, 400, 1000), 100) == 200


def test_the_unit_grid_holds_each_stage_whole_over_its_own_column():
    """Every stage's units in its whole rows (heaviest first) and one piece about its column, no
    two pieces of a row overlapping, no two stages on one column."""
    weights = [64, 32, 16, 9, 8, 4, 2, 1, 1]
    rows, columns = _rows(weights, 12)
    placed = {stage: 0 for stage in range(len(weights))}
    for row in rows:
        spans = sorted((first, first + count) for _, first, count in row)
        assert all(end <= start for (_, end), (start, _) in pairwise(spans))
        assert all(0 <= first and first + count <= 12 for _, first, count in row)
        for stage, first, count in row:
            placed[stage] += count
            if count < 12:  # a stage's rest covers its column
                assert first <= columns[stage] < first + count
    assert placed == dict(enumerate(weights))
    assert len(set(columns.values())) == len(weights)
    assert [row[0][0] for row in rows[:5]] == [0, 0, 0, 0, 0]  # the heaviest stage's whole rows first


def test_a_supply_pin_jogs_off_its_strap_where_the_column_above_it_is_taken():
    """vdd's and vss's straps closer at each end of a bank than two thick-via landings: vdd's pin on
    the left, its column jogged along M4 clear of a state's column beside the strap; vss's on the
    right, the two columns a bank apart."""
    strap = lambda x: db.Box(x - 50, 0, x + 50, 4000)
    state = db.Box(400, -(10**6), 800, -100)
    pins = {"straps": {"vdd": [strap(200), strap(9200)], "vss": [strap(0), strap(9400)]}, "columns": [state], "m4": []}
    vdd = _supply_pin(pins["straps"]["vdd"], -1, pins, RULE, GEO)
    vss = _supply_pin(pins["straps"]["vss"][::-1], -1, pins, RULE, GEO)
    assert vdd["strap_x"] == 200 and vdd["x"] < 200 and vdd["clear"] >= 0
    assert _clearance(vdd["column"], [state], RULE, "M5") >= 0
    assert vss["strap_x"] == vss["x"] == 9400 and vss["clear"] >= 0
    assert pins["columns"] == [state, vdd["column"], vss["column"]] and pins["m4"] == [vdd["m4"], vss["m4"]]
