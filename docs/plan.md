# FRIDA → OpenROAD Analog Layout Flow: Implementation Plan

## Architecture Overview

The system has three cleanly separated concerns:

1. **VLSIR (existing)** — Emits LEF abstracts from primitive layouts and structural Verilog netlists from hdl21 circuit descriptions. Already works via `flow/layout/serialize.py` and `vlsirtools.netlist`. Don't touch the core; extend with new emitters only.

2. **Constraint language (new: `flow/constraint/`)** — Python dataclasses modeled on hdl21+ALIGN syntax that capture analog placement/routing intent (symmetry pairs, net groups, ordering, routing rules). Tool-neutral; no OpenROAD semantics leak in.

3. **TCL generation (new: `flow/openroad/`)** — Takes VLSIR artifacts (LEF, Verilog, DEF) plus constraint objects and emits a self-contained `.tcl` script that OpenROAD can `source`. The Python side's job ends once the TCL is written.

```
┌─────────────────────────────────────────────────────────────────────┐
│  Python generator side                                              │
│                                                                     │
│  hdl21 Module ──► h.to_proto() ──► vlsirtools ──► structural .v     │
│                                                                     │
│  KLayout primitive ──► export_layout() ──► vlsir.raw ──► .lef       │
│                                    ▲                                │
│                              (new emitter)                          │
│                                                                     │
│  Constraint objects ──► tcl_emitter() ──► flow.tcl                  │
│         ▲                                                           │
│    (new module)                                                     │
└──────────────────────────────┬──────────────────────────────────────┘
                               │ files on disk
                               ▼
┌─────────────────────────────────────────────────────────────────────┐
│  OpenROAD                                                           │
│                                                                     │
│  source flow.tcl                                                    │
│    ├── read_lef tech.lef                                            │
│    ├── read_lef {prim1.lef prim2.lef ...}                           │
│    ├── read_verilog design.v                                        │
│    ├── read_def design.def  (or initialize_floorplan)               │
│    ├── [placement passes with locks, net weights, partitioning]     │
│    ├── [routing passes with NDRs, guide mirroring, net subsets]     │
│    └── write_def placed_routed.def                                  │
└─────────────────────────────────────────────────────────────────────┘
```

The partitioned placement/routing strategy (from Wei's ALOE thesis) maps to
sequences of TCL `place` / `route` commands that select subsets of instances
and nets, not to a Python sidecar running alongside OpenROAD.

---

## Component 1: Constraint Language (`flow/constraint/`)

Python-native constraint vocabulary. References hdl21 instance names and signal
names as plain strings. Modeled on ALIGN's schema (`SymmetricBlocks`,
`SymmetricNets`, `GroupBlocks`, `Order`, etc.) and Fritchman Ch. 7 priorities,
with hard/soft strength and integer priority.

Does NOT live in VLSIR proto yet — that's a future step once the flow is proven.

### Files

- [ ] `flow/constraint/__init__.py` — Public API re-exports
- [ ] `flow/constraint/types.py` — All constraint dataclasses and enums

### Enums

- [ ] `Strength` — `HARD`, `SOFT`
- [ ] `SymmetryAxis` — `VERTICAL`, `HORIZONTAL`
- [ ] `OrderDirection` — `LEFT_TO_RIGHT`, `BOTTOM_TO_TOP`
- [ ] `AlignEdge` — `LEFT`, `RIGHT`, `TOP`, `BOTTOM`, `CENTER_H`, `CENTER_V`
- [ ] `PortSide` — `LEFT`, `RIGHT`, `TOP`, `BOTTOM`

### Placement Constraint Dataclasses

Each is a frozen dataclass with `strength: Strength = HARD` and `priority: int = 0`.

- [ ] `SymmetricBlocks` — Paired instance placement across a symmetry axis
  - `pairs: list[tuple[str, str]]` — Instance name pairs (e.g. `("mdiff_p", "mdiff_n")`)
  - `axis: SymmetryAxis = VERTICAL`
- [ ] `SelfSymmetric` — Single instance that must be symmetric about its own axis
  - `instance: str`
  - `axis: SymmetryAxis = VERTICAL`
- [ ] `GroupBlocks` — Virtual hierarchy / placement group
  - `name: str` — Group name (e.g. `"preamp"`, `"latch"`)
  - `instances: list[str]` — Instance names in the group
