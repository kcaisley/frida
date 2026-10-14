# PDKs

One submodule per process (`tsmc65`, `tsmc28`, `tower180`, `ihp130`, `lf150`, `tpsc65`), each the Python package
`pdk.<tech>` and laid out by toolchain. A PDK carries only the directories it has content for.

| Directory | Contents | Imported as |
| --- | --- | --- |
| `hdl21/` | device and standard-cell modules (`pdk_logic`, `pdk_data`, `primitives`, `stdcells`) and the site installation (`site`) | `pdk.<tech>.hdl21.*` |
| `layout/` | the layout description every generator shares (`tech.py`: layers, metal and via rules, the stems row profile; `README.md`: the profile's numbers), standard-cell locations (`paths.py`), the PDK's test netlists (`netlists/`) | `pdk.<tech>.layout` |
| `netlist/` | netlist collateral shared by the tools (LVS source netlists) | scripts |
| `klayout/` | layer palette and technology (`.lyp`, `.lyt`, `.lyd25`), KLayout LVS | files |
| `calibre/` | foundry deck specialisation, the signoff runner (`signoff_rules`; LF150's runs Assura for LVS), recognition decks | `pdk.<tech>.calibre.*` |
| `gdscheck/` | gdscheck process and rule decks derived from the Calibre rules | files |
| `openroad/` | technology LEF, the standard-cell views (`lef/`, `lib/`, `gds/`, `sp/`), an `init.tcl` that reads them, and a design of every cell (`v/`) that `pdk/test_openroad.py` links | files |
| `docs/` | notes on the PDK (layout-dependent effects in the models, `lde.md`) | |
| `tests/` | the PDK's tests | |

`pdk.<tech>` itself registers the HDL21 PDK and re-exports `hdl21.pdk_logic`. The layout
generators (cIcCreator, laygo, ALIGN) have no files here: their drivers in `flow/layout/<tool>/`
know no PDK and generate each tool's technology (`.tech`, `layers.json`, template YAML) from
`layout/tech.py` into `build/`. Only the standard tools (KLayout, OpenROAD, Calibre, gdscheck)
keep their own rule files. The superproject holds no PDK's numbers, layouts or cell names.
