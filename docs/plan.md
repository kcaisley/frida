# Layout Refactor Plan: Split Serialization + Canonical Layer IDs

## Summary
- Keep the generation model as **PDK-aware at input time**: generators receive `vlsir.tech`-derived rules and layer mappings and produce concrete KLayout geometry.
- Build KLayout geometry in memory using canonical, process-agnostic names (`OD`, `PO`, `M1.draw`, `M2.pin`, `VIA3`, etc.).
- Split the current mixed module into focused modules, including a dedicated serializer file `layout/serialize.py`.
- Standardize primitive generator APIs on **canonical process-agnostic layer IDs** (e.g. `M1`, `M2`, `POLY`) with per-PDK alias mapping.
- Resolve canonical layer names to real `(layer, datatype)` only during `vlsir.raw` serialization, using `vlsir.tech.Technology.layers` (`LayerInfo`) from the loaded technology object.
- Apply a **hard cutover** (no compatibility shim): update all imports in one change.
- Restructure rules as a typed, layer-owned API using canonical enum keys (`L.OD`, `L.PO`, `L.CO`, `L.M1` ... `L.M10`, `L.VIA1` ... `L.VIA9`, etc.) with lower-case rule names.
   - same-layer spacing owned by the layer (`deck.layer(L.M1).min_spacing(rule=...)`)
   - inter-layer spacing uses `to=` and is still owned by the higher layer (`deck.layer(L.M2).min_spacing(to=L.M1, ...)`)
   - enclosure is owned by the higher layer (`deck.layer(L.M1).min_enclosure(of=L.CO, ...)`)
   - min-area/ min-width/ related per-layer checks stay on the owning layer
   - parallel-run-length spacing is represented as multiple explicit entries (for example three `min_spacing` calls with different `run_length`), not a spacing-table object
   - this same typed layer enum is used in generators, then mapped to process `(layer, datatype)` only at `vlsir.raw` serialization via `Technology.layers`
- Rule definitions are authored directly in Python `RuleDeck` code and treated as source-of-truth; do not add a reverse `Technology -> RuleDeck` conversion feature.
- Keep explicit stackup ordering per PDK even with canonical naming.
- Canonical layer IDs cover the full common stack up through `M10`; each PDK alias-map may implement only the subset it supports and should fail clearly on unresolved layers.
- Keep transistor/capacitor PCell generators mostly monolithic and top-to-bottom: one primary layout function plus at most 2-3 focused helpers for repeated operations.
- Keep serialization as a separate component from generator flow (target: `flow/layout/serialize.py`; transitional colocated end-of-file block is acceptable only if needed during migration).