- [ ] `GroupCaps` — Common-centroid / interdigitated capacitor group
  - `name: str`
  - `instances: list[str]`
  - `num_units: list[int]` — Per-instance unit count ratios
  - `dummy: bool = True`
- [ ] `Order` — Relative placement ordering
  - `instances: list[str]` — Ordered list
  - `direction: OrderDirection = BOTTOM_TO_TOP`
- [ ] `Align` — Edge/center alignment
  - `instances: list[str]`
  - `edge: AlignEdge`
- [ ] `Floorplan` — Row or column arrangement
  - `rows: list[list[str]]` — Each inner list is a row of instance names
- [ ] `Boundary` — Explicit block boundary
  - `width_nm: int`
  - `height_nm: int`
- [ ] `AspectRatio` — Aspect ratio bounds
  - `min_ratio: float = 0.5`
  - `max_ratio: float = 2.0`
- [ ] `PlaceOnGrid` — Grid legalization for an instance
  - `instance: str`
  - `grid_x_nm: int`
  - `grid_y_nm: int`
- [ ] `FixedPlacement` — Lock instance at absolute coordinates
  - `instance: str`
  - `x_nm: int`
  - `y_nm: int`
  - `orientation: str = "N"` — LEF/DEF orientation string (N, S, FN, FS, etc.)
- [ ] `Distance` — Min/max distance between two instances
  - `inst_a: str`
  - `inst_b: str`
  - `min_nm: int | None = None`
  - `max_nm: int | None = None`
- [ ] `GuardRing` — Guard ring around a group
  - `instances: list[str]`
  - `ring_type: str = "substrate"` — `"substrate"` or `"nwell"`

### Routing Constraint Dataclasses

- [ ] `SymmetricNets` — Net pairs that must route symmetrically
  - `nets: list[tuple[str, str]]` — Net name pairs
  - `axis: SymmetryAxis = VERTICAL`
- [ ] `RouteConstraint` — Per-net routing rules
  - `nets: list[str]`
  - `min_layer: str | None = None` — e.g. `"M2"`
  - `max_layer: str | None = None` — e.g. `"M4"`
  - `width_mult: int = 1` — Width multiplier for NDR
  - `spacing_mult: int = 1` — Spacing multiplier for NDR
  - `shield_net: str | None = None`
- [ ] `NetPriority` — Criticality / routing order
  - `nets: list[str]`
  - `priority: int` — Higher = route first
- [ ] `MultiConnection` — Multi-wire / multi-via intent
  - `nets: list[str]`
  - `width_mult: int = 2`
- [ ] `DoNotRoute` — Nets that OpenROAD must not touch
  - `nets: list[str]`
- [ ] `PortLocation` — Pin placement on block boundary
  - `port: str`
  - `side: PortSide`
  - `layer: str | None = None`

### Container Dataclasses

- [ ] `ModuleConstraints` — All constraints for one hdl21 Module
  - `module: str` — Module name (matches hdl21 `Module.name`)
  - `constraints: list[Constraint]`
  - Method: `validate(module: h.Module) -> list[str]` — Check instance/signal names exist
- [ ] `ConstraintLibrary` — Collection across multiple modules
  - `domain: str`
  - `modules: list[ModuleConstraints]`

### Constraint type union

- [ ] `Constraint` — Type alias: `Union[SymmetricBlocks, SelfSymmetric, GroupBlocks, ...]`

### Tests

- [ ] `flow/constraint/test_types.py`
  - [ ] Construct each constraint type, verify fields
  - [ ] Build `ModuleConstraints` for the comparator (`flow/comp/subckt.py`)
  - [ ] `validate()` against a real `Comp` module — confirm instance names match
  - [ ] `validate()` with a bad instance name — confirm error is reported
  - [ ] Verify `Strength` and `priority` defaults

---

## Component 2: VLSIR Emitters (`flow/layout/` extensions)

Convert existing VLSIR raw protos and hdl21 packages into the three file formats
OpenROAD needs: LEF, structural Verilog, and DEF. Two of these three already
have working implementations in our `libs/` dependencies:

- **LEF**: Layout21 (`libs/Layout21`) already has the full pipeline:
  `vlsir.raw.proto` → `layout21raw::Library` (via `ProtoImporter`) →
  `lef21::LefLibrary` (via `LefExporter`) → `.lef` file (via `LefLibrary::save()`).
  The code lives in `layout21raw/src/proto.rs` (proto↔layout21 conversion) and
  `layout21raw/src/lef.rs` (layout21→LEF export with Abstract/port/blockage support).

