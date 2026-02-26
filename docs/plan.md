# Layout Plan v2: Minimal Runtime + Monolithic Generators

This plan replaces the current over-split layout stack with a minimal, generator-focused implementation.

Primary goals:
- keep only what is needed for `mosfet` and `momcap` generation,
- keep generator files readable and mostly monolithic (target `200-300` lines each),
- keep generic layer names (`L.M1`, etc.) in generator code,
- generate KLayout geometry on name-only layers (for example `"M1.draw"`, `"M1.pin"`) with no numeric layer ids in generator logic,
- remap those named layers in-place to tech-layer `(layer, datatype)` right before raw export,
- minimize tests to: VLSIR interface checks + mosfet/momcap sweep tests.


## 1) End-State Architecture

### Keep
- `flow/layout/dsl.py` for `Param`, `@paramclass`, `@generator` ergonomics.
- `flow/layout/layers.py` for generic layer enum + minimal mapping helpers.
- `flow/layout/klayout.py` for small KLayout helpers.
- `flow/layout/serialize.py` for KLayout -> VLSIR raw conversion and write-to-disk.
- `flow/layout/tech.py` (trimmed) for reading tech proto and extracting only rules used by generators.
- a tiny remap utility that migrates shapes from name-only generic layers to numeric tech layers in-place.
- `flow/layout/mosfet.py` new unified NMOS/PMOS + dummy-opposite generator.
- `flow/layout/momcap.py` monolithic MOMCAP generator.
- tech-layer metadata modules under `pdk/*/layout/pdk_layout.py` (trimmed to needed metadata).

### Remove / reduce
- heavy test fanout in `flow/layout` and `pdk/*/layout`.
- helper explosions in generator modules.
- duplicated conversion APIs that do the same work with different names.


## 2) Parameter DSL (already started)

We use one local layout namespace API `L` for layers and generator/ param decorators.

In this plan, `L` is the single surface for:
- layer ids (`L.M1`, `L.VIA1`, ...),
- parameter fields (`L.Param(...)`),
- decorators (`@L.paramclass`, `@L.generator`).

```python
from flow.layout import L


@L.paramclass
class MosfetParams:
    fing_count = L.Param(dtype=int, desc="Number of fingers", default=4)
    wf_mult = L.Param(dtype=int, desc="Finger width in min-width multiples", default=1)
    lf_mult = L.Param(dtype=int, desc="Gate length in min-length multiples", default=1)
```

Generator annotation pattern:

```python
@L.generator
def mosfet(params: MosfetParams, tech_rules: "TechRules") -> "kdb.Layout":
    ...
```

The decorator behavior stays intentionally lightweight:
- dataclass conversion,
- runtime type/validator checks,
- generator first-arg type check.


## 3) M1 Rail Width + Track Model

### Required new parameter
Add an explicit parameter for M1 power rail width control with default tied to min M1 width:

```python
@L.paramclass
class MosfetParams:
    # New:
    m1_power_bar_width_mult = L.Param(
        dtype=float,
        desc="M1 power-bar width multiplier of M1 minimum width",
        default=2.0,
    )
```

Default behavior:

```python
rail_width_um = params.m1_power_bar_width_mult * tech.m1_min_width_um
```

### Track / row handling
Design decision:
- routing minimum width/spacing and enclosure rules come from the typed rule deck,
- rail width default is parameterized (`m1_power_bar_width_mult = 2.0`),
- any row-height/ pitch convention that is not available in rules is kept as explicit generator parameter input rather than a hardcoded per-PDK table in this plan.


## 4) Typed Runtime Rules Model (minimal)

Use one compact runtime structure consumed by both generators:

```python
from dataclasses import dataclass
from flow.layout import L
from flow.layout.rules import RuleDeck


@dataclass(frozen=True)
class MetalRule:
    min_width_um: float
    min_spacing_um: float
    pitch_um: float | None
    offset_um: float | None


@dataclass(frozen=True)
class TechRules:
    tech_name: str
    dbu_um: float
    m1: MetalRule
    m2: MetalRule
    m3: MetalRule
    # typed deck queried by generic layer ids (L.OD, L.PO, L.CO, ...)
    deck: RuleDeck
```

