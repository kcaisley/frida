"""Typed layout rule deck and generic->tech layer mapping utilities."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Self

import hdl21 as h
import klayout.db as kdb

from .dsl import L, Layer, LayerRef


@dataclass(frozen=True)
class LayerInfoData:
    """Tech layer-purpose descriptor used for remap and tech serialization."""

    name: str
    index: int
    sub_index: int = 0
    purpose_type: str = "DRAWING"
    purpose_description: str = "drawing"


@dataclass(frozen=True)
class RuleStatementData:
    """Tokenized rule statement for technology protobuf conversion."""

    keyword: str
    tokens: tuple[str | int | float | bool, ...] = ()
    raw: str = ""


@dataclass(frozen=True)
class LayerRuleSetData:
    """Rules associated with a single generic layer name."""

    name: str
    layer_type: str = ""
    rules: tuple[RuleStatementData, ...] = ()


@dataclass(frozen=True)
class LayerPairRuleSetData:
    """Rules associated with a pair of generic layer names."""

    first_layer: str
    second_layer: str
    rules: tuple[RuleStatementData, ...] = ()
    source: str = "manual"


TechLayerMap = dict[LayerRef, LayerInfoData]


STACK_ORDER: dict[Layer, int] = {
    Layer.OD: 1,
    Layer.PO: 2,
    Layer.CO: 3,
    Layer.M1: 4,
    Layer.VIA1: 5,
    Layer.M2: 6,
    Layer.VIA2: 7,
    Layer.M3: 8,
    Layer.VIA3: 9,
    Layer.M4: 10,
    Layer.VIA4: 11,
    Layer.M5: 12,
    Layer.VIA5: 13,
    Layer.M6: 14,
    Layer.VIA6: 15,
    Layer.M7: 16,
    Layer.VIA7: 17,
    Layer.M8: 18,
    Layer.VIA8: 19,
    Layer.M9: 20,
    Layer.VIA9: 21,
    Layer.M10: 22,
    Layer.NP: 1,
    Layer.PP: 1,
    Layer.NWELL: 1,
    Layer.VTH_LVT: 1,
    Layer.VTH_HVT: 1,
    Layer.TEXT: 99,
    Layer.PR_BOUNDARY: 99,
}


@dataclass(frozen=True)
class SpacingRule:
    owner: Layer
    to: Layer
    rule: h.Prefixed
    run_length: h.Prefixed | None = None


@dataclass(frozen=True)
class EnclosureRule:
    owner: Layer
    of: Layer
    rule: h.Prefixed


@dataclass(frozen=True)
class AreaRule:
    owner: Layer
    rule: h.Prefixed


@dataclass(frozen=True)
class WidthRule:
    owner: Layer
    rule: h.Prefixed


@dataclass
class RuleDeck:
    """Typed authored layout rule deck."""

    database_microns: int = 1000
    manufacturing_grid_microns: float = 0.001
    spacing: list[SpacingRule] = field(default_factory=list)
    enclosure: list[EnclosureRule] = field(default_factory=list)
    area: list[AreaRule] = field(default_factory=list)
    width: list[WidthRule] = field(default_factory=list)

    def layer(self, owner: Layer) -> LayerRules:
        return LayerRules(owner=owner, deck=self)


@dataclass
class LayerRules:
    owner: Layer
    deck: RuleDeck

    def min_spacing(
        self,
        *,
        rule: h.Prefixed,
        to: Layer | None = None,
        run_length: h.Prefixed | None = None,
    ) -> Self:
        target = self.owner if to is None else to
        if STACK_ORDER[self.owner] < STACK_ORDER[target]:
            raise ValueError(
                f"{self.owner.name} cannot own spacing to higher layer {target.name}."
            )
        self.deck.spacing.append(
            SpacingRule(owner=self.owner, to=target, rule=rule, run_length=run_length)
        )
        return self

    def min_enclosure(self, *, of: Layer, rule: h.Prefixed) -> Self:
        if self.owner is of or STACK_ORDER[self.owner] < STACK_ORDER[of]:
            raise ValueError(
                f"{self.owner.name} must be above {of.name} to own enclosure."
            )
        self.deck.enclosure.append(EnclosureRule(owner=self.owner, of=of, rule=rule))
        return self

    def min_area(self, *, rule: h.Prefixed) -> Self:
        self.deck.area.append(AreaRule(owner=self.owner, rule=rule))
        return self

    def min_width(self, *, rule: h.Prefixed) -> Self:
        self.deck.width.append(WidthRule(owner=self.owner, rule=rule))
        return self


def _prefixed_to_um(value: h.Prefixed) -> float:
    return round(float(value) * 1e6, 12)


def _prefixed_to_um2(value: h.Prefixed) -> float:
    return round(float(value) * 1e12, 12)


def rule_statement(
    keyword: str,
    *tokens: str | int | float | bool,
) -> RuleStatementData:
    raw_tokens = " ".join(str(t) for t in tokens)
    raw = f"{keyword} {raw_tokens}".strip()
    return RuleStatementData(keyword=keyword.upper(), tokens=tuple(tokens), raw=raw)


def rule_deck_to_tech_rules(
    deck: RuleDeck,
) -> tuple[tuple[LayerRuleSetData, ...], tuple[LayerPairRuleSetData, ...]]:
    """Convert authored typed rules to tech rule-set payloads.

    Uses generic layer names (`L.M1 -> "M1"`) as technology-rule keys.
    """

    layer_rules: dict[Layer, list[RuleStatementData]] = {}
    pair_rules: dict[tuple[Layer, Layer], list[RuleStatementData]] = {}

    for stmt in deck.width:
        layer_rules.setdefault(stmt.owner, []).append(
            rule_statement("WIDTH", _prefixed_to_um(stmt.rule))
        )

    for stmt in deck.area:
        layer_rules.setdefault(stmt.owner, []).append(
            rule_statement("AREA", _prefixed_to_um2(stmt.rule))
        )

    for spacing in deck.spacing:
        spacing_um = _prefixed_to_um(spacing.rule)
        if spacing.run_length is None:
            statement = rule_statement("SPACING", spacing_um)
        else:
            statement = rule_statement(
                "SPACING",
                spacing_um,
                "PARALLELRUNLENGTH",
                _prefixed_to_um(spacing.run_length),
            )
        if spacing.owner is spacing.to:
            layer_rules.setdefault(spacing.owner, []).append(statement)
        else:
            pair_rules.setdefault((spacing.owner, spacing.to), []).append(statement)

    for enclosure in deck.enclosure:
        enc_um = _prefixed_to_um(enclosure.rule)
        pair_rules.setdefault((enclosure.owner, enclosure.of), []).append(
            rule_statement("ENCLOSURE", enc_um, enc_um)
        )

    out_layers: list[LayerRuleSetData] = []
    for layer, statements in layer_rules.items():
        out_layers.append(
            LayerRuleSetData(name=layer.name, layer_type="", rules=tuple(statements))
        )

    out_pairs: list[LayerPairRuleSetData] = []
    for (first, second), statements in pair_rules.items():
        out_pairs.append(
            LayerPairRuleSetData(
                first_layer=first.name,
                second_layer=second.name,
                rules=tuple(statements),
                source="manual",
            )
        )

    out_layers.sort(key=lambda item: item.name)
    out_pairs.sort(key=lambda item: (item.first_layer, item.second_layer))
    return tuple(out_layers), tuple(out_pairs)


def map_generic_to_tech_layers(
    layout: kdb.Layout, tech_layer_map: TechLayerMap
) -> None:
    """Mutate layout in-place: generic named layers -> concrete tech layers."""

    for ref, info in tech_layer_map.items():
        generic = L.generic_name(ref)
        src_idx = layout.find_layer(kdb.LayerInfo(generic))
        if src_idx is None or src_idx < 0:
            continue

        dst_idx = layout.layer(kdb.LayerInfo(info.index, info.sub_index, info.name))

        for cell in layout.each_cell():
            src_shapes = cell.shapes(src_idx)
            if src_shapes.is_empty():
                continue
            for shape in src_shapes.each():
                cell.shapes(dst_idx).insert(shape)
            src_shapes.clear()
