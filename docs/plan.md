# Layout Plan v2: Minimal Runtime + Monolithic Generators

This plan replaces the current over-split layout stack with a minimal, generator-focused implementation.

Primary goals:
- keep only what is needed for `mosfet` and `momcap` generation,
- keep generator files readable and mostly monolithic (target `200-300` lines each),
- keep generic layer names (`L.M1`, etc.) in generator code,
- generate KLayout geometry on name-only layers (for example `"M1.draw"`, `"M1.pin"`) with no numeric layer ids in generator logic,
- remap those named layers in-place to tech-layer `(layer, datatype)` right before raw export,
- minimize tests to: VLSIR interface checks + in-file sweep tests inside generator modules.


## 1) End-State Architecture

### Keep
- `flow/layout/dsl.py` for `Param`, `@paramclass`, `@generator` ergonomics.
- `flow/layout/tech.py` for generic->tech mapping types, typed rule/layer data, and `map_generic_to_tech_layers(...)`.
- `flow/layout/serialize.py` for KLayout <-> VLSIR serdes (`vlsir.raw` export and `vlsir.tech` read/write).
- `flow/layout/mosfet.py` new unified NMOS/PMOS + dummy-opposite generator.
- `flow/layout/momcap.py` monolithic MOMCAP generator.
- tech-layer metadata modules under `pdk/*/layout/pdk_layout.py` (trimmed to needed metadata).

### Remove / reduce
- heavy test fanout in `flow/layout` and `pdk/*/layout`.
- helper explosions in generator modules.
- duplicated conversion APIs that do the same work with different names.

### Expected `flow/layout` tree (end state)

```text
flow/layout/
├── __init__.py      # public API surface; exports L namespace + core helpers
├── dsl.py           # L.Layer ids, L.Param, @L.paramclass, @L.generator
├── tech.py          # rule/layer/map types + map_generic_to_tech_layers(...) + tech-map helpers
├── serialize.py     # KLayout->vlsir.raw, vlsir.tech read/write, filesystem I/O, inline test
├── mosfet.py        # unified MOSFET generator + in-file test_mosfet(mode)
└── momcap.py        # strip+ring MOMCAP generator + in-file test_momcap(mode)
```

Files expected to be removed from `flow/layout/`:

```text
nmos.py             # replaced by mosfet.py
layers.py           # merged into dsl.py/ tech.py
rules.py            # merged into tech.py
klayout.py          # helpers inlined in generators where needed
test_serialize.py   # moved to in-file serialize.py test function
test_layers.py      # removed
test_rules.py       # removed
test_generators.py  # removed
layout.py           # already removed
```


## 2) Parameter DSL (already started)

We use one local layout namespace API `L` for layers and generator/ param decorators.

In this plan, `L` is the single surface for:
- layer ids (`L.M1`, `L.VIA1`, ...),
- parameter fields (`L.Param(...)`),
- decorators (`@L.paramclass`, `@L.generator`).

For typed parameter selection, `dsl.py` defines integer-backed enums and a
single conversion function from user params -> generic layers:

```python
from enum import IntEnum
from dataclasses import dataclass


class Purpose(IntEnum):
    DRAW = 0
    PIN = 1


@dataclass(frozen=True)
class LayerRef:
    layer: L
    purpose: Purpose


class MosType(IntEnum):
    NMOS = 0
    PMOS = 1


class MosVth(IntEnum):
    LOW = 0
    REGULAR = 1
    HIGH = 2


class SourceTie(IntEnum):
    OFF = 0
    ON = 1


class MetalDraw(IntEnum):
    M1 = 1
    M2 = 2
    M3 = 3
    M4 = 4
    M5 = 5
    M6 = 6
    M7 = 7
    M8 = 8
    M9 = 9
    M10 = 10


def generic_name(ref: LayerRef) -> str:
    if ref.purpose == Purpose.DRAW:
        return f"{ref.layer.name}.draw"
    if ref.purpose == Purpose.PIN:
        return f"{ref.layer.name}.pin"
    raise ValueError("Unsupported layer purpose")


METAL_DRAW_TO_GENERIC = {
    MetalDraw.M1: L.M1,
    MetalDraw.M2: L.M2,
    MetalDraw.M3: L.M3,
    MetalDraw.M4: L.M4,
    MetalDraw.M5: L.M5,
    MetalDraw.M6: L.M6,
    MetalDraw.M7: L.M7,
    MetalDraw.M8: L.M8,
    MetalDraw.M9: L.M9,
    MetalDraw.M10: L.M10,
}

VTH_TO_GENERIC = {
    MosVth.LOW: L.VTH_LVT,
    MosVth.REGULAR: None,
    MosVth.HIGH: L.VTH_HVT,
}


def param_to_generic(
    *, metal: MetalDraw | None = None, vth: MosVth | None = None
) -> L | None:
    """Map typed parameter enums to generic layer ids."""
    if (metal is None) == (vth is None):
        raise ValueError("pass exactly one selector: metal or vth")
    if metal is not None:
        return METAL_DRAW_TO_GENERIC[metal]
    return VTH_TO_GENERIC[vth]
```

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
def mosfet(params: MosfetParams, tech: "vtech.Technology") -> "kdb.Layout":
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
    powerrail_mult = L.Param(
        dtype=int,
        desc="Power-rail width multiplier of M1 minimum width",
        default=2,
    )
