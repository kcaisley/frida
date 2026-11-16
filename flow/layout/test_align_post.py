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


def capped_straps() -> tuple[int, dict[str, int], bool]:
    """Run bound to a PDK: two rows of cells and an empty row between them under an M3 sheet across
    the block (capacitors' plates), their rails' lines vss, vdd, vss, vdd; (the straps drawn, each supply's M3 labels, whether every
    trunk lies outside the block and every rail line meets its supply's trunks by a VIA2)."""

    import klayout.db as kdb
    import rowcell
    from tech import LAYERS, XPITCH

    from flow.layout import post

    layout = kdb.Layout()
    layout.dbu = 0.001
    top = layout.create_cell("TOP")
    width = 16 * XPITCH
    for k in (0, 2):
        cell = rowcell.Cell("row", width)
        rowcell.rails(cell, width, "n")
        t = kdb.Trans(0, k * rowcell.H) if k % 2 == 0 else kdb.Trans(kdb.Trans.M0, 0, (k + 1) * rowcell.H)
        for r in cell.rects:
            if rowcell.GLAYERS.get(r.layer) and r.kind != "stub":
                top.shapes(layout.layer(*rowcell.GLAYERS[r.layer])).insert(
                    kdb.Box(r.x0, r.y0, r.x1, r.y1).transformed(t)
                )
    top.shapes(layout.layer(*LAYERS["M3"])).insert(kdb.Box(0, -rowcell.H, width, 4 * rowcell.H))
    straps = post.supply_straps(layout, top, (0, width))
    m3 = layout.layer(*post.PIN_TEXT["M3"])
    labels: dict[str, int] = {}
    for s in top.shapes(m3).each():
        if s.is_text():
            labels[s.text.string] = labels.get(s.text.string, 0) + 1
    trunks = kdb.Region(top.shapes(layout.layer(*LAYERS["M3"]))) - kdb.Region(
        kdb.Box(0, -rowcell.H, width, 4 * rowcell.H)
    )
    v2 = kdb.Region(top.shapes(layout.layer(*LAYERS["V2"])))
    outside = trunks.inside(kdb.Region(kdb.Box(0, -rowcell.H, width, 4 * rowcell.H))).is_empty()
    joined = all(
        not (v2 & kdb.Region(kdb.Box(-10 * XPITCH, y - 1, width + 10 * XPITCH, y + 1))).is_empty()
        for y in (0, rowcell.H, 2 * rowcell.H, 3 * rowcell.H)
    )
    return straps, labels, outside and joined


@pytest.mark.parametrize("pdk", ("ihp130", "gf180"))
def test_supplies_under_a_capacitor_sheet_get_trunks_outside_the_block(pdk) -> None:
    if not (ROOT / f"pdk/{pdk}/layout/tech.py").is_file():
        pytest.skip(f"needs the {pdk} PDK")
    straps, labels, ok = in_pdk(pdk, "flow.layout.test_align_post", "capped_straps")
    assert straps == 4 and labels == {"vss": 2, "vdd": 2} and ok


