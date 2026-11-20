"""One layout-only extraction through KLayout-PEX's library, by FasterCap or by kpex's 2.5-D engine
(``spec["engine"]``: ``fastercap``, ``rcx25``), run by kpex's own Python
(``flow.layout.kpex.run_layout_pex`` writes its inputs and starts it): this file imports KLayout and
klayout_pex alone.

    <kpex python> kpex_extract.py <spec.json>

The spec holds the GDS, its top cell, kpex's technology (a JSON file; the 2.5-D engine's coefficients
in it), each conductor's GDS pairs and its labels', the vias that join the conductors, the texts to
add (a net the layout leaves unlabelled: its conductor, a point on it and its name), the engine,
FasterCap's executable and settings, and the netlist to write. The layout's nets are found by
KLayout (each conductor joined to itself, each via to the conductors above and below it, each label
naming the net under it). FasterCap's model of them gives a Maxwell matrix, a net's capacitance to
infinity its row sum; the 2.5-D engine gives each pair's capacitance, the substrate's among them,
each edge's sidewall stopped at its own polygon (``_shielded_by_own_polygon``), the fringe past each
line end on the conductors the spec gives a reach (``line_ends``), and where the spec asks, its
capacitances by the coefficient each is linear in (``parts``).
Either becomes a Spectre netlist of capacitors between the nets by their labels, a net's capacitance
to the substrate or infinity to ground, ``0``, as an extractor whose substrate is an infinite plane
counts it. Beside it (``spec["probes"]``), each net's
probes: points on a few of its shapes, each with its conductor's GDS pair, by which an LVS database
finds the net among its own (``flow.layout.annotate``).
"""

import json
import os
import sys
from itertools import pairwise
from pathlib import Path

import klayout.db as kdb
from klayout_pex.fastercap.fastercap_input_builder import FasterCapInputBuilder
from klayout_pex.fastercap.fastercap_runner import fastercap_parse_capacitance_matrix, run_fastercap
from klayout_pex.klayout.lvsdb_extractor import KLayoutExtractionContext
from klayout_pex.rcx25.c.polygon_utils import find_polygon_with_nearest_edge
from klayout_pex.rcx25.c.sidewall_and_fringe_extractor import SidewallAndFringeExtractor
from klayout_pex.rcx25.extractor import RCX25Extractor
from klayout_pex.rcx25.pex_mode import PEXMode
from klayout_pex.tech_info import TechInfo


def nets(spec: dict) -> kdb.LayoutToNetlist:
    """The layout's nets: its conductors joined through its vias, named by its labels."""
    layout = kdb.Layout()
    layout.read(spec["gds"])
    top = layout.cell(spec["top"])
    # the nets the layout leaves unlabelled, labelled as the router named them: each text on its
    # conductor's first label layer, at a point of one of the net's own shapes
    for conductor, x, y, text in spec.get("texts", []):
        layer, datatype = spec["labels"][conductor][0]
        top.shapes(layout.layer(layer, datatype)).insert(kdb.Text(text, kdb.Trans(x, y)))
    l2n = kdb.LayoutToNetlist(kdb.RecursiveShapeIterator(layout, top, []))
    regions = {}
    for name, pairs in spec["layers"].items():
        indexes = [index for layer, datatype in pairs if (index := layout.find_layer(layer, datatype)) is not None]
        if len(indexes) == 1:
            region = l2n.make_layer(indexes[0], name)
        elif not indexes:
            region = l2n.make_layer(name)  # empty: the layout has none of it
        else:
            region = l2n.make_layer(indexes[0])
            for index in indexes[1:]:
                region += l2n.make_layer(index)
            l2n.register(region, name)
        l2n.connect(region)
        regions[name] = region
    for name, pairs in spec["labels"].items():
        for number, (layer, datatype) in enumerate(pairs):
            index = layout.find_layer(layer, datatype)
            if index is not None:
                l2n.connect(regions[name], l2n.make_text_layer(index, f"{name}_label{number}"))
    for below, via, above in spec["vias"]:
        l2n.connect(regions[below], regions[via])
        l2n.connect(regions[via], regions[above])
    l2n.extract_netlist()
    return l2n


