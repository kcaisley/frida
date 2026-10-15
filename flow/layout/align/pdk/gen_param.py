# ruff: noqa  -- ALIGN style: ALIGN imports this module from the PDK directory by name
"""ALIGN's ``gen_param`` for the row-cell PDK: ALIGN's own, its Bulk65nm mock PDK's (loaded from the
ALIGN install), sizes every primitive and lists its arrays (``x_cells`` x ``y_cells``), with two
additions: a standard cell is one fixed primitive (stdcell.py, through ALIGN's guard-ring path),
and where a floorplan fixes the rows (``STEMS_STD_DENSE``) a primitive is one row."""

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


def gen_param(subckt, primitives, pdk_dir):
    name, generator = subckt.name, subckt.generator["name"]
    if get_generator(generator, pdk_dir) and generator.upper() not in ("NMOS", "PMOS", "MOS", "CAP", "RES"):
        from pdk.stdcell import CELLS, INDEX_BASE, generator_class  # a standard cell, see stdcell.RingGenerator

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
    if os.environ.get("STEMS_STD_DENSE"):  # one row: the floorplan's row holds the primitive
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