Extraction entrypoint:

```python
def rules_from_technology(tech: vtech.Technology, *, pdk_name: str) -> TechRules:
    """Single conversion from vlsir.tech -> runtime rules used by generators."""
    ...
```


## 5) Unified `mosfet.py` (target ~220-300 LOC)

### Public API

```python
from enum import Enum, auto


class MosType(Enum):
    NMOS = auto()
    PMOS = auto()


class MosVth(Enum):
    LOW = auto()
    REGULAR = auto()
    HIGH = auto()


@L.paramclass
class MosfetParams:
    cell_name = L.Param(dtype=str)
    wf_mult = L.Param(dtype=int, default=1)
    lf_mult = L.Param(dtype=int, default=1)
    fing_count = L.Param(dtype=int, default=4)
    mosfet_vth = L.Param(dtype=MosVth, default=MosVth.LOW)
    track_count = L.Param(dtype=int, default=9)
    mosfet_type = L.Param(dtype=MosType, default=MosType.NMOS)
    source_tie = L.Param(dtype=bool, default=False)
    m1_power_bar_width_mult = L.Param(dtype=float, default=2.0)
```

### Generator structure

```python
@L.generator
def mosfet(params: MosfetParams, rules: TechRules) -> kdb.Layout:
    layout = create_layout(rules.dbu_um)
    top = layout.create_cell(params.cell_name)

    # name-only generic layers (no numeric ids in generator code)
    m1_draw = layout.layer(kdb.LayerInfo("M1.draw"))
    m1_pin = layout.layer(kdb.LayerInfo("M1.pin"))
    od_draw = layout.layer(kdb.LayerInfo("OD.draw"))
    po_draw = layout.layer(kdb.LayerInfo("PO.draw"))

    # 1) derive dimensions from rules + params
    # 2) draw VSS/VDD rails using M1 and m1_power_bar_width_mult
    # 3) place active/poly/contact arrays
    # 4) place opposite dummy row (NMOS<->PMOS)
    # 5) route S/D/G rails + pin markers
    # 6) boundary/text
    return layout
```

### Internal helper budget
Maximum `2-3` focused helpers in this file, for example:

```python
def _rail_width_um(params: MosfetParams, rules: TechRules) -> float: ...
def _draw_contact_array(...): ...
def _draw_pin(...): ...
```


## 6) `momcap.py` (target ~180-260 LOC)

Monolithic top-level generator with a small parameter class and compact geometry derivation.

```python
@L.paramclass
class MomcapParams:
    cell_name = L.Param(dtype=str)
    top_layer = L.Param(dtype=type(L.M1), default=L.M6)
    bottom_layer = L.Param(dtype=type(L.M1), default=L.M5)

    # integer-only geometry controls (all defaults = 1)
    inner_width_mult = L.Param(dtype=int, default=1)
    inner_width_height = L.Param(dtype=int, default=1)
    spacing_multi = L.Param(dtype=int, default=1)
    outer_width_mult = L.Param(dtype=int, default=1)
```

```python
@L.generator
def momcap(params: MomcapParams, rules: TechRules) -> kdb.Layout:
    layout = create_layout(rules.dbu_um)
    top = layout.create_cell(params.cell_name)

    # one inner strip + one outer surrounding ring (no fingers)
    # place uniform vias to connect top/bottom around both structures

    top_min_w = min_width_um(rules, params.top_layer)
    top_min_area = min_area_um2(rules, params.top_layer)
    top_long_spacing = min_spacing_long_run_um(rules, params.top_layer)

    # base height to satisfy min-area with minimum top-metal width
    base_inner_h = top_min_area / top_min_w

    inner_w = params.inner_width_mult * top_min_w
    inner_h = params.inner_width_height * base_inner_h
    gap = params.spacing_multi * top_long_spacing
    ring_w = params.outer_width_mult * top_min_w

    # draw inner strip and ring on top and bottom layers
    # then add uniformly stepped vias along perimeters
    return layout
```

