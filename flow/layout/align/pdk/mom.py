# ruff: noqa  -- an ALIGN PDK generator (ALIGN style), run in ALIGN's own Python
"""FMOM capacitors for ALIGN, drawn on cell_fabric grids from the PDK's numbers (``capcell``):

- ``MomUnit``: the test structures (``ring``, ``strip``, ``difference``), a generic primitive (a
  ``Generator`` constraint naming it): the fingers vertical wires on a centre-line grid of pitch
  width + spacing, the ring's bars horizontal wires on a grid of its two bar centres, the shield a
  region on the metal below (``capcell.mom_geometry``);
- ``DifferenceUnit``: a CDAC unit of one weight, ring and fingers the same way, its shield mesh,
  landings and recognition regions, its access cuts vias on the nanometre grid
  (``capcell.difference_geometry``);
- ``ArrayWiring``: a CDAC's top over its placed units (``capcell.caparray_plan``), its buses,
  top-plate stack and shield taps.

Every end, via centre and region corner sits on a nanometre stop grid. A terminal's pin becomes,
where ALIGN merges it, its finger: the pin and its label are the terminal's metal and its centre.
Every mask layer agrees shape for shape with the stems drawing these replaced (all six PDKs: the
36 test structures and six arrays each); the pin purpose (the ``.PIN`` squares, the labels' place
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

_STEMS = json.loads((Path(__file__).resolve().parent / "stems.json").read_text())  # written by make_pdk.py
sys.path[:0] = [_STEMS["layout"], _STEMS["stems"]]  # the PDK's tech and paths, then the engine
import capcell


def _nm(value):
    """A coordinate on the nanometre grid, rounded half up as a klayout D-box is."""
    return math.floor(value + 0.5)


class _Fabric(DefaultCanvas):
    """A canvas on the generated PDK in nanometres: wires on centre-line grids, every end, via
    centre and region corner on a nanometre stop grid. The PDK's checkers sign it off, as the row
    cells' (``mos.py``): no via-induced short check (a unit's metals run both ways), no DRC."""

    def __init__(self, pdk=None):
        super().__init__(pdk or Pdk().load(Path(__file__).resolve().parent / "layers.json"))
        self.nm = SingleGrid(pitch=1)
        self.layer_stack = []
        self._regions = {}

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
        return data


class MomUnit(_Fabric):
    """One FMOM test structure on the PDK's top 1-3 MOM metals over its shield."""

    def generate(self, ports, netlist_parameters, netlistdir=None):
        """ALIGN's generic-primitive entry: the unit its netlist parameters name."""
        p = netlist_parameters
        self.unit(p["style"], int(p["layers"]), int(p["length"]), int(p.get("diff_length", 0)), int(p.get("space", 0)))

    def unit(self, style, layers, length, diff_length=0, space=0):
        """``length`` the inner finger's (``ring``), the main finger's (``difference``) or the strips'
        (``strip``), ``diff_length`` the difference finger's, ``space`` the plates' spacing (0: the
        minimum), all in nm."""

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
            height = length + diff_length + 3 * e + 2 * w if style == "difference" else length + 2 * e + 2 * w
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
        # every terminal a pin at its via column on the top metal
        pin = Via(
            "mom_pin", f"M{g['metals'][-1]}", h_clg=self.nm, v_clg=fingers, WidthX=g["via_cut"], WidthY=g["via_cut"]
        )
        for terminal, column, _y0, _y1, centre in columns:
            if centre is not None:
                self.transform_and_add(pin.segment(terminal, column, centre, netType="pin"))
        # the shield on the metal below, a spacing past the unit on every side, its pin in the margin
        shield = self.addGen(Region("mom_shield", f"M{g['shield']}", h_grid=self.nm, v_grid=self.nm))
        self.addRegion(shield, "SHIELD", -s, -s, outer + s, height + s)
        corner, half = -(s // 2), max(g["grid"], s // 4)
        self.transform_and_add(
            shield.segment("SHIELD", corner - half, corner - half, corner + half, corner + half, netType="pin")
        )
        self.computeBbox()
        return self


class DifferenceUnit(_Fabric):
    """One weighted CDAC unit (``capcell.difference_geometry``'s numbers): a ring, the top plate,
    around a main finger from the bottom and a difference finger from the top on every active
    metal, over a shield mesh, each inner finger's access (landings and vias) down to the route
    metal at its outer end."""

    def unit(self, g, route, shield, active, weight, tied=False, unary_length=None, strip=True, marks=()):
        """Weight 0: an edge dummy, its inner fingers floating or, ``tied``, joined to the ring at
        their outer ends (no access). ``unary_length``: one main finger that long and no
        difference finger. The geometry ``g`` is ``capcell.difference_geometry``'s (nm);
        ``strip`` the shield's strip under the fingers, ``marks`` the recognition layers the PDK
        draws (``capcell.caparray_plan``)."""

        width, height, ring = g["outer_width"], g["outer_height"], g["ring_width"]
        finger, gap = g["finger_width"], g["gap"]
        if finger != ring or finger % 2:
            raise ValueError("the ring and the fingers share one even width")
        inner_y0 = ring + g["end_gap"]
        bottom_y1 = inner_y0 + g["nominal_length"] + weight * g["weight_step"]
        top_y0 = bottom_y1 + g["end_gap"]
        top_y1 = height - ring - g["end_gap"]
        tied = tied and not weight
        if unary_length:
            if not g["tail_length"] <= unary_length <= top_y1 - inner_y0:
                raise ValueError(f"a unary finger of {unary_length} nm does not fit its unit")
            bottom_y1 = inner_y0 + unary_length
        main, diff = ("TOP", "TOP") if tied else ("MAIN", "DIFF")
        # the vertical lines: column 0 the ring's left wall, 1 the inner fingers, 2 its right wall
        columns = UncoloredCenterLineGrid(pitch=finger + gap, width=finger, offset=finger // 2)
        # the ring's bars: centre lines at the bottom bar's and the top bar's
        bars = CenterLineGrid()
        bars.addCenterLine(ring // 2, ring)
        bars.addCenterLine(height - ring // 2, ring)
        for metal in active:
            vertical = self.addGen(Wire(f"unit_v{metal}", f"M{metal}", "v", clg=columns, spg=self.nm))
            horizontal = self.addGen(Wire(f"unit_h{metal}", f"M{metal}", "h", clg=bars, spg=self.nm))
            for row in (0, 1):
                self.addWire(horizontal, "TOP", row, 0, width)
            for column in (0, 2):
                self.addWire(vertical, "TOP", column, ring, height - ring)
            self.addWire(vertical, main, 1, ring if tied else inner_y0, bottom_y1)
            if not unary_length:
                self.addWire(vertical, diff, 1, top_y0, height - ring if tied else top_y1)
        # the PDK's MOM recognition, where its LVS recognizes the unit as a device
        self.marks = set(marks)
        if weight and "MOM_RECOG" in self.marks:
            self._recognition(g, inner_y0, bottom_y1, "main")
            if not unary_length:
                self._recognition(g, top_y0, top_y1, "diff")
            inset = g["grid"]
            bridges = g["shield_bridge_ys"]
            self.mark("MOM_RECOG_SHIELD", inset, bridges[0] + inset, width - inset, bridges[-1] + ring - inset)
        self._shield(g, f"M{shield}", shared_routing=route == shield, strip=strip)
        if not tied:
            access_x, bottom, top = capcell.access_centers(g)
            extension = (g["landing_long"] - g["via_landing"]) / 2
            accesses = [("MAIN", bottom, bottom + extension)]
            if not unary_length:
                accesses.append(("DIFF", top, top - extension))
            for net, access_y, landing_y in accesses:
                for metal in range(route, active[0]):
                    self.landing(f"M{metal}", net, access_x, landing_y, g)
                for lower in range(route, active[-1]):
                    self.vias(f"V{lower}", net, access_x, access_y, g)
        self.computeBbox()
        return self

    def mark(self, name, x0, y0, x1, y1):
        """A rectangle of the PDK's annotation layer ``name``, where the PDK draws it."""
        if name in self.marks:
            self.rect(f"Ann_{name}", None, x0, y0, x1, y1)

    def landing(self, layer, net, x, y, g, *, horizontal=False):
        """A via landing about (x, y): the short side across the line, the long side along it."""
        short, long = g["landing_short"], g["landing_long"]
        w, h = (long, short) if horizontal else (short, long)
        self.rect(layer, net, x - w / 2, y - h / 2, x + w / 2, y + h / 2)

    def vias(self, layer, net, x, y, g, *, rows=2, columns=1):
        """``rows`` by ``columns`` cuts about (x, y) at the via pitch, each centred on the
        nanometre grid (the geometry's widths and pitches are even)."""
        cut, pitch = g["via_cut"], g["via_pitch"]
        if cut % 2:
            raise ValueError(f"a via cut of {cut} nm has no centre on the nanometre grid")
        name = f"cut_{layer}"
        if name not in self.generators:
            self.addGen(Via(name, layer, h_clg=self.nm, v_clg=self.nm, WidthX=cut, WidthY=cut))
        for row in range(rows):
            for column in range(columns):
                cx = x + (column - (columns - 1) / 2) * pitch
                cy = y + (row - (rows - 1) / 2) * pitch
                if cx != int(cx) or cy != int(cy):
                    raise ValueError(f"a via at ({cx}, {cy}) is off the nanometre grid")
                self.addVia(self.generators[name], net, int(cx), int(cy))

    def _shield(self, g, layer, *, shared_routing, strip):
        """A mesh of longitudinal strips and bridges, open corridors for the access landings."""
        width, height, ring = g["outer_width"], g["outer_height"], g["ring_width"]
        inner_x = ring + g["gap"]
        if shared_routing:
            bottom, top = g["shield_bridge_ys"][0], g["shield_bridge_ys"][-1] + ring
            inner_bottom, inner_top = bottom, top
        else:
            bottom, top = 0, height
            inner_bottom = ring + 2 * g["end_gap"] + g["landing_long"]
            inner_top = height - inner_bottom
            self.rect(layer, "SHIELD", 0, 0, width, ring)
            self.rect(layer, "SHIELD", 0, height - ring, width, height)
        self.rect(layer, "SHIELD", 0, bottom, ring, top)
        self.rect(layer, "SHIELD", width - ring, bottom, width, top)
        if strip:
            self.rect(layer, "SHIELD", inner_x, inner_bottom, inner_x + g["finger_width"], inner_top)
        for y in g["shield_bridge_ys"]:
            self.rect(layer, "SHIELD", 0, y, width, y + ring)

    def _recognition(self, g, y0, y1, side):
        """One U on the outer ring and the inner finger's window. Adjacent units own opposite halves
        of a shared ring wall: the two Us end either side of its midpoint."""
        inset, ring, pitch, height = g["grid"], g["ring_width"], g["unit_pitch"], g["outer_height"]
        left0, left1 = ring / 2 + inset, ring - inset
        right0, right1 = pitch + inset, pitch + ring / 2 - inset
        band_height = ring / 2 - 2 * inset
        if side == "main":
            band0 = ring / 2 + inset
            leg0, leg1 = band0, height / 2 - inset
        else:
            band0 = height - ring + inset
            leg0, leg1 = height / 2 + inset, band0 + band_height
        self.mark("MOM_RECOG", left0, band0, right1, band0 + band_height)
        self.mark("MOM_RECOG", left0, leg0, left1, leg1)
        self.mark("MOM_RECOG", right0, leg0, right1, leg1)
        inner_x = ring + g["gap"]
        self.mark("MOM_RECOG_INNER", inner_x - inset, y0 - inset, inner_x + g["finger_width"] + inset, y1 + inset)


class ArrayWiring(DifferenceUnit):
    """A CDAC's own wiring over its placed units (``capcell.caparray_plan``): each stage's main and
    difference buses on the route metal across its units' landings, the top plate's bar over the
    units' top ring walls down a stack beside the array, and the shield's taps out past it."""

    def wiring(self, g, spec):
        route, shield, active = spec["route"], spec["shield"], spec["active"]
        coarse = spec["family"]["coarse_weight"]
        unary = spec["family"].get("unary_length")
        pitch, ring = g["unit_pitch"], g["ring_width"]
        route_metal = f"M{route}"
        x_local, bottom_y, top_y = capcell.access_centers(g)
        extension = (g["landing_long"] - g["via_landing"]) / 2
        pin_half = max(g["grid"], g["finger_width"]) / 2
        for main, diff, first, size in spec["groups"]:
            # the difference bus spans the units with a difference finger (none of a unary stage)
            with_diff = [
                position for position in range(first, first + size) if not (unary and spec["order"][position] == coarse)
            ]
            spans = [(main, bottom_y, bottom_y + extension, first, first + size - 1)]
            if with_diff:
                spans.append((diff, top_y, top_y - extension, with_diff[0], with_diff[-1]))
            for label, y, landing_y, left, right in spans:
                x0 = left * pitch + x_local - g["landing_short"] / 2
                x1 = right * pitch + x_local + g["landing_short"] / 2
                self.rect(
                    route_metal, label, x0, landing_y - g["landing_long"] / 2, x1, landing_y + g["landing_long"] / 2
                )
                cx = left * pitch + x_local
                self.rect(route_metal, label, cx - pin_half, y - pin_half, cx + pin_half, y + pin_half, "pin")

        # the top plate: a bar over the units' top ring walls, down a stack beside the array
        array_right = (len(spec["order"]) - 1) * pitch + g["outer_width"]
        output_right = array_right + g["side_extension"]
        pad = g["via_landing"]
        stack_left = array_right + g["shield_cutout_width"]
        stack_x = stack_left + pad / 2
        y = top_y - (g["landing_long"] + g["via_opposite_enclosure"])
        bar_bottom = g["outer_height"] - ring
        plate = spec["topplate"]
        for metal in range(route, active[-1] + 1):
            if metal in active:
                self.rect(f"M{metal}", plate, 0, bar_bottom, stack_left, bar_bottom + pad)
                self.rect(f"M{metal}", plate, stack_left, y - pad / 2, stack_left + pad, bar_bottom + pad)
            self.rect(f"M{metal}", plate, stack_left, y - pad / 2, stack_left + pad, y + pad / 2)
        for lower in range(route, active[-1]):
            self.vias(f"V{lower}", plate, stack_x, y, g, columns=2)
        self.rect(route_metal, plate, stack_x - ring / 2, y - ring / 2, stack_x + ring / 2, y + ring / 2, "pin")

        # the shield's taps on its bridges at the array's right wall, out on the route metal past
        # the top plate's stack: a tap that would meet the stack's pad is left out
        tap_x = array_right - ring / 2
        clearance = pad / 2 + ring / 2 + g["shield_spacing"]
        ys = [bridge + ring / 2 for bridge in g["shield_bridge_ys"] if abs(bridge + ring / 2 - y) >= clearance]
        if not ys:
            raise ValueError("unit family is too short for a shield tap beside the top plate's stack")
        net = spec["shieldplate"]
        for index, tap_y in enumerate(ys):
            for metal in range(route, shield):
                self.landing(f"M{metal}", net, tap_x, tap_y, g, horizontal=True)
            for lower in range(route, shield):
                self.vias(f"V{lower}", net, tap_x, tap_y, g, rows=1)
            start_x = array_right if route == shield else tap_x
            self.rect(route_metal, net, start_x, tap_y - ring / 2, output_right, tap_y + ring / 2)
            if index == len(ys) // 2:
                self.rect(
                    route_metal, net, output_right - ring, tap_y - ring / 2, output_right, tap_y + ring / 2, "pin"
                )
        self.rect("Boundary", None, 0, 0, output_right, g["outer_height"] - ring + g["via_landing"])
        self.computeBbox()
        return self
