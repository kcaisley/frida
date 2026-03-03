# Analog OpenROAD (AOR) — Manual Test Directory

## Purpose

This directory contains **hand-written input files** for testing OpenROAD's
analog placement and routing capabilities with FRIDA's comparator design.

The goal is to verify — by hand — that the file formats and TCL commands we
plan to auto-generate will actually work before building the generator.
These files represent the **end target** of the `flow/openroad/` TCL emitter:
if `openroad flow.tcl` runs successfully here, we know what to aim for.

## Status

**Experimental / temporary.** Once the automated flow (`plan.md` Phases 1–4)
is implemented, these hand-written files become redundant. Keep them around as
a reference and regression test.

## Files

| File | What it is | How it was made |
|---|---|---|
| `sg13g2_tech.lef` | IHP SG13G2 technology LEF | Copied verbatim from `libs/IHP-Open-PDK/ihp-sg13g2/libs.ref/sg13g2_stdcell/lef/sg13g2_tech.lef` |
| `sg13g2_macros.lef` | Macro LEF for `sg13_lv_nmos` / `sg13_lv_pmos` | Hand-written from mosfet generator bbox and PIN1-layer shapes |
| `comp.v` | Structural Verilog netlist of the Strong-ARM comparator | Generated via `vlsirtools.VerilogNetlister` from `hdl21 Comp(CompParams())` compiled with ihp130, then hand-edited to fix `NONE`-direction ports → `inout` and simplify the module name hash |
| `flow.tcl` | OpenROAD TCL script: read → floorplan → place → route → write DEF | Hand-written, modeling what `flow/openroad/tcl_emitter.py` should eventually produce |
| `notes.md` | This file | |

## How to run

```sh
# OpenROAD is installed at /usr/local/bin/openroad
# (built from ~/libs/OpenROAD/build)
openroad design/aor/flow.tcl
```

The script will attempt to:
1. Read tech LEF + macro LEF + Verilog
2. Initialize a 30×30 µm floorplan
3. Place all 15 transistor instances at hand-computed symmetric positions (LOCKED)
4. Run global + detailed routing on Metal1–Metal5
5. Write `comp_placed_routed.def`

## Known issues to investigate

- **Macro LEF is simplified.** The real primitives have FEOL layers (OD, PO,
  CO, implants) inside them. The hand-written LEF only has Metal1 pins and a
  full-cell Metal1 obstruction. This may cause routing to fail if OpenROAD
  cannot find legal access points.

- **No SITE definition in macro LEF.** OpenROAD may complain about missing
  site for `initialize_floorplan`. The `-site unit` flag is a placeholder.

- **No liberty (.lib) file.** OpenROAD's NDR and net-weight commands may
  require timing data. We don't have timing — these are analog blocks.
  The NDR section in `flow.tcl` is commented out for this reason.

- **Port direction fixup.** `hdl21` emits `h.Port()` (direction=NONE) for
  `vdd`/`vss`, which `VerilogNetlister` rejects. The automated flow needs
  a wrapper that patches NONE → INOUT before calling vlsirtools.

- **Module name hash.** `vlsirtools` appends a parameter hash to the module
  name (e.g. `Comp_d070292453746f93412a800dbc7e00cd_`). The automated flow
  needs to either control this or use `link_design` with the hashed name.

- **Parametric instances.** The auto-generated Verilog includes `#(.w(...), .l(...))`
  parameter overrides on each instance. OpenROAD's Verilog reader may not
  handle these — it expects each parametric variant to be a distinct LEF macro.
  The hand-written `comp.v` strips these out. The real flow must map each
  unique parameter combination to a separate macro name.

- **Symmetric routing.** OpenROAD has no native support. The guide-mirror
  workaround (documented in `docs/or_analog.md` §Symmetric Routing) requires
  Python ODB scripting and cannot be expressed in pure TCL. The `flow.tcl`
  leaves this as a TODO comment block.

## What this validates for the automated flow

If `openroad flow.tcl` succeeds (even partially), we confirm:

1. **LEF format**: OpenROAD can read our macro abstracts (pin names, sizes, layers)
2. **Verilog format**: OpenROAD can link the structural netlist to LEF macros
3. **TCL commands**: The placement/routing command sequence is valid
4. **Manual placement**: `setLocation` + `LOCKED` works for analog symmetry
5. **Routing feasibility**: Global + detailed routing can connect the instances

Each confirmed item means the corresponding Python emitter (`lef.py`,
`verilog.py`, `tcl_emitter.py`) has a known-good target format to generate.