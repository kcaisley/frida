"""Generate GDS cells for sg13_lv_nmos and sg13_lv_pmos from the FRIDA mosfet generator.

These GDS files are needed by def2gds.py to fill in the transistor geometry
when converting the routed DEF to GDS. Without them the macro cells are
empty shells (LEF abstract only).

Usage:
    uv run python design/aor/gen_macros_gds.py

Outputs:
    design/aor/sg13_lv_nmos.gds
    design/aor/sg13_lv_pmos.gds

The generated cells use default MosfetParams (nf=4, w=1, l=1, vth=LOW,
source_tie=OFF, pr=2) which match the hand-written LEF macros in
sg13g2_macros.lef (cell size 3.020 x 3.060 um).
"""

from importlib import import_module
from pathlib import Path

import klayout.db as kdb

from flow.layout.dsl import MosType
from flow.mosfet.primitive import MosfetParams, mosfet


def _safe_remap(layout: kdb.Layout, tech_map: dict) -> None:
    """Two-pass layer remap that avoids the collision bug in remap_layers.

    The standard remap_layers() fails when a generic layer number equals
    its PDK target (e.g. generic 1/0 OD -> PDK 1/0 ACTIVE): it copies
    shapes to the same layer index, then clears the source, deleting
    everything. It also fails when an intermediate target collides with
    a later source (e.g. M1 10/0->7/0 writes to 7, then LVTN 7/0->70/0
    reads the combined data and clears 7).

    This function avoids both issues by:
      1. Copying all shapes to temporary layers (offset +1000)
      2. Clearing all original source layers
      3. Copying from temporary layers to final PDK layers
      4. Clearing temporary layers
    """
    cell = layout.top_cell()

    # Pass 1: copy to temp layers
    temp_copies: dict[kdb.LayerInfo, kdb.LayerInfo] = {}
    for generic, pdk_layer in tech_map.items():
        src_idx = layout.find_layer(generic)
        if src_idx is None or src_idx < 0:
            continue
        if cell.shapes(src_idx).is_empty():
            continue
        temp_info = kdb.LayerInfo(pdk_layer.layer + 1000, pdk_layer.datatype)
        temp_idx = layout.layer(temp_info)
        for shape in cell.shapes(src_idx).each():
            cell.shapes(temp_idx).insert(shape)
        temp_copies[temp_info] = pdk_layer

    # Pass 2: clear all original source layers
    for generic in tech_map:
        src_idx = layout.find_layer(generic)
        if src_idx is not None and src_idx >= 0:
            cell.shapes(src_idx).clear()

    # Pass 3: copy from temp to final PDK layers
    for temp_info, pdk_layer in temp_copies.items():
        temp_idx = layout.find_layer(temp_info)
        dst_idx = layout.layer(pdk_layer)
        for shape in cell.shapes(temp_idx).each():
            cell.shapes(dst_idx).insert(shape)
        cell.shapes(temp_idx).clear()


def generate_macro_gds(params: MosfetParams, cell_name: str, outpath: Path) -> None:
    """Generate a single macro GDS file with correct PDK layers."""
    pdk_module = import_module("pdk.ihp130.layout")
    tech_map = pdk_module.layer_map()

    layout = mosfet(params, "ihp130")
    _safe_remap(layout, tech_map)

    # Rename the top cell to match the LEF macro name
    layout.top_cell().name = cell_name

    layout.write(str(outpath))

    # Verify
    verify = kdb.Layout()
    verify.read(str(outpath))
    vc = verify.top_cell()
    total = sum(vc.shapes(li).size() for li in verify.layer_indexes())
    print(f"  {cell_name}: {total} shapes -> {outpath}")


def main() -> None:
    script_dir = Path(__file__).resolve().parent

    print("Generating macro GDS cells...")

    # NMOS — default params
    generate_macro_gds(
        MosfetParams(),
        "sg13_lv_nmos",
        script_dir / "sg13_lv_nmos.gds",
    )

    # PMOS — same params but PMOS type
    generate_macro_gds(
        MosfetParams(mosfet_type=MosType.PMOS),
        "sg13_lv_pmos",
        script_dir / "sg13_lv_pmos.gds",
    )

    print("Done.")


if __name__ == "__main__":
    main()
