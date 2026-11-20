# ruff: noqa  -- ALIGN style: ALIGN imports this module from the PDK directory by name
"""ALIGN's ``gen_param`` for the row-cell PDK: ALIGN's own, its Bulk65nm mock PDK's (loaded from the
ALIGN install), sizes every primitive and lists its arrays (``x_cells`` x ``y_cells``), with two
additions: a standard cell is one fixed primitive (stdcell.py, through ALIGN's guard-ring path),
and where a floorplan fixes the rows (``ROWS_STD_DENSE``) a primitive is one row."""

import importlib.util
import os
from pathlib import Path

import align
from align.compiler.util import get_generator

_SPEC = importlib.util.spec_from_file_location(
    "align_mock_gen_param", Path(align.__file__).resolve().parents[1] / "pdks" / "Bulk65nm_Mock_PDK" / "gen_param.py"
)
_ALIGN = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_ALIGN)


# the PDK's own generators a netlist names (``Generator(name=...)``): ALIGN's generic primitives, each
# drawn by its class's ``generate(ports, netlist_parameters)`` from its subcircuit's parameters
_generic = ("MomUnit", "CmosInverter", "CmosChain", "MosWell")


def _inverter_values(subckt):
    """A complementary inverter's drawing from its own devices (mos.CmosInverter): the NMOS is the
    one whose source is VSS; widths per finger (make_design.py writes them so), in nm."""
    import mosline

    values = {}
    for e in subckt.elements:
        q = {k.lower(): str(v) for k, v in e.parameters.items()}
        side = "n" if str(e.pins.get("S", "")).upper() == "VSS" else "p"
        values[f"w{side}"] = mosline.nm(q["w"])
        values["nf"] = int(float(q.get("nf", 1)))
        values["l"] = mosline.nm(q["l"])
    return values


def _well_values(subckt):
    """PMOS in a well of their own (mos.MosWell): each device as ``name:l:w:nf:d:g:s:far`` (nm, w per
    finger as make_design.py writes it, ``far`` its terminals on the other type's rail), ``;``
    between, in the netlist's order; their bulk (one net, the well's)."""
    import mosline

    devices, bulks = [], set()
    for e in subckt.elements:
        q = {k.lower(): str(v) for k, v in e.parameters.items()}
        pins = {k.upper(): str(v) for k, v in e.pins.items()}
        nf = int(float(q.get("nf", 1))) * int(float(q.get("m", 1)))
        far = int(float(q.get("far", 0)))
        fields = [e.name, mosline.nm(q["l"]), mosline.nm(q["w"]), nf, pins["D"], pins["G"], pins["S"], far]
        devices.append(":".join(str(f) for f in fields))
        bulks.add(pins["B"])
    assert len(bulks) == 1, f"{subckt.name}: one bulk a well, got {bulks}"
    return {"devices": ";".join(devices), "bulk": bulks.pop()}


def gen_param(subckt, primitives, pdk_dir):
    named = [c.name for c in subckt.constraints if type(c).__name__ == "Generator"]  # Generator(name=...)
    name = subckt.name
    generator = (subckt.generator["name"] if "name" in subckt.generator else "") or (named[0] if named else "")
    kind = next((g for g in _generic if g.upper() == generator.upper()), None)
    if kind:
        if kind == "CmosInverter":
            values = _inverter_values(subckt)
            for c in subckt.constraints:  # the annotation's own parameters (Generator(parameters=...))
                if type(c).__name__ == "Generator":
                    values.update({k.lower(): v for k, v in (c.parameters or {}).items()})
        elif kind == "CmosChain":  # its inverters from the annotation's own parameters
            values = {}
            for c in subckt.constraints:
                if type(c).__name__ == "Generator":
                    values.update({k.lower(): v for k, v in (c.parameters or {}).items()})
        elif kind == "MosWell":  # its devices, and the annotation's supplies
            values = _well_values(subckt)
            for c in subckt.constraints:
                if type(c).__name__ == "Generator":
                    values.update({k.lower(): v for k, v in (c.parameters or {}).items()})
        else:
            values = {k.lower(): v for k, v in (subckt.elements[0].parameters if subckt.elements else {}).items()}
        parameters = {"ports": list(subckt.pins), "values": values, "real_inst_type": kind}
        primitives[name] = {
            "primitive": "generic",
            "parameters": parameters,
            "abstract_template_name": name,
            "concrete_template_name": name,
        }
        return True
    if get_generator(generator, pdk_dir) and generator.upper() not in ("NMOS", "PMOS", "MOS", "CAP", "RES"):
        from .stdcell import CELLS, INDEX_BASE, generator_class  # a standard cell, see stdcell.RingGenerator

        primitives[name] = {
            "primitive": "guard_ring",
            "x_cells": INDEX_BASE + CELLS.index(generator_class(generator).cell),
            "y_cells": 1,
            "abstract_template_name": name,
            "concrete_template_name": name,
        }
        return True
    before = set(primitives)
    done = _ALIGN.gen_param(subckt, primitives, pdk_dir)
    if os.environ.get("ROWS_STD_DENSE"):  # one row: the floorplan's row holds the primitive
        added = [k for k in primitives if k not in before and "y_cells" in primitives[k]]
        for k in added:
            p = primitives[k]
            if p["y_cells"] > 1:
                del primitives[k]
                flat = f"{p['abstract_template_name']}_X{p['x_cells'] * p['y_cells']}_Y1"
                primitives.setdefault(
                    flat, {**p, "x_cells": p["x_cells"] * p["y_cells"], "y_cells": 1, "concrete_template_name": flat}
                )
    return done