- **Structural Verilog**: `vlsirtools` (`libs/Vlsir/VlsirTools`) already has a
  `VerilogNetlister` in `vlsirtools/netlist/verilog.py` that emits structural
  Verilog from `vlsir.circuit.Package`. Frida already uses this — the CLI
  supports `flow netlist -c comp -f verilog` and `run_netlist_variants()` in
  `flow/circuit/netlist.py` handles the `fmt="verilog"` path.

So the work here is NOT reimplementing LEF/Verilog emitters from scratch.
Instead it is: (a) ensuring the primitive generators populate `vlsir.raw.Abstract`
correctly so Layout21's LEF exporter has the data it needs, (b) writing a thin
Python wrapper that shells out to the Layout21 Rust binary or calls it via a
compiled CLI, (c) writing a tech LEF emitter (which Layout21 does NOT cover —
`lef21` handles macro LEF only, not technology LEF), and (d) writing a minimal
DEF seed file.

### 2a. Primitive Abstract Annotation

The existing `mosfet()` and `momcap()` generators emit GDS-layer shapes and
PIN-layer markers, but they do NOT populate `vlsir.raw.Cell.abstract`. The
`export_layout()` path in `flow/layout/serialize.py` only fills
`vlsir.raw.Cell.layout`, not `vlsir.raw.Cell.abstract`. Layout21's LEF
exporter (`LefExporter`) only exports cells that have `.abs` — cells with
only `.layout` are silently skipped.

- [ ] Extend `flow/layout/serialize.py` — `layout_to_vlsir_raw()`
  - [ ] After building `raw_layout`, also build `raw.Abstract` for each cell:
    - [ ] Derive `outline` polygon from the cell's bounding box
    - [ ] Identify PIN-layer shapes (e.g. layer 10/datatype 1 = `PIN1`) and
          group them by associated text label to form `AbstractPort` entries
    - [ ] Collect all non-pin drawing-layer shapes as `blockages`
    - [ ] Populate `vlsir.raw_pb2.Cell.abstract` alongside `.layout`
  - [ ] Alternatively, add a new function `build_abstract(cell, layout, G) -> raw.Abstract`
        that the generators call explicitly

#### Key decisions

- Pin names come from text labels on the PIN layer. The mosfet generator
  currently does NOT emit text labels on PIN layers — it only inserts boxes.
  We either need to add text labels in the generators, or infer pin names
  from position (less robust).
- [ ] Add pin-name text labels to `mosfet()` generator on each PIN-layer shape
- [ ] Add pin-name text labels to `momcap()` generator on each PIN-layer shape

#### Tests

- [ ] `flow/layout/test_serialize.py` (extend existing `test_serialize`)
  - [ ] Generate mosfet → `export_layout()` → verify `Cell.abstract` is populated
  - [ ] Verify `Abstract.ports` has correct pin names (vss, vdd, gate, drain)
  - [ ] Verify `Abstract.outline` matches cell bounding box
  - [ ] Verify `Abstract.blockages` contains non-pin drawing-layer shapes

### 2b. LEF Generation via Layout21

Use Layout21's existing Rust pipeline to convert `vlsir.raw.pb` (with Abstract
populated per §2a) to `.lef` files. This is a Rust binary invocation, not a
Python reimplementation.

- [ ] Build Layout21 workspace: `cargo build --release` in `libs/Layout21/`
  - [ ] Verify `proto2gds` binary builds (confirms proto support compiles)
  - [ ] Write or identify a CLI entry point for `proto2lef` conversion
    - Layout21 does NOT currently ship a `proto2lef` binary. The pieces exist
      (`ProtoImporter` + `LefExporter`) but there is no CLI wiring them together.
    - [ ] Option A: Add a small `proto2lef.rs` binary to `layout21converters/src/bin/`
          that reads a `vlsir.raw.Library` protobuf file, imports it via
          `ProtoImporter`, exports via `LefExporter`, and saves via `LefLibrary::save()`
    - [ ] Option B: Write a thin Rust `cdylib` with a C FFI that Python calls via `ctypes`
    - [ ] Option C: Write a standalone Python LEF text emitter that reads the
          `vlsir.raw_pb2` protobuf directly (fallback if Rust compilation is impractical)
  - Recommendation: Option A is simplest. ~30 lines of Rust.