def probes(l2n: kdb.LayoutToNetlist, spec: dict, count: int = 4) -> dict[str, list[list[int]]]:
    """Each net's probes, by its name as the netlist gives it: up to ``count`` points, each inside
    one of its shapes (the conductors in the spec's order), as its conductor's GDS layer and
    datatype and the point's x and y in database units."""
    found: dict[str, list[list[int]]] = {}
    for net in l2n.netlist().top_circuit().each_net():
        points = found.setdefault(net.expanded_name(), [])
        for name, pairs in spec["layers"].items():
            # a point inside each shape: the centre of one of its trapezoids (a comb's own is outside it)
            for polygon in l2n.shapes_of_net(net, l2n.layer_by_name(name), True).each():
                centre = polygon.decompose_trapezoids()[0].bbox().center()
                if len(points) < count and polygon.inside(centre):
                    points.append([*pairs[0], centre.x, centre.y])
    return found


def fastercap(context: KLayoutExtractionContext, tech: TechInfo, spec: dict, out: Path) -> list[tuple[str, str, float]]:
    """FasterCap's capacitances (fF) of the layout's nets: each pair's (the Maxwell matrix's
    off-diagonals), each net's to infinity (its row sum) to the substrate."""
    builder = FasterCapInputBuilder(
        pex_context=context,
        tech_info=tech,
        substrate_net_name=context.substrate_net_name,
        k_void=spec["k_void"],
        delaunay_amax=50.0,
        delaunay_b=0.5,
    )
    model = builder.build()
    inputs = out / "FasterCap_Input_Files"
    inputs.mkdir(exist_ok=True)
    lst = model.write_fastcap(output_dir_path=str(inputs), prefix="FasterCap_Input_")[0]
    os.environ["OMP_NUM_THREADS"] = str(spec["threads"])
    log = out / "FasterCap_Output.txt"
    run_fastercap(
        exe_path=spec["fastercap"],
        lst_file_path=lst,
        log_path=str(log),
        tolerance=spec["tolerance"],
        d_coeff=0.5,
        mesh_refinement_value=spec["mesh"],
        ooc_condition=None,
        auto_preconditioner=True,
        galerkin_scheme=spec["galerkin"],
        jacobi_preconditioner=False,
    )
    matrix = fastercap_parse_capacitance_matrix(str(log)).averaged_off_diagonals()
    matrix.write_csv(str(out / "FasterCap_Result_Matrix_Avg.csv"))
    # FasterCap names its conductors g<index>_<net>
    names = [name.split("_", 1)[1] for name in matrix.conductor_names]
    found = [(a, names[j], -matrix[i][j] * 1e15) for i, a in enumerate(names) for j in range(i + 1, len(names))]
    ground = context.substrate_net_name
    return found + [(a, ground, sum(matrix[i]) * 1e15) for i, a in enumerate(names) if a != ground]


def _shielded_by_own_polygon() -> None:
    """The 2.5-D engine's sidewall stopped by the edge's own polygon: kpex 0.6.12 takes, for each
    stretch of an edge, the nearest polygon of another net on its layer however far, past the
    edge's own polygon where it lies nearer (a merged comb's other walls: the top plate's ring walls
    of an array's units, which saw another stage's finger through every empty unit between them, up
    to the halo). Its fringe stops there already (the lateral shield). Wraps kpex's visitor: each
    stretch's own nearest distance noted as kpex meets the edge, a sidewall beyond it dropped."""
    visitor = SidewallAndFringeExtractor.PEXEdgeNeighborhoodVisitor
    if getattr(visitor, "_own_polygon_shields", False):
        return
    on_edge, emit_sidewall = visitor.on_edge, visitor.emit_sidewall

    def noted(self, layout, cell, edge, neighborhood):
        own = len(self.all_layer_names)  # kpex's child index of the edge's own polygon
        self.own_nearest = {
            tuple(interval): find_polygon_with_nearest_edge(by_child[own])[0]
            for interval, by_child in neighborhood
            if by_child.get(own)
        }
        return on_edge(self, layout, cell, edge, neighborhood)

    def shielded(self, layer_name, edge, edge_interval, polygon, geometry_restorer):
        distance = min(polygon.bbox().p1.y, polygon.bbox().p2.y)
        if self.own_nearest.get(tuple(edge_interval), distance + 1) < distance:
            return
        return emit_sidewall(self, layer_name, edge, edge_interval, polygon, geometry_restorer)

    visitor.on_edge, visitor.emit_sidewall, visitor._own_polygon_shields = noted, shielded, True


