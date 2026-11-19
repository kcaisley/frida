"""Place the parts frida-scc-2p0 adds to frida-scc-1p1, inside its outline.

Run with KiCad's Python after ``place_from_1p1.py`` (which leaves these parts beside the outline):

    $KICAD_APPDIR/bin/python3.11 place_new.py

Three kinds of placement, all in millimetres on the board (x right, y down, the outline from
100, 50 to 200, 150):

- ``FIXED``: the large parts and connectors, each by the centre of its courtyard.
- blocks: a regulator and its nine parts, a probe channel and its three chips, each the same
  arrangement repeated at the origins in ``REGULATORS`` and ``CHANNELS``.
- ``NEAR``: each small part goes to the free spot closest to the pin of the part it serves,
  turned so that the pad they share faces that pin.

Left of the chip: the supplies (regulators in two columns, the rails' select jumpers between them
and the chip, the external-rail header at the lower left) and, above them, the signal source
beside the input jumpers. Right of the chip: the four oscilloscope SMAs down the edge, each with
its switch, multiplexer and select register, and the second RJ45 above the first.
"""

from __future__ import annotations

import collections
import math
from pathlib import Path
from typing import Any

import pcbnew

HERE = Path(__file__).parent
OLD = HERE.parent / "frida-scc-1p1.kicad_pcb"
NEW = HERE / "eda" / "frida-scc-2p0.kicad_pcb"
GAP = 0.15  # between courtyards
EDGE = 1.0  # from a courtyard to the outline
REACH = 14.0  # how far a NEAR part may end up from its pin

# part -> (x, y, rotation) of its courtyard's centre
FIXED = {
    "SOURCE.U_REF": (106.2, 64.0, 0),
    "SOURCE.U_DAC": (113.8, 64.0, 0),
    "SOURCE.U_BUF_P": (121.0, 64.0, 0),
    "SOURCE.U_BUF_N": (121.0, 72.5, 0),
    "INPUT.J_SRC": (128.6, 65.3, 0),
    "SUPPLIES.J_SEL_DAC": (132.6, 87.5, 0),
    "SUPPLIES.J_SEL_A": (132.6, 96.4, 0),
    "SUPPLIES.J_SEL_D": (132.6, 105.3, 0),
    "SUPPLIES.J_SEL_IO": (132.6, 114.2, 0),
    "SUPPLIES.J_EXT": (105.0, 127.0, 0),
    "SUPPLIES.C_P_BULK": (127.0, 122.6, 0),
    "SUPPLIES.C_N_BULK": (133.0, 122.6, 0),
    "AUX.J_AUX": (191.7, 123.35, 90),  # facing the right edge, set in from it as the first RJ45 is from the lower one
}

# a regulator's parts about the centre of its chip: the input side on the left, the output side
# and the set point on the right, the power-good divider below
REGULATOR = {
    "U_REG": (0.0, 0.0, 0),
    "C_IN": (-4.4, -0.9, 90),
    "R_ILIM": (-4.35, 1.6, 0),
    "R_IMON": (-4.35, 2.8, 0),
    "C_OUT": (4.4, -0.9, 90),
    "R_SET": (4.9, 1.85, 0),
    "C_SET": (4.9, 3.6, 0),
    "R_PG_TOP": (-1.1, 3.1, 0),
    "R_PG_BOT": (1.1, 3.1, 0),
    "R_BLEED": (0.0, 3.1, 0),  # the negative regulator's, in the divider's place
}
REGULATORS = {  # the chip rails' in the column nearer the chip
    "SUPPLIES.REG_3V3A": (108.6, 87.0),
    "SUPPLIES.REG_VS_N": (108.6, 95.4),
    "SUPPLIES.REG_2V5": (108.6, 103.8),
    "SUPPLIES.REG_DAC": (122.4, 87.0),
    "SUPPLIES.REG_A": (122.4, 95.4),
    "SUPPLIES.REG_D": (122.4, 103.8),
    "SUPPLIES.REG_IO": (122.4, 112.2),
}

