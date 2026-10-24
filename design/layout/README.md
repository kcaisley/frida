# Comparator layouts

Circuit-specific inputs of the comparator layout flows, besides the generator itself. The flows themselves are circuit-agnostic:
the tool drivers are in `flow/layout/{cic,laygo,align}`, the row cells they all draw in `flow/layout/stems`,
and each PDK's values in `pdk/<tech>/layout` (e.g. `pdk/tsmc65/layout/README.md`, in the private PDK submodule).
Everything they produce goes to `build/layout/comp/<target>/<timestamp>/`.

- `comp_frida1.json`, `comp_c040.json` — hand-written floorplans: rows top first, each left to
  right and mirrored about the centre, the generated netlist they place (`{pdk}` filled in; a
  runner passes its own), the devices split into equal parts for a cross-quad (`split`), the edge
  each port leaves at (`escape`), and ALIGN's primitive of each device (`groups`, ALIGN's library
  names: `DP_NMOS_B_0`, `CCP_PMOS_0`, ...). The design takes the floorplan's name. A floorplan
  from ALIGN's placement (for cIcCreator and laygo; ALIGN itself places on its own there) says
  `"symmetric": false` (its rows are not mirrored).
- `mos_inv.json`, `pdk/<pdk>/layout/netlists/mos_inv.sp` — the single-device test: one NMOS and one PMOS
  row cell (an inverter), each in a row of its own, hand-written per PDK.
- `comparison.md` — notes from evaluating cIcCreator, laygo and ALIGN.

The comparator layout runner (`flow/comp/layout.py`) builds them, and floorplans from ALIGN's
placement, with all three tools and signs each layout off:

```bash
uv run python -m flow layout comp --instance frida1          # this floorplan, in all six PDKs
uv run python -m flow layout comp --instance c040 --auto     # a floorplan from ALIGN's placement
uv run python -m flow layout.mos_inv                         # the single-device test
```

The netlists come from the generator (`flow/comp/subckt.py`), compiled for the PDK exactly as for
simulation: every device fingered to the row cells and sized in whole unit widths. `c040` is the
size sweep's topology 40 at the half profile (`40_half`). Signoff (`flow/layout/signoff.py`
`row_signoff`) runs the PDK's provider, `pdk/<pdk>/signoff.py`: the gdscheck precheck, then
Calibre DRC and LVS (Assura for LF150 LVS, the IHP open KLayout decks for ihp130).

## How a netlist is recognized

Two layers of recognition turn a netlist into what the tools place.

**Standard cells** (`flow/layout/stdcells.py`). `recognize` finds groups of transistors that form one
of the PDK's library cells (`tech.STD_CELLS`, read from the library SPICE): the same connections
(drain and source either way, parallel fingers and parallel copies of a series stack merged), the
same polarity and channel length, and internal nets that touch nothing else. Of the drive strengths
that match one group, the closest in width wins; larger cells first. The group becomes an instance
of the cell, named after its transistors (`Mbuf1_outp_n`, `Mbuf1_outp_p` -> `Xbuf1_outp`). The
length check keeps analog devices that happen to form a gate (the 780 nm tail and its reset, an
inverter in shape) as transistors. Logic is always the PDK's library cells: the row cells draw
no logic gates of their own (they took 1.3 to 8 times a library cell's area).

| Targets | Netlist | Logic |
| --- | --- | --- |
| `comp_*_manual_<pdk>` | the generator's standard-cell netlist | library cells, as the floorplan names them |
| `comp_*_auto_<pdk>` | the generator's transistor netlist, `recognize`d | library cells |

**ALIGN's primitives.** On a netlist without a floorplan, ALIGN matches devices to its primitive
library (its own `basic_template.sp` and `user_template.sp`): groups such as `DP_NMOS`, `CMC_PMOS`,
`CCP_*` or `CMB_*`, and single devices (`NMOS_S`, `PMOS_4T`, ...); its logic templates (`INV`,
`INV_B`, `STAGE2_INV`) and its transmission gate (`TGATE`, an NMOS and a PMOS in one primitive) are off (`DoNotUseLib`, by the names ALIGN gives them). ALIGN chooses each group's array (units per row, rows) and pattern:
common centroid, interdigitated, ratio, or a Generator constraint's `exact_patterns`.
`align/pdk/mos.py` assigns the units' devices as ALIGN's own mock generator does and draws them
with the row-cell engine (`rowcell.mos_grid`). Two gate nets whose gates interleave need a second
gate track (`GATE_SPARE` in the PDK's `tech.py`, set in tsmc28); elsewhere such a pair is drawn side
by side. Library cells stay leaves (`align/pdk/stdcell.py`). ALIGN's grouping,
`1_topology`'s `GroupBlocks`, becomes the floorplan's `groups`; with a floorplan, ALIGN keeps every
device a primitive of its own: a device the floorplan's `groups` do not name is kept out of
ALIGN's matching (`DoNotIdentify`), which would otherwise pair devices by their connections alone.

A floorplan from ALIGN's placement keeps transistors and standard cells in rows of their own, as
many standard-cell rows as their width needs, and an even number of rows, so both block edges are
VSS rails.
