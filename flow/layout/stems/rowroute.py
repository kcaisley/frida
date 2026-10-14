"""A small M2/M3 router for blocks of row cells (the scheme the laygo design script uses).

Every signal pin is an M2 bar on a cell track. A net gets vertical M3 trunks, each
dropping a VIA2 onto the pins whose bars it crosses (pins grouped greedily by x
overlap); trunks of a net are joined spanning-tree style by M2 bars on free tracks.
Ports leave on M3 to the top or bottom edge. Everything is booked per track with the
net, so different nets share tracks where they are far enough apart.

Geometry from the PDK's ``tech``: M3 tracks every XPITCH in x, M2 tracks every PITCH in y,
wires M2W / M3W wide, VIA2 enclosed BAR_END - V2 / 2 along the wire, wires at least
M2_MIN_LEN long (the minimum area), all from the PDK's ``tech``.

    r = Router(blocked_m2, width, height); r.route(net, pins); r.escape(net, up); r.rects
"""

from __future__ import annotations

import itertools

import tech as _tech
from tech import BAR_END as END
from tech import M2_MIN_LEN as MIN
from tech import M2_SPACE as SP
from tech import M2W, M3W, PITCH, V2, XPITCH, H

P2, P3 = PITCH, getattr(_tech, "M3_PITCH", XPITCH)  # M2 tracks (y), M3 tracks (x: the cell grid unless finer)
HW2, HW3, HV2 = M2W // 2, M3W // 2, V2 // 2
# cuts on one trunk closer than this share one (where the via space exceeds what the M2 pitch leaves)
VIA_GAP = max(P2, V2 + getattr(_tech, "VIA_SPACE", 0))
GAP3, GAP2 = 2 * SP, 2 * SP  # keep-out between different nets' segments on one track (line ends, via pads)


