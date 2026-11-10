"""The shared layout step: ALIGN alone (``lay_out_align``), by the PDK's router, by the other where
that one fails, routed again where its route joins two nets; the signoff is the CLI's steps'."""

from __future__ import annotations

from pathlib import Path

import pytest
from klayout import db

from flow.layout import step


def _gds(path: Path) -> Path:
    layout_ = db.Layout()
    layout_.dbu = 0.001
    layout_.create_cell("TOP").shapes(layout_.layer(1, 0)).insert(db.Box(0, 0, 2000, 1000))
    path.parent.mkdir(parents=True, exist_ok=True)
    layout_.write(str(path))
    return path


@pytest.fixture
def aligned(monkeypatch):
    """ALIGN's inputs and its route's check stood in for: the netlists and design directory of
    ``inputs`` (an LVS netlist ``inv.cdl``), no route joining two nets; ``shorts`` the nets the next
    routes join, one entry a route."""
    shorts: list[dict] = []

    def inputs(block, out, pdk, design, params, seconds=None):
        (seconds if seconds is not None else {}).update(netlist=0.2, floorplan=0.1)
        return out / "align" / "input" / design, [], out / "netlist" / f"{design}.cdl", True

    monkeypatch.setattr(step, "inputs", inputs)
    monkeypatch.setattr(step, "pdk_router", lambda pdk: "astar")
    monkeypatch.setattr(step, "route_shorts", lambda work, name: shorts.pop(0) if shorts else {})
    monkeypatch.setattr(step, "annealed", lambda work: True)
    return shorts


def test_align_lays_out_the_design_and_gives_what_the_signoff_takes(tmp_path: Path, monkeypatch, aligned) -> None:
    """The GDS, its size, its LVS netlist, ALIGN's netlist, the router and each part's seconds."""
    monkeypatch.setattr(
        step, "build_design", lambda pdk, design, cells, out, placed, seed=0, router=None: _gds(out / "inv" / "inv.gds")
    )
    laid = step.lay_out_align("inv", "tsmc65", None, tmp_path)
    parts, tool = laid.pop("parts"), laid.pop("tool")
    assert laid == {
        "gds": str(tmp_path / "align" / "inv" / "inv.gds"),
        "source": str(tmp_path / "netlist" / "inv.cdl"),
        "netlist": str(tmp_path / "netlist" / "inv.sp"),
        "cell_um": [2.0, 1.0],
        "router": "astar",
        "placed": True,
        "route_shorts": None,
    }
    # its parts under the names every layout flow shares, in order; ALIGN has no clock tree
    assert list(parts) == list(step.PARTS) and parts["cts"] is None and tool["name"] == "align"


def test_a_layout_the_first_router_cannot_draw_is_drawn_by_the_other(tmp_path: Path, monkeypatch, aligned) -> None:
    """Where ALIGN fails (or stops) with the PDK's router, the other router lays the design out
    (``align_<router>/``); where both fail, the first router's failure is the step's."""

    def build(pdk, design, cells, out, placed, seed=0, router=None):
        if router == "astar":
            raise RuntimeError("ALIGN stopped after 1800 s")
        return _gds(out / "inv" / "inv.gds")

    monkeypatch.setattr(step, "build_design", build)
    laid = step.lay_out_align("inv", "tsmc65", None, tmp_path / "run")
    assert laid["router"] == "hanan" and laid["gds"] == str(tmp_path / "run" / "align_hanan" / "inv" / "inv.gds")

    def neither(pdk, design, cells, out, placed, seed=0, router=None):
        raise RuntimeError(f"{router} gave up")

    monkeypatch.setattr(step, "build_design", neither)
    with pytest.raises(RuntimeError, match="astar gave up"):
        step.lay_out_align("inv", "tsmc65", None, tmp_path / "none")


def test_a_route_joining_two_nets_is_routed_again_with_another_seed(tmp_path: Path, monkeypatch, aligned) -> None:
    """ALIGN's route joining two nets, where its placer annealed: placed and routed again, its
    placer's seed the next, three times at most; the joins of the last route kept."""
    seeds = []

    def build(pdk, design, cells, out, placed, seed=0, router=None):
        seeds.append(seed)
        return _gds(out / "inv" / "inv.gds")

    monkeypatch.setattr(step, "build_design", build)
    aligned.extend([{("a", "b"): 2}, {}])
    assert step.lay_out_align("inv", "tsmc65", None, tmp_path / "once")["route_shorts"] is None
    assert seeds == [0, 1]
    seeds.clear()
    aligned.extend([{("a", "b"): 2}] * 3)
    assert step.lay_out_align("inv", "tsmc65", None, tmp_path / "thrice")["route_shorts"] == {"a/b": 2}
    assert seeds == [0, 1, 2]


def test_the_extraction_records_the_engine_that_ran(tmp_path: Path, monkeypatch) -> None:
    """The pex step's output names KLayout-PEX's engine (``engine``, ``extractor``): FasterCap at its
    tolerance by default, the 2.5-D engine where asked; the extraction is given it."""
    from flow.layout import signoff
    from flow.layout.kpex import Engine

    given: list = []

    def run_layout_pex(pdk, gds, top, name, run_dir, tolerance=None, texts=(), engine=Engine.FASTERCAP):
        given.append(engine)
        netlist = run_dir / "kpex" / f"{name}.pex.netlist"
        netlist.parent.mkdir(parents=True, exist_ok=True)
        netlist.write_text("c_0 ( a 0 ) capacitor c=2f\nc_1 ( a b ) capacitor c=0.5f\n")
        return netlist

    monkeypatch.setattr(signoff, "run_layout_pex", run_layout_pex)
    gds = _gds(tmp_path / "layout" / "toy.gds")
    default = step.extracted("tsmc65", gds, "toy", tmp_path / "fastercap")
    assert (default["engine"], default["extractor"]) == ("fastercap", "KLayout-PEX (FasterCap, 5%)")
    rcx25 = step.extracted("tsmc65", gds, "toy", tmp_path / "rcx25", engine=Engine.RCX25)
    assert (rcx25["engine"], rcx25["extractor"]) == ("rcx25", "KLayout-PEX (2.5-D)")
    assert given == [Engine.FASTERCAP, Engine.RCX25]
    assert rcx25["nets"] == {"a": pytest.approx(2.5e-15), "b": pytest.approx(0.5e-15)} and rcx25["capacitors"] == 2
