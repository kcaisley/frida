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
  from ALIGN's placement says `"symmetric": false` (its rows are not mirrored).
- `mos_inv.json`, `pdk/<pdk>/layout/netlists/mos_inv.sp` — the single-device test: one NMOS and one PMOS
  row cell (an inverter), each in a row of its own, hand-written per PDK.
- `comparison.md` — notes from evaluating cIcCreator, laygo and ALIGN.

The comparator layout runner (`flow/comp/layout.py`) builds them, and floorplans from ALIGN's
placement, with all three tools and signs each layout off:

```bash
uv run python -m flow.comp.layout                              # the 36 targets
uv run python -m flow.comp.layout comp_frida1_manual_tsmc65    # this floorplan, one PDK
uv run python -m flow.comp.layout comp_c040_auto_tsmc65        # a floorplan from ALIGN's placement
uv run python -m flow.comp.layout mos_inv_all_pdks             # one case in all six PDKs
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
inverter in shape) as transistors. `expand` does the reverse: a library cell's transistors at the
library's sizes, with the row cells' models, so a netlist that asks for, say, a 1x NAND2 can be
drawn from the row cells, or as ALIGN's own logic gate.

| Targets | Netlist | Logic |
| --- | --- | --- |
| `comp_*_manual_<pdk>` | the generator's standard-cell netlist | library cells, as the floorplan names them |
| `comp_*_auto_<pdk>` | the generator's transistor netlist, `recognize`d | library cells |
| `comp_*_gates_<pdk>` | the standard-cell netlist, `expand`ed | row-cell transistors (ALIGN's logic gates where the PDK has logic cells) |

**ALIGN's primitives.** On a netlist without a floorplan, ALIGN matches devices to its primitive
library (its `basic_template.sp`, plus `flow/layout/align/pdk/user_template.sp`): pairs such as
`DP_NMOS`, `CMC_PMOS` and `CCP_*` (drawn by `align/pdk/mos.py` as one `rowcell.mos_row`, A left of
B), single devices (`NMOS_S`, `PMOS_4T`, ...), and the logic gates `INV`, `NAND2` and `NOR2`
(drawn by `stems/logiccell.py`; a PDK without logic cells keeps them single devices through
ALIGN's `DoNotUseLib`). Library cells stay leaves (`align/pdk/stdcell.py`). ALIGN's grouping,
`1_topology`'s `GroupBlocks`, becomes the floorplan's `groups`; with a floorplan, ALIGN keeps every
device a primitive of its own.

A floorplan from ALIGN's placement keeps transistors and standard cells in rows of their own, as
many standard-cell rows as their width needs, and an even number of rows, so both block edges are
VSS rails.
