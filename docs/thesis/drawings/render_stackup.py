"""The thesis's 3-D scenes: chapter 1's sensor and readout arrangements, each a section through
the middle of two pixels of a real layout (seen nearly square on, with a little depth), with what
the layouts do not draw (silicon, oxide, passivation, bumps, redistribution, through-silicon vias),
and the FRIDA-1 test board; rendered by Blender (stackup_blender.py) into
docs/thesis/figures/stack_<scene>.png, and the sections also as .glb for the web page.

    uv run python docs/thesis/drawings/render_stackup.py [SCENE ...]

The layout pieces are small clips of other chips' layouts (clip_layout.py), kept with their layer
roles outside the repository, in ``FRIDA_STACKUPS`` (default the main checkout's build/stackups):
``<piece>.gds`` and ``layers.toml``, a table per piece mapping our generic roles to that piece's
GDS layer and datatype (a piece from one of our kits takes most from the kit's own map). Nothing
of any foundry's process is written here: the silicon's depths and the metal stack's height are
round sizes after published cross-sections (wells some 1.5 µm, a 30 µm epitaxial layer, some
10 µm of metal and 8 µm of passivation, 30 µm bumps), the metals spread evenly over that height.
"""

from __future__ import annotations

import json
import math
import os
import shutil
import subprocess
import sys
import tempfile
import tomllib
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.append(str(ROOT))  # the kits (pdk/) of the checkout, unless PYTHONPATH names others
import check

STACKUPS = Path(os.environ.get("FRIDA_STACKUPS") or Path(check.TOOLS).parent / "stackups")
FIGURES = HERE.parent / "figures"
SITE = ("klayout==0.30.13", "pyyaml==6.0.3")  # Blender's own Python lacks them

# the web viewer's palette (flow/web/static/js/layers.js): M1, M2, ... and the vias above each
METALS = ["#5E81AC", "#B48EAD", "#D08770", "#EBCB8B", "#8FBCBB", "#88C0D0", "#81A1C1", "#A3BE8C", "#BF616A"]
FIXED = {
    "OD": {"color": "#A3BE8C", "roughness": 0.6},
    "PO": {"color": "#BF616A", "roughness": 0.55},
    "CO": {"color": "#4C566A", "metallic": 0.5, "roughness": 0.4},
    "NW": {"color": "#8FBCBB", "roughness": 0.7, "alpha": 0.55},
    "PW": {"color": "#D08770", "roughness": 0.7, "alpha": 0.35},
    "DNW": {"color": "#81A1C1", "roughness": 0.7, "alpha": 0.45},
    "NP": {"color": "#88C0D0", "roughness": 0.7, "alpha": 0.6},
    "PP": {"color": "#D08770", "roughness": 0.7, "alpha": 0.6},
    "MIM": {"color": "#EBCB8B", "metallic": 0.6, "roughness": 0.35},
    "DPW": {"color": "#D08770", "roughness": 0.7, "alpha": 0.45},
    "NLAYER": {"color": "#88C0D0", "roughness": 0.7, "alpha": 0.5},
    "PAD": {"color": "#D8DEE9", "metallic": 0.85, "roughness": 0.3},
}
SILICON = {"color": "#9AA3B5", "roughness": 0.55}
SURFACE = {"color": "#C9D1DE", "roughness": 0.5, "alpha": 0.28}  # the silicon holding the wells
SENSOR = {"color": "#C3CEDC", "roughness": 0.5}
EPI = {"color": "#A9B6C9", "roughness": 0.55}
SOLDER = {"color": "#C5C9CF", "metallic": 0.9, "roughness": 0.25}
COPPER = {"color": "#D08770", "metallic": 0.9, "roughness": 0.3}
ALUMINIUM = {"color": "#D8DEE9", "metallic": 0.9, "roughness": 0.3}


def metal(n: int) -> dict:
    return {"color": METALS[(n - 1) % len(METALS)], "metallic": 0.55, "roughness": 0.35}


def via(n: int) -> dict:
    return {"color": METALS[n % len(METALS)], "metallic": 0.55, "roughness": 0.35}


def nominal_stack(roles: dict[str, list[int]], scale: float) -> list[dict]:
    """The piece's layers at the viewer's nominal heights (µm, times ``scale``): metal n from
    0.3 + 0.28 (n - 1) up 0.14, its via up to the next, the front end under them, wells below the
    surface; a pad (PAD) a little above the top metal."""

    def metal_z(n: int) -> tuple[float, float]:
        bottom = 0.3 + (n - 1) * 0.28
        return bottom, 0.14

    top = max((int(role[1:]) for role in roles if role[0] == "M" and role[1:].isdigit()), default=0)
    layers = []
    for role, number in roles.items():
        if role == "BUMP":  # an opening, where a bump goes: placed, not drawn
            continue
        if role[0] == "M" and role[1:].isdigit():
            z, height = metal_z(int(role[1:]))
            style = metal(int(role[1:]))
        elif role[0] == "V" and role[1:].isdigit():
            n = int(role[1:])
            below, above = metal_z(n), metal_z(n + 1)
            z, height = below[0] + below[1], above[0] - below[0] - below[1]
            style = via(n)
        elif role == "PAD":
            z, height = metal_z(top)[0] + 0.14, 0.3
            style = FIXED[role]
        else:
            z, height = {
                "OD": (0.0, 0.06),
                "PO": (0.06, 0.08),
                "CO": (0.06, 0.24),
                "MIM": (metal_z(max(top - 1, 1))[0] + 0.16, 0.04),
                "NW": (-0.5, 0.5),
                "PW": (-0.45, 0.45),
                "DNW": (-0.9, 0.35),
                "NP": (-0.08, 0.08),
                "PP": (-0.08, 0.08),
                "DPW": (-1.0, 0.6),
                "NLAYER": (-1.9, 0.6),
            }[role]
            style = FIXED[role]
        layers.append({"name": role, "gds": number, "z": z * scale, "height": height * scale, "material": style})
    return layers


def piece(name: str, roles: tuple[str, ...], kit: str | None = None) -> tuple[str, dict[str, list[int]]]:
    """A clipped piece's GDS and the layers of the roles named: from the kit's own map where the
    piece is in one of ours (``kit``), else or besides from the piece's table in layers.toml."""

    import importlib

    table = dict(importlib.import_module(f"pdk.{kit}.layout.tech").LAYERS) if kit else {}
    table.update(tomllib.loads((STACKUPS / "layers.toml").read_text()).get(name, {}))
    layers = {role: list(table[role]) for role in roles if table.get(role)}
    return str(STACKUPS / f"{name}.gds"), layers


