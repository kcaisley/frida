# Comparator layouts

Circuit-specific inputs of the comparator layout flows, besides the generator itself. The flows themselves are circuit-agnostic:
the tool drivers are in `flow/layout/{cic,laygo,align}`, the row cells they all draw in `flow/layout/stems`,
and each PDK's values in `pdk/<tech>/layout` (e.g. `pdk/tsmc65/layout/README.md`, in the private PDK submodule).
Everything they produce goes to `build/layout/`.

- `comp_frida1.json`, `comp_c040.json` — hand-written floorplans: rows top first, each left to
  right and mirrored about the centre, the generated netlist they place (`{pdk}` filled in), the
  devices split into equal parts for a cross-quad (`split`), and the edge each port leaves at
  (`escape`). The design takes the floorplan's name.
- `mos_inv.json`, `pdk/<pdk>/layout/netlists/mos_inv.sp` — the single-device test: one NMOS and one PMOS
  row cell (an inverter), each in a row of its own, hand-written per PDK.
- `comparison.md` — notes from evaluating cIcCreator, laygo and ALIGN.

```bash
pdk=tsmc65   # or ihp130, tower180, tsmc28, lf150, tpsc65
uv run python -m flow.comp.subckt frida1 build/layout/netlists/$pdk/comp_frida1_stdcells.sp --output-stage stdcells --pdk $pdk
uv run python -m flow.comp.subckt frida1 build/layout/netlists/$pdk/comp_frida1_transistors.sp --pdk $pdk
uv run python flow/layout/stems/stdcell_access.py pdk/$pdk/layout                   # once per PDK library
flow/layout/cic/build.sh $pdk design/layout/comp_frida1.json
flow/layout/laygo/build.sh $pdk design/layout/comp_frida1.json
flow/layout/align/build.sh $pdk design/layout/comp_frida1.json          # floorplanned (ALIGN host)
flow/layout/align/build.sh $pdk design/layout/comp_frida1.json --free   # ALIGN places freely
flow/layout/check.sh $pdk cic design/layout/comp_frida1.json build/layout/cic/$pdk/comp_frida1/comp_frida1.gds
flow/layout/check.sh $pdk align design/layout/mos_inv.json build/layout/align/$pdk/mos_inv/mos_inv.gds
```

The netlists come from the generator (`flow/comp/subckt.py`), compiled for the PDK exactly as for
simulation: every device fingered to the row cells and sized in whole unit widths. `c040` is the
size sweep's topology 40 at the half profile (`40_half`). `check.sh` runs the PDK's gdscheck
precheck, then Calibre where it is installed and the PDK's KLayout decks elsewhere (IHP's open
decks).
