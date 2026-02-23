"""
Shared KLayout and VLSIR helpers for FRIDA primitive layout generation.

This module keeps the default flow "in-memory geometry -> VLSIR raw protobuf",
with optional GDS export only for debug/inspection.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re

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
    layer_infos: tuple[LayerInfoData, ...] = ()
    rule_deck: RuleDeckData | None = None


@dataclass(frozen=True)
class TechArtifacts:
    """Paths written by a technology-export operation."""

    pb: Path
    pbtxt: Path


_LEF_TOKEN_RE = re.compile(r'"[^"]*"|\(|\)|[^\s()]+')
_INT_RE = re.compile(r"^[+-]?\d+$")
_FLOAT_RE = re.compile(r"^[+-]?(?:\d+\.\d*|\d*\.\d+|\d+)(?:[Ee][+-]?\d+)?$")


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


def _parse_scalar_token(token: str) -> RuleTokenValue:
    if token.startswith('"') and token.endswith('"') and len(token) >= 2:
        return token[1:-1]
    up = token.upper()
    if up == "TRUE":
        return True
    if up == "FALSE":
        return False
    if _INT_RE.fullmatch(token):
        return int(token)
    if _FLOAT_RE.fullmatch(token):
        return float(token)
    return token


def _parse_statement(stmt: str) -> RuleStatementData:
    raw = " ".join(stmt.split())
    parts = _LEF_TOKEN_RE.findall(raw)
    if not parts:
        return RuleStatementData(keyword="", tokens=(), raw=raw)
    keyword = parts[0].upper()
    tokens = tuple(_parse_scalar_token(tok) for tok in parts[1:])
    return RuleStatementData(keyword=keyword, tokens=tokens, raw=raw)


def _collect_statements(lines: list[str]) -> list[str]:
    """Collect `;`-terminated statements from LEF block lines."""
    stmts: list[str] = []
    buf = ""
    for line in lines:
        line = line.split("#", maxsplit=1)[0].strip()
        if not line:
            continue
        buf = f"{buf} {line}".strip() if buf else line
        while ";" in buf:
            stmt, tail = buf.split(";", maxsplit=1)
            stmt = stmt.strip()
            if stmt:
                stmts.append(stmt)
            buf = tail.strip()
    tail = buf.strip()
    if tail:
        stmts.append(tail)
    return stmts


def _find_end_line(lines: list[str], start: int, end_name: str) -> int:
    end_tag = f"END {end_name.upper()}"
    for idx in range(start, len(lines)):
        head = lines[idx].split("#", maxsplit=1)[0].strip().upper()
        if head.startswith(end_tag):
            return idx
    raise ValueError(f"Missing '{end_tag}' while parsing LEF block.")


def parse_tech_lef(path: Path) -> RuleDeckData:
    """
    Parse a TECHLEF file into a `RuleDeckData`.

    The parser captures:
    - UNITS / MANUFACTURINGGRID
    - PROPERTYDEFINITIONS
    - LAYER blocks
    - VIA blocks
    - VIARULE blocks
    """

    lines = path.read_text(encoding="utf-8").splitlines()
    database_microns: int | None = None
    manufacturing_grid: float | None = None
    unit_scales: list[UnitScaleData] = []
    prop_defs: list[PropertyDefinitionData] = []
    layers: list[LayerRuleSetData] = []
    vias: list[ViaDefinitionData] = []
    via_rules: list[ViaDefinitionData] = []

    idx = 0
    while idx < len(lines):
        raw = lines[idx].split("#", maxsplit=1)[0].strip()
        upper = raw.upper()
        if not raw:
            idx += 1
            continue

        if upper.startswith("UNITS"):
            end_idx = _find_end_line(lines, idx + 1, "UNITS")
            unit_stmts = _collect_statements(lines[idx + 1 : end_idx])
            for stmt in unit_stmts:
                parsed = _parse_statement(stmt)
                if parsed.keyword == "DATABASE":
                    if len(parsed.tokens) >= 2 and isinstance(
                        parsed.tokens[1], (int, float)
                    ):
                        database_microns = int(parsed.tokens[1])
                elif len(parsed.tokens) >= 2 and isinstance(
                    parsed.tokens[1], (int, float)
                ):
                    unit_scales.append(
                        UnitScaleData(
                            quantity=parsed.keyword,
                            unit=str(parsed.tokens[0]),
                            scale=float(parsed.tokens[1]),
                        )
                    )
            idx = end_idx + 1
            continue

        if upper.startswith("PROPERTYDEFINITIONS"):
            end_idx = _find_end_line(lines, idx + 1, "PROPERTYDEFINITIONS")
            prop_stmts = _collect_statements(lines[idx + 1 : end_idx])
            for stmt in prop_stmts:
                parsed = _parse_statement(stmt)
                if len(parsed.tokens) >= 2:
                    prop_defs.append(
                        PropertyDefinitionData(
                            object_type=parsed.keyword,
                            name=str(parsed.tokens[0]),
                            value_type=str(parsed.tokens[1]),
                        )
                    )
            idx = end_idx + 1
            continue

        if upper.startswith("MANUFACTURINGGRID"):
            stmt = raw[:-1].strip() if raw.endswith(";") else raw
            parsed = _parse_statement(stmt)
            if parsed.tokens and isinstance(parsed.tokens[0], (int, float)):
                manufacturing_grid = float(parsed.tokens[0])
            idx += 1
            continue

        if upper.startswith("LAYER "):
            parts = raw.split()
            if len(parts) < 2:
                raise ValueError(f"Malformed LAYER start line: '{raw}'")
            name = parts[1]
            end_idx = _find_end_line(lines, idx + 1, name)
            layer_stmts = tuple(
                _parse_statement(stmt)
                for stmt in _collect_statements(lines[idx + 1 : end_idx])
            )
            layer_type = ""
            for stmt in layer_stmts:
                if stmt.keyword == "TYPE" and stmt.tokens:
                    layer_type = str(stmt.tokens[0]).upper()
                    break
            layer = LayerRuleSetData(name=name, layer_type=layer_type, rules=layer_stmts)
            layers.append(layer)
            idx = end_idx + 1
            continue

        if upper.startswith("VIA "):
            parts = raw.split()
            if len(parts) < 2:
                raise ValueError(f"Malformed VIA start line: '{raw}'")
            name = parts[1]
            header_tokens = tuple(_parse_scalar_token(tok) for tok in parts[2:])
            end_idx = _find_end_line(lines, idx + 1, name)
            via_stmts = tuple(
                _parse_statement(stmt)
                for stmt in _collect_statements(lines[idx + 1 : end_idx])
            )
            vias.append(
                ViaDefinitionData(
                    name=name,
                    header_tokens=header_tokens,
                    rules=via_stmts,
                )
            )
            idx = end_idx + 1
            continue

        if upper.startswith("VIARULE "):
            parts = raw.split()
            if len(parts) < 2:
                raise ValueError(f"Malformed VIARULE start line: '{raw}'")
            name = parts[1]
            header_tokens = tuple(_parse_scalar_token(tok) for tok in parts[2:])
            end_idx = _find_end_line(lines, idx + 1, name)
            via_rule_rules = tuple(
                _parse_statement(stmt)
                for stmt in _collect_statements(lines[idx + 1 : end_idx])
            )
            via_rules.append(
                ViaDefinitionData(
                    name=name,
                    header_tokens=header_tokens,
                    rules=via_rule_rules,
                )
            )
            idx = end_idx + 1
            continue

        idx += 1

    return RuleDeckData(
        database_microns=database_microns,
        manufacturing_grid_microns=manufacturing_grid,
        unit_scales=tuple(unit_scales),
        property_definitions=tuple(prop_defs),
        layers=tuple(layers),
        vias=tuple(vias),
        via_rules=tuple(via_rules),
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


def load_layer_map_from_lyt(lyt_path: Path) -> tuple[LayerInfoData, ...]:
    """
    Extract layer mapping from KLayout `.lyt` LEF/DEF layer-map settings.

    Returns:
        Tuple of `LayerInfoData` sorted by `(index, sub_index, name)`.
    """
    tech = kdb.Technology()
    tech.load(str(lyt_path))
    layout_options = tech.load_layout_options
    lefdef_config = layout_options.lefdef_config
    layer_map = lefdef_config.layer_map
    map_str = layer_map.to_string()
    entries: list[LayerInfoData] = []

    def add_entry(name: str, index: int, sub_index: int, purpose_type: str) -> None:
        if purpose_type == "PIN":
            purpose_desc = "pin"
        elif purpose_type == "OBSTRUCTION":
            purpose_desc = "obstruction"
        elif purpose_type == "LABEL":
            purpose_desc = "label"
        elif purpose_type == "OUTLINE":
            purpose_desc = "outline"
        else:
            purpose_desc = "drawing"
        entries.append(
            LayerInfoData(
                name=name,
                index=index,
                sub_index=sub_index,
                purpose_type=purpose_type,
                purpose_description=purpose_desc,
            )
        )

    for match in re.finditer(r"(\d+)/(\d+)\s*:\s*([^\n]+)", map_str):
        index = int(match.group(1))
        sub_index = int(match.group(2))
        name = match.group(3).strip()
        upper = name.upper()
        if ".PIN" in upper:
            purpose = "PIN"
        elif ".OBS" in upper:
            purpose = "OBSTRUCTION"
        elif ".LABEL" in upper:
            purpose = "LABEL"
        elif "OVERLAP" in upper:
            purpose = "OUTLINE"
        else:
            purpose = "DRAWING"
        add_entry(name, index, sub_index, purpose)

    if not entries:
        # Many `.lyt` files keep canonical layer map in connectivity `symbols`.
        lyt_text = lyt_path.read_text(encoding="utf-8")
        for sym in re.finditer(r"<symbols>\s*([^<]+)\s*</symbols>", lyt_text):
            payload = sym.group(1).strip()
            sm = re.match(r"([A-Za-z0-9_.]+)\s*=\s*'([^']+)'", payload)
            if sm is None:
                continue
            base_name = sm.group(1).strip()
            specs = [part.strip() for part in sm.group(2).split("+") if part.strip()]
            for idx, spec in enumerate(specs):
                lm = re.match(r"(\d+)\s*/\s*(\d+)", spec)
                if lm is None:
                    continue
                layer = int(lm.group(1))
                datatype = int(lm.group(2))
                if idx == 0:
                    add_entry(base_name, layer, datatype, "DRAWING")
                elif idx == 1:
                    add_entry(f"{base_name}.PIN", layer, datatype, "PIN")
                else:
                    add_entry(f"{base_name}.ALT{idx}", layer, datatype, "DRAWING")
    unique: dict[str, LayerInfoData] = {}
    for entry in entries:
        unique.setdefault(entry.name, entry)
    return tuple(sorted(unique.values(), key=lambda x: (x.index, x.sub_index, x.name)))


def read_technology_proto(path: Path) -> vtech.Technology:
    """Read `vlsir.tech.Technology` from `.pb` or text-proto (`.pbtxt`)."""
    tech = vtech.Technology()
    if path.suffix == ".pb":
        tech.ParseFromString(path.read_bytes())
    else:
        text_format.Parse(path.read_text(encoding="utf-8"), tech)
    return tech


def dbu_um_from_technology(tech: vtech.Technology, default: float = 0.001) -> float:
    """Derive layout DBU in microns from LEF `DATABASE MICRONS`."""
    db_units = tech.rules.lef_units.database_microns
    if db_units > 0:
        return 1.0 / float(db_units)
    return default


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


def find_technology_layer_name(
    tech: vtech.Technology,
    aliases: tuple[str, ...] | list[str],
) -> str | None:
    """
    Find a layer-name in `tech.layers` matching any alias (case-insensitive).

    Returns:
        The exact stored name if found, else `None`.
    """
    alias_set = _normalized_aliases(aliases)
    for info in tech.layers:
        if info.name.upper() in alias_set:
            return info.name
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


def resolve_layer_index_from_technology(
    layout: kdb.Layout,
    tech: vtech.Technology,
    aliases: tuple[str, ...] | list[str],
) -> int | None:
    """Resolve KLayout layer-index by alias from `Technology.layers`."""
    spec = resolve_layer_spec_from_technology(tech, aliases)
    if spec is None:
        return None
    return layout.layer(spec[0], spec[1])


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


def layer_index_optional(layout: kdb.Layout, preset: TechLayoutPreset, name: str) -> int | None:
    """Resolve a named layer-index, returning `None` when undefined."""
    if name not in preset.layers:
        return None
    layer, purpose = preset.layers[name]
    return layout.layer(layer, purpose)


def tech_layout_preset_from_vlsir(
    tech: vtech.Technology,
    fallback_name: str = "tech",
) -> TechLayoutPreset:
    """
    Build `TechLayoutPreset` from `vlsir.tech.Technology` rules/layer mapping.

    Required layer aliases:
    - active: `ACTIVE|OD|ACTIV`
    - poly: `POLY|PO|GATPOLY`
    - contact: `CONTACT|CO|CONT`
    - metal1: `M1|METAL1`
    """

    def must_spec(aliases: tuple[str, ...], logical_name: str) -> tuple[int, int]:
        spec = resolve_layer_spec_from_technology(tech, aliases)
        if spec is None:
            raise ValueError(
                f"Could not resolve required layer '{logical_name}' from aliases {aliases}."
            )
        return spec

    name = tech.name or fallback_name

    active_aliases = ("ACTIVE", "OD", "ACTIV")
    poly_aliases = ("POLY", "PO", "GATPOLY")
    cont_aliases = ("CONTACT", "CO", "CONT")
    m1_aliases = ("M1", "METAL1")

    m1_width = technology_rule_value(tech, m1_aliases, "WIDTH") or 0.14
    m1_spacing = technology_rule_spacing(tech, m1_aliases, width=m1_width, prl=0.0) or 0.14
    cont_size = technology_rule_value(tech, cont_aliases, "WIDTH") or 0.16
    cont_spacing = technology_rule_spacing(tech, cont_aliases, width=cont_size, prl=0.0) or 0.18
    active_width = technology_rule_value(tech, active_aliases, "WIDTH") or 0.15
    poly_width = technology_rule_value(tech, poly_aliases, "WIDTH") or 0.13
    gate_length_min = (
        technology_rule_value(tech, poly_aliases, "MINLENGTH")
        or technology_rule_value(tech, poly_aliases, "MINGATELENGTH")
        or poly_width
    )

    cont_enc_active = (
        technology_pair_rule_value(tech, active_aliases, cont_aliases, "ENCLOSURE")
        or 0.07
    )
    cont_enc_poly = (
        technology_pair_rule_value(tech, poly_aliases, cont_aliases, "ENCLOSURE")
        or cont_enc_active
    )
    cont_enc_metal = (
        technology_pair_rule_value(tech, m1_aliases, cont_aliases, "ENCLOSURE") or 0.06
    )
    cont_gate_dist = (
        technology_pair_rule_value(tech, poly_aliases, cont_aliases, "SPACING")
        or cont_spacing * 0.5
    )
    poly_over_active = (
        technology_pair_rule_value(tech, active_aliases, poly_aliases, "ENCLOSURE")
        or max(gate_length_min, 0.18)
    )
    psd_over_active = (
        technology_pair_rule_value(tech, active_aliases, ("PSD", "PPLUS"), "ENCLOSURE")
        or 0.18
    )
    nwell_over_active = (
        technology_pair_rule_value(tech, active_aliases, ("NWELL", "NW"), "ENCLOSURE")
        or 0.31
    )

    track_pitch = max(m1_width + m1_spacing, 0.2)
    track_count = 9
    stdcell_height = track_count * track_pitch
    m1_rail_width = max(2 * m1_width, m1_width + 0.5 * m1_spacing)

    layers: dict[str, tuple[int, int]] = {
        "active": must_spec(active_aliases, "active"),
        "poly": must_spec(poly_aliases, "poly"),
        "contact": must_spec(cont_aliases, "contact"),
        "metal1": must_spec(m1_aliases, "metal1"),
    }

    opt_map: list[tuple[str, tuple[str, ...]]] = [
        ("metal1_pin", ("M1.PIN", "METAL1.PIN")),
        ("nsd", ("NSD", "NPLUS", "NPLUSDIFF")),
        ("psd", ("PSD", "PPLUS", "PPLUSDIFF")),
        ("nwell", ("NWELL", "NW")),
        ("text", ("TEXT", "LABEL")),
        ("pr_boundary", ("PR_BOUNDARY", "BOUNDARY", "OVERLAP", "OUTLINE")),
    ]
    for logical, aliases in opt_map:
        spec = resolve_layer_spec_from_technology(tech, aliases)
        if spec is not None:
            layers[logical] = spec

    if "metal1_pin" not in layers:
        layers["metal1_pin"] = layers["metal1"]

    return TechLayoutPreset(
        name=name,
        dbu_um=dbu_um_from_technology(tech),
        stdcell_height_um=stdcell_height,
        track_count=track_count,
        track_pitch_um=track_pitch,
        gate_length_min_um=gate_length_min,
        finger_width_min_um=active_width,
        cont_size_um=cont_size,
        cont_spacing_um=cont_spacing,
        cont_enc_active_um=cont_enc_active,
        cont_enc_poly_um=cont_enc_poly,
        cont_enc_metal_um=cont_enc_metal,
        cont_gate_dist_um=cont_gate_dist,
        poly_over_active_um=poly_over_active,
        psd_over_active_um=psd_over_active,
        nwell_over_active_um=nwell_over_active,
        m1_width_um=m1_width,
        m1_rail_width_um=m1_rail_width,
        layers=layers,
    )


def ihp130_layout_preset() -> TechLayoutPreset:
    """
    Return IHP130 defaults derived from IHP Open PDK values.

    Key references:
    - stdcell row height: `3.78um`
    - FEOL rules from IHP `tech.py` (contact/poly/metal parameters)
    """

    return TechLayoutPreset(
        name="ihp130",
        dbu_um=0.001,  # 1nm dbu
        stdcell_height_um=3.78,
        track_count=9,
        track_pitch_um=3.78 / 9.0,
        gate_length_min_um=0.13,
        finger_width_min_um=0.15,
        cont_size_um=0.16,
        cont_spacing_um=0.18,
        cont_enc_active_um=0.07,
        cont_enc_poly_um=0.07,
        cont_enc_metal_um=0.06,
        cont_gate_dist_um=0.11,
        poly_over_active_um=0.18,
        psd_over_active_um=0.18,
        nwell_over_active_um=0.31,
        m1_width_um=0.14,
        m1_rail_width_um=0.28,
        layers={
            "active": (1, 0),
            "poly": (5, 0),
            "contact": (6, 0),
            "nsd": (7, 0),
            "metal1": (8, 0),
            "metal1_pin": (8, 2),
            "psd": (14, 0),
            "nwell": (31, 0),
            "text": (63, 0),
            "pr_boundary": (189, 0),
        },
    )


def get_layout_preset(name: str) -> TechLayoutPreset:
    """Lookup a layout preset by process name."""
    normalized = name.lower()
    if normalized in {"ihp130", "ihp", "sg13g2"}:
        return ihp130_layout_preset()
    if normalized in {"tsmc65", "tsmc28"}:
        raise NotImplementedError(
            f"Layout preset '{name}' is planned but not implemented in this phase."
        )
    raise ValueError(f"Unknown layout preset '{name}'.")


def create_layout(preset: TechLayoutPreset) -> kdb.Layout:
    """Create a KLayout layout object with preset DBU."""
    layout = kdb.Layout()
    layout.dbu = preset.dbu_um
    return layout


def layer_index(layout: kdb.Layout, preset: TechLayoutPreset, name: str) -> int:
    """Resolve a named logical layer to a KLayout layer index."""
    if name not in preset.layers:
        raise KeyError(f"Layer '{name}' is not defined in preset '{preset.name}'.")
    layer, purpose = preset.layers[name]
    return layout.layer(layer, purpose)


def um_to_dbu(layout: kdb.Layout, value_um: float) -> int:
    """Convert microns to integer DBU coordinates."""
    return int(round(value_um / layout.dbu))


def dbu_to_um(layout: kdb.Layout, value_dbu: int) -> float:
    """Convert integer DBU to microns."""
    return value_dbu * layout.dbu


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