def shapes(gds: str, layer: list[int], cell: str | None = None) -> list[tuple[float, float, float, float]]:
    """A layer's merged shapes in a piece, as boxes (µm): where its bumps or pixels are."""

    import klayout.db as kdb

    layout = kdb.Layout()
    layout.read(gds)
    top = layout.cell(cell) if cell else layout.top_cells()[0]
    region = kdb.Region(top.begin_shapes_rec(layout.find_layer(*layer))).merged()
    return [(b.left, b.bottom, b.right, b.top) for b in (p.bbox().to_dtype(layout.dbu) for p in region.each())]


def centre(box: tuple[float, float, float, float]) -> tuple[float, float]:
    return (box[0] + box[2]) / 2, (box[1] + box[3]) / 2


# ----------------------------------------------------------------------- the cross-sections' look
# as pixel cross-sections are usually drawn: n-type red and p-type blue (the deeper wells darker,
# the low-dose silicon light), the transistors' gates green, the metals grey (their vias and
# contacts lighter) in a cream dielectric under a pale green passivation, as a foundry draws its
# stack. Each role's last number is how far (µm)
# it stands proud of the cut and of the visible side, so overlapping wells and implants show in
# order (implants over wells over deep wells) instead of flickering in one plane.
METAL_LOOK = {"color": "#7D838C", "roughness": 0.6}
VIA_LOOK = {"color": "#AEB3BA", "roughness": 0.6}
LOOK = {
    "NPLUS": ({"color": "#C8414F", "roughness": 0.6}, 0.09),
    "PPLUS": ({"color": "#3D6CC0", "roughness": 0.6}, 0.09),
    "NW": ({"color": "#E27D86", "roughness": 0.6}, 0.06),
    "PW": ({"color": "#7FA6E6", "roughness": 0.6}, 0.06),
    "DPW": ({"color": "#2A4BA6", "roughness": 0.6}, 0.045),
    "DNW": ({"color": "#A3283A", "roughness": 0.6}, 0.03),
    "NLAYER": ({"color": "#F2C7CB", "roughness": 0.6}, 0.02),
    "PO": ({"color": "#8CBF6A", "roughness": 0.5}, 0.1),
    "CO": (VIA_LOOK, 0.11),
    "MIM": (METAL_LOOK, 0.08),
    "PAD": ({"color": "#969CA4", "roughness": 0.6}, 0.07),
}
LOW_P = {"color": "#D5E3F3", "roughness": 0.6}  # low-dose p: an epitaxial layer, a high-resistivity substrate
P_SUBSTRATE = {"color": "#B3C8E3", "roughness": 0.6}  # the substrate under an epitaxial layer
OXIDE = {"color": "#F4EDD3", "roughness": 0.8}
PASSIVATION = {"color": "#CFEBCF", "roughness": 0.8}
UBM = {"color": "#5E636B", "roughness": 0.6}  # the metal under a bump, lining its opening
ETCH_STOP = {"color": "#DCD1A8", "roughness": 0.8}  # the thin layers between the dielectric's levels
DRAWN = {"matte": True, "outline": 1.2}  # a section's look: flat colours, every structure edged
BEOL = 14.0  # µm from the silicon to the top metal's top, whatever the metal count (some 10 µm, drawn taller)
PASSIVATION_THICKNESS = 8.0
BUMP = 30.0  # µm across


def section_stack(roles: list[str], depths: dict[str, tuple[float, float]]) -> list[dict]:
    """The roles' heights (µm): the silicon's from ``depths`` (top, bottom; below the surface at
    0), the gates and contacts on it, the metals evenly up to BEOL (the top metal thicker, each via
    above its metal), a pad (PAD) on the top metal; each with its look and its priority."""

    metals = [int(role[1:]) for role in roles if role[0] == "M" and role[1:].isdigit()]
    top = max(metals, default=1)
    pitch = (BEOL - 1.0) / (top - 0.2)

    def metal_z(n: int) -> float:
        return 1.0 + (n - 1) * pitch

    layers = []
    for role in roles:
        if role[0] == "M" and role[1:].isdigit():
            n = int(role[1:])
            z, height, look = metal_z(n), (0.8 if n == top else 0.45) * pitch, (METAL_LOOK, 0.06)
        elif role[0] == "V" and role[1:].isdigit():
            n = int(role[1:])
            z, height, look = metal_z(n) + 0.45 * pitch, 0.55 * pitch, (VIA_LOOK, 0.07)
        elif role in depths:
            upper, lower = depths[role]
            z, height, look = lower, upper - lower, LOOK[role]
        else:
            z, height = {
                "PO": (0.0, 0.25),
                "CO": (0.0, 1.0),
                "MIM": (metal_z(max(top - 1, 1)) + 0.55 * pitch, 0.12 * pitch),
                "PAD": (BEOL, 1.5),
            }[role]
            look = LOOK[role]
        layers.append({"name": role, "z": z, "height": height, "material": look[0], "priority": look[1]})
    return layers


def role_piece(
    name: str,
    kit: str | None,
    sources: tuple[str, ...],
    derived: dict[str, str],
    box: list[float],
    keep: tuple[str, ...],
) -> tuple[str, dict[str, list[int]]]:
    """A section's area of a piece with only the roles it draws, each on a layer of its own
    (1000 + its index, nothing of the foundry's numbering), written beside the pieces: the source
    roles as the piece has them, the derived ones (``derived``: "A & B", "A - B", "A | B" of
    source roles) such as a diffusion's n+ part or the deep p-well under the electronics."""

    import hashlib

    import klayout.db as kdb

    gds, numbers = piece(name, sources, kit=kit)
    layout = kdb.Layout()
    layout.read(gds)
    top = layout.top_cells()[0]
    clip = kdb.Region(kdb.DBox(*box).to_itype(layout.dbu))

    def region(role: str) -> kdb.Region:
        index = layout.find_layer(*numbers[role]) if role in numbers else None
        return (kdb.Region(top.begin_shapes_rec(index)) & clip).merged() if index is not None else kdb.Region()

    regions = {role: region(role) for role in sources}
    for role, expression in derived.items():
        left, operator, right = expression.split()
        a, b = regions[left], regions[right]
        regions[role] = {"&": a & b, "-": a - b, "|": a | b}[operator]
    key = hashlib.sha1(json.dumps([name, sources, derived, box, keep]).encode()).hexdigest()[:10]
    out = STACKUPS / "roles" / f"{name}_{key}.gds"
    out.parent.mkdir(parents=True, exist_ok=True)
    target = kdb.Layout()
    target.dbu = layout.dbu
    cell = target.create_cell("section")
    layers = {}
    for index, role in enumerate(keep):
        layers[role] = [1000 + index, 0]
        cell.shapes(target.layer(1000 + index, 0)).insert(regions.get(role, kdb.Region()))
    target.write(str(out))
    return str(out), layers


