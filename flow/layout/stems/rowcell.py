"""Analog row cells one standard-cell row tall, drawn from the PDK's ``tech`` values.

Every cell is one standard-cell row tall (``H``) and carries both supply rails with their taps,
so NMOS and PMOS cells, and standard cells, abut in any order along a row and the rows share
rails like a digital block (rows alternate R0 / MX; VSS on even rail lines, VDD on odd ones).
Each PDK's row profile, with its numbers, is in ``pdk/<pdk>/layout/README.md``. In the cell
frame R0 (VSS at the bottom):

    y      what                                      tech value
    0      M1 rail VSS, P+ tap diffusion, contacts   RAIL, TAP_OD, TAP_PITCH
    H      M1 rail VDD, N+ tap diffusion, contacts   likewise
           tap implant bands at both rails           PP_TAP, NP_TAP (as the standard cells')
           N-well                                    NW_N (NMOS cell), NW_P (PMOS cell) .. NW_TOP

The device hugs its own rail, the gate contacts face away from it (NMOS gates on top, PMOS gates
at the bottom), so a source tied to its rail runs straight down (or up) in M1:

    diffusion    OD_LIMIT[pol], fingers up to W_MAX
    gate bar     GATE_TRACK[pol]: poly bar and M1 bar joining the gates, and their M2 track
    S/D tracks   SD_TRACKS[pol]: one M2 track per source/drain net

The device implant covers its gates (DEV_IMP). The tap implant bands and the well band at the N
tap overhang the cell sides like the standard cells' (IMP_OH, NW_OH), which closes them at the row
ends; device implants and the PMOS well body stay inside the cell. Fingers alternate S D S D ...
starting with S; a source equal to the rail's net is tied to the rail, every other net gets its
own M2 track. The M1 rails are the supply pins (rails connect by abutment, like standard cells);
optional M2 straps over them (``m2``) are off by default, so supply vias are left to the block
level.

``mos()`` returns plain rectangles, so every generator (ALIGN on juno, laygo, cic) can
draw the same cells without sharing a geometry library.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace

import tech as _tech  # optional values, with the defaults below
from tech import (  # the PDK's values: its stems directory goes on the path ahead of this one
    BAR_END,
    CO,
    CO_GATE,
    CO_OD_END,
    CO_OD_SIDE,
    CO_PITCH,
    EDGE,
    GATE_GAP,
    GATE_PAD,
    GATE_TRACK,
    IMP_OH,
    LAYERS,
    M1_AREA,
    M1_BAR_MIN,
    M1_CO_END,
    M1_EDGE,
    M1_MIN_LEN,
    M1_SPACE,
    M1W,
    M2_EDGE,
    M2_MIN_LEN,
    M2_SPACE,
    M2W,
    M3_EDGE,
    M3W,
    MFG_GRID,
    NP_TAP,
    NW_N,
    NW_OH,
    NW_P,
    NW_TOP,
    OD_EXT,
    OD_GAP,
    OD_LIMIT,
    PO_BAR_END,
    PO_ENDCAP,
    PO_HEAD,
    PP_TAP,
    RAIL,
    SD_TRACKS,
    SHORT_L,
    STD_NW,
    TAP_OD,
    TAP_PITCH,
    V1,
    V2,
    VT_BAND,
    W_MAX,
    XPITCH,
    H,
)

RAIL_TAPS = getattr(_tech, "RAIL_TAPS", True)  # tap contacts under the rails (else tie cells)
RAIL_OD = getattr(_tech, "RAIL_OD", True)  # diffusion under the rails
RAIL_IMPLANTS = getattr(_tech, "RAIL_IMPLANTS", ("PP", "NP"))  # implant of the VSS and the VDD rail diffusion
# a cell's device implant (y from, to) per type, where it stops short of the other type's rail diffusion
DEV_IMP = getattr(_tech, "DEV_IMP", {"n": (_tech.PP_TAP, _tech.NP_TAP), "p": (_tech.PP_TAP, _tech.NP_TAP)})
# gridded poly: gates longer than LONG_L follow the long-channel values; no poly bar
# joins a device's gates (each gate is a rectangle with its own contact); dummy poly lines past
# each diffusion end, (space from the poly before, width) outwards; a marker over the poly of
# short or long devices; a marker over PMOS poly
LONG_L = getattr(_tech, "LONG_L", None)
CO_GATE_LONG = getattr(_tech, "CO_GATE_LONG", CO_GATE)
OD_EXT_LONG = getattr(_tech, "OD_EXT_LONG", OD_EXT)
PO_BAR = getattr(_tech, "PO_BAR", True)
PO_DUMMY = getattr(_tech, "PO_DUMMY", None)  # {False: short gates, True: long gates}
PO_MARK = getattr(_tech, "PO_MARK", {})  # {long?: layer}
PO_EDGE = getattr(_tech, "PO_EDGE", 0)  # dummy poly kept from the cell edge
# over a PMOS cell: {"layer", "poly": past the poly, "x": past the cell sides, "top": up to}
GATE_MARK = getattr(_tech, "GATE_MARK", None)
# markers drawn with the VT band of each type (layers the PDK requires beside its VT layers)
VT_MARKS = getattr(_tech, "VT_MARKS", {})
# markers over both rails' taps, (layer, half height), overhanging the cell like the tap implants
# (a counter-dope region, say); the dummy poly's own layer where it has one
RAIL_MARKS = getattr(_tech, "RAIL_MARKS", ())
PO_DUMMY_LAYER = getattr(_tech, "PO_DUMMY_LAYER", "PO")
VT = {pol: (vt, *VT_MARKS.get(pol, ())) for pol, vt in (("n", "VTN"), ("p", "VTP"))}
VIA_SPACE = getattr(_tech, "VIA_SPACE", 0)  # via to via where it exceeds what the M2 track pitch leaves

GLAYERS = LAYERS
M1_HW, M2_HW, M3_HW = M1W // 2, M2W // 2, M3W // 2  # half widths: M1 strips and pads, M2 and M3 bars
V1_H, V2_H = V1 // 2, V2 // 2  # half cuts
CPP = CO + 2 * CO_GATE  # contacted gate pitch minus the gate length


@dataclass
class Rect:
    layer: str
    x0: int
    y0: int
    x1: int
    y1: int
    net: str | None = None
    kind: str = "drawing"  # drawing | pin | stub (helper M1 under a via, inside a rail) | blockage (ALIGN keep-out)
    term: str | None = None  # device terminal a contact belongs to, "dev:pin"


@dataclass
class Cell:
    name: str
    width: int
    rects: list[Rect] = field(default_factory=list)
    pins: dict[str, list[Rect]] = field(default_factory=dict)

    def add(self, layer, x0, y0, x1, y1, net=None, kind="drawing", term=None):
        r = Rect(layer, int(x0), int(y0), int(x1), int(y1), net, kind, term)
        self.rects.append(r)
        if kind == "pin":
            self.pins.setdefault(net, []).append(r)
        return r


def _up(v: int, g: int) -> int:
    return -(-v // g) * g


def _on_grid(v: int) -> int:
    """v rounded down to the manufacturing grid."""
    return v // MFG_GRID * MFG_GRID


def _long(l: int) -> bool:
    return LONG_L is not None and l > LONG_L


def _cpp(l: int) -> int:
    """Contacted gate pitch of a gate of length l."""
    return l + CO + 2 * (CO_GATE_LONG if _long(l) else CO_GATE)


def _od_ext(l: int) -> int:
    """OD past the outermost strip centre of a device with gates of length l."""
    return OD_EXT_LONG if _long(l) else OD_EXT


def _gate_off(l: int) -> int:
    """A strip centre to the edge of its gate."""
    return CO // 2 + (CO_GATE_LONG if _long(l) else CO_GATE)


def rails(cell: Cell, w: int, pol: str, vss: str = "vss", vdd: str = "vdd", m2: bool = False) -> None:
    """Both rails with taps, implant bands, well, VT band and boundary for a cell of width w."""
    c = cell
    for y, net in ((0, vss), (H, vdd)):
        c.add("M1", 0, y - RAIL, w, y + RAIL, net, "pin" if net else "drawing")
        if RAIL_OD:
            c.add("OD", 0, y - TAP_OD, w, y + TAP_OD)
        for x in range(TAP_PITCH // 2, w - M1_HW, TAP_PITCH):
            if RAIL_TAPS:
                c.add("CO", x - CO // 2, y - CO // 2, x + CO // 2, y + CO // 2, net)
                c.add("M1", x - M1_HW, y - RAIL, x + M1_HW, y + RAIL, net, "stub")
            if m2 and (x // TAP_PITCH) % 2 == 0:
                c.add("V1", x - V1_H, y - V1_H, x + V1_H, y + V1_H, net)
        if m2:
            c.add("M2", 0, y - M2_HW, w, y + M2_HW, net, "pin")
    c.add(RAIL_IMPLANTS[0], -IMP_OH, -PP_TAP, w + IMP_OH, PP_TAP)
    c.add(RAIL_IMPLANTS[1], -IMP_OH, NP_TAP, w + IMP_OH, 2 * H - NP_TAP)
    for layer, half in RAIL_MARKS:
        for y in (0, H):
            c.add(layer, -IMP_OH, y - half, w + IMP_OH, y + half)
    lo, hi = DEV_IMP[pol]
    c.add("NP" if pol == "n" else "PP", 0, lo, w, hi)
    c.add("NW", -NW_OH, NW_N, w + NW_OH, NW_TOP)
    if pol == "p":
        c.add("NW", 0, NW_P, w, NW_N)
    for layer in VT[pol]:
        c.add(layer, 0, VT_BAND[0], w, VT_BAND[1])
    c.add("BND", 0, 0, w, H)


@dataclass
class Dev:
    """One transistor of a row cell: nf fingers of width w, gate length l (nm)."""

    name: str  # terminal label prefix ("name:S")
    l: int
    w: int
    nf: int
    d: str
    g: str
    s: str


def std_pad(cell: Cell, x0: int, x1: int, lib_side: str, vss: str = "vss", vdd: str = "vdd") -> None:
    """A standard cell's pad from x0 to x1: the library's implant, well and VT profile with
    the rail taps, drawn up to the pad's ends and no further, so an analog row cell can abut
    it (its devices keep EDGE to the well and the P+ implant) and the library cell's own
    overhangs end inside it; only the bands every row cell shares overhang the far end. Tap contacts on a 200 nm pitch from the library cell's side
    (``lib_side``: "left" or "right"), at least 100 nm from the far end."""
    c = cell
    for y, net in ((0, vss), (H, vdd)):
        if RAIL_OD:
            c.add("OD", x0, y - TAP_OD, x1, y + TAP_OD)
        half = TAP_PITCH // 2
        xs = (
            range(x1 - half, x0 + half - 1, -TAP_PITCH)
            if lib_side == "right"
            else range(x0 + half, x1 - half + 1, TAP_PITCH)
        )
        for x in xs if RAIL_TAPS else ():
            c.add("CO", x - CO // 2, y - CO // 2, x + CO // 2, y + CO // 2, net)
            c.add("M1", x - M1_HW, y - RAIL, x + M1_HW, y + RAIL, net, "stub")
    c.add(RAIL_IMPLANTS[0], x0, -PP_TAP, x1, PP_TAP)
    c.add("NP", x0, PP_TAP, x1, STD_NW)
    c.add("PP", x0, STD_NW, x1, NP_TAP)
    c.add(RAIL_IMPLANTS[1], x0, NP_TAP, x1, 2 * H - NP_TAP)
    c.add("NW", x0, STD_NW, x1, NW_TOP)
    for layer in VT["n"]:
        c.add(layer, x0, VT_BAND[0], x1, STD_NW)
    for layer in VT["p"]:
        c.add(layer, x0, STD_NW, x1, VT_BAND[1])
    # past the far end only what every row cell has there: the tap bands and the N-tap well band
    # overhang like rails()'s, so the taps stay enclosed at a row end
    o0, o1 = (x0 - IMP_OH, x0) if lib_side == "right" else (x1, x1 + IMP_OH)
    c.add(RAIL_IMPLANTS[0], o0, -PP_TAP, o1, PP_TAP)
    c.add(RAIL_IMPLANTS[1], o0, NP_TAP, o1, 2 * H - NP_TAP)
    for layer, half in RAIL_MARKS:  # over the pad and past its far end
        for y in (0, H):
            c.add(layer, min(x0, o0), y - half, max(x1, o1), y + half)
    o0, o1 = (x0 - NW_OH, x0) if lib_side == "right" else (x1, x1 + NW_OH)
    c.add("NW", o0, NW_N, o1, NW_TOP)
    if GATE_MARK:  # the library's marker over its PMOS half
        c.add(GATE_MARK["layer"], x0, STD_NW, x1, GATE_MARK["top"])


def mos(
    name: str,
    pol: str,
    l: int,
    w: int,
    nf: int,
    d: str,
    g: str,
    s: str,
    grid: int = XPITCH,
    dev: str = "M0",
    vss: str = "vss",
    vdd: str = "vdd",
    m2_rails: bool = False,
) -> Cell:
    """One transistor (nf fingers of width w, gate length l), padded to a multiple of ``grid``."""
    return mos_row(name, pol, [Dev(dev, l, w, nf, d, g, s)], grid, vss, vdd, m2_rails)


def mos_row(
    name: str,
    pol: str,
    devs: list[Dev],
    grid: int = XPITCH,
    vss: str = "vss",
    vdd: str = "vdd",
    m2_rails: bool = False,
    extra: int = 0,
) -> Cell:
    """One transistor, or a pair of one type (ALIGN's DP, CMC, CCP ... primitives) in one row.

    A pair is drawn mirrored about its middle, A's fingers reversed against B's: A and B share
    the middle strip when their sources are one net (same L and W), else a diffusion break
    separates them. Gates of one net share a bar; differing gates at a shared strip are pushed
    apart (GATE_GAP), except where the dummy poly lines stand on the gates' pitch (gridded poly):
    there a gate keeps one space to the lines either side, so differing gates take a diffusion
    break under the dummy lines instead, every line on the pitch. A gate net that is also a drain
    or source net of the cell (cross-coupled, diode) is joined to that net's track by an M3 jumper
    with two VIA2, so every net is one connected piece inside the cell. A pair too narrow for its
    jumpers' M3 columns is drawn ``grid`` wider (``extra``) until they fit.
    """
    assert 1 <= len(devs) <= 2, f"{name}: one or two devices per row cell"
    for v in devs:
        assert v.w <= W_MAX, f"{name}: finger width {v.w} > {W_MAX}"
    pair = len(devs) == 2
    l0 = devs[0].l
    on_pitch = (
        pair
        and PO_DUMMY is not None
        and devs[1].l == l0
        and all((sp, w) == (_cpp(l0) - l0, l0) for sp, w in PO_DUMMY[_long(l0)])
    )
    shared = pair and devs[0].s == devs[1].s and (l0, devs[0].w) == (devs[1].l, devs[1].w)
    shared = shared and not (on_pitch and devs[0].g != devs[1].g)
    split = shared and devs[0].g != devs[1].g
    widen = _up(max(0, GATE_GAP - _cpp(devs[0].l)), 10) // 2 if split else 0

    # strips [x, net, pin, devices] and gates (x, device) in a local frame, first strip at 0
    strips, gates, ods = [], [], []
    x = 0
    for k, v in enumerate(devs):
        p = _cpp(v.l)  # contacted gate pitch: CO + 2 x CO_GATE to the gate
        seq = ["S" if i % 2 == 0 else "D" for i in range(v.nf + 1)]
        steps = [p] * v.nf
        if pair and k == 0:
            seq.reverse()
        if widen:
            steps[-1 if k == 0 else 0] += widen
        if k == 1:
            if shared:
                x = strips[-1][0]
            elif on_pitch:  # a diffusion break under the dummy lines, the next gate a pitch past the last
                x = strips[-1][0] + len(PO_DUMMY[_long(l0)]) * _cpp(l0)
            elif PO_DUMMY:  # a diffusion break with one dummy poly line, the first of either device's
                (sa, wa), (sb, wb) = PO_DUMMY[_long(devs[0].l)][0], PO_DUMMY[_long(v.l)][0]
                x = strips[-1][0] + _gate_off(devs[0].l) + 2 * max(sa, sb) + max(wa, wb) + _gate_off(v.l)
            else:
                x = strips[-1][0] + _od_ext(devs[0].l) + OD_GAP + _od_ext(v.l)
        xs = [x]
        for st in steps:
            xs.append(xs[-1] + st)
        for i, (sx, pin) in enumerate(zip(xs, seq)):
            if k == 1 and i == 0 and shared:
                strips[-1][3].append(v)
                continue
            strips.append([sx, v.s if pin == "S" else v.d, pin, [v]])
        for i in range(v.nf):
            # the finger next to a widened shared strip keeps its gate at the usual distance from its other strip
            gx = xs[i + 1] - p // 2 if widen and k == 1 and i == 0 else xs[i] + p // 2
            gates.append((gx, v))
        if shared and k == 1:
            ods[-1][2] = xs[-1]
        else:
            ods.append([v, xs[0], xs[-1]])
        x = xs[-1]

    gt = GATE_TRACK[pol]
    pad = (gt - GATE_PAD, gt + GATE_PAD)
    # a gate's metal (contact, pad, via, bars) on the grid: the centre of a gate whose half length
    # is off it (an odd multiple of half the grid) is half a grid step off too; the poly stays put
    on_grid = _on_grid
    groups = {}
    for gx, v in gates:
        groups.setdefault(v.g, []).append(on_grid(gx))
    mid = (strips[0][0] + strips[-1][0]) / 2

    def side(gxs):  # which way short gate bars grow: away from the other gate net
        return 0 if len(groups) == 1 else (-1 if sum(gxs) / len(gxs) < mid else 1)

    def bar(lo, hi, length, s):
        if hi - lo >= length:
            return lo, hi
        if s == 0:
            m = _on_grid((lo + hi) // 2)
            return m - length // 2, m + length // 2
        return (hi - length, hi) if s < 0 else (lo, lo + length)

    m1bars = {}
    m2bars = {}
    for g, gxs in groups.items():
        lo, hi = min(gxs) - M1_HW, max(gxs) + M1_HW
        m1bars[g] = bar(lo, hi, M1_BAR_MIN, side(gxs)) if (hi - lo) * (pad[1] - pad[0]) < M1_AREA else (lo, hi)
        m2bars[g] = bar(min(gxs) - BAR_END, max(gxs) + BAR_END, M2_MIN_LEN, side(gxs))  # M2 area

    # S/D tracks. A pair's mirrored nets share one (both drains, both sources), each net's bar
    # on its own half, so the pair's metal mirrors like its devices; otherwise one per net
    rail_net = vss if pol == "n" else vdd
    tracks = {}
    roles = [{v.s for v in devs} - {rail_net}, {v.d for v in devs} - {rail_net}]
    if pair and not (roles[0] & roles[1]):
        for nets in roles:
            if nets:
                y = SD_TRACKS[pol][len(set(tracks.values()))]
                tracks.update({n: y for n in sorted(nets)})
    for _, net, _, _ in strips:
        if net != rail_net and net not in tracks:
            assert len(set(tracks.values())) < len(SD_TRACKS[pol]), f"{name}: more S/D nets than tracks"
            tracks[net] = SD_TRACKS[pol][len(set(tracks.values()))]
    shared_y = {y for y in tracks.values() if list(tracks.values()).count(y) > 1}
    sdbars = {}
    for net, t in tracks.items():
        sx = [x for x, n, _, _ in strips if n == net]
        sdbars[net] = bar(
            min(sx) - BAR_END,
            max(sx) + BAR_END,
            M2_MIN_LEN,
            (-1 if sum(sx) / len(sx) < mid else 1) if t in shared_y else 0,
        )

    # dummy poly lines (local x0, x1, device) outwards from each diffusion's outer gates; one
    # line between a pair's diffusions, none where a gate is
    dummies = []
    if PO_DUMMY:
        for v, xa, xb in ods:
            for edge, out in ((xa + _gate_off(v.l), -1), (xb - _gate_off(v.l), 1)):
                pos = edge
                for sp, w in PO_DUMMY[_long(v.l)]:
                    a = pos + out * sp
                    x0, x1 = min(a, a + out * w), max(a, a + out * w)
                    pos = a + out * w
                    clash = any(x0 < gx + u.l // 2 and gx - u.l // 2 < x1 for gx, u in gates)
                    if not clash and all((d[0], d[1]) != (x0, x1) for d in dummies):
                        dummies.append((x0, x1, v))

    # cell outline: the OD keeps EDGE to the sides, the gate bars half a spacing, dummy poly PO_EDGE
    m2s = list(m2bars.values()) + (list(sdbars.values()) if pair else [])
    lo = min(
        strips[0][0] - EDGE - _od_ext(devs[0].l),
        min(b[0] for b in m2s) - M2_EDGE,
        min(b[0] for b in m1bars.values()) - M1_EDGE,
        *(d[0] - PO_EDGE for d in dummies),
    )
    hi = max(
        strips[-1][0] + EDGE + _od_ext(devs[-1].l),
        max(b[1] for b in m2s) + M2_EDGE,
        max(b[1] for b in m1bars.values()) + M1_EDGE,
        *(d[1] + PO_EDGE for d in dummies),
    )
    width = _up(hi - lo, grid) + extra
    sh = on_grid((width - (hi - lo)) // 2) - lo
    c = Cell(name, width)
    rails(c, width, pol, vss, vdd, m2_rails)
    rail_y = 0 if pol == "n" else H

    def od_y(v):
        lo_, hi_ = OD_LIMIT[pol]
        if pol == "n":
            assert lo_ + v.w <= hi_
            return lo_, lo_ + v.w
        assert hi_ - v.w >= lo_
        return hi_ - v.w, hi_

    def contacts(
        v,
    ):  # contacts on the strips, 40 nm M1 enclosure along the strip; short gates leave room for the gate pads
        oy0, oy1 = od_y(v)
        short = v.l < SHORT_L
        if pol == "n":
            top = min(oy1 - CO_OD_SIDE, pad[0] - M1_SPACE - M1_CO_END) if short else oy1 - CO_OD_SIDE
            cys = list(range(oy0 + CO_OD_END + CO // 2, top - CO // 2 + 1, CO_PITCH))
        else:
            bot = max(oy0 + CO_OD_SIDE, pad[1] + M1_SPACE + M1_CO_END) if short else oy0 + CO_OD_SIDE
            cys = list(range(oy1 - CO_OD_END - CO // 2, bot + CO // 2 - 1, -CO_PITCH))
        assert cys, f"{name}: no room for S/D contacts"
        return cys

    for v, xa, xb in ods:
        oy0, oy1 = od_y(v)
        c.add("OD", xa + sh - _od_ext(v.l), oy0, xb + sh + _od_ext(v.l), oy1)

    for x, net, pin, vs in strips:
        x += sh
        cys = contacts(vs[0])
        for j, cy in enumerate(cys):  # a shared strip's contacts alternate between the devices
            c.add("CO", x - CO // 2, cy - CO // 2, x + CO // 2, cy + CO // 2, net, term=f"{vs[j % len(vs)].name}:{pin}")
        ys = [min(cys) - CO // 2 - M1_CO_END, max(cys) + CO // 2 + M1_CO_END]
        if net == rail_net:  # tied to its own rail
            ys.append(rail_y)
        else:
            t = tracks[net]
            ys += [t - BAR_END, t + BAR_END]
            c.add("V1", x - V1_H, t - V1_H, x + V1_H, t + V1_H, net)
        y0, y1 = min(ys), max(ys)
        # the strip covers its devices' diffusion, keeping the M1 space (an end-of-line space where
        # the PDK has one) to the gate's M1 on the gate track and to the rail
        oy0, oy1 = min(od_y(v)[0] for v in vs), max(od_y(v)[1] for v in vs)
        gap = max(M1_SPACE, getattr(_tech, "LINE_END", 0))
        if pol == "n":
            y0, y1 = min(y0, max(oy0, RAIL + gap)), max(y1, min(oy1, pad[0] - gap))
        else:
            y0, y1 = min(y0, max(oy0, pad[1] + gap)), max(y1, min(oy1, H - RAIL - gap))
        if y1 - y0 < M1_MIN_LEN:  # M1 area: grow towards the gates, the rail side is closer
            if pol == "n":
                y1 = y0 + M1_MIN_LEN
            else:
                y0 = y1 - M1_MIN_LEN
        c.add("M1", x - M1_HW, y0, x + M1_HW, y1, net)

    # jumpers: a gate net that is also an S/D net reaches its track on M3. A cross-coupled pair
    # gets a mirrored pair of them: drain bar -> M3 -> an M2 crossing over the middle -> M3 ->
    # the other half's gate bar; only the two crossings sit on different tracks.
    sdx = {n: [lo_ + sh + BAR_END, hi_ + sh - BAR_END] for n, (lo_, hi_) in sdbars.items()}  # V2 reach of each bar
    gx2 = {g: [lo_ + sh + BAR_END, hi_ + sh - BAR_END] for g, (lo_, hi_) in m2bars.items()}
    m3s, crossings = [], []
    na, nb = (devs[0].d, devs[1].d) if pair else (None, None)
    if pair and devs[0].g == nb and devs[1].g == na and na != nb and na in tracks and nb in tracks:
        free = _crossing_tracks(pol, set(tracks.values()), {tracks[na], tracks[nb]}, gt)
        assert len(free) >= 2, f"{name}: no tracks for the cross-coupling"
        (dlo, dhi), (glo, ghi) = sdx[nb], gx2[nb]  # B's drain bar (right), A's gate bar (left)
        # extend bars only outwards, away from their mirror images; stay M3_EDGE inside the cell
        xd_c = list(range(_up(dlo, XPITCH), width - M3_EDGE + 1, XPITCH))
        xg_c = list(range(_up(M3_EDGE, XPITCH), ghi + 1, XPITCH))
        best = min(
            ((max(0, m - dhi) + max(0, glo - k), m, k) for m in xd_c for k in xg_c if abs(m - (width - k)) >= XPITCH),
            default=None,
        )
        if best is None:  # too narrow: one column wider, centred
            assert extra < 8 * grid, f"{name}: no M3 tracks for the cross-coupling"
            return mos_row(name, pol, devs, grid, vss, vdd, m2_rails, extra + grid)
        _, xd, xg = best
        for net, d_, g_, tc in ((nb, xd, xg, free[0]), (na, width - xd, width - xg, free[1])):
            sdx[net] = [min(sdx[net][0], d_), max(sdx[net][1], d_)]
            gx2[net] = [min(gx2[net][0], g_), max(gx2[net][1], g_)]
            m3s += [(net, d_, tracks[net], tc), (net, g_, tc, gt)]
            crossings.append((net, tc, min(d_, g_), max(d_, g_)))
    else:
        used = []
        for g in groups:
            if g not in tracks:
                continue
            glo, ghi = gx2[g]
            sx = [x + sh for x, net, _, _ in strips if net == g]
            target = (min(sx) + max(sx)) / 2

            def clear(m, g=g):  # the stretched bar keeps M2_SPACE to other nets' bars on its track
                a, b = min(sdx[g][0], m) - BAR_END, max(sdx[g][1], m) + BAR_END
                return all(
                    b + M2_SPACE <= sdx[n][0] - BAR_END or a - M2_SPACE >= sdx[n][1] + BAR_END
                    for n in tracks
                    if n != g and tracks[n] == tracks[g]
                )

            # inside the gate bar if possible, else stretch the gate bar (its track holds only gates)
            cand = [
                m
                for m in range(_up(M3_EDGE, XPITCH), width - M3_EDGE + 1, XPITCH)
                if all(abs(m - u) >= XPITCH for u in used) and clear(m)
            ]
            assert cand, f"{name}: no M3 track for the {g} jumper"
            m = min(cand, key=lambda m: (max(0, glo - m, m - ghi), abs(m - target)))
            used.append(m)
            sdx[g] = [min(sdx[g][0], m), max(sdx[g][1], m)]
            gx2[g] = [min(gx2[g][0], m), max(gx2[g][1], m)]
            m3s.append((g, m, tracks[g], gt))

    for net, t in tracks.items():
        a, b = sdx[net][0] - BAR_END, sdx[net][1] + BAR_END
        # a single strip's minimum-length bar keeps half an M2 space to the cell edge (it still covers its VIA1)
        a, b = (a, b) if a >= M2_EDGE else (M2_EDGE, b + M2_EDGE - a)
        a, b = (a, b) if b <= width - M2_EDGE else (a - (b - width + M2_EDGE), width - M2_EDGE)
        c.add("M2", a, t - M2_HW, b, t + M2_HW, net, "pin")

    # gates: poly over the OD, a head with the contact at the gate track, an M1 pad, VIA1, M2 bar
    for g, gxs in groups.items():
        gxs = [gx + sh for gx in gxs]
        for gx, v in gates:
            if v.g != g:
                continue
            oy0, oy1, cx, gx = *od_y(v), on_grid(gx) + sh, gx + sh
            if pol == "n":
                c.add("PO", gx - v.l // 2, oy0 - PO_ENDCAP, gx + v.l // 2, gt + PO_HEAD)
            else:
                c.add("PO", gx - v.l // 2, gt - PO_HEAD, gx + v.l // 2, oy1 + PO_ENDCAP)
            c.add("CO", cx - CO // 2, gt - CO // 2, cx + CO // 2, gt + CO // 2, g, term=f"{v.name}:G")
            c.add("M1", cx - M1_HW, pad[0], cx + M1_HW, pad[1], g)
            c.add("V1", cx - V1_H, gt - V1_H, cx + V1_H, gt + V1_H, g)
        # poly bar: the contact's enclosure left and right; M1 bar: the minimum area (M1_AREA)
        if PO_BAR:
            c.add("PO", min(gxs) - PO_BAR_END, gt - PO_HEAD, max(gxs) + PO_BAR_END, gt + PO_HEAD)
        c.add("M1", m1bars[g][0] + sh, pad[0], m1bars[g][1] + sh, pad[1], g)
        c.add("M2", gx2[g][0] - BAR_END, gt - M2_HW, gx2[g][1] + BAR_END, gt + M2_HW, g, "pin")
    for x0, x1, v in dummies:  # as tall as the gates (the poly area)
        oy0, oy1 = od_y(v)
        y0, y1 = (oy0 - PO_ENDCAP, gt + PO_HEAD) if pol == "n" else (gt - PO_HEAD, oy1 + PO_ENDCAP)
        c.add(PO_DUMMY_LAYER, x0 + sh, y0, x1 + sh, y1)
    # markers over the poly: of short or long devices (PO_MARK), of a PMOS cell (GATE_MARK)
    po = [r for r in c.rects if r.layer in ("PO", PO_DUMMY_LAYER)]
    for is_long, layer in PO_MARK.items():
        xs = [(gx + sh - v.l // 2, gx + sh + v.l // 2) for gx, v in gates if _long(v.l) == is_long]
        xs += [(x0 + sh, x1 + sh) for x0, x1, v in dummies if _long(v.l) == is_long]
        if xs:
            c.add(layer, min(a for a, _ in xs), min(r.y0 for r in po), max(b for _, b in xs), max(r.y1 for r in po))
    if GATE_MARK and pol == "p":
        m = GATE_MARK
        y0 = min(r.y0 for r in po) - m["poly"]
        c.add(m["layer"], -m["x"], y0, width + m["x"], max(max(r.y1 for r in po) + m["poly"], m["top"]))
    for net, x, ya, yb in m3s:
        for y in (ya, yb):
            c.add("V2", x - V2_H, y - V2_H, x + V2_H, y + V2_H, net)
        y0, y1 = min(ya, yb) - BAR_END, max(ya, yb) + BAR_END
        if y1 - y0 < M2_MIN_LEN:  # M3 area
            y0, y1 = _on_grid((y0 + y1) // 2) - M2_MIN_LEN // 2, _on_grid((y0 + y1) // 2) + M2_MIN_LEN // 2
        c.add("M3", x - M3_HW, y0, x + M3_HW, y1, net)
    for net, y, xa, xb in crossings:
        c.add("M2", xa - BAR_END, y - M2_HW, xb + BAR_END, y + M2_HW, net)
    return c


def _crossing_tracks(pol: str, used: set[int], drains: set[int], gt: int) -> list[int]:
    """The M2 tracks a cross-coupled pair's two crossings may take: the free S/D tracks where both
    keep each jumper's VIA2 apart (VIA_SPACE) from its other end, on the drain or the gate track;
    else every M2 track of the cell without a bar that does, past the gate track and beside the
    rails too (a PDK with three S/D tracks, whose pair of non-rail sources and drains takes two),
    the shortest jumpers first."""

    clear = lambda t: all(abs(t - y) >= V2 + VIA_SPACE for y in (*drains, gt))
    free = [t for t in SD_TRACKS[pol] if t not in used]
    if len(free) >= 2 and all(clear(t) for t in free[:2]):
        return free[:2]
    pitch = _tech.PITCH
    spare = [t for t in range(pitch, H, pitch) if t not in used and t != gt and clear(t)]
    return sorted(spare, key=lambda t: (sum(abs(t - d) for d in drains) / len(drains) + abs(t - gt), t))


def mos_rows(
    name: str, pol: str, devs: list[Dev], rows: int, grid: int = XPITCH, vss: str = "vss", vdd: str = "vdd"
) -> Cell:
    """``mos_row``'s transistor or pair folded over ``rows`` rows instead of one wide row.

    Each device's fingers are shared evenly between the rows, every row is the same ``mos_row``
    (odd rows mirrored about their middle line, so neighbours share a rail as abutted rows do),
    and a pair keeps A on the left and B on the right in every row: its mirror symmetry about
    the vertical axis holds. Each signal net's bars, one per row on the same track, are joined
    by an M3 strap with a VIA2 on every bar, on a column clear of the row's own M3 jumpers, a
    bar too short for a free column stretched to the nearest one; columns with VIA2 on the same
    track keep two M3 pitches apart, so no two VIA2 face each other a pitch apart.
    """
    assert rows >= 1 and all(v.nf % rows == 0 for v in devs), f"{name}: fingers must split evenly over {rows} rows"
    row = mos_row(name, pol, [replace(v, nf=v.nf // rows) for v in devs], grid, vss, vdd)
    c = Cell(name, row.width)
    for k in range(rows):
        for r in row.rects:
            y0, y1 = (r.y0, r.y1) if k % 2 == 0 else (H - r.y1, H - r.y0)
            c.add(r.layer, r.x0, y0 + k * H, r.x1, y1 + k * H, r.net, r.kind, r.term)
    if rows == 1:
        return c
    bars = {}  # each signal net's widest M2 bar in the row: (x0, x1, y)
    for r in row.rects:
        signal = r.layer == "M2" and r.net and r.net not in (vss, vdd) and r.kind in ("drawing", "pin")
        if signal and r.x1 - r.x0 > bars.get(r.net, (0, 0, 0))[1] - bars.get(r.net, (0, 0, 0))[0]:
            bars[r.net] = (r.x0, r.x1, (r.y0 + r.y1) // 2)
    # occupied M3 columns, the jumpers' first, with the tracks their VIA2 sit on (row frame)
    used = [
        (
            (r.x0 + r.x1) // 2,
            {(v.y0 + v.y1) // 2 for v in row.rects if v.layer == "V2" and v.x0 >= r.x0 and v.x1 <= r.x1},
        )
        for r in row.rects
        if r.layer == "M3"
    ]
    m2 = [(r.x0, r.x1, (r.y0 + r.y1) // 2, r.net) for r in row.rects if r.layer == "M2"]
    for net, (x0, x1, y) in sorted(bars.items(), key=lambda b: b[1][1] - b[1][0]):  # the shortest bars choose first

        def clear(m, net=net, x0=x0, x1=x1, y=y):  # a bar stretched to m keeps M2_SPACE to other nets on its track
            a, b = min(x0, m - BAR_END), max(x1, m + BAR_END)
            return all(b + M2_SPACE <= p0 or a - M2_SPACE >= p1 for p0, p1, py, n in m2 if py == y and n != net)

        # inside the bar if a column is free there, else the nearest one the bar can be stretched to
        cand = [
            m
            for m in range(_up(M3_EDGE, XPITCH), c.width - M3_EDGE + 1, XPITCH)
            # a pitch from every other column, two where both put a VIA2 on this track (VIA2 facing)
            if all(abs(m - u) >= (2 * XPITCH if y in ys else XPITCH) for u, ys in used) and clear(m)
        ]
        assert cand, f"{name}: no M3 column for the {net} strap"
        m = min(cand, key=lambda m: (max(0, x0 + BAR_END - m, m - x1 + BAR_END), abs(2 * m - x0 - x1)))
        used.append((m, {y}))
        lo, hi = min(x0, m - BAR_END), max(x1, m + BAR_END)
        ys = [k * H + (y if k % 2 == 0 else H - y) for k in range(rows)]
        for yv in ys:
            c.add("V2", m - V2_H, yv - V2_H, m + V2_H, yv + V2_H, net)
            if (lo, hi) != (x0, x1):
                c.add("M2", lo, yv - M2_HW, hi, yv + M2_HW, net)
        c.add("M3", m - M3_HW, min(ys) - BAR_END, m + M3_HW, max(ys) + BAR_END, net)
    return c


def _m2_bar(c: Cell, xs: list[int], y: int, net: str) -> None:
    lo, hi = min(xs) - BAR_END, max(xs) + BAR_END
    if hi - lo < M2_MIN_LEN:  # M2 area
        mid = _on_grid((lo + hi) // 2)
        lo, hi = mid - M2_MIN_LEN // 2, mid + M2_MIN_LEN // 2
    c.add("M2", lo, y - M2_HW, hi, y + M2_HW, net, "pin")


def to_klayout(cell: Cell, layout, kdb):
    """Draw a Cell into a klayout Layout (helpers: stubs are dropped, they lie inside the rails;
    layers the PDK does not draw, None in its LAYERS, are skipped)."""
    kc = layout.create_cell(cell.name)
    for r in cell.rects:
        if r.kind in ("stub", "blockage") or not GLAYERS.get(r.layer):
            continue
        kc.shapes(layout.layer(*GLAYERS[r.layer])).insert(kdb.Box(r.x0, r.y0, r.x1, r.y1))
    return kc
