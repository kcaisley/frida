# Layout Refactor Plan: Split Serialization + Canonical Layer IDs

## Summary
- Keep the generation model as **PDK-aware at input time**: generators receive `vlsir.tech`-derived dimensions/rules and layer mappings and produce concrete KLayout geometry.
- Q: The layers mappings across the PDKs should be cleaned up, so that the names of the layers are consistent. Since in the end we will be generating GDS files, which can be used with .lyt files to see the actual layer names this isn't an issue.
- Q: Referencing the above, use OD, PO, M1.draw, M2.pin, VIA3, etc as the names, etc
- Split the current mixed module into focused modules, including a dedicated serializer file `layout/serialize.py`.
- Standardize primitive generator APIs on **canonical process-agnostic layer IDs** (e.g. `M1`, `M2`, `POLY`) with per-PDK alias mapping.
- I found that klayout, which is going to build up our layers, can actually handle in memory layers with just name, but no layer number purpose number pair. Therefore, we can built our layouts just by name. And before the serialization step, simply add the corresponding numbers.
- Apply a **hard cutover** (no compatibility shim): update all imports in one change.
- Q: Restructure the dimensions, so that it's organized by layer, from implatation, OD, PO, up through the metal stack. Perhaps we can use a syntax inspired by calibre rules? I'd like to use all caps for the layer names, but normal lower case for the rules?
   - Metal, poly and via minimum area, minimum width
   - Metal minimum enclosure
   - Metal to Metal spacing, table based on parallel run length
   - VIA to VIA spacing, and metal above and below enclosure. Applies also to the CO layer, which goes down to PO and OD.
   - implatation enclosure and spacing to opposite implatations (we need a good set of generic names which cover all pdks)
- Q: I don't know if we need to stackup orders. Because I think once our names are generic, all our four pdks use the same ordering maybe?