# a probe channel's parts about its SMA: the switch beside it, its two board-facing inputs
# towards the chip; the multiplexer (its output towards the switch) and the register beyond
CHANNEL = {
    "J_SCOPE": (0.0, 0.0, 0),
    "U_RF": (-9.4, 0.0, 0),
    "U_SLOW": (-17.6, -3.1, 180),
    "U_SEL": (-17.6, 3.1, 0),
}
CHANNELS = {"CH1": (195.0, 63.5), "CH2": (195.0, 78.0), "CH3": (195.0, 92.5), "CH4": (195.0, 107.0)}

# small part -> the part it sits beside (at the pin whose net they share)
NEAR = {
    "SOURCE.C_REF_IN": "SOURCE.U_REF",
    "SOURCE.C_REF_OUT": "SOURCE.U_REF",
    "SOURCE.C_REF_100N": "SOURCE.U_REF",
    "SOURCE.C_DAC_VDD": "SOURCE.U_DAC",
    "SOURCE.C_DAC_VLOGIC": "SOURCE.U_DAC",
    "SOURCE.C_DAC_OUT": "SOURCE.U_DAC",
    "SOURCE.R_CS_PU": "SOURCE.U_DAC",
    "SOURCE.R_LDAC_PD": "SOURCE.U_DAC",
    "SOURCE.C_BUF_P_VP": "SOURCE.U_BUF_P",
    "SOURCE.C_BUF_P_VN": "SOURCE.U_BUF_P",
    "SOURCE.R_OUT_P": "SOURCE.U_BUF_P",
    "SOURCE.C_OUT_P": "SOURCE.R_OUT_P",
    "SOURCE.C_BUF_N_VP": "SOURCE.U_BUF_N",
    "SOURCE.C_BUF_N_VN": "SOURCE.U_BUF_N",
    "SOURCE.R_MID_TOP": "SOURCE.U_BUF_N",
    "SOURCE.R_MID_BOT": "SOURCE.U_BUF_N",
    "SOURCE.C_MID": "SOURCE.U_BUF_N",
    "SOURCE.R_OUT_N": "SOURCE.U_BUF_N",
    "SOURCE.C_OUT_N": "SOURCE.R_OUT_N",
    "R_MON_SRC_TOP": "INPUT.J_SRC",
    "R_MON_SRC_BOT": "R_MON_SRC_TOP",
    "INPUT.R_MON_VIN_P": "ASIC.U_ASIC",
    "INPUT.R_MON_VIN_N": "ASIC.U_ASIC",
    "INPUT.R_MON_AMP_P": "INPUT.U_AMP",
    "INPUT.R_MON_AMP_N": "INPUT.U_AMP",
    "R_MON_SPI_CS_B": "LINK.U_SHIFT",
    "R_MON_SPI_SCLK": "LINK.U_SHIFT",
    "R_MON_SPI_SDI": "LINK.U_SHIFT",
    "R_MON_SPI_SDO": "LINK.U_SHIFT",
    "SUPPLIES.R_MON_3V3A_TOP": "SUPPLIES.REG_3V3A.U_REG",
    "SUPPLIES.R_MON_3V3A_BOT": "SUPPLIES.R_MON_3V3A_TOP",
    "SUPPLIES.R_MON_VS_N_BOT": "SUPPLIES.REG_VS_N.U_REG",
    "SUPPLIES.R_MON_VS_N_TOP": "SUPPLIES.R_MON_VS_N_BOT",
    "AUX.R_SDI_PD": "AUX.J_AUX",
    "AUX.R_RCLK_PD": "AUX.J_AUX",
    "AUX.R_SCLK_PD": "AUX.J_AUX",
    **{f"{ch}.C_RF": f"{ch}.U_RF" for ch in CHANNELS},
    **{f"{ch}.R_SLOW": f"{ch}.U_RF" for ch in CHANNELS},
    **{f"{ch}.C_SLOW": f"{ch}.U_SLOW" for ch in CHANNELS},
    **{f"{ch}.C_SEL": f"{ch}.U_SEL" for ch in CHANNELS},
}

