"""Tests for ALIGN's post step (flow/layout/align/post.py)."""

import pytest

from .pdkproc import ROOT, in_pdk

needs_tsmc28 = pytest.mark.skipif(
    not (ROOT / "pdk/tsmc28/layout/tech.py").is_file(), reason="needs the tsmc28 PDK submodule"
)


def site_gap_fill() -> tuple[int, bool]:
    """Run bound to a PDK whose library fillers start at two sites: fill a row of standard cells
    with a one-site gap between two of them; (gaps filled, the gap under N-well as the cells' sides)."""

    import klayout.db as kdb
    import rowcell
    from tech import LAYERS, STD_FILLS

    from flow.layout.align import post

    site = min(w for _, w in STD_FILLS) // 2
    layout = kdb.Layout()
    layout.dbu = 0.001
    top = layout.create_cell("TOP")
    for x0, x1 in ((0, 4 * site), (5 * site, 9 * site)):
        top.shapes(layout.layer(*LAYERS["BND"])).insert(kdb.Box(x0, 0, x1, rowcell.H))
    filled = post.fill_rows(layout, top, {0}, {})
    nw = kdb.Region(top.shapes(layout.layer(*LAYERS["NW"])))
    gap = kdb.Region(kdb.Box(4 * site, rowcell.H - 10, 5 * site, rowcell.H))
    return filled, (gap - nw).is_empty()


@needs_tsmc28
def test_a_gap_narrower_than_the_library_fillers_takes_the_standard_cells_profile() -> None:
    assert in_pdk("tsmc28", "flow.layout.test_align_post", "site_gap_fill") == (1, True)
