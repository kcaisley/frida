"""ALIGN design directory for a design in standard-cell rows, from a shared floorplan.

    uv run python flow/layout/align/make_design.py tsmc65 design/layout/comp_c040.json [--free] [--out=DIR]
    uv run python flow/layout/align/make_design.py tsmc65 build/layout/netlists/tsmc65/comp_c040_transistors.sp

Writes <DIR>/<name>/<name>.sp (DIR: build/layout/align/<pdk>/input) (the floorplan's netlist for the
PDK) and <name>.const.json: rows as ALIGN's Floorplan constraint (top first, ordered,
mirrored), vdd/vss left to the rails.

The standard cells the netlist uses are defined by their transistors (library SPICE, names
made parseable, diodes dropped) with a Generator annotation: ALIGN keeps each one a leaf
(align/pdk/stdcell.py draws it) and knows its inputs are gates and its outputs drains.

``--free`` writes <name>_free instead (a netlist given directly is always free, under its own name): no floorplan, ALIGN's own compiler defaults (parallel
and series devices merged, library primitives, arrays) and its symmetry detection; only the
supplies are declared. Identical parallel devices must be merged for the symmetry search, which
pairs every neighbour of a net uniquely.
"""

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
PDK = sys.argv[1]
sys.path[:0] = [str(ROOT / "pdk" / PDK / "layout"), str(ROOT / "flow/layout/stems")]
import netcells
import tech
from paths import STD_SPICE


def std_subckts(cells: set[str]) -> str:
    """The cells' .subckt blocks for ALIGN: transistors only, '-' in names replaced."""
    out, keep = [], False
    for line in STD_SPICE.read_text().splitlines():
        f = line.split()
        if f and f[0].lower() == ".subckt":
            keep = f[1] in cells
            if keep:  # ALIGN reads the annotation only after a lower-case .subckt
                out += [" ".join([".subckt", *f[1:]]), f"* @: Generator(name='{f[1]}')"]
            continue
        if keep and f and f[0].lower() == ".ends":
            out.append(".ends")
            keep = False
        elif keep and f and f[0][0] in "Mm":
            out.append(_nf(line.replace("-", "_")).rstrip())
    return "\n".join(out) + "\n"


def _nf(line: str) -> str:
    """ALIGN knows fingers as nf: rename a PDK's ng."""
    return re.sub(r"(?i)\bng=", "nf=", line)


arg = Path(sys.argv[2])
if arg.suffix == ".sp":  # a netlist without floorplan
    fp, src, name, free = None, arg.read_text(), arg.stem, True
else:  # the design is named after its floorplan; a free design keeps the netlist unsplit
    fp = json.loads(arg.read_text())
    name = arg.stem
    free = "--free" in sys.argv[3:]
    src = (arg.parent / fp["netlist"].format(pdk=PDK)).read_text() if free else netcells.floorplan_netlist(arg, PDK)[1]
    src = re.sub(r"(?im)^(\.subckt|\.ends)\s+\S+", rf"\1 {name}", src)
src = (
    "\n".join(_nf(l) if l[:1] in "Mm" else l for l in netcells.per_finger(src).splitlines()) + "\n"
)  # ALIGN reads w per finger
std = {}  # instance -> (cell, nets)
for line in src.splitlines():
    f = line.split()
    if f and f[0][0] in "Xx":
        std[f[0]] = (f[-1], f[1:-1])
supplies = [
    {"constraint": "PowerPorts", "ports": ["vdd"]},
    {"constraint": "GroundPorts", "ports": ["vss"]},
    {"constraint": "DoNotRoute", "nets": ["vdd", "vss"]},
]
if free and fp:
    src = re.sub(rf"\b{name}\b", f"{name}_free", src)
    name = f"{name}_free"
if free:
    const = [
        *supplies,
        # a roughly square block: the placer chooses each folded primitive's shape (gen_param.fold_rows)
        {"constraint": "AspectRatio", "ratio_low": 1 / 1.5, "ratio_high": 1.5},
    ]
    if not hasattr(tech, "LOGIC_GRID"):
        # ALIGN groups devices into its logic gates (INV, NAND2, NOR2), which only a PDK with logic
        # cells draws (stems/logiccell.py, a PDK with LOGIC_GRID); elsewhere they stay single devices
        const.append({"constraint": "DoNotUseLib", "libraries": ["INV", "INV_B", "NAND2", "NOR2"]})
else:
    const = [
        {
            "constraint": "ConfigureCompiler",
            "auto_constraint": False,
            "merge_series_devices": False,
            "merge_parallel_devices": False,
            "remove_dummy_hierarchies": False,
            "identify_array": False,
            "propagate": True,
        },
        *supplies,
        {"constraint": "Floorplan", "regions": fp["rows"], "order": True, "symmetrize": True},
    ]
out_dir = next((a.split("=", 1)[1] for a in sys.argv[3:] if a.startswith("--out=")), f"build/layout/align/{PDK}/input")
out = Path(out_dir) / name
out.mkdir(parents=True, exist_ok=True)
# the cells before the block: ALIGN's parser models an unknown cell at its first instance
(out / f"{name}.sp").write_text(std_subckts({c for c, _ in std.values()}) + "\n" + src)
(out / f"{name}.const.json").write_text(json.dumps(const, indent=1) + "\n")
print(out)
