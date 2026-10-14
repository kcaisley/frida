"""Tests for running layout steps in processes bound to one PDK each."""

import sys

import pytest

from .pdkproc import ROOT, pdk_value

PDKS = [p.parts[-3] for p in sorted(ROOT.glob("pdk/*/layout/tech.py"))]


@pytest.mark.skipif(len(PDKS) < 2, reason="needs two PDK submodules")
def test_each_pdk_gets_its_own_tech_in_one_test_process() -> None:
    first, second = PDKS[:2]
    for pdk in (first, second, first):
        assert pdk_value(pdk, "tech", "__file__") == str(ROOT / "pdk" / pdk / "layout" / "tech.py")
        assert pdk_value(pdk, "rowcell", "__file__") == str(ROOT / "flow" / "layout" / "stems" / "rowcell.py")
    assert "tech" not in sys.modules  # the test process itself stays unbound


def test_missing_pdk_is_reported() -> None:
    with pytest.raises(FileNotFoundError, match="pdk/nopdk/layout/tech.py is missing"):
        pdk_value("nopdk", "tech", "H")
