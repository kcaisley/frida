"""Convert routed DEF + LEF into GDS using KLayout.

Adapted from OpenROAD-flow-scripts/flow/util/def2stream.py for the
FRIDA analog-openroad (AOR) hand-written test case.

Usage:
    klayout -zz \
        -rd tech_file=sg13g2.lyt \
        -rd layer_map=sg13g2.map \
        -rd in_def=comp_placed_routed.def \
        -rd in_lef="sg13g2_tech.lef;sg13g2_macros.lef" \
        -rd in_gds="sg13_lv_nmos.gds sg13_lv_pmos.gds" \
        -rd design_name=Comp \
        -rd out_file=comp_placed_routed.gds \
        -rm def2gds.py

Or simply (uses defaults for the AOR directory):
    cd design/aor && klayout -zz -rm def2gds.py
"""

import os
import sys

import pya

# ── Resolve parameters (from -rd flags or defaults) ─────────────────

script_dir = os.path.dirname(os.path.abspath(__file__))


def rd(name, default):
    """Read a -rd variable, falling back to a default."""
    try:
        return eval(name)  # KLayout injects -rd vars into global scope
    except NameError:
        return default


tech_file = rd("tech_file", os.path.join(script_dir, "sg13g2.lyt"))
layer_map = rd("layer_map", os.path.join(script_dir, "sg13g2.map"))
in_def = rd("in_def", os.path.join(script_dir, "comp_placed_routed.def"))
in_lef = rd("in_lef", "")
in_gds = rd("in_gds", "")
design_name = rd("design_name", "Comp")
out_file = rd("out_file", os.path.join(script_dir, "comp_placed_routed.gds"))

# Default LEF files if none provided via -rd
if not in_lef:
    in_lef = ";".join(
        [
            os.path.join(script_dir, "sg13g2_tech.lef"),
            os.path.join(script_dir, "sg13g2_macros.lef"),
        ]
    )

# Default GDS files for macro cells if none provided via -rd
if not in_gds:
    in_gds = " ".join(
        [
            os.path.join(script_dir, "sg13_lv_nmos.gds"),
            os.path.join(script_dir, "sg13_lv_pmos.gds"),
        ]
    )

# ── Load technology ─────────────────────────────────────────────────

print(f"[INFO] Technology file: {tech_file}")
print(f"[INFO] Layer map:       {layer_map}")
print(f"[INFO] Input DEF:       {in_def}")
print(f"[INFO] Input LEF:       {in_lef}")
print(f"[INFO] Input GDS:       {in_gds}")
print(f"[INFO] Design:          {design_name}")
print(f"[INFO] Output GDS:      {out_file}")

tech = pya.Technology()
tech.load(tech_file)
layout_options = tech.load_layout_options

# Apply layer map for LEF/DEF reading
if layer_map:
    layout_options.lefdef_config.map_file = layer_map

# Inject LEF files so KLayout can resolve macros from the DEF
lef_files = [f.strip() for f in in_lef.replace(";", " ").split() if f.strip()]
if lef_files:
    layout_options.lefdef_config.lef_files = lef_files
    print(f"[INFO] LEF files injected: {lef_files}")

# ── Read DEF ────────────────────────────────────────────────────────

main_layout = pya.Layout()
main_layout.read(in_def, layout_options)

top_cell = main_layout.cell(design_name)
if top_cell is None:
    # Try to find the top cell by name match (case-insensitive fallback)
    for cell in main_layout.each_cell():
        if cell.name.lower() == design_name.lower():
            top_cell = cell
            break

if top_cell is None:
    print(f"[ERROR] Design '{design_name}' not found in DEF. Available cells:")
    for cell in main_layout.each_cell():
        print(f"  - {cell.name}")
    sys.exit(1)

print(f"[INFO] Top cell: {top_cell.name}")

top_cell_index = top_cell.cell_index()

# ── Clear empty LEF-stub cells before merging GDS ───────────────────
#
# When KLayout reads the DEF+LEF it creates stub cells for each macro
# (e.g. sg13_lv_nmos, sg13_lv_pmos). These stubs may contain only
# LEF-derived pin/obs shapes. We clear them so that when we read the
# source GDS files below, the full transistor geometry replaces the
# stubs cleanly.
#
# We keep VIA cells (created by the DEF reader) — they already have
# correct geometry.

for cell in main_layout.each_cell():
    if cell.cell_index() == top_cell_index:
        continue
    if cell.name.startswith("VIA_") or cell.name.startswith("VIA"):
        continue
    cell.clear()

# ── Merge GDS files for macro cells ─────────────────────────────────
#
# Each GDS file should contain a cell whose name matches a LEF macro
# (e.g. sg13_lv_nmos.gds contains cell "sg13_lv_nmos"). KLayout merges
# by cell name — the GDS cell fills in the geometry for the empty stub
# that was created from the LEF.

gds_files = [f.strip() for f in in_gds.split() if f.strip()]
for gds_file in gds_files:
    if not os.path.isfile(gds_file):
        print(f"[WARNING] GDS file not found, skipping: {gds_file}")
        continue
    print(f"[INFO] Merging GDS: {gds_file}")
    main_layout.read(gds_file)

# ── Copy top cell tree to a clean layout ────────────────────────────
#
# This drops any orphan cells that came in from the GDS files but are
# not referenced by the top cell.

top_only_layout = pya.Layout()
top_only_layout.dbu = main_layout.dbu
top = top_only_layout.create_cell(design_name)
top.copy_tree(main_layout.cell(design_name))

# ── Report and check ────────────────────────────────────────────────

print("[INFO] Cells in final layout:")
errors = 0
for cell in top_only_layout.each_cell():
    shapes_count = sum(cell.shapes(li).size() for li in top_only_layout.layer_indexes())
    inst_count = cell.child_instances()
    marker = " (top)" if cell.name == design_name else ""
    print(f"  - {cell.name}: {shapes_count} shapes, {inst_count} instances{marker}")

    if cell.name == design_name:
        continue
    if cell.is_empty():
        if cell.name.startswith("VIA_") or cell.name.startswith("VIA"):
            continue
        print(
            f"[ERROR] Cell '{cell.name}' is empty — no matching GDS cell found. "
            f"Provide a GDS file containing a cell with this name."
        )
        errors += 1

# Check for orphan cells
for cell in top_only_layout.each_cell():
    if cell.name != design_name and cell.parent_cells() == 0:
        print(f"[ERROR] Orphan cell '{cell.name}' (not referenced by top cell)")
        errors += 1

if errors == 0:
    print("[INFO] All macro cells have matching GDS geometry")

# ── Write GDS ───────────────────────────────────────────────────────

top_only_layout.write(out_file)
print(f"[INFO] Wrote {out_file}")

sys.exit(errors)
