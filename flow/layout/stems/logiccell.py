"""CMOS logic cells (INV, NAND2, NOR2, ...) in one standard-cell row: NMOS below, PMOS above.

The standard cells' arrangement: the N+ implant below the P+ implant and the N-well, one
vertical poly per gate column crossing both. Every column carries one NMOS and one PMOS finger
with the same gate net, so a gate's NMOS and PMOS have the same finger count (the netlist says
so: flow/comp/subckt.py gives each gate's NMOS and PMOS one count); their widths and lengths are
independent (any P/N ratio, a long NMOS under a short PMOS: the poly is as wide as each side's L
and joins at the gate bar between the halves). The PDK's ``tech`` places it (``LOGIC_*``; the
numbers are in ``pdk/<pdk>/layout/README.md``):

    y (R0, VSS at the bottom)
    NMOS diffusion, its finger limit, kept from the well
    gate track: poly bar, contact, M1 pad, VIA1, M2 input pin
    PMOS diffusion, its finger limit, inside the well, the gate end short of the N-tap diffusion
    the M2 tracks of the NMOS side's signal net (one) and the PMOS side's

Fingers alternate source/drain along a side and share diffusion wherever adjacent nets
agree (a series stack's middle node needs no contact); different nets meet at a
diffusion break. A net on both sides (the output) joins its NMOS and PMOS bars with an M3
jumper. Implants, well and VT are the standard cells' and stop at the cell outline (only
the tap bands and the N-tap well band overhang, like every row cell), and the devices
keep EDGE to the sides: logic cells abut analog row cells, standard cells (wrapped) and
each other in any order.

    cell = logiccell.logic("X1", [LDev("MN", "n", 60, 200, 1, "zn", "a", "vss"), ...])
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass

from rowcell import (
    BAR_END,
    CO,
    CO_OD_END,
    CO_PITCH,
    CPP,
    EDGE,
    M1_AREA,
    M1_CO_END,
    M1_EDGE,
    M1_HW,
    M1_SPACE,
    M1W,
    M2_EDGE,
    M2_HW,
    M2_MIN_LEN,
    M3_EDGE,
    M3_HW,
    NP_TAP,
    OD_EXT,
    OD_GAP,
    PO_BAR_END,
    PO_ENDCAP,
    PO_HEAD,
    PP_TAP,
    V1_H,
    V2_H,
    XPITCH,
    Cell,
    H,
    _up,
)
from tech import (
    DC_N,
    DC_N_CO_TOP,
    DC_NBAR,
    DC_P,
    DC_P_CO_BOT,
    DC_PAD_H,
    DC_PBAR,
    LOGIC_GRID,
    LOGIC_GT,
    N_CO_TOP,
    N_M1,
    N_OD0,
    N_TRACKS,
    N_WMAX,
    P_CO_BOT,
    P_CO_TOP,
    P_M1,
    P_OD0,
    P_TRACKS,
    P_WMAX,
    PAD_H,
    PAD_W,
    PO_SPACE,
    STRIP_W,
)

GT = LOGIC_GT


@dataclass
class LDev:
    name: str
    pol: str  # "n" or "p"
    l: int
    w: int  # per finger
    nf: int
    d: str
    g: str
    s: str


def logic(
    name: str,
    devs: list[LDev],
    grid: int = LOGIC_GRID,
    vss: str = "vss",
    vdd: str = "vdd",
    ports: set[str] | None = None,
) -> Cell:
    """``ports``: the nets exposed as pins (all of them by default)."""
    rail = {"n": vss, "p": vdd}
    inputs = list(dict.fromkeys(d.g for d in devs))
    by = {(d.g, d.pol): d for d in devs}
    assert len(by) == len(devs), f"{name}: one NMOS and one PMOS per gate net at most"
    for g in inputs:
        ks = {d.nf for d in devs if d.g == g}
        assert len(ks) == 1, f"{name}: gate {g}: NMOS and PMOS finger counts differ {ks}"
    for d in devs:
        assert d.w <= (N_WMAX if d.pol == "n" else P_WMAX), (
            f"{name}: {d.name} finger {d.w} nm too wide for the half row"
        )

    # ---- topology: per side the strip nets along the gate columns, best order and orientation
    def side_strips(order, pol, starts):
        """Strip runs of one side: per input the k+1 strip nets; None where the side has no device."""
        out = []
        for g, st in zip(order, starts):
            d = by.get((g, pol))
            if d is None:
                out.append(None)
                continue
            a, b = (d.s, d.d) if st else (d.d, d.s)
            out.append([a if i % 2 == 0 else b for i in range(d.nf + 1)])
        return out

    best = None
    for order in itertools.permutations(inputs):
        cost, choice = 0, {}
        for pol in "np":
            opts = []
            for starts in itertools.product((True, False), repeat=len(order)):
                runs = side_strips(order, pol, starts)
                breaks = sum(1 for r0, r1 in itertools.pairwise(runs) if r0 and r1 and r0[-1] != r1[0])
                opts.append((breaks, starts))
            breaks, starts = min(opts, key=lambda o: o[0])
            cost += breaks
            choice[pol] = side_strips(order, pol, starts)
        if best is None or cost < best[0]:
            best = (cost, order, choice)
    _, order, runs = best

    # ---- columns: gate x positions, local frame
    def lmax(g):
        return max(d.l for d in devs if d.g == g)

    pitch = {g: lmax(g) + CPP for g in order}  # contacted pitch
    k = {g: next(d.nf for d in devs if d.g == g) for g in order}
    contact = {g: (k[g] - 1) // 2 for g in order}  # the gate column holding the contact (middle)
    gx = {}
    x = 0
    for i, g in enumerate(order):
        if i:
            gp = order[i - 1]
            dist = pitch[gp] // 2 + pitch[g] // 2
            if any(runs[p][i - 1] and runs[p][i] and runs[p][i - 1][-1] != runs[p][i][0] for p in "np"):
                dist = pitch[gp] // 2 + 2 * OD_EXT + OD_GAP + pitch[g] // 2
            # poly bars and heads of the two gate nets: PO.S; contacts side by side: the M1 pads
            right = max(lmax(gp) // 2, PO_BAR_END if contact[gp] == k[gp] - 1 else 0)
            left = max(lmax(g) // 2, PO_BAR_END if contact[g] == 0 else 0)
            dist = max(dist, right + PO_SPACE + left)
            if contact[gp] == k[gp] - 1 and contact[g] == 0:
                dist = max(dist, PAD_W + M1_SPACE)
            x = gx[(gp, k[gp] - 1)] + _up(dist, 10)
        for j in range(k[g]):
            gx[(g, j)] = x + j * pitch[g]

    # strips per side: (x, net, devices on it); OD per device from its first to its last strip
    strips = {"n": [], "p": []}
    ods = {"n": [], "p": []}
    for pol in "np":
        prev = None  # index of the previous input with a device on this side
        for i, g in enumerate(order):
            r = runs[pol][i]
            if r is None:
                prev = None
                continue
            d = by[(g, pol)]
            xs = [gx[(g, 0)] - pitch[g] // 2] + [gx[(g, j)] + pitch[g] // 2 for j in range(k[g])]
            if prev == i - 1 and strips[pol][-1][1] == r[0]:  # one strip, centred between the gates
                last = strips[pol].pop()
                gp = order[i - 1]
                xs[0] = (gx[(gp, k[gp] - 1)] + gx[(g, 0)]) // 2
                ods[pol][-1][2] = xs[0]
                strips[pol].append((xs[0], r[0], last[2] + [d]))
                strips[pol].extend((xx, net, [d]) for xx, net in zip(xs[1:], r[1:]))
            else:
                strips[pol].extend((xx, net, [d]) for xx, net in zip(xs, r))
            ods[pol].append([d, xs[0], xs[-1]])
            prev = i

    # ---- tracks: a net needs one when it has several strips on a side or is on both sides
    track = {}
    for pol, tracks in (("n", N_TRACKS), ("p", P_TRACKS)):
        other = {s[1] for s in strips["p" if pol == "n" else "n"]}
        nets = [
            n
            for n in dict.fromkeys(s[1] for s in strips[pol])
            if n != rail[pol] and (sum(1 for s in strips[pol] if s[1] == n) > 1 or n in other)
        ]
        assert len(nets) <= len(tracks), f"{name}: {pol} side needs tracks for {nets}"
        for n, t in zip(nets, tracks):
            track[(pol, n)] = t

    # outline (local): strips with OD and EDGE, gate pads, input bars grown outwards
    xs_all = [s[0] for p in "np" for s in strips[p]]
    lo, hi = min(xs_all) - OD_EXT - EDGE, max(xs_all) + OD_EXT + EDGE
    cx = {g: gx[(g, contact[g])] for g in order}
    inbar = {}
    for i, g in enumerate(order):
        a, b = cx[g] - BAR_END, cx[g] + BAR_END
        if b - a < M2_MIN_LEN:
            if len(order) > 1 and i == 0:
                a = b - M2_MIN_LEN
            elif len(order) > 1 and i == len(order) - 1:
                b = a + M2_MIN_LEN
            else:
                a, b = cx[g] - M2_MIN_LEN // 2, cx[g] + M2_MIN_LEN // 2
        inbar[g] = [a, b]
        lo, hi = min(lo, a - M2_EDGE, cx[g] - PAD_W // 2 - M1_EDGE), max(hi, b + M2_EDGE, cx[g] + PAD_W // 2 + M1_EDGE)
    width = _up(hi - lo, grid)
    sh = (width - (hi - lo)) // 10 * 5 - lo  # centred, on the 5 nm grid
    c = Cell(name, width)
    std_profile(c, width, vss, vdd)

    # ---- devices: OD, poly, contacts, strips
    def od_y(d):
        return (N_OD0, N_OD0 + d.w) if d.pol == "n" else (P_OD0, P_OD0 + d.w)

    for pol in "np":
        for d, x0, x1 in ods[pol]:
            y0, y1 = od_y(d)
            c.add("OD", x0 + sh - OD_EXT, y0, x1 + sh + OD_EXT, y1)
    for g in order:
        for j in range(k[g]):
            x = gx[(g, j)] + sh
            for pol in "np":
                d = by.get((g, pol))
                if d is None:
                    continue
                y0, y1 = od_y(d)
                if pol == "n":
                    c.add("PO", x - d.l // 2, y0 - PO_ENDCAP, x + d.l // 2, GT)
                else:
                    c.add("PO", x - d.l // 2, GT, x + d.l // 2, y1 + PO_ENDCAP)
        # gate bar over the input's columns, head and contact at its contact column
        x0, x1 = gx[(g, 0)] + sh, gx[(g, k[g] - 1)] + sh
        c.add(
            "PO",
            min(x0 - lmax(g) // 2, cx[g] + sh - PO_BAR_END),
            GT - PO_HEAD,
            max(x1 + lmax(g) // 2, cx[g] + sh + PO_BAR_END),
            GT + PO_HEAD,
        )
        x = cx[g] + sh
        c.add(
            "CO",
            x - CO // 2,
            GT - CO // 2,
            x + CO // 2,
            GT + CO // 2,
            g,
            term=f"{by.get((g, 'n'), by.get((g, 'p'))).name}:G",
        )
        c.add("M1", x - PAD_W // 2, GT - PAD_H // 2, x + PAD_W // 2, GT + PAD_H // 2, g)
        c.add("V1", x - V1_H, GT - V1_H, x + V1_H, GT + V1_H, g)
        c.add("M2", inbar[g][0] + sh, GT - M2_HW, inbar[g][1] + sh, GT + M2_HW, g, "pin")

    for pol in "np":
        for x, net, ds in strips[pol]:
            x += sh
            y0, y1 = od_y(min(ds, key=lambda d: d.w))  # a shared strip: the narrower device's diffusion
            t = track.get((pol, net))
            exposed = net != rail[pol] and t is None and ports is not None and net in ports
            if net != rail[pol] and t is None and not exposed:
                continue  # a series stack's middle node: diffusion only
            if pol == "n":
                cys = list(range(y0 + CO_OD_END + CO // 2, min(y1 - CO_OD_END, N_CO_TOP) - CO // 2 + 1, CO_PITCH))
            else:
                top = min(y1 - CO_OD_END, P_CO_TOP) - CO // 2 + 1
                cys = list(range(max(y0 + CO_OD_END, P_CO_BOT) + CO // 2, top, CO_PITCH))
            assert cys, f"{name}: no room for contacts on {ds[0].name}"
            for j, cy in enumerate(cys):  # a shared strip's contacts alternate between its devices
                d = ds[j % len(ds)]
                c.add(
                    "CO",
                    x - CO // 2,
                    cy - CO // 2,
                    x + CO // 2,
                    cy + CO // 2,
                    net,
                    term=f"{d.name}:{'S' if net == d.s else 'D'}",
                )
            ys = [min(cys) - CO // 2 - M1_CO_END, max(cys) + CO // 2 + M1_CO_END]
            if net == rail[pol]:
                ys.append(0 if pol == "n" else H)
            elif not exposed:
                ys += [t - BAR_END, t + BAR_END]
                c.add("V1", x - V1_H, t - V1_H, x + V1_H, t + V1_H, net)
            w = STRIP_W if pol == "n" and net != rail[pol] else M1W
            y0, y1 = min(ys), max(ys)
            if net != rail[pol]:  # M1_AREA: grow towards the gates, within the strip's range
                lim = N_M1 if pol == "n" else P_M1
                y1 = min(max(y1, y0 + -(-M1_AREA // w)), lim[1])
                y0 = max(min(y0, y1 - -(-M1_AREA // w)), lim[0])
            c.add("M1", x - w // 2, y0, x + w // 2, y1, net, "pin" if exposed else "drawing")  # an exposed node: M1 pin

    # ---- signal bars per side; nets on both sides joined by an M3 jumper
    span = {}
    for pol, net in track:
        sx = [s[0] + sh for s in strips[pol] if s[1] == net]
        span[(pol, net)] = [min(sx), max(sx)]
    for net in {n for (_, n) in track}:
        if ("n", net) in track and ("p", net) in track:
            a, b = span[("n", net)], span[("p", net)]
            target = (max(a[0], b[0]) + min(a[1], b[1])) / 2
            m = min(range(_up(M3_EDGE, XPITCH), width - M3_EDGE + 1, XPITCH), key=lambda m: abs(m - target))
            for key in (("n", net), ("p", net)):
                span[key] = [min(span[key][0], m), max(span[key][1], m)]
            yn, yp = track[("n", net)], track[("p", net)]
            for y in (yn, yp):
                c.add("V2", m - V2_H, y - V2_H, m + V2_H, y + V2_H, net)
            c.add("M3", m - M3_HW, yn - BAR_END, m + M3_HW, yp + BAR_END, net)
    for (pol, net), t in track.items():
        a, b = span[(pol, net)][0] - BAR_END, span[(pol, net)][1] + BAR_END
        if b - a < M2_MIN_LEN:
            m = (a + b) // 10 * 5
            a, b = m - M2_MIN_LEN // 2, m + M2_MIN_LEN // 2
        a, b = (a, b) if a >= M2_EDGE else (M2_EDGE, b + M2_EDGE - a)
        a, b = (a, b) if b <= width - M2_EDGE else (a - (b - width + M2_EDGE), width - M2_EDGE)
        c.add("M2", a, t - M2_HW, b, t + M2_HW, net, "pin" if ports is None or net in ports else "drawing")
    return c


def std_profile(c: Cell, w: int, vss: str, vdd: str) -> None:
    """Rails (pins), rail taps, the standard cells' implant/well/VT profile over the cell;
    the tap bands and the N-tap well band overhang both sides like every row cell's."""
    from rowcell import IMP_OH, NW_N, NW_OH, NW_TOP, RAIL, STD_NW, TAP_OD, TAP_PITCH, VT_BAND

    for y, net in ((0, vss), (H, vdd)):
        c.add("M1", 0, y - RAIL, w, y + RAIL, net, "pin")
        c.add("OD", 0, y - TAP_OD, w, y + TAP_OD)
        for x in range(TAP_PITCH // 2, w - M1_HW, TAP_PITCH):
            c.add("CO", x - CO // 2, y - CO // 2, x + CO // 2, y + CO // 2, net)
            c.add("M1", x - M1_HW, y - RAIL, x + M1_HW, y + RAIL, net, "stub")
    c.add("PP", -IMP_OH, -PP_TAP, w + IMP_OH, PP_TAP)
    c.add("NP", 0, PP_TAP, w, STD_NW)
    c.add("PP", 0, STD_NW, w, NP_TAP)
    c.add("NP", -IMP_OH, NP_TAP, w + IMP_OH, 2 * H - NP_TAP)
    c.add("NW", 0, STD_NW, w, NW_TOP)
    c.add("NW", -NW_OH, NW_N, 0, NW_TOP)
    c.add("NW", w, NW_N, w + NW_OH, NW_TOP)
    c.add("VTN", 0, VT_BAND[0], w, STD_NW)
    c.add("VTP", 0, STD_NW, w, VT_BAND[1])
    c.add("BND", 0, 0, w, H)


# ---- decap fill (rows from tech: DC_N, DC_P, DC_NBAR, DC_PBAR ...) -------------------------


def decap_fingers(width: int, l: int) -> int:
    return (width - 2 * (EDGE + OD_EXT)) // (l + CPP)


def decap(
    name: str, width: int, l: int = 300, vss: str = "vss", vdd: str = "vdd", hi: str = "hi", lo: str = "lo"
) -> tuple[Cell, list[tuple]]:
    """Decap filling a row gap of ``width``: MOS capacitors behind a tie-high/tie-low pair, as
    the library's decap cells (no gate on a rail), in the logic cells' profile so it abuts any
    row cell. Fingers of gate length ``l``; the leftmost NMOS finger is the tie-low (drain lo:
    the PMOS gates), the rightmost PMOS finger the tie-high (drain hi: the NMOS gates); every
    other finger is a capacitor with source and drain on its rail (with one finger the tie pair
    alone is the capacitor, from 800 nm on). Returns the cell and its
    devices (name, pol, d, g, s, b, w, l) for the LVS source.

        y   275..575 NMOS   690 hi bar   980 lo bar   1095..1535 PMOS
    """
    p = l + CPP
    n = decap_fingers(width, l)
    # one finger: just the tie pair (each gate is the other's load); its two gate pads sit one
    # strip apart and need a long enough L to keep M1_SPACE to the other strap
    assert n >= 2 or (n == 1 and l >= 100), f"{name}: {width} nm is too narrow for a decap of L {l}"
    x0 = (width - n * p) // 10 * 5  # leftmost strip, centred, on the 5 nm grid
    xs = [x0 + i * p for i in range(n + 1)]
    gx = [x + p // 2 for x in xs[:-1]]
    nnet = [lo] + [vss] * n
    pnet = [vdd] * n + [hi]
    c = Cell(name, width)
    std_profile(c, width, vss, vdd)
    c.add("OD", xs[0] - OD_EXT, DC_N[0], xs[-1] + OD_EXT, DC_N[1])
    c.add("OD", xs[0] - OD_EXT, DC_P[0], xs[-1] + OD_EXT, DC_P[1])
    for x in gx:  # separate NMOS and PMOS gates, each up/down to its bar
        c.add("PO", x - l // 2, DC_N[0] - PO_ENDCAP, x + l // 2, DC_NBAR + PO_HEAD)
        c.add("PO", x - l // 2, DC_PBAR - PO_HEAD, x + l // 2, DC_P[1] + PO_ENDCAP)
    # bars with their contact heads: hi at the right end strip, lo at the left end strip
    for y, cx, net in ((DC_NBAR, xs[-1], hi), (DC_PBAR, xs[0], lo)):
        c.add(
            "PO", min(gx[0] - l // 2, cx - PO_BAR_END), y - PO_HEAD, max(gx[-1] + l // 2, cx + PO_BAR_END), y + PO_HEAD
        )
        c.add("CO", cx - CO // 2, y - CO // 2, cx + CO // 2, y + CO // 2, net)
        c.add("M1", cx - PAD_W // 2, y - DC_PAD_H, cx + PAD_W // 2, y + DC_PAD_H, net)
    for i, x in enumerate(xs):
        for pol, net in (("n", nnet[i]), ("p", pnet[i])):
            if pol == "n":
                top = min(DC_N[1] - CO_OD_END, DC_N_CO_TOP) - CO // 2 + 1
                cys = list(range(DC_N[0] + CO_OD_END + CO // 2, top, CO_PITCH))
            else:
                top = min(DC_P[1] - CO_OD_END, P_CO_TOP) - CO // 2 + 1
                cys = list(range(DC_P_CO_BOT + CO // 2, top, CO_PITCH))
            for cy in cys:
                c.add("CO", x - CO // 2, cy - CO // 2, x + CO // 2, cy + CO // 2, net)
            y0, y1 = min(cys) - CO // 2 - M1_CO_END, max(cys) + CO // 2 + M1_CO_END
            if net == vss:
                y0 = 0
            elif net == vdd:
                y1 = H
            elif net == lo:  # the tie-low drain up to the PMOS gate bar's pad
                y1 = DC_PBAR + DC_PAD_H
            else:  # the tie-high drain down to the NMOS gate bar's pad
                y0 = DC_NBAR - DC_PAD_H
            c.add("M1", x - M1_HW, y0, x + M1_HW, y1, net)
    devs = []
    for i in range(n):
        nd, ns = nnet[i], nnet[i + 1]
        devs.append((f"{name}_n{i}", "n", nd, hi, ns, vss, DC_N[1] - DC_N[0], l))
        pd, ps = pnet[i + 1], pnet[i]
        devs.append((f"{name}_p{i}", "p", pd, lo, ps, vdd, DC_P[1] - DC_P[0], l))
    return c, devs
