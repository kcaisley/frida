"""Give frida-scc-2p0's board the outline of frida-scc-1p1 and the placement of the parts both have.

Run with KiCad's Python (its ``pcbnew`` module), after ``pcb layout`` has made the board:

    $KICAD_APPDIR/bin/python3.11 place_from_1p1.py

``SAME`` names, for each part of frida-scc-1p1, the part of frida-scc-2p0 that takes its place:
its position, rotation and side are copied. A two-pad part whose pads are wired the other way
round here is turned by 180 degrees, so that each pad stays on the net it was on. Parts with no
counterpart are moved as one block to the right of the outline, where they wait to be placed.
The ``pcb`` tool keeps all of this on its later runs: it places only parts that are new.

The script also checks the port: over every shared part, the nets of the two boards must
correspond one to one. It lists each net that does not.
"""

from pathlib import Path
from typing import Any

import pcbnew

HERE = Path(__file__).parent
OLD = HERE.parent / "frida-scc-1p1.kicad_pcb"
NEW = HERE / "eda" / "frida-scc-2p0.kicad_pcb"
STAGING_GAP_MM = 15.0  # between the outline's right edge and the parts not yet placed

# frida-scc-1p1 reference -> frida-scc-2p0 instance path
SAME = {
    # the chip, its clock terminations, decoupling and reset pull-up
    "U3": "ASIC.U_ASIC",
    "R10": "ASIC.R_TERM_COMP",
    "R11": "ASIC.R_TERM_SAMP",
    "R12": "ASIC.R_TERM_LOGIC",
    "R13": "ASIC.R_TERM_INIT",
    "R36": "ASIC.R_RST_PU",
    "C7": "ASIC.C_A_BULK",
    "C10": "ASIC.C_A_1U",
    "C13": "ASIC.C_A_100N_1",
    "C16": "ASIC.C_A_100N_2",
    "C8": "ASIC.C_D_BULK",
    "C11": "ASIC.C_D_1U",
    "C14": "ASIC.C_D_100N_1",
    "C17": "ASIC.C_D_100N_2",
    "C20": "ASIC.C_DAC_BULK",
    "C23": "ASIC.C_DAC_1U",
    "C26": "ASIC.C_DAC_100N_1",
    "C29": "ASIC.C_DAC_100N_2",
    "C19": "ASIC.C_IO_BULK",
    "C22": "ASIC.C_IO_1U",
    "C25": "ASIC.C_IO_100N_1",
    "C28": "ASIC.C_IO_100N_2",
    # the two cables to the FPGA board and the level shifter
    "J1": "LINK.J_DP",
    "J14": "LINK.J_CTRL",
    "U2": "LINK.U_SHIFT",
    "TH1": "LINK.TH_BOARD",
    "R1": "LINK.R_SHELL",
    "C1": "LINK.C_SHELL",
    "R33": "LINK.R_DIR2",
    "R34": "LINK.R_DIR1",
    "R35": "LINK.R_OE",
    "C31": "LINK.C_BDAQ_1U",
    "C32": "LINK.C_BDAQ_100N",
    "C33": "LINK.C_IO_100N",
    "C34": "LINK.C_IO_1U",
    # each clock leg's 1 kohm to ground is now its probe tap, on the same pads
    "R2": "TAP_COMP.R_P",
    "R3": "TAP_COMP.R_N",
    "R4": "TAP_LOGIC.R_P",
    "R5": "TAP_LOGIC.R_N",
    "R6": "TAP_SAMP.R_N",
    "R7": "TAP_SAMP.R_P",
    "R8": "TAP_INIT.R_N",
    "R9": "TAP_INIT.R_P",
    # the analog input
    "J3": "INPUT.J_INN",
    "J4": "INPUT.J_INP",
    "J8": "INPUT.J_VOCM_IN",
    "J5": "INPUT.J_SE",
    "J6": "INPUT.J_TERM",
    "J7": "INPUT.J_GAIN",
    "J9": "INPUT.J_VOCM",
    "J10": "INPUT.J_VIN",
    "U1": "INPUT.U_AMP",
    "Q1": "INPUT.Q_PD",
    "D1": "INPUT.D_CLAMP_N",
    "D2": "INPUT.D_CLAMP_P",
    "JP1": "INPUT.JP_CLAMP_N",
    "JP2": "INPUT.JP_CLAMP_P",
    "R14": "INPUT.R_SE",
    "R15": "INPUT.R_G_P_ALT",
    "R16": "INPUT.R_G_P",
    "R17": "INPUT.R_G_N",
    "R18": "INPUT.R_G_N_ALT",
    "R19": "INPUT.R_TERM_N",
    "R20": "INPUT.R_TERM_P",
    "R21": "INPUT.R_F_P",
    "R22": "INPUT.R_F_N",
    "R23": "INPUT.R_VOCM_TOP",
    "R24": "INPUT.R_VOCM_BOT",
    "R25": "INPUT.R_OUT_N",
    "R26": "INPUT.R_OUT_P",
    "R31": "INPUT.R_PD_PU",
    "R32": "INPUT.R_PD_PD",
    "C2": "INPUT.C_VOCM_1U",
    "C3": "INPUT.C_VOCM_100N",
    "C4": "INPUT.C_F_P",
    "C5": "INPUT.C_F_N",
    "C6": "INPUT.C_OUT",
    "C9": "INPUT.C_VS_P_BULK",
    "C12": "INPUT.C_VS_P_1U",
    "C15": "INPUT.C_VS_P_100N_1",
    "C18": "INPUT.C_VS_P_100N_2",
    "C21": "INPUT.C_VS_N_BULK",
    "C24": "INPUT.C_VS_N_1U",
    "C27": "INPUT.C_VS_N_100N_1",
    "C30": "INPUT.C_VS_N_100N_2",
    # power entry and mechanics
    "J12": "SUPPLIES.J_PWR",
    "FB3": "SUPPLIES.FB_P",
    "FB2": "SUPPLIES.FB_N",
    "H1": "H1",
    "H2": "H2",
    "H3": "H3",
    "H4": "H4",
}


