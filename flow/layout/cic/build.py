"""cIcCreator (cicpy) flow for a design in standard-cell rows: the PDK's tech file (make_tech.py),
placeholders and real cells (gen.py), routes (route.py), compile, convert to GDS (cic2gds.py),
finish (post.py).

``CICPY``: the cicpy command (default ``cicpy`` on the PATH; it needs ``compile``, cicpy 0.3).
"""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

from flow.layout.cic.cic2gds import convert
from flow.layout.pdkproc import access_points, in_pdk

CICPY = os.environ.get("CICPY", "cicpy")


def build(pdk: str, floorplan: Path, netlist: Path, out_dir: Path) -> Path:
    """Lay out ``netlist`` in ``pdk`` with cicpy as ``floorplan`` places it; returns the GDS
    ``out_dir/<name>/<name>.gds`` (``<name>``: the floorplan's)."""

    access_points(pdk)
    name = floorplan.stem
    out = out_dir / name
    top = name.upper()
    tech = in_pdk(pdk, "flow.layout.cic.make_tech", "build", pdk, out_dir / f"{pdk}.tech")
    in_pdk(pdk, "flow.layout.cic.gen", "generate", pdk, floorplan, out_dir, netlist)
    in_pdk(pdk, "flow.layout.cic.route", "route", pdk, out, floorplan, netlist)
    (out / f"{name}.cic").unlink(missing_ok=True)
    log = out / "compile.log"
    with log.open("w") as f:
        subprocess.run(
            [CICPY, "compile", f"{name}.json", str(tech.resolve()), name],
            cwd=out, stdout=f, stderr=subprocess.STDOUT, check=True,
        )  # fmt: skip
    errors = [line for line in log.read_text().splitlines() if re.search("ERROR|Traceback", line)]
    if errors:
        raise RuntimeError(f"cicpy compile failed ({log}):\n" + "\n".join(errors[:10]))
    convert(out / f"{name}.cic", tech, out / f"{name}_raw.gds", top)
    gds = out / f"{name}.gds"
    in_pdk(
        pdk, "flow.layout.cic.post", "post", str(out / f"{name}_raw.gds"), str(out / f"{name}_cells.gds"), str(gds), top
    )
    print(f"wrote {gds}")
    return gds
