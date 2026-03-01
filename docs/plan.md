# Layout API Refactor Plan

## Task Checklist

### VLSIR proto revert
- [ ] Revert commit `e19027c` in VLSIR repo (`git revert e19027c` on `spectre` branch)
- [ ] Regenerate Python bindings for `vlsir.tech_pb2`

### PDK cleanup (supply rails, model libraries)
- [x] Remove `model_libraries()` from all 4 `pdk_data.py` files (dead code duplicating `Install.include_*()`)
- [x] Move `supply_rails()` data into each PDK's `Install` class as `SUPPLY_RAILS` dict + `supply_voltage()` method
- [x] Update `SupplyVals.corner()` to call `Install.supply_voltage()` directly (uses `@classmethod`, no singleton needed)
- [x] Remove `supply_rails()` and `supply_voltage()` from `pdk/__init__.py`
- [x] Rewrite `pdk/test_supply_rails.py` to test `Install.SUPPLY_RAILS` and `Install.supply_voltage()` directly

### New APIs — `dsl.py`
- [x] Add `GenericLayers` class with all canonical `kdb.LayerInfo` attributes
- [x] Add `load_generic_layers(layout)` function
- [x] ~~Update `METAL_DRAW_TO_GENERIC` and `VTH_TO_GENERIC` to use `GenericLayers` `LayerInfo` values~~ — superseded: generators now use direct `if/else` on params with `G.LVTN` etc. instead of mapping dicts; the `_LAYER`/`_PIN` variants were removed; the old `Layer`-enum-based dicts remain only for `_LayoutNamespace` compat (slated for removal in cleanup phase)

### New APIs — `tech.py`
- [x] Implement new `RuleDeck`, `LayerRules`, `RelativeRules` classes (hierarchical dot-path)
- [x] Add `load_rules_deck(tech_name)` function
- [x] Add `load_dbu(tech_name)` function
- [x] Add `remap_layers(layout, mapping)` function
- [x] Add inline `test_rule_deck()` and `test_remap_layers()` tests

### Standardize PDK layout files
- [x] Rename `ihp130_rule_deck()` → `rule_deck()` (and equivalents in all PDKs)
- [x] Rewrite rule deck bodies to use `R.M1.width = 160` syntax (plain int, nanometers)
- [x] Add module-level `DBU` constant to each `pdk_layout.py` (e.g. `DBU = 0.001` for 1 nm, `DBU = 0.0005` for 0.5 nm)
- [x] Add `layer_map() -> dict[kdb.LayerInfo, kdb.LayerInfo]` to each PDK module
- [x] Keep `layer_infos()` (still used by `write_technology_proto` for `vlsir.tech` layer-info export)

### Simplify `serialize.py`
- [x] Remove `_rule_token_to_proto()`, `_statement_to_proto()`
- [x] Remove all `tech.rules.*` population from `write_technology_proto()`
- [x] Remove `rule_deck` parameter from `write_technology_proto()` (keep `tech_name`, `layer_infos`, `out_dir`)
- [x] Remove imports of `RuleDeck`, `RuleStatementData`, `rule_deck_to_tech_rules` from `tech.py`
- [x] Keep `layout_to_vlsir_raw()`, `export_layout()`, `vlsir_raw_to_disk()`, `read_technology_proto()`

### Migrate generators
- [x] Change `mosfet.py` signature to `mosfet(P: MosfetParams, tech_name: str)`; load `R` and `dbu` inside via `load_rules_deck` / `load_dbu`; replace all `RuleStatement` token parsing with `R.*` access; remove `import vlsir.tech_pb2`
- [x] Change `momcap.py` signature similarly
- [x] Update `test_mosfet` / `test_momcap` to load `rule_deck()` directly from PDK module

### Cleanup old code
- [x] Remove old `Layer` enum, `Purpose` enum, `LayerRef`, `METAL_DRAW_TO_GENERIC`, `VTH_TO_GENERIC`, `generic_name`, `param_to_generic` from `dsl.py` — done; `_LayoutNamespace` and `L` kept but slimmed to only `Param`, `paramclass`, `generator`, `MosType`, `MosVth`, `SourceTie`, `MetalDraw`
- [x] Remove old `SpacingRule`, `EnclosureRule`, `AreaRule`, `WidthRule`, chained `LayerRules` builder from `tech.py`
- [x] Remove `RuleStatementData`, `LayerRuleSetData`, `LayerPairRuleSetData`, `rule_deck_to_tech_rules()` from `tech.py`
- [x] Remove `map_generic_to_tech_layers()`, `STACK_ORDER` from `tech.py`
- [x] Remove old `tech_layer_map()` from PDK files (replaced by `layer_map()`)

---

## Goal

Make generator code read like this:

