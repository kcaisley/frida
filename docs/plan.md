# Layout API Refactor Plan

## Goal

Make generator code read like this:

```python
layers = bind_generic_layers(layout)
R = rules_from_technology(tech, unit="nm")

rail_w = params.powerrail_mult * R.M1.width
track_pitch = R.M1.width + R.M1.spacing.M1

top.shapes(layers.M1).insert(kdb.Box(x0, y_vss0, x1, y_vss1))
top.shapes(layers.PIN1).insert(kdb.Box(x0, y_vss0, x0 + rail_w, y_vss1))
```

Key outcomes:

- `R` holds PDK rules in a readable, typed namespace (`R.M1.spacing.M1`, `R.VIA2.width`).
- `layers` holds bound KLayout layer indices (`layers.M1`, `layers.PIN2`, `layers.OD`).
- derived values are clearly separate from PDK rules (prefix derived with `drv_`).

---

## Why This Needs Typed Objects (Autocomplete)

- `dict` works for storage, but not good dot-path autocomplete (`rules["M1"]["spacing"]["M1"]`).
- `Enum` is good for names/ keys, but does not hold nested rule data naturally.
- best autocomplete path is typed classes/ dataclasses with explicit fields.

Recommendation:

- keep an enum for canonical names,
- expose runtime access through typed dataclass namespaces.

---

## Current Types: What They Mean Today

- `L` (`flow/layout/dsl.py`): convenience namespace exposing enums and helpers.
- `Layer`: generic logical layer enum (`M1`, `OD`, `VIA2`, etc).
- `LayerRef`: `(Layer, Purpose)` pair (`M1.draw`, `M1.pin`).
- `LayerInfoData`: serializable tech-layer descriptor (`name`, `index`, `sub_index`).
- `tuple[LayerInfoData]`: per-PDK layer catalog payload.
- `TechLayerMap`: mapping from generic `LayerRef` to concrete `LayerInfoData`.

This is functional, but generator ergonomics are not ideal.

---

## Proposed End-State Model (Three Main Concepts)

1. **Generic layer catalog** for generator scripts (`generic.*`, `layers.*`).
2. **Rule namespace** for rule lookups (`R.*`).
3. **Remap map** from generic `LayerInfo` to PDK `LayerInfo`.

---

## Proposed API by File

## `flow/layout/dsl.py`

### Keep

- existing param/generator decorators and parameter enums.

### Add

```python
from dataclasses import dataclass
import klayout.db as kdb

@dataclass(frozen=True)
class GenericLayerCatalog:
    OD: kdb.LayerInfo
    PO: kdb.LayerInfo
    CO: kdb.LayerInfo
    M1: kdb.LayerInfo
    PIN1: kdb.LayerInfo
    VIA1: kdb.LayerInfo
    M2: kdb.LayerInfo
    PIN2: kdb.LayerInfo
    VIA2: kdb.LayerInfo
    # ... through M9/ PIN9 (+ M10 if used)

@dataclass(frozen=True)
class BoundGenericLayers:
    OD: int
    PO: int
    CO: int
    M1: int
    PIN1: int
    VIA1: int
    M2: int
    PIN2: int
    VIA2: int
    # ...

def generic_layers() -> GenericLayerCatalog: ...
def bind_generic_layers(layout: kdb.Layout) -> BoundGenericLayers: ...
```

### Notes

- `generic_layers()` returns `kdb.LayerInfo` definitions (name + default layer/datatype).
- `bind_generic_layers(layout)` calls `layout.layer(db.LayerInfo(...))` and returns indices.
- this gives dot-path autocomplete in generator files (`layers.M1`, `layers.PIN2`).

---

## `flow/layout/tech.py`

### Keep

- rule-deck authoring (`RuleDeck`, `LayerRules`) and serialization bridge.

### Add runtime typed rule namespace

```python
from dataclasses import dataclass, field

@dataclass(frozen=True)
class PerTargetRule:
    OD: int | None = None
    PO: int | None = None
    CO: int | None = None
    M1: int | None = None
    VIA1: int | None = None
    M2: int | None = None
    # ...

@dataclass(frozen=True)
class LayerRuleView:
    width: int | None = None
    area: int | None = None
    spacing: PerTargetRule = field(default_factory=PerTargetRule)
    enclosure: PerTargetRule = field(default_factory=PerTargetRule)

@dataclass(frozen=True)
class RuleNamespace:
    OD: LayerRuleView = field(default_factory=LayerRuleView)
    PO: LayerRuleView = field(default_factory=LayerRuleView)
    CO: LayerRuleView = field(default_factory=LayerRuleView)
    M1: LayerRuleView = field(default_factory=LayerRuleView)
    VIA1: LayerRuleView = field(default_factory=LayerRuleView)
    M2: LayerRuleView = field(default_factory=LayerRuleView)
    # ... no PIN* entries by design

def rules_from_technology(tech: vtech.Technology, *, unit: str = "nm") -> RuleNamespace: ...
```

