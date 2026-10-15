"""Tests for the row cells' pairs in tsmc28: cross-coupled pairs on three S/D tracks, short gates on gridded poly."""

from itertools import pairwise

import pytest

from .pdkproc import ROOT, in_pdk

DevSpec = tuple[str, int, int, int, str, str, str]  # rowcell.Dev: name, L, W per finger, fingers, d, g, s

needs_tsmc28 = pytest.mark.skipif(
    not (ROOT / "pdk/tsmc28/layout/tech.py").is_file(), reason="needs the tsmc28 PDK submodule"
)


def via2_gaps(
    pol: str, sources: tuple[str, str], size: tuple[int, int, int] = (180, 240, 4)
) -> tuple[int, int, list[int]]:
    """Run bound to a PDK: draw a cross-coupled pair; (V2 size, VIA_SPACE, the V2 gaps on each M3 column)."""

    import rowcell  # the bound PDK's row cells
    import tech

    devs = [
        rowcell.Dev("A", *size, "latch_n", "latch_p", sources[0]),
        rowcell.Dev("B", *size, "latch_p", "latch_n", sources[1]),
    ]
    cell = rowcell.mos_row("CCP", pol, devs)
    columns: dict[int, list[int]] = {}
    for r in cell.rects:
        if r.layer == "V2":
            columns.setdefault((r.x0 + r.x1) // 2, []).append((r.y0 + r.y1) // 2)
    gaps = [b - a for ys in columns.values() for a, b in zip(sorted(ys), sorted(ys)[1:], strict=False)]
    return tech.V2, getattr(tech, "VIA_SPACE", 0), gaps


@needs_tsmc28
@pytest.mark.parametrize(
    ("pol", "sources", "size"),
    [
        ("n", ("src_p", "src_n"), (180, 240, 4)),
        ("p", ("vdd", "vdd"), (180, 240, 4)),
        ("n", ("vss", "vss"), (180, 240, 4)),
        ("p", ("vdd", "vdd"), (30, 340, 1)),  # one finger: widened until its jumpers fit
    ],
    ids=["nmos-own-sources", "pmos-on-rail", "nmos-on-rail", "one-finger"],
)
def test_cross_coupled_pairs_keep_their_via2_apart(
    pol: str, sources: tuple[str, str], size: tuple[int, int, int]
) -> None:
    v2, space, gaps = in_pdk("tsmc28", "flow.layout.test_rowcell", "via2_gaps", pol, sources, size)
    assert gaps and min(gaps) >= v2 + space


def poly_spaces(pol: str, devs: list[DevSpec]) -> list[int]:
    """Run bound to a PDK: draw a row cell; the spaces between its poly lines, gates and dummies, left to right."""

    import rowcell

    cell = rowcell.mos_row("P", pol, [rowcell.Dev(*d) for d in devs])
    po = sorted({(r.x0, r.x1) for r in cell.rects if r.layer in ("PO", rowcell.PO_DUMMY_LAYER)})
    return [b0 - a1 for (_, a1), (b0, _) in pairwise(po)]


@needs_tsmc28
@pytest.mark.parametrize(
    ("pol", "devs"),
    [
        ("p", [("A", 30, 340, 1, "da", "ga", "vdd"), ("B", 30, 340, 1, "db", "gb", "vdd")]),
        ("n", [("A", 30, 280, 4, "da", "ga", "s"), ("B", 30, 280, 4, "db", "gb", "s")]),
        ("n", [("A", 30, 280, 2, "da", "ga", "sa"), ("B", 30, 280, 2, "db", "gb", "sb")]),
    ],
    ids=["one-finger-on-rail", "four-fingers-shared-source", "own-sources"],
)
def test_a_pair_of_short_gates_keeps_its_poly_on_one_pitch(pol: str, devs: list[DevSpec]) -> None:
    spaces = in_pdk("tsmc28", "flow.layout.test_rowcell", "poly_spaces", pol, devs)
    assert len(spaces) > 2 and len(set(spaces)) == 1


def pattern_cell(rows: list[list[tuple[int, int]]], devs: list[DevSpec], pol: str = "n") -> tuple[dict, int]:
    """Run bound to a PDK: an array of ``devs`` in ``rows`` of runs (device index, fingers); each gate
    net's M2 track, and how many signal nets are not one connected piece."""

    import rowcell

    cell = rowcell.mos_grid("P", pol, [rowcell.Dev(*d) for d in devs], [[rowcell.Run(*r) for r in row] for row in rows])
    order = {"M1": 0, "V1": 1, "M2": 2, "V2": 3, "M3": 4}
    by: dict[str, list] = {}
    for r in cell.rects:
        if r.net and r.layer in order and r.net not in ("vss", "vdd"):
            by.setdefault(r.net, []).append(r)
    split = 0
    for rs in by.values():
        parent = list(range(len(rs)))

        def find(i: int, parent: list[int] = parent) -> int:
            while parent[i] != i:
                i = parent[i]
            return i

        for i, a in enumerate(rs):
            for j, b in enumerate(rs[:i]):
                near = abs(order[a.layer] - order[b.layer]) <= 1
                if near and a.x0 <= b.x1 and b.x0 <= a.x1 and a.y0 <= b.y1 and b.y0 <= a.y1:
                    parent[find(i)] = find(j)
        split += len({find(i) for i in range(len(rs))}) > 1
    gates = {r.net: (r.y0 + r.y1) // 2 for r in cell.rects if r.layer == "M2" and r.net in {d[5] for d in devs}}
    return gates, split


@needs_tsmc28
def test_interdigitated_gates_take_their_own_tracks_and_every_net_is_one_piece() -> None:
    dp = [("A", 30, 280, 4, "da", "ga", "s"), ("B", 30, 280, 4, "db", "gb", "s")]
    gates, split = in_pdk("tsmc28", "flow.layout.test_rowcell", "pattern_cell", [[(0, 2), (1, 2), (0, 2), (1, 2)]], dp)
    assert len(set(gates.values())) == 2 and split == 0


@needs_tsmc28
def test_a_common_centroid_array_over_two_rows_is_connected() -> None:
    ccp = [("A", 30, 280, 2, "x", "y", "vss"), ("B", 30, 280, 2, "y", "x", "vss")]
    rows = [[(0, 1), (1, 2), (0, 1)], [(1, 1), (0, 2), (1, 1)]]
    _, split = in_pdk("tsmc28", "flow.layout.test_rowcell", "pattern_cell", rows, ccp)
    assert split == 0
