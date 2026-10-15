"""Tests for the row cells' cross-coupled pairs, in a PDK whose rows have three S/D tracks."""

import pytest

from .pdkproc import ROOT, in_pdk

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
