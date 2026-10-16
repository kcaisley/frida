# ruff: noqa  -- a fill-in template: rowtemplates.py replaces the __NAMES__ before it runs
# A design in standard-cell rows for the hosted laygo server: transistors as row cells (stems), logic as
# the PDK's standard cells. TEMPLATE: rowtemplates.py fills in the __NAMES__ from a floorplan
# (design/layout/<design>.json) and the PDK's tech values, and writes <design>.py.
# Technology: <design>_laygo.yaml from rowtemplates.py, one fixed template per instance with its
# pins named after their nets; post.py swaps in the PDK's cells.
# The following imports are done automatically on the server. No further imports are allowed.
# import laygo2
# import laygo2_tech as tech
# import numpy as np

libname = "frida"
cellname = "__CELLNAME__"

templates, grids = tech.load_templates_and_grids()
pg, r23 = grids["placement_basic"], grids["routing_23_cmos"]
dsn = laygo2.Design(name=cellname, libname=libname, pgrid=pg, rgrid=r23)

# Rows, top first, each mirrored about the centre: the left half as drawn, the right half flipped (MY).
# Every cell carries both rails (VSS at the bottom in R0); rows alternate R0 / MX so they share rails,
# VSS on even rail lines, VDD on odd ones. Fillers (rails and taps) close each row to the block width;
# edge cells (three M3 pitches) at both ends drop the rails to the M3 supply trunks (vss one pitch,
# vdd two pitches from the block edge).
ROWS = __ROWS__
PINS = __PINS__  # template pins (= net names), from rowtemplates.py
TECH = __TECH__  # the PDK's row and routing values (nm), from rowtemplates.py
H, PITCH, END, HW2, SP, MIN = TECH["H"], TECH["PITCH"], TECH["END"], TECH["HW2"], TECH["SP"], TECH["MIN"]
NROWS = len(ROWS)
width = lambda name: templates[name].size()[0]
widths = [sum(width(n) for n in row) for row in ROWS]
W = max(widths)
devices, placed = [], []
for i, row in enumerate(ROWS):
    r = NROWS - 1 - i  # laygo rows count from the bottom
    flip = r % 2 == 1
    half = len(row) // 2
    insts = []
    left = (W - widths[i]) // (2 * TECH["XPITCH"]) * TECH["XPITCH"]
    right = W - widths[i] - left
    fill = "stdfill" if all(n.startswith("X") for n in row) else "fill"  # standard-cell rows take FILL1 cells
    edge = ("stdedge_" if fill == "stdfill" else "edge_") + str(TECH["EDGE_W"])
    insts.append(templates[edge].generate(name=f"EDGE{r}L", transform="MX" if flip else "R0"))
    if left:
        insts.append(templates[f"{fill}_{left}"].generate(name=f"FILL{r}L", transform="MX" if flip else "R0"))
    for j, name in enumerate(row):
        mirror = j >= len(row) - half
        t = {(False, False): "R0", (True, False): "MX", (False, True): "MY", (True, True): "R180"}[(flip, mirror)]
        d = templates[name].generate(name=name, transform=t, netmap={p: p for p in PINS[name]})
        insts.append(d)
        devices.append(d)
    if right:
        insts.append(templates[f"{fill}_{right}"].generate(name=f"FILL{r}R", transform="MX" if flip else "R0"))
    insts.append(templates[edge].generate(name=f"EDGE{r}R", transform="R180" if flip else "MY"))
    dsn.place(grid=pg, inst=[insts], mn=[0, r], pattern="stripe")
    placed.append(insts)