def pad_nets(footprint: Any) -> dict[str, str]:
    """Return ``{pad number: net name}`` over a footprint's connected, numbered pads."""

    return {pad.GetNumber(): pad.GetNetname() for pad in footprint.Pads() if pad.GetNumber() and pad.GetNetname()}


def copy_outline(old: Any, new: Any) -> int:
    """Give the new board copies of the old board's Edge.Cuts drawings, unless it has an outline."""

    edges = [drawing for drawing in old.GetDrawings() if drawing.GetLayer() == pcbnew.Edge_Cuts]
    if any(drawing.GetLayer() == pcbnew.Edge_Cuts for drawing in new.GetDrawings()):
        return 0
    for drawing in edges:
        shape = pcbnew.PCB_SHAPE(new)
        shape.SetShape(drawing.GetShape())
        if drawing.GetShape() == pcbnew.SHAPE_T_ARC:
            shape.SetArcGeometry(drawing.GetStart(), drawing.GetArcMid(), drawing.GetEnd())
        else:
            shape.SetStart(drawing.GetStart())
            shape.SetEnd(drawing.GetEnd())
        shape.SetWidth(drawing.GetWidth())
        shape.SetLayer(pcbnew.Edge_Cuts)
        new.Add(shape)
    return len(edges)


def main() -> None:
    old = pcbnew.LoadBoard(str(OLD))
    new = pcbnew.LoadBoard(str(NEW))
    by_path = {fp.GetFieldText("Path").rsplit(".", 1)[0]: fp for fp in new.GetFootprints()}

    copied = copy_outline(old, new)
    print(f"outline: {copied} drawings copied" if copied else "outline: already there")

    # position, rotation and side
    pairs = []
    for reference, path in SAME.items():
        old_fp = old.FindFootprintByReference(reference)
        new_fp = by_path[path]
        if old_fp.IsFlipped() != new_fp.IsFlipped():
            new_fp.Flip(new_fp.GetPosition(), pcbnew.FLIP_DIRECTION_LEFT_RIGHT)
        new_fp.SetPosition(old_fp.GetPosition())
        new_fp.SetOrientation(old_fp.GetOrientation())
        pairs.append((reference, path, old_fp, new_fp))

    # the nets' correspondence, from the parts with three or more pads (their pads cannot be swapped)
    net_map: dict[str, str] = {}
    conflicts = set()
    for reference, path, old_fp, new_fp in pairs:
        old_nets, new_nets = pad_nets(old_fp), pad_nets(new_fp)
        if len(old_nets) < 3:
            continue
        for number, old_net in old_nets.items():
            new_net = new_nets.get(number)
            if new_net is None:
                continue
            if net_map.setdefault(old_net, new_net) != new_net:
                conflicts.add((old_net, net_map[old_net], new_net, f"{reference}/{path} pad {number}"))
    for conflict in sorted(conflicts):
        print("net conflict:", *conflict)

    # two-pad parts: keep each pad on its net
    turned, undecided = [], []
    for reference, path, old_fp, new_fp in pairs:
        old_nets, new_nets = pad_nets(old_fp), pad_nets(new_fp)
        if set(old_nets) != {"1", "2"} or set(new_nets) != {"1", "2"}:
            continue
        mapped = [net_map.get(old_nets["1"]), net_map.get(old_nets["2"])]
        same = (mapped[0] == new_nets["1"]) + (mapped[1] == new_nets["2"])
        swapped = (mapped[0] == new_nets["2"]) + (mapped[1] == new_nets["1"])
        if swapped > same:
            new_fp.SetOrientation(new_fp.GetOrientation() + pcbnew.EDA_ANGLE(180.0, pcbnew.DEGREES_T))
            turned.append(reference)
        elif swapped == same:
            undecided.append(f"{reference}/{path}")
    print(f"placed {len(pairs)} parts as on frida-scc-1p1; turned by 180 degrees: {' '.join(turned)}")
    if undecided:
        print("pad order undecided (no net in common with a larger part):", " ".join(undecided))

    # everything else waits to the right of the outline, keeping the arrangement the tool gave it
    placed = {new_fp.GetFieldText("Path") for _, _, _, new_fp in pairs}
    waiting = [fp for fp in new.GetFootprints() if fp.GetFieldText("Path") not in placed]
    edge = new.GetBoardEdgesBoundingBox()
    left = min(fp.GetBoundingBox().GetLeft() for fp in waiting)
    top = min(fp.GetBoundingBox().GetTop() for fp in waiting)
    shift = pcbnew.VECTOR2I(
        edge.GetRight() + pcbnew.FromMM(STAGING_GAP_MM) - left,
        edge.GetTop() - top,
    )
    for fp in waiting:
        fp.Move(shift)
    print(f"{len(waiting)} parts wait to the right of the outline")

    pcbnew.SaveBoard(str(NEW), new)


if __name__ == "__main__":
    main()