Dimension equations used by the generator:

```python
inner_rect = Rect(0, 0, inner_w, inner_h)
ring_inner = expand(inner_rect, dx=gap, dy=gap)
ring_outer = expand(ring_inner, dx=ring_w, dy=ring_w)
ring_shape = ring_outer - ring_inner
```

Uniform via placement strategy:

```python
via_size = min_width_um(rules, via_between(params.bottom_layer, params.top_layer))
via_spacing = min_spacing_um(rules, via_between(params.bottom_layer, params.top_layer))
via_step = via_size + via_spacing

place_vias_on_perimeter(inner_rect, step=via_step)
place_vias_on_perimeter(ring_inner, step=via_step)
place_vias_on_perimeter(ring_outer, step=via_step)
```


## 7) Generic-to-Tech-Layer Mapping at Export Time

Generator writes only generic named layers (`"M1.draw"`, `"M1.pin"`, ...).
Before serialization we do an in-place migration to the numeric `(layer, datatype)` from `Technology.layers`.

### Internal layer naming strategy

```python
# Generic names used while building geometry.
DRAW_LAYER_NAME = {
    L.OD: "OD.draw",
    L.PO: "PO.draw",
    L.CO: "CO.draw",
    L.M1: "M1.draw",
    L.VIA1: "VIA1.draw",
    # ...
}

PIN_LAYER_NAME = {
    L.M1: "M1.pin",
    L.M2: "M2.pin",
    L.M3: "M3.pin",
    # ...
}
```

### In-place remap before serialization

```python
def remap_named_layers_inplace(layout: kdb.Layout, tech: vtech.Technology) -> None:
    """Mutate layout so named generic layers move to numeric tech-layer LPPs."""

    # 1) resolve target numeric specs from technology aliases
    target_by_name = {
        "M1.draw": resolve_layer_spec_from_technology(tech, ("M1", "METAL1")),
        "M1.pin": resolve_layer_spec_from_technology(tech, ("M1.PIN", "METAL1.PIN")),
        "PO.draw": resolve_layer_spec_from_technology(tech, ("PO", "POLY")),
        # ... full generic table
    }

    # 2) for each named source layer, move all shapes to numeric destination
    for generic_name, dst_spec in target_by_name.items():
        if dst_spec is None:
            continue

        src_idx = layout.find_layer(kdb.LayerInfo(generic_name))
        if src_idx < 0:
            continue

        dst_idx = layout.layer(kdb.LayerInfo(dst_spec[0], dst_spec[1], generic_name))

        for cell in layout.each_cell():
            src_shapes = cell.shapes(src_idx)
            if src_shapes.is_empty():
                continue

            # copy then clear source layer in-place
            for shape in src_shapes.each():
                cell.shapes(dst_idx).insert(shape)
            src_shapes.clear()
```

```python
layout = mosfet(params, rules)               # generic named layers only
remap_named_layers_inplace(layout, tech)     # mutates to physical numeric tech-layer LPP
raw = layout_to_vlsir_raw(layout)
vlsir_raw_to_disk(raw, pb_path, pbtxt_path)
```

### Param-derived raw instance naming (single-function implementation)

We will implement parameter-derived raw-instance names inside the existing serializer function,
without introducing additional top-level helper functions.

