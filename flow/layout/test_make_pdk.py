"""Each PDK's ALIGN files in its layout directory (``pdk/<pdk>/layout``: layers.json, models.sp,
rows.json, user_template.sp) are what ``make_pdk.py`` writes from its ``tech`` now; a PDK not checked out is skipped."""

import pytest

from flow.layout.package import ROOT
from flow.layout.pdkproc import in_pdk

PDKS = ("tsmc65", "tsmc28", "tpsc65", "tower180", "ihp130", "lf150", "sky130", "gf180")


@pytest.mark.parametrize("pdk", PDKS)
def test_committed_align_files_are_current(pdk, tmp_path):
    layout = ROOT / "pdk" / pdk / "layout"
    if not (layout / "tech.py").is_file():
        pytest.skip(f"{pdk} is not checked out")
    in_pdk(pdk, "flow.layout.make_pdk", "build", pdk, tmp_path)
    for name in ("layers.json", "models.sp", "rows.json", "user_template.sp"):
        assert (tmp_path / name).read_text() == (layout / name).read_text(), f"{pdk}: {name} is stale; rerun make_pdk"