# ---- routing: one M3 trunk per group of x-overlapping pins, placed inside the overlap so that
# route_net only drops vias (an M2 branch would cross the neighbouring devices' pins on the same
# track). Groups of a net are joined by M2 bars on the free in-row tracks. M3 tracks and M2 routing tracks
# are booked over the y (resp. x) range they actually use, so different nets can share a track.
P3 = TECH["M3_PITCH"]  # M3 track pitch (routing_23_cmos vertical)
GAPS = {
    "m3": TECH["GAP3"],
    "m2": -(-(2 * END + SP) // 50) * 50,
}  # keep-out around booked segments: via pads reach END past a segment, then the line-end space
bbox = dsn.bbox
TOP = NROWS * H
occ3, occ2 = {}, {}
# M2 tracks for the bars: every track of every row except the rails, i.e. the free track above the
# gates, the gate-side row boundaries, and the device rows' own S/D/G tracks wherever no pin is
# (between devices, over tied sources). Pins and route_net's own M2 are kept in m2pins.
ROUTE_YS = [r * H + o for r in range(NROWS) for o in range(PITCH, H, PITCH)]
m2pins = {}  # y -> [(x0, x1)] drawn M2 that is not a bar


def block_m2(xy):
    (x0, y0), (x1, y1) = xy
    half, c = abs(y1 - y0) / 2, (y0 + y1) / 2  # every track whose bar would come within the M2 space
    for y in range(int(c - half - HW2 - SP) // PITCH * PITCH, int(c + half + HW2 + SP) + 1, PITCH):
        if abs(y - c) < half + HW2 + SP:
            m2pins.setdefault(y, []).append((min(x0, x1) - END, max(x0, x1) + END))


pinbars = {}  # y -> [(x0, x1, net)]: the cells' M2 pins
for row in placed:
    for inst in row:
        for name, pin in inst.pins.items():
            if pin.layer[0] == "Metal2":
                block_m2(pin.xy)
                (x0, y), (x1, _) = pin.xy
                pinbars.setdefault(y, []).append((min(x0, x1), max(x0, x1), name))


def free(occ, k, a, b):  # a net's own bookings never block it
    g = GAPS["m2" if occ is occ2 else "m3"]
    return all(b + g < lo or a - g > hi for lo, hi, net in occ.get(k, []) if net != current[0])


def end_clash(y, a, b):  # a bar end next to a bar on a neighbouring routing track (M2 dense line-end rule)
    if not TECH["LINE_END"]:
        return False
    near = lambda x, lo, hi: lo - GAPS["m2"] <= x <= hi + GAPS["m2"]
    return any(
        near(a, lo, hi) or near(b, lo, hi) or near(lo, a, b) or near(hi, a, b)
        for yy in ROUTE_YS
        if 0 < abs(yy - y) <= PITCH
        for lo, hi, _ in occ2.get(yy, [])
    )


def book(occ, k, a, b):
    occ.setdefault(k, []).append((a, b, current[0]))


current = ["supply"]
drawn = {}  # net -> M3 trunks actually drawn: (track, y0, y1)
# the cells' own M3 (jumpers, far-rail ties: rowtemplates.py's "<net>__m3_<k>" keep-outs), booked on
# their tracks as their nets', so only a route of the same net comes near them
for row in placed:
    for inst in row:
        for name, pin in inst.pins.items():
            if pin.layer[0] == "Metal3" and "__m3_" in name:
                (x0, y0), (x1, y1) = pin.xy
                occ3.setdefault(round((x0 + x1) / 2 / P3), []).append(
                    (min(y0, y1), max(y0, y1), name.split("__m3_")[0])
                )


routed2 = {}  # y -> [(x0, x1, net)]: route_net's M2 so far (each pin's branch to its trunk)


def branch_ok(m, members, pins=True):  # route_net's M2 from each pin to a trunk past its end, and the via pad,
    for lo, hi, y, d in members:  # keep the M2 space to other nets' pins on the pin's track, and to any
        a, b = min(lo, m * P3 - END), max(hi, m * P3 + END)  # pin on a track closer than a bar and a space
        for yy, bars in pinbars.items():  # (half-pitch pin tracks), the net's own unless it touches them
            if not pins or abs(yy - y) >= 2 * HW2 + SP:  # (pins: False for a trunk over its pins, which keep
                continue  # their spaces already)
            for x0, x1, n in bars:
                near = a - SP < x1 and x0 < b + SP
                joined = n == current[0] and a <= x1 and x0 <= b and abs(yy - y) <= 2 * HW2
                if near and (n != current[0] or (yy != y and not joined)):
                    return False
        yc = sum(xy[1] for xy in d.pins[current[0]].xy) / 2  # and to other nets' branches and bars on its track
        segs = [s for yy, ss in routed2.items() if abs(yy - yc) < PITCH / 2 for s in ss]
        segs += [(x0 - END, x1 + END, n) for yy, ss in occ2.items() if abs(yy - yc) < PITCH / 2 for x0, x1, n in ss]
        if any(a - SP < x1 and x0 < b + SP for x0, x1, n in segs if n != current[0]):
            return False
    return True


def pick(lo, hi, y0, y1, pad=0, members=()):
    mid = (lo + hi) / 2
    ms = [
        m
        for m in range(max(-(-(lo - pad) // P3), xl0 + 1), min((hi + pad) // P3, xr0 - 1) + 1)  # inside the block
        # a trunk over its pins still puts a via pad there: other nets' branches and bars stay clear of it
        if free(occ3, m, y0, y1) and branch_ok(m, members, pins=bool(pad))
    ]
    return min(ms, key=lambda m: abs(m * P3 - mid)) if ms else None


M3LOG = []  # (net, track, y0, y1, source): every M3 drawn, for the final check


def m3(m, ya, yb, why="m3"):  # an M3 segment on track m between two routing_23 y positions
    M3LOG.append((current[0], m, min(ya, yb) - END, max(ya, yb) + END, why))
    return dsn.route(grid=r23, mn=[r23.mn([m * P3, ya]), r23.mn([m * P3, yb])], via_tag=[False, False])


def m2bar(ma, mb, y):  # an M2 bar on a routing track with M2-M3 vias at both ends
    a, b = sorted((ma, mb))
    dsn.via(grid=r23, mn=r23.mn([a * P3, y]))
    dsn.via(grid=r23, mn=r23.mn([b * P3, y]))
    return dsn.route(grid=r23, mn=[r23.mn([a * P3, y]), r23.mn([b * P3, y])], via_tag=[False, False])


# supply rails: VSS on even rail lines, VDD on odd ones (M2 straps in every cell)
rail_ys = {"vss": {k * H for k in range(0, NROWS + 1, 2)}, "vdd": {k * H for k in range(1, NROWS + 1, 2)}}
for net in ("vss", "vdd"):
    for y in rail_ys[net]:
        current[0] = net
        book(occ2, y, -(10**6), 10**6)
# supply trunks joining each net's rails: M3 over the edge cells, which hold the rail vias
xl0, xr0 = -(-bbox[0][0] // P3), bbox[1][0] // P3
supply = {}
K = TECH["EDGE_STEP"] // P3  # the edge cells' supply pads sit one and two edge steps in (netcells.EDGE_STEP)
for net, (ml, mr) in (("vss", (xl0 + K, xr0 - K)), ("vdd", (xl0 + 2 * K, xr0 - 2 * K))):
    ys = sorted(rail_ys[net])
    current[0] = net
    for m in (ml, mr):
        book(occ3, m, 0, NROWS * H)
        supply.setdefault(net, m3(m, 0, NROWS * H))
        for y in ys:
            dsn.via(grid=r23, mn=r23.mn([m * P3, y]))


def flat(r):  # route_net returns nested lists of Rects and via Instances
    if isinstance(r, (list, tuple)):
        return [o for x in r for o in flat(x)]
    return [r] if hasattr(r, "layer") and r.layer is not None else []


def pins_of(net):
    return [(d, net) for d in devices if net in d.pins]


def xspan(pin):
    return min(pin.xy[0][0], pin.xy[1][0]), max(pin.xy[0][0], pin.xy[1][0])


def connect(net):
    current[0] = net
    groups = []  # greedy sweep over pins sorted by x: start a new group when the overlap vanishes
    for d, t in sorted(pins_of(net), key=lambda p: xspan(p[0].pins[p[1]])[0]):
        lo, hi = xspan(d.pins[t])
        y = d.pins[t].xy[0][1]
        if groups and max(groups[-1][0], lo) <= min(groups[-1][1], hi):
            g = groups[-1]
            g[0], g[1] = max(g[0], lo), min(g[1], hi)
            g[2], g[3] = min(g[2], y), max(g[3], y)
            g[4].append(d)
            g[5].append((lo, hi, y, d))
        else:
            groups.append([lo, hi, y, y, [d], [(lo, hi, y, d)]])
    trunks = drawn.setdefault(net, [])
    queue = list(groups)
    while queue:
        lo, hi, y0, y1, nodes, members = queue.pop(0)
        # the trunk spans its pins' tracks (checked against what route_net draws below)
        if y1 - y0 < MIN - 2 * END:  # a short trunk grows to the M3 area (below, about its middle): room for it
            need = -(-(MIN - 2 * END) // PITCH) * PITCH
            a = y0 - need // 2 // PITCH * PITCH
            grown = (a - END - HW2 - 10, a + need + END + HW2 + 10)
        else:
            grown = (y0, y1)
        y0, y1 = (
            min(y0 - PITCH - END - 10, grown[0]),
            max(y1 + PITCH + END + 10, grown[1]),
        )  # route_net runs a trunk ~a track past its pins, plus the via pad
        # a net with several trunks needs each to reach an M2 routing track: take a track free up to
        # the nearest one as well, and reserve that access now
        ranges = [(y0, y1)]
        if len(groups) > 1 and not any(y0 <= y <= y1 for y in ROUTE_YS):
            ranges = sorted(
                ((y0, min(y for y in ROUTE_YS if y > y1)) for _ in [0] if any(y > y1 for y in ROUTE_YS)),
                key=lambda r: r[1] - r[0],
            ) + sorted(
                ((max(y for y in ROUTE_YS if y < y0), y1) for _ in [0] if any(y < y0 for y in ROUTE_YS)),
                key=lambda r: r[1] - r[0],
            )
            ranges.sort(key=lambda r: r[1] - r[0])
        m = None
        for pad in (0, 2 * P3):
            for a, b in ranges:
                m = pick(lo, hi, a, b, pad, members)
                if m is not None:
                    y0, y1 = a, b
                    break
            if m is not None:
                break
        if m is None and len(members) > 1:  # no track over the whole group: one trunk per pin, joined by bars
            queue[:0] = [[l, h, y, y, [d], [(l, h, y, d)]] for l, h, y, d in members]
            groups.extend(queue[: len(members)])
            continue
        if m is None:
            assert False, f"no free M3 track for {net} in x [{lo}, {hi}] y [{y0}, {y1}] " + str(
                {k: v for k, v in occ3.items() if abs(k * P3 - lo) < 900}
            )
        r = dsn.route_net(netname=net, nodes=nodes, track=[m, None])
        for o in flat(r):
            if o.layer[0] == "Metal3":
                M3LOG.append((net, m, min(o.xy[0][1], o.xy[1][1]), max(o.xy[0][1], o.xy[1][1]), f"route_net {y0} {y1}"))
            if o.layer[0] == "Metal2":
                block_m2(o.xy)
        # route_net returns only the trunk; its M2 from each pin's centre to the via at the trunk, and
        # the via pad, booked like pins
        for lo_, hi_, yp, d in members:
            xc, yc = (lo_ + hi_) / 2, sum(xy[1] for xy in d.pins[net].xy) / 2
            block_m2([[min(xc, m * P3 - END), yp], [max(xc, m * P3 + END), yp]])
            routed2.setdefault(yc, []).append((min(xc, m * P3) - END, max(xc, m * P3) + END, net))
        ys = [y for o in flat(r) if o.layer[0] == "Metal3" for y in (o.xy[0][1], o.xy[1][1])]
        assert free(occ3, m, min(ys), max(ys)), f"{net}: trunk on {m} [{min(ys)}, {max(ys)}] hits " + str(occ3.get(m))
        if max(ys) - min(ys) < MIN - 2 * END:  # a short trunk (one pin): grown on its track to the M3 area
            need = -(-(MIN - 2 * END) // PITCH) * PITCH
            for a in (min(ys), max(ys) - need, min(ys) - need // 2 // PITCH * PITCH):
                if free(occ3, m, a - END, a + need + END):
                    m3(m, a, a + need, "area")
                    ys += [a, a + need]
                    break
        book(occ3, m, min(ys + [y0]), max(ys + [y1]))
        trunks.append((m, min(ys), max(ys)))  # bars and extensions attach to what was drawn
    # join the trunks spanning-tree style: each trunk gets an M2 bar on a routing track to the cheapest
    # already connected trunk, on the free routing track that needs the least M3 extension
    join(net, trunks)
    # trunks of the net on one track closer than the M3 space: one piece (no notch)
    on = {}
    for m, y0, y1 in trunks:
        on.setdefault(m, []).append((y0, y1))
    for m, spans in on.items():
        spans.sort()
        for (a0, a1), (b0, b1) in zip(spans, spans[1:]):
            if a1 < b0 < a1 + GAPS["m3"]:
                m3(m, a1 - END, b0 + END)


def extension(t, y):  # M3 span to add so trunk t = (m, y0, y1) reaches y, or None
    m, y0, y1 = t
    return None if y0 <= y <= y1 else (y1, y) if y > y1 else (y, y0)


def reach(t, y):  # M3 length to add so trunk t reaches routing track y, or None if blocked
    e = extension(t, y)
    if not e:
        return 0
    return e[1] - e[0] if free(occ3, t[0], *e) else None  # the net's own segments never block it


def bar_ok(y, ma, mb):
    a, b = sorted((ma, mb))
    clear = all(b * P3 + TECH["CLEAR"] < x0 or a * P3 - TECH["CLEAR"] > x1 for x0, x1 in m2pins.get(y, []))
    return clear and free(occ2, y, a * P3, b * P3) and not end_clash(y, a * P3, b * P3)


def extend(t, y):
    e = extension(t, y)
    if e:
        book(occ3, t[0], *e)
        m3(t[0], *e)


def draw_bar(ma, mb, y):
    a, b = sorted((ma, mb))
    book(occ2, y, a * P3, b * P3)
    if a != b and (b - a) * P3 + 2 * END < MIN:  # a bar too short for the M2 area: carry it a track further
        b2 = b + 1 if bar_ok(y, a, b + 1) else a - 1
        book(occ2, y, min(a, b2) * P3, max(b, b2) * P3)
        lo, hi = min(a, b2), max(b, b2)
        dsn.via(grid=r23, mn=r23.mn([a * P3, y]))
        dsn.via(grid=r23, mn=r23.mn([b * P3, y]))
        dsn.route(grid=r23, mn=[r23.mn([lo * P3, y]), r23.mn([hi * P3, y])], via_tag=[False, False])
    elif a != b:
        m2bar(a, b, y)
    # a == b: both trunks on one track, extended to y, meet on M3 (a via there would only leave an
    # M2 pad below the minimum area)


def jog_span(ya, yb):  # the M3 of a jog between routing tracks ya and yb, at least the M3 area long
    lo, hi = sorted((ya, yb))
    if hi - lo < MIN - 2 * END:
        need = -(-(MIN - 2 * END) // PITCH) * PITCH
        lo -= (need - (hi - lo)) // 2 // PITCH * PITCH
        hi = lo + need
    return lo, hi


def join(net, trunks):
    done = trunks[:1]
    for t in trunks[1:]:
        options = []
        for u in done:
            for y in ROUTE_YS:
                ct, cu = reach(t, y), reach(u, y)
                if ct is not None and cu is not None and bar_ok(y, t[0], u[0]):
                    options.append((ct + cu + abs(t[0] - u[0]) * P3 // 4, u, y))
        if options:
            _, u, y = min(options, key=lambda o: o[0])
            extend(t, y)
            extend(u, y)
            draw_bar(t[0], u[0], y)
            done.append(t)
            continue
        # two bends: bar from t to a free M3 jog track, jog to another routing track, bar to u
        jog = None
        for u in done:
            for ya in [y for y in ROUTE_YS if reach(t, y) is not None]:
                for yb in [y for y in ROUTE_YS if y != ya and reach(u, y) is not None]:
                    lo, hi = jog_span(ya, yb)
                    for mj in sorted(
                        range(min(t[0], u[0]) - 40, max(t[0], u[0]) + 41), key=lambda m: abs(m - (t[0] + u[0]) / 2)
                    ):
                        if (
                            mj not in (t[0], u[0])
                            and xl0 < mj < xr0
                            and free(occ3, mj, lo - GAPS["m3"], hi + GAPS["m3"])
                            and bar_ok(ya, t[0], mj)
                            and bar_ok(yb, u[0], mj)
                        ):
                            jog = (u, ya, yb, mj)
                            break
                    if jog:
                        break
                if jog:
                    break
            if jog:
                break
        if not jog:  # say why, per routing track near the trunks
            why = []
            for y in ROUTE_YS:
                if abs(y - t[1]) < 2 * H:
                    a, b = sorted((t[0], done[0][0]))
                    clear = all(
                        b * P3 + TECH["CLEAR"] < x0 or a * P3 - TECH["CLEAR"] > x1 for x0, x1 in m2pins.get(y, [])
                    )
                    why.append(
                        (
                            y,
                            reach(t, y),
                            reach(done[0], y),
                            clear,
                            free(occ2, y, a * P3, b * P3),
                            not end_clash(y, a * P3, b * P3),
                        )
                    )
            assert jog, f"no M2 route for {net}: t={t} done={done} " + str(why)
        u, ya, yb, mj = jog
        extend(t, ya)
        extend(u, yb)
        book(occ3, mj, *jog_span(ya, yb))
        m3(mj, *jog_span(ya, yb))
        draw_bar(t[0], mj, ya)
        draw_bar(u[0], mj, yb)
        done.append(t)


# most constrained first: the standard-cell nets, then the rest, the escaping inputs last
nets = __NETS__
for net in nets:
    connect(net)


# ---- block boundary: power on the M3 supply trunks, the ports leave at the top or bottom edge (as
# the floorplan says), each on an M3 stub that ends on the edge
def escape(net, up):
    current[0] = net
    ts = sorted(drawn[net], key=lambda t: (TOP - t[2]) if up else t[1])
    for m, y0, y1 in ts:  # straight on: the trunk's own track to the edge
        a, b = (y1, TOP) if up else (0, y0)
        if free(occ3, m, a, b):
            book(occ3, m, a, b)
            return m3(m, y1, TOP) if up else m3(m, 0, y0)
    for t in ts:  # an M2 bar to a free M3 track, then straight on
        for y in sorted((y for y in ROUTE_YS if reach(t, y) is not None), key=lambda y: -y if up else y):
            lo, hi = (y, TOP) if up else (0, y)
            if hi - lo < MIN - 2 * END:  # a stub short of the M3 area: on past the bar, away from the edge
                need = -(-(MIN - 2 * END) // PITCH) * PITCH
                lo, hi = (TOP - need, TOP) if up else (0, need)
            for m2 in sorted(range(t[0] - 30, t[0] + 31), key=lambda k: abs(k - t[0])):
                if m2 != t[0] and xl0 < m2 < xr0 and bar_ok(y, t[0], m2) and free(occ3, m2, lo, hi):
                    extend(t, y)
                    draw_bar(t[0], m2, y)
                    book(occ3, m2, lo, hi)
                    return m3(m2, lo, hi)
    assert False, f"no edge escape for {net}"


for net, up in __ESCAPES__:
    dsn.pin(name=net, mn=escape(net, up))
for net, trunk in supply.items():
    dsn.pin(name=net, mn=trunk)

# every pair of different nets' M3 on one track keeps the M3 space
bad = []
for i, (na, ma, a0, a1, wa) in enumerate(M3LOG):
    for nb, mb, b0, b1, wb in M3LOG[i + 1 :]:
        if ma == mb and na != nb and a0 < b1 + SP and b0 < a1 + SP:
            bad.append(((na, a0, a1, wa), (nb, b0, b1, wb), ma))
assert not bad, f"M3 too close: {bad[:4]} " + str([e for e in M3LOG if e[1] == bad[0][2]])

# Export command will be automatically added by the webserver.
