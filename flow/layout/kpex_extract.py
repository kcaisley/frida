"""One layout-only extraction by FasterCap through KLayout-PEX's library, run by kpex's own Python
(``flow.layout.kpex.run_layout_pex`` writes its inputs and starts it): this file imports KLayout and
klayout_pex alone.

    <kpex python> kpex_extract.py <spec.json>

The spec holds the GDS, its top cell, kpex's technology (a JSON file), each conductor's GDS pairs
and its labels', the vias that join the conductors, FasterCap's executable and settings, and the
netlist to write. The layout's nets are found by KLayout (each conductor joined to itself, each via
to the conductors above and below it, each label naming the net under it), kpex turns them into
FasterCap's model, and FasterCap's Maxwell matrix becomes a Spectre netlist of capacitors between the
nets by their labels, a net's capacitance to infinity (its row sum) to ground, ``0``, as an
extractor whose substrate is an infinite plane counts it.
"""

import json
import os
import sys
from pathlib import Path

import klayout.db as kdb
from klayout_pex.fastercap.fastercap_input_builder import FasterCapInputBuilder
from klayout_pex.fastercap.fastercap_runner import fastercap_parse_capacitance_matrix, run_fastercap
from klayout_pex.klayout.lvsdb_extractor import KLayoutExtractionContext
from klayout_pex.tech_info import TechInfo


def nets(spec: dict) -> kdb.LayoutToNetlist:
    """The layout's nets: its conductors joined through its vias, named by its labels."""
    layout = kdb.Layout()
    layout.read(spec["gds"])
    top = layout.cell(spec["top"])
    l2n = kdb.LayoutToNetlist(kdb.RecursiveShapeIterator(layout, top, []))
    regions = {}
    for name, pairs in spec["layers"].items():
        indexes = [index for layer, datatype in pairs if (index := layout.find_layer(layer, datatype)) is not None]
        if len(indexes) == 1:
            region = l2n.make_layer(indexes[0], name)
        elif not indexes:
            region = l2n.make_layer(name)  # empty: the layout has none of it
        else:
            region = l2n.make_layer(indexes[0])
            for index in indexes[1:]:
                region += l2n.make_layer(index)
            l2n.register(region, name)
        l2n.connect(region)
        regions[name] = region
    for name, pairs in spec["labels"].items():
        for number, (layer, datatype) in enumerate(pairs):
            index = layout.find_layer(layer, datatype)
            if index is not None:
                l2n.connect(regions[name], l2n.make_text_layer(index, f"{name}_label{number}"))
    for below, via, above in spec["vias"]:
        l2n.connect(regions[below], regions[via])
        l2n.connect(regions[via], regions[above])
    l2n.extract_netlist()
    return l2n


def main(path: str) -> None:
    spec = json.loads(Path(path).read_text())
    out = Path(spec["out_dir"])
    out.mkdir(parents=True, exist_ok=True)
    tech = TechInfo.from_json(spec["tech"], dielectric_filter=None)
    context = KLayoutExtractionContext.prepare_extraction(
        lvsdb=nets(spec), top_cell=spec["top"], tech=tech, blackbox_devices=False
    )
    builder = FasterCapInputBuilder(
        pex_context=context,
        tech_info=tech,
        substrate_net_name=context.substrate_net_name,
        k_void=spec["k_void"],
        delaunay_amax=50.0,
        delaunay_b=0.5,
    )
    model = builder.build()
    inputs = out / "FasterCap_Input_Files"
    inputs.mkdir(exist_ok=True)
    lst = model.write_fastcap(output_dir_path=str(inputs), prefix="FasterCap_Input_")[0]
    os.environ["OMP_NUM_THREADS"] = str(spec["threads"])
    log = out / "FasterCap_Output.txt"
    run_fastercap(
        exe_path=spec["fastercap"],
        lst_file_path=lst,
        log_path=str(log),
        tolerance=spec["tolerance"],
        d_coeff=0.5,
        mesh_refinement_value=spec["mesh"],
        ooc_condition=None,
        auto_preconditioner=True,
        galerkin_scheme=spec["galerkin"],
        jacobi_preconditioner=False,
    )
    matrix = fastercap_parse_capacitance_matrix(str(log)).averaged_off_diagonals()
    matrix.write_csv(str(out / "FasterCap_Result_Matrix_Avg.csv"))
    # FasterCap names its conductors g<index>_<net>; the substrate's net is ground
    names = [name.split("_", 1)[1] for name in matrix.conductor_names]
    ground = context.substrate_net_name
    node = {name: "0" if name == ground else name for name in names}
    lines = [
        "// FasterCap through KLayout-PEX, by the layout's net names; each net's capacitance to infinity to ground",
        "simulator lang=spectre",
        f"subckt {spec['top']} ( {' '.join(name for name in names if name != ground)} )",
    ]
    count = 0
    for i, first in enumerate(names):
        for j in range(i + 1, len(names)):
            value = -matrix[i][j]
            if value > 0:
                lines.append(f"c_{count} ( {node[first]} {node[names[j]]} ) capacitor c={value * 1e15:.6g}f")
                count += 1
        if first != ground:
            infinity = sum(matrix[i])
            if infinity > 0:
                lines.append(f"c_{count} ( {node[first]} 0 ) capacitor c={infinity * 1e15:.6g}f")
                count += 1
    lines.append(f"ends {spec['top']}")
    Path(spec["netlist"]).write_text("\n".join(lines) + "\n")


if __name__ == "__main__":
    main(sys.argv[1])