```python
R = load_rules_deck(tech_name)
layout = kdb.Layout()
layout.dbu = load_dbu(tech_name)
L = load_generic_layers(layout)

rail_w = P.powerrail_mult * R.M1.width
track_pitch = R.M1.width + R.M1.spacing.M1

top.shapes(L.M1).insert(kdb.Box(x0, y_vss0, x1, y_vss1))
top.shapes(L.PIN1).insert(kdb.Box(x0, y_vss0, x0 + rail_w, y_vss1))
```

Key outcomes:

- `L` holds `kdb.LayerInfo` objects for all generic layers. Returned by `load_generic_layers(layout)`, which also registers the layers in the layout. Usable directly in `cell.shapes(L.M1)`.
- `R` holds PDK rules in a readable, hierarchical namespace (`R.M1.width`, `R.M1.spacing.M1`, `R.CO.enclosure.OD`). Loaded directly from `pdk_layout.py` — no proto round-trip.
- `P` is the conventional name for the params object (`P.powerrail_mult`, `P.fing_count`).
- Any bare local variable (e.g. `rail_w`, `gate_len`, `sd_pitch`) is implicitly a derived value. No prefix needed.

---

## Three Main Concepts

1. **Generic layers** (`L.*`): process-agnostic `kdb.LayerInfo` objects used by generators to draw shapes. `load_generic_layers(layout)` registers them in a layout and returns a namespace for dot-access.
2. **Rule deck** (`R.*`): hierarchical typed object for PDK design rules. Supports `R.M1.width`, `R.M1.spacing.M2`, `R.CO.enclosure.OD`. Used for both authoring (in PDK scripts) and reading (in generators).
3. **Layer remap map**: dictionary from generic `kdb.LayerInfo` to PDK-specific `kdb.LayerInfo`. Applied after generation to convert generic layers to concrete tech layers.

---

## `flow/layout/dsl.py`

### Keep

- `Param`, `paramclass`, `generator` decorators.
- `MosType`, `MosVth`, `SourceTie`, `MetalDraw` parameter enums.
- `METAL_DRAW_TO_GENERIC`, `VTH_TO_GENERIC` mappings (updated to use `LayerInfo` values). `VTH_TO_GENERIC` maps `(MosVth, MosType)` pairs to the correct generic layer (e.g. `LVTN`, `HVTP`).

### Replace

The `Layer` enum, `Purpose` enum, `LayerRef`, `_LayoutNamespace`, and module-level `L` singleton are all replaced by `GenericLayers` and `load_generic_layers()`.

### Add: `GenericLayers` and `load_generic_layers`

```python
import klayout.db as kdb

class GenericLayers:
    """Namespace of kdb.LayerInfo objects for all generic process layers.

    Each attribute (e.g. .M1, .PIN1, .OD) is a kdb.LayerInfo with a
    canonical name and default layer/datatype numbers.  These can be
    passed directly to cell.shapes(L.M1).insert(...).
    """
    # Draw layers — (layer_number, datatype, name)
    OD   = kdb.LayerInfo(1, 0, "OD")
    PO   = kdb.LayerInfo(2, 0, "PO")
    CO   = kdb.LayerInfo(3, 0, "CO")
    NP   = kdb.LayerInfo(4, 0, "NP")
    PP   = kdb.LayerInfo(5, 0, "PP")
    NW   = kdb.LayerInfo(6, 0, "NW")
    DNW  = kdb.LayerInfo(6, 1, "DNW")

    # Threshold voltage layers — datatype 0 = N, datatype 1 = P
    LVTN = kdb.LayerInfo(7, 0, "LVTN")
    LVTP = kdb.LayerInfo(7, 1, "LVTP")
    HVTN = kdb.LayerInfo(8, 0, "HVTN")
    HVTP = kdb.LayerInfo(8, 1, "HVTP")

    # Metal stack starts at layer 10
    M1   = kdb.LayerInfo(10, 0, "M1")
    VIA1 = kdb.LayerInfo(11, 0, "VIA1")
    M2   = kdb.LayerInfo(12, 0, "M2")
    VIA2 = kdb.LayerInfo(13, 0, "VIA2")
    M3   = kdb.LayerInfo(14, 0, "M3")
    VIA3 = kdb.LayerInfo(15, 0, "VIA3")
    M4   = kdb.LayerInfo(16, 0, "M4")
    VIA4 = kdb.LayerInfo(17, 0, "VIA4")
    M5   = kdb.LayerInfo(18, 0, "M5")
    VIA5 = kdb.LayerInfo(19, 0, "VIA5")
    M6   = kdb.LayerInfo(20, 0, "M6")
    VIA6 = kdb.LayerInfo(21, 0, "VIA6")
    M7   = kdb.LayerInfo(22, 0, "M7")
    VIA7 = kdb.LayerInfo(23, 0, "VIA7")
    M8   = kdb.LayerInfo(24, 0, "M8")
    VIA8 = kdb.LayerInfo(25, 0, "VIA8")
    M9   = kdb.LayerInfo(26, 0, "M9")
    VIA9 = kdb.LayerInfo(27, 0, "VIA9")
    M10  = kdb.LayerInfo(28, 0, "M10")

    # Pin layers
    PIN1 = kdb.LayerInfo(10, 1, "PIN1")
    PIN2 = kdb.LayerInfo(12, 1, "PIN2")
    PIN3 = kdb.LayerInfo(14, 1, "PIN3")
    PIN4 = kdb.LayerInfo(16, 1, "PIN4")
    PIN5 = kdb.LayerInfo(18, 1, "PIN5")
    PIN6 = kdb.LayerInfo(20, 1, "PIN6")
    PIN7 = kdb.LayerInfo(22, 1, "PIN7")
    PIN8 = kdb.LayerInfo(24, 1, "PIN8")
    PIN9 = kdb.LayerInfo(26, 1, "PIN9")

    # Special layers
    TEXT         = kdb.LayerInfo(60, 0, "TEXT")
    PR_BOUNDARY  = kdb.LayerInfo(61, 0, "PR_BOUNDARY")


def load_generic_layers(layout: kdb.Layout) -> GenericLayers:
    """Register all generic layers in `layout` and return the namespace.

    Calls layout.layer(info) for every LayerInfo on GenericLayers.
    This ensures the layers exist in the layout's layer table.
    Returns the GenericLayers class itself (not an instance) so that
    L.M1, L.PIN2 etc. resolve to kdb.LayerInfo objects usable in
    cell.shapes(L.M1).insert(...).
    """
    layers = GenericLayers()
    for name in dir(layers):
        val = getattr(layers, name)
        if isinstance(val, kdb.LayerInfo):
            layout.layer(val)          # register in layout
    return layers
```

