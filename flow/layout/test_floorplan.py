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
    )
    assert fp["rows"] == [["Me", "Mf", "Mg"], ["Ma", "Mb", "Md", "Mc"]]  # 5.0 x 3.6 um
    assert fp["split"] == {}


def _cells(names: list[str], width: int) -> list[tuple[str, int]]:
    return [(name, width) for name in names]


def test_rows_pack_toward_a_square_mirrored_about_the_centre() -> None:
    pairs = [(_cells(pair, 1000), False) for pair in (["Ma", "Mb"], ["Mc", "Md"], ["Me", "Mf"], ["Mg", "Mh"])]
    rows = pack_rows([*pairs, (_cells(["Xa"], 800), True), (_cells(["Xb"], 800), True)], H)
    # 6.0 x 7.2 um: the standard cells split for an even number of rows
    assert rows == [["Me", "Mc", "Ma", "Mb", "Md", "Mf"], ["Mg", "Mh"], ["Xa"], ["Xb"]]


def test_rows_merge_with_their_own_kind_only() -> None:
    rows = pack_rows(
        [(_cells(["Ma", "Mb"], 1000), False), (_cells(["Xa"], 800), True), (_cells(["Mc", "Md"], 1000), False)], H
    )
    assert rows == [["Mc", "Ma", "Mb", "Md"], ["Xa"]]


def test_a_wide_row_of_standard_cells_takes_several_rows() -> None:
    std = (_cells([f"X{k}" for k in range(8)], 1000), True)
    rows = pack_rows([(_cells(["Ma", "Mb"], 1000), False), std], H)
    # 4.0 x 7.2 um: in halves, and the first half in two again for an even number of rows
    assert rows == [["Ma", "Mb"], ["X0", "X1"], ["X2", "X3"], ["X4", "X5", "X6", "X7"]]


def test_centred_standard_cells_go_where_their_nets_are_shortest() -> None:
    """A comparator's output stage as ALIGN places it: the latch gates mirrored, the four output
    inverters self-symmetric on the axis, one per row; nested, they would all end on the right."""

    nets = {
        "Xsr_n": frozenset({"sr_p", "decision_p", "sr_n"}),
        "Xsr_p": frozenset({"sr_n", "decision_n", "sr_p"}),
        "Xdec_p": frozenset({"latch_n", "decision_p"}),
        "Xdec_n": frozenset({"latch_p", "decision_n"}),
        "Xbuf1_n": frozenset({"sr_n", "outn_b"}),
        "Xbuf2_n": frozenset({"outn_b", "outn"}),
        "Xbuf1_p": frozenset({"sr_p", "outp_b"}),
        "Xbuf2_p": frozenset({"outp_b", "outp"}),
    }
    std = [["Xdec_p", "Xdec_n"], ["Xsr_n", "Xsr_p"], ["Xbuf1_n"], ["Xbuf2_n"], ["Xbuf1_p"], ["Xbuf2_p"]]
    rows = [(_cells(["Ma", "Mb"], 8000), False), *((_cells(row, 1000), True) for row in std)]
    assert pack_rows(rows, H)[1] == ["Xsr_n", "Xdec_p", "Xdec_n", "Xsr_p", "Xbuf1_n", "Xbuf2_n", "Xbuf1_p", "Xbuf2_p"]
    assert pack_rows(rows, H, nets)[1] == [
        *("Xbuf2_n", "Xbuf1_n", "Xsr_n", "Xdec_p"),
        *("Xdec_n", "Xsr_p", "Xbuf1_p", "Xbuf2_p"),
    ]


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
    placement = _placement(
        ("X_MA_MB", "PAIR", 0, 3 * H, 1, 1),
        ("X_MC_MD", "PAIR", 0, 2 * H, 1, 1),
        ("X_ME_MF", "PAIR", 0, H, 1, 1),
        ("X_MG", "ONE", 0, 0, 1, 1),
    )
    pack = lambda widths: placement_to_floorplan(
        placement, GROUPS, DEVICES, H, escape={}, netlist="n.sp", widths=widths
    )["rows"]
    assert pack(None) == [["Mc", "Ma", "Mb", "Md"], ["Me", "Mf", "Mg"]]  # ALIGN's widths: 4.0 x 3.6 um
    wide = dict.fromkeys(["Ma", "Mb", "Mc", "Md", "Me", "Mf", "Mg"], 2000)
    assert pack(wide) == [["Ma", "Mb"], ["Mc", "Md"], ["Me", "Mf"], ["Mg"]]  # 4.0 x 7.2 beats 8.0 x 3.6
