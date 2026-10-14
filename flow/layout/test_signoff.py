"""Tests for technology-dispatched signoff."""

from pathlib import Path
from types import SimpleNamespace

import pytest

from . import signoff
from .signoff import SignoffParams, run_signoff


def test_signoff_dispatches_all_stages(tmp_path: Path, monkeypatch) -> None:
    gds = tmp_path / "layout.gds"
    source = tmp_path / "source.cdl"
    gds.touch()
    source.touch()
    calls: list[str] = []

    def drc(**kwargs):
        calls.append("drc")
        path = kwargs["run_dir"] / "drc.report"
        path.write_text("clean", encoding="utf-8")
        return path

    def lvs(**kwargs):
        calls.append("lvs")
        path = kwargs["run_dir"] / "lvs.report"
        path.write_text("CORRECT", encoding="utf-8")
        return True, path

    def pex(**kwargs):
        calls.append("pex")
        path = kwargs["run_dir"] / "pex.netlist"
        path.write_text("", encoding="utf-8")
        return path

    monkeypatch.setattr(
        "flow.layout.signoff.import_module",
        lambda _name: SimpleNamespace(run_drc=drc, run_lvs=lvs, run_pex=pex),
    )
    result = run_signoff(
        SignoffParams("synthetic", gds, "TOP", source, "TOP", "top"),
        tmp_path / "run",
    )
    assert calls == ["drc", "lvs", "pex"]
    assert result.lvs_correct
    assert result.pex_netlist.name == "pex.netlist"


def test_incorrect_lvs_prevents_pex_after_block_assembly(tmp_path, monkeypatch):
    gds, source, report = (tmp_path / name for name in ("layout.gds", "source.cdl", "lvs.report"))
    gds.touch()
    source.touch()
    report.write_text("INCORRECT: disconnected plate")
    extracted = []
    monkeypatch.setattr(
        "flow.layout.signoff.import_module",
        lambda _name: SimpleNamespace(
            run_drc=lambda **_kwargs: tmp_path / "drc.report",
            run_lvs=lambda **_kwargs: (False, report),
            run_pex=lambda **_kwargs: extracted.append(True),
        ),
    )
    with pytest.raises(RuntimeError, match="LVS was expected to be correct"):
        run_signoff(SignoffParams("synthetic", gds, "ADC", source, "ADC", "adc"), tmp_path / "run")
    assert not extracted


def test_post_devices_join_the_source_top(tmp_path, monkeypatch) -> None:
    source, extra = tmp_path / "source.cdl", tmp_path / "x.gds.extra.sp"
    source.write_text(
        ".subckt cell a b\nM1 a b vss vss nch w=1u l=1u\n.ends cell\n"
        ".subckt top in out vdd vss\nX1 in out cell\nMa out in vss vss nch w=1u l=1u\n.ends top\n"
    )
    extra.write_text(
        "* added by align/post.py (decap fill, ring)\n*.DNW\n*.PORTS vsub\nMdecap vdd vss vdd vdd pch w=2u l=1u\n"
    )
    models = []
    monkeypatch.setattr(
        signoff, "pdk_value", lambda pdk, module, name, default: models.append(pdk) or {"nch": "nch_dnw"}
    )
    signoff.add_post_devices("tsmc65", source, extra, "TOP")
    assert source.read_text().splitlines() == [
        ".subckt cell a b",
        "M1 a b vss vss nch_dnw w=1u l=1u",
        ".ends cell",
        ".subckt top in out vdd vss vsub",
        "X1 in out cell",
        "Ma out in vss vss nch_dnw w=1u l=1u",
        "Mdecap vdd vss vdd vdd pch w=2u l=1u",
        ".ends top",
    ]
    assert models == ["tsmc65"]


def test_post_devices_without_deep_nwell_keep_the_models(tmp_path, monkeypatch) -> None:
    source, extra = tmp_path / "source.cdl", tmp_path / "x.gds.extra.sp"
    source.write_text(".subckt top a vss\nMa a a vss vss nch w=1u l=1u\n.ends top\n")
    extra.write_text("* added by align/post.py (plain fill)\n")
    monkeypatch.setattr(signoff, "pdk_value", lambda *_args: pytest.fail("no deep N-well, no model lookup"))
    signoff.add_post_devices("tsmc65", source, extra, "top")
    assert source.read_text() == ".subckt top a vss\nMa a a vss vss nch w=1u l=1u\n.ends top\n"


def test_provider_without_extraction_still_signs_off_drc_and_lvs(tmp_path, monkeypatch) -> None:
    gds, source = tmp_path / "layout.gds", tmp_path / "source.cdl"
    gds.touch()
    source.touch()
    report = tmp_path / "lvs.report"
    report.write_text("CORRECT")
    provider = SimpleNamespace(
        run_drc=lambda **_kwargs: tmp_path / "drc.json", run_lvs=lambda **_kwargs: (True, report)
    )
    monkeypatch.setattr("flow.layout.signoff.import_module", lambda _name: provider)
    params = SignoffParams("synthetic", gds, "TOP", source, "TOP", "top")
    assert signoff.run_lvs(params, tmp_path / "run") == (True, report)
    with pytest.raises(TypeError, match="has no extraction"):
        signoff.run_pex(params, tmp_path / "run")