def _tips(polygon: kdb.Polygon) -> list[tuple[kdb.Point, tuple[int, int], tuple[int, int]]]:
    """A polygon's line ends: each edge shorter than both its neighbours, both its corners convex,
    axis-parallel (a finger's tips, a difference stub's however short). Each end's two corners, each with the unit direction past the
    tip along its side and the side's outward normal (KLayout's hulls run clockwise: outward is
    left of an edge's direction)."""
    points = list(polygon.each_point_hull())
    count = len(points)
    found = []

    def unit(a: kdb.Point, b: kdb.Point) -> tuple[int, int]:
        return ((b.x > a.x) - (b.x < a.x), (b.y > a.y) - (b.y < a.y))

    for i in range(count):
        before, start, end, after = (points[(i + k) % count] for k in (-1, 0, 1, 2))
        lengths = [start.distance(before), end.distance(start), after.distance(end)]
        directions = [unit(before, start), unit(start, end), unit(end, after)]
        if any(0 not in d for d in directions) or lengths[1] >= min(lengths[0], lengths[2]):
            continue
        # convex corners turn right on a clockwise hull: a negative cross product
        if any(a[0] * b[1] - a[1] * b[0] >= 0 for a, b in pairwise(directions)):
            continue
        side, other = directions[0], directions[2]
        found.append((start, side, (-side[1], side[0])))
        found.append((end, (-other[0], -other[1]), (-other[1], other[0])))
    return found


def _beyond(box: kdb.Box, corner: kdb.Point, normal: tuple[int, int]) -> int:
    """How far a box lies out from a side's line through ``corner``, along the side's ``normal``."""
    return {
        (1, 0): box.left - corner.x,
        (-1, 0): corner.x - box.right,
        (0, 1): box.bottom - corner.y,
        (0, -1): corner.y - box.top,
    }[normal]


def line_ends(l2n: kdb.LayoutToNetlist, tech: TechInfo, lengths: dict[str, float]) -> list[list]:
    """The fringe past each wire's end, which kpex's 2.5-D engine leaves out (its sidewall ends with
    the edge), on the conductors ``lengths`` names (um, ``flow.layout.kpex_coefficients``'s fit of
    a MOM finger's ends): each side of a line end (``_tips``) continued that far past the tip, its
    sidewall, by the conductor's coefficients, to the nearest polygon it faces there within the
    halo where that is another net's. As ``parts``' rows: ``line_end``, the conductor twice, the
    two nets, fF."""
    dbu = l2n.internal_layout().dbu
    halo = round(tech.tech.process_parasitics.side_halo / dbu)
    nets = [(net.expanded_name(), net) for net in l2n.netlist().top_circuit().each_net()]
    found: dict[tuple, float] = {}
    for layer, length_um in lengths.items():
        coefficient = tech.sidewall_cap_by_layer_name[layer]
        shapes = kdb.Shapes()
        owned = []
        for name, net in nets:
            for polygon in l2n.shapes_of_net(net, l2n.layer_by_name(layer), True).merged().each():
                shapes.insert(kdb.PolygonWithProperties(polygon, {"net": name}))
                owned.append((name, polygon))
        reach = round(length_um / dbu)
        for name, polygon in owned:
            for corner, past, normal in _tips(polygon):
                ends = [corner.x + past[0] * reach + normal[0] * halo, corner.y + past[1] * reach + normal[1] * halo]
                box = kdb.Box(corner.x, corner.y, *ends)
                nearest = None
                for shape in shapes.each_overlapping(box):
                    for piece in (kdb.Region(shape.polygon) & kdb.Region(box)).each():
                        near = _beyond(piece.bbox(), corner, normal)
                        if near > 0 and (nearest is None or near < nearest[0]):
                            nearest = (near, shape.property("net"))
                if nearest is None or nearest[1] == name:
                    continue
                # not in the reference texts: kpex's sidewall, length K / (s + o) per facing pair
                # of edges halved (each edge counts its half), over the length past the tip
                value = length_um * coefficient.capacitance / (nearest[0] * dbu + coefficient.offset) / 2 / 1000
                index = ("line_end", layer, layer, *sorted((name, nearest[1])))
                found[index] = found.get(index, 0.0) + value
    return [[*index, value] for index, value in sorted(found.items())]