- [ ] `flow/layout/lef.py` — Python wrapper
  - [ ] `proto_to_lef(pb_path: Path, lef_path: Path) -> Path`
    - Calls the `proto2lef` binary via `subprocess.run()`
    - Validates output file exists
  - [ ] `emit_primitives_lef(primitives: list[Path], out: Path) -> Path`
    - Takes a list of `.raw.pb` files from primitive generation
    - Concatenates or merges into a single macro LEF
    - Returns path to the output `.lef`

- [ ] Tech LEF emitter (Layout21/lef21 do NOT handle this — it's macro-only)
  - [ ] `emit_tech_lef(rule_deck: NewRuleDeck, tech_name: str, out: Path) -> Path`
    - Emit `UNITS DATABASE MICRONS ...`
    - Emit `MANUFACTURINGGRID`
    - Emit `LAYER` definitions from rule deck (name, type, direction, pitch, width, spacing)
    - Emit `VIA` definitions from rule deck (cut layer + enclosures)
    - Emit `VIARULE GENERATE` definitions
    - Emit `SITE` definition (width = track pitch, height = row height)
    - This is pure Python string formatting — tech LEF is a simple text format

#### Tests

- [ ] `flow/layout/test_lef.py`
  - [ ] Generate a mosfet layout → `export_layout()` (with Abstract) → `proto_to_lef()`
        → verify output `.lef` file exists and contains `MACRO`, `PIN`, `OBS` keywords
  - [ ] Generate a momcap layout → same flow → verify LEF
  - [ ] `emit_tech_lef()` from ihp130 rule deck → verify `LAYER` names match
        rule deck entries, pitches/widths are correct in micron units
  - [ ] Verify tech LEF `UNITS` and `MANUFACTURINGGRID` are present

### 2c. Structural Verilog via vlsirtools

The `VerilogNetlister` in `vlsirtools/netlist/verilog.py` already emits
structural Verilog from `vlsir.circuit.Package`. The frida path is:

```
hdl21 Module → h.to_proto() → vlsir.circuit.Package → vlsirtools.netlist(pkg, fmt='verilog') → .v
```

This already works and is already wired into `flow/circuit/netlist.py`'s
`run_netlist_variants(netlist_fmt="verilog")` path.

**However**, the existing Verilog output assumes all instances resolve to
modules defined within the same package. For the OpenROAD flow, compiled
device instances (post `pdk.compile()`) reference PDK `ExternalModule`s that
are NOT in the package. The `VerilogNetlister` treats unresolved references
as errors.

- [ ] Investigate `VerilogNetlister` behavior with compiled PDK devices
  - [ ] Test: compile a `Comp` module with ihp130, call `h.to_proto()`,
        call `vlsirtools.netlist(pkg, fmt='verilog')` — does it succeed or error?
  - [ ] If it errors on unresolved `ExternalModule` references:
    - [ ] Option A: Add stub module definitions to the package for each
          unique `ExternalModule` (matching LEF macro pin names)
    - [ ] Option B: Patch `VerilogNetlister` to emit `ExternalModule` references
          as black-box instantiations (the module is defined by LEF, not Verilog)
    - Recommendation: Option A — keep vlsirtools unmodified; add stubs in the
      frida integration layer

- [ ] `flow/layout/verilog.py` — Thin wrapper (only if stub injection is needed)
  - [ ] `emit_structural_verilog(module: h.Module, stem_cell_map: dict[str, str], out: Path) -> Path`
    - `stem_cell_map`: maps hdl21 `ExternalModule` qualified names → LEF macro names
    - Calls `h.to_proto()`, injects stub module defs for external modules, then
      calls `vlsirtools.netlist()` with `fmt='verilog'`
    - If no stubs needed, this is just a thin convenience function

#### Key decisions

- The **stem cell map** connects hdl21's `ExternalModule` world (where a
  compiled NMOS is e.g. `pdk.ihp130.NMOS`) to the LEF macro name
  (`MOSFET_nf4_w1_l1_...`). This mapping is built by the user or by the
  layout sweep — it says "this parameterized device instance uses this
  specific LEF cell."
- Port ordering in the Verilog must match LEF pin names exactly.
- Power/ground nets (`vdd`, `vss`) are explicit wires, not implicit globals.

#### Tests

