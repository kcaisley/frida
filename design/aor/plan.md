# AOR Validation Plan — Get Hand-Written Files Through OpenROAD

## Goal

Get `openroad flow.tcl` to produce a clean `comp_placed_routed.def` with
zero routing violations, using only the hand-written files in this directory.
No Python code generation yet — this validates the **target format** so we
know exactly what to generate later.

## Files

| File | Role | Source |
|---|---|---|
| `sg13g2_tech.lef` | Technology LEF | Copied from IHP PDK (`libs/IHP-Open-PDK/...`) |
| `sg13g2_macros.lef` | Macro LEF for `sg13_lv_nmos` / `sg13_lv_pmos` | Hand-written from mosfet generator bbox + PIN1 shapes |
| `comp.v` | Structural Verilog netlist | Hand-written from hdl21 `Comp(CompParams())` output |
| `flow.tcl` | OpenROAD TCL script (read → place → route → write) | Hand-written |
| `gen_macros_gds.py` | Generate `sg13_lv_nmos.gds` / `sg13_lv_pmos.gds` from FRIDA mosfet generator | New — uses `flow.mosfet.primitive` with PDK layer remap |
| `sg13g2.lyt` | KLayout technology file (configures LEF/DEF reader) | Copied from ORFS `flow/platforms/ihp-sg13g2/` |
| `sg13g2.map` | LEF/DEF → GDS layer number mapping | Copied from ORFS `flow/platforms/ihp-sg13g2/` |
| `def2gds.py` | KLayout script: DEF + LEF + macro GDS → final GDS | Adapted from ORFS `flow/util/def2stream.py` |

## How to run

```sh
# 1. Generate macro GDS cells (produces sg13_lv_nmos.gds, sg13_lv_pmos.gds)
uv run python design/aor/gen_macros_gds.py

# 2. Place & route (produces comp_placed_routed.def)
openroad design/aor/flow.tcl

# 3. Convert to GDS with full cell geometry (produces comp_placed_routed.gds)
cd design/aor && klayout -zz -rm def2gds.py
```

## Tool versions

```
openroad -version   → 26Q1-954-g76bd2cf3a1
klayout -v          → KLayout 0.30.5
```

---

## Step 1: Verilog reads without error

OpenROAD must parse `comp.v` and link the design without errors.

- [x] **1a.** `endmodule // Comp` causes `STA-0164` syntax error on line 166.
  OpenROAD's Verilog reader does not accept comments after `endmodule`.
  **Fix:** changed to bare `endmodule`.

- [x] **1b.** Verilog-2001 `input wire` / `output wire` port style — confirmed
  this IS accepted by OpenROAD (tested with a minimal module). No change needed.

- [x] **1c.** After fix 1a, `read_verilog` + `link_design Comp` succeeds.
  Warnings `ORD-2011 LEF master ... has no liberty cell` are expected and
  harmless for analog (no timing).

## Step 2: Floorplan initializes

`initialize_floorplan` must succeed with the die/core area we specify.

- [x] **2a.** `-site unit` fails with `IFP-0018 Unable to find site: unit`
  because neither the tech LEF nor the macro LEF defines a SITE named `unit`.
  **Fix:** added a minimal SITE definition to `sg13g2_macros.lef`:
  ```
  SITE unit
    SYMMETRY Y ;
    CLASS CORE ;
    SIZE 0.005 BY 0.005 ;
  END unit
  ```
  The 5 nm size matches the manufacturing grid (0.005 µm). This creates a
  fine placement grid appropriate for analog (no standard-cell row constraints).

- [x] **2b.** After fix 2a, `initialize_floorplan` succeeds:
  `IFP-0001 Added 5600 rows of 5600 site unit.`

## Step 3: Pin placement succeeds

`place_pins` must assign I/O pins to the die boundary.

- [x] **3a.** Pin placement works. Warnings `PPL-0015 Macro ... is not placed`
  appear because pins are placed before instances — this is expected and
  the warnings are harmless.

## Step 4: Manual instance placement — no overlaps

All 15 instances must be placed without overlapping each other.

- [x] **4a.** Instances `mrst_p` (y=10.0) and `mlatch_rst_p` (y=10.5) overlap.
  Cell height is 3.060 µm, so the gap must be ≥ 3.060. Same for `mrst_n` /
  `mlatch_rst_n` on the right side.
  **Fix:** recomputed Y coordinates with 4.0 µm row pitch (cell_h + ~1 µm
  routing channel). Stacking from bottom:

  | Row | Instance(s) | Y (µm) |
  |---|---|---|
  | 0 | mtail (centered) | 1.0 |
  | 1 | mdiff_p, mdiff_n | 5.0 |
  | 2 | mrst_p, mrst_n | 9.0 |
  | 3 | mlatch_rst_p, mlatch_rst_n | 13.0 |
  | 4 | ma_p, ma_n | 17.0 |
  | 5 | mb_p, mb_n | 21.0 |
  | 6 | mbuf_outp_top, mbuf_outn_top | 25.0 |
  | 7 | mbuf_outp_bot, mbuf_outn_bot | 29.0 |

  Die area increased to 35 × 35 µm (row 7 top edge = 29.0 + 3.060 = 32.06;
  plus margin). Buffer inverters placed at wider X spread (±5.0 µm from axis)
  to avoid horizontal overlap with the core stack.

