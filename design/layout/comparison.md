# Layout-generator comparison: FRIDA-1 comparator in TSMC65

> The cIcCreator and laygo flows were removed on 2026-10-27: ALIGN draws every layout. This comparison is kept as the record of why.

This evaluation covers the first-generation prototypes (`gen_comp.py`, `tsmc65_post.py`, the
1.5 um laygo rows), since removed. The current flows place row cells of the standard-cell row
height in all three tools: see `pdk/tsmc65/layout/README.md` in the private PDK submodule.

Goal: build the FRIDA-1 comparator (StrongARM latch + NOR SR latch + buffers, 32
transistors, gate lengths 60/300/360/780/1020 nm) in each tool's native format, then
scale to the 296 HDL21 variants (`flow/comp/subckt.py`).

| | cIcCreator (cicpy) | laygo (hosted) | ALIGN |
|---|---|---|---|
| Native input | object `.json` + `.spi` | Python script (laygo2 API) + tech YAML | SPICE + `const.json` |
| TSMC65 tech effort | tech file + ASCII-art unit-transistor patterns (`tr_tsmc65.json`) | micro-template GDS + YAML, generated (`laygo/laygo_tech.py`) | `layers.json` + mock MOS generator, abstract layers remapped after (`tsmc65_post.py`) |
| Gate lengths | one pattern cell per L (stretched gate row) | one template family per L; built-in `nmos/pmos` is a single L, others via `TileMOSTemplate` | per-device, from the netlist |
| Width | stacks of 500 nm unit fingers | finger count x per-family finger width | fins (100 nm) x even `nf` |
| Placement | instance names = columns, netlist order = position in the column; rows by building transposed + `LayoutRotateCell` | rows written by hand (`dsn.place`) | automatic |
| Routing (M1-M3 only) | explicit rectangles from a small router in the generator: pins reach M2 trunks in M1, M3 bars join rows | `route_net` per net onto M3 trunks, M2 bars on a free track built into 1.5 um rows and on unused stretches of the device rows' own tracks | automatic, layers capped at M3 in `layers.json` (M2 end-to-end raised to 200 nm: the router left a 60 nm gap at 100) |
| FRIDA-1 status (M1-M3) | Calibre DRC clean (block waivers) + LVS correct, 21.3 x 16.8 um | Calibre DRC clean (block waivers) + LVS correct, 15.0 x 10.6 um | symmetric-hierarchical, M1-M3: Calibre DRC clean (block waivers) + LVS correct, 37.2 x 25.2 um (flat/hierarchical were clean with M2-M5 + M5/M6 grid) |
| Block pins and power | generator: M3 stubs to the top/bottom edge, full-width M1 rails per row | script: M3 stubs to the top/bottom edge (`escape`), full-width M2 rails per row | `PortLocation` is a soft placement hint only (pins stayed inside the cell); within M1-M3 its power grid shorts vdd to vss, so vdd/vss are routed as plain nets (no `PowerPorts`/`GroundPorts`) |
| Gate direction | vertical only (horizontal pattern cells, block rotated R90 with `LayoutRotateCell`) | vertical only (templates) | vertical only (PDK poly direction V) |
| Runtime per comparator | seconds (cicpy, laptop) | seconds (hosted server) | ~10 min single-threaded on juno, ~9 GB RAM |
| Scaling to 296 variants | `gen_comp.py` already emits the native files from HDL21 | needs the same script made generic (rows from the netlist) | netlist + 4-line constraint file per variant; ~50 h serial, parallel limited by memory |

## What was hard

**cIcCreator.** The pattern language is compact once understood, and it compiles in
seconds (pure Python). Routing is the cost: routes are stringly typed (`trunkx7000`, not
`trunkx=7000`; a wrong form is silently ignored), every via is at least two cuts, a one-pin
route draws nothing, and the minimum-area rules for via pads have to be designed around. The
orthogonal router puts trunks on M3 with M2 stubs; limited to M1-M3 that leaves no layer to
cross rows on, so the generator now draws all routing itself (M2 trunks reached in M1, M3 bars).
Its transistor patterns size the gate along y (the `G` character), so poly runs
horizontally and unit cells stack into columns; vertical gates in rows came from building the
cell transposed and wrapping it in the native `LayoutRotateCell` (R90). In practice the object
file has to be generated (`gen_comp.py`, which also carries a small slot/bar router); written
by hand it is dozens of coordinates per net. Upside: everything is deterministic and debuggable with
`cicpy checkroutes`, and the result was Calibre-clean on the first full generator run.

**laygo3.** laygo3 is Hanyang's (Nifty Chips Lab) successor to laygo2; the package is internal to
the lab and only reachable through its Web Console, which runs uploaded scripts server-side. Scripts
still use the laygo2 API and module names (`laygo2.Design`, `laygo2_tech`), so nothing can be run or
inspected locally. Device generation is pleasant, and `route_net` keeps simple designs short.
But the technology model assumes one transistor family (fixed L and finger width), so a
multi-L analog circuit needs custom families through laygo internals. The hosted server
ships four technology setups (emul028 default, etri_0p5um, sky130, ihp130); each points at
template GDS and layer-map files stored on the server, and only the YAML can be edited. A
new PDK can therefore describe its templates and grids, but its drawn cells and layer
numbers have to be substituted after download (`laygo/post.py`, here on top of the ihp130
setup's files). Its sandbox has no `print`, `repr` or exceptions (debugging by
`assert`). `route_net` stretches trunks past the pins and `route()` adds vias implicitly, so
safe track assignment in a dense layout needed a small router inside the script (track
bookkeeping per net, cross-row bars, two-bend fallbacks), plus a row-band implant fill and cut
merge in post-processing to reach a DRC-clean result. Within M1-M3 the device rows' M2 is largely
taken by the templates' pin bars, so the generated tech has 1.5 um rows with one free M2 track
above the gates (`laygo/laygo_tech.py`, `ROUTE_TRACKS`), and the script also books the stretches of the
device tracks that no pin uses; the row orientation must follow the row's position because the
routing grid repeats every two rows. Boundary cells are a poly pitch wide (1.22 um for
L = 1.02 um), so devices of one family sharing a source net abut with `bndl/bndr=False`; a
narrower boundary with an offset M1 grid broke the tile generator's terminal routing.

**ALIGN.** The input is the smallest of the three (netlist + power/ground/clock ports +
one compiler switch), which is what makes it attractive for hundreds of variants. Costs:
building it (C++ PnR, solver libraries), memory (the laptop's 15 GB was not enough; runs
live on juno) and runtime (~10 min per comparator). Placement only became feasible with
ALIGN's automatic symmetry constraints switched off (`ConfigureCompiler auto_constraint:
false`). Hand-written `SymmetricBlocks` do work inside each sub-block (`comp_frida1_sym`:
StrongARM and SR latch each mirrored), but any placement constraint on the top level left
the placer without a solution, and the result is loose (32.6 x 28.2 um, vs 15.7 x 10.4 um
for laygo3) because every primitive comes with its own tap and filler tiles. The mock 65 nm PDK only approximates TSMC65: reaching Calibre-clean took
`layers.json` changes (M1 width, metal min length, poly-contact and body-tap sizes) and a
post-processor (`tsmc65_post.py`) that maps layers, rebuilds VTL around the gates, snaps to
the 5 nm grid, removes degenerate polygons, and resolves well and implant checkerboard corners where
ALIGN's tiles of opposite type meet diagonally (NW notched apart, gaps < 470 nm closed).

## Signoff

`calibre/signoff_rules.py` runs the foundry Calibre decks on juno (block-level waivers: the density
checks, `DRC_BLOCK_WAIVERS` in the PDK). `klayout/klayout_lvs.py` is a local approximation used while Calibre is unreachable;
it agrees with Calibre on the cIcCreator layout.
