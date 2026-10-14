"""Tests for the floorplan from ALIGN's placement, and for a floorplan's ALIGN groups."""

import pytest

from .floorplan import pack_rows, placement_to_floorplan
from .pdkproc import ROOT, in_pdk

H = 1800
LEAVES = {
    "PAIR": (2000, H),
    "PAIR_Y2": (6000, 2 * H),
    "PAIR_Y2_NARROW": (2000, 2 * H),
    "ONE": (1000, H),
    "INVD1": (800, H),
}
GROUPS = {
    "X_MA_MB": ("DP_NMOS", ["MA", "MB"]),
    "X_MC_MD": ("DP_NMOS", ["MC", "MD"]),
    "X_ME_MF": ("CCP_PMOS", ["ME", "MF"]),
    "X_MG": ("NMOS_S", ["MG"]),
}
DEVICES = ["Ma", "Mb", "Mc", "Md", "Me", "Mf", "Mg", "Xinv"]


def _placement(*instances: tuple[str, str, int, int, int, int]) -> dict:
    """ALIGN's placement: (instance, leaf, oX, oY, sX, sY) each."""

    return {
        "modules": [
            {
                "instances": [
                    {
                        "instance_name": name,
                        "concrete_template_name": leaf,
                        "transformation": {"oX": x, "oY": y, "sX": sx, "sY": sy},
                    }
                    for name, leaf, x, y, sx, sy in instances
                ]
            }
        ],
        "leaves": [{"concrete_name": leaf, "bbox": [0, 0, w, h]} for leaf, (w, h) in LEAVES.items()],
    }


def _floorplan(*instances: tuple[str, str, int, int, int, int]) -> dict:
    return placement_to_floorplan(
        _placement(*instances), GROUPS, DEVICES, H, escape={"up": [], "down": []}, netlist="n.sp"
    )


def test_rows_from_single_pair_flipped_pair_folded_pair_and_standard_cell() -> None:
    fp = _floorplan(
        ("X_MA_MB", "PAIR", 0, 0, 1, 1),  # a pair: A left of B
        ("X_MC_MD", "PAIR", 4000, 0, -1, 1),  # mirrored about its right edge: B left of A
        ("X_ME_MF", "PAIR_Y2", 0, H, 1, 1),  # folded over rows 1 and 2, too wide to pack
        ("X_MG", "ONE", 3000, 2 * H, 1, -1),  # one device, flipped about its top edge into row 1
        ("XINV", "INVD1", 5000, 0, 1, 1),  # a standard cell among the transistors of row 0
    )
    assert fp["rows"] == [["Me_a", "Mf_a"], ["Me_b", "Mf_b", "Mg"], ["Ma", "Mb", "Md", "Mc"], ["Xinv"]]
    assert fp["split"] == {"Me": 2, "Mf": 2}
    assert fp["groups"] == {
        "CCP_PMOS_0": ["Me", "Mf"],
        "DP_NMOS_0": ["Ma", "Mb"],
        "DP_NMOS_1": ["Mc", "Md"],
        "NMOS_S_0": ["Mg"],
    }
    assert fp["netlist"] == "n.sp"
    assert fp["symmetric"] is False  # ALIGN keeps the rows' order without mirror pairs


def test_a_fold_whose_parts_share_a_packed_row_is_whole_again() -> None:
    fp = _floorplan(
        ("X_MA_MB", "PAIR", 0, 0, 1, 1),
        ("X_MC_MD", "PAIR", 4000, 0, -1, 1),
        ("X_ME_MF", "PAIR_Y2_NARROW", 0, H, 1, 1),
        ("X_MG", "ONE", 3000, 2 * H, 1, -1),
        ("XINV", "INVD1", 5000, 0, 1, 1),
    )
    assert fp["rows"] == [["Me", "Mf", "Mg"], ["Ma", "Mb", "Md", "Mc"], ["Xinv"]]  # 5.0 x 5.4 um
    assert fp["split"] == {}


def test_rows_pack_toward_a_square_mirrored_about_the_centre() -> None:
    pairs = [
        (["Ma", "Mb"], 2000, False),
        (["Mc", "Md"], 2000, False),
        (["Me", "Mf"], 2000, False),
        (["Mg", "Mh"], 2000, False),
    ]
    rows = pack_rows([*pairs, (["Xa"], 800, True), (["Xb"], 800, True)], H)
    assert rows == [["Mc", "Ma", "Mb", "Md"], ["Mg", "Me", "Mf", "Mh"], ["Xa", "Xb"]]  # 4.0 x 5.4 um


def test_rows_merge_with_their_own_kind_only() -> None:
    rows = pack_rows([(["Ma", "Mb"], 2000, False), (["Xa"], 800, True), (["Mc", "Md"], 2000, False)], H)
    assert rows == [["Mc", "Ma", "Mb", "Md"], ["Xa"]]


def test_rows_are_ordered_top_first_and_left_to_right() -> None:
    fp = _floorplan(
        ("X_MG", "ONE", 0, 2 * H, 1, 1), ("X_MC_MD", "PAIR", 3000, 0, 1, 1), ("X_MA_MB", "PAIR", 0, 0, 1, 1)
    )
    assert fp["rows"] == [["Mg"], ["Ma", "Mb", "Mc", "Md"]]  # merged, 5.0 x 1.8 um, is no square


def test_placement_off_the_rows_is_rejected() -> None:
    with pytest.raises(ValueError, match="off the 1800 nm rows"):
        _floorplan(("X_MG", "ONE", 0, 900, 1, 1))


def test_instance_outside_the_netlist_is_rejected() -> None:
    with pytest.raises(ValueError, match="XNAND not in the netlist"):
        _floorplan(("XNAND", "INVD1", 0, 0, 1, 1))


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


def test_rows_pack_by_the_row_cells_widths_where_given() -> None:
    placement = _placement(("X_MA_MB", "PAIR", 0, H, 1, 1), ("X_MG", "ONE", 0, 0, 1, 1))
    pack = lambda widths: placement_to_floorplan(
        placement, GROUPS, DEVICES, H, escape={}, netlist="n.sp", widths=widths
    )["rows"]
    assert pack(None) == [["Ma", "Mb", "Mg"]]  # ALIGN's widths: 3.0 x 1.8 um beats 2.0 x 3.6
    assert pack({"Ma": 4000, "Mb": 4000, "Mg": 1000}) == [["Ma", "Mb"], ["Mg"]]  # 8.0 x 3.6 beats 9.0 x 1.8