## Review Findings (Verified)
1. High: one module currently mixes unrelated responsibilities (tech schema + rule queries + KLayout drawing + VLSIR raw serialization), which makes maintenance and API design hard.  
   File: [layout.py](/home/kcaisley/frida/flow/layout/layout.py#L1)
2. Medium: primitive generators already depend on PDK rule values at generation time, which matches your preferred flow and should be formalized as the contract.  
   Files: [nmos.py](/home/kcaisley/frida/flow/layout/nmos.py#L1), [momcap.py](/home/kcaisley/frida/flow/layout/momcap.py#L1)
3. Medium: layer naming is partially process-agnostic via alias tuples, but not standardized as a single canonical API.  
   Files: [nmos.py](/home/kcaisley/frida/flow/layout/nmos.py#L1), [momcap.py](/home/kcaisley/frida/flow/layout/momcap.py#L1)
4. Medium: KLayout supports absolute transforms, hierarchy, and arrays, but not a built-in declarative relative-placement constraint system. Relative placement would be your own abstraction layer.
5. Verification result: Layout21 and BFG do **not** use a “generic geometry then post-raw pdkwalker” flow for raw export.
   - Layout21 raw exports concrete geometry directly; Layout21 tetris has a compile step that resolves relative placements to absolute before raw conversion.
   - BFG loads technology/rules, builds concrete layout using that DB, then serializes to `vlsir.raw`.
   Files: [/home/kcaisley/libs/Layout21/layout21raw/src/proto.rs](/home/kcaisley/libs/Layout21/layout21raw/src/proto.rs#L1), [/home/kcaisley/libs/Layout21/layout21tetris/src/placer.rs](/home/kcaisley/libs/Layout21/layout21tetris/src/placer.rs#L1), [/home/kcaisley/libs/Layout21/layout21tetris/src/conv/raw.rs](/home/kcaisley/libs/Layout21/layout21tetris/src/conv/raw.rs#L1), [/home/kcaisley/libs/bfg/src/layout.cc](/home/kcaisley/libs/bfg/src/layout.cc#L327), [/home/kcaisley/libs/bfg/src/physical_properties_database.cc](/home/kcaisley/libs/bfg/src/physical_properties_database.cc#L52)

## Public API / Interface Changes
- Add `flow/layout/serialize.py` with:
  - `layout_to_vlsir_raw(layout, domain="frida.layout") -> vlsir.raw_pb2.Library`
  - use `vlsir.raw_pb2` directly in Python code (no local alias)
  - `vlsir_raw_to_disk(library, pb_path, pbtxt_path=None) -> None`
  - `export_layout(layout, out_dir, stem, domain="frida.layout", write_debug_gds=False) -> ExportArtifacts`
  - `ExportArtifacts` dataclass
- Add `flow/layout/tech.py` with:
  - existing technology dataclasses and proto read/write helpers
  - existing rule lookup utilities (`technology_rule_value`, spacing, pair rules, etc.)
- Add `flow/layout/klayout.py` with:
  - `create_layout`, `nm_to_dbu`, `insert_box_nm`, `insert_text_nm`
  - keep these as thin wrappers so generators remain integer-nm driven and geometry insertion stays repeatable
- Add `flow/layout/layers.py` with:
  - canonical typed layer ID enum/type (process-agnostic) reused by generators and rules, including full stack definitions through `M10`/`VIA9`
  - stack-order metadata for ownership checks
  - alias-map type and resolver helpers from canonical ID -> actual `(layer, datatype)` using `Technology.layers`
  - `Technology.layers` refers to the repeated `LayerInfo` entries in `vlsir.tech.Technology`
- Add `flow/layout/rules.py` with:
  - typed rule records (`SpacingRule`, `EnclosureRule`, `AreaRule`)
  - `RuleDeck` + `LayerRules` method API
  - `min_spacing(to=..., rule=..., run_length=...)` (`to` defaults to owner for same-layer spacing)
  - `min_enclosure(of=..., rule=...)` and `min_area(rule=...)`
  - represent PRL spacing as multiple rule records instead of a table payload
- Update callers to import from new modules directly (hard cutover).
- Update package exports in [__init__.py](/home/kcaisley/frida/flow/layout/__init__.py#L1) to reflect new module boundaries.

## Full Code Examples
### Rules API (typed layers, owner checks, explicit PRL entries)
```python
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Self

import hdl21 as h


class L(Enum):
    OD = auto()
    PO = auto()
    CO = auto()
    M1 = auto()
    VIA1 = auto()
    M2 = auto()
    VIA2 = auto()
    M3 = auto()
    VIA3 = auto()
    M4 = auto()
    VIA4 = auto()
    M5 = auto()
    VIA5 = auto()
    M6 = auto()
    VIA6 = auto()
    M7 = auto()
    VIA7 = auto()
    M8 = auto()
    VIA8 = auto()
    M9 = auto()
    VIA9 = auto()
    M10 = auto()
    NP = auto()
    PP = auto()


Z = {
    L.OD: 1,
    L.PO: 2,
    L.CO: 3,
    L.M1: 4,
    L.VIA1: 5,
    L.M2: 6,
    L.VIA2: 7,
    L.M3: 8,
    L.VIA3: 9,
    L.M4: 10,
    L.VIA4: 11,
    L.M5: 12,
    L.VIA5: 13,
    L.M6: 14,
    L.VIA6: 15,
    L.M7: 16,
    L.VIA7: 17,
    L.M8: 18,
    L.VIA8: 19,
    L.M9: 20,
    L.VIA9: 21,
    L.M10: 22,
    L.NP: 1,
    L.PP: 1,
}


@dataclass(frozen=True)
class SpacingRule:
    owner: L
    to: L
    rule: h.Prefixed
    run_length: h.Prefixed | None = None


@dataclass(frozen=True)
class EnclosureRule:
    owner: L
    of: L
    rule: h.Prefixed


@dataclass(frozen=True)
class AreaRule:
    owner: L
    rule: h.Prefixed


@dataclass
class RuleDeck:
    spacing: list[SpacingRule] = field(default_factory=list)
    enclosure: list[EnclosureRule] = field(default_factory=list)
    area: list[AreaRule] = field(default_factory=list)

    def layer(self, owner: L) -> LayerRules:
        return LayerRules(owner=owner, deck=self)


@dataclass
class LayerRules:
    owner: L
    deck: RuleDeck

    def min_spacing(
        self,
        *,
        rule: h.Prefixed,
        to: L | None = None,
        run_length: h.Prefixed | None = None,
    ) -> Self:
        target = self.owner if to is None else to
        if Z[self.owner] < Z[target]:
            msg = f"{self.owner.name} cannot own spacing to higher layer {target.name}"
            raise ValueError(msg)
        self.deck.spacing.append(
            SpacingRule(owner=self.owner, to=target, rule=rule, run_length=run_length)
        )
        return self

    def min_enclosure(self, *, of: L, rule: h.Prefixed) -> Self:
        if Z[self.owner] <= Z[of]:
            msg = f"{self.owner.name} must be above {of.name} to own enclosure"
            raise ValueError(msg)
        self.deck.enclosure.append(EnclosureRule(owner=self.owner, of=of, rule=rule))
        return self

    def min_area(self, *, rule: h.Prefixed) -> Self:
        self.deck.area.append(AreaRule(owner=self.owner, rule=rule))
        return self


deck = RuleDeck()

# Same-layer spacing with three PRL points (explicit entries, no table object)
deck.layer(L.M1).min_spacing(rule=80 * h.n)
deck.layer(L.M1).min_spacing(rule=100 * h.n, run_length=200 * h.n)
deck.layer(L.M1).min_spacing(rule=120 * h.n, run_length=500 * h.n)

# Cross-layer spacing uses `to=`, owned by the higher layer
deck.layer(L.M2).min_spacing(to=L.M1, rule=120 * h.n)

# Higher layer owns enclosure of lower layer
deck.layer(L.M1).min_enclosure(of=L.CO, rule=50 * h.n)

# Per-layer min area
deck.layer(L.M1).min_area(rule=500 * (h.n * h.n))
```

### Primitive Generator Example (PCell Code)
```python
from __future__ import annotations

import klayout.db as kdb

from flow.layout.layers import L, LayerMap
from flow.layout.tech import Technology, technology_rule_value_nm


def nm_to_dbu(layout: kdb.Layout, nm: int) -> int:
    # layout.dbu is microns per database unit
    return int(round((nm * 1e-3) / layout.dbu))

# just an example, as though an single layer rectabl were our whole pcell
# in reality we wouldn't have a function this specific or granualr for a real pcell
def draw_m1_track(
    layout: kdb.Layout,
    top_cell: kdb.Cell,
    *,
    tech: Technology,
    layer_map: LayerMap,
    width_mult: int = 1,
    length_mult: int = 10,
) -> None:
    # Pull physical mins in integer nanometers from technology input.
    m1_min_width_nm = technology_rule_value_nm(tech, layer="M1", rule="min_width")
    m1_min_pitch_nm = technology_rule_value_nm(tech, layer="M1", rule="min_pitch")

    width_nm = width_mult * m1_min_width_nm
    length_nm = length_mult * m1_min_pitch_nm

    # Resolve typed canonical layer -> concrete (layer, datatype).
    lp = layer_map.draw[L.M1]
    layer_index = layout.layer(lp.gds_layer, lp.gds_datatype)

    # Draw concrete geometry in KLayout memory using integer DBU coordinates.
    x0 = nm_to_dbu(layout, 0)
    y0 = nm_to_dbu(layout, 0)
    x1 = nm_to_dbu(layout, length_nm)
    y1 = nm_to_dbu(layout, width_nm)
    top_cell.shapes(layer_index).insert(kdb.Box(x0, y0, x1, y1))
```

### Serializer Example (KLayout -> VLSIR.Raw)
```python
from __future__ import annotations

import klayout.db as kdb
import vlsir.raw_pb2

from flow.layout.layers import L
from flow.layout.tech import Technology


def find_layer_info(tech: Technology, canonical_layer: L, purpose: str) -> tuple[int, int]:
    # Canonical name lookup happens only at serialization time.
    expected_name = f"{canonical_layer.name}.{purpose}"
    for li in tech.layers:
        if li.name == expected_name:
            return (li.gds_layer, li.gds_datatype)
    raise KeyError(f"Missing layer mapping for {expected_name}")


def add_box_as_raw_rect(
    raw_struct: vlsir.raw_pb2.Struct,
    *,
    gds_layer: int,
    gds_datatype: int,
    box: kdb.Box,
) -> None:
    elem = raw_struct.elements.add()
    elem.layer.number = gds_layer
    elem.layer.purpose = gds_datatype
    elem.rect.p0.x = box.left
    elem.rect.p0.y = box.bottom
    elem.rect.p1.x = box.right
    elem.rect.p1.y = box.top


def serialize_draw_layer(
    top_cell: kdb.Cell,
    layer_index: int,
    *,
    raw_struct: vlsir.raw_pb2.Struct,
    gds_layer: int,
    gds_datatype: int,
) -> None:
    # Serializer only converts already-generated geometry.
    for shape in top_cell.shapes(layer_index).each():
        if shape.is_box():
            add_box_as_raw_rect(
                raw_struct,
                gds_layer=gds_layer,
                gds_datatype=gds_datatype,
                box=shape.box,
            )
```

## Implementation Plan
- Execution order is defined only by [Ordered Execution Checklist](#ordered-execution-checklist) at the bottom of this file.
- This section intentionally avoids duplicate step numbering to keep one authoritative plan of record.

## Tests and Scenarios
1. Serializer equivalence tests:
   - rectangle/polygon/path/text conversion
   - instance serialization including arrays expansion and transforms
   - assert output structure invariants match prior behavior
2. Layer resolver tests:
   - canonical ID resolves across alias variants (`M1`, `METAL1`, process name forms)
   - missing canonical ID fails with clear error
3. Rule API tests:
   - invalid owner/target ordering is rejected for enclosure and inter-layer spacing
   - `min_spacing` default `to` behavior is same-layer
   - PRL spacing entries are preserved as separate records with distinct `run_length`
4. Generator regression tests:
   - NMOS and MOMCAP smoke tests still pass and produce expected top-level geometry/layer usage
5. Integration test:
   - full flow from tech proto read -> generator -> KLayout memory -> raw protobuf export
6. Acceptance criteria:
   - no remaining imports from `flow.layout.layout`
   - all existing layout tests pass, plus new resolver/serializer tests pass

## Assumptions and Defaults
- Default model is PDK-aware generation (chosen): no generic post-serialization “pdkwalker compiler” stage for physical rules.
- Canonical layer IDs are the stable generator-facing interface; PDK alias maps are the adaptation layer.
- Rule source-of-truth is authored Python `RuleDeck` construction; no reverse-import `Technology -> RuleDeck` path is in scope.
- KLayout remains the in-memory source-of-truth for concrete geometry prior to raw serialization.
- No compatibility shim is kept; this is a one-shot migration across FRIDA internal call sites.

## Ordered Execution Checklist
1. [x] Create `flow/layout/layers.py` with canonical typed IDs through `L.M10`/`L.VIA9`, FEOL/implant/well/purpose IDs, and stack-order metadata.
2. [x] Create `flow/layout/rules.py` with `RuleDeck`/`LayerRules` and typed rule records (`SpacingRule`, `EnclosureRule`, `AreaRule`).
   - include layer-owned API coverage for:
   - same-layer spacing (`min_spacing(rule=...)`)
   - PRL spacing (`min_spacing(rule=..., run_length=...)`)
   - inter-layer spacing ownership (`min_spacing(to=..., rule=...)`)
   - higher-layer enclosure (`min_enclosure(of=..., rule=...)`)
   - per-layer area (`min_area(rule=...)`)
3. [x] Enforce authored `RuleDeck` as the only rule-entry path; do not implement `Technology -> RuleDeck` reverse conversion.
4. [x] Ensure authored rules can express all required families (including via-via spacing and opposite-implant spacing/enclosure) and cover them in tests/examples.
5. [x] Move tech dataclasses, proto I/O, and rule/layer lookup helpers out of `flow/layout/layout.py` into `flow/layout/tech.py`.
   - preserve behavior for existing lookup utilities (`technology_rule_value`, spacing helpers, pair-rule helpers).
6. [x] Move and standardize KLayout geometry helpers into `flow/layout/klayout.py` with nm-driven helper entry points (`nm_to_dbu`, `insert_box_nm`, `insert_text_nm`).
7. [x] Run a repo-wide migration from legacy `um` geometry/rule paths to `nm`-driven paths and remove superseded helper APIs.
8. [x] Move KLayout -> VLSIR raw serialization/export functions into `flow/layout/serialize.py` (using `vlsir.raw_pb2` directly).
   - serializer must convert existing KLayout geometry only (no new geometry synthesis in serialization).
9. [x] Refactor [nmos.py](/home/kcaisley/frida/flow/layout/nmos.py#L1) to canonical layer IDs and keep generation as one primary top-to-bottom function (with at most 2-3 focused helpers).
   - keep extraction of physical rules from authored rule deck + tech inputs at generator entry.
   - remove process-specific layer-name assumptions from generator internals.
   - keep serialization outside generator flow.
10. [x] Refactor [momcap.py](/home/kcaisley/frida/flow/layout/momcap.py#L1) to canonical layer IDs and keep generation as one primary top-to-bottom function (with at most 2-3 focused helpers).
   - keep extraction of physical rules from authored rule deck + tech inputs at generator entry.
   - remove process-specific layer-name assumptions from generator internals.
   - keep serialization outside generator flow.
11. [x] Update all PDK layout metadata modules to expose/consume canonical alias maps and provide clear errors for unsupported canonical layers.
   - apply this pattern to [/home/kcaisley/frida/pdk/ihp130/layout/pdk_layout.py](/home/kcaisley/frida/pdk/ihp130/layout/pdk_layout.py#L1) and mirror for other `pdk/*/layout/` modules.
12. [x] Add per-PDK validation tests for canonical layer coverage (`M1..M10`, `VIA1..VIA9`) and expected failure behavior on unsupported layers.
13. [x] Update [__init__.py](/home/kcaisley/frida/flow/layout/__init__.py#L1) exports and perform hard-cutover import updates across FRIDA (no `flow.layout.layout` imports left).
14. [x] Replace or remove [layout.py](/home/kcaisley/frida/flow/layout/layout.py#L1) once no importers remain.
   - either keep a minimal boundary/doc module or remove the file entirely.
15. [x] Add/ update tests: serializer equivalence, layer resolver coverage, rule API behavior, generator regressions, and full integration flow.
   - serializer: rectangle/polygon/path/text + instance transforms/arrays
   - resolver: canonical ID alias resolution + clear missing-layer failures
   - rule API: ownership checks, default `to` behavior, PRL entry preservation
   - generators: NMOS + MOMCAP smoke/regression behavior
   - integration: tech/rules -> generator -> KLayout memory -> raw protobuf export
16. [x] Run the layout test suite and confirm acceptance criteria are met before finalizing.