def section_part(
    name: str,
    gds: str,
    layers: dict[str, list[int]],
    stack: list[dict],
    crop: list[float],
    origin: list[float],
    grow: tuple[str, ...],
    **place,
) -> dict:
    """A layout part of a role piece: each layer cropped to the section, standing proud of the
    cut and the visible side (``grow``: of x0, y0, x1, y1) by its priority."""

    sides = {"x0": (0, -1), "y0": (1, -1), "x1": (2, 1), "y1": (3, 1)}
    parts = []
    for layer in stack:
        if layer["name"] not in layers:
            continue
        box = list(crop)
        for side in grow:
            index, sign = sides[side]
            box[index] += sign * layer["priority"]
        parts.append({**{k: v for k, v in layer.items() if k != "priority"}, "gds": layers[layer["name"]], "crop": box})
    return {"kind": "layout", "name": name, "gds": gds, "crop": crop, "origin": origin, "layers": parts, **place}


def slabs(
    x: tuple[float, float], y: tuple[float, float], spans: list[tuple[float, float, dict]], name: str = "silicon"
) -> list[dict]:
    """Boxes over the section's footprint: silicon under the surface, oxide and passivation
    over it (``spans``: bottom, top, look)."""

    return [
        {"kind": "box", "name": f"{name}{n}", "min": [x[0], y[0], z0], "max": [x[1], y[1], z1], "material": look}
        for n, (z0, z1, look) in enumerate(spans)
    ]


def etch_stops(
    stack: list[dict],
    x: tuple[float, float],
    y: tuple[float, float],
    z: float = 0.0,
    flip: bool = False,
    proud: tuple[str, ...] = ("y1", "x1"),
) -> list[dict]:
    """Thin layers across the oxide at each metal level's foot (as a dielectric is built level by
    level), standing a little proud of the oxide's faces but behind the metals' (``proud``)."""

    lo, hi = [x[0], y[0]], [x[1], y[1]]
    for side in proud:
        index = {"x": 0, "y": 1}[side[0]]
        if side[1] == "1":
            hi[index] += 0.02
        else:
            lo[index] -= 0.02
    parts = []
    for layer in stack:
        if layer["name"][0] == "M" and layer["name"][1:].isdigit():
            foot = layer["z"] - 0.08
            z0, z1 = (z - foot - 0.16, z - foot) if flip else (z + foot, z + foot + 0.16)
            box = {"min": [lo[0], lo[1], z0], "max": [hi[0], hi[1], z1]}
            parts.append({"kind": "box", "name": f"etch_stop_{layer['name']}", **box, "material": ETCH_STOP})
    return parts


SECTION_CAMERA = {"elevation": 12, "fov": 16}  # nearly square on to the cut: a drawn section with a little depth


