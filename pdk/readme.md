# PDKs

One submodule per process, each the Python package `pdk.<tech>` and laid out by toolchain: the foundry
kits `tsmc65`, `tsmc28`, `tower180`, `lf150`, `tpsc65` and the open ones `ihp130`, `sky130`, `gf180`
(each finds its open PDK's install by an environment variable: `IHP_OPEN_PDK`, `SKY130_OPEN_PDK`,
`GF180_OPEN_PDK`). A PDK carries only the directories it has content for.

| Directory | Contents | Imported as |
| --- | --- | --- |
| `hdl21/` | device and standard-cell modules (`pdk_logic`, `pdk_data`, `primitives`, `stdcells`), the library of the generic cells (`cells`, written by `flow/circuit/cellmap.py`), the devices' Spectre wrappers where the kit has them (`spectre_devices.scs`), and the site installation (`site`) | `pdk.<tech>.hdl21.*` |
| `layout/` | the layout description every generator shares (`tech.py`: layers, metal and via rules, the row profile; `README.md`: the profile's numbers), standard-cell locations (`paths.py`), the PDK's test netlists (`netlists/`), ALIGN's PDK files (below) | `pdk.<tech>.layout` |
| `devices/` | the precharacterized device tables (`mosfet`, `moscap`, `polyres`, `momcap` `.json`), written by `flow/layout/devices` | files |
| `kpex/` | KLayout-PEX's metal stack (`stack.json`) and, where its 2.5-D engine runs, the kit's coefficients (`parasitics.json`) | files |
| `signoff.py` | the signoff provider of `flow/layout/signoff.py`: `run_drc` (gdscheck where installed, then the PDK's DRC; writes `drc_violations.json`, raises unless clean), `run_lvs`, and `run_pex` where the PDK extracts | `pdk.<tech>.signoff` |
| `netlist/` | netlist collateral shared by the tools (`lvs.py`: the LVS source's rules, each MOS (`mos`) and the library cells and devices a layout calls (`library`)) | `pdk.<tech>.netlist.*` |
| `klayout/` | layer palette, technology and layer map (`.lyp`, `.lyt`, `.lyd25`, `.map`), KLayout LVS | files |
| `calibre/` | (the foundry kits) foundry deck specialisation, the signoff checks `signoff.py` wraps (`signoff_rules`; LF150's runs Assura for LVS), recognition decks | `pdk.<tech>.calibre.*` |
| `gdscheck/` | gdscheck process and rule decks | files |
| `openroad/` | technology LEF, the standard-cell views (`lef/`, `lib/`, `gds/`, `sp/`), an `init.tcl` that reads them, and a design of every cell (`v/`) that `pdk/test_openroad.py` links | files |
| `docs/` | notes on the PDK (layout-dependent effects in the models, `lde.md`) | |
| `tests/` | the PDK's tests | |

`pdk.<tech>` itself registers the HDL21 PDK and re-exports `hdl21.pdk_logic`. The layout
generator is ALIGN: its driver (`flow/layout/run.py`) knows no PDK, and each kit's `layout/` is
ALIGN's PDK package, its `layers.json`, `models.sp`, `rows.json` and `user_template.sp` written from
`layout/tech.py` by `flow/layout/make_pdk.py` and committed with it (`flow/layout/test_make_pdk.py`
checks they are current). Only the standard tools (KLayout, OpenROAD, Calibre, gdscheck)
keep their own rule files. The superproject holds no PDK's numbers, layouts or cell names.
