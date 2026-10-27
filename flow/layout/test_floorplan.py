"""Tests for a floorplan's ALIGN groups."""

import pytest

from .pdkproc import ROOT, in_pdk

# ---- groups: checked by the row-cell engine (stems/netcells.py), in a process bound to a PDK

PDK = next((p.parts[-3] for p in sorted(ROOT.glob("pdk/*/layout/tech.py"))), None)
needs_pdk = pytest.mark.skipif(PDK is None, reason="no PDK submodule checked out")
ROWS = {"rows": [["Ma", "Mb"], ["Mc_a", "Md_a"], ["Mc_b", "Md_b"]], "split": {"Mc": 2, "Md": 2}}


def _check(groups: dict[str, list[str]]) -> None:
    in_pdk(PDK, "netcells", "check_groups", {**ROWS, "groups": groups}, {"Ma", "Mb", "Mc", "Md"})


@needs_pdk
def test_groups_in_one_row_or_in_the_same_split_rows_are_valid() -> None:
    _check({"DP_NMOS_0": ["Ma", "Mb"], "CCP_PMOS_0": ["Mc", "Md"]})
    _check({})
    in_pdk(PDK, "netcells", "check_groups", ROWS, {"Ma", "Mb", "Mc", "Md"})  # no groups at all


@needs_pdk
@pytest.mark.parametrize(
    ("groups", "message"),
    [
        ({"DP_NMOS_0": ["Ma", "Mz"]}, "Mz is not in the netlist"),
        ({"DP_NMOS_0": ["Ma", "Mb"], "NMOS_S_0": ["Mb"]}, "Mb is in groups DP_NMOS_0 and NMOS_S_0"),
        ({"DP_NMOS_0": ["Ma", "Mc"]}, "split into different numbers of parts"),
        ({"DP_NMOS_0": ["Mb", "Ma"], "CMC_PMOS_0": ["Mc", "Ma"]}, "Ma is in groups"),
    ],
)
def test_invalid_groups_are_rejected(groups: dict[str, list[str]], message: str) -> None:
    with pytest.raises(ValueError, match=message):
        _check(groups)


@needs_pdk
def test_group_across_rows_is_rejected() -> None:
    rows = {"rows": [["Ma"], ["Mb"]], "groups": {"DP_NMOS_0": ["Ma", "Mb"]}}
    with pytest.raises(ValueError, match="Ma, Mb are not placed in one row"):
        in_pdk(PDK, "netcells", "check_groups", rows, {"Ma", "Mb"})