- [ ] `flow/layout/test_verilog.py`
  - [ ] Build a `Comp` module, compile with ihp130 PDK, emit structural Verilog
        via the existing `vlsirtools` path, verify output `.v` file is syntactically valid
  - [ ] Verify all instance names from the hdl21 module appear in the Verilog
  - [ ] Verify all port names appear as `input`/`output`/`inout`
  - [ ] Verify all internal signals appear as `wire`
  - [ ] If stem cell map injection is needed: verify substituted module names
        match the LEF macro names

### 2d. DEF Seed File (Minimal)

Creates an initial DEF file with the design header, die area, and component
list (all instances UNPLACED). OpenROAD reads this as the starting point.
This is simple enough to emit directly as text — no library needed.

Alternatively, this can be omitted entirely if the TCL script uses
`initialize_floorplan` instead of `read_def`. OpenROAD can derive the
initial placement from just LEF + Verilog + floorplan commands.

- [ ] `flow/layout/def_writer.py`
  - [ ] `emit_initial_def(module_name: str, instances: list[tuple[str, str]], die_area: tuple[int,int,int,int] | None, out: Path) -> Path`
    - Emit `VERSION`, `DESIGN`, `UNITS`
    - Emit `DIEAREA` if provided, otherwise omit (let `initialize_floorplan` handle it)
    - Emit `COMPONENTS` section: each instance with `UNPLACED` status
    - Emit empty `PINS`, `NETS` sections (OpenROAD populates from Verilog)
  - [ ] Or: skip this entirely and use `initialize_floorplan` in TCL script (§3)

#### Tests

- [ ] `flow/layout/test_def_writer.py`
  - [ ] Emit a DEF for a small design, verify it parses (regex check on sections)
  - [ ] Verify component count matches input

---

## Component 3: TCL Generation (`flow/openroad/`)

Translates constraint objects + file paths into a complete OpenROAD TCL script.
This is the experimental component. No VLSIR dependency — it consumes
constraint dataclasses and emits text.

### Files

- [ ] `flow/openroad/__init__.py` — Public API
- [ ] `flow/openroad/tcl_emitter.py` — Core TCL generation logic
- [ ] `flow/openroad/tcl_fragments.py` — Helper functions that emit individual TCL command strings

### `tcl_fragments.py` — Low-level TCL command builders

Each function returns a `list[str]` of TCL lines. No file I/O.

#### Design Setup

- [ ] `read_design(tech_lef: str, macro_lefs: list[str], verilog: str, def_file: str | None) -> list[str]`
  - `read_lef`, `read_verilog`, `read_def` or `initialize_floorplan`
- [ ] `write_result(def_out: str) -> list[str]`
  - `write_def`

#### Floorplanning

- [ ] `init_floorplan(aspect_ratio: float, utilization: float, die_area: tuple | None) -> list[str]`
  - `initialize_floorplan -aspect_ratio ... -utilization ...`
  - Or `initialize_floorplan -die_area {x0 y0 x1 y1} -site ...`
- [ ] `make_tracks(rule_deck_summary: dict) -> list[str]`
  - `make_tracks` for each metal layer with correct offset and pitch
- [ ] `pin_placement(constraints: list[PortLocation]) -> list[str]`
  - `set_io_pin_constraint -pin_names ... -region ...`

#### Placement

- [ ] `lock_instance(inst: str, x: int, y: int, orient: str) -> list[str]`
  - TCL block: `set inst [$block findInst "<inst>"]`; `$inst setLocation ...`; `$inst setPlacementStatus LOCKED`
- [ ] `set_net_weight(net: str, weight: float) -> list[str]`
  - `createNetGroup` + `specifyNetWeight` (Wei ALOE approach)
- [ ] `global_placement(density: float, overflow: float) -> list[str]`
  - `global_placement -density ... -overflow ...`
- [ ] `detail_placement() -> list[str]`
  - `detailed_placement` + `check_placement -verbose`

#### NDR / Routing Setup

- [ ] `create_ndr(name: str, layers: list[str], width_mult: int, spacing_mult: int) -> list[str]`
  - `add_ndr -name ... -width_multiplier {layer mult ...} -spacing_multiplier {layer mult ...}`
- [ ] `assign_ndr(net: str, ndr_name: str) -> list[str]`
  - `setAttribute -net ... -non_default_rule ...`

#### Routing

- [ ] `set_routing_layers(signal_min: str, signal_max: str) -> list[str]`
  - `set_routing_layers -signal <min>-<max>`
- [ ] `global_route(guide_file: str | None) -> list[str]`
  - `global_route` with optional `-guide_file`
- [ ] `detail_route() -> list[str]`
  - `detailed_route`