- [x] **4b.** Uncommented `check_placement -verbose` in `flow.tcl`. It runs
  silently — no overlap or placement violations reported.

## Step 5: Macro LEF pin access — fix off-grid pins

The detail router warns `DRT-0419 No routing tracks pass through the center
of Term ...` for nearly every pin. This means pins in the macro LEF are not
aligned to the routing grid, so the router cannot access them.

- [x] **5a.** Audited pin rectangles against Metal1 track pattern (pitch
  0.42 µm, offset 0). Original pins were 0.320 × 0.320 µm with centers
  off-grid. **Fix:** enlarged all pins to 0.420 × 0.420 µm (one full track
  pitch) so they span at least one track regardless of instance placement
  offset. New pin geometry:
  - `s`: RECT 0.000 0.000 0.420 0.420 (bottom-left, source/vss)
  - `d`: RECT 2.600 0.630 3.020 1.050 (right-side, drain)
  - `g`: RECT 0.000 1.320 0.420 1.740 (left-side, gate)
  - `b`: RECT 0.000 2.640 0.420 3.060 (top-left, bulk/vdd)

- [x] **5b.** After fix, zero `DRT-0419` warnings. All 60 macro pins have
  valid access points (`macroValidPlanarAp = 505`, `macroValidViaAp = 415`,
  `macroNoAp = 0`).

## Step 6: Reduce Metal1 OBS to avoid shorts

The macro LEF has a full-cell Metal1 OBS covering the entire cell. This
tells the router that Metal1 is blocked everywhere inside the cell, which
conflicts with the Metal1 pins (the router must route on Metal1 to reach
them but the OBS says it cannot).

- [x] **6a.** Removed the full-cell Metal1 OBS entirely from both macros.
  The cell interior is opaque to the router as a BLOCK macro anyway; the
  full-cell OBS was overly conservative and conflicted with pin access.
  Blockage count dropped from 15 to 0 in global routing
  (`GRT-0004 Blockages: 0`).

- [x] **6b.** After removing OBS, violations dropped dramatically (see Step 7).

## Step 7: Global + detail routing completes with zero violations

- [x] **7a.** Global routing completes with 0 overflow across all layers.
  Total usage 3.27% (39 / 1192 resources). 11 nets routed.

- [x] **7b.** Detail routing converges to **zero violations** in 2 iterations:
  - 0th iteration: 7 violations (6 Metal1 spacing + 1 short)
  - 1st iteration: **0 violations** ✅
  Total wire length: 349 µm (Metal1: 169, Metal2: 132, Metal3: 46).
  Total vias: 37 (33 Metal1→Via1, 4 Metal2→Via2).

- [x] **7c.** No further investigation needed — Steps 4–6 fixes resolved
  all violations. The router uses Metal1–Metal3 only (Metal4/Metal5 unused),
  indicating comfortable routing resources for this design density.

## Step 8: DEF output is written

- [x] **8a.** `write_def comp_placed_routed.def` executes. File exists
  (375 KB).

- [x] **8b.** DEF inspection confirms:
  - All 15 COMPONENTS present with `FIXED` placement status
  - 8 PINS placed on die boundary (inp, inn, outp, outn, clk, clkb, vdd, vss)
  - 11 NETS with full physical routes (ROUTED segments + vias)
  - No violations section

- [x] **8c.** DEF can be loaded back into OpenROAD for inspection (confirmed
  via re-read test — `read_def` succeeds on the output).

## Step 9: Macro GDS generation + DEF → GDS conversion

- [x] **9a.** Created `gen_macros_gds.py` to generate transistor cell GDS
  files from the FRIDA mosfet generator (`flow.mosfet.primitive`).
  Run: `uv run python design/aor/gen_macros_gds.py`
  Produces `sg13_lv_nmos.gds` (32 shapes) and `sg13_lv_pmos.gds` (32 shapes)
  with correct IHP PDK layer numbers (Active 1/0, Poly 2/0, Contact 3/0,
  NSD 4/0, PSD 5/0, NWell 6/0, Metal1 7/0, Metal1.PIN 7/1, LVTN 70/0,
  LVTP 70/1).

  **Bug found:** `flow.layout.tech.remap_layers()` has a collision bug
  when generic layer numbers equal their PDK targets (e.g. generic 1/0 OD
  → PDK 1/0 ACTIVE). It copies shapes to the same layer, then clears the
  source, deleting everything. Also fails when an intermediate target
  collides with a later source (M1 10/0→7/0, then LVTN 7/0→70/0 picks up
  the M1 shapes). Workaround: `gen_macros_gds.py` uses a two-pass remap
  via temporary offset layers (+1000). This bug should be fixed in
  `remap_layers()` itself in a future commit.

- [x] **9b.** Copied `sg13g2.lyt` (KLayout tech file) and `sg13g2.map`
  (LEF/DEF → GDS layer mapping) from ORFS IHP platform directory
  (`~/OpenROAD-flow-scripts/flow/platforms/ihp-sg13g2/`).