# the COMP_OUT taps: pad 1 where frida-scc-1p1's probe header (J2) met each leg of the pair
ON_LINE = {"TAP_COMP_OUT.R_P": ("J2", "5"), "TAP_COMP_OUT.R_N": ("J2", "6")}

mm = pcbnew.ToMM


def turn(x: float, y: float, degrees: float) -> tuple[float, float]:
    """A footprint's own (x, y) on the board when the footprint is turned (KiCad's sense)."""

    c, s = math.cos(math.radians(degrees)), math.sin(math.radians(degrees))
    return x * c + y * s, -x * s + y * c


class Part:
    """A footprint to place: its courtyard and pads about its anchor, measured unturned."""

    def __init__(self, footprint: Any) -> None:
        self.fp = footprint
        footprint.SetOrientationDegrees(0)
        footprint.SetPosition(pcbnew.VECTOR2I(0, 0))
        footprint.BuildCourtyardCaches()
        box = footprint.GetCourtyard(pcbnew.F_CrtYd).BBox()
        if box.GetWidth() == 0:
            box = footprint.GetBoundingBox(False)
        self.box = (mm(box.GetLeft()), mm(box.GetTop()), mm(box.GetRight()), mm(box.GetBottom()))
        self.pads = {p.GetNumber(): (mm(p.GetPosition().x), mm(p.GetPosition().y)) for p in footprint.Pads()}
        self.nets = {p.GetNumber(): p.GetNetname() for p in footprint.Pads() if p.GetNetname()}

    def centre(self, degrees: float) -> tuple[float, float]:
        """The courtyard's centre about the anchor at a rotation."""

        x0, y0, x1, y1 = self.box
        return turn((x0 + x1) / 2, (y0 + y1) / 2, degrees)

    def size(self, degrees: float) -> tuple[float, float]:
        x0, y0, x1, y1 = self.box
        w, h = x1 - x0, y1 - y0
        return (h, w) if round(degrees / 90) % 2 else (w, h)

    def courtyard(self, x: float, y: float, degrees: float) -> tuple[float, float, float, float]:
        """The courtyard's box when its centre is at (x, y)."""

        w, h = self.size(degrees)
        return (x - w / 2, y - h / 2, x + w / 2, y + h / 2)

    def pad(self, number: str, x: float, y: float, degrees: float) -> tuple[float, float]:
        """A pad's place when the courtyard's centre is at (x, y)."""

        cx, cy = self.centre(degrees)
        px, py = turn(*self.pads[number], degrees)
        return x - cx + px, y - cy + py

    def put(self, x: float, y: float, degrees: float) -> None:
        cx, cy = self.centre(degrees)
        self.fp.SetOrientationDegrees(degrees)
        self.fp.SetPosition(pcbnew.VECTOR2I(pcbnew.FromMM(x - cx), pcbnew.FromMM(y - cy)))


