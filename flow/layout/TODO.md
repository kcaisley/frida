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

## Next

- [x] gdscheck decks for tsmc28, tower180 and ihp130; `check.sh` runs the precheck first.
- [x] Bring up lf150.
- [x] Bring up tpsc65.