This works because `cell.shapes()` accepts a `kdb.LayerInfo` directly (KLayout ≥ 0.29.7). The `load_generic_layers(layout)` call both registers the layers and returns the namespace, so generators only need one call.

### Usage in generators

```python
L = load_generic_layers(layout)
top.shapes(L.M1).insert(kdb.Box(x0, y0, x1, y1))
top.shapes(L.PIN1).insert(kdb.Box(x0, y0, x0 + pin_w, y1))
```

### Usage in PDK scripts

PDK scripts import `GenericLayers` to reference canonical layer names when building the layer remap map:

```python
from flow.layout.dsl import GenericLayers
L = GenericLayers()

def layer_map() -> dict[kdb.LayerInfo, kdb.LayerInfo]:
    return {
        L.OD:   kdb.LayerInfo(1, 0, "ACTIVE"),
        L.M1:   kdb.LayerInfo(7, 0, "METAL1"),
        L.PIN1: kdb.LayerInfo(7, 1, "M1.PIN"),
        # ...
    }
```

---

## `flow/layout/tech.py`

### Rewrite: `RuleDeck` as a hierarchical read/write namespace

The old `RuleDeck` stored rules as flat lists (`deck.spacing`, `deck.width`, etc.) and required a `LayerRules` builder with chained methods. The new `RuleDeck` uses a hierarchical structure so the **same dot-path syntax** works for both authoring and reading:

```
R.M1.width          → int (nanometers, matching layout units = NANO)
R.M1.spacing.M1     → int
R.M1.spacing.M2     → int
R.M1.enclosure.CO   → int
R.CO.enclosure.OD   → int
R.M1.area           → int
```

#### Rule type hierarchy

There are five rule types. `width` and `area` are **single-value** (no relative layer). `spacing`, `enclosure`, and `overlap` are **relative** (indexed by a second layer name):

| Rule type   | Access pattern           | Has relative layer? |
|-------------|--------------------------|---------------------|
| `width`     | `R.M1.width`             | No                  |
| `area`      | `R.M1.area`              | No                  |
| `spacing`   | `R.M1.spacing.M2`        | Yes                 |
| `enclosure` | `R.M1.enclosure.CO`      | Yes                 |
| `overlap`   | `R.M1.overlap.VIA1`      | Yes                 |

#### Implementation

```python
class RelativeRules:
    """Per-relative-layer rule storage. Supports R.M1.spacing.M2 syntax.

    Values are plain integers in the layout's units (NANO by convention).
    """

    def __setattr__(self, name: str, value):
        object.__setattr__(self, name, value)

    def __getattr__(self, name: str):
        raise AttributeError(
            f"No rule defined for target layer '{name}'"
        )


class LayerRules:
    """Rules for a single layer. Supports both read and write.

    Write (PDK authoring):
        R.M1.width = 160
        R.M1.spacing.M1 = 180
        R.M1.enclosure.CO = 60

    Read (generator):
        rail_w = R.M1.width
        gap = R.M1.spacing.M1

    All values are plain integers in layout units (NANO).
    """

    def __init__(self):
        self.width: int | None = None
        self.area: int | None = None
        self.spacing: RelativeRules = RelativeRules()
        self.enclosure: RelativeRules = RelativeRules()
        self.overlap: RelativeRules = RelativeRules()


class RuleDeck:
    """Hierarchical layout rule deck.

    Supports dot-path access for both authoring and reading:

        deck = RuleDeck()
        deck.M1.width = 160
        deck.M1.spacing.M1 = 180
        deck.CO.enclosure.OD = 70

    All values are plain integers in layout units.  By convention,
    generators set units = NANO (matching vlsir.raw.Units), so values
    are nanometers and can be passed directly to Box() calls.
    """

    def __init__(self):
        self._layers: dict[str, LayerRules] = {}

    def __getattr__(self, name: str) -> LayerRules:
        if name.startswith("_"):
            raise AttributeError(name)
        if name not in self._layers:
            self._layers[name] = LayerRules()
        return self._layers[name]
```