class Router:
    def __init__(
        self,
        blocked: list[tuple[str, int, int, int, int]],
        width: int,
        height: int,
        rail_pitch: int = H,
        m3_keep: list[tuple[int, int, int]] = (),
    ):
        """``blocked``: (net, x0, y0, x1, y1) of all M2 in the cells (pins and pads)."""
        self.w, self.h = width, height
        self.occ3: dict[int, list] = {}
        self.occ2: dict[int, list] = {}
        self.rects: list[tuple[str, int, int, int, int]] = []
        self.exact2 = [(net, x0, y0, x1, y1) for net, x0, y0, x1, y1 in blocked]  # for exact checks
        self.trunks: dict[str, list[list[int]]] = {}
        for m, y0, y1 in m3_keep:
            self.occ3.setdefault(m, []).append((y0, y1, "__keep"))
        for net, x0, y0, x1, y1 in blocked:  # every M2 track whose wire would come within the M2 space
            self._book2(net, x0, y0, x1, y1)
        self.tracks2 = [y for y in range(P2, height, P2) if y % rail_pitch]

    def _book2(self, net, x0, y0, x1, y1):
        for t in range((y0 - HW2 - SP) // P2 * P2, y1 + HW2 + SP + 1, P2):
            if t - HW2 < y1 + SP and t + HW2 > y0 - SP:
                self.occ2.setdefault(t, []).append((x0 - HW2, x1 + HW2, net))

    # ---- bookkeeping -------------------------------------------------------------------
    @staticmethod
    def _free(occ, k, a, b, net, gap):
        return all(b + gap <= lo or a - gap >= hi for lo, hi, n in occ.get(k, []) if n != net)

    def free3(self, m, a, b, net):
        return 0 < m * P3 < self.w and self._free(self.occ3, m, a, b, net, GAP3)

    def free2(self, y, a, b, net):
        # bars only join trunks, never pins: keep clear of every M2, the net's own included
        # (touching a pin of the net would leave jogs and holes, against the grid and minimum-area rules)
        return self._free(self.occ2, y, a, b, None, GAP2)

    @staticmethod
    def _span(a, b):
        """The M3 drawn between via centres a and b: END past them, the minimum length about the middle."""
        a, b = min(a, b), max(a, b)
        if b - a < MIN - 2 * END:
            mid = (a + b) // 2
            a, b = mid - (MIN - 2 * END) // 2, mid + (MIN - 2 * END) // 2
        return a - END, b + END

    def m3(self, net, m, a, b):
        lo, hi = self._span(a, b)
        self.occ3.setdefault(m, []).append((lo, hi, net))
        self.rects.append(("M3", m * P3 - HW3, lo, m * P3 + HW3, hi))

    def via2(self, x, y):
        # a second cut on one trunk closer than a via pitch: the M2 under both is one piece already;
        # closer than VIA_GAP (bars on adjacent tracks): an M2 strap joins this bar to the other's
        near = [r for r in self.rects if r[0] == "VIA2" and r[1] == x - HV2 and abs(r[2] - (y - HV2)) < VIA_GAP]
        if not near:
            self.rects.append(("VIA2", x - HV2, y - HV2, x + HV2, y + HV2))
        elif all(abs(r[2] - (y - HV2)) >= P2 for r in near):
            yo = near[0][2] + HV2
            self.rects.append(("M2", x - HW2, min(y, yo) - HW2, x + HW2, max(y, yo) + HW2))

    def m2(self, net, y, xa, xb):
        a, b = min(xa, xb) - END, max(xa, xb) + END
        if b - a < MIN:
            b = a + MIN if self.free2(y, a, a + MIN, net) else b
            a = b - MIN
        self.occ2.setdefault(y, []).append((a, b, net))
        self.rects.append(("M2", a, y - HW2, b, y + HW2))
        self.exact2.append((net, a, y - HW2, b, y + HW2))

    def block2(self, net, x0, y0, x1, y1):
        """Book an M2 shape drawn outside the router (e.g. a landing pad)."""
        self.exact2.append((net, x0, y0, x1, y1))
        self._book2(net, x0, y0, x1, y1)

    def free_box2(self, net, x0, y0, x1, y1) -> bool:
        """No other net's M2 (cells or routes) within the M2 space of the box (exact geometry)."""
        for n, a, b, c, d in self.exact2:
            if n == net and n:
                continue
            if a - SP < x1 and x0 < c + SP and b - SP < y1 and y0 < d + SP:
                return False
        return True

    def reachable(self, net, x0, x1, y) -> bool:
        """An M3 track can drop a VIA2 on the bar (x0, x1) at y."""
        return self._pick(net, x0 + END, x1 - END, y, y) is not None

    # ---- routing -----------------------------------------------------------------------
    def route(self, net: str, pins: list[tuple[int, int, int]]) -> None:
        """pins: (x0, x1, y) of the net's M2 bars."""
        uniq = []  # one pin per bar: shapes of one net closer than a via pitch are one bar here
        for p in sorted(set(pins), key=lambda p: -(p[1] - p[0])):
            if not any(abs(p[2] - q[2]) < P2 and p[0] < q[1] and q[0] < p[1] for q in uniq):
                uniq.append(p)
        pins = uniq
        groups = []
        for x0, x1, y in sorted(pins):
            lo, hi = x0 + END, x1 - END  # trunk centre: VIA2 enclosed along the bar
            if groups and max(groups[-1][0], lo) <= min(groups[-1][1], hi):
                g = groups[-1]
                g[0], g[1] = max(g[0], lo), min(g[1], hi)
                g[2].append(y)
            else:
                groups.append([lo, hi, [y]])
        queue, trunks = list(groups), self.trunks.setdefault(net, [])
        while queue:
            lo, hi, ys = queue.pop(0)
            m = self._pick(net, lo, hi, min(ys), max(ys))
            if m is None and len(ys) == 1:  # one pin: its bar reaches out on M2 to a free track
                m = self._reach_out(net, lo, hi, ys[0])
            if m is None and len(ys) > 1:  # split: one trunk per pin
                xs = [p for p in pins if p[2] in ys and p[0] + END <= hi and p[1] - END >= lo] or pins
                queue[:0] = [[x0 + END, x1 - END, [y]] for x0, x1, y in sorted(xs) if y in ys]
                continue
            assert m is not None, f"{net}: no M3 track in [{lo}, {hi}] for y {ys}"
            self.m3(net, m, min(ys), max(ys))
            for y in ys:
                self.via2(m * P3, y)
            trunks.append([m, min(ys) - END, max(ys) + END])
        self._join(net, trunks)
        self._bridge3(net)

    def _bridge3(self, net):
        """The net's own M3 pieces on one track closer than the M3 gap: joined into one (no notch)."""
        for m, occ in list(self.occ3.items()):
            spans = sorted((lo, hi) for lo, hi, n in occ if n == net)
            for (_, a1), (b0, _) in itertools.pairwise(spans):
                if a1 < b0 < a1 + GAP3:
                    occ.append((a1, b0, net))
                    self.rects.append(("M3", m * P3 - HW3, a1, m * P3 + HW3, b0))

    def _reach_out(self, net, lo, hi, y):
        """No free M3 track over the pin bar (x lo..hi are its via range): the nearest free track
        it can reach by an M2 extension clear of other nets' M2; the extension is drawn."""
        near = sorted(range(lo // P3 - 6, hi // P3 + 7), key=lambda m: min(abs(m * P3 - lo), abs(m * P3 - hi)))
        for m in near:
            x = m * P3
            if lo <= x <= hi or not self.free3(m, y - END, y + END, net):
                continue
            box = (x - END, y - HW2, lo - END + 1, y + HW2) if x < lo else (hi + END - 1, y - HW2, x + END, y + HW2)
            if self.free_box2(net, *box):
                self.rects.append(("M2", *box))
                self.block2(net, *box)
                return m
        return None

    def _pick(self, net, lo, hi, y0, y1):
        ms = [m for m in range(-(-lo // P3), hi // P3 + 1) if self.free3(m, *self._span(y0, y1), net)]
        mid = (lo + hi) / 2
        return min(ms, key=lambda m: abs(m * P3 - mid)) if ms else None

    def _reach(self, t, y):
        """Extra M3 for trunk t to reach track y, or None if blocked."""
        m, a, b = t
        if a + END <= y <= b - END:
            return 0
        lo, hi = self._span(b - END, y) if y > b - END else self._span(y, a + END)  # as _extend draws it
        return hi - lo if self.free3(m, lo, hi, self._net) else None

    def _extend(self, t, y):
        m, a, b = t
        if y + END > b:
            self.m3(self._net, m, b - END, y)
            t[2] = y + END
        elif y - END < a:
            self.m3(self._net, m, y, a + END)
            t[1] = y - END

    def _join(self, net, trunks):
        self._net = net
        done = trunks[:1]
        for t in trunks[1:]:
            best = None
            for u in done:
                for y in self.tracks2:
                    ct, cu = self._reach(t, y), self._reach(u, y)
                    a, b = sorted((t[0] * P3, u[0] * P3))
                    if ct is None or cu is None or not self.free2(y, a - END, b + END, net):
                        continue
                    cost = ct + cu + (b - a) // 4
                    if best is None or cost < best[0]:
                        best = (cost, u, y)
            if best is None:
                self._join_jog(net, t, done)
            else:
                _, u, y = best
                self._extend(t, y)
                self._extend(u, y)
                self.m2(net, y, t[0] * P3, u[0] * P3)
                self.via2(t[0] * P3, y)
                self.via2(u[0] * P3, y)
            done.append(t)

    def _join_jog(self, net, t, done):
        """Two bars and an M3 jog between them."""
        for u in done:
            for ya in [y for y in self.tracks2 if self._reach(t, y) is not None]:
                for yb in [y for y in self.tracks2 if y != ya and self._reach(u, y) is not None]:
                    for mj in sorted(range(1, self.w // P3), key=lambda m: abs(m - (t[0] + u[0]) / 2)):
                        if mj in (t[0], u[0]) or not self.free3(mj, *self._span(ya, yb), net):
                            continue
                        if self.free2(ya, min(t[0], mj) * P3 - END, max(t[0], mj) * P3 + END, net) and self.free2(
                            yb, min(u[0], mj) * P3 - END, max(u[0], mj) * P3 + END, net
                        ):
                            self._extend(t, ya)
                            self._extend(u, yb)
                            self.m3(net, mj, ya, yb)
                            for y, m in ((ya, t[0]), (yb, u[0])):
                                self.m2(net, y, m * P3, mj * P3)
                                self.via2(m * P3, y)
                                self.via2(mj * P3, y)
                            return
        raise AssertionError(f"{net}: cannot join trunk {t} to {done}")

    def escape(self, net: str, up: bool) -> tuple[int, int, int]:
        """Carry the net to the top (or bottom) edge on M3; returns (track, y0, y1) of the stub."""
        self._net = net
        edge = self.h if up else 0
        for t in sorted(self.trunks[net], key=lambda t: (self.h - t[2]) if up else t[1]):
            m, a, b = t
            lo, hi = (b, edge) if up else (edge, a)
            if self.free3(m, lo, hi, net):
                self.m3(net, m, b - END, edge - END) if up else self.m3(net, m, edge + END, a + END)
                self._bridge3(net)
                return m, lo, hi
        for t in self.trunks[net]:
            for y in sorted((y for y in self.tracks2 if self._reach(t, y) is not None), key=lambda y: -y if up else y):
                for m2 in sorted(range(t[0] - 30, t[0] + 31), key=lambda k: abs(k - t[0])):
                    lo, hi = (y - END, edge) if up else (edge, y + END)
                    if (
                        m2 != t[0]
                        and self.free3(m2, lo, hi, net)
                        and self.free2(y, min(t[0], m2) * P3 - END, max(t[0], m2) * P3 + END, net)
                    ):
                        self._extend(t, y)
                        self.m2(net, y, t[0] * P3, m2 * P3)
                        self.via2(t[0] * P3, y)
                        self.via2(m2 * P3, y)
                        self.m3(net, m2, y, edge - END if up else edge + END)
                        self._bridge3(net)
                        return m2, lo, hi
        raise AssertionError(f"{net}: no edge escape")
