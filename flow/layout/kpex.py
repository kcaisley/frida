"""Layout-only 3-D extraction by FasterCap through KLayout-PEX (kpex): every PDK's default extractor
of a layout by its own net names (``flow.layout.signoff.run_layout_pex``). A kit's own extractor
(``Extractor.CALIBRE``: Calibre's xACT, or Quantus where the kit has it so) is the manual check.

The PDK gives its process stack (``pdk/<tech>/kpex/stack.json``: each conductor's height and
thickness and the planar dielectrics, made from its kit's typical interconnect corner by
``stack_from_ict``) and its layers (its layout tech's ``LAYERS``, ``RULES`` and pin labels). This
module makes kpex's technology of them (``technology``): each metal with the via above it, the
dielectric of its own level (a film around it filling the level; the slabs' mean by thickness, as
the field between neighbours runs along them) and the one from its top to the next metal (the
slabs' in series, as the field between levels crosses them); and runs the extraction in kpex's own Python (``KPEX_HOME``, a
subprocess: ``kpex_extract.py``), FasterCap (``FASTERCAP``) at ``TOLERANCE`` and ``MESH`` with
Galerkin's scheme. Each net's capacitance to infinity counts to ground, as an extractor's infinite
substrate plane has it. The result is a Spectre netlist of capacitors by the layout's net names, as
the kits' extractors write theirs, so one parser reads either.

    uv run python -m flow.layout.kpex stack <ict> PO=poly M1=metal1 ...   # a PDK's stack.json, printed
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from enum import Enum, auto
from importlib import import_module
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
KPEX_HOME = Path(os.environ.get("KPEX_HOME", "/local/kcaisley/tools/kpex-env"))
FASTERCAP = Path(os.environ.get("FASTERCAP", "/local/kcaisley/tools/src/FasterCap-kpex/build/FasterCap"))
# FasterCap's settings: its relative tolerance and mesh refinement (finer moves a small structure's
# couplings by a few percent, its plate couplings by under one; docs/klayout.md)
TOLERANCE = 0.005
MESH = 0.1
# the permittivity outside kpex's model (8 um around the layout): an oxide's
K_VOID = 3.9
# the dielectric above the top metal is taken over this much (um)
TOP_SPAN_UM = 5.0
# the film of a metal's level around its shapes (um): thin, the level's permittivity
FILM_UM = 0.005


class Extractor(Enum):
    """Which tool extracts a layout: FasterCap through KLayout-PEX, the default; or the kit's own
    (Calibre's xACT, Quantus where the kit has it so), the manual check."""

    KLAYOUT = auto()
    CALIBRE = auto()


def _ict_blocks(text: str):
    """Each block of an ICT file (Cadence's interconnect technology): its kind, name and fields."""
    pattern = r'^\s*(dielectric|conductor|diffusion|via)\s+"?([A-Za-z0-9_]+)"?\s*\{(.*?)^\s*\}'
    for kind, name, body in re.findall(pattern, text, re.DOTALL | re.MULTILINE):
        yield kind, name, dict(re.findall(r"^\s*([a-z_]+)\s+([^\s{}]+)\s*$", body, re.MULTILINE))


def stack_from_ict(path: Path, names: dict[str, str]) -> dict:
    """A process stack from an ICT file: the conductors ``names`` maps (the layout's name, ``M1``, to
    the file's) by their bottoms and thicknesses (um), and every planar dielectric, bottom, top and
    permittivity. A layer's bottom is its ``height``, or its ``delta_height`` above the top of its
    ``delta_layer``; else a dielectric stacks on the planar ones before it and a conductor sits in
    the last of them, its top at theirs (a conformal film, thin, is left out)."""

    layers: dict[str, tuple[float, float]] = {}
    slabs: list[tuple[float, float, float]] = []
    top = 0.0
    for kind, name, fields in _ict_blocks(path.read_text()):
        if kind not in ("dielectric", "conductor"):
            continue
        thickness = float(fields.get("thickness", 0.0))
        if "height" in fields:
            bottom = float(fields["height"])
        elif "delta_layer" in fields:
            bottom = layers[fields["delta_layer"].strip('"')][1] + float(fields.get("delta_height", 0.0))
        else:
            bottom = top - thickness if kind == "conductor" else top
        layers[name] = (bottom, bottom + thickness)
        planar = fields.get("conformal", "FALSE").upper() != "TRUE"
        if kind == "dielectric" and planar and thickness > 0:
            slabs.append((round(bottom, 6), round(bottom + thickness, 6), float(fields["dielectric_constant"])))
            top = max(top, bottom + thickness)
    return {
        "conductors": {
            ours: {"z": round(layers[theirs][0], 6), "thickness": round(layers[theirs][1] - layers[theirs][0], 6)}
            for ours, theirs in names.items()
        },
        "dielectrics": sorted(slabs),
    }


def _k(slabs: list[list[float]], bottom: float, top: float, *, along: bool = False) -> float:
    """The permittivity of the dielectrics between two heights: in series, as a field across them
    sees it, or ``along`` them, their mean by thickness, as a field parallel to them (between two
    conductors of one level) sees it; the nearest slab's where none covers them."""
    covered = [(min(top, b) - max(bottom, a), k) for a, b, k in slabs if min(top, b) > max(bottom, a)]
    if not covered:
        return min(slabs, key=lambda slab: abs((slab[0] + slab[1]) / 2 - (bottom + top) / 2))[2]
    if along:
        return sum(span * k for span, k in covered) / sum(span for span, _k in covered)
    return sum(span for span, _k in covered) / sum(span / k for span, k in covered)


def technology(pdk: str) -> tuple[dict, dict]:
    """kpex's technology of the PDK (``stack.json`` and its layout tech), and the layers' GDS pairs,
    labels and vias the extraction joins its nets by."""

    stack = json.loads((ROOT / "pdk" / pdk / "kpex" / "stack.json").read_text())
    tech = import_module(f"pdk.{pdk}.layout.tech")
    conductors = stack["conductors"]
    metals = sorted((name for name in conductors if re.fullmatch(r"M\d+", name)), key=lambda name: int(name[1:]))
    slabs = stack["dielectrics"]

    def pair(gds: tuple[int, int]) -> dict:
        return {"layer": gds[0], "datatype": gds[1]}

    layers, computed, process = [], [], []
    process += [
        {
            "name": "subs",
            "layer_type": "LAYER_TYPE_SUBSTRATE",
            "substrate_layer": {"thickness": 0.28, "reference": "fox"},
        },
        {
            "name": "fox",
            "layer_type": "LAYER_TYPE_FIELD_OXIDE",
            "field_oxide_layer": {"dielectric_k": _k(slabs, 0.0, conductors["PO"]["z"])},
        },
    ]
    # poly first: kpex's field oxide reaches up to it, and its dielectric up to the first metal
    below = "fox"
    for name in ("PO", *metals):
        z, thickness = conductors[name]["z"], conductors[name]["thickness"]
        purpose = {"purpose": "PURPOSE_METAL", "name": name, "drw_gds_pair": pair(tech.LAYERS[name])}
        layers.append(purpose)
        computed.append(
            {"kind": "KIND_REGULAR", "layer_info": purpose, "original_layer_name": name, "process_layer_name": name}
        )
        metal: dict = {"z": z, "thickness": thickness}
        index = metals.index(name) if name in metals else -1
        above = metals[index + 1] if index + 1 < len(metals) else None
        next_z = conductors[above]["z"] if above else z + thickness + TOP_SPAN_UM
        if above and name != "PO":
            via = f"V{name[1:]}"
            rules = tech.RULES.get(via, {})
            info = {"purpose": "PURPOSE_VIA", "name": via, "drw_gds_pair": pair(tech.LAYERS[via])}
            layers.append(info)
            computed.append(
                {"kind": "KIND_REGULAR", "layer_info": info, "original_layer_name": via, "process_layer_name": via}
            )
            metal["contact_above"] = {
                "name": via,
                "layer_below": name,
                "metal_above": above,
                "thickness": round(next_z - z - thickness, 6),
                "width": rules.get("cut", 100) / 1000,
                "spacing": rules.get("space", 100) / 1000,
            }
        if name == "PO":
            next_z = conductors[metals[0]]["z"]
        process.append({"name": name, "layer_type": "LAYER_TYPE_METAL", "metal_layer": metal})
        # the metal's own level (beside it: its neighbours' lateral field) as a film around it and
        # filling the level, then the via level above it, each its own permittivity
        process.append(
            {
                "name": f"level_{name}",
                "layer_type": "LAYER_TYPE_CONFORMAL_DIELECTRIC",
                "conformal_dielectric_layer": {
                    "dielectric_k": round(_k(slabs, z, z + thickness, along=True), 4),
                    "thickness_over_metal": 0.0,
                    "thickness_where_no_metal": thickness,
                    "thickness_sidewall": FILM_UM,
                    "reference": name,
                },
            }
        )
        dielectric = f"diel_{name}"
        process.append(
            {
                "name": dielectric,
                "layer_type": "LAYER_TYPE_SIMPLE_DIELECTRIC",
                "simple_dielectric_layer": {
                    "dielectric_k": round(_k(slabs, z + thickness, next_z), 4),
                    "reference": below,
                },
            }
        )
        below = dielectric
    kpex = {
        "name": pdk,
        "layers": layers,
        "lvs_computed_layers": computed,
        "process_stack": {"layers": process},
        "substrate": {"net_names": ["GROUND"]},
    }
    # each conductor's labels: its pin layer, its pin text, any text on its drawn pair
    labels = {
        name: [
            list(gds)
            for gds in (tech.LAYERS[name], tech.LAYERS.get(f"{name}.PIN"), getattr(tech, "PIN_TEXT", {}).get(name))
            if gds
        ]
        for name in ("PO", *metals)
    }
    joins = {
        "layers": {name: [list(tech.LAYERS[name])] for name in ("PO", *metals)}
        | {f"V{name[1:]}": [list(tech.LAYERS[f"V{name[1:]}"])] for name in metals[:-1]},
        "labels": labels,
        "vias": [[name, f"V{name[1:]}", metals[i + 1]] for i, name in enumerate(metals[:-1])],
    }
    return kpex, joins


def run_layout_pex(pdk: str, gds_path: Path, layout_top: str, output_stem: str, run_dir: Path) -> Path:
    """Extract ``layout_top`` of ``gds_path`` in ``pdk`` by FasterCap, in ``run_dir/kpex/``: the
    Spectre netlist of its nets' capacitances (``<output_stem>.pex.netlist``)."""

    work = (run_dir / "kpex").resolve()
    work.mkdir(parents=True, exist_ok=True)
    kpex, joins = technology(pdk)
    (work / "tech.pb.json").write_text(json.dumps(kpex, indent=1))
    netlist = work / f"{output_stem}.pex.netlist"
    spec = {
        "gds": str(gds_path.resolve()),
        "top": layout_top,
        "tech": str(work / "tech.pb.json"),
        **joins,
        "out_dir": str(work),
        "netlist": str(netlist),
        "fastercap": str(FASTERCAP),
        "tolerance": TOLERANCE,
        "mesh": MESH,
        "galerkin": True,
        "k_void": K_VOID,
        "threads": int(os.environ.get("KPEX_THREADS", "4")),
    }
    (work / "spec.json").write_text(json.dumps(spec, indent=1))
    log = work / "kpex.log"
    with log.open("w") as stream:
        result = subprocess.run(
            # -P: the script's folder (this one, with a kpex.py of its own) stays off its path
            [
                str(KPEX_HOME / "bin" / "python"),
                "-P",
                str(Path(__file__).with_name("kpex_extract.py")),
                str(work / "spec.json"),
            ],
            stdout=stream,
            stderr=subprocess.STDOUT,
            cwd=work,
            check=False,
        )
    if result.returncode or not netlist.is_file():
        raise RuntimeError(f"KLayout-PEX extraction of {layout_top} failed; see {log}")
    return netlist


if __name__ == "__main__":
    if sys.argv[1:2] == ["stack"]:
        names = dict(arg.split("=", 1) for arg in sys.argv[3:])
        print(json.dumps(stack_from_ict(Path(sys.argv[2]), names), indent=1))