```python
def layout_to_vlsir_raw(
    layout: kdb.Layout,
    domain: str = "frida.layout",
    instance_params: dict[object, object] | None = None,
) -> vlsir.raw_pb2.Library:
    """
    KLayout -> VLSIR raw conversion.

    `instance_params` is optional. When provided, instance names include
    param-derived suffixes similar to HDL21 netlist naming.

    Accepted mapping keys (priority order):
    1) (parent_cell_name, inst_idx, ia, ib)
    2) (parent_cell_name, inst_idx)
    3) target_cell_name
    """

    params_map = instance_params or {}
    library = vlsir.raw_pb2.Library(domain=domain, units=vlsir.raw_pb2.Units.MICRO)

    for cell in layout.each_cell():
        raw_layout = vlsir.raw_pb2.Layout(name=cell.name)

        # ... existing shape conversion code ...

        for inst_idx, inst in enumerate(cell.each_inst()):
            target_name = layout.cell(inst.cell_index).name
            trans = inst.trans

            # arrays expanded as in current serializer
            array_points = [(0, 0, int(trans.disp.x), int(trans.disp.y))]
            if inst.is_regular_array() and (inst.na > 1 or inst.nb > 1):
                array_points = [
                    (
                        ia,
                        ib,
                        int(trans.disp.x + ia * inst.a.x + ib * inst.b.x),
                        int(trans.disp.y + ia * inst.a.y + ib * inst.b.y),
                    )
                    for ia in range(inst.na)
                    for ib in range(inst.nb)
                ]

            for ia, ib, x, y in array_points:
                params = params_map.get((cell.name, inst_idx, ia, ib))
                if params is None:
                    params = params_map.get((cell.name, inst_idx))
                if params is None:
                    params = params_map.get(target_name)

                # inline param -> slug formatting (single-function design)
                slug = ""
                if params is not None:
                    fields = []
                    if hasattr(params, "__dict__"):
                        for k, v in vars(params).items():
                            if k.startswith("_"):
                                continue
                            vv = getattr(v, "name", v)  # enum support
                            fields.append((k, str(vv).lower()))
                    fields.sort(key=lambda x: x[0])
                    slug = "__".join(f"{k}-{v}" for k, v in fields)

                if slug:
                    inst_name = f"{target_name.lower()}__{slug}__i{inst_idx}_{ia}_{ib}"
                else:
                    inst_name = f"{target_name.lower()}__i{inst_idx}_{ia}_{ib}"

                raw_layout.instances.append(
                    vlsir.raw_pb2.Instance(
                        name=inst_name,
                        cell=vutils.Reference(local=target_name),
                        origin_location=vlsir.raw_pb2.Point(x=x, y=y),
                        reflect_vert=bool(trans.is_mirror()),
                        rotation_clockwise_degrees=int(trans.angle * 90),
                    )
                )

        library.cells.append(vlsir.raw_pb2.Cell(name=cell.name, layout=raw_layout))

    return library
```

Usage sketch:

```python
raw = layout_to_vlsir_raw(
    layout,
    domain=f"frida.layout.{tech_name}",
    instance_params={
        ("TOP", 0): mosfet_params_a,
        ("TOP", 1): mosfet_params_b,
    },
)
```


## 8) Tech-Layer Rule Deck in `pdk/*/layout/pdk_layout.py`

Each `pdk/*/layout/pdk_layout.py` should keep only a tiny API surface.

Per PDK layout file, target exactly four functions:
1. `canonical_layer_aliases() -> CanonicalAliasMap` (generic -> tech-layer names)
2. `layer_infos() -> tuple[LayerInfoData, ...]` (tech layer-purpose pairs)
3. `<pdk>_rule_deck() -> RuleDeck` (minimal typed rules needed by generators)
4. `write_<pdk>_tech_proto(out_dir: Path) -> TechArtifacts` (serialize to VLSIR tech)

And per PDK test file, keep one function:
- `test_<pdk>_to_vlsir(...)`

No extra helper stacks in these files unless strictly required for readability.

Each `pdk/*/layout/pdk_layout.py` therefore keeps only:
- generic alias maps,
- `layer_infos()` for tech-layer purpose pairs,
- a compact typed rule deck with only the rule families needed by `@L.generator` layout code.

The intent is to keep PDK portability by querying a small consistent rule surface.

Example style for a PDK rule deck:

