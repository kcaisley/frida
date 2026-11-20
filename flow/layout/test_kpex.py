"""The KLayout-PEX extractor's own pieces that need no PDK: a kit's stack read from its ICT file, and
the permittivity of the dielectrics between two heights."""

from pathlib import Path

import pytest

from flow.layout import kpex

ICT = """
dielectric "field" {
        height              0
        thickness           0.4
        dielectric_constant 4.0
}
conductor "poly" {
        height              0.4
        thickness           0.2
}
dielectric "low" {
        thickness           0.6
        dielectric_constant 3.0
}
conductor "m1" {
        thickness           0.3
}
dielectric "cap" {
        conformal           TRUE
        thickness           0.05
        dielectric_constant 7.0
}
dielectric "high" {
        thickness           0.5
        dielectric_constant 6.0
}
conductor "m2" {
        delta_height        0.2
        delta_layer         m1
        thickness           0.4
}
"""


def test_a_kits_stack_places_each_conductor(tmp_path: Path) -> None:
    """A height where the file gives one; else a dielectric stacks on the planar ones before it, a
    conductor sits in the last of them, its top at theirs; or its ``delta_height`` above its
    ``delta_layer``. A conformal film is left out."""
    path = tmp_path / "stack.ict"
    path.write_text(ICT)
    stack = kpex.stack_from_ict(path, {"PO": "poly", "M1": "m1", "M2": "m2"})
    assert stack["conductors"] == {
        "PO": {"z": 0.4, "thickness": 0.2},
        "M1": {"z": 0.7, "thickness": 0.3},  # the top of "low", 1.0, less its thickness
        "M2": {"z": 1.2, "thickness": 0.4},  # 0.2 above m1's top
    }
    assert stack["dielectrics"] == [(0.0, 0.4, 4.0), (0.4, 1.0, 3.0), (1.0, 1.5, 6.0)]


def test_the_dielectrics_between_two_heights_are_in_series_across_and_in_parallel_along() -> None:
    slabs = [[0.0, 1.0, 2.0], [1.0, 2.0, 4.0]]
    assert kpex._k(slabs, 0.0, 2.0) == pytest.approx(2 / (1 / 2.0 + 1 / 4.0))
    assert kpex._k(slabs, 0.5, 1.0) == pytest.approx(2.0)
    # along them (a lateral field): their mean by thickness
    assert kpex._k(slabs, 0.0, 2.0, along=True) == pytest.approx(3.0)
    # beyond every slab: the nearest one's
    assert kpex._k(slabs, 3.0, 4.0) == pytest.approx(4.0)


@pytest.fixture
def kit(tmp_path: Path, monkeypatch):
    """A toy kit: its stack (poly and two metals) and its layout tech's layers; ``folder`` its
    ``kpex/``, where a 2.5-D coefficient table goes."""
    import json
    import sys
    from types import SimpleNamespace

    folder = tmp_path / "pdk" / "toykit" / "kpex"
    folder.mkdir(parents=True)
    conductors = {
        "PO": {"z": 0.3, "thickness": 0.1},
        "M1": {"z": 0.6, "thickness": 0.2},
        "M2": {"z": 1.0, "thickness": 0.2},
    }
    (folder / "stack.json").write_text(json.dumps({"conductors": conductors, "dielectrics": [[0.0, 2.0, 4.0]]}))
    tech = SimpleNamespace(LAYERS={"PO": (1, 0), "M1": (2, 0), "V1": (3, 0), "M2": (4, 0)}, RULES={})
    monkeypatch.setattr(kpex, "ROOT", tmp_path)
    monkeypatch.setitem(sys.modules, "pdk.toykit.layout.tech", tech)
    return folder


