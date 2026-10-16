# Layout TODO

Progress tracker for the layout flows and the PDK submodules. Tick items as they land.

## One PDK description, one geometry library

Goal: each PDK describes its layout once, as data in `pdk/<tech>/layout/tech.py`; every generator
(stems, the caparray, later ones) is generic code in `flow/` drawing `klayout.db` shapes from it.
`pdk/<tech>/layout/layout.py` and the DSL's generic-layer/rule-deck machinery go away.

- [x] 0. Reference GDS of every generated structure, before any change (`build/layout/reference/A`;
  `build_all.sh`, `align_all.sh` on juno, `compare.py`). A rebuild of unchanged code matches 42/42.
  - [x] cic: both comparators in all four PDKs (with each design's row-cell library, `*_cells.gds`)
  - [x] laygo: both comparators in all four PDKs (with each design's templates)
  - [x] ALIGN: both comparators in tsmc65, ihp130, tower180, and tsmc65 frida1 with the guard ring
    (tsmc28 fails, see below)
  - [x] standard-cell access points (`build/layout/stems/*_access.json`)
  - [x] caparray: the three tsmc65 targets (GDS and geometry manifest); no other PDK generates one
- [x] 1. Rule deck into `tech.py`: per-layer table for all metals and vias, layer map, DBU and grid;
  `rule_deck()` callers (caparray, ringfmom, tsmc65 signoff) read it; stems constants defined from it.
  A/B: identical GDS (local 42/42, ALIGN 7/7). The other PDKs' tables come from their tech
  LEFs: their old decks and layer maps were placeholders copied from IHP's numbers.
- [x] 2. stems draws `klayout.db` shapes instead of its own `Rect` list: decided against. The
  routers and all three drivers rely on the rectangles' insertion order and on fast net/kind/terminal
  access, and ALIGN needs helper shapes (M1 stubs) that never reach the GDS: a KLayout-backed `Cell`
  would carry its own ordered list beside the shapes, a layer more instead of one less. The
  duplication that hurt (a second PDK description, generic layers, rule decks, the DSL) is gone;
  stems keeps its two small records, and KLayout stays the only way to GDS. (KLayout is installed
  in ALIGN's environment on juno, which its markers needed anyway.)
- [x] 3. Caparray on `tech.py` with PDK layer names, no generic-layer remapping. A/B: identical GDS.
- [x] 4. Remove `pdk/<tech>/layout/layout.py`, the generic-layer remap, `NewRuleDeck`, the VLSIR
  technology export and the DSL (`flow/layout/{dsl,tech,serialize}.py`: nothing used them any more).
- [x] 5. Docs: `pdk/README.md`, `pdk/tsmc65/layout/{README,rules}.md`.

## PDK contract status

- [x] tsmc65: every folder in `pdk/README.md` present.
- [x] tsmc28: `gdscheck/` (precheck from `RULES`; it flags the M1 strip ends of the tsmc28 cells).
  - [x] Liberty, LEF and GDS are the only releases in the kit; the full-library link passes. Noted
    in `openroad/init.tcl`.
- [x] tower180: `gdscheck/` (precheck from `RULES`; clean on cic and laygo, flags the ALIGN spacing).
- [x] ihp130: `gdscheck/` (precheck; gdscheck also embeds the full `ihp-sg13g2` decks) and `docs/lde.md`
  (no `calibre/` by design: open KLayout decks).
- [x] lf150: every folder in `pdk/README.md` but `align/`, `cic/`, `laygo/` (none has one).
  - [x] Standard cells: the kit's 9-track library, per-cell GDS joined into one; worst and best
    Liberty (the kit's typical is a conditional library). The full-library link passes.
  - [x] hdl21 (HS, LL, native and 3.3 V devices; the model wrappers take no finger count, so
    fingers are `m` copies, which netcells honours for every PDK), `layout/tech.py` from the
    LF150i rules, LVS source, gdscheck precheck, `docs/lde.md` (BSIM3v3: no LOD/WPE), tests.
  - [x] Signoff: Calibre DRC on the kit's 6-metal deck; LVS on Assura (LF150i ships no Calibre
    LVS), the kit's rules with the METAL_T black-box layer its GDS section lacks.
- [x] tpsc65: every folder in `pdk/README.md` but `align/`, `cic/`, `laygo/` (none has one).
  - [x] Standard cells: the kit's 12-track LVT library; typical and slow Liberty. The full-library link passes.
  - [x] hdl21 (LVT, SLVT and 3.3 V devices, fingered by `m` as in LF150), `layout/tech.py` from the
    TPS65ISC DRM (7M2L1F stack), LVS source, gdscheck precheck, `docs/lde.md` (BSIM4 wrappers with
    LOD/WPE/STI-width terms, neutral at their defaults), tests.
  - [x] Signoff: the kit's encrypted Calibre decks, which name their inputs `LAYOUT_PATH` /
    `LAYOUT_PRIMARY` / `SOURCE_PATH` / `SOURCE_PRIMARY`: the runner writes copies under those
    names. Block-level waivers: density, the generated deep P-well's enclosures, and the standard
    cells' well-expansion DFM guideline (DRM 6.1.2).

## Comparator layouts

- [x] tsmc28 cic: gridded poly in the row cells (gate rectangles, dummy poly, poly markers,
  implant and M2 line-end spacing: `LONG_L`, `PO_DUMMY`, `PO_MARK`, `GATE_MARK`), the library
  cells' own M2 plates kept clear (`M2_PLATE`, `VIA_SPACE`), a minimum finger (`MOS_FINGER_MIN_UNITS`). DRC
  clean (density waived at block level), LVS correct.
- [x] tsmc28 laygo: DRC clean, LVS correct (short trunks grown to the M3 area, close VIA2 pairs
  joined, library rectangular vias kept).
- [x] tsmc28 ALIGN: the cells' netlists had trailing blanks ALIGN's parser chokes on (not the
  models); markers on ALIGN's spare layers; DRC clean, LVS correct.
- [x] tower180 ALIGN: ALIGN's M2 grid at the routing pitch; a half-pitch standard-cell pin reaches
  ALIGN as a pin bar on the free track beside its via pad, with a keep-out on the other track
  (`netcells.align_access`; post.py draws the pads and drops the keep-outs); pin bars span two M3
  grid points. mos_inv and frida1 DRC clean, LVS correct.
  - [x] c040 (and lf150 c040): ALIGN left one SR-latch net open. Its router keeps M2 line ends
    2 M2 spaces apart by default, so the dense standard-cell row's pin bars, one space apart on
    a track, shut it out; neither LEF has an M2 end-of-line rule, so `M2_LINE_END` is the
    plain space there (make_pdk.py). All three designs DRC clean, LVS correct.
- [x] ihp130 ALIGN frida1: the hanan router (`ALIGN_ROUTER`), ALIGN's default where it crashes.
- [x] tsmc65 ALIGN c040: the M2 line-end space fixed in the cells (`M2_EDGE`).
- [x] lf150: cic and laygo DRC clean and LVS correct in all three designs; ALIGN mos_inv and frida1
  too (row fillers past the block ends, `ALIGN_ROW_ENDS`, for the generated P-well's width). Fixed
  on the way, for every PDK: gate metal on the manufacturing grid for gates of odd half length,
  laygo's M2 branches to a trunk past a pin kept off other nets' pins, no lone via where two trunks
  meet on one track. Other PDKs' layouts unchanged (A/B).
- [x] tpsc65: cic and laygo DRC clean and LVS correct in all three designs; ALIGN mos_inv too. The
  row cells copy the library's tap profile (`RAIL_IMPLANTS`, the counter-dope marker in
  `RAIL_MARKS`), dummy poly on its own layer (`PO_DUMMY_LAYER`); placed library cells are cut back
  to the rows' well and implant bands (`STD_CLIP`: theirs reach into the next row); pins shorter than a via landing take the cut with its line-end enclosure across
  (`VIA_EOL_ACROSS`); the row-end supply stacks sit far enough in for their pads (`EDGE_STEP`).
  Other PDKs' layouts and access tables unchanged (A/B).
  - [x] ALIGN frida1 and c040: one net each was left unrouted. All pins sat on the two middle
    tracks, and two vias one track apart on an M3 column break V2's 0.14 space (LEF `SPACING
    0.14 PARALLELOVERLAP`), so a route between neighbouring cells' pins found no column; the
    pins now take every other track first (`STD_TRACKS`), and `M2_LINE_END` as for Tower. cic
    and laygo rebuilt with the new access, all nine DRC clean, LVS correct.
- [x] Single-device test: `design/layout/mos_inv.json` (one NMOS, one PMOS row cell) in every PDK
  and tool, DRC clean and LVS correct.
- [x] Floorplans: the decision inverters swapped so no nets cross in the standard-cell row.

## Comparator layout runner

- [x] `flow/comp/layout.py`: 30 per-PDK targets (frida1 and c040, from the hand-written floorplan
  or from ALIGN's placement, and mos_inv), five `*_all_pdks` targets and `all_comp_layouts`.
  `flow/layout` is a library (no command lines or shell scripts); each step that reads a PDK runs
  in a process bound to it (`pdkproc.py`). The hand-written floorplans' 54 layouts are identical
  to the shell scripts' (per-layer XOR and labels, 2026-10-14), with the same DRC and LVS results.
- [x] Signoff providers `pdk/<pdk>/signoff.py` (gdscheck, then Calibre; Assura for LF150 LVS, the
  open KLayout decks for ihp130) and `row_signoff`. A checker that stops early now fails instead
  of passing (ihp130 DRC without its deck) or reporting a mismatch (LVS without a report).
- [x] Floorplans from ALIGN's placement (`floorplan.py`); `groups` with ALIGN's primitives in every
  floorplan, checked by `netcells.check_groups`.
- [ ] The tools use `groups`: cIcCreator and laygo keep a group's devices side by side, and
  `align/make_design.py` turns the groups into ALIGN constraints for floorplanned runs (this
  changes the ALIGN layouts, so it waited for the identical-layout check).
- [x] Floorplans from ALIGN's placement packed toward a square (`pack_rows`): ALIGN's single-axis
  placement alone gives a tall stack, mostly one primitive per row. Packed, the blocks are smaller
  than the hand-written ones (row fill 0.64 to 0.85 against 0.40 to 0.65; frida1 in tsmc65 12.7 x
  11.1 um against 15.3 x 11.1). DRC clean and LVS correct in all three tools: frida1 in tsmc65 and
  tpsc65, c040 in tsmc65; cIcCreator and laygo also c040 in tsmc28, ihp130 and tpsc65 (2026-10-15).
- [x] Well and implant rules at a block's top edge (tower180, tpsc65, ihp130): a block of an odd number
  of rows ends on a VDD rail, whose implant and well overhangs no row above covers. `pack_rows` makes
  the number of rows even (both edges VSS rails, as the hand-written floorplans). NMOS and PMOS row
  cells abut cleanly in a row (checked in tower180, ihp130, tsmc28, lf150).
- [x] Cross-coupled pairs (ALIGN's CCP) in PDKs with three S/D tracks (tsmc28, tower180): a pair whose
  sources are no rail took every track; the crossings now take any M2 track of the cell without a bar
  whose VIA2 keep the via space from the jumpers' ends (beside the rails, past the gate track). The
  tsmc28 pairs on a rail had their crossings a track from the drains (VIA2 spacing); fixed too.
- [x] Standard cells recognized in transistor netlists (`stdcells.py`): the `auto`
  targets start from the transistor netlist. The `gates` targets (library cells drawn as transistors,
  and ALIGN's logic gates as generated cells in tsmc65) are gone: generated logic took 1.3 to 2 times
  a library cell's area, separate transistors 2 to 8 times; logic is always the library's cells.
- [x] Row routers (cIcCreator's `rowroute`, laygo's script): an M2 piece keeps the M2 space to a
  separate piece of its own net too, and laygo's branches to pins on the next, half-pitch pin track
  (tower180: a pin bar stretched to a trunk ran within 200 nm of the same net's pin on the next track).
- [x] ALIGN's MOS primitives as ALIGN chooses them (`align/pdk/mos.py`, 2026-10-15): the array
  (`x_cells`, `y_cells`, ALIGN's own variants in `gen_param.py`) and the pattern (common centroid,
  interdigitated, ratio, non common centroid, `exact_patterns`), each unit's device as ALIGN's mock
  generator assigns it, drawn by the row-cell engine (`rowcell.mos_array`: any finger order of one
  or more devices of a type; `mos_grid`: rows of them). The existing cells are drawn identically
  (checked for every device and pair of the comparators in all six PDKs). Gates of two nets that
  interleave need a second gate track (`GATE_SPARE`): tsmc28 has one (its patterns DRC clean); the
  other PDKs draw such a pair side by side, as before, while groups with one gate net (CMC, SCM,
  CMB) take ALIGN's patterns everywhere.
- [x] Floorplans from ALIGN's placement fall back to a placement on one axis in any outline (without
  the AspectRatio constraint; `pack_rows` squares the rows anyway) where none fits the square one
  (frida1's gates in tsmc28: 15 self-symmetric blocks). ALIGN's own symmetry groups failed there too.
- [x] Pairs of differing short gates where the dummy poly stands on the gates' pitch (tsmc28: 30 nm)
  take a diffusion break under the dummy lines, every line on the pitch. A shared strip with the
  gates pushed apart gave each gate two spaces to its neighbours and met the gates' M2 bars end to
  end; a break with one dummy line crowded the lines (ALIGN's DP_NMOS of c040's `Minner_init`
  pair, `comp_c040_auto_tsmc28`).
- [x] laygo's port labels attach to M3 (`laygo/post.py`), where every port of the template sits: in
  `comp_c040_auto_tsmc65` the clkb label sat where latch_p's M2 bar was centred too, and named it.
- [x] N-well notches narrower than the well space close in all three tools' post steps
  (`netcells.close_wells`, ALIGN's already did): a row padded by a filler narrower than the space left
  a notch between a PMOS cell's well and the row end's library profile (`comp_c040_auto_tower180`).
- [x] The standard cells ALIGN centres on its axis (self-symmetric, one per row: a comparator's output
  inverters) go where their nets are shortest in the merged row (`pack_rows`): nested, they all went
  to one side, and in `comp_c040_auto_lf150` cIcCreator and laygo found no route.
- [x] A gap in ALIGN's row of standard cells narrower than the library's fillers (tsmc28: one site;
  ALIGN places on a finer grid than the cells') takes the standard cells' profile (`align/post.py`).
- [x] A row of transistors too wide for any packing in ALIGN's aspect ratio splits into nested rings of
  its mirror pairs, each mirrored (`pack_rows`; c040 with its logic as transistors in tsmc65: 21.5 x
  7.5 um in four rows before, six rows after).
- [x] ALIGN runs on its own in the `auto` targets (2026-10-16): one run that derives its
  constraints (primitives, symmetry), places and routes; its placement is the floorplan of
  cIcCreator and laygo. The floorplanned second ALIGN run and the merge of ALIGN's symmetry groups
  onto one axis (one_axis.py) are gone. Results: frida1 in tsmc65 clean in all three tools (ALIGN
  10.9 x 13.0 um, cIcCreator and laygo 13.5 x 11.1, was 22.5 x 7.5 with the floorplanned run's
  arrays), c040 in tsmc65 clean (ALIGN 10.9 x 13.0, 12.5 x 11.1), frida1 in tower180 clean in all
  three (ALIGN's open buffer nets on the floorplan are gone), c040 in tsmc28 cIcCreator and laygo
  clean. A generator fallback draws a group side by side in one row where ALIGN's array does not fit.
- [ ] ALIGN on its own in tsmc28: free placement leaves gaps whose dummy-poly spacing the gridded
  poly rule (second poly line past a 30 nm gate) forbids (`comp_c040_auto_tsmc28` and
  `comp_frida1_auto_tsmc28`: 32 each, LVS correct; cIcCreator and laygo clean).
  Place on the cells' abutment grid, or fill such gaps with poly on the gate pitch.
- [ ] Not yet run with ALIGN on its own: the other auto targets (ihp130, lf150, tpsc65). Earlier
  ALIGN-only findings on floorplans from its placement (tpsc65's CMC_S_PMOS_B dummy poly, lf150
  frida1's clk-tail short) need checking again. In ihp130 ALIGN's ILP placement of c040 ran for
  over two hours without finishing (2026-10-16).
- [x] lf150 LVS on asiclab003: Assura (its `gdsIIToVdb`) needs `libicui18n.so.50`, package `libicu50`
  (installed 2026-10-15). The manual and auto floorplans of both comparators are LVS correct in all
  three tools, except ALIGN's frida1 from its placement below.

## Building blocks

- [x] Eleven block generators beside the sampler (`flow/<block>/`: delay, latch, ota, follower,
  moscap, idac, cml, pi, clkgen, lvshift, ringamp), laid out from `design/layout/<block>_*.json`
  with all three tools in all six PDKs: with the sampler's, 912 of 918 layouts DRC clean and LVS
  correct (2026-10-16). The comparators' manual, mos_inv and auto (tsmc65, tsmc28, tower180)
  results are unchanged.
- [ ] ALIGN's detailed router (A*, nets in turn, no rip-up) leaves a net open in
  `delay_ring4_tail_tower180` and `delay_ring5_starved_tpsc65` (its log says
  `A_star.FindFeasiblePath`); its other router, hanan, fails there too.
- [ ] lf150's smallest library inverter, in its dense frame (`stdcell_access.py`), reaches both
  pins from the one M3 track in the cell: `clkgen_pulse_lf150`, a chain of them, routes in no tool. A frame one site wider would
  give each pin a track of its own.
- [ ] laygo finds no route for `ringamp_se_tower180` (cIcCreator and ALIGN do).

## Next

- [x] gdscheck decks for tsmc28, tower180 and ihp130; every signoff provider runs the precheck first.
- [x] Bring up lf150.
- [x] Bring up tpsc65.
