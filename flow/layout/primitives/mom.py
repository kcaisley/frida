# ruff: noqa  -- an ALIGN PDK generator (ALIGN style), run in ALIGN's own Python
"""FMOM capacitors for ALIGN, drawn on cell_fabric grids from the PDK's numbers (``capcell``):

- ``MomUnit``: the test structures (``ring``, ``strip``, ``difference``), a generic primitive (a
  ``Generator`` constraint naming it): the fingers vertical wires on a centre-line grid of pitch
  width + spacing, the ring's bars horizontal wires on a grid of its two bar centres, the shield a
  region on the metal below (``capcell.mom_geometry``); placed side by side (``abut``), the units
  of a capacitor array, their shield's channels or columns on the metal below.

Every end, via centre and region corner sits on a nanometre stop grid. A terminal's pin becomes,
where ALIGN merges it, its finger: the pin and its label are the terminal's metal and its centre.
Every mask layer agrees shape for shape with the row-engine drawing these replaced (all six PDKs: the
36 test structures each); the pin purpose (the ``.PIN`` squares, the labels' place
on the terminal, IHP130's labels on its text layer) is ALIGN's.

    unit = MomUnit()
    unit.unit("difference", 3, length=8000, diff_length=25000)
    unit.writeGDS(open("momunit.gds", "wb"), macro_name="momunit")
"""

import json
import math
import sys
from pathlib import Path

from align.cell_fabric.generators import Region, Via, Wire
from align.cell_fabric.grid import CenterLineGrid, SingleGrid, UncoloredCenterLineGrid
from align.cell_fabric.pdk import Pdk
from align.primitive.default.canvas import DefaultCanvas

from ._pdk import DATA, ROWS as _ROWS  # the PDK's layout directory (its tech, rows.json) and the engine
import capcell


def _nm(value):
    """A coordinate on the nanometre grid, rounded half up as a klayout D-box is."""
    return math.floor(value + 0.5)


