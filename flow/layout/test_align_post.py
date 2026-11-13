"""Tests for ALIGN's post step (flow/layout/post.py)."""

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

    from flow.layout import post

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


def routed_gap_fill(routed: bool) -> tuple[int, int, int, bool]:
    """Run bound to a PDK: an analog row's gap between two cells, an M1 wire of ALIGN's down
    through it across both rail lines when ``routed``; (the fill's M1 pieces, its contacts, the
    contacts of the plain fill, whether the fill keeps M1's space from the wire)."""

    import klayout.db as kdb
    import rowcell
    from tech import LAYERS, M1_SPACE, XPITCH

    from flow.layout import post

    def fill(wire: kdb.Box | None) -> tuple[kdb.Region, kdb.Region]:
        layout = kdb.Layout()
        layout.dbu = 0.001
        top = layout.create_cell("TOP")
        for x0, x1 in ((0, 4 * XPITCH), (12 * XPITCH, 16 * XPITCH)):
            top.shapes(layout.layer(*LAYERS["BND"])).insert(kdb.Box(x0, 0, x1, rowcell.H))
        m1 = layout.layer(*LAYERS["M1"])
        if wire:
            top.shapes(m1).insert(wire)
        post.fill_rows(layout, top, set(), {})
        shapes = kdb.Region(top.shapes(m1)).merged()
        cuts = kdb.Region(top.shapes(layout.layer(*LAYERS["CO"]))) if LAYERS.get("CO") else kdb.Region()
        return shapes - (kdb.Region(wire) if wire else kdb.Region()), cuts

    wire = kdb.Box(8 * XPITCH - 100, -rowcell.H // 2, 8 * XPITCH + 100, rowcell.H + rowcell.H // 2)
    _, plain_cuts = fill(None)
    m1, cuts = fill(wire if routed else None)
    clear = (m1.sized(M1_SPACE - 1) & kdb.Region(wire)).is_empty() and (cuts & kdb.Region(wire)).is_empty()
    return m1.count(), cuts.count(), plain_cuts.count(), clear


@pytest.mark.parametrize("pdk", ("ihp130", "gf180", "sky130", "tsmc65"))
def test_a_gap_fill_keeps_clear_of_the_m1_routed_through_it(pdk) -> None:
    if not (ROOT / f"pdk/{pdk}/layout/tech.py").is_file():
        pytest.skip(f"needs the {pdk} PDK")
    plain = in_pdk(pdk, "flow.layout.test_align_post", "routed_gap_fill", False)
    pieces, cuts, plain_cuts, clear = in_pdk(pdk, "flow.layout.test_align_post", "routed_gap_fill", True)
    assert plain[0] == 2  # the two rails across the gap
    assert clear and pieces == 4 and cuts <= plain_cuts  # each rail cut back on either side of the wire
