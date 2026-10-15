"""Tests for the row router's M2 clearance (flow/layout/stems/rowroute.py)."""

import pytest

from .pdkproc import ROOT, in_pdk

PDK = next((p.parts[-3] for p in sorted(ROOT.glob("pdk/*/layout/tech.py"))), None)


def clearances() -> tuple[bool, bool, bool]:
    """Run bound to a PDK: may an M2 extension of net a run beside another piece of net a (a gap
    smaller than the M2 space, diagonally), beside net b, and onto a piece of net a it touches?"""

    import rowroute
    from tech import M2_SPACE, M2W

    bar = (0, 0, 1000, M2W)  # the extension, net a
    beside = (1000 + M2_SPACE // 2, M2W, 2000, 2 * M2W)  # the next track up, a corner closer than the space
    router = rowroute.Router([("a", *beside)], 4000, 4000)
    own = router.free_box2("a", *bar)
    other = rowroute.Router([("b", *beside)], 4000, 4000).free_box2("a", *bar)
    touching = rowroute.Router([("a", 1000, 0, 2000, M2W)], 4000, 4000).free_box2("a", *bar)
    return own, other, touching


@pytest.mark.skipif(PDK is None, reason="no PDK submodule checked out")
def test_a_separate_piece_of_the_net_keeps_the_m2_space_too() -> None:
    own, other, touching = in_pdk(PDK, "flow.layout.test_rowroute", "clearances")
    assert (own, other, touching) == (False, False, True)