class _Fabric(DefaultCanvas):
    """A canvas on the generated PDK in nanometres: wires on centre-line grids, every end, via
    centre and region corner on a nanometre stop grid. The PDK's checkers sign it off, as the row
    cells' (``mos.py``): no via-induced short check (a unit's metals run both ways), no DRC."""

    def __init__(self, pdk=None):
        super().__init__(pdk or Pdk().load(DATA / "layers.json"))
        self.nm = SingleGrid(pitch=1)
        self.layer_stack = []
        self._regions = {}
        self.marks = set()  # the PDK's recognition layers this drawing marks

    def mark(self, name, x0, y0, x1, y1):
        """A rectangle of the PDK's annotation layer ``name``, where the PDK draws it."""
        if name in self.marks:
            self.rect(f"Ann_{name}", None, x0, y0, x1, y1)

    def rect(self, layer, net, x0, y0, x1, y1, kind="drawing"):
        """A rectangle of ``layer`` by its corners (nm, rounded as a klayout D-box), a region."""
        if layer not in self._regions:
            self._regions[layer] = self.addGen(Region(f"region_{layer}", layer, h_grid=self.nm, v_grid=self.nm))
        self.transform_and_add(self._regions[layer].segment(net, _nm(x0), _nm(y0), _nm(x1), _nm(y1), netType=kind))

    def gen_data(self, *, run_drc=False, run_pex=False, **kwargs):
        data = super().gen_data(run_drc=False, run_pex=False, **kwargs)
        if self.drc is None:
            self.drc = type("NoDRC", (), {"errors": [], "num_errors": property(lambda s: len(s.errors))})()
        # a pin on a wire becomes its terminal's metal (ALIGN merges the pin square into the finger it
        # sits on), and ALIGN's writer draws a pin on its pin purpose alone: the metal is drawn as
        # well (a region's pin sits on metal drawn apart)
        data["terminals"] += [
            {**term, "netType": "drawing"}
            for term in data["terminals"]
            if term.get("netType") == "pin" and term["layer"] not in self.rd.skip_layers
        ]
        if getattr(self, "primitive", False):
            # placed by ALIGN: its outline on the placement grid (height a whole M2 pitch, width M3's);
            # an abutting unit's from wall centre to wall centre, on a grid of its own width
            x0, y0, x1, y1 = data["bbox"]
            h, w = self.pdk["M2"]["Pitch"], self.pdk["M3"]["Pitch"]
            abut_x = getattr(self, "abut_x", None)
            if abut_x:
                x0, x1 = abut_x
            else:
                x1 = x0 + -(-(x1 - x0) // w) * w
            abut_y = getattr(self, "abut_y", None)
            if abut_y:  # a column unit: bar centre to bar centre, a whole number of tracks
                y0, y1 = abut_y
            data["bbox"] = [x0, y0, x1, y0 + -(-(y1 - y0) // h) * h]
        return data


class MomUnit(_Fabric):
    """One FMOM test structure on the PDK's top 1-3 MOM metals over its shield."""

    def generate(self, ports, netlist_parameters, netlistdir=None):
        """ALIGN's generic-primitive entry: the unit its netlist parameters name."""
        p = netlist_parameters
        self.primitive = True
        self.unit(
            str(p["style"]).lower(),
            int(p["layers"]),
            int(p["length"]),
            int(p.get("diff_length", 0)),
            int(p.get("space", 0)),
            abut=bool(int(p.get("abut", 0))),
            left=str(p.get("left", "edge")).lower(),
            right=str(p.get("right", "edge")).lower(),
            above=str(p.get("above", "edge")).lower(),
            below=str(p.get("below", "edge")).lower(),
            frame=int(p.get("frame", 0)),
            array_kind=str(p.get("array", "channels")).lower(),
            pin_band=int(p.get("pin_band", 0)),
        )

    def unit(
        self,
        style,
        layers,
        length,
        diff_length=0,
        space=0,
        *,
        abut=False,
        left="edge",
        right="edge",
        above="edge",
        below="edge",
        frame=0,
        array_kind="channels",
        pin_band=0,
    ):
        """``length`` the inner finger's (``ring``), the main finger's (``difference``) or the strips'
        (``strip``), ``diff_length`` the difference finger's, ``space`` the plates' spacing (0: the
        minimum), all in nm. A ring's shield is its ring again on the metal below (the top plate
        shielded, the inner plates open below). ``abut``: a ring's outline from the centre line of
        its left wall to its right wall's, on a placement grid of that width, so units placed side
        by side share their walls and their shields' (one top plate, one shield); else (a test
        structure) its whole ring. An abutting unit's shield is a ground grid with channels where its
        inner plates are reached from below (``_channels``), its bars joined to its neighbours'
        or apart (``left``, ``right``: ``joined``, ``apart``, ``edge``). A ring unit of a column array
        (``array_kind`` ``columns``, ``_columns``) instead runs its inner plate's metal below it down its
        column, joined to the units above and below of its stage (``above``, ``below``), its ring
        ``frame`` long inside (every row one height), the array's bottom row a band with the bars
        joining a stage's columns, its strip's pins ``pin_band`` from its bottom at most (0: along
        the whole strip)."""

        g = capcell.mom_geometry(layers, space)
        w, s, e, hold = g["width"], g["space"], g["end_gap"], g["min_length"]
        if length < hold or (style == "difference" and diff_length < hold):
            raise ValueError(f"plates shorter than {hold} nm cannot hold their vias")
        # the vertical fingers' centre lines: column 0 the left plate, 1 the next, 2 the ring's right bar
        fingers = UncoloredCenterLineGrid(pitch=w + s, width=w, offset=w // 2)
        # (terminal, column, bottom, top, via centre's height or None)
        columns = []
        bars = []  # (terminal, row of the bar grid, x0, x1)
        if style == "strip":
            columns = [("A", 0, 0, length, length - hold // 2), ("B", 1, 0, length, hold // 2)]
            height, outer = length, 2 * w + s
        elif style in ("ring", "difference"):
            height = (
                length + diff_length + 3 * e + 2 * w if style == "difference" else max(length, frame) + 2 * e + 2 * w
            )
            if abut and array_kind == "columns":  # rows abut at their bars' centres: a whole number of M2 pitches apart
                height += -(height - w) % self.pdk["M2"]["Pitch"]
            outer = 3 * w + 2 * s
            inner = "MAIN" if style == "difference" else "INNER"
            columns = [
                ("TOP", 0, 0, height, height // 2),
                ("TOP", 2, 0, height, None),
                (inner, 1, w + e, w + e + length, w + e + hold // 2),
            ]
            if style == "difference":
                top = height - w - e
                columns.append(("DIFF", 1, top - diff_length, top, top - hold // 2))
            bars = [("TOP", 0, 0, outer), ("TOP", 1, 0, outer)]
        else:
            raise ValueError(f"unknown FMOM style {style!r}")
        # the ring's bars: centre lines at the bottom bar's and the top bar's
        bar_grid = CenterLineGrid()
        bar_grid.addCenterLine(w // 2, w)
        bar_grid.addCenterLine(height - w // 2, w)
        for metal in g["metals"]:
            layer = f"M{metal}"
            vertical = self.addGen(Wire(f"mom_v{metal}", layer, "v", clg=fingers, spg=self.nm))
            for terminal, column, y0, y1, _via in columns:
                self.addWire(vertical, terminal, column, y0, y1)
            if bars:
                horizontal = self.addGen(Wire(f"mom_h{metal}", layer, "h", clg=bar_grid, spg=self.nm))
                for terminal, row, x0, x1 in bars:
                    self.addWire(horizontal, terminal, row, x0, x1)
        # each terminal's plates joined by a via per metal at its terminal end
        for metal in g["metals"][:-1]:
            via = self.addGen(
                Via(
                    f"mom_via{metal}",
                    f"V{metal}",
                    h_clg=self.nm,
                    v_clg=fingers,
                    WidthX=g["via_cut"],
                    WidthY=g["via_cut"],
                )
            )
            for terminal, column, _y0, _y1, centre in columns:
                if centre is not None:
                    self.addVia(via, terminal, column, centre)
        # every terminal a pin at its via column on the top metal; an abutting unit's inner plates
        # theirs on their channels' bars instead (``_channels``)
        array = abut and style in ("ring", "difference")
        self.columns_mode = array and style == "ring" and array_kind == "columns"
        pin = Via(
            "mom_pin", f"M{g['metals'][-1]}", h_clg=self.nm, v_clg=fingers, WidthX=g["via_cut"], WidthY=g["via_cut"]
        )
        for terminal, column, _y0, _y1, centre in columns:
            if centre is not None and not (array and column == 1):
                self.transform_and_add(pin.segment(terminal, column, centre, netType="pin"))
        # the shield on the metal below. A ring's (the top plate's) is the ring itself, its walls and
        # bars: the top plate shielded from below, the inner (bottom) plates open, their switching no
        # matter; its pin on the bottom bar. A strip's is a sheet a spacing past it on every side,
        # its pin in the margin.
        shield = self.addGen(Region("mom_shield", f"M{g['shield']}", h_grid=self.nm, v_grid=self.nm))
        ringed = style in ("ring", "difference")
        self.abut_x = (w // 2, outer - w // 2) if abut and ringed else None
        if self.abut_x:
            # ALIGN places it on multiples of its width and on M2's tracks, never mirrored: its
            # channels' bars meet its neighbours' as drawn (``left``, ``right``), its main channel
            # at the bottom over its main drivers
            self.metadata = {
                "constraints": [
                    {
                        "constraint": "PlaceOnGrid",
                        "direction": "V",
                        "pitch": self.abut_x[1] - self.abut_x[0],
                        "ored_terms": [{"offsets": [0], "scalings": [1]}],
                    },
                    {
                        "constraint": "PlaceOnGrid",
                        "direction": "H",
                        "pitch": self.pdk["M2"]["Pitch"],
                        "ored_terms": [{"offsets": [0], "scalings": [1]}],
                    },
                ]
            }
        half = max(g["grid"], s // 4)
        if array and self.columns_mode:
            self._columns(g, layers, space, columns, height, outer, left, right, above, below, pin_band)
        elif array:
            self._channels(g, layers, space, columns, height, outer, left, right)
        elif ringed:
            for x0, y0, x1, y1 in (
                (0, 0, w, height),
                (outer - w, 0, outer, height),
                (0, 0, outer, w),
                (0, height - w, outer, height),
            ):
                self.addRegion(shield, "SHIELD", x0, y0, x1, y1)
            pin_x, pin_y, half = outer // 2, w // 2, w // 2
        else:
            self.addRegion(shield, "SHIELD", -s, -s, outer + s, height + s)
            pin_x = pin_y = -(s // 2)
        if not array:
            self.transform_and_add(
                shield.segment("SHIELD", pin_x - half, pin_y - half, pin_x + half, pin_y + half, netType="pin")
            )
        # the PDK's MOM recognition, where its LVS reads this stack as a device: each inner finger one
        self.marks = set(capcell.mom_marks(layers)) if style in ("ring", "difference") else set()
        if self.marks:
            fingers_at = [(w + e, w + e + length, "main")]
            if style == "difference":
                fingers_at.append((height - w - e - diff_length, height - w - e, "diff"))
            for y0, y1, side in fingers_at:
                self._recognition(g, outer, height, y0, y1, side)
            self.mark("MOM_RECOG_SHIELD", g["grid"], g["grid"], outer - g["grid"], height - g["grid"])
        self.computeBbox()
        return self

    def _columns(self, g, layers, space, columns, height, outer, left, right, above, below, pin_band=0):
        """A ring unit of a column array, on the metal below its plates (``capcell.mom_channel``'s
        numbers), within the ring's outline. Its inner plate's strip under its inner finger, a cut up
        to the finger's root, runs down the column: joined across the shared bar to the unit above or
        below of its stage (``joined``), else stopping a line-end gap short of a ground bar across the
        unit there (another stage, ``apart``, or the array's top edge). The walls are ground lines,
        joined at the top. The array's bottom row (``below`` ``edge``) has a band under the ring: the
        frame along its bottom and a bar on a routing track that the strip comes down to, joined
        across the walls to the columns of the stage (``left``, ``right`` ``joined``), or stopping half
        a spacing short of the wall's centre line, another stage's bar beyond (``apart``); the ground
        walls stop above the bars, at the array's edges they run down to the frame. The bar is the
        terminal's pin, and its strip too: pins along it, two tracks apart, where ALIGN's router
        lands its via from below (within ``pin_band`` of the unit's bottom, where the drivers'
        rows stand under the array: a pin higher up only gives each net's router more points to
        try), and a stub on the metal below at its middle, a landing no other net takes."""
        c = capcell.mom_channel(layers, space)
        w, sp, layer = g["width"], g["space"], f"M{c['metal']}"
        pitch, offset = self._tracks(c["metal"])
        bar, wide, eol = c["bar"], c["wide"], g["end_gap"]
        inner_x = w + sp
        ends = {"joined": w // 2, "apart": w // 2 + c["space"] // 2, "edge": w + c["space"]}
        for side in (left, right, above, below):
            if side not in ends:
                raise ValueError(f"a unit's sides are joined, apart or edge: {side!r}")
        ((terminal, _column, f0, f1, centre),) = [col for col in columns if col[1] == 1]
        # the outline: bar centre to bar centre, the array's edges to the frame; the bottom row's a
        # whole number of tracks (the band under it makes it up), so the rows above abut at their
        # bars, the bar on one of the band's tracks
        y1 = height if above == "edge" else height - w // 2
        band = 0
        if below == "edge":
            band = -y1 % pitch
            while True:
                tracks = [y for y in range(-band + pitch, 0, pitch)]
                fit = [t for t in tracks if t - bar // 2 >= -band + w + wide and t + bar // 2 + wide <= 0]
                if fit:
                    track = fit[-1]
                    break
                band += pitch
        y0 = -band if below == "edge" else w // 2
        self.abut_y = (y0, y1)
        offset = (y0 + offset) % pitch  # the tracks run from the outline's bottom, placed on M2's grid

        # ground: the walls, the bars across the unit at a stage's end and the array's top edge
        wall_low = {}
        for side, x in ((left, 0), (right, outer - w)):
            low = 0 if below != "edge" else (-band if side == "edge" else track + bar // 2 + wide)
            wall_low[x] = low
            self.rect(layer, "SHIELD", x, low, x + w, height)
        if above != "joined":
            self.rect(layer, "SHIELD", 0, height - w, outer, height)
        if below == "apart":
            self.rect(layer, "SHIELD", 0, 0, outer, w)
        if below == "edge":
            self.rect(layer, "SHIELD", 0, -band, outer, -band + w)

        # the inner plate's strip down the column, its cut up to the finger's root
        lo = 0 if below == "joined" else (w + eol if below == "apart" else track)
        hi = height if above == "joined" else height - w - eol
        self.rect(layer, terminal, inner_x, lo, inner_x + w, hi)
        cut = self.addGen(
            Via(
                f"mom_column_via{c['metal']}",
                f"V{c['metal']}",
                h_clg=self.nm,
                v_clg=self.nm,
                WidthX=c["via_cut"],
                WidthY=c["via_cut"],
            )
        )
        self.addVia(cut, terminal, inner_x + w // 2, centre)
        if below == "edge":  # the bar joining the stage's columns: the pin
            x0, x1 = ends[left], outer - ends[right]
            if (x1 - x0) * bar < c["area"]:
                raise ValueError(f"a {x1 - x0} nm column bar is below M{c['metal']}'s area ({left}, {right})")
            self.rect(layer, terminal, x0, track - bar // 2, x1, track + bar // 2)
            self.rect(layer, terminal, x0, track - bar // 2, x1, track + bar // 2, "pin")
        # where the strip runs on into the unit above or below, a pin on the bar they share: ALIGN
        # sees the two units' pins meet there, the stage's columns one terminal
        if above == "joined":
            self.rect(layer, terminal, inner_x, height - w, inner_x + w, height, "pin")
        if below == "joined":
            self.rect(layer, terminal, inner_x, 0, inner_x + w, w, "pin")
        # pins along the strip (above the bar), on every other track: a driver under the array's
        # middle reaches its column there, not only at the bar
        below_v = self.pdk[f"V{c['metal'] - 1}"]
        reach = below_v["WidthY"] // 2 + below_v["VencA_H"]
        start = track + 2 * pitch if below == "edge" else lo + reach
        first = offset + -(-(start - offset) // pitch) * pitch
        last = hi - reach if not pin_band else min(hi - reach, pin_band - reach)
        for at in range(first, last + 1, 2 * pitch):
            self.rect(layer, terminal, inner_x, at - reach, inner_x + w, at + reach, "pin")
        # the shield's pin on the left wall's inner half, at a track
        mid = offset + round(((height // 2) - offset) / pitch) * pitch
        self.rect(layer, "SHIELD", w // 2, mid - w // 2, w, mid + w // 2, "pin")
        # a landing reserved at the strip's middle, a stub on the metal below: a column's units of
        # several stages share their strips' track, each unit keeps its own place on it
        self._landing(c["metal"] - 1, terminal, inner_x + w // 2, mid)

    def _landing(self, metal, terminal, x, y):
        """A stub on ``metal`` (vertical) centred on (``x``, ``y``), its metal's minimum length and
        area, joined by a cut up to the bar above, the terminal's pin."""
        m, v = self.pdk[f"M{metal}"], self.pdk[f"V{metal}"]
        hw, grid = m["Width"] // 2, capcell.tech.MFG_GRID
        area = capcell.tech.RULES.get(f"M{metal}", {}).get("area", 0)
        least = capcell._snap(-(-area // (2 * hw)), 2 * grid)  # the length that meets the area
        half = max(m["MinL"], v["WidthY"] + 2 * v["VencA_L"], least) // 2
        name = f"mom_landing_via{metal}"
        via = self.generators.get(name) or self.addGen(
            Via(name, f"V{metal}", h_clg=self.nm, v_clg=self.nm, WidthX=v["WidthX"], WidthY=v["WidthY"])
        )
        self.addVia(via, terminal, x, y)
        self.rect(f"M{metal}", terminal, x - hw, y - half, x + hw, y + half)
        self.rect(f"M{metal}", terminal, x - hw, y - half, x + hw, y + half, "pin")

    def _tracks(self, metal):
        """ALIGN's routing tracks on a horizontal ``metal`` in this unit (pitch, offset): its outline
        sits on M2's tracks (``gen_data``), so the metal's must be theirs."""
        layer = self.pdk[f"M{metal}"]
        if layer["Direction"].lower() != "h" or layer["Pitch"] != self.pdk["M2"]["Pitch"]:
            raise ValueError(f"M{metal} is no horizontal metal on M2's tracks: an array unit's pins need one")
        return layer["Pitch"], layer["Offset"]

    def _channels(self, g, layers, space, columns, height, outer, left, right):
        """An abutting unit's shield and its bottom plates' channels on the metal below its plates
        (``capcell.mom_channel``), within the ring's outline. Across the bottom (the main or inner
        finger's root) and, a difference unit, the top (the difference finger's root) a channel:
        a bar on one of the metal's routing tracks, a cut up to the finger's root, the bar the
        terminal's pin, where ALIGN's router lands its via from below. A stage's pieces' bars meet
        across their shared walls (``joined``), into one bar along the metal's tracks; another
        stage's stop half a spacing short of the wall (``apart``); at the array's edge the frame
        closes through the channel (``edge``). The rest is ground: the frame under the ring's bars,
        a bar across the unit inside each channel, and between those a grid of lines under the
        unit's columns, its walls and its inner finger, the plates' own pitch."""
        c = capcell.mom_channel(layers, space)
        w, layer = g["width"], f"M{c['metal']}"
        pitch, offset = self._tracks(c["metal"])
        up = lambda y: offset + -(-(y - offset) // pitch) * pitch  # noqa: E731
        down = lambda y: offset + (y - offset) // pitch * pitch  # noqa: E731
        bar, wide, reach = c["bar"], c["wide"], c["via_end"] + c["via_cut"] // 2
        inner_x = w + g["space"]  # the inner column's left edge
        ends = {"joined": w // 2, "apart": w // 2 + c["space"] // 2, "edge": w + c["space"]}
        if left not in ends or right not in ends:
            raise ValueError(f"a unit's sides are joined, apart or edge: {left!r}, {right!r}")
        x0, x1 = ends[left], outer - ends[right]
        if (x1 - x0) * bar < c["area"]:
            raise ValueError(f"a {x1 - x0} nm channel bar is below M{c['metal']}'s area ({left}, {right})")
        cut = self.addGen(
            Via(
                f"mom_channel_via{c['metal']}",
                f"V{c['metal']}",
                h_clg=self.nm,
                v_clg=self.nm,
                WidthX=c["via_cut"],
                WidthY=c["via_cut"],
            )
        )
        self.rect(layer, "SHIELD", 0, 0, outer, w)  # the frame under the ring's bars
        self.rect(layer, "SHIELD", 0, height - w, outer, height)
        low, high = 0, height  # the grid's ends: the frame, or a channel's inner bar
        for terminal, column, y0, y1, centre in columns:
            if column != 1:
                continue
            bottom = centre < (y0 + y1) / 2  # the finger rooted at the unit's bottom
            if bottom:
                track = up(max(w + wide + bar // 2, y0 + reach))
                ground = up(track + bar // 2 + wide + w // 2)  # the channel's inner bar
                band = (0, ground + w // 2)
                low = ground - w // 2
            else:
                track = down(min(height - w - wide - bar // 2, y1 - reach))
                ground = down(track - bar // 2 - wide - w // 2)
                band = (ground - w // 2, height)
                high = ground + w // 2
            if not y0 + reach <= track <= y1 - reach:
                raise ValueError(f"the {terminal} finger ({y1 - y0} nm) is too short for its channel")
            self.rect(layer, terminal, x0, track - bar // 2, x1, track + bar // 2)
            # the pin one wire on the bar's own track: a pin as tall as the bar gives the router
            # access on the tracks above and below it too, and a route landing there sits closer
            # to the next net's metal than the layer's spacing (the drawn bar blocks them as an
            # obstruction instead)
            half = self.pdk[layer]["Width"] // 2
            self.rect(layer, terminal, x0, track - half, x1, track + half, "pin")
            self.addVia(cut, terminal, inner_x + w // 2, track)
            # its landing reserved: a cut down from the bar at its track and a stub there on the
            # metal below, the terminal's pin, so that no other net's route takes the one track a
            # lone piece's bar has (ALIGN routes one net after another, never ripping one up)
            self._landing(c["metal"] - 1, terminal, inner_x + w // 2, track)
            self.rect(layer, "SHIELD", 0, ground - w // 2, outer, ground + w // 2)
            for side, x in ((left, 0), (right, outer - w)):  # the frame through the channel
                if side == "edge":
                    self.rect(layer, "SHIELD", x, band[0], x + w, band[1])
            if bottom:  # the shield's pin on the channel's inner bar, on a track
                self.rect(layer, "SHIELD", inner_x, ground - w // 2, inner_x + w, ground + w // 2, "pin")
        for x in (0, inner_x, outer - w):  # the grid under the walls and the inner finger
            self.rect(layer, "SHIELD", x, low, x + w, high)

    def _recognition(self, g, outer, height, y0, y1, side):
        """One U on the ring's inner halves (the bar at the finger's root and both walls to half
        height) and the inner finger's window."""
        inset, w = g["grid"], g["width"]
        band_height = w / 2 - 2 * inset
        if side == "main":
            band0 = w / 2 + inset
            leg0, leg1 = band0, height / 2 - inset
        else:
            band0 = height - w + inset
            leg0, leg1 = height / 2 + inset, band0 + band_height
        left0, left1 = w / 2 + inset, w - inset
        right0, right1 = outer - w + inset, outer - w / 2 - inset
        self.mark("MOM_RECOG", left0, band0, right1, band0 + band_height)
        self.mark("MOM_RECOG", left0, leg0, left1, leg1)
        self.mark("MOM_RECOG", right0, leg0, right1, leg1)
        inner_x = w + g["space"]
        self.mark("MOM_RECOG_INNER", inner_x - inset, y0 - inset, inner_x + w + inset, y1 + inset)