#### PDK authoring example (`pdk/ihp130/layout/pdk_layout.py`)

```python
from flow.layout.tech import RuleDeck

def rule_deck() -> RuleDeck:
    R = RuleDeck()

    R.OD.width       = 150
    R.OD.spacing.OD  = 180

    R.PO.width       = 130
    R.PO.spacing.PO  = 180

    R.CO.width       = 160
    R.CO.spacing.CO  = 180
    R.CO.spacing.PO  = 110
    R.CO.enclosure.OD = 70
    R.CO.enclosure.PO = 70

    R.M1.width       = 160
    R.M1.spacing.M1  = 180
    R.M1.area        = 50_000   # square area
    R.M1.enclosure.CO = 60

    R.NP.enclosure.OD  = 180
    R.PP.enclosure.OD  = 180
    R.NW.enclosure.OD  = 310

    R.VIA1.width      = 220
    R.VIA1.spacing.VIA1 = 220

    R.M2.width       = 200
    R.M2.spacing.M2  = 220
    R.M2.area        = 60_000   # square area
    # ... etc
    return R
```

### Add: `load_rules_deck`

```python
from importlib import import_module


def load_rules_deck(tech_name: str) -> RuleDeck:
    """Load a PDK's rule deck by name.

    Imports pdk.<tech_name>.layout.pdk_layout.rule_deck() and returns
    the RuleDeck directly.  All values are already plain integers in
    layout units (NANO), so no conversion is needed.

    After loading:
        R = load_rules_deck("ihp130")
        R.M1.width       # → 160  (int, nanometers)
        R.M1.spacing.M1  # → 180
    """
    module = import_module(f"pdk.{tech_name}.layout.pdk_layout")
    return module.rule_deck()


def load_dbu(tech_name: str) -> float:
    """Load a PDK's database-unit size (microns per dbu).

    Imports pdk.<tech_name>.layout.pdk_layout.DBU and returns
    the float directly.

    After loading:
        layout.dbu = load_dbu("ihp130")   # 0.001 → 1 nm per dbu
    """
    module = import_module(f"pdk.{tech_name}.layout.pdk_layout")
    return module.DBU
```

The `tech_name` string comes from whatever technology context the generator is invoked with. Every PDK module exports `rule_deck()` with that exact function name.

### Keep: `remap_layers`

```python
LayerInfoMap = dict[kdb.LayerInfo, kdb.LayerInfo]

def remap_layers(
    layout: kdb.Layout,
    mapping: LayerInfoMap,
    *,
    delete_source: bool = True,
) -> None:
    """Move shapes from generic layers to PDK-specific layers.

    For each (generic_info -> pdk_info) pair in `mapping`:
    - find or create the source and destination layers,
    - copy all shapes from source to destination,
    - optionally delete the source layer.
    """
    for generic_info, pdk_info in mapping.items():
        src_idx = layout.find_layer(generic_info)
        if src_idx is None or src_idx < 0:
            continue
        dst_idx = layout.layer(pdk_info)
        for cell in layout.each_cell():
            src_shapes = cell.shapes(src_idx)
            if src_shapes.is_empty():
                continue
            for shape in src_shapes.each():
                cell.shapes(dst_idx).insert(shape)
            src_shapes.clear()
```

### Remove

- Old `SpacingRule`, `EnclosureRule`, `AreaRule`, `WidthRule` frozen dataclasses.
- Old `LayerRules` chained-method builder class.
- `rule_deck_to_tech_rules()` and `RuleStatementData` / `LayerRuleSetData` / `LayerPairRuleSetData` (protobuf conversion from flat lists).
- `map_generic_to_tech_layers()` (replaced by `remap_layers` operating on `LayerInfo` keys).
- `STACK_ORDER` dict (validation logic will move into `RuleDeck` if needed later).

---

## `flow/layout/serialize.py`

### Keep

- `layout_to_vlsir_raw()`, `vlsir_raw_to_disk()`, `export_layout()` — `vlsir.raw` layout geometry export.
- `write_technology_proto(tech_name, layer_infos, out_dir)` — `vlsir.tech` layer-info export (simplified, see below).
- `read_technology_proto(path)` — reads `vlsir.tech.Technology` back from `.pb`/`.pbtxt`.
- `ExportArtifacts`, `TechArtifacts` dataclasses.