def mono_pixel() -> dict:
    """Monolithic, readout in each pixel: two of TJ-Monopix2's 33 µm pixels cut through their
    collection electrodes: the p-wells and n-wells of the electronics over the deep p-well, the
    low-dose n-layer with its gaps at the pixel edges, inside the 30 µm epitaxial layer, on the
    substrate (the chip thinned to 50 µm)."""

    sources = (
        "NW",
        "DPW",
        "NLAYER",
        "OD",
        "NP",
        "PP",
        "PO",
        "CO",
        *(f"M{n}" for n in range(1, 7)),
        *(f"V{n}" for n in range(1, 6)),
    )
    gds, numbers = piece("tjmonopix2_2x2", sources, kit="tower180")
    pixels = sorted((centre(box) for box in shapes(gds, numbers["NLAYER"])), key=lambda c: (round(c[1]), c[0]))
    middle = pixels[len(pixels) // 2]
    row = sorted((c for c in pixels if abs(c[1] - middle[1]) < 1), key=lambda c: abs(c[0] - middle[0]))
    a, b = sorted(row[:2])
    pitch, depth = b[0] - a[0], 12.0  # the slab behind the cut
    crop = [a[0] - pitch / 2, a[1] - depth, b[0] + pitch / 2, a[1]]
    keep = (
        "NPLUS",
        "PPLUS",
        "NW",
        "PW",
        "DPW",
        "NLAYER",
        "PO",
        "CO",
        *(f"M{n}" for n in range(1, 7)),
        *(f"V{n}" for n in range(1, 6)),
    )
    derived = {"NPLUS": "OD & NP", "PPLUS": "OD & PP", "PW": "DPW - NW"}
    roles_gds, layers = role_piece(
        "tjmonopix2_2x2", "tower180", sources, derived, [crop[0] - 1, crop[1] - 1, crop[2] + 1, crop[3] + 1], keep
    )
    depths = {
        "NPLUS": (0, -0.3),
        "PPLUS": (0, -0.3),
        "NW": (0, -1.5),
        "PW": (0, -1.5),
        "DPW": (-1.5, -3.0),
        "NLAYER": (-3.0, -8.0),
    }
    stack = section_stack(list(keep), depths)
    beol = max(layer["z"] + layer["height"] for layer in stack)
    x, y = (crop[0] - a[0], crop[2] - a[0]), (crop[1] - a[1], 0.0)
    spans = [
        (-50.0, -30.0, P_SUBSTRATE),
        (-30.0, 0.0, LOW_P),
        (0.0, beol, OXIDE),
        (beol, beol + PASSIVATION_THICKNESS, PASSIVATION),
    ]
    return {
        "camera": {"azimuth": 78, **SECTION_CAMERA},
        **DRAWN,
        "parts": [
            section_part("chip", roles_gds, layers, stack, crop, [a[0], a[1]], ("y1", "x1"), z=0.0),
            *slabs(x, y, spans),
            *etch_stops(stack, x, y),
        ],
    }


def mono_edge() -> dict:
    """Monolithic, readout at the matrix edge: a 3T test matrix's first column cut down its
    middle, two pixels and the column readout at the matrix's edge: each pixel's electronics in
    p-wells and n-wells over a deep p-well, inside the very deep n-well that collects the charge,
    in the high-resistivity substrate (the chip thinned to 50 µm)."""

    sources = ("NW", "PW", "DNW", "OD", "NP", "PP", "PO", "CO", "M1", "V1", "M2", "V2", "M3", "V3", "M4", "MIM")
    pitch, x0, row = 76.04, 848.18, 1774.9  # the matrix's pitch, first column and bottom row
    cut, depth = x0 + pitch / 2, 12.0
    crop = [cut - depth, 1680.0, cut, row + 2 * pitch]
    keep = ("NPLUS", "PPLUS", "NW", "PW", "DPW", "DNW", "PO", "CO", "M1", "V1", "M2", "V2", "M3", "V3", "M4", "MIM")
    derived = {"NPLUS": "OD & NP", "PPLUS": "OD & PP", "DPW": "PW & DNW"}
    roles_gds, layers = role_piece(
        "lf3t_edge", None, sources, derived, [crop[0] - 1, crop[1] - 1, crop[2] + 1, crop[3] + 1], keep
    )
    depths = {
        "NPLUS": (0, -0.3),
        "PPLUS": (0, -0.3),
        "NW": (0, -1.5),
        "PW": (0, -1.5),
        "DPW": (-1.5, -3.0),
        "DNW": (-1.5, -7.0),
    }
    stack = section_stack(list(keep), depths)
    beol = max(layer["z"] + layer["height"] for layer in stack)
    x, y = (-depth, 0.0), (0.0, crop[3] - crop[1])
    return {
        "camera": {"azimuth": 12, **SECTION_CAMERA},
        **DRAWN,
        "parts": [
            section_part("chip", roles_gds, layers, stack, crop, [cut, crop[1]], ("x1", "y1"), z=0.0),
            *slabs(x, y, [(-50.0, 0.0, LOW_P), (0.0, beol, OXIDE), (beol, beol + PASSIVATION_THICKNESS, PASSIVATION)]),
            *etch_stops(stack, x, y, proud=("x1", "y1")),
        ],
    }


def hybrid_pixel() -> dict:
    """Hybrid, readout in each pixel: two of ITkPix-V1's 50 µm pixels cut through their bump
    pads, a passive CMOS sensor's pixels flipped onto them through 30 µm solder bumps, each in
    tapered openings of the two passivations lined with the metal under the bump (the chip
    thinned to 50 µm, the sensor 100 µm)."""

    chip_sources = (
        "NW",
        "DNW",
        "OD",
        "NP",
        "PP",
        "PO",
        "CO",
        *(f"M{n}" for n in range(1, 10)),
        *(f"V{n}" for n in range(1, 9)),
        "AP",
        "BUMP",
    )
    gds, numbers = piece("itkpix_core", chip_sources, kit="tsmc65")
    bumps = sorted((centre(box) for box in shapes(gds, numbers["BUMP"])), key=lambda c: (round(c[1]), c[0]))
    middle = bumps[len(bumps) // 2]
    row = sorted((c for c in bumps if abs(c[1] - middle[1]) < 1), key=lambda c: abs(c[0] - middle[0]))
    a, b = sorted(row[:2])
    pitch, depth = b[0] - a[0], 16.0
    crop = [a[0] - pitch / 2, a[1] - depth, b[0] + pitch / 2, a[1]]
    keep = (
        "NPLUS",
        "PPLUS",
        "NW",
        "DNW",
        "PO",
        "CO",
        *(f"M{n}" for n in range(1, 10)),
        *(f"V{n}" for n in range(1, 9)),
        "PAD",
    )
    derived = {"NPLUS": "OD & NP", "PPLUS": "OD & PP", "PAD": "AP | AP"}
    chip_gds, chip_layers = role_piece(
        "itkpix_core", "tsmc65", chip_sources, derived, [crop[0] - 1, crop[1] - 1, crop[2] + 1, crop[3] + 1], keep
    )
    chip_stack = section_stack(
        list(keep), {"NPLUS": (0, -0.25), "PPLUS": (0, -0.25), "NW": (0, -1.2), "DNW": (-1.2, -2.2)}
    )
    beol = max(layer["z"] + layer["height"] for layer in chip_stack if layer["name"] != "PAD")
    pad_top = beol + 1.5
    chip_face = beol + PASSIVATION_THICKNESS
    gap = 12.0  # between the two passivations
    sensor_face = chip_face + gap + PASSIVATION_THICKNESS  # the sensor's top metal, face down

    sensor_sources = ("NW", "PW", "OD", "NP", "PP", "PO", "CO", "M1", "V1", "M2", "V2", "M3")
    s_centre = (1600.0, 1600.0)  # a sensor pixel's centre (its bump pad), over the first bump
    s_crop = [
        s_centre[0] - pitch / 2,
        s_centre[1],
        s_centre[0] + 1.5 * pitch,
        s_centre[1] + depth,
    ]  # flipped: y turns over
    s_keep = ("NPLUS", "PPLUS", "NW", "PW", "PO", "CO", "M1", "V1", "M2", "V2", "M3")
    s_derived = {"NPLUS": "OD & NP", "PPLUS": "OD & PP"}
    sensor_gds, sensor_layers = role_piece(
        "lf_sensor_array",
        None,
        sensor_sources,
        s_derived,
        [s_crop[0] - 1, s_crop[1] - 1, s_crop[2] + 1, s_crop[3] + 1],
        s_keep,
    )
    sensor_stack = section_stack(
        list(s_keep), {"NPLUS": (0, -0.3), "PPLUS": (0, -0.3), "NW": (0, -2.5), "PW": (0, -1.5)}
    )
    s_beol = max(layer["z"] + layer["height"] for layer in sensor_stack)
    surface = sensor_face + s_beol  # the sensor's silicon surface, its bulk above
    x, y = (crop[0] - a[0], crop[2] - a[0]), (-depth, 0.0)
    narrow, wide = 9.0, 13.0  # the openings' radii at the pad and at the passivation's face
    chip_openings = [{"centre": [p[0] - a[0], 0.0], "radius": narrow, "top_radius": wide} for p in (a, b)]
    sensor_openings = [{"centre": [p[0] - a[0], 0.0], "radius": wide, "top_radius": narrow} for p in (a, b)]
    parts = [
        section_part("chip", chip_gds, chip_layers, chip_stack, crop, [a[0], a[1]], ("y1", "x1"), z=0.0),
        *slabs(x, y, [(-50.0, 0.0, P_SUBSTRATE), (0.0, beol, OXIDE)], "chip"),
        {
            "kind": "box",
            "name": "chip_passivation",
            "min": [x[0], y[0], beol],
            "max": [x[1], y[1], chip_face],
            "material": PASSIVATION,
            "holes": chip_openings,
        },
        *etch_stops(chip_stack, x, y),
        section_part(
            "sensor",
            sensor_gds,
            sensor_layers,
            sensor_stack,
            s_crop,
            list(s_centre),
            ("y0", "x1"),
            z=surface,
            flip=True,
        ),
        *slabs(x, y, [(sensor_face, surface, OXIDE), (surface, surface + 100.0, LOW_P)], "sensor"),
        {
            "kind": "box",
            "name": "sensor_passivation",
            "min": [x[0], y[0], sensor_face - PASSIVATION_THICKNESS],
            "max": [x[1], y[1], sensor_face],
            "material": PASSIVATION,
            "holes": sensor_openings,
        },
        *etch_stops(sensor_stack, x, y, z=surface, flip=True),
    ]
    section = {"axis": "y", "at": 0.08}  # proud of the slabs at the cut, so the sections show
    neck = {"axis": "y", "at": 0.07}  # the solder in the openings, just behind the bump's section
    liner = {"axis": "y", "at": 0.09}  # the liners in front of both
    for n, p in enumerate((a, b)):
        cx = p[0] - a[0]
        parts += [
            # each opening lined with the metal under the bump, the solder filling it and swelling between
            {
                "kind": "frustum",
                "name": f"liner_chip{n}",
                "centre": [cx, 0.0],
                "z": [pad_top - 0.6, chip_face],
                "radius": [narrow, wide],
                "shell": 0.7,
                "material": UBM,
                "cut": liner,
            },
            {
                "kind": "frustum",
                "name": f"liner_sensor{n}",
                "centre": [cx, 0.0],
                "z": [sensor_face - PASSIVATION_THICKNESS, sensor_face + 0.6],
                "radius": [wide, narrow],
                "shell": 0.7,
                "material": UBM,
                "cut": liner,
            },
            {
                "kind": "frustum",
                "name": f"neck_chip{n}",
                "centre": [cx, 0.0],
                "z": [pad_top, chip_face + 0.5],
                "radius": [narrow - 0.7, wide - 0.6],
                "material": SOLDER,
                "cut": neck,
            },
            {
                "kind": "frustum",
                "name": f"neck_sensor{n}",
                "centre": [cx, 0.0],
                "z": [sensor_face - PASSIVATION_THICKNESS - 0.5, sensor_face],
                "radius": [wide - 0.6, narrow - 0.7],
                "material": SOLDER,
                "cut": neck,
            },
            {
                "kind": "bump",
                "name": f"bump{n}",
                "centre": [cx, 0.0, (chip_face + sensor_face - PASSIVATION_THICKNESS) / 2],
                "radius": BUMP / 2,
                "height": gap + 6.0,
                "material": SOLDER,
                "cut": section,
            },
        ]
    return {"camera": {"azimuth": 78, **SECTION_CAMERA}, **DRAWN, "parts": parts}


def hybrid_super() -> dict:
    """Hybrid, readout grouped (a sketch after CoRDIA's superpixel, Marras et al. 2024): sixteen
    sensor pixels (4 x 4 of the passive sensor's, flipped) bumped onto the readout chip's top
    metal, where redistribution lines bring the sixteen inputs together to a compact cluster of
    front ends, their correlated double sampling and one shared ADC (FRIDA-1's, from its
    layout), beside the readout lines and a through-silicon via; cut through a row of bumps, the
    passivations left out so the redistribution shows."""

    pitch = 50.0
    columns = [25.0 + pitch * i for i in range(4)]
    rows = [0.0 - pitch * j for j in range(4)]  # the first row cut through its bumps' centres
    width, low = 200.0, -175.0
    adc_box = [419.91, 443.53, 480.41, 478.0]  # half of an ADC of FRIDA-1's, cut through its middle
    adc_sources = ("OD", "NP", "PP", "NW", "PO", "CO", *(f"M{n}" for n in range(1, 8)), *(f"V{n}" for n in range(1, 7)))
    adc_keep = ("NPLUS", "PPLUS", "NW", "PO", "CO", *(f"M{n}" for n in range(1, 8)), *(f"V{n}" for n in range(1, 7)))
    adc_gds, adc_layers = role_piece_die(
        adc_sources,
        {"NPLUS": "OD & NP", "PPLUS": "OD & PP"},
        [adc_box[0] - 1, adc_box[1] - 1, adc_box[2] + 1, adc_box[3] + 1],
        adc_keep,
    )
    adc_stack = section_stack(list(adc_keep), {"NPLUS": (0, -0.25), "PPLUS": (0, -0.25), "NW": (0, -1.2)})
    beol = BEOL
    rdl = beol + 1.0  # the redistribution over the top metal
    gap = 12.0
    face = beol + PASSIVATION_THICKNESS + gap + PASSIVATION_THICKNESS
    fe_top = 0.6 * beol
    section = {"axis": "y", "at": 0.08}
    parts = [
        {"kind": "box", "name": "substrate", "min": [0, low, -50.0], "max": [width, 0, -0.01], "material": P_SUBSTRATE},
        section_part(
            "adc", adc_gds, adc_layers, adc_stack, adc_box, [adc_box[0], adc_box[3]], ("y1",), z=0.0, at=[124.0, 0.0]
        ),
        {
            "kind": "box",
            "name": "cds",
            "min": [102.0, -96.0, 0],
            "max": [120.0, 0, fe_top],
            "material": {"color": "#EBCB8B", "roughness": 0.5},
        },
        {
            "kind": "box",
            "name": "readout",
            "min": [8.0, -132.0, 0],
            "max": [192.0, -112.0, fe_top],
            "material": {"color": "#B48EAD", "roughness": 0.5},
        },
        {
            "kind": "cylinder",
            "name": "tsv",
            "centre": [193.0, -22.0],
            "z": [-50.5, 0.3 * beol],
            "radius": 6.0,
            "material": COPPER,
        },
        {
            "kind": "cylinder",
            "name": "tsv_liner",
            "centre": [193.0, -22.0],
            "z": [-50.5, 0.3 * beol],
            "radius": 7.0,
            "material": {"color": "#A3BE8C", "roughness": 0.5, "alpha": 0.45},
        },
    ]
    inputs = {}
    for i in range(4):  # the front ends: 4 x 4 blocks, their inputs at their tops
        for j in range(4):
            x0, y0 = 10.0 + 22.0 * i, -96.0 + 24.0 * j
            parts.append(
                {
                    "kind": "box",
                    "name": f"fe{i}{j}",
                    "min": [x0, y0, 0],
                    "max": [x0 + 20.0, min(y0 + 22.0, -0.01), fe_top],
                    "material": {"color": "#5E81AC", "roughness": 0.5},
                }
            )
            inputs[i, j] = (x0 + 10.0, y0 + 11.0)
    # two redistribution layers: runs along y on the lower, along x on the upper, each line on its
    # own track (bump column c and row r give the offsets), vias where a line changes layer
    low_z, high_z, thick, line = rdl, rdl + 1.8, 0.8, 1.6
    pad_z = high_z + thick + 0.6
    for c, bx in enumerate(columns):
        for r, by in enumerate(rows):
            fx, fy = inputs[c, 3 - r]  # the front row of bumps to the front row of front ends
            x_run, y_run = bx + (r - 1.5) * 3.2, fy + 6.0 + (c - 1.5) * 3.2
            n = 4 * c + r
            parts += [
                {
                    "kind": "trace",
                    "name": f"rdl{n}a",
                    "points": [(bx, by), (x_run, by), (x_run, y_run)],
                    "z": low_z,
                    "width": line,
                    "height": thick,
                    "material": METAL_LOOK,
                },
                {
                    "kind": "trace",
                    "name": f"rdl{n}b",
                    "points": [(x_run, y_run), (fx, y_run)],
                    "z": high_z,
                    "width": line,
                    "height": thick,
                    "material": METAL_LOOK,
                },
                {
                    "kind": "trace",
                    "name": f"rdl{n}c",
                    "points": [(fx, y_run), (fx, fy)],
                    "z": low_z,
                    "width": line,
                    "height": thick,
                    "material": METAL_LOOK,
                },
                {
                    "kind": "cylinder",
                    "name": f"in{n}",
                    "centre": [fx, fy],
                    "z": [fe_top, low_z],
                    "radius": 1.2,
                    "material": METAL_LOOK,
                },
            ]
            for k, (vx, vy, z0, z1) in enumerate(
                [(bx, by, low_z, pad_z), (x_run, y_run, low_z, high_z + thick), (fx, y_run, low_z, high_z + thick)]
            ):
                parts.append(
                    {
                        "kind": "cylinder",
                        "name": f"via{n}{k}",
                        "centre": [vx, vy],
                        "z": [z0, z1],
                        "radius": 0.9,
                        "material": METAL_LOOK,
                    }
                )
            cutting = {"cut": section} if by == 0.0 else {}
            parts.append(
                {
                    "kind": "cylinder",
                    "name": f"pad{n}",
                    "centre": [bx, by],
                    "z": [pad_z, pad_z + 0.8],
                    "radius": 11.5,
                    "material": UBM,
                    **cutting,
                }
            )
            parts.append(
                {
                    "kind": "bump",
                    "name": f"bump{n}",
                    "centre": [bx, by, (pad_z + 0.8 + face) / 2],
                    "radius": BUMP / 2,
                    "height": face - pad_z - 0.8,
                    "material": SOLDER,
                    **cutting,
                }
            )
    sensor_sources = ("NW", "PW", "OD", "NP", "PP", "PO", "CO", "M1", "V1", "M2", "V2", "M3")
    s_keep = ("NPLUS", "PPLUS", "NW", "PW", "PO", "CO", "M1", "V1", "M2", "V2", "M3")
    # the sensor cut back to the second row of bumps, so the redistribution under it shows
    centre_s, back = (1600.0, 1600.0), -pitch
    s_crop = [centre_s[0] - 25.0, centre_s[1] - back, centre_s[0] + 175.0, centre_s[1] - low]
    sensor_gds, sensor_layers = role_piece(
        "lf_sensor_array",
        None,
        sensor_sources,
        {"NPLUS": "OD & NP", "PPLUS": "OD & PP"},
        [s_crop[0] - 1, s_crop[1] - 1, s_crop[2] + 1, s_crop[3] + 1],
        s_keep,
    )
    sensor_stack = section_stack(
        list(s_keep), {"NPLUS": (0, -0.3), "PPLUS": (0, -0.3), "NW": (0, -2.5), "PW": (0, -1.5)}
    )
    s_beol = max(layer["z"] + layer["height"] for layer in sensor_stack)
    surface = face + s_beol
    parts += [
        section_part(
            "sensor",
            sensor_gds,
            sensor_layers,
            sensor_stack,
            s_crop,
            list(centre_s),
            ("y0", "x0", "x1"),
            z=surface,
            flip=True,
            at=[25.0, 0.0],
        ),
        *slabs((0.0, width), (low, back), [(face, surface, OXIDE), (surface, surface + 40.0, LOW_P)], "sensor"),
    ]
    return {"camera": {"azimuth": 60, "elevation": 48, "fov": 24}, **DRAWN, "parts": parts}


def role_piece_die(
    sources: tuple[str, ...], derived: dict[str, str], box: list[float], keep: tuple[str, ...]
) -> tuple[str, dict[str, list[int]]]:
    """role_piece for FRIDA-1's own layout (the chip GDS beside the stack-up pieces)."""

    target = STACKUPS / "frida-1.gds"
    if not target.exists() or target.stat().st_mtime < DIE.stat().st_mtime:
        shutil.copy(DIE, target)
    return role_piece("frida-1", "tsmc65", sources, derived, box, keep)


# ------------------------------------------------------------------------------ the test board

PCB = ROOT / "design" / "pcb" / "frida65A.kicad_pcb"
DIE = Path(check.TOOLS).parent / "frida-1.gds"  # the chip's layout, built in the main checkout
BOARD_STYLES = {  # the mask a little translucent, so the copper under it shows as lighter lines
    "mask": {"color": "#1E4A2C", "roughness": 0.5, "coat": 0.0, "alpha": 0.8},
    "laminate": {"color": "#2F3524", "roughness": 0.75},
    "copper": {"color": "#B98A52", "metallic": 0.5, "roughness": 0.45},
    "pads": {"color": "#E6B85C", "metallic": 1.0, "roughness": 0.25},
    "silkscreen": {"color": "#ECEFF4", "roughness": 0.6},
}
COPPER_TOP = 1.55  # mm: the bare pads' surface in kicad-cli's export (its mask sheet at 1.56)
EPOXY = 0.02  # the die attach under the die
DIE_TOP = COPPER_TOP + EPOXY + 0.25  # the die a nominal 0.25 mm thick


def kicad_cli() -> str:
    """kicad-cli from the pinned KiCad AppImage, unpacked on first use (no FUSE needed)."""

    root = check.install("kicad")
    if not (root / "AppDir").exists():
        image = next(root.glob("kicad-*.AppImage"))
        subprocess.run([str(image), "--appimage-extract"], cwd=root, check=True, capture_output=True)
    return str(root / "AppDir" / "bin" / "kicad-cli")


def board_glb() -> Path:
    """The board with its parts as GLB (kicad-cli), exported again when the board changes."""

    out = STACKUPS / "frida65A.glb"
    sources = [PCB, *(PCB.parent / "frida.pretty").iterdir()]  # the board and its parts' models
    if not out.exists() or out.stat().st_mtime < max(path.stat().st_mtime for path in sources):
        # a copy whose zones are filled afresh (a saved board keeps its last fill, maybe stale),
        # beside the project's libraries so the footprints find their 3-D models
        work = STACKUPS / "board"
        work.mkdir(parents=True, exist_ok=True)
        for name in (PCB.name, PCB.with_suffix(".kicad_pro").name, "fp-lib-table", "sym-lib-table"):
            shutil.copy(PCB.parent / name, work / name)
        library = work / "frida.pretty"
        if not library.exists():
            library.symlink_to(PCB.parent / "frida.pretty")
        board = work / PCB.name
        subprocess.run(
            [kicad_cli(), "pcb", "drc", "--refill-zones", "--save-board", "-o", str(work / "drc.rpt"), str(board)],
            check=True,
            capture_output=True,
        )
        subprocess.run(
            [
                kicad_cli(),
                "pcb",
                "export",
                "glb",
                "--force",
                "--subst-models",
                "--include-tracks",
                "--include-pads",
                "--include-zones",
                "--include-silkscreen",
                "--include-soldermask",
                "-o",
                str(out),
                str(board),
            ],
            check=True,
            capture_output=True,
        )
    return out


def footprint_pads(reference: str) -> dict[str, tuple[float, float]]:
    """A footprint's pads on the board (mm, KiCad's axes: y down), from the .kicad_pcb."""

    import re

    text = PCB.read_text()
    start = text.index(f'(property "Reference" "{reference}"')
    start = text.rindex("(footprint", 0, start)
    depth, end = 0, start
    for end in range(start, len(text)):
        depth += {"(": 1, ")": -1}.get(text[end], 0)
        if depth == 0:
            break
    block = text[start : end + 1]
    at = re.search(r"\n\t\t\(at ([-\d.]+) ([-\d.]+)(?: ([-\d.]+))?\)", block)
    x0, y0, rotation = float(at.group(1)), float(at.group(2)), float(at.group(3) or 0)
    if rotation:
        raise SystemExit(f"{reference} is rotated: not handled")
    pads = {}
    for match in re.finditer(r'\(pad "(\w+)" smd \w+\s*\(at ([-\d.]+) ([-\d.]+)', block):
        pads[match.group(1)] = (x0 + float(match.group(2)), y0 + float(match.group(3)))
    return pads


def die_pads() -> list[tuple[float, float]]:
    """FRIDA-1's bond pads (µm from the die's centre, the layout's axes), in the order the board
    numbers its pads: down the left side, along the bottom, up the right side, back along the top."""

    import importlib

    import klayout.db as kdb

    tech = importlib.import_module("pdk.tsmc65.layout.tech")
    layout = kdb.Layout()
    layout.read(str(DIE))
    top = layout.cell("frida_top")
    region = kdb.Region(top.begin_shapes_rec(layout.find_layer(*tech.LAYERS["AP"]))).merged()
    pads = []
    for polygon in region.each():
        box = polygon.bbox().to_dtype(layout.dbu)
        if 80 < max(box.width(), box.height()) < 100 and 50 < min(box.width(), box.height()) < 70:
            pads.append((box.center().x, box.center().y))
    size = top.dbbox()
    inner = (size.left + 150, size.right - 150)
    left = sorted((p for p in pads if p[0] < inner[0]), key=lambda p: -p[1])
    bottom = sorted((p for p in pads if p[1] < size.bottom + 150 and inner[0] <= p[0] <= inner[1]), key=lambda p: p[0])
    right = sorted((p for p in pads if p[0] > inner[1]), key=lambda p: p[1])
    top_row = sorted((p for p in pads if p[1] > size.top - 150 and inner[0] <= p[0] <= inner[1]), key=lambda p: -p[0])
    ordered = left + bottom + right + top_row
    if len(ordered) != 28:
        raise SystemExit(f"expected 28 bond pads, found {len(ordered)}")
    centre = size.center()
    return [(x - centre.x, y - centre.y) for x, y in ordered]


def board_parts() -> list[dict]:
    """The board (kicad-cli), the FRIDA-1 die on U3's paddle (its top metals and pad openings
    from its layout) and its 28 aluminium wedge bonds, die pad n to board pad n (scene in mm)."""

    import importlib

    tech = importlib.import_module("pdk.tsmc65.layout.tech")
    pads = footprint_pads("U3")
    cx, cy = pads["29"][0], -pads["29"][1]  # the paddle, in Blender's axes (y up)
    roles = {role: list(tech.LAYERS[role]) for role in ("M8", "V8", "M9")}
    roles["PAD"] = list(tech.LAYERS["AP"])
    layers = nominal_stack(roles, 1e-3 * 4)  # µm to mm, the thin stack thickened four times
    surface = max(layer["z"] + layer["height"] for layer in layers)
    for layer in layers:
        layer["z"] -= surface  # the stack's top at the die's surface
    parts = [
        {"kind": "glb", "path": str(board_glb()), "scale": 1000.0, "styles": BOARD_STYLES},
        {
            "kind": "box",
            "name": "epoxy",
            "min": [cx - 0.54, cy - 0.54, COPPER_TOP],
            "max": [cx + 0.54, cy + 0.54, COPPER_TOP + EPOXY],
            "material": {"color": "#C8CCD2", "metallic": 0.4, "roughness": 0.6},
        },
        {
            "kind": "box",
            "name": "die",
            "min": [cx - 0.5, cy - 0.5, COPPER_TOP + EPOXY],
            "max": [cx + 0.5, cy + 0.5, DIE_TOP - 0.004],
            "material": {"color": "#3B4252", "roughness": 0.45},
        },
        {
            "kind": "layout",
            "name": "die",
            "gds": str(DIE),
            "cell": "frida_top",
            "unit": 1e-3,
            "crop": [0, 0, 1.0, 1.0],
            "origin": [0.5, 0.5],
            "at": [cx, cy],
            "z": DIE_TOP,
            "layers": layers,
        },
    ]
    radius = 0.0125  # 25 µm aluminium wire, wedge bonded at both ends
    for n, (dx, dy) in enumerate(die_pads(), start=1):
        bx, by = pads[str(n)][0], -pads[str(n)][1]
        sx, sy = cx + dx / 1000, cy + dy / 1000
        length = math.hypot(bx - sx, by - sy)
        ux, uy = (bx - sx) / length, (by - sy) / length
        top, pad = DIE_TOP + radius, COPPER_TOP + radius

        def along(d: float, z: float, sx: float = sx, sy: float = sy, ux: float = ux, uy: float = uy) -> list[float]:
            return [sx + ux * d, sy + uy * d, z]

        points = [
            along(-0.03, top),
            along(0.02, top),
            along(0.07, top + 0.16),  # off the die's wedge, up
            along(0.35 * length, top + 0.30),  # the loop
            along(length - 0.24, pad + 0.07),
            along(length - 0.09, pad + 0.004),  # down, shallow
            along(length - 0.03, pad - 0.002),
            along(length + 0.01, pad - 0.004),  # along the foot
        ]
        parts.append({"kind": "wire", "name": f"bond{n}", "points": points, "radius": radius, "material": ALUMINIUM})
        angle = math.degrees(math.atan2(uy, ux))
        parts.append(
            {
                "kind": "wedge",
                "name": f"foot{n}",
                "centre": along(length - 0.02, COPPER_TOP + 0.007),
                "angle": angle,
                "size": [0.09, 0.038, 0.014],
                "material": ALUMINIUM,
            }
        )
        parts.append(
            {
                "kind": "wedge",
                "name": f"heel{n}",
                "centre": along(-0.005, DIE_TOP + 0.006),
                "angle": angle,
                "size": [0.065, 0.034, 0.012],
                "material": ALUMINIUM,
            }
        )
    return parts


def board() -> dict:
    """The FRIDA-1 test board."""

    return {"camera": {"azimuth": -62, "elevation": 40}, "parts": board_parts(), "glb": None}


def board_die() -> dict:
    """FRIDA-1 bonded on the test board, close up."""

    pads = footprint_pads("U3")
    cx, cy = pads["29"][0], -pads["29"][1]
    return {
        "camera": {"azimuth": -62, "elevation": 42, "target": [cx, cy, DIE_TOP], "span": 6.0},
        "parts": board_parts(),
        "glb": None,
    }


def board_top() -> dict:
    """The board from above, around FRIDA-1 and the clock pairs feeding it."""

    pads = footprint_pads("U3")
    cx, cy = pads["29"][0], -pads["29"][1]
    return {
        "camera": {"azimuth": -90, "elevation": 89.5, "target": [cx, cy - 10, DIE_TOP], "span": 34.0},
        "parts": board_parts(),
        "glb": None,
    }


SCENES = {
    "mono_pixel": mono_pixel,
    "mono_edge": mono_edge,
    "hybrid_pixel": hybrid_pixel,
    "hybrid_super": hybrid_super,
    "board": board,
    "board_die": board_die,
    "board_top": board_top,
}


# ------------------------------------------------------------------------------------- render


def blender() -> tuple[str, list[str]]:
    """Blender's binary and the paths its Python needs: the BlenderGDS add-on and, installed on
    first use beside the tools, klayout and PyYAML for Blender's Python."""

    root = check.install("blender")
    addon = check.install("blendergds")
    version = (
        subprocess.run(
            [
                str(root / "blender"),
                "-b",
                "--factory-startup",
                "--python-expr",
                "import sys; print('PY', sys.version_info[0], sys.version_info[1])",
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        .stdout.split("PY ")[1]
        .split()[:2]
    )
    site = Path(check.TOOLS) / f"blender-site-py{''.join(version)}"
    if not site.exists():
        subprocess.run(
            [
                "uv",
                "pip",
                "install",
                "-q",
                "--target",
                str(site),
                "--python-version",
                ".".join(version),
                "--python-platform",
                "x86_64-manylinux_2_28",
                *SITE,
            ],
            check=True,
        )
    return str(root / "blender"), [str(site), str(addon)]


def render(name: str, size: tuple[int, int] = (1600, 1200), samples: int = 96) -> Path:
    exe, sys_path = blender()
    spec = SCENES[name]()
    FIGURES.mkdir(exist_ok=True)
    out = FIGURES / f"stack_{name}.png"
    glb = spec.pop("glb", True)
    spec.update(
        {
            "sys_path": sys_path,
            "out": str(out),
            "glb": str(out.with_suffix(".glb")) if glb else None,
            "size": list(size),
            "samples": samples,
            "threads": min(32, os.cpu_count() or 8),
        }
    )
    with tempfile.TemporaryDirectory() as tmp:
        scene = Path(tmp) / "scene.json"
        scene.write_text(json.dumps(spec))
        result = subprocess.run(
            [exe, "-b", "--factory-startup", "--python", str(HERE / "stackup_blender.py"), "--", str(scene)],
            capture_output=True,
            text=True,
            check=False,
        )
    lines = [
        line
        for line in result.stdout.splitlines()
        if line.startswith(("scene built", "rendered", "exported", "Traceback", "  File", "Error")) or "Error" in line
    ]
    print("\n".join(lines))
    if result.returncode or not out.exists():
        print(result.stdout[-3000:], result.stderr[-2000:])
        raise SystemExit(f"{name}: Blender failed")
    return out


THESIS = ("mono_pixel", "mono_edge", "hybrid_pixel", "hybrid_super", "board", "board_die")


def main() -> None:
    for name in sys.argv[1:] or THESIS:
        print(render(name))


if __name__ == "__main__":
    main()