def main() -> None:
    board = pcbnew.LoadBoard(str(NEW))
    old = pcbnew.LoadBoard(str(OLD))
    edge = board.GetBoardEdgesBoundingBox()
    inside = (
        mm(edge.GetLeft()) + EDGE,
        mm(edge.GetTop()) + EDGE,
        mm(edge.GetRight()) - EDGE,
        mm(edge.GetBottom()) - EDGE,
    )
    by_path = {fp.GetFieldText("Path").rsplit(".", 1)[0]: fp for fp in board.GetFootprints()}

    # the courtyards already on the board, and the parts still beside it
    taken: list[tuple[float, float, float, float]] = []
    waiting: dict[str, Part] = {}
    for path, fp in by_path.items():
        if edge.Contains(fp.GetPosition()):
            fp.BuildCourtyardCaches()
            box = fp.GetCourtyard(pcbnew.B_CrtYd if fp.IsFlipped() else pcbnew.F_CrtYd).BBox()
            if box.GetWidth() == 0:
                box = fp.GetBoundingBox(False)
            taken.append((mm(box.GetLeft()), mm(box.GetTop()), mm(box.GetRight()), mm(box.GetBottom())))
        else:
            waiting[path] = Part(fp)

    def clear(box: tuple[float, float, float, float]) -> bool:
        """No courtyard on the board within GAP of this one."""

        return all(
            box[2] + GAP <= t[0] or t[2] + GAP <= box[0] or box[3] + GAP <= t[1] or t[3] + GAP <= box[1] for t in taken
        )

    def free(box: tuple[float, float, float, float]) -> bool:
        """Clear, and EDGE inside the outline (the connectors at an edge are placed by hand)."""

        within = box[0] >= inside[0] and box[1] >= inside[1] and box[2] <= inside[2] and box[3] <= inside[3]
        return within and clear(box)

    pads_on = collections.Counter(pad.GetNetname() for fp in board.GetFootprints() for pad in fp.Pads())
    clashes = []

    def place(path: str, x: float, y: float, degrees: float) -> None:
        part = waiting.pop(path)
        box = part.courtyard(x, y, degrees)
        if not clear(box):
            clashes.append(path)
        part.put(x, y, degrees)
        taken.append(box)

    for path, (x, y, degrees) in FIXED.items():
        place(path, x, y, degrees)
    for block, origins in ((REGULATOR, REGULATORS), (CHANNEL, CHANNELS)):
        for instance, (ox, oy) in origins.items():
            for name, (dx, dy, degrees) in block.items():
                if f"{instance}.{name}" in waiting:
                    place(f"{instance}.{name}", ox + dx, oy + dy, degrees)

    # the COMP_OUT taps: pad 1 on the line, the body pointing where there is room
    for path, (reference, number) in ON_LINE.items():
        spot = old.FindFootprintByReference(reference).FindPadByNumber(number).GetPosition()
        part = waiting[path]
        for degrees in (270, 90, 0, 180):
            px, py = part.pad("1", 0.0, 0.0, degrees)
            x, y = mm(spot.x) - px, mm(spot.y) - py
            if free(part.courtyard(x, y, degrees)):
                break
        place(path, x, y, degrees)

    # the small parts, each beside the pin it shares a net with
    far = []
    for path, beside in NEAR.items():
        part = waiting[path]
        neighbour = by_path[beside]
        shared = [
            (pad.GetNetname(), pad)
            for pad in neighbour.Pads()
            if pad.GetNetname() in part.nets.values() and pad.GetNetname() != "GND"
        ]
        if not shared:
            raise SystemExit(f"{path} shares no net with {beside}")
        # the net they share that has the fewest pads on the board: the particular connection
        net, anchor = min(shared, key=lambda item: pads_on[item[0]])
        target = (mm(anchor.GetPosition().x), mm(anchor.GetPosition().y))
        own = next(number for number, name in part.nets.items() if name == net)
        best = None
        steps = int(REACH / 0.25)
        for ix in range(-steps, steps + 1):
            for iy in range(-steps, steps + 1):
                x, y = target[0] + ix * 0.25, target[1] + iy * 0.25
                reach = math.hypot(ix, iy) * 0.25
                if best is not None and reach > best[0] + 2.5:
                    continue
                for degrees in (0, 90, 180, 270):
                    if not free(part.courtyard(x, y, degrees)):
                        continue
                    px, py = part.pad(own, x, y, degrees)
                    score = math.hypot(px - target[0], py - target[1])
                    if best is None or score < best[0]:
                        best = (score, x, y, degrees)
        if best is None:
            raise SystemExit(f"no room for {path} within {REACH} mm of {beside}")
        if best[0] > 5.0:
            far.append(f"{path} {best[0]:.1f} mm")
        place(path, best[1], best[2], best[3])

    if waiting:
        raise SystemExit(f"not placed: {' '.join(sorted(waiting))}")
    print(
        f"placed {len(FIXED)} large parts, {len(REGULATORS)} regulators, {len(CHANNELS)} channels, {len(NEAR)} small parts"
    )
    if clashes:
        print("courtyards overlapping:", " ".join(clashes))
    if far:
        print("more than 5 mm from their pin:", ", ".join(far))
    pcbnew.SaveBoard(str(NEW), board)


if __name__ == "__main__":
    main()