### Remove

- `_rule_token_to_proto()`, `_statement_to_proto()` — rule-deck proto serialization helpers.
- All `tech.rules.*` population in `write_technology_proto()`.
- `rule_deck` parameter from `write_technology_proto()` signature.
- Imports of `RuleDeck`, `RuleStatementData`, `rule_deck_to_tech_rules` from `tech.py`.

After cleanup, `write_technology_proto` only populates `Technology(name=..., layers=[LayerInfo(...)])` using the upstream proto messages that survive the VLSIR revert.

---

## `pdk/<name>/layout/pdk_layout.py`

Each PDK file exports exactly two things:

1. `rule_deck() -> RuleDeck` — the design rules, authored with hierarchical dot-path syntax.
2. `layer_map() -> dict[kdb.LayerInfo, kdb.LayerInfo]` — generic-to-tech layer mapping.

### Example: `pdk/ihp130/layout/pdk_layout.py`

```python
import klayout.db as kdb

import klayout.db as kdb

from flow.layout.dsl import GenericLayers
from flow.layout.tech import RuleDeck

PDK_NAME = "ihp130"
DBU = 0.001   # 1 dbu = 1 nm (1000 database units per micron)
L = GenericLayers()


def layer_map() -> dict[kdb.LayerInfo, kdb.LayerInfo]:
    return {
        L.OD:    kdb.LayerInfo(1, 0, "ACTIVE"),
        L.PO:    kdb.LayerInfo(2, 0, "POLY"),
        L.CO:    kdb.LayerInfo(3, 0, "CONT"),
        L.NP:    kdb.LayerInfo(4, 0, "NSD"),
        L.PP:    kdb.LayerInfo(5, 0, "PSD"),
        L.NW:    kdb.LayerInfo(6, 0, "NWELL"),
        L.M1:    kdb.LayerInfo(7, 0, "METAL1"),
        L.PIN1:  kdb.LayerInfo(7, 1, "M1.PIN"),
        L.VIA1:  kdb.LayerInfo(8, 0, "VIA1"),
        L.M2:    kdb.LayerInfo(9, 0, "METAL2"),
        L.PIN2:  kdb.LayerInfo(9, 1, "M2.PIN"),
        L.VIA2:  kdb.LayerInfo(10, 0, "VIA2"),
        L.M3:    kdb.LayerInfo(11, 0, "METAL3"),
        L.PIN3:  kdb.LayerInfo(11, 1, "M3.PIN"),
        # ... through M7 for IHP130
        L.LVTN:         kdb.LayerInfo(70, 0, "LVTN"),
        L.LVTP:         kdb.LayerInfo(70, 1, "LVTP"),
        L.HVTN:         kdb.LayerInfo(71, 0, "HVTN"),
        L.HVTP:         kdb.LayerInfo(71, 1, "HVTP"),
        L.TEXT:         kdb.LayerInfo(63, 0, "TEXT"),
        L.PR_BOUNDARY:  kdb.LayerInfo(189, 0, "PR_BOUNDARY"),
    }


def rule_deck() -> RuleDeck:
    R = RuleDeck()

    R.OD.width          = 150
    R.OD.spacing.OD     = 180

    R.PO.width          = 130
    R.PO.spacing.PO     = 180

    R.CO.width          = 160
    R.CO.spacing.CO     = 180
    R.CO.spacing.PO     = 110
    R.CO.enclosure.OD   = 70
    R.CO.enclosure.PO   = 70

    R.M1.width          = 160
    R.M1.spacing.M1     = 180
    R.M1.area           = 50_000
    R.M1.enclosure.CO   = 60

    R.NP.enclosure.OD   = 180
    R.PP.enclosure.OD   = 180
    R.NW.enclosure.OD   = 310

    R.VIA1.width        = 220
    R.VIA1.spacing.VIA1 = 220

    R.M2.width          = 200
    R.M2.spacing.M2     = 220
    R.M2.area           = 60_000

    R.VIA2.width        = 190
    R.VIA2.spacing.VIA2 = 220

    R.M3.width          = 200
    R.M3.spacing.M3     = 220
    R.M3.area           = 60_000

    R.VIA3.width        = 190
    R.VIA3.spacing.VIA3 = 220

    R.M4.width          = 200
    R.M4.spacing.M4     = 220
    R.M4.area           = 70_000

    R.VIA4.width        = 190
    R.VIA4.spacing.VIA4 = 220

    R.M5.width          = 200
    R.M5.spacing.M5     = 220
    R.M5.area           = 80_000

    R.VIA5.width        = 420
    R.VIA5.spacing.VIA5 = 420

    R.M6.width          = 1640
    R.M6.spacing.M6     = 1640
    R.M6.area           = 1_000_000

    R.VIA6.width        = 900
    R.VIA6.spacing.VIA6 = 1060

    R.M7.width          = 2000
    R.M7.spacing.M7     = 2000
    R.M7.area           = 2_000_000

    return R
```

