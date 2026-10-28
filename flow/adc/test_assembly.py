"""The ADC's blocks side by side (``flow.adc.assembly``), from the blocks' layouts under build/: one
top cell, each block labelled where the viewer's export finds it, nothing signed off."""

import json
from pathlib import Path

import pytest
from klayout import db

from flow.adc import sweep
from flow.adc.assembly import assemble_blocks
from flow.cdac.caparray.subckt import RedunStrat
from flow.sweep.runner import ROOT
from flow.web.export import export_layout


def test_the_blocks_sit_side_by_side_in_one_labelled_cell(tmp_path: Path) -> None:
    # the first converter of the sweep with MSB redistribution of 4 extra cycles and the second
    # comparator of the grid
    params = next(
        p
        for p in sweep.instances("tsmc65")
        if p.cdac.n_extra == 4 and p.cdac.redun_strat == RedunStrat.MSB_REDIST and p.comp == sweep.COMPARATORS[1]
    )
    try:
        entry = assemble_blocks("tsmc65", params, tmp_path)
    except (FileNotFoundError, LookupError) as error:
        pytest.skip(f"the blocks are not laid out under build/: {error}")

    assert entry["error"] is None and entry["drc_violations"] is None and entry["lvs_correct"] is None
    names = [block["name"] for block in entry["blocks"]]
    assert {"comp", "samp_p", "samp_n", "cap_p", "cap_n"} <= set(names)
    assert all((ROOT / block["source"]).exists() for block in entry["blocks"])
    # in a row, apart, inside the cell's extent
    lefts = [block["x_um"] for block in entry["blocks"]]
    assert lefts == sorted(lefts)
    for left, right in zip(entry["blocks"], entry["blocks"][1:]):
        assert left["x_um"] + left["w_um"] < right["x_um"]
    assert entry["w_um"] > sum(block["w_um"] for block in entry["blocks"])
    assert entry["h_um"] >= max(block["h_um"] for block in entry["blocks"])

    gds = ROOT / entry["gds"]
    layout = db.Layout()
    layout.read(str(gds))
    assert [cell.name for cell in layout.top_cells()] == ["adc_blocks"]
    # the viewer's export: the labels on the boundary layer, which it shows
    exported = export_layout(str(gds), "tsmc65", str(tmp_path / "adc_blocks.layout.json"))
    assert {"M1", "OD", "PO", "BND"} <= set(exported["layers"])
    labels = json.loads((tmp_path / "adc_blocks.layout.json").read_text())["labels"]
    assert {label["text"] for label in labels if label["layer"] == "BND"} == set(names)