```python
import hdl21 as h

n = h.n
deck = RuleDeck()

deck.layer(L.OD).min_spacing(rule=140 * n)
deck.layer(L.PO).min_spacing(rule=100 * n)
deck.layer(L.CO).min_spacing(rule=100 * n)
deck.layer(L.VIA1).min_spacing(rule=100 * n)
deck.layer(L.VIA2).min_spacing(rule=100 * n)
deck.layer(L.VIA3).min_spacing(rule=100 * n)
deck.layer(L.VIA4).min_spacing(rule=100 * n)
deck.layer(L.VIA5).min_spacing(rule=100 * n)
deck.layer(L.VIA6).min_spacing(rule=100 * n)
deck.layer(L.VIA7).min_spacing(rule=340 * n)
deck.layer(L.VIA8).min_spacing(rule=340 * n)
deck.layer(L.VIA9).min_spacing(rule=3000 * n)
deck.layer(L.M10).min_spacing(rule=2000 * n)

deck.layer(L.CO).min_enclosure(of=L.OD, rule=30 * n)
deck.layer(L.CO).min_enclosure(of=L.PO, rule=30 * n)
deck.layer(L.CO).min_spacing(to=L.PO, rule=50 * n)
deck.layer(L.M1).min_enclosure(of=L.CO, rule=20 * n)
deck.layer(L.NP).min_enclosure(of=L.OD, rule=80 * n)
deck.layer(L.PP).min_enclosure(of=L.OD, rule=80 * n)
deck.layer(L.NWELL).min_enclosure(of=L.OD, rule=120 * n)
```

For this plan, this minimal set is treated as sufficient for portable MOSFET/MOMCAP generators.

Example alias/layer-info signatures:

```python
def canonical_layer_aliases() -> CanonicalAliasMap:
    return {
        L.OD: ("ACTIVE",),
        L.PO: ("POLY",),
        L.CO: ("CONT",),
        L.M1: ("METAL1",),
        L.VIA1: ("VIA1",),
        # ...
        L.NWELL: ("NWELL",),
        L.TEXT: ("TEXT",),
        L.PR_BOUNDARY: ("PR_BOUNDARY",),
    }


def layer_infos() -> tuple[LayerInfoData, ...]:
    return (
        LayerInfoData(name="ACTIVE", index=1, sub_index=0),
        LayerInfoData(name="POLY", index=2, sub_index=0),
        LayerInfoData(name="CONT", index=3, sub_index=0),
        LayerInfoData(name="METAL1", index=7, sub_index=0),
        LayerInfoData(name="M1.PIN", index=7, sub_index=1, purpose_type="PIN"),
        # ...
        LayerInfoData(name="TEXT", index=63, sub_index=0, purpose_type="LABEL"),
        LayerInfoData(name="PR_BOUNDARY", index=189, sub_index=0, purpose_type="OUTLINE"),
    )
```


## 9) Test Reduction Plan

### Keep
- `flow/layout/test_serialize.py` (VLSIR interface verification).

### Replace current generator/ layer/ rule tests with two runtime sweeps
- `flow/layout/test_mosfet.py`
- `flow/layout/test_momcap.py`

### Delete (planned)
- `flow/layout/test_layers.py`
- `flow/layout/test_rules.py`
- `flow/layout/test_generators.py`

### Keep one PDK->VLSIR conversion test per PDK package
- `pdk/ihp130/layout/test_pdk_layout.py` keeps a single `test_ihp130_to_vlsir()` style test
- `pdk/tower180/layout/test_pdk_layout.py` keeps a single `test_tower180_to_vlsir()` style test
- `pdk/tsmc28/layout/test_pdk_layout.py` keeps a single `test_tsmc28_to_vlsir()` style test
- `pdk/tsmc65/layout/test_pdk_layout.py` keeps a single `test_tsmc65_to_vlsir()` style test

Each test should only verify:
- tech proto generation succeeds,
- `Technology.layers` has expected key entries,
- rule deck conversion to `vlsir.tech` succeeds without schema errors.

Example (`pdk/tsmc65/layout/test_pdk_layout.py`):

```python
def test_tsmc65_to_vlsir(tmp_path: Path) -> None:
    artifacts = write_tsmc65_tech_proto(tmp_path)
    tech = read_technology_proto(artifacts.pb)

    assert tech.name.lower() == "tsmc65"
    assert any(li.name.upper() in ("M1", "METAL1") for li in tech.layers)
    assert len(tech.rules.layers) > 0
```