### Standardized names

All PDK modules export the **same names**: `rule_deck()`, `layer_map()`, and `DBU`. This allows `load_rules_deck(tech_name)` and `load_dbu(tech_name)` to import any PDK dynamically without knowing PDK-specific details.

---

## Generator Coding Conventions After Refactor

### Setup (top of every generator)

The generator receives a `tech_name` string identifying the target PDK. It loads the rule deck and dbu separately, creates the layout, and loads generic layers:

```python
R = load_rules_deck(tech_name)
layout = kdb.Layout()
layout.dbu = load_dbu(tech_name)
L = load_generic_layers(layout)
```

### Naming conventions

- `R.*` = PDK rules (read-only after load).
- `P.*` = generator parameters.
- `L.*` = generic layer references.
- Bare local variables = derived geometry values.

### Example generator body

```python
@generator
def mosfet(P: MosfetParams, tech_name: str) -> kdb.Layout:
    R = load_rules_deck(tech_name)
    layout = kdb.Layout()
    layout.dbu = load_dbu(tech_name)
    top = layout.create_cell("MOSFET")

    L = load_generic_layers(layout)

    rail_w = P.powerrail_mult * R.M1.width
    track_pitch = R.M1.width + R.M1.spacing.M1
    gate_len = max(R.PO.width, P.lf_mult * R.PO.width)
    sd_pitch = R.CO.width + 2 * R.CO.spacing.PO + gate_len

    top.shapes(L.M1).insert(kdb.Box(x0, y_vss0, x1, y_vss1))
    top.shapes(L.PIN1).insert(kdb.Box(x0, y_vss0, x0 + rail_w, y_vss1))
    top.shapes(L.OD).insert(kdb.Box(x_act0, y0, x_act1, y1))

    return layout
```

This eliminates all manual `stmt.keyword` parsing and protobuf token extraction boilerplate that currently fills up `mosfet.py` and `momcap.py`.

---

## Migration Plan

### Phase 1: Implement new APIs (no breakage)

- Add `GenericLayers` class and `load_generic_layers()` to `dsl.py`.
- Rewrite `RuleDeck`, `LayerRules`, `RelativeRules` in `tech.py` with hierarchical dot-path structure.
- Add `load_rules_deck()` to `tech.py`.
- Add `remap_layers()` to `tech.py`.
- Keep all old types and functions in place so existing code still works.

### Phase 2: Standardize PDK files

- Rename `ihp130_rule_deck()` → `rule_deck()` in all PDK modules.
- Rewrite rule deck bodies to use `R.M1.width = 160` syntax (plain int, nanometers) instead of chained `deck.layer(L.M1).min_width(rule=...)`.
- Add `layer_map()` returning `dict[kdb.LayerInfo, kdb.LayerInfo]` to each PDK module.
- Keep old `layer_infos()` (still used by `write_technology_proto` for layer-info export) and `tech_layer_map()` temporarily for backward compat.

### Phase 3: Migrate generators

- Migrate `mosfet.py` and `momcap.py` to use `load_generic_layers()` and `load_rules_deck()`.
- Replace all manual `stmt.keyword` / token parsing with `R.*` dot-path access.
- Replace `layout.layer(kdb.LayerInfo(L.generic_name(...)))` calls with `L = load_generic_layers(layout)`.
- Use `remap_layers()` instead of `map_generic_to_tech_layers()`.
- Change generator signatures from `mosfet(params, tech: vtech.Technology)` to `mosfet(P: MosfetParams, tech_name: str)`. Load `R` and `dbu` inside via `load_rules_deck` / `load_dbu`. Remove `import vlsir.tech_pb2` from generators.

### Phase 4: Cleanup

- Remove old `Layer` enum, `Purpose` enum, `LayerRef`, `_LayoutNamespace`, module-level `L`.
- Remove `SpacingRule`, `EnclosureRule`, `AreaRule`, `WidthRule` dataclasses.
- Remove `rule_deck_to_tech_rules()`, `RuleStatementData`, `LayerRuleSetData`, `LayerPairRuleSetData`.
- Remove `map_generic_to_tech_layers()`, `STACK_ORDER`.
- Remove old `tech_layer_map()` from PDK files (replaced by `layer_map()`).
- Keep `layer_infos()` in PDK files (still used by `write_technology_proto` for `vlsir.tech` layer-info export).

---

## Tests To Add

1. **`test_rule_deck()` in `tech.py`** — inline test that builds a small `RuleDeck` with dummy values, verifies `R.M1.width`, `R.M1.spacing.M1`, `R.CO.enclosure.OD` resolve correctly.

2. **`test_remap_layers()` in `tech.py`** — inline test that creates shapes on generic layers, calls `remap_layers()` with a dummy PDK mapping, verifies shapes moved to destination layers.

---

## Expected Final File Responsibilities

