"""Tests for the row designs' cells and finishing steps (flow/layout/stems/netcells.py)."""

import pytest

from .pdkproc import ROOT, in_pdk

PDK = next((p.parts[-3] for p in sorted(ROOT.glob("pdk/*/layout/tech.py"))), None)


def closed_wells(gap_in_spaces: float) -> tuple[int, int]:
    """Run bound to a PDK: a well with a notch ``gap_in_spaces`` N-well spaces wide (a PMOS cell's
    well, a narrow filler's band, the row end's), closed; (polygons, area off the notch-free outline)."""

    import klayout.db as kdb
    import netcells
    from tech import LAYERS, NW_SPACE

    layout = kdb.Layout()
    layout.dbu = 0.001
    top = layout.create_cell("TOP")
    li = layout.layer(*LAYERS["NW"])
    gap = int(gap_in_spaces * NW_SPACE)
    top.shapes(li).insert(kdb.Box(0, 0, 4000, 1000))  # the band along the rail
    top.shapes(li).insert(kdb.Box(0, 0, 2000, 3000))  # the PMOS cell's well
    top.shapes(li).insert(kdb.Box(2000 + gap, 0, 4000, 2000))  # the row end's
    netcells.close_wells(layout, kdb, top)
    nw = kdb.Region(top.shapes(li)).merged()
    box = kdb.Region(kdb.Box(0, 0, 2000, 3000)) + kdb.Region(kdb.Box(2000, 0, 4000, 2000))
    return nw.count(), int((nw ^ box.merged()).area())


@pytest.mark.skipif(PDK is None, reason="no PDK submodule checked out")
def test_a_well_notch_within_the_space_is_closed_and_a_wider_one_kept() -> None:
    assert in_pdk(PDK, "flow.layout.test_netcells", "closed_wells", 0.9) == (1, 0)
    count, extra = in_pdk(PDK, "flow.layout.test_netcells", "closed_wells", 1.5)
    assert count == 1 and extra > 0
