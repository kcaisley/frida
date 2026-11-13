"""Tests for the row engine's per-kit knobs in the open kits: gf180's taps inside each cell (TAP_Y),
the keep-outs round a library pin's own M2 pad (netcells.align_access, ``own``), sky130's pads
split like the library's cells (STD_SPLIT) and its row ends' supply stacks."""

import pytest

from .pdkproc import ROOT, in_pdk

needs = lambda pdk: pytest.mark.skipif(
    not (ROOT / f"pdk/{pdk}/layout/tech.py").is_file(), reason=f"needs the {pdk} PDK"
)


def tap_rows() -> tuple[int, int, set[int]]:
    """Run bound to a PDK: (TAP_Y, H, the y centres of an NMOS row cell's rail contacts)."""

    import rowcell

    cell = rowcell.mos("N", "n", 280, 440, 2, "d", "g", "vss")
    rails = {(r.y0 + r.y1) // 2 for r in cell.rects if r.layer == "CO" and r.term is None}
    return rowcell.TAP_Y, rowcell.H, rails


@needs("gf180")
def test_gf180_taps_sit_inside_each_cell() -> None:
    tap_y, h, ys = in_pdk("gf180", "flow.layout.test_rowknobs", "tap_rows")
    assert tap_y > 0 and ys == {tap_y, h - tap_y}


def pad_keepouts(gap: int) -> tuple[int, list[tuple[int, int, int, int]]]:
    """Run bound to a PDK: a frame with one pin on M2 (``own``) reaching ``gap`` short of the M2
    space from the next track's wires; (that track, the keep-outs)."""

    import netcells
    import tech

    y, hw = 3 * tech.PITCH, tech.M2W // 2
    top = y + tech.PITCH - hw - tech.M2_SPACE + gap  # the pad's top edge
    frame = {
        "padded": 4000,
        "offset": 0,
        "access": {
            "A": {
                "cuts": [],
                "patch": None,
                "bar": [1000, y - hw, 2000, y + hw],
                "pad": None,
                "own": [[1200, y - hw, 1700, top]],
            }
        },
    }
    return y + tech.PITCH, netcells.align_access(frame)[1]


@needs("gf180")
def test_a_pad_near_the_next_track_keeps_its_wires_away() -> None:
    track, keep = in_pdk("gf180", "flow.layout.test_rowknobs", "pad_keepouts", 20)
    assert [((k[1] + k[3]) // 2, k[0], k[2]) for k in keep] == [(track, 1200 - 280, 1700 + 280)]
    assert in_pdk("gf180", "flow.layout.test_rowknobs", "pad_keepouts", 0)[1] == []


def pad_implants() -> tuple[tuple[int, int], list[tuple[str, int, int]]]:
    """Run bound to a PDK: (STD_SPLIT, the N+ and P+ implants of a standard cell's pad between the rails)."""

    import rowcell

    c = rowcell.Cell("PAD", 460)
    rowcell.std_pad(c, 0, 460, "left")
    bands = [(r.layer, r.y0, r.y1) for r in c.rects if r.layer in ("NP", "PP") and 0 < r.y0 < rowcell.H and r.x1 > 0]
    return rowcell.STD_SPLIT, bands


@needs("sky130")
def test_sky130_pads_split_their_implants_as_the_library() -> None:
    (lo, hi), bands = in_pdk("sky130", "flow.layout.test_rowknobs", "pad_implants")
    assert lo < hi
    assert any(b[0] == "NP" and b[2] == lo for b in bands) and any(b[0] == "PP" and b[1] == hi for b in bands)