| File | Responsibility |
|------|---------------|
| `dsl.py` | `GenericLayers`, `load_generic_layers()`, `Param`, `paramclass`, `generator`, parameter enums |
| `tech.py` | `RuleDeck`, `LayerRules`, `RelativeRules`, `load_rules_deck()`, `remap_layers()` |
| `serialize.py` | `vlsir.raw` layout export (`layout_to_vlsir_raw`, `export_layout`), `vlsir.tech` layer-info export (`write_technology_proto`, `read_technology_proto`) |
| `pdk/<name>/layout/pdk_layout.py` | `rule_deck()`, `layer_map()` |

---


## VLSIR `tech.proto` — Revert and Bypass

### Problem with the current approach

Our commit `e19027c` expanded `tech.proto` with a large LEF-style schema
(`RuleDeck`, `VoltageRail`, `ModelLibrary`, routing/cut/via structures, etc.).
In practice none of this is needed right now:

- **Layout generators** (`mosfet.py`, `momcap.py`) currently accept a
  `vtech.Technology` proto object, but the only reason it exists is an
  unnecessary round-trip: Python dicts → `write_technology_proto()` →
  `.tech.pb` file → `read_technology_proto()` → proto object → painful
  `RuleStatement` token parsing inside the generator. The data originates in
  `pdk_layout.py` and can be consumed directly as typed Python objects.

- **Supply rails** (`pdk_data.supply_rails()`) and **model libraries**
  (`pdk_data.model_libraries()`) are consumed via a Python-only path
  (`pdk/__init__.py` → `SupplyVals.corner()` → testbench `Vdc`/`Vpulse`).
  The matching proto messages (`VoltageRail`, `ModelLibrary`, `CornerSection`)
  are never serialized or deserialized — they are dead code in the proto.

- **`vlsir.raw`** (layout geometry export) is still valuable and untouched by
  this change.

### Action: revert commit `e19027c` in VLSIR

Revert `tech.proto` back to the upstream state (commit `d9b5def`), which
contains only:

```proto
message Technology {
  string name = 1;
  repeated Package packages = 11;
  repeated LayerInfo layers = 101;
}
```

Plus the unchanged `Package`, `LayerPurposeType`, `LayerPurpose`, and
`LayerInfo` messages. Everything added by `e19027c` is removed:

- `RuleDeck` and all sub-messages (`LayerRuleSet`, `LayerPairRuleSet`,
  `RuleStatement`, `RuleToken`, `LefUnits`, `UnitScale`, etc.)
- `VoltageRail`, `ModelLibrary`, `CornerSection`
- `PropertyDefinition`, `PropertyAssignment`
- All LEF-centric enums and structures (`LayerFamily`, `RoutingDirection`,
  `SpacingValue`, `RoutingRules`, `CutRules`, `AntennaRules`,
  `ViaDefinition`, `ViaRuleDefinition`, `EnclosureRule`, etc.)

Regenerate Python bindings after the revert.

> **Future:** If we later want a serialized technology exchange format (e.g. for
> tool interop or caching), we can re-introduce a minimal `tech.proto` schema
> at that point. For now the Python-only path is simpler and sufficient.

### Action: remove rule-deck proto round-trip from generators

**Current flow (remove):**
```
pdk_layout.py → write_technology_proto() → .tech.pb → read_technology_proto()
             → vtech.Technology proto → generator parses RuleStatement tokens
```

**New flow:**
```
pdk_layout.py  →  rule_deck()   →  RuleDeck (typed Python)  →  generator reads R.M1.width
               →  layer_map()   →  dict[LayerInfo, LayerInfo] →  remap_layers()
```

Generators receive the `RuleDeck` and `dbu` directly from Python — no proto
serialization, no token parsing.

### `serialize.py` after cleanup

Two serialization responsibilities remain:

1. **`vlsir.raw` — layout geometry export** (unchanged).
   `layout_to_vlsir_raw()`, `vlsir_raw_to_disk()`, `export_layout()`.
   Converts a KLayout `Layout` (after PDK layer remapping) into
   `vlsir.raw_pb2.Library` for downstream consumption.

2. **`vlsir.tech` — layer-info export** (simplified).
   `write_technology_proto()` and `read_technology_proto()` stay, but are
   reduced to only populating the upstream `Technology.layers` field with
   `LayerInfo` entries (name, index, sub_index, purpose). All rule-deck
   serialization (`RuleDeck`, `RuleStatement`, `RuleToken`, `LefUnits`,
   `_rule_token_to_proto`, `_statement_to_proto`, `rule_deck_to_tech_rules`)
   is removed — those proto messages no longer exist after the revert.

What is removed from `serialize.py`:
- `_rule_token_to_proto()`, `_statement_to_proto()`
- All `tech.rules.*` population in `write_technology_proto()`
- Imports of `RuleDeck`, `RuleStatementData`, `rule_deck_to_tech_rules` from `tech.py`
- The `rule_deck` parameter from `write_technology_proto()`

