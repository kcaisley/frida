"""The capacitive DAC's driver bands (``subckt._driver_rows``): rows at most, balance, outline."""

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
