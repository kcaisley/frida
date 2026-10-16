"""laygo flow for a design in standard-cell rows: templates and design script (rowtemplates.py),
the hosted run, post.py.

A net the server's router cannot place goes first next time (rip up and retry); one that failed
first already, the other nets in a shuffled order (seeded) next time; up to TRIES runs.
``LAYGO_CLIENT``: the laygo client script (default ~/Documents/libs/laygo3-client/laygo3.py); it
needs internet.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

from flow.layout.pdkproc import access_points, in_pdk

LAYGO_CLIENT = Path(os.environ.get("LAYGO_CLIENT", "~/Documents/libs/laygo3-client/laygo3.py")).expanduser()
TRIES = 16
FAILED = re.compile(r"(?:no M2 route for|no free M3 track for|no edge escape for) ([A-Za-z0-9_]+)")


def build(pdk: str, floorplan: Path, netlist: Path, out_dir: Path) -> Path:
    """Lay out ``netlist`` in ``pdk`` with laygo as ``floorplan`` places it; returns the GDS
    ``out_dir/<name>.gds`` (``<name>``: the floorplan's)."""

    access_points(pdk)
    name = floorplan.stem
    gen = out_dir / name
    raw = out_dir / f"{name}_raw.gds"
    first: list[str] = []
    shuffle = 0
    for attempt in range(1, TRIES + 1):
        in_pdk(pdk, "flow.layout.laygo.rowtemplates", "build", pdk, floorplan, gen, netlist, first, shuffle)
        log = gen / "run.log"
        with log.open("w") as f:
            done = subprocess.run(
                [sys.executable, str(LAYGO_CLIENT), "run", str(gen / f"{name}.py"),
                 "--yaml", str(gen / f"{name}_laygo.yaml"), "-o", str(raw)],
                stdout=f, stderr=subprocess.STDOUT, check=False,
            )  # fmt: skip
        if done.returncode == 0:
            break
        failed = FAILED.search(log.read_text())
        if failed is None or attempt == TRIES:
            raise RuntimeError(f"laygo run failed ({log}):\n{log.read_text()[-3000:]}")
        if first[:1] == [failed.group(1)]:  # first already: the others in another order
            shuffle += 1
            print(f"retry: {failed.group(1)} first, the others shuffled ({shuffle})")
        else:
            print(f"retry: {failed.group(1)} first")
            first = [failed.group(1)] + [n for n in first if n != failed.group(1)]
    gds = out_dir / f"{name}.gds"
    in_pdk(pdk, "flow.layout.laygo.post", "post", str(raw), str(gen / f"{name}_templates.gds"), str(gds))
    print(f"wrote {gds}")
    return gds