- [ ] `route_net_subset(nets: list[str]) -> list[str]`
  - `set_nets_to_route -nets {net1 net2 ...}` + `global_route` + `detailed_route`
  - This is the partitioned routing mechanism

#### Symmetric Routing Workaround

- [ ] `mirror_guides_comment_block(net_a: str, net_b: str, axis_x: int) -> list[str]`
  - Emit a commented TCL procedure skeleton that documents the guide-mirroring
    approach (extract guides from `net_a`, mirror X coordinates about `axis_x`,
    apply to `net_b`).
  - This is not fully automatable in pure TCL — it's a placeholder for the
    approach described in `or_analog.md` lines 278–326.
  - Mark with `# TODO: requires custom ODB scripting or Python API session`

### `tcl_emitter.py` — High-level orchestrator

- [ ] `class OpenROADScript`
  - Constructor: `(tech_lef: str, macro_lefs: list[str], verilog: str, def_file: str | None, output_def: str)`
  - Method: `add_constraints(mc: ModuleConstraints)` — Absorbs constraint objects
  - Method: `emit(out: Path) -> Path` — Writes the complete `.tcl` file

#### `emit()` logic — the TCL script structure

The generated TCL script has this sequential structure:

```tcl
# ── 1. Design Read ──
read_lef ...
read_verilog ...
read_def ... / initialize_floorplan ...

# ── 2. Track Setup ──
make_tracks ...

# ── 3. Pin Placement ──
set_io_pin_constraint ...

# ── 4. Fixed Placements (from FixedPlacement constraints) ──
# Lock symmetric-pair center instances, guard ring anchors, etc.

# ── 5. NDR Setup (from RouteConstraint constraints) ──
add_ndr ...
setAttribute -net ... -non_default_rule ...

# ── 6. Net Weights (from NetPriority + RouteConstraint) ──
createNetGroup ...
specifyNetWeight ...

# ── 7. Global Placement ──
global_placement ...

# ── 8. Detail Placement ──
detailed_placement
check_placement

# ── 9. Global Routing ──
global_route ...

# ── 10. Detail Routing ──
detailed_route

# ── 11. Output ──
write_def ...
```

#### Constraint → TCL mapping

Each constraint type maps to specific TCL command(s) inserted at the right
stage of the script:

| Constraint | TCL Stage | TCL Commands |
|---|---|---|
| `FixedPlacement` | §4 | `findInst` → `setLocation` → `setPlacementStatus LOCKED` |
| `SymmetricBlocks` | §4 | Lock one instance, compute mirror position, lock the other |
| `SelfSymmetric` | §4 | Lock instance centered on symmetry axis |
| `GroupBlocks` | §6 | Comment annotation (OpenROAD has no native group placement) |
| `Order` | §4 | Compute stacked positions, lock each instance |
| `Align` | §4 | Compute aligned positions, lock each instance |
| `Boundary` | §2 | `initialize_floorplan -die_area ...` |
| `AspectRatio` | §2 | `initialize_floorplan -aspect_ratio ...` |
| `PortLocation` | §3 | `set_io_pin_constraint -pin_names ... -region ...` |
| `RouteConstraint` | §5 | `add_ndr` + `setAttribute -net ...` |
| `NetPriority` | §6 | `specifyNetWeight` |
| `MultiConnection` | §5 | NDR with higher width multiplier |
| `DoNotRoute` | §9 | Omit nets from `set_nets_to_route` |
| `SymmetricNets` | §9–10 | Comment block documenting guide-mirror approach |
| `GuardRing` | §4 | Comment annotation (manual geometry, not OpenROAD native) |
| `GroupCaps` | §4 | Comment annotation (common-centroid is generator-level) |
| `Distance` | — | Validation-only; no direct TCL mapping |

### Tests

- [ ] `flow/openroad/test_tcl.py`
  - [ ] Build `ModuleConstraints` for the comparator with representative constraints
  - [ ] Emit TCL script to a string, verify it contains expected commands
  - [ ] Verify `read_lef` / `read_verilog` appear at the top
  - [ ] Verify `FixedPlacement` emits `setLocation` + `LOCKED`
  - [ ] Verify `RouteConstraint` emits `add_ndr` with correct layer/multiplier args
  - [ ] Verify `NetPriority` emits `specifyNetWeight`
  - [ ] Verify `DoNotRoute` nets are excluded from routing commands
  - [ ] Verify `write_def` appears at the end
  - [ ] Verify the script is valid TCL syntax (no unclosed braces/brackets)