def test_a_kits_2_5d_coefficients_join_its_technology(kit: Path) -> None:
    """kpex's technology carries the kit's 2.5-D coefficients (``parasitics.json``, kpex's
    ``process_parasitics``) where the kit has them, and none where it has not."""
    import json

    assert "process_parasitics" not in kpex.technology("toykit")[0]
    table = {"side_halo": 8.0, "capacitance": {"substrates": [], "overlaps": [], "sidewalls": [], "sideoverlaps": []}}
    (kit / "parasitics.json").write_text(json.dumps(table))
    assert kpex.technology("toykit")[0]["process_parasitics"] == table


def test_the_extraction_runs_the_engine_it_is_given(kit: Path, tmp_path: Path, monkeypatch) -> None:
    """The spec kpex's Python reads names the engine (FasterCap by default); the 2.5-D engine is
    refused in a kit without its coefficients, before anything runs."""
    import json

    specs: list[dict] = []

    def run(command, **kwargs):
        spec = json.loads(Path(command[-1]).read_text())
        specs.append(spec)
        Path(spec["netlist"]).write_text("simulator lang=spectre\n")
        return ""

    monkeypatch.setattr(kpex, "run_logged", run)
    gds = tmp_path / "toy.gds"
    gds.write_bytes(b"")
    with pytest.raises(ValueError, match="no 2.5-D coefficients"):
        kpex.run_layout_pex("toykit", gds, "TOY", "toy", tmp_path / "none", engine=kpex.Engine.RCX25)
    assert not specs and not (tmp_path / "none").exists()
    kpex.run_layout_pex("toykit", gds, "TOY", "toy", tmp_path / "default")
    (kit / "parasitics.json").write_text(json.dumps({"side_halo": 8.0}))
    netlist = kpex.run_layout_pex("toykit", gds, "TOY", "toy", tmp_path / "rcx25", engine=kpex.Engine.RCX25)
    assert [spec["engine"] for spec in specs] == ["fastercap", "rcx25"]
    assert netlist == (tmp_path / "rcx25" / "kpex" / "toy.pex.netlist").resolve()
    assert (
        json.loads((tmp_path / "rcx25" / "kpex" / "tech.pb.json").read_text())["process_parasitics"]["side_halo"] == 8.0
    )


def test_the_2_5d_fit_recovers_its_forms() -> None:
    """The coefficients' fit (``flow.layout.kpex_coefficients``): an area capacitance is its slabs'
    in series, and the sidewall fit recovers K and o of c = K / (s + o), with no offset where the
    fit's pole would fall among the spaces."""
    import numpy as np

    from flow.layout import kpex_coefficients as fit

    stack = [(0.0, 1.0, 4.0), (1.0, 2.0, 2.0)]
    assert fit.area_f(stack, 0.0, 2.0) == pytest.approx(fit.EPS0 / (1 / 4 + 1 / 2))
    assert fit.area_f(stack, 0.5, 1.0) == pytest.approx(fit.EPS0 * 4 / 0.5)
    spaces = np.array([0.1, 0.14, 0.2, 0.3, 0.5])
    assert fit.sidewall_fit(spaces, 20.0 / (spaces + 0.05), 0.1) == pytest.approx((20.0, 0.05))
    k, o = fit.sidewall_fit(spaces, np.array([1.0, 50.0, 30.0, 20.0, 10.0]), 0.1)
    assert o == 0.0 and k > 0


def _toy_parasitics() -> dict:
    """A 2.5-D coefficient table for the toy kit's poly and two metals: every conductor's own and
    every pair's, round numbers."""
    names = ("PO", "M1", "M2")
    return {
        "side_halo": 8.0,
        "capacitance": {
            "substrates": [{"layer_name": n, "area_capacitance": 10.0, "perimeter_capacitance": 10.0} for n in names],
            "overlaps": [
                {"top_layer_name": top, "bottom_layer_name": bottom, "capacitance": 20.0}
                for i, bottom in enumerate(names)
                for top in names[i + 1 :]
            ],
            "sidewalls": [{"layer_name": n, "capacitance": 40.0, "offset": 0.0} for n in names],
            "sideoverlaps": [
                {"in_layer_name": a, "out_layer_name": b, "capacitance": 5.0} for a in names for b in names if a != b
            ],
        },
        "resistance": {},
    }