### New sweep examples

```python
def test_mosfet_sweep(tmp_path: Path, tech: str) -> None:
    tech_pb = write_pdk_tech_proto(tech, tmp_path / "tech")
    proto = read_technology_proto(tech_pb)
    rules = rules_from_technology(proto, pdk_name=tech)

    variants = [
        MosfetParams(
            cell_name=f"mos_{tp.name.lower()}_{n}f_{wf}w",
            mosfet_type=tp,
            track_count=9,
            fing_count=n,
            wf_mult=wf,
            lf_mult=1,
            source_tie=tie,
            m1_power_bar_width_mult=2.0,
        )
        for tp in (MosType.NMOS, MosType.PMOS)
        for n in (2, 4, 8)
        for wf in (1, 2, 3)
        for tie in (False, True)
    ]

    for p in variants:
        layout = mosfet(p, rules)
        remap_named_layers_inplace(layout, proto)
        export_layout(layout, tmp_path, p.cell_name, domain=f"frida.layout.{tech}")
```

```python
def test_momcap_sweep(tmp_path: Path, tech: str) -> None:
    tech_pb = write_pdk_tech_proto(tech, tmp_path / "tech")
    proto = read_technology_proto(tech_pb)
    rules = rules_from_technology(proto, pdk_name=tech)

    for iw in (1, 2, 3):
        for ih in (1, 2, 4):
            for sp in (1, 2, 3):
                for ow in (1, 2):
                    p = MomcapParams(
                        cell_name=f"momcap_iw{iw}_ih{ih}_sp{sp}_ow{ow}",
                        top_layer=L.M6,
                        bottom_layer=L.M5,
                        inner_width_mult=iw,
                        inner_width_height=ih,
                        spacing_multi=sp,
                        outer_width_mult=ow,
                    )
                    layout = momcap(p, rules)
                    remap_named_layers_inplace(layout, proto)
                    export_layout(layout, tmp_path, p.cell_name)
```


## 10) Implementation Order

1. Finalize DSL API and expose from `flow/layout/__init__.py`.
2. Add `TechRules` extraction path (single runtime object).
3. Trim each `pdk/*/layout/pdk_layout.py` to the four-function contract (aliases, layer infos, rule deck, write-tech-proto).
4. Create `flow/layout/mosfet.py` unified generator with `m1_power_bar_width_mult` default `2.0`.
5. Refactor `flow/layout/momcap.py` to the same style (single primary function).
6. Add generic named-layer -> numeric tech-layer LPP in-place remap utility and call it before export.
7. Add param-derived raw-instance naming support inside `layout_to_vlsir_raw(...)`.
8. Replace layout tests with minimal set (serialize + mosfet sweep + momcap sweep).
9. Reduce each PDK layout test file to one `test_*_to_vlsir` conversion test.
10. Delete obsolete tests and legacy generator modules (`nmos.py`).
11. Run `uv run pytest flow/layout pdk` and fix only regressions relevant to new flow.


## 11) Code Size Targets

- `flow/layout/mosfet.py`: `220-300` LOC
- `flow/layout/momcap.py`: `180-260` LOC
- `flow/layout/tech.py` generator-facing runtime extraction section: `120-180` LOC
- tests total under `flow/layout`: `<= 3` files


## 12) Notes

- This plan intentionally favors readability and directness over maximal abstraction.
- We keep generic layer IDs in generator code (`L.M1`, etc.), consistent with your preferred syntax style.
- M1 power-bar width is explicitly parameterized, with default tied to technology minimum (`2x`).
- MOMCAP geometry parameters are integer-only multipliers (`inner_width_mult`, `inner_width_height`, `spacing_multi`, `outer_width_mult`).
- MOMCAP spacing uses long-run minimum spacing from the selected top metal layer.
- PDK layout tests are reduced to one `test_*_to_vlsir` smoke conversion test per PDK.