What stays:
- `write_technology_proto(tech_name, layer_infos, out_dir)` — writes
  `Technology(name=..., layers=[LayerInfo(...), ...])` to `.tech.pb` / `.pbtxt`
- `read_technology_proto(path)` — reads it back
- `ExportArtifacts`, `TechArtifacts` dataclasses
- All `vlsir.raw` functions

### Other code changes

| File | Change |
|------|--------|
| `mosfet.py` | Change signature from `mosfet(params, tech: vtech.Technology)` to `mosfet(P: MosfetParams, tech_name: str)`. Load `R` via `load_rules_deck`, `dbu` via `load_dbu`. Replace all `RuleStatement` token parsing with `R.M1.width`, `R.M1.spacing`, etc. Remove `import vlsir.tech_pb2`. |
| `momcap.py` | Same treatment as `mosfet.py`. |
| `tech.py` | Remove old `RuleDeck` dataclass (flat, for proto serialization), `RuleStatementData`, `LayerRuleSetData`, `LayerPairRuleSetData`, `rule_deck_to_tech_rules()`. Keep `LayerInfoData` (still needed by `write_technology_proto` and `layer_map`). These are replaced by the new typed `RuleDeck`/`LayerRules`/`RelativeRules` classes. |
| `pdk_layout.py` (all PDKs) | Keep `layer_infos()` (still used by `write_technology_proto`). Keep `rule_deck()` and `layer_map()`. |
| `test_mosfet`, `test_momcap` | Keep `write_technology_proto` for layer-info export, but remove proto as input to generator. Load `rule_deck()` directly from the PDK module and pass to generator. |
| VLSIR repo | `git revert e19027c`, regenerate bindings. |

### Supply rails and model libraries

#### How `compile` and the walker relate

`h.pdk.compile(src)` is the top-level hdl21 API. It delegates to the active
PDK module's `compile()` function, which instantiates the PDK's
`HierarchyWalker` subclass (e.g. `IhpWalker`) and calls `.walk(src)`.
The walker traverses the hdl21 module tree and replaces generic `h.Primitive`
instances (`Mos`, `PhysicalResistor`, …) with PDK-specific `ExternalModule`s
(e.g. `sg13_lv_nmos`), applying device scaling along the way. So `compile`
*is* the walker — `compile` is just the entry point that creates and runs it.

Each PDK also has an `Install(PdkInstallation)` dataclass in `pdk_logic.py`
that holds site-specific paths and provides `include_*(corner)` methods
returning `h.sim.Lib(path=..., section=...)` for model library includes.
This is the idiomatic hdl21 home for PDK installation metadata.

#### `model_libraries()` — dead duplicate, remove

`model_libraries()` in `pdk_data.py` is dead code (never called by anything)
that redundantly declares the same paths and corner→section mappings already
provided by `Install.include_*(corner)` in `pdk_logic.py`. For example,
IHP's `model_libraries()` declares `cornerMOSlv.lib` with `TYP→tt`,
`FAST→ff`, `SLOW→ss` — exactly what `Install.include_mos_lv(corner)` returns.
These functions were added by us on top of the upstream hdl21 PDK wrappers
and serve no purpose. Remove `model_libraries()` from all 4 PDKs.

#### `supply_rails()` — works but misplaced

`supply_rails()` in `pdk_data.py` *is* actively used:

```
pdk_data.supply_rails()  →  pdk/__init__.py::supply_voltage()  →  SupplyVals.corner()
                          →  testbenches: Vdc(dc=supply.VDD), Vpulse(v2=supply.VDD)
```

It provides nominal/min/max VDD per voltage corner for testbench stimulus.
However, like `model_libraries()`, it was bolted onto `pdk_data.py` outside
the hdl21 PDK infrastructure. The `Install` class is the natural home: it
already holds site-specific PDK metadata and corner-aware methods.

**Action:** Move supply-rail data into each PDK's `Install` class, e.g.:

```python
class Install(PdkInstallation):
    ...
    SUPPLY_RAILS = {
        "VDD":  {"nominal": 1.2, "min": 1.08, "max": 1.32},
        "VDDIO": {"nominal": 3.3, "min": 3.0,  "max": 3.6},
        "VSS":  {"nominal": 0.0, "min": 0.0,  "max": 0.0},
    }

    def supply_voltage(self, rail: str, corner: Corner) -> float:
        r = self.SUPPLY_RAILS[rail.upper()]
        return {Corner.SLOW: r["min"], Corner.TYP: r["nominal"], Corner.FAST: r["max"]}[corner]
```

Then update `SupplyVals.corner()` to call `Install.instance().supply_voltage()`
instead of the free-standing `pdk/__init__.py::supply_voltage()` function.
Remove `supply_rails()` from all 4 `pdk_data.py` files, the `supply_rails()`
and `supply_voltage()` helpers from `pdk/__init__.py`, and
`pdk/test_supply_rails.py` (replace with a test against `Install`).