def parts(results) -> list[list]:
    """The 2.5-D engine's capacitances (fF) by the coefficient each is linear in: each net pair's
    overlaps (``overlap``, the top conductor and the bottom one: the substrate's area capacitance
    where it is the substrate), sidewalls (``sidewall``, the conductor twice) and fringes
    (``sideoverlap``, the edge's conductor and the plate's: the substrate's perimeter capacitance
    where it is the substrate), summed."""
    found: dict[tuple, float] = {}
    for cell in results.cell_extraction_results.values():
        tables = (
            ("overlap", cell.overlap_table, lambda k: (k.layer_top, k.layer_bot, k.net_top, k.net_bot)),
            ("sidewall", cell.sidewall_table, lambda k: (k.layer, k.layer, k.net1, k.net2)),
            (
                "sideoverlap",
                cell.sideoverlap_table,
                lambda k: (k.layer_inside, k.layer_outside, k.net_inside, k.net_outside),
            ),
        )
        for kind, table, fields in tables:
            for key, entries in table.items():
                a, b, net1, net2 = fields(key)
                index = (kind, a, b, *sorted((net1, net2)))
                found[index] = found.get(index, 0.0) + sum(entry.cap_value for entry in entries)
    return [[*index, value] for index, value in sorted(found.items())]


def rcx25(
    context: KLayoutExtractionContext, tech: TechInfo, out: Path, spec: dict, l2n: kdb.LayoutToNetlist
) -> list[tuple[str, str, float]]:
    """kpex's 2.5-D capacitances (fF) of the layout's nets, by the technology's coefficients: each
    pair's, a net's to the substrate among them, and the fringe past the line ends on the
    conductors the spec gives a length (``line_ends``); and, where the spec asks (``parts``), the
    capacitances by coefficient (``parts``, ``line_ends``) written there. Each edge's sidewall
    stops at its own polygon (``_shielded_by_own_polygon``)."""
    _shielded_by_own_polygon()
    extractor = RCX25Extractor(
        pex_context=context,
        pex_mode=PEXMode.CC,
        scale_ratio_to_fit_halo=True,
        delaunay_amax=0,
        delaunay_b=0.5,
        tech_info=tech,
        report_path=str(out / "rcx25_report.rdb"),
        report_caps=False,
    )
    results = extractor.extract()
    ends = line_ends(l2n, tech, spec.get("line_ends") or {})
    if spec.get("parts"):
        Path(spec["parts"]).write_text(json.dumps(parts(results) + ends) + "\n")
    found = [(key.net1, key.net2, c) for key, c in results.summarize().capacitances.items()]
    return found + [(net1, net2, value) for _kind, _a, _b, net1, net2, value in ends]


def main(path: str) -> None:
    spec = json.loads(Path(path).read_text())
    out = Path(spec["out_dir"])
    out.mkdir(parents=True, exist_ok=True)
    tech = TechInfo.from_json(spec["tech"], dielectric_filter=None)
    l2n = nets(spec)
    Path(spec["probes"]).write_text(json.dumps(probes(l2n, spec)) + "\n")
    context = KLayoutExtractionContext.prepare_extraction(
        lvsdb=l2n, top_cell=spec["top"], tech=tech, blackbox_devices=False
    )
    if spec["engine"] == "rcx25":
        found, made = rcx25(context, tech, out, spec, l2n), "kpex's 2.5-D engine"
    else:
        found, made = fastercap(context, tech, spec, out), "FasterCap"
    # the substrate's net is ground (the 2.5-D engine's own name for it, VSUBS, too)
    ground = {context.substrate_net_name, "VSUBS"}
    node = {name: "0" if name in ground else name for pair in found for name in pair[:2]}
    ports = sorted({name for name in node.values() if name != "0"})
    lines = [
        f"// {made} through KLayout-PEX, by the layout's net names; a net's to the substrate or infinity to ground",
        "simulator lang=spectre",
        f"subckt {spec['top']} ( {' '.join(ports)} )",
    ]
    count = 0
    for a, b, value in found:
        if value > 0 and node[a] != node[b]:
            lines.append(f"c_{count} ( {node[a]} {node[b]} ) capacitor c={value:.6g}f")
            count += 1
    lines.append(f"ends {spec['top']}")
    Path(spec["netlist"]).write_text("\n".join(lines) + "\n")


if __name__ == "__main__":
    main(sys.argv[1])