---

## Component 4: End-to-End Integration

### 4a. Comparator Example (`flow/comp/layout.py`)

Wire up all three components for the comparator as a proof-of-concept.

- [ ] `flow/comp/layout.py`
  - [ ] Define `comp_constraints(p: CompParams) -> ModuleConstraints`
    - `SymmetricBlocks` for the diff pair (`mdiff_p` / `mdiff_n`)
    - `SymmetricBlocks` for load/reset devices (`mrst_p` / `mrst_n`)
    - `SymmetricBlocks` for latch cross-coupled pairs (`ma_p`/`ma_n`, `mb_p`/`mb_n`)
    - `SymmetricNets` for internal differential signals (`outp_int` / `outn_int`)
    - `Order` for vertical stacking: tail → diffpair → loads
    - `GroupBlocks` for preamp vs latch functional groups
    - `RouteConstraint` for differential outputs (wider wires, mid-layer routing)
    - `NetPriority` for clock and differential signal nets
  - [ ] Define `stem_cell_map(p: CompParams, tech: str) -> dict[str, str]`
    - Maps each compiled `ExternalModule` to the corresponding LEF macro name
    - This requires the primitive layout sweep to have run first
  - [ ] Define `run_openroad_prep(p: CompParams, tech: str, outdir: Path) -> Path`
    - Generate primitive layouts → emit LEF (one per unique device parameterization)
    - Emit tech LEF from rule deck
    - Build and compile the `Comp` module → emit structural Verilog
    - Emit initial DEF (optional — can let `initialize_floorplan` handle it)
    - Build constraints → emit TCL script
    - Return path to the generated `.tcl` file

#### Tests

- [ ] `flow/comp/test_layout.py`
  - [ ] `run_openroad_prep` produces all expected files in output directory:
    `tech.lef`, `*.macro.lef`, `comp.v`, `flow.tcl`
  - [ ] Constraint validation passes against the compiled `Comp` module
  - [ ] Generated TCL script references the correct LEF and Verilog filenames

### 4b. CLI Extension