```

Default behavior:

```python
rail_width_nm = params.powerrail_mult * min_width_nm[L.M1]
```

### Track / row handling
Design decision:
- routing minimum width/spacing and enclosure rules come from `tech.rules`,
- rail width default is parameterized (`powerrail_mult = 2`),
- any row-height/ pitch convention that is not available in rules is kept as explicit generator parameter input rather than a hardcoded per-PDK table in this plan.


## 4) Runtime Technology Model (no duplicate extraction object)

Generators consume `vlsir.tech_pb2.Technology` directly.

- no separate `TechRules` dataclass,
- no `rules_from_technology(...)` conversion layer,
- rules are read directly from `tech.rules` inside generator bodies.

```python
def mosfet(params: MosfetParams, tech: vtech.Technology) -> kdb.Layout:
    layout = kdb.Layout()
    layout.dbu = tech.units * 1e-3  # example conversion to um/dbu

    # inline extraction from tech.rules (no separate helper object)
    min_width_nm = {
        L.M1: ...,
        L.PO: ...,
        L.OD: ...,
    }
    min_spacing_nm = {
        L.PO: ...,
        L.OD: ...,
    }
    ...
```


## 5) Unified `mosfet.py` (target ~220-300 LOC)

### Public API

```python
@L.paramclass
class MosfetParams:
    wf_mult = L.Param(dtype=int, default=1)
    lf_mult = L.Param(dtype=int, default=1)
    fing_count = L.Param(dtype=int, default=4)
    mosfet_vth = L.Param(dtype=L.MosVth, default=L.MosVth.LOW)
    track_count = L.Param(dtype=int, default=9)
    mosfet_type = L.Param(dtype=L.MosType, default=L.MosType.NMOS)
    source_tie = L.Param(dtype=L.SourceTie, default=L.SourceTie.OFF)
    powerrail_mult = L.Param(dtype=int, default=2)
```

### Generator structure

```python
@L.generator
def mosfet(params: MosfetParams, tech: vtech.Technology) -> kdb.Layout:
    layout = kdb.Layout()
    layout.dbu = tech.units * 1e-3  # example conversion to um/dbu
    top = layout.create_cell("MOSFET")

    # name-only generic layers (no numeric ids in generator code)
    m1_draw = layout.layer(kdb.LayerInfo("M1.draw"))
    m1_pin = layout.layer(kdb.LayerInfo("M1.pin"))
    od_draw = layout.layer(kdb.LayerInfo("OD.draw"))
    po_draw = layout.layer(kdb.LayerInfo("PO.draw"))

    # 1) derive dimensions from rules + params
    # 2) draw VSS/VDD rails using M1 and powerrail_mult
    # 3) place active/poly/contact arrays
    # 4) place opposite dummy row (NMOS<->PMOS)
    # 5) route S/D/G rails + pin markers
    # 6) boundary/text

    # direct rule pulls from tech.rules (no helper wrappers / no extra object)
    min_width_nm = {
        L.M1: ...,
        L.PO: ...,
        L.OD: ...,
    }
    min_spacing_nm = {
        L.PO: ...,
        L.OD: ...,
    }

    m1_min_w = min_width_nm[L.M1]
    po_min_space = min_spacing_nm[L.PO]
    od_min_space = min_spacing_nm[L.OD]
    vth_layer = L.param_to_generic(vth=params.mosfet_vth)

    # all geometry expressed as integer multiples of technology mins + params
    rail_w = params.powerrail_mult * m1_min_w
    finger_pitch = po_min_space + m1_min_w

    for fing in range(params.fing_count):
        x0 = fing * finger_pitch
        x1 = x0 + params.wf_mult * m1_min_w
        top.shapes(od_draw).insert(kdb.Box(x0, 0, x1, params.lf_mult * m1_min_w))
        top.shapes(po_draw).insert(kdb.Box(x0, -od_min_space, x1, rail_w + od_min_space))

    # apply optional VTH selection doping by enum -> generic layer mapping
    if vth_layer is not None:
        vth_draw = layout.layer(kdb.LayerInfo(L.generic_name(LayerRef(vth_layer, L.Purpose.DRAW))))
        top.shapes(vth_draw).insert(kdb.Box(0, 0, finger_pitch * params.fing_count, rail_w))

    return layout