### Add remap primitives (LayerInfo to LayerInfo)

```python
LayerInfoMap = dict[kdb.LayerInfo, kdb.LayerInfo]

def remap_layers(layout: kdb.Layout, mapping: LayerInfoMap, *, delete_source: bool = True) -> None: ...
```

Implementation behavior:

- move/ copy all shapes from each source layer to destination layer,
- optionally delete source layers,
- require `layout.is_editable()` for in-place mutation safety.

---

## `flow/layout/serialize.py`

### Keep

- `write_technology_proto`, `read_technology_proto`, raw-layout export.

### Add

```python
def rule_namespace_from_proto(path: Path, *, unit: str = "nm") -> RuleNamespace: ...
def rule_namespace_from_tech(tech: vtech.Technology, *, unit: str = "nm") -> RuleNamespace: ...
```

### Casing policy

- keep keywords authored in lowercase by PDK code,
- do not force case during serialization,
- consumers should use case-insensitive parse during migration window.

---

## `pdk/<name>/layout/pdk_layout.py` (example: `pdk/ihp130/layout/pdk_layout.py`)

Each PDK file should provide only:

1. generic-to-tech layer mapping (`LayerInfoMap` style),
2. rule deck builder,
3. optional helper to return typed runtime rule namespace.

Example shape:

```python
def layer_map() -> LayerInfoMap:
    g = generic_layers()
    return {
        g.OD: kdb.LayerInfo(3, 0, "OD"),
        g.PO: kdb.LayerInfo(4, 0, "PO"),
        g.CO: kdb.LayerInfo(9, 0, "CO"),
        g.M1: kdb.LayerInfo(11, 0, "M1"),
        g.VIA1: kdb.LayerInfo(11, 1, "VIA1"),
        g.PIN1: kdb.LayerInfo(11, 2, "PIN1"),
        g.M2: kdb.LayerInfo(12, 0, "M2"),
        g.VIA2: kdb.LayerInfo(12, 1, "VIA2"),
        g.PIN2: kdb.LayerInfo(12, 2, "PIN2"),
    }

def ihp130_rule_deck() -> RuleDeck:
    deck = RuleDeck(database_microns=1000, manufacturing_grid_microns=0.005)
    deck.layer(L.M1).min_width(rule=160 * n).min_spacing(rule=180 * n)
    deck.layer(L.VIA2).min_width(rule=190 * n).min_spacing(rule=220 * n)
    # ...
    return deck
```

---

## Generator Coding Conventions After Refactor

1. bind layers once at top:

```python
layers = bind_generic_layers(layout)
```

2. parse rules once at top:

```python
R = rules_from_technology(tech, unit="nm")
```

3. distinguish names clearly:

- `R.*` = raw PDK rules,
- `drv_*` = derived geometry values.

Example:

```python
drv_gate_len = max(R.PO.width or 0, params.lf_mult * (R.PO.width or 0))
drv_sd_pitch = (R.CO.width or 0) + 2 * (R.CO.spacing.PO or 0) + drv_gate_len

top.shapes(layers.M1).insert(kdb.Box(x0, y0, x1, y1))
```

---

## Migration Plan

### Phase 1: Add APIs (no breakage)

- add `generic_layers`, `bind_generic_layers`, `rules_from_technology`, `remap_layers`.
- keep current `L`, `LayerRef`, and existing generator code working.

### Phase 2: Migrate generators

- migrate `mosfet.py` and `momcap.py` first.
- replace manual loops over `stmt.keyword` with `R.*` lookups.
- rename derived values with `drv_` prefix.

### Phase 3: Simplify PDK files

- enforce one map function + one rule deck builder per PDK.
- remove duplicated per-generator rule extraction logic.

### Phase 4: Cleanup

- deprecate legacy helper paths only after all generators migrate.
- add tests that assert `R` and `layers` expose expected attributes.

---

## Tests To Add

1. `test_rules_namespace_access.py`

- verify `R.M1.width`, `R.M1.spacing.M1`, `R.VIA2.width` resolve.

2. `test_generic_layer_binding.py`

- verify `bind_generic_layers(layout)` returns valid KLayout indices.

3. `test_layer_remap.py`

- create shapes on generic layers, remap to PDK layers, verify occupancy.

4. generator golden tests

- `mosfet`/`momcap` output unchanged (or intentionally changed) after migration.

---

## Expected Final File Responsibilities

- `dsl.py`: typed generic layer catalog + bind helpers + generator decorators.
- `tech.py`: rule-deck authoring + typed rule namespace build + remap engine.
- `serialize.py`: protobuf IO + adapters into typed runtime namespaces.
- `pdk/<name>/layout/pdk_layout.py`: layer-map declaration + rule deck declaration.