- [ ] Extend `flow/cli.py` with a new `openroad` subcommand:
  ```
  flow openroad -c comp -t ihp130 -o scratch/
  ```
  - Calls `run_openroad_prep()` to generate all input files
  - Prints summary: file paths, constraint count, stem cell count
  - Does NOT run OpenROAD (that's manual: `openroad scratch/flow.tcl`)

---

## Execution Order and Dependencies

```
Phase 0: Verify existing tools work (no code changes — just testing)
  ├── Compile Layout21: cargo build --release in libs/Layout21/
  ├── Test vlsirtools verilog: flow netlist -c comp -t ihp130 -f verilog
  └── Identify any gaps (ExternalModule handling, missing proto2lef binary)

Phase 1: Constraint types (no dependencies)
  └── flow/constraint/types.py
  └── flow/constraint/__init__.py
  └── flow/constraint/test_types.py

Phase 2a: Primitive abstract annotation (depends on existing flow/layout/)
  ├── Add pin-name text labels to mosfet/momcap generators
  ├── Extend layout_to_vlsir_raw() to populate Cell.abstract
  └── Tests: verify Abstract is populated with ports/outline/blockages

Phase 2b: LEF pipeline (depends on Phase 2a + Layout21 compilation)
  ├── proto2lef.rs binary in libs/Layout21/ (~30 lines Rust)
  ├── flow/layout/lef.py (Python subprocess wrapper + tech LEF emitter)
  └── flow/layout/test_lef.py

Phase 2c: Verilog investigation (depends on existing vlsirtools)
  ├── Test VerilogNetlister with compiled PDK devices
  ├── flow/layout/verilog.py (stub injection wrapper, if needed)
  └── flow/layout/test_verilog.py

Phase 2d: DEF seed (optional, can be deferred)
  └── flow/layout/def_writer.py + test

Phase 3: TCL generation (depends on Phase 1 constraint types)
  ├── flow/openroad/tcl_fragments.py
  ├── flow/openroad/tcl_emitter.py
  └── flow/openroad/test_tcl.py

Phase 4: Integration (depends on Phases 1–3)
  ├── flow/comp/layout.py
  ├── flow/comp/test_layout.py
  └── cli.py extension
```

Phase 0 is pure investigation — no code, just build & test existing tools.
Phases 1 and 2a–2d are independent of each other and can proceed in parallel
(except 2b depends on 2a).
Phase 3 requires Phase 1.
Phase 4 requires all of Phases 1–3.

---

## What This Plan Does NOT Cover (Future Work)

These are explicitly out of scope for the first implementation:

- [ ] **`vlsir.constraints` proto** — The constraint types live as Python dataclasses
  for now. Promoting them to a `.proto` schema in `Vlsir/protos/constraints.proto`
  happens only after the flow is proven to work end-to-end.

- [ ] **Partitioned placement/routing via evolutionary algorithm** — Wei's ALOE uses
  an EA to drive net weights and then rank layouts by post-PEX simulation. The TCL
  emitter supports net weights as a knob, but the EA loop is a separate concern.

- [ ] **DEF → GDS back-annotation** — Reading the placed+routed DEF back into VLSIR
  `tetris.proto` or `raw.proto` for GDS export / DRC checking in KLayout.

- [ ] **UPF / power domain integration** — The `or_analog.md` UPF section is relevant
  for mixed-signal SoC integration, not for the analog block P&R itself.

- [ ] **Automatic stem-cell-map generation** — Automatically matching hdl21 compiled
  device parameters to pre-generated LEF cells. For now this map is manual.

- [ ] **KLayout DRC/LVS integration** — Checking the OpenROAD output against PDK
  rules via KLayout's DRC engine.

- [ ] **Multi-block hierarchical constraint propagation** — The ALIGN `translator.py`
  pattern of propagating constraints through hierarchy. Start flat, add hierarchy later.

- [ ] **Python bindings for Layout21** — Layout21 is pure Rust today. A `pyo3` or
  `ctypes` bridge would eliminate the subprocess call for `proto2lef`, but is not
  needed for a first pass.

---

## File Summary

New files to create:

| File | Purpose | LoC est. |
|---|---|---|
| `flow/constraint/__init__.py` | Public API | ~60 |
| `flow/constraint/types.py` | All constraint dataclasses | ~250 |
| `flow/constraint/test_types.py` | Unit tests for constraints | ~120 |
| `flow/layout/lef.py` | Tech LEF emitter + Layout21 subprocess wrapper | ~200 |
| `flow/layout/test_lef.py` | LEF pipeline tests | ~150 |
| `flow/layout/verilog.py` | Stem-cell-map stub injector (if needed) | ~80 |
| `flow/layout/test_verilog.py` | Verilog output tests | ~100 |
| `flow/layout/def_writer.py` | Initial DEF emitter (optional) | ~80 |
| `flow/layout/test_def_writer.py` | DEF emitter tests | ~60 |
| `flow/openroad/__init__.py` | Public API | ~20 |
| `flow/openroad/tcl_fragments.py` | Individual TCL command builders | ~300 |
| `flow/openroad/tcl_emitter.py` | High-level script orchestrator | ~250 |
| `flow/openroad/test_tcl.py` | TCL generation tests | ~200 |
| `flow/comp/layout.py` | Comparator integration example | ~150 |
| `flow/comp/test_layout.py` | Integration tests | ~100 |
| `libs/Layout21/.../proto2lef.rs` | Proto-to-LEF CLI binary | ~30 |
| **Total** | | **~2150** |

Files to modify:

| File | Change |
|---|---|
| `flow/layout/serialize.py` | Populate `Cell.abstract` in `layout_to_vlsir_raw()` (~60 lines) |
| `flow/mosfet/primitive.py` | Add pin-name text labels on PIN layers (~10 lines) |
| `flow/momcap/primitive.py` | Add pin-name text labels on PIN layers (~10 lines) |
| `flow/cli.py` | Add `openroad` subcommand (~30 lines) |

Existing code reused (NOT reimplemented):

| Existing code | Location | What it provides |
|---|---|---|
| `VerilogNetlister` | `libs/Vlsir/VlsirTools/vlsirtools/netlist/verilog.py` | Structural Verilog from `vlsir.circuit.Package` |
| `ProtoImporter` | `libs/Layout21/layout21raw/src/proto.rs` | `vlsir.raw.proto` → `layout21raw::Library` |
| `LefExporter` | `libs/Layout21/layout21raw/src/lef.rs` | `layout21raw::Library` (with `Abstract`) → `lef21::LefLibrary` |
| `LefLibrary::save()` | `libs/Layout21/lef21/src/write.rs` | `lef21::LefLibrary` → `.lef` file on disk |