"""
Shared KLayout and VLSIR helpers for FRIDA primitive layout generation.

This module keeps the default flow "in-memory geometry -> VLSIR raw protobuf",
with optional GDS export only for debug/inspection.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import klayout.db as kdb
import vlsir.raw_pb2 as vraw
import vlsir.tech_pb2 as vtech
import vlsir.utils_pb2 as vutils
from google.protobuf import text_format

type RuleTokenValue = str | int | float | bool


@dataclass(frozen=True)
class TechLayoutPreset:
    """Process-specific geometry and layer defaults for primitive generation."""

    name: str
    dbu_um: float
    stdcell_height_um: float
    track_count: int
    track_pitch_um: float
    gate_length_min_um: float
    finger_width_min_um: float
    cont_size_um: float
    cont_spacing_um: float
    cont_enc_active_um: float
    cont_enc_poly_um: float
    cont_enc_metal_um: float
    cont_gate_dist_um: float
    poly_over_active_um: float
    psd_over_active_um: float
    nwell_over_active_um: float
    m1_width_um: float
    m1_rail_width_um: float
    layers: dict[str, tuple[int, int]]


@dataclass(frozen=True)
class ExportArtifacts:
    """Paths written by an export operation."""

    pb: Path
    pbtxt: Path
    gds: Path | None = None


@dataclass(frozen=True)
class RuleStatementData:
    """Tokenized LEF-like rule statement."""

    keyword: str
    tokens: tuple[RuleTokenValue, ...] = ()
    raw: str = ""


@dataclass(frozen=True)
class LayerRuleSetData:
    """Rules associated with one layer."""

    name: str
    layer_type: str = ""
    rules: tuple[RuleStatementData, ...] = ()


@dataclass(frozen=True)
class ViaDefinitionData:
    """Rules associated with one VIA block."""

    name: str
    header_tokens: tuple[RuleTokenValue, ...] = ()
    rules: tuple[RuleStatementData, ...] = ()


@dataclass(frozen=True)
class LayerPairRuleSetData:
    """Pairwise FEOL relationship rules."""

    first_layer: str
    second_layer: str
    rules: tuple[RuleStatementData, ...] = ()
    source: str = "manual"


@dataclass(frozen=True)
class PropertyDefinitionData:
    """Top-level PROPERTYDEFINITIONS entry."""

    object_type: str
    name: str
    value_type: str


@dataclass(frozen=True)
class UnitScaleData:
    """Top-level UNITS entry excluding DATABASE MICRONS."""

    quantity: str
    unit: str
    scale: float


@dataclass(frozen=True)
class LayerInfoData:
    """Plain-Python layer map entry for `vlsir.tech.LayerInfo`."""

    name: str
    index: int
    sub_index: int = 0
    purpose_type: str = "DRAWING"
    purpose_description: str = "drawing"


@dataclass(frozen=True)
class CornerSectionData:
    """Corner-to-section mapping for a model library."""

    corner: str
    section: str


@dataclass(frozen=True)
class ModelLibraryData:
    """Simulator model-library file path and corner sections."""

    simulator: str
    path: str
    corner_sections: tuple[CornerSectionData, ...] = ()
    notes: str = ""


@dataclass(frozen=True)
class RuleDeckData:
    """Plain-Python technology rule deck description."""

    database_microns: int | None = None
    manufacturing_grid_microns: float | None = None
    unit_scales: tuple[UnitScaleData, ...] = ()
    property_definitions: tuple[PropertyDefinitionData, ...] = ()
    layers: tuple[LayerRuleSetData, ...] = ()
    vias: tuple[ViaDefinitionData, ...] = ()
    via_rules: tuple[ViaDefinitionData, ...] = ()
    layer_pairs: tuple[LayerPairRuleSetData, ...] = ()


@dataclass(frozen=True)
class TechnologyData:
    """Plain-Python `vlsir.tech.Technology` description."""

    name: str
    packages: tuple[str, ...] = ()
    model_libraries: tuple[ModelLibraryData, ...] = ()
    layer_infos: tuple[LayerInfoData, ...] = ()
    rule_deck: RuleDeckData | None = None


@dataclass(frozen=True)
class TechArtifacts:
    """Paths written by a technology-export operation."""

    pb: Path
    pbtxt: Path


def rule_statement(keyword: str, *tokens: RuleTokenValue) -> RuleStatementData:
    """Helper to build a LEF-like statement in plain Python."""
    raw_tokens = " ".join(str(t) for t in tokens)
    raw = f"{keyword} {raw_tokens}".strip()
    return RuleStatementData(keyword=keyword.upper(), tokens=tuple(tokens), raw=raw)


def merge_rule_decks(
    base: RuleDeckData,
    *,
    layers: tuple[LayerRuleSetData, ...] = (),
    vias: tuple[ViaDefinitionData, ...] = (),
    via_rules: tuple[ViaDefinitionData, ...] = (),
    layer_pairs: tuple[LayerPairRuleSetData, ...] = (),
) -> RuleDeckData:
    """Merge additional rule sets into an existing rule deck."""

    return RuleDeckData(
        database_microns=base.database_microns,
        manufacturing_grid_microns=base.manufacturing_grid_microns,
        unit_scales=base.unit_scales,
        property_definitions=base.property_definitions,
        layers=base.layers + layers,
        vias=base.vias + vias,
        via_rules=base.via_rules + via_rules,
        layer_pairs=base.layer_pairs + layer_pairs,
    )


def _token_to_proto(token: RuleTokenValue) -> vtech.RuleToken:
    proto = vtech.RuleToken()
    if isinstance(token, bool):
        proto.boolean = token
    elif isinstance(token, int):
        proto.integer = token
    elif isinstance(token, float):
        proto.real = token
    else:
        proto.text = str(token)
    return proto


def _statement_to_proto(stmt: RuleStatementData) -> vtech.RuleStatement:
    return vtech.RuleStatement(
        keyword=stmt.keyword,
        tokens=[_token_to_proto(token) for token in stmt.tokens],
        raw=stmt.raw,
    )


def _layer_rules_to_proto(layer: LayerRuleSetData) -> vtech.LayerRuleSet:
    return vtech.LayerRuleSet(
        name=layer.name,
        layer_type=layer.layer_type,
        rules=[_statement_to_proto(stmt) for stmt in layer.rules],
    )


def _via_def_to_proto(via: ViaDefinitionData) -> vtech.ViaDefinition:
    return vtech.ViaDefinition(
        name=via.name,
        header_tokens=[_token_to_proto(token) for token in via.header_tokens],
        rules=[_statement_to_proto(stmt) for stmt in via.rules],
    )


def _via_rule_def_to_proto(via_rule: ViaDefinitionData) -> vtech.ViaRuleDefinition:
    return vtech.ViaRuleDefinition(
        name=via_rule.name,
        header_tokens=[_token_to_proto(token) for token in via_rule.header_tokens],
        rules=[_statement_to_proto(stmt) for stmt in via_rule.rules],
    )


def _layer_pair_to_proto(pair: LayerPairRuleSetData) -> vtech.LayerPairRuleSet:
    return vtech.LayerPairRuleSet(
        first_layer=pair.first_layer,
        second_layer=pair.second_layer,
        rules=[_statement_to_proto(stmt) for stmt in pair.rules],
        source=pair.source,
    )


def technology_to_proto(data: TechnologyData) -> vtech.Technology:
    """Convert plain-Python technology data into `vlsir.tech.Technology`."""
    tech = vtech.Technology(name=data.name)
    for package in data.packages:
        tech.packages.append(vtech.Package(name=package))
    for model in data.model_libraries:
        tech_model = vtech.ModelLibrary(
            simulator=model.simulator,
            path=model.path,
            notes=model.notes,
        )
        tech_model.corner_sections.extend(
            [
                vtech.CornerSection(corner=corner.corner, section=corner.section)
                for corner in model.corner_sections
            ]
        )
        tech.model_libraries.append(tech_model)
    purpose_map = {
        "UNKNOWN": vtech.LayerPurposeType.UNKNOWN,
        "LABEL": vtech.LayerPurposeType.LABEL,
        "DRAWING": vtech.LayerPurposeType.DRAWING,
        "PIN": vtech.LayerPurposeType.PIN,
        "OBSTRUCTION": vtech.LayerPurposeType.OBSTRUCTION,
        "OUTLINE": vtech.LayerPurposeType.OUTLINE,
    }
    for info in data.layer_infos:
        ptype = purpose_map.get(info.purpose_type.upper(), vtech.LayerPurposeType.UNKNOWN)
        tech.layers.append(
            vtech.LayerInfo(
                name=info.name,
                purpose=vtech.LayerPurpose(
                    description=info.purpose_description,
                    type=ptype,
                ),
                index=info.index,
                sub_index=info.sub_index,
            )
        )

    if data.rule_deck is None:
        return tech

    deck = data.rule_deck
    if deck.database_microns is not None:
        tech.rules.lef_units.database_microns = deck.database_microns
    for scale in deck.unit_scales:
        tech.rules.lef_units.unit_scales.append(
            vtech.UnitScale(
                quantity=scale.quantity,
                unit=scale.unit,
                scale=scale.scale,
            )
        )
    if deck.manufacturing_grid_microns is not None:
        tech.rules.manufacturing_grid_microns = deck.manufacturing_grid_microns
    for prop in deck.property_definitions:
        tech.rules.property_definitions.append(
            vtech.PropertyDefinition(
                object_type=prop.object_type,
                name=prop.name,
                value_type=prop.value_type,
            )
        )
    tech.rules.layers.extend([_layer_rules_to_proto(layer) for layer in deck.layers])
    tech.rules.vias.extend([_via_def_to_proto(via) for via in deck.vias])
    tech.rules.via_rules.extend(
        [_via_rule_def_to_proto(via_rule) for via_rule in deck.via_rules]
    )
    tech.rules.layer_pairs.extend(
        [_layer_pair_to_proto(pair) for pair in deck.layer_pairs]
    )
    return tech


def write_tech_to_proto(
    data: TechnologyData,
    out_dir: Path,
    stem: str | None = None,
) -> TechArtifacts:
    """Serialize technology-rule data to VLSIR tech binary and text protobuf."""

    out_dir.mkdir(parents=True, exist_ok=True)
    stem = stem or data.name
    pb_path = out_dir / f"{stem}.tech.pb"
    pbtxt_path = out_dir / f"{stem}.tech.pbtxt"
    proto = technology_to_proto(data)
    pb_path.write_bytes(proto.SerializeToString())
    pbtxt_path.write_text(text_format.MessageToString(proto), encoding="utf-8")
    return TechArtifacts(pb=pb_path, pbtxt=pbtxt_path)


def read_technology_proto(path: Path) -> vtech.Technology:
    """Read `vlsir.tech.Technology` from `.pb` or text-proto (`.pbtxt`)."""
    tech = vtech.Technology()
    if path.suffix == ".pb":
        tech.ParseFromString(path.read_bytes())
    else:
        text_format.Parse(path.read_text(encoding="utf-8"), tech)
    return tech


def _normalized_aliases(aliases: tuple[str, ...] | list[str]) -> set[str]:
    return {alias.upper() for alias in aliases}


def _rule_token_value(token: vtech.RuleToken) -> RuleTokenValue | None:
    field = token.WhichOneof("value")
    if field is None:
        return None
    return getattr(token, field)


def _as_float(value: RuleTokenValue | None) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


def resolve_layer_spec_from_technology(
    tech: vtech.Technology,
    aliases: tuple[str, ...] | list[str],
) -> tuple[int, int] | None:
    """Resolve layer `(index, sub_index)` by alias from `Technology.layers`."""
    alias_set = _normalized_aliases(aliases)
    for info in tech.layers:
        if info.name.upper() in alias_set:
            return int(info.index), int(info.sub_index)
    return None


def _find_rule_layer(
    tech: vtech.Technology,
    aliases: tuple[str, ...] | list[str],
) -> vtech.LayerRuleSet | None:
    alias_set = _normalized_aliases(aliases)
    for layer in tech.rules.layers:
        if layer.name.upper() in alias_set:
            return layer
    return None


def _parse_spacingtable_tokens(
    tokens: list[RuleTokenValue | None],
) -> tuple[list[float], list[tuple[float, list[float]]]] | None:
    if not tokens:
        return None
    idx = 0
    head = tokens[idx]
    if not isinstance(head, str) or head.upper() != "PARALLELRUNLENGTH":
        return None
    idx += 1

    prls: list[float] = []
    while idx < len(tokens):
        tok = tokens[idx]
        if isinstance(tok, str) and tok.upper() == "WIDTH":
            break
        val = _as_float(tok)
        if val is None:
            return None
        prls.append(val)
        idx += 1
    if not prls:
        return None

    rows: list[tuple[float, list[float]]] = []
    while idx < len(tokens):
        tok = tokens[idx]
        if not isinstance(tok, str) or tok.upper() != "WIDTH":
            idx += 1
            continue
        idx += 1
        if idx >= len(tokens):
            break
        width_key = _as_float(tokens[idx])
        idx += 1
        if width_key is None:
            continue
        spacings: list[float] = []
        for _ in range(len(prls)):
            if idx >= len(tokens):
                break
            spacing = _as_float(tokens[idx])
            idx += 1
            if spacing is None:
                break
            spacings.append(spacing)
        if len(spacings) == len(prls):
            rows.append((width_key, spacings))
    if not rows:
        return None
    return prls, rows


def _spacingtable_lookup(
    prls: list[float],
    rows: list[tuple[float, list[float]]],
    width: float,
    prl: float,
) -> float:
    row = rows[0]
    for candidate in rows:
        if width >= candidate[0]:
            row = candidate
    prl_idx = 0
    for idx, threshold in enumerate(prls):
        if prl >= threshold:
            prl_idx = idx
    return row[1][prl_idx]


def technology_rule_value(
    tech: vtech.Technology,
    layer_aliases: tuple[str, ...] | list[str],
    keyword: str,
) -> float | None:
    """Get first numeric value from a rule statement on a layer."""
    layer = _find_rule_layer(tech, layer_aliases)
    if layer is None:
        return None
    key = keyword.upper()
    for stmt in layer.rules:
        if stmt.keyword.upper() != key:
            continue
        for token in stmt.tokens:
            value = _as_float(_rule_token_value(token))
            if value is not None:
                return value
    return None


def technology_rule_spacing(
    tech: vtech.Technology,
    layer_aliases: tuple[str, ...] | list[str],
    width: float,
    prl: float = 0.0,
) -> float | None:
    """Get spacing rule, preferring `SPACINGTABLE` over scalar `SPACING`."""
    layer = _find_rule_layer(tech, layer_aliases)
    if layer is None:
        return None

    for stmt in layer.rules:
        if stmt.keyword.upper() != "SPACINGTABLE":
            continue
        parsed = _parse_spacingtable_tokens([_rule_token_value(tok) for tok in stmt.tokens])
        if parsed is None:
            continue
        prls, rows = parsed
        return _spacingtable_lookup(prls, rows, width=width, prl=prl)

    return technology_rule_value(tech, layer_aliases, "SPACING")


def technology_pair_rule_value(
    tech: vtech.Technology,
    first_layer_aliases: tuple[str, ...] | list[str],
    second_layer_aliases: tuple[str, ...] | list[str],
    keyword: str,
) -> float | None:
    """Get first numeric value for a pair-rule statement (order-insensitive)."""
    first_aliases = _normalized_aliases(first_layer_aliases)
    second_aliases = _normalized_aliases(second_layer_aliases)
    key = keyword.upper()
    for pair in tech.rules.layer_pairs:
        f = pair.first_layer.upper()
        s = pair.second_layer.upper()
        direct = f in first_aliases and s in second_aliases
        reverse = f in second_aliases and s in first_aliases
        if not (direct or reverse):
            continue
        for stmt in pair.rules:
            if stmt.keyword.upper() != key:
                continue
            for token in stmt.tokens:
                value = _as_float(_rule_token_value(token))
                if value is not None:
                    return value
    return None


def create_layout(preset: TechLayoutPreset) -> kdb.Layout:
    """Create a KLayout layout object with preset DBU."""
    layout = kdb.Layout()
    layout.dbu = preset.dbu_um
    return layout


def um_to_dbu(layout: kdb.Layout, value_um: float) -> int:
    """Convert microns to integer DBU coordinates."""
    return int(round(value_um / layout.dbu))


def insert_box_um(
    cell: kdb.Cell,
    layout: kdb.Layout,
    layer_idx: int,
    x0_um: float,
    y0_um: float,
    x1_um: float,
    y1_um: float,
) -> None:
    """Insert an axis-aligned rectangle in micron coordinates."""
    x0 = um_to_dbu(layout, x0_um)
    y0 = um_to_dbu(layout, y0_um)
    x1 = um_to_dbu(layout, x1_um)
    y1 = um_to_dbu(layout, y1_um)
    xl, xh = sorted((x0, x1))
    yl, yh = sorted((y0, y1))
    if xh <= xl or yh <= yl:
        return
    cell.shapes(layer_idx).insert(kdb.Box(xl, yl, xh, yh))


def insert_text_um(
    cell: kdb.Cell,
    layout: kdb.Layout,
    layer_idx: int,
    text: str,
    x_um: float,
    y_um: float,
) -> None:
    """Insert text label at a micron-coordinate location."""
    x = um_to_dbu(layout, x_um)
    y = um_to_dbu(layout, y_um)
    cell.shapes(layer_idx).insert(kdb.Text(text, kdb.Trans(kdb.Point(x, y))))


def _shape_box_to_vlsir_rect(shape: kdb.Shape) -> vraw.Rectangle:
    box = shape.box
    return vraw.Rectangle(
        lower_left=vraw.Point(x=int(box.left), y=int(box.bottom)),
        width=int(box.right - box.left),
        height=int(box.top - box.bottom),
    )


def _shape_polygon_to_vlsir_poly(shape: kdb.Shape) -> vraw.Polygon:
    polygon = shape.polygon
    vertices = [vraw.Point(x=int(p.x), y=int(p.y)) for p in polygon.each_point_hull()]
    return vraw.Polygon(vertices=vertices)


def _shape_path_to_vlsir_path(shape: kdb.Shape) -> vraw.Path:
    path = shape.path
    points = [vraw.Point(x=int(p.x), y=int(p.y)) for p in path.each_point()]
    return vraw.Path(points=points, width=int(path.width))


def _append_instance(
    raw_layout: vraw.Layout,
    name: str,
    target_cell_name: str,
    x: int,
    y: int,
    reflect_vert: bool,
    rotation_quadrants: int,
) -> None:
    raw_layout.instances.append(
        vraw.Instance(
            name=name,
            cell=vutils.Reference(local=target_cell_name),
            origin_location=vraw.Point(x=x, y=y),
            reflect_vert=reflect_vert,
            rotation_clockwise_degrees=int(rotation_quadrants * 90),
        )
    )


def layout_to_vlsir_raw(
    layout: kdb.Layout,
    domain: str = "frida.layout",
) -> vraw.Library:
    """
    Convert an in-memory KLayout layout database to VLSIR raw protobuf.

    Notes:
    - Primitive geometry is captured in `Cell.layout`.
    - KLayout texts are mapped to raw `annotations`.
    - Instance arrays are expanded to individual `Instance` entries.
    """

    library = vraw.Library(domain=domain, units=vraw.Units.MICRO)
    layer_indexes = list(layout.layer_indexes())

    for cell in layout.each_cell():
        raw_layout = vraw.Layout(name=cell.name)

        for layer_idx in layer_indexes:
            shapes = cell.shapes(layer_idx)
            if shapes.is_empty():
                continue

            layer_info = layout.get_info(layer_idx)
            layer_shapes = vraw.LayerShapes(
                layer=vraw.Layer(
                    number=int(layer_info.layer),
                    purpose=int(layer_info.datatype),
                )
            )

            for shape in shapes.each():
                if shape.is_box():
                    layer_shapes.rectangles.append(_shape_box_to_vlsir_rect(shape))
                elif shape.is_polygon():
                    layer_shapes.polygons.append(_shape_polygon_to_vlsir_poly(shape))
                elif shape.is_path():
                    layer_shapes.paths.append(_shape_path_to_vlsir_path(shape))
                elif shape.is_text():
                    text = shape.text
                    raw_layout.annotations.append(
                        vraw.TextElement(
                            string=text.string,
                            loc=vraw.Point(x=int(text.x), y=int(text.y)),
                        )
                    )

            if (
                len(layer_shapes.rectangles)
                + len(layer_shapes.polygons)
                + len(layer_shapes.paths)
            ) > 0:
                raw_layout.shapes.append(layer_shapes)

        for inst_idx, inst in enumerate(cell.each_inst()):
            target_name = layout.cell(inst.cell_index).name
            trans = inst.trans

            if inst.is_regular_array() and (inst.na > 1 or inst.nb > 1):
                for ia in range(inst.na):
                    for ib in range(inst.nb):
                        dx = int(trans.disp.x + ia * inst.a.x + ib * inst.b.x)
                        dy = int(trans.disp.y + ia * inst.a.y + ib * inst.b.y)
                        _append_instance(
                            raw_layout=raw_layout,
                            name=f"I{inst_idx}_{ia}_{ib}",
                            target_cell_name=target_name,
                            x=dx,
                            y=dy,
                            reflect_vert=bool(trans.is_mirror()),
                            rotation_quadrants=int(trans.angle),
                        )
            else:
                _append_instance(
                    raw_layout=raw_layout,
                    name=f"I{inst_idx}",
                    target_cell_name=target_name,
                    x=int(trans.disp.x),
                    y=int(trans.disp.y),
                    reflect_vert=bool(trans.is_mirror()),
                    rotation_quadrants=int(trans.angle),
                )

        library.cells.append(vraw.Cell(name=cell.name, layout=raw_layout))

    return library


def write_vlsir_raw_library(
    library: vraw.Library,
    pb_path: Path,
    pbtxt_path: Path | None = None,
) -> None:
    """Write VLSIR raw protobuf in binary and optional text format."""
    pb_path.parent.mkdir(parents=True, exist_ok=True)
    pb_path.write_bytes(library.SerializeToString())
    if pbtxt_path is not None:
        pbtxt_path.parent.mkdir(parents=True, exist_ok=True)
        pbtxt_path.write_text(text_format.MessageToString(library), encoding="utf-8")


def export_layout(
    layout: kdb.Layout,
    out_dir: Path,
    stem: str,
    domain: str = "frida.layout",
    write_debug_gds: bool = False,
) -> ExportArtifacts:
    """
    Export a KLayout layout to VLSIR raw files and optional debug GDS.

    Primary artifacts are always:
    - `{stem}.raw.pb`
    - `{stem}.raw.pbtxt`
    """

    out_dir.mkdir(parents=True, exist_ok=True)
    pb_path = out_dir / f"{stem}.raw.pb"
    pbtxt_path = out_dir / f"{stem}.raw.pbtxt"
    library = layout_to_vlsir_raw(layout, domain=domain)
    write_vlsir_raw_library(library=library, pb_path=pb_path, pbtxt_path=pbtxt_path)

    gds_path: Path | None = None
    if write_debug_gds:
        gds_path = out_dir / f"{stem}.debug.gds"
        layout.write(str(gds_path))

    return ExportArtifacts(pb=pb_path, pbtxt=pbtxt_path, gds=gds_path)
