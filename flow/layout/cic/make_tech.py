"""A cIcCreator technology file for a PDK's row cells, from its ``tech``.

cicpy only places abstracts here (gen.py), so the file names the layers (GDS numbers, pin
text layers for the port labels) and gives rules in gamma units (MFG_GRID) that are the
PDK's widths and spaces.

Run bound to a PDK (flow/layout/pdkproc.py); flow/layout/cic/build.py calls it.
"""

from __future__ import annotations

import json
from pathlib import Path

# cicpy layer name, tech name, material, previous, next, colour
STACK = [
    ("OD", "OD", "diffusion", "", "CO", "green"),
    ("PO", "PO", "poly", "", "CO", "red"),
    ("CO", "CO", "cut", "PO", "M1", "yellow"),
    ("M1", "M1", "metal", "CO", "VIA1", "blue"),
    ("VIA1", "V1", "cut", "M1", "M2", "darkblue"),
    ("M2", "M2", "metal", "VIA1", "VIA2", "goldenrod"),
    ("VIA2", "V2", "cut", "M2", "M3", "darkgreen"),
    ("M3", "M3", "metal", "VIA2", "", "green"),
]
MARKERS = [
    ("NW", "NW", "implant"),
    ("PP", "PP", "implant"),
    ("NP", "NP", "implant"),
    ("VTN", "VTN", "implant"),
    ("VTP", "VTP", "implant"),
    ("PR", "BND", "marker"),
]


def build(pdk: str, out: Path) -> Path:
    import tech as t  # the PDK this process is bound to (flow/layout/pdkproc.py)

    g = t.MFG_GRID
    gamma = lambda nm: -(-nm // g)
    layers = {}
    for name, key, material, prev, nxt, colour in STACK:
        number, datatype = t.LAYERS[key]
        entry = {
            "number": number,
            "datatype": datatype,
            "material": material,
            "previous": prev,
            "next": nxt,
            "color": colour,
        }
        if key in t.PIN_TEXT:
            entry["pin"] = name + "_pin"
            layers[name + "_pin"] = {"number": t.PIN_TEXT[key][0], "datatype": t.PIN_TEXT[key][1], "material": "metal"}
        layers[name] = entry
    for name, key, material in MARKERS:
        if t.LAYERS.get(key):
            number, datatype = t.LAYERS[key]
            layers[name] = {"number": number, "datatype": datatype, "material": material, "fill": "nofill"}
    w = lambda width, space: {"space": gamma(space), "width": gamma(width), "minwidth": gamma(width)}
    tech = {
        "layers": layers,
        "technology": {
            "gamma": g * 10,
            "grid": g,
            "spiceunit": 1,
            "techlib": pdk,
            "devices": {
                t.MODELS["n"]: {
                    "name": t.MODELS["n"],
                    "devicetype": "M",
                    "ports": ["D", "G", "S", "B"],
                    "propertymap": {"l": {"name": "length", "str": "u"}, "w": {"name": "width", "str": "u"}},
                },
                t.MODELS["p"]: {"inherit": t.MODELS["n"], "name": t.MODELS["p"]},
            },
        },
        "rules": {
            "ROUTE": {"horizontalgrid": gamma(t.XPITCH), "verticalgrid": gamma(t.PITCH)},
            "CELL": {"space": 0, "digitalspace": 0},
            "CO": {"space": gamma(t.CO_PITCH - t.CO), "width": gamma(t.CO), "height": gamma(t.CO)},
            "M1": w(t.M1W, t.M1_SPACE),
            "VIA1": {"space": gamma(t.V1_PAIR - t.V1), "width": gamma(t.V1), "height": gamma(t.V1)},
            "M2": w(t.M2W, t.M2_SPACE),
            "VIA2": {"space": gamma(t.V1_PAIR - t.V2), "width": gamma(t.V2), "height": gamma(t.V2)},
            "M3": w(t.M3W, t.M2_SPACE),
        },
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(tech, indent=1) + "\n")
    return out
