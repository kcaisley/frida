"""An ALIGN PDK directory for a PDK's row cells: generic generators plus the PDK's numbers.

Copies flow/layout/align/pdk (the generators: rowcell MOS primitives and standard cells; the
capacitor and resistor generators ALIGN asks for raise) and writes, from the PDK's ``tech``:

* layers.json: layers_base.json (PDK-neutral placeholders) with the GDS layers, routing pitches
  (M2 tracks PITCH, M1/M3 XPITCH), widths, cuts and spacings replaced, and the metals and cuts
  above M3 from the PDK's RULES; a layer the PDK does not draw (NP, VT) goes to an abstract
  255/x layer, which post.py removes;
* models.sp: models_base.sp plus the PDK's MOS models;
* stems.json: where mos.py finds the PDK's layout directory and the stems engine, and which of
  ALIGN's spare layers (Rvt, Hvt, Pb) carry the PDK's own row-cell markers (its PO_MARK,
  GATE_MARK, VT_MARKS, RAIL_MARKS and PO_DUMMY_LAYER).

Run bound to a PDK (flow/layout/pdkproc.py); flow/layout/align/build.py and
flow/layout/floorplan.py call ``build``.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent


def build(pdk: str, out: Path) -> Path:
    layout_dir = ROOT / "pdk" / pdk / "layout"
    import tech as t  # the PDK this process is bound to

    # overwrite in place (parallel builds of one PDK may run this at once)
    shutil.copytree(HERE / "pdk", out, ignore=shutil.ignore_patterns("__pycache__"), dirs_exist_ok=True)
    base = json.loads((HERE / "layers_base.json").read_text())
    abstract = iter(range(20, 100))

    def gds(name):  # (layer, datatype) of a tech layer, or a fresh abstract one
        ld = t.LAYERS.get(name)
        return ld if ld else (255, next(abstract))

    # ALIGN wants every M2 pin on its M2 grid, the routing tracks: a standard-cell pin between them
    # (PIN_PITCH) reaches ALIGN as an M3 stub instead (pdk/stdcell.py)
    m2_pitch = t.PITCH
    # ALIGN's M1 lines carry vias in their run: the PDK's width for a via inside a line (VIA_M1_W)
    m1_w = getattr(t, "VIA_M1_W", t.M1W)
    m3_pitch = getattr(t, "M3_PITCH", t.XPITCH)
    metal = {
        "M1": (m3_pitch, m1_w, t.M1_SPACE),
        "M2": (m2_pitch, t.M2W, getattr(t, "M2_LINE_END", 2 * t.M2_SPACE)),
        "M3": (m3_pitch, t.M3W, getattr(t, "LINE_END", t.M2_SPACE)),  # line end to line end
    }
    cut = {
        "V0": (t.CO, t.CO_PITCH - t.CO, "CO"),
        "V1": (t.V1, t.V1_PAIR - t.V1, "V1"),
        "V2": (t.V2, t.V1_PAIR - t.V2, "V2"),
    }
    names = {
        "Poly": "PO",
        "Pc": "PO",
        "Nwell": "NW",
        "Active": "OD",
        "Nselect": "NP",
        "Pselect": "PP",
        "Lvt": "VTN",
        "Slvt": "VTP",
        "Boundary": "BND",
    }
    # the row cells' markers ALIGN has no layer for, each on a spare one
    marks = [*getattr(t, "PO_MARK", {}).values(), *([t.GATE_MARK["layer"]] if getattr(t, "GATE_MARK", None) else [])]
    marks += [m for ms in getattr(t, "VT_MARKS", {}).values() for m in ms]
    marks += [layer for layer, _ in getattr(t, "RAIL_MARKS", ())]
    marks += [t.PO_DUMMY_LAYER] if getattr(t, "PO_DUMMY_LAYER", "PO") != "PO" else []
    extra = dict(zip(marks, ("Rvt", "Hvt", "Pb"), strict=False))
    names.update({align: key for key, align in extra.items()})
    layers = []
    for a in base["Abstraction"]:
        a = dict(a)
        name = a.get("Layer")
        if name in metal:
            pitch, width, end = metal[name]
            (a["GdsLayerNo"], a["GdsDatatype"]["Draw"]) = gds(name)
            a.update(Pitch=pitch, Width=width, EndToEnd=end)
            if name in t.PIN_TEXT:  # ALIGN writes the metal's pin labels on the PDK's pin-text layer
                a["LabelLayerNo"] = [list(t.PIN_TEXT[name])]
            if name != "M1":
                a["MinL"] = t.M2_MIN_LEN
        elif name in cut:
            size, space, tl = cut[name]
            (a["GdsLayerNo"], a["GdsDatatype"]["Draw"]) = gds(tl)
            venc = t.BAR_END - size // 2 + 10 if name != "V0" else a["VencA_L"]
            a.update(WidthX=size, WidthY=size, SpaceX=space, SpaceY=space, VencA_L=venc, VencA_H=venc)
        elif name in names:
            (a["GdsLayerNo"], a["GdsDatatype"]["Draw"]) = gds(names[name])
        elif name in ("M4", "M5", "M6", "M7", "M8", "M9", "V3", "V4", "V5", "V6", "V7", "V8"):
            (a["GdsLayerNo"], a["GdsDatatype"]["Draw"]) = gds(name)  # unused above M3: abstract
            if f"{name}.PIN" in t.LAYERS:  # a metal's labels (the MOM units' terminals) on its pin layer
                a["LabelLayerNo"] = [list(t.LAYERS[f"{name}.PIN"])]
            rule = t.RULES.get(name, {})
            if "pitch" in rule:  # a metal: the PDK's pitch, width and space
                a.update(Pitch=rule["pitch"], Width=rule["width"], EndToEnd=rule["space"])
            elif "cut" in rule and "space" in rule:
                a.update(WidthX=rule["cut"], WidthY=rule["cut"], SpaceX=rule["space"], SpaceY=rule["space"])
        elif name == "Cap":
            a.update(m1Pitch=t.XPITCH, m2Pitch=t.PITCH, m3Pitch=t.XPITCH, m1Width=t.M1W, m2Width=t.M2W, m3Width=t.M3W)
        layers.append(a)
    # the MOM units' annotations (mom.py: their LVS recognition), each its own ALIGN layer
    layers += [
        {"Layer": f"Ann_{name}", "GdsLayerNo": ld[0], "GdsDatatype": {"Draw": ld[1]}}
        for name, ld in t.LAYERS.items()
        if name.startswith("MOM_RECOG") and ld
    ]
    base["Abstraction"] = layers
    base["_comment"] = (
        f"ALIGN abstraction for {pdk} row cells, generated by flow/layout/align/make_pdk.py from pdk/{pdk}/layout/tech.py."
    )
    (out / "layers.json").write_text(json.dumps(base, indent=2) + "\n")
    models = (HERE / "models_base.sp").read_text()
    for pol, model in t.MODELS.items():
        # far: the device's terminals on the other type's rail (make_design.py, align/pdk/mos.py)
        line = f".model {model} {pol}mos l=1 w=1 nf=1 m=1 stack=1 parallel=1 far=0"
        if f".model {model} " not in models:
            models += line + "\n"
    (out / "models.sp").write_text(models)
    (out / "stems.json").write_text(
        json.dumps({"layout": str(layout_dir), "stems": str(ROOT / "flow/layout/stems"), "extra": extra}) + "\n"
    )
    return out