def decap_gap_fill(gap_sites: int, routed: bool, pol: str = "n") -> dict:
    """Run bound to a PDK: an analog row's gap of ``gap_sites`` sites between two cells of type
    ``pol`` (NMOS "n", PMOS "p"), an M1
    wire of ALIGN's down through its middle when ``routed``; what ``fill_rows`` drew there: its
    decaps (type, fingers, x, width), its plain stretches' widths, the gap's width, whether every
    decap lies inside the gap and keeps M1's space beside a rail from the wire, and the decaps' LVS
    lines."""

    import fillcell
    import klayout.db as kdb
    import rowcell
    from tech import LAYERS, XPITCH

    from flow.layout import post

    layout = kdb.Layout()
    layout.dbu = 0.001
    top = layout.create_cell("TOP")
    left, right = 4 * XPITCH, (4 + gap_sites) * XPITCH
    for x0, x1 in ((0, left), (right, right + 4 * XPITCH)):
        cell = rowcell.Cell("row", x1 - x0)
        rowcell.rails(cell, x1 - x0, pol)
        for r in cell.rects:
            if rowcell.GLAYERS.get(r.layer) and r.kind != "stub":
                top.shapes(layout.layer(*rowcell.GLAYERS[r.layer])).insert(kdb.Box(r.x0 + x0, r.y0, r.x1 + x0, r.y1))
    middle = (left + right) // 2 // XPITCH * XPITCH
    wire = kdb.Box(middle - 50, -rowcell.H // 2, middle + 50, rowcell.H + rowcell.H // 2)
    if routed:
        top.shapes(layout.layer(*LAYERS["M1"])).insert(wire)
    fill = post.Fill()
    post.fill_rows(layout, top, set(), {}, fill=fill)
    boxes = [kdb.Box(d.x, d.y, d.x + fillcell.width(d.pol, d.nf), d.y + rowcell.H) for d in fill.decaps]
    keep = post._rail_space()
    return {
        "decaps": [(d.pol, d.nf, d.x, fillcell.width(d.pol, d.nf)) for d in fill.decaps],
        "plain": fill.plain,
        "gap": right - left,
        "inside": all(left <= b.left and b.right <= right for b in boxes),
        "clear": all(b.right + keep <= wire.left or b.left - keep >= wire.right for b in boxes) if routed else True,
        "lines": [fillcell.lvs_line(f"Mdecap_{i}", d.pol, d.nf) for i, d in enumerate(fill.decaps)],
        "smallest": fillcell.width("n", 1),
        "record": fill.record(),
    }


@pytest.mark.parametrize("pdk", ("ihp130", "gf180", "sky130", "tsmc65", "tsmc28"))
def test_a_row_gap_takes_decaps_and_plain_filler_in_what_is_left(pdk) -> None:
    if not (ROOT / f"pdk/{pdk}/layout/tech.py").is_file():
        pytest.skip(f"needs the {pdk} PDK")
    wide = in_pdk(pdk, "flow.layout.test_align_post", "decap_gap_fill", 40, False)
    assert wide["decaps"] and wide["inside"]
    assert all(pol == "n" for pol, *_ in wide["decaps"])  # beside NMOS cells, NMOS decaps
    # decaps from the gap's left, plain filler in what is left, narrower than the smallest decap
    assert sum(w for *_, w in wide["decaps"]) + sum(wide["plain"]) == wide["gap"]
    assert all(width < wide["smallest"] for width in wide["plain"])
    assert wide["record"]["decap ff"] > 0 and wide["record"]["decaps"] == len(wide["lines"])
    assert all(line.split()[1:5] == ["vss", "vdd", "vss", "vss"] for line in wide["lines"])
    routed = in_pdk(pdk, "flow.layout.test_align_post", "decap_gap_fill", 40, True)
    assert routed["decaps"] and routed["inside"] and routed["clear"]
    narrow = in_pdk(pdk, "flow.layout.test_align_post", "decap_gap_fill", 1, False)
    assert not narrow["decaps"] and narrow["plain"] == [narrow["gap"]]
    beside_pmos = in_pdk(pdk, "flow.layout.test_align_post", "decap_gap_fill", 40, False, "p")
    assert beside_pmos["decaps"] and all(pol == "p" for pol, *_ in beside_pmos["decaps"])
    assert all(line.split()[1:5] == ["vdd", "vss", "vdd", "vdd"] for line in beside_pmos["lines"])


def reserved_rows() -> tuple[list[int], int, int, dict[str, int]]:
    """Run bound to a PDK: a row of cells at the bottom and one at the top, three rows between them
    with no cell under an M4 sheet (capacitors stacked over the rows); (the rows left empty, the M1
    drawn inside them, the straps drawn, each supply's M3 labels)."""

    import klayout.db as kdb
    import rowcell
    from tech import LAYERS, XPITCH

    from flow.layout import post

    layout = kdb.Layout()
    layout.dbu = 0.001
    top = layout.create_cell("TOP")
    width = 24 * XPITCH
    for k in (0, 4):
        cell = rowcell.Cell("row", width)
        rowcell.rails(cell, width, "n")
        cell.add("BND", 0, 0, width, rowcell.H)
        t = kdb.Trans(0, k * rowcell.H) if k % 2 == 0 else kdb.Trans(kdb.Trans.M0, 0, (k + 1) * rowcell.H)
        for r in cell.rects:
            if rowcell.GLAYERS.get(r.layer) and r.kind != "stub":
                top.shapes(layout.layer(*rowcell.GLAYERS[r.layer])).insert(
                    kdb.Box(r.x0, r.y0, r.x1, r.y1).transformed(t)
                )
    sheet = kdb.Region(kdb.Box(0, 0, width, 5 * rowcell.H))
    top.shapes(layout.layer(*LAYERS["M4"])).insert(sheet)
    fill = post.Fill()
    post.fill_rows(layout, top, set(), {}, capacitors=sheet, fill=fill)
    inside = kdb.Region(kdb.Box(0, rowcell.H + rowcell.RAIL, width, 4 * rowcell.H - rowcell.RAIL))
    m1 = kdb.Region(top.shapes(layout.layer(*LAYERS["M1"]))) & inside
    straps = post.supply_straps(layout, top, empty=fill.reserved)
    labels: dict[str, int] = {}
    for s in top.shapes(layout.layer(*post.PIN_TEXT["M3"])).each():
        if s.is_text():
            labels[s.text.string] = labels.get(s.text.string, 0) + 1
    return sorted(fill.reserved), m1.count(), straps, labels


@pytest.mark.parametrize("pdk", ("tsmc65", "ihp130"))
def test_rows_left_empty_under_capacitors_get_no_rails_and_the_bands_join_by_trunks(pdk) -> None:
    if not (ROOT / f"pdk/{pdk}/layout/tech.py").is_file():
        pytest.skip(f"needs the {pdk} PDK")
    reserved, m1, straps, labels = in_pdk(pdk, "flow.layout.test_align_post", "reserved_rows")
    assert reserved == [1, 2, 3] and m1 == 0
    assert straps == 4 and labels == {"vss": 2, "vdd": 2}  # a trunk of each supply at each end