- [x] **9c.** Created `def2gds.py` (adapted from ORFS `flow/util/def2stream.py`).
  The script loads the KLayout tech file, injects LEF files for macro
  resolution, reads the routed DEF, merges macro GDS cells, copies the
  top cell tree to a clean layout, and writes the final GDS.
  Run: `cd design/aor && klayout -zz -rm def2gds.py`
  All parameters have defaults but can be overridden via `-rd` flags.

- [x] **9d.** Output `comp_placed_routed.gds` produced successfully.
  Contains full transistor geometry inside each macro cell (32 shapes
  each across 9 PDK layers), plus 162 routing shapes in the top cell,
  52 cell instances, and via cells (`VIA_Via1_XY`, `VIA_Via2_YX`,
  `VIA_Via1_YY`). No empty cells, no orphans.

## Step 10: Clean run end-to-end

- [x] **10a.** `openroad flow.tcl` runs from start to finish without errors,
  produces `comp_placed_routed.def`, and exits cleanly. Final detail routing
  iteration shows zero violations. Runtime < 1 second (excluding DRT memory
  allocation). Only expected warnings remain:
  - `ORD-2011` (no liberty cell — expected for analog)
  - `PPL-0015` (macros not yet placed at pin-placement time — harmless)
  - `GRT-0300` (no timing — expected for analog)
  - `DRT-0349` (LEF58_ENCLOSURE without CUTCLASS — tech LEF limitation)
  - `DRT-0290` (no DRC report path specified — optional)

- [x] **10b.** `uv run python design/aor/gen_macros_gds.py` generates macro
  GDS cells with full transistor geometry (32 shapes each).

- [x] **10c.** `klayout -zz -rm def2gds.py` converts the DEF to GDS with
  full macro cell geometry merged in. No errors, no empty cells, no orphans.

---

## Lessons Learned (for the code generator)

Record format insights here as they are discovered. These become
requirements for `flow/openroad/tcl_emitter.py` and the LEF/Verilog
emitters.

### Verilog format
- **No comments after `endmodule`.** OpenROAD's parser rejects
  `endmodule // ModuleName`. Emit bare `endmodule`.
- **Verilog-2001 port style is OK.** `input wire`, `output wire`,
  `inout wire` all accepted.
- **No parametric instances.** `#(.w(40), .l(1))` is not supported.
  Each unique parameter combination must be a distinct module name
  with a matching LEF macro. The automated flow must map hdl21
  `ExternalModule` parameterizations → unique macro names.
- **Port direction NONE → INOUT.** hdl21 `h.Port()` has no direction;
  vlsirtools rejects it. The emitter must patch to INOUT for power/ground.

### LEF format
- **SITE is required.** `initialize_floorplan -site <name>` needs a SITE
  defined in one of the LEF files. For analog, use a minimal unit SITE
  matching the manufacturing grid.
- **Pin rectangles must span routing tracks.** Pin centers must align to
  the track grid, or pins must be wide enough to cross at least one track.
  The code generator must compute pin geometry from the mosfet generator's
  PIN-layer shapes and snap/widen to the track grid.
- **OBS must not cover pins.** A full-cell Metal1 OBS blocks the router
  from accessing Metal1 pins. Either omit OBS entirely (simplest for
  analog BLOCK macros), or cut pin-sized holes.
- **No liberty file needed.** `ORD-2011` warnings about missing liberty
  are harmless for analog. Net weights and NDR can still be set without
  timing data.

### TCL commands
- **`setLocation` units are DEF database units** (microns × 1000 for
  `DATABASE MICRONS 1000`). The `expr {int($x * 1000)}` pattern works.
- **`place_pins` before instance placement** generates `PPL-0015` warnings
  (macros not yet placed) but is otherwise fine.
- **`global_placement` with all instances LOCKED** may warn about no
  movable instances. Can be skipped entirely for fully manual placement.
- **`check_placement -verbose`** should be run after placement to catch
  overlaps early, before the expensive routing step.
- **Row pitch matters.** With cell height 3.060 µm, a 4.0 µm row pitch
  (cell + ~1 µm channel) gives the router enough room. Tighter packing
  (e.g. 3.5 µm) causes overlaps and routing failures.
- **`setPlacementStatus "LOCKED"`** in TCL maps to `FIXED` in DEF output.
  Both mean the instance cannot be moved by the placer/router.

### GDS conversion
- **Macro cells need source GDS.** The DEF→GDS conversion (via KLayout)
  creates empty stub cells for LEF macros. Source GDS files must be
  merged in for the output to contain actual transistor geometry.
- **`remap_layers()` has a collision bug.** When generic layer numbers
  equal PDK target numbers, the copy-then-clear sequence deletes data.
  Use a two-pass remap (temp offset layers) as a workaround.
- **Cell names must match.** The GDS cell name must exactly match the
  LEF macro name for KLayout's merge-by-name to work.
- **ORFS `.lyt` + `.map` files** provide the LEF/DEF→GDS layer mapping.
  Copy them from the platform directory rather than hand-writing.