## Review Findings (Verified)
1. High: one module currently mixes unrelated responsibilities (tech schema + rule queries + KLayout drawing + VLSIR raw serialization), which makes maintenance and API design hard.  
   File: [layout.py](/home/kcaisley/frida/flow/layout/layout.py#L1)
2. Medium: primitive generators already depend on PDK rule values at generation time, which matches your preferred flow and should be formalized as the contract.  
   Files: [nmos.py](/home/kcaisley/frida/flow/layout/nmos.py#L1), [momcap.py](/home/kcaisley/frida/flow/layout/momcap.py#L1)
3. Medium: layer naming is partially process-agnostic via alias tuples, but not standardized as a single canonical API.  
   Files: [nmos.py](/home/kcaisley/frida/flow/layout/nmos.py#L1), [momcap.py](/home/kcaisley/frida/flow/layout/momcap.py#L1)
4. Medium: KLayout supports absolute transforms, hierarchy, and arrays, but not a built-in declarative relative-placement constraint system. Relative placement would be your own abstraction layer.
5. Verification result: Layout21 and BFG do **not** use a “generic geometry then post-raw pdkwalker” flow for raw export.
   - Layout21 raw exports concrete geometry directly; Layout21 tetris has a compile step that resolves relative placements to absolute before raw conversion.
   - BFG loads technology/rules, builds concrete layout using that DB, then serializes to `vlsir.raw`.
   Files: [/home/kcaisley/libs/Layout21/layout21raw/src/proto.rs](/home/kcaisley/libs/Layout21/layout21raw/src/proto.rs#L1), [/home/kcaisley/libs/Layout21/layout21tetris/src/placer.rs](/home/kcaisley/libs/Layout21/layout21tetris/src/placer.rs#L1), [/home/kcaisley/libs/Layout21/layout21tetris/src/conv/raw.rs](/home/kcaisley/libs/Layout21/layout21tetris/src/conv/raw.rs#L1), [/home/kcaisley/libs/bfg/src/layout.cc](/home/kcaisley/libs/bfg/src/layout.cc#L327), [/home/kcaisley/libs/bfg/src/physical_properties_database.cc](/home/kcaisley/libs/bfg/src/physical_properties_database.cc#L52)

## Public API / Interface Changes
- Add `flow/layout/serialize.py` with:
  - `layout_to_vlsir_raw(layout, domain="frida.layout") -> vraw.Library`
  - Q: waht is vraw above? I'm not familiar with that naming convention?
  - `vlsir_raw_to_disk(library, pb_path, pbtxt_path=None) -> None`
  - `export_layout(layout, out_dir, stem, domain="frida.layout", write_debug_gds=False) -> ExportArtifacts`
  - `ExportArtifacts` dataclass
- Add `flow/layout/tech.py` with:
  - existing technology dataclasses and proto read/write helpers
  - existing rule lookup utilities (`technology_rule_value`, spacing, pair rules, etc.)
- Add `flow/layout/klayout.py` with:
  - `create_layout`, `um_to_dbu`, `insert_box_um`, `insert_text_um`
  - Q: do we need these four functions? Doe the api not provide this?
- Add `flow/layout/layers.py` with:
  - canonical layer ID enum/type (process-agnostic)
  - alias-map type and resolver helpers from canonical ID -> actual `(layer, datatype)` using `Technology.layers`
  - Q: what is this Technology.layers namespace? I'm not familiar?
- Update callers to import from new modules directly (hard cutover).
- Update package exports in [__init__.py](/home/kcaisley/frida/flow/layout/__init__.py#L1) to reflect new module boundaries.

## Implementation Plan
1. Create `layers.py` and define canonical IDs for primitives used now (`ACTIVE`, `POLY`, `CONT`, `M1`, `M1_PIN`, `NSD`, `PSD`, `NWELL`, `TEXT`, `PR_BOUNDARY`, plus MOMCAP-used metal/pin IDs).
2. Move tech dataclasses + tech proto I/O + rule/layer lookup functions from [layout.py](/home/kcaisley/frida/flow/layout/layout.py#L1) to `tech.py` with unchanged behavior.
3. Move KLayout geometry helper functions to `klayout.py` with unchanged signatures.
4. Move KLayout->VLSIR serialization/export functions to `layout_serialize.py` with unchanged serialization behavior.
5. Update [nmos.py](/home/kcaisley/frida/flow/layout/nmos.py#L1) and [momcap.py](/home/kcaisley/frida/flow/layout/momcap.py#L1):
   - switch to canonical layer IDs in resolver paths
   - keep extraction of physical dimensions/rules from `vlsir.tech` at generator input
   - remove process-specific layer-name assumptions from generator internals
6. Update PDK layout metadata modules to expose/consume alias maps for canonical IDs:
   - [/home/kcaisley/frida/pdk/ihp130/layout/pdk_layout.py](/home/kcaisley/frida/pdk/ihp130/layout/pdk_layout.py#L1)
   - same pattern for other PDK layout metadata modules in `pdk/*/layout/`.
7. Update [__init__.py](/home/kcaisley/frida/flow/layout/__init__.py#L1) exports and remove old `flow.layout.layout` import usage everywhere (hard cutover).
8. Replace [layout.py](/home/kcaisley/frida/flow/layout/layout.py#L1) with either:
   - a minimal boundary doc module that no longer owns mixed functionality, or
   - remove it entirely if no importers remain.

## Tests and Scenarios
1. Serializer equivalence tests:
   - rectangle/polygon/path/text conversion
   - instance serialization including arrays expansion and transforms
   - assert output structure invariants match prior behavior
2. Layer resolver tests:
   - canonical ID resolves across alias variants (`M1`, `METAL1`, process name forms)
   - missing canonical ID fails with clear error
3. Generator regression tests:
   - NMOS and MOMCAP smoke tests still pass and produce expected top-level dimensions/layer usage
4. Integration test:
   - full flow from tech proto read -> generator -> KLayout memory -> raw protobuf export
5. Acceptance criteria:
   - no remaining imports from `flow.layout.layout`
   - all existing layout tests pass, plus new resolver/serializer tests pass

## Assumptions and Defaults
- Default model is PDK-aware generation (chosen): no generic post-serialization “pdkwalker compiler” stage for physical dimensions.
- Canonical layer IDs are the stable generator-facing interface; PDK alias maps are the adaptation layer.
- KLayout remains the in-memory source of truth for concrete geometry prior to raw serialization.
- No compatibility shim is kept; this is a one-shot migration across FRIDA internal call sites.
