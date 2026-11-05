"""The PDK these generators draw for: its ALIGN files (``layers.json``, ``rows.json``: ``make_pdk.py``)
in the directory ``package.py`` names, else in ``tech``'s, its layout directory (``package.py`` puts
it first on the path), and the row-cell engine beside them."""

import json
import os
import sys
from pathlib import Path

import tech

DATA = Path(os.environ.get("FRIDA_ALIGN_PDK") or Path(tech.__file__).resolve().parent)
ROWS = json.loads((DATA / "rows.json").read_text())
_ENGINE = str(Path(__file__).resolve().parents[1] / "rows")  # flow/layout/rows: rowcell, capcell, netcells
if _ENGINE not in sys.path:
    sys.path.insert(1, _ENGINE)