@pytest.mark.skipif(not (kpex.KPEX_HOME / "bin" / "python").is_file(), reason="KLayout-PEX's own Python is not here")
def test_a_sidewall_ends_at_its_edges_own_polygon(kit: Path, tmp_path: Path) -> None:
    """The 2.5-D engine's sidewall from an edge stops at the edge's own polygon: a comb's far wall
    shields a wire beyond it from the comb's near wall, so the comb and its far wall alone couple to
    the wire alike (kpex 0.6.12 took the nearest polygon of another net however far,
    ``flow.layout.kpex_extract``)."""
    import json

    from klayout import db

    from flow.layout.annotate import capacitors

    (kit / "parasitics.json").write_text(json.dumps(_toy_parasitics()))

    def coupling(walls: list[tuple[int, int, int, int]], name: str) -> float:
        layout = db.Layout()
        layout.dbu = 0.001
        top = layout.create_cell("TOY")
        m1 = layout.layer(2, 0)
        region = db.Region()
        for box in walls:
            region.insert(db.Box(*box))
        top.shapes(m1).insert(region.merged())
        top.shapes(m1).insert(db.Box(1000, 0, 1100, 5000))
        top.shapes(m1).insert(db.Text("A", db.Trans(550, 2500)))
        top.shapes(m1).insert(db.Text("B", db.Trans(1050, 2500)))
        gds = tmp_path / f"{name}.gds"
        layout.write(str(gds))
        netlist = kpex.run_layout_pex("toykit", gds, "TOY", name, tmp_path / name, engine=kpex.Engine.RCX25)
        return sum(c for a, b, c in capacitors(netlist) if {a, b} == {"A", "B"}) * 1e15  # fF

    comb = coupling([(0, 0, 100, 5000), (500, 0, 600, 5000), (0, 0, 600, 100)], "comb")
    wall = coupling([(500, 0, 600, 5000)], "wall")
    assert wall > 0
    assert comb == pytest.approx(wall, rel=0.02)


def test_the_calibration_scales_each_mom_metals_sidewall_to_fastercaps_slope() -> None:
    """``flow.layout.kpex_coefficients``'s 3-D stage: a strip's coupling by coefficient sums by
    terminal pair (and by a metal's sidewalls alone); its slope over the finger's length leaves the
    ends out; the fewest metals' count sets its metals' scale and a count of more metals the rest,
    so each count's slope comes out FasterCap's; the table scales only those metals' sidewalls."""
    from flow.layout import kpex_coefficients as fit

    parts = [
        ["sidewall", "M3", "M3", "MAIN", "TOP", 1.0],
        ["sidewall", "M4", "M4", "MAIN", "TOP", 2.0],
        ["sideoverlap", "M3", "M2", "MAIN", "TOP", 0.5],
        ["sidewall", "M4", "M4", "DIFF", "TOP", 4.0],
    ]
    assert fit.coupling(parts, ("TOP", "MAIN")) == pytest.approx(3.5)
    assert fit.coupling(parts, ("MAIN", "TOP"), {"M4"}) == pytest.approx(2.0)
    assert fit.slope([2.0, 4.0, 8.0], [1.5, 2.5, 4.5]) == pytest.approx((0.5, 0.5))
    # one metal (M4) alone: FasterCap's 0.9 of its 1.0, the rest 0.0; then both: M3 takes the rest
    slopes = {1: [(0.9, {"M4": 1.0, "M3": 0.0}, 0.0)], 2: [(2.0, {"M4": 1.0, "M3": 1.2}, 0.2)]}
    scales = fit.nested_fit(slopes)
    assert scales == pytest.approx({"M4": 0.9, "M3": (2.0 - 0.2 - 0.9) / 1.2})
    for [(fastercap, sidewalls, rest)] in slopes.values():
        assert sum(scales[m] * s for m, s in sidewalls.items()) + rest == pytest.approx(fastercap)
    # several values: their errors relative to FasterCap's least squares
    (length,) = fit.nested_fit({1: [(1.1, {"M4": 1.0}, 0.0), (1.8, {"M4": 2.0}, 0.0)]}).values()
    assert length == pytest.approx((1.1 / 1.1**2 + 1.8 * 2 / 1.8**2) / (1 / 1.1**2 + 4 / 1.8**2))
    table = _toy_parasitics()
    out = fit.scaled(table, {"M1": 0.5})
    assert [e["capacitance"] for e in out["capacitance"]["sidewalls"]] == [40.0, 20.0, 40.0]
    assert table["capacitance"]["sidewalls"][1]["capacitance"] == 40.0  # its own left as it was


