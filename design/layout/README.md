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