```

Generator core-function rule:
- no local helper functions for geometry construction in `mosfet(...)` or `momcap(...)`
- no wrapper calls like `draw_*`, `expand`, `place_*`, or `min_*_um` helpers in the core body
- use direct KLayout PyPI API (`kdb.Box`, `kdb.Cell.shapes(...).insert(...)`) and simple `for` loops
- dimensions are driven directly from `tech.rules` extraction + integer parameter multipliers


## 6) `momcap.py` (target ~180-260 LOC)

Monolithic top-level generator with a small parameter class and compact geometry derivation.

```python
@L.paramclass
class MomcapParams:
    # typed metal selectors (not raw ints)
    top_layer = L.Param(
        dtype=L.MetalDraw,
        default=L.MetalDraw.M6,
    )
    bottom_layer = L.Param(
        dtype=L.MetalDraw,
        default=L.MetalDraw.M5,
    )

    # integer-only geometry controls (all defaults = 1)
    inner_width_mult = L.Param(dtype=int, default=1)
    inner_width_height = L.Param(dtype=int, default=1)
    spacing_multi = L.Param(dtype=int, default=1)
    outer_width_mult = L.Param(dtype=int, default=1)
```

```python
@L.generator
def momcap(params: MomcapParams, tech: vtech.Technology) -> kdb.Layout:
    layout = kdb.Layout()
    layout.dbu = tech.units * 1e-3  # example conversion to um/dbu
    top = layout.create_cell("MOMCAP")

    # one inner strip + one outer surrounding ring (no fingers)
    # place uniform vias to connect top/bottom around both structures

    top_layer = L.param_to_generic(metal=params.top_layer)
    bottom_layer = L.param_to_generic(metal=params.bottom_layer)
    if top_layer is None or bottom_layer is None:
        raise ValueError("MetalDraw must map to generic drawing layers")

    min_width_nm = {
        top_layer: ...,
    }
    min_area_nm2 = {
        top_layer: ...,
    }
    long_run_spacing_nm = {
        top_layer: ...,
    }
    via_between = {
        (bottom_layer, top_layer): ...,
    }
    min_spacing_nm = {
        via_between[(bottom_layer, top_layer)]: ...,
    }

    top_min_w = min_width_nm[top_layer]
    top_min_area = min_area_nm2[top_layer]
    top_long_spacing = long_run_spacing_nm[top_layer]
    via_min_w = min_width_nm[via_between[(bottom_layer, top_layer)]]
    via_min_space = min_spacing_nm[via_between[(bottom_layer, top_layer)]]

    # base height to satisfy min-area with minimum top-metal width (integer math)
    base_inner_h = max(1, (top_min_area + top_min_w - 1) // top_min_w)

    inner_w = params.inner_width_mult * top_min_w
    inner_h = params.inner_width_height * base_inner_h
    gap = params.spacing_multi * top_long_spacing
    ring_w = params.outer_width_mult * top_min_w
    via_step = via_min_w + via_min_space

    # direct coordinate math (no helper wrappers)
    ix0, iy0 = 0, 0
    ix1, iy1 = inner_w, inner_h

    rx0 = ix0 - gap - ring_w
    ry0 = iy0 - gap - ring_w
    rx1 = ix1 + gap + ring_w
    ry1 = iy1 + gap + ring_w

    rix0 = ix0 - gap
    riy0 = iy0 - gap
    rix1 = ix1 + gap
    riy1 = iy1 + gap

    # draw inner strip and ring with raw kdb.Box inserts
    top.shapes(top_draw).insert(kdb.Box(ix0, iy0, ix1, iy1))
    top.shapes(top_draw).insert(kdb.Box(rx0, ry0, rx1, riy0))
    top.shapes(top_draw).insert(kdb.Box(rx0, riy1, rx1, ry1))
    top.shapes(top_draw).insert(kdb.Box(rx0, riy0, rix0, riy1))
    top.shapes(top_draw).insert(kdb.Box(rix1, riy0, rx1, riy1))

    # uniform via placement using explicit for-loops
    for x in range(ix0, ix1 + 1, via_step):
        top.shapes(via_draw).insert(kdb.Box(x, iy0, x + via_min_w, iy0 + via_min_w))
        top.shapes(via_draw).insert(kdb.Box(x, iy1 - via_min_w, x + via_min_w, iy1))
    for y in range(iy0, iy1 + 1, via_step):
        top.shapes(via_draw).insert(kdb.Box(ix0, y, ix0 + via_min_w, y + via_min_w))
        top.shapes(via_draw).insert(kdb.Box(ix1 - via_min_w, y, ix1, y + via_min_w))

    return layout
```


## 7) Generic-to-Tech-Layer Mapping at Export Time

Generator writes only generic named layers (`"M1.draw"`, `"M1.pin"`, ...).
Before serialization we do an in-place migration to the numeric `(layer, datatype)` from `Technology.layers`.

### Internal layer naming strategy

```python
# generator inserts shapes on generic names built from LayerRef
top.shapes(layout.layer(kdb.LayerInfo(L.generic_name(LayerRef(L.M1, L.Purpose.DRAW)))))
top.shapes(layout.layer(kdb.LayerInfo(L.generic_name(LayerRef(L.M1, L.Purpose.PIN)))))
```

### In-place remap before serialization

```python
TechLayerMap = dict[LayerRef, LayerInfoData]


def map_generic_to_tech_layers(layout: kdb.Layout, tech_layers: TechLayerMap) -> None:
    """Mutate layout so generic names move to explicit tech layer/purpose ids."""

    for ref, info in tech_layers.items():
        generic = L.generic_name(ref)
        src_idx = layout.find_layer(kdb.LayerInfo(generic))
        if src_idx < 0:
            continue

        dst_idx = layout.layer(kdb.LayerInfo(info.index, info.sub_index, info.name))

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
layout = mosfet(params, tech)                       # generic named layers only
map_generic_to_tech_layers(layout, tech_layer_map())  # mutates to physical numeric tech-layer LPP
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
1. `tech_layer_map() -> TechLayerMap` (generic layer-purpose -> concrete tech `LayerInfoData`)
2. `layer_infos() -> tuple[LayerInfoData, ...]` (tech layer-purpose pairs)
3. `<pdk>_rule_deck() -> RuleDeck` (minimal typed rules needed by generators)
4. `test_<pdk>_to_vlsir(...)` (in-file conversion smoke test)

Tech-proto read/write is handled by shared serdes helpers in `flow/layout/serialize.py`
rather than per-PDK write wrappers.

No extra helper stacks in these files unless strictly required for readability.

Each `pdk/*/layout/pdk_layout.py` therefore keeps only:
- one generic->tech layer map including explicit `index`/`sub_index` and tech names,
- `layer_infos()` for tech-layer purpose pairs,
- a compact typed rule deck with only the rule families needed by `@L.generator` layout code.
- one in-file `test_<pdk>_to_vlsir(...)` function.

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

Example tech-map/layer-info signatures:

```python
TechLayerMap = dict[LayerRef, LayerInfoData]


def tech_layer_map() -> TechLayerMap:
    return {
        LayerRef(L.OD, L.Purpose.DRAW): LayerInfoData(name="ACTIVE", index=1, sub_index=0),
        LayerRef(L.PO, L.Purpose.DRAW): LayerInfoData(name="POLY", index=2, sub_index=0),
        LayerRef(L.CO, L.Purpose.DRAW): LayerInfoData(name="CONT", index=3, sub_index=0),
        LayerRef(L.M1, L.Purpose.DRAW): LayerInfoData(name="METAL1", index=31, sub_index=0),
        LayerRef(L.M1, L.Purpose.PIN): LayerInfoData(name="M1.PIN", index=31, sub_index=1, purpose_type="PIN"),
        LayerRef(L.M2, L.Purpose.PIN): LayerInfoData(name="M2.PIN", index=9, sub_index=1, purpose_type="PIN"),
        # ...
        LayerRef(L.TEXT, L.Purpose.DRAW): LayerInfoData(name="TEXT", index=63, sub_index=0, purpose_type="LABEL"),
        LayerRef(L.PR_BOUNDARY, L.Purpose.DRAW): LayerInfoData(name="PR_BOUNDARY", index=189, sub_index=0, purpose_type="OUTLINE"),
    }


def layer_infos() -> tuple[LayerInfoData, ...]:
    return (
        LayerInfoData(name="ACTIVE", index=1, sub_index=0),
        LayerInfoData(name="POLY", index=2, sub_index=0),
        LayerInfoData(name="CONT", index=3, sub_index=0),
        LayerInfoData(name="METAL1", index=31, sub_index=0),
        LayerInfoData(name="M1.PIN", index=31, sub_index=1, purpose_type="PIN"),
        # ...
        LayerInfoData(name="TEXT", index=63, sub_index=0, purpose_type="LABEL"),
        LayerInfoData(name="PR_BOUNDARY", index=189, sub_index=0, purpose_type="OUTLINE"),
    )
```


## 9) Test Reduction Plan

### Keep
- one in-file `test_serialize(...)` function inside `flow/layout/serialize.py`.

### Generator sweep tests live inline
- add one in-file `test_mosfet(...)` function inside `flow/layout/mosfet.py`
- add one in-file `test_momcap(...)` function inside `flow/layout/momcap.py`
- do **not** create `flow/layout/test_mosfet.py` or `flow/layout/test_momcap.py`
- do **not** keep `flow/layout/test_serialize.py`

### Mode behavior via existing `conftest.py` option
- use existing `--mode` fixture (`min` / `max`) for both in-file sweep tests
- `mode=min`: run one default param set only (single instance)
- `mode=max`: run full cartesian parameter sweeps
- expected invocation: `pytest flow/layout --tech=tsmc65 --mode=min` or `pytest flow/layout --tech=tsmc65 --mode=max`
- update pytest discovery to collect inline tests from `mosfet.py`, `momcap.py`, `serialize.py`, and `pdk_layout.py`

### Delete (planned)
- `flow/layout/test_serialize.py`
- `flow/layout/test_layers.py`
- `flow/layout/test_rules.py`
- `flow/layout/test_generators.py`

### PDK test-file cleanup note
- delete extra `test_*.py` files in `pdk/*/layout/`
- keep one `test_<pdk>_to_vlsir(...)` conversion function in the same file: `pdk/*/layout/pdk_layout.py`
- this single in-file conversion function is the only PDK-specific test in scope

Each test should only verify:
- tech proto generation succeeds,
- `Technology.layers` has expected key entries,
- rule deck conversion to `vlsir.tech` succeeds without schema errors.

Example (`pdk/tsmc65/layout/pdk_layout.py`):

```python
def test_tsmc65_to_vlsir(tmp_path: Path) -> None:
    artifacts = write_technology_proto(
        tech_name="tsmc65",
        layer_infos=layer_infos(),
        rule_deck=tsmc65_rule_deck(),
        out_dir=tmp_path,
    )
    tech = read_technology_proto(artifacts.pb)

    assert tech.name.lower() == "tsmc65"
    assert any(li.name.upper() in ("M1", "METAL1") for li in tech.layers)
    assert len(tech.rules.layers) > 0
```

### New sweep examples

```python
def test_mosfet(tmp_path: Path, tech: str, mode: str) -> None:
    tech_pb = write_pdk_tech_proto(tech, tmp_path / "tech")
    proto = read_technology_proto(tech_pb)

    if mode == "min":
        variants = [MosfetParams()]
    else:
        variants = [
            MosfetParams(
                mosfet_type=tp,
                mosfet_vth=vth,
                track_count=9,
                fing_count=n,
                wf_mult=wf,
                lf_mult=1,
                source_tie=tie,
                powerrail_mult=2,
            )
            for tp in (L.MosType.NMOS, L.MosType.PMOS)
            for vth in (L.MosVth.LOW, L.MosVth.REGULAR, L.MosVth.HIGH)
            for n in (2, 4, 8)
            for wf in (1, 2, 3)
            for tie in (L.SourceTie.OFF, L.SourceTie.ON)
        ]

    for p in variants:
        layout = mosfet(p, proto)
        map_generic_to_tech_layers(layout, tech_layer_map())
        stem = (
            f"mos_t{p.mosfet_type.name.lower()}_v{p.mosfet_vth.name.lower()}_"
            f"nf{p.fing_count}_w{p.wf_mult}_l{p.lf_mult}_"
            f"s{p.source_tie.name.lower()}_pr{p.powerrail_mult}"
        )
        export_layout(layout, tmp_path, stem, domain=f"frida.layout.{tech}")
```

```python
def test_momcap(tmp_path: Path, tech: str, mode: str) -> None:
    tech_pb = write_pdk_tech_proto(tech, tmp_path / "tech")
    proto = read_technology_proto(tech_pb)

    if mode == "min":
        variants = [MomcapParams()]
    else:
        variants = [
            MomcapParams(
                top_layer=L.MetalDraw.M6,
                bottom_layer=L.MetalDraw.M5,
                inner_width_mult=iw,
                inner_width_height=ih,
                spacing_multi=sp,
                outer_width_mult=ow,
            )
            for iw in (1, 2, 3)
            for ih in (1, 2, 4)
            for sp in (1, 2, 3)
            for ow in (1, 2)
        ]

    for p in variants:
        layout = momcap(p, proto)
        map_generic_to_tech_layers(layout, tech_layer_map())
        stem = (
            f"momcap_t{p.top_layer.name.lower()}_b{p.bottom_layer.name.lower()}_iw{p.inner_width_mult}_"
            f"ih{p.inner_width_height}_sp{p.spacing_multi}_ow{p.outer_width_mult}"
        )
        export_layout(layout, tmp_path, stem)
```


## 10) Implementation Order

1. Finalize DSL API and expose from `flow/layout/__init__.py`.
2. Remove `TechRules` extraction layer and consume `vlsir.tech_pb2.Technology` directly in generators.
3. Trim each `pdk/*/layout/pdk_layout.py` to the four-function contract (tech-layer map, layer infos, rule deck, in-file `test_*_to_vlsir`).
4. Create `flow/layout/mosfet.py` unified generator with `powerrail_mult` default `2`.
5. Refactor `flow/layout/momcap.py` to the same style (single primary function).
6. Add `map_generic_to_tech_layers(...)` in-place remap utility and call it before export.
7. Add param-derived raw-instance naming support inside `layout_to_vlsir_raw(...)`.
8. Replace layout tests with minimal set (in-file `test_serialize` + in-file `test_mosfet` + in-file `test_momcap`).
9. Update pytest discovery config so inline tests in `mosfet.py`, `momcap.py`, `serialize.py`, and `pdk_layout.py` are collected with `pytest flow/layout pdk`.
10. Delete extra `pdk/*/layout/test_*.py` files and keep one `test_*_to_vlsir` function in each `pdk/*/layout/pdk_layout.py`.
11. Delete obsolete layout modules/tests (`nmos.py`, `layers.py`, `rules.py`, `klayout.py`, `test_serialize.py`, `test_layers.py`, `test_rules.py`, `test_generators.py`).
12. Run `uv run pytest flow/layout pdk` and fix only regressions relevant to new flow.


## 11) Code Size Targets

- `flow/layout/mosfet.py`: `220-300` LOC
- `flow/layout/momcap.py`: `180-260` LOC
- `flow/layout/serialize.py`: `160-260` LOC
- `flow/layout/tech.py` mapping/rule-query section: `120-180` LOC
- standalone tests under `flow/layout`: `0` files (tests live inline)


## 12) Notes

- This plan intentionally favors readability and directness over maximal abstraction.
- We keep generic layer IDs in generator code (`L.M1`, etc.), consistent with your preferred syntax style.
- rail width is explicitly parameterized as `powerrail_mult` (integer, default `2`).
- enum selectors use typed values (`L.MosType`, `L.MosVth`, `L.SourceTie`, `L.MetalDraw`) with `L.param_to_generic(...)` conversion to generic layers.
- MOMCAP geometry parameters are integer-only multipliers (`inner_width_mult`, `inner_width_height`, `spacing_multi`, `outer_width_mult`).
- MOMCAP spacing uses long-run minimum spacing from the selected top metal layer.
- PDK layout tests are reduced to one in-file `test_*_to_vlsir` smoke conversion function per PDK.