def test_a_tables_own_keys_stay_out_of_kpexs_technology(kit: Path) -> None:
    """A coefficient table's provenance and line ends (``kpex_coefficients``'s) are frida's, not
    kpex's: the technology leaves them out, from the kit's file or a table given in its place, and
    the line ends go to the extraction's own step (``kpex_extract.line_ends``)."""
    import json

    table = {**_toy_parasitics(), "provenance": {"method": "toy"}, "line_ends_um": {"M1": 0.3}}
    (kit / "parasitics.json").write_text(json.dumps(table))
    kept, joins = kpex.technology("toykit")
    assert not set(kpex.FRIDA_KEYS) & set(kept["process_parasitics"]) and joins["line_ends"] == {"M1": 0.3}
    given, joins = kpex.technology("toykit", {**table, "side_halo": 4.0, "line_ends_um": {}})
    assert given["process_parasitics"]["side_halo"] == 4.0 and "provenance" not in given["process_parasitics"]
    assert joins["line_ends"] == {}


@pytest.mark.skipif(not (kpex.KPEX_HOME / "bin" / "python").is_file(), reason="KLayout-PEX's own Python is not here")
def test_a_line_ends_fringe_continues_its_sides_past_the_tip(kit: Path, tmp_path: Path) -> None:
    """A wire's two ends in a comb (a finger between two walls, its bar below it): each of its four
    corners continues the side's sidewall the table's line end past the tip, to the wall it faces
    there (``flow.layout.kpex_extract.line_ends``), and adds it to the wire's coupling."""
    import json

    from klayout import db

    layout = db.Layout()
    layout.dbu = 0.001
    top = layout.create_cell("TOY")
    m1 = layout.layer(2, 0)
    comb = db.Region()
    for box in [(0, 0, 100, 5000), (500, 0, 600, 5000), (0, 0, 600, 100)]:
        comb.insert(db.Box(*box))
    top.shapes(m1).insert(comb.merged())
    top.shapes(m1).insert(db.Box(250, 500, 350, 4000))
    top.shapes(m1).insert(db.Text("A", db.Trans(550, 2500)))
    top.shapes(m1).insert(db.Text("B", db.Trans(300, 2500)))
    gds = tmp_path / "comb.gds"
    layout.write(str(gds))
    table = {**_toy_parasitics(), "line_ends_um": {"M1": 0.2}}
    parts = tmp_path / "parts.json"
    netlist = kpex.run_layout_pex(
        "toykit", gds, "TOY", "comb", tmp_path / "comb", engine=kpex.Engine.RCX25, parts=parts, parasitics=table
    )
    ends = [row for row in json.loads(parts.read_text()) if row[0] == "line_end"]
    # four corners, each 0.2 um of the 40 aF/um sidewall at the walls' 0.15 um, halved per pair
    assert ends == [["line_end", "M1", "M1", "A", "B", pytest.approx(4 * 0.2 * 40 / 0.15 / 2 / 1000)]]
    assert "( A B )" in netlist.read_text() or "( B A )" in netlist.read_text()
