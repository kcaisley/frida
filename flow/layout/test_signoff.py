"""Tests for technology-dispatched signoff."""

from pathlib import Path
from types import SimpleNamespace

import pytest

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
