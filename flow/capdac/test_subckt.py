"""The capacitive DAC's driver bands (``subckt._driver_rows``): rows at most, balance, outline."""

import hdl21 as h

from . import subckt


def test_balanced_rows_split_the_widths_as_evenly_as_it_goes() -> None:
    widths = [9200, 7400, 4000, 3200, *[2400] * 12]
    rows = subckt._balanced(widths, 3)
    assert sorted(i for r in rows for i in r) == list(range(len(widths)))
    assert all(r == sorted(r) for r in rows)
    assert subckt._rows_width(widths, rows) <= 18000  # the lower bound is sum / 3 = 17533 nm


def test_a_band_never_takes_more_rows_than_its_cap() -> None:
    main, diff = [2400] * 16, [1000] * 16
    for stacked in (True, False):
        m, d = subckt._driver_rows(main, diff, (5000, 40000), 1800, stacked, 200)
        assert len(m) <= subckt.MAIN_ROWS and len(d) <= subckt.DIFF_ROWS
        assert sorted(i for r in m for i in r) == list(range(16)) and sorted(i for r in d for i in r) == list(range(16))


def test_the_rows_reach_past_the_capacitors_where_three_rows_do_not_fit_under_them() -> None:
    main = [2400] * 16
    m, _ = subckt._driver_rows(main, [], (5000, 40000), 1800, True)
    assert len(m) == subckt.MAIN_ROWS and subckt._rows_width(main, m) > 5000


def test_the_fewest_rows_where_more_would_not_narrow_the_outline() -> None:
    main = [1000] * 4
    m, d = subckt._driver_rows(main, [], (20000, 40000), 1800, True)
    assert len(m) == 1 and d == []


def test_a_stage_in_as_many_strips_as_pieces_is_its_pieces() -> None:
    plates = [(64.0, 0.0), (64.0, 0.0), (44.0, 20.0)]
    assert subckt._segments(plates, 3) == plates


def test_strips_keep_each_stages_plates_and_hold_no_more_than_their_length() -> None:
    plates = [[(64.0, 0.0)] * 5 + [(44.0, 20.0)], [(40.0, 24.0)], [(64.0, 0.0), (33.0, 31.0)]]
    for length in (16.0, 48.0, 64.0, 96.0, 200.0):
        for stage, strips in zip(plates, subckt._strips(plates, length), strict=True):
            assert all(m + d <= length + 1e-9 for m, d in strips)
            assert abs(sum(m for m, _ in strips) - sum(m for m, _ in stage)) < 1e-9
            assert abs(sum(d for _, d in strips) - sum(d for _, d in stage)) < 1e-9
            assert len({round(m + d, 9) for m, d in strips}) == 1  # a stage's strips one load
    # half a piece's length: each piece in two strips, each its half
    assert subckt._strips([[(44.0, 20.0)]], 32.0) == [[(22.0, 10.0), (22.0, 10.0)]]


def test_the_outline_nearest_two_to_one_within_the_area_held() -> None:
    outlines = {1.0: (100, 40), 2.0: (45, 90), 3.0: (40, 100), 4.0: (30, 160)}
    assert subckt._two_to_one(outlines, 1.0) == 3.0  # 2.0 and 3.0 in ASPECT, 3.0 the smaller; 4.0 too big
    assert subckt._two_to_one({1.0: (100, 40), 2.0: (45, 90), 0.5: (200, 20)}, 1.0) == 2.0
    # more area than GROWTH allows is never taken, however near two to one
    assert subckt._two_to_one({1.0: (100, 40), 2.0: (80, 160)}, 1.0) == 1.0
    # the plain one where another is no nearer
    assert subckt._two_to_one({1.0: (100, 40), 0.5: (100, 40)}, 1.0) == 1.0


def test_a_tie_cell_abuts_each_driver_and_both_sides_of_a_wide_one() -> None:
    side = h.Module(name="side")
    side.vdd, side.vss = h.Port(), h.Port()
    cell = h.ExternalModule(name="TIE", port_list=[h.Inout(name="VDD"), h.Inout(name="VSS")], paramtype=h.HasNoParams)
    inv = h.ExternalModule(name="INV", port_list=[h.Inout(name="VDD")], paramtype=h.HasNoParams)
    narrow, broad = side.add(inv()(VDD=side.vdd), name="narrow"), side.add(inv()(VDD=side.vdd), name="broad")
    entries, abut = subckt._tied_row(side, cell, (narrow, broad), {"broad"}, "main0")
    assert [e.name for e in entries] == ["Xtie_main0_0", "narrow", "Xtie_main0_1", "broad", "Xtie_main0_1r"]
    assert len(abut) == 2 and all(a.abut for a in abut)
