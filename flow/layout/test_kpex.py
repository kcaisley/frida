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
