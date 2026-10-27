"""Run ALIGN (``schematic2layout.py``) on one design directory with an ALIGN PDK directory.

ALIGN cannot run in frida's environment (it needs ``pydantic<2`` and its compiled placer and
router): it runs from its own install, ``ALIGN_HOME`` (default
/local/kcaisley/tools/ALIGN-public), with that install's Python, as a subprocess. Its
``LD_LIBRARY_PATH`` starts with the directory of the install's ``libOsiCbc.so.3`` (under
``_skbuild``). A design with a Floorplan constraint runs with ``STEMS_STD_DENSE=1``: the
generators in the PDK directory (align/pdk) then draw standard cells for rows of their own.
"""

from __future__ import annotations

import json
import os
import signal
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

ALIGN_HOME = Path(os.environ.get("ALIGN_HOME", "/local/kcaisley/tools/ALIGN-public"))


def _schematic2layout(design_dir: Path, pdk_dir: Path, work: Path, args: list[str], env: dict[str, str]) -> None:
    """One ALIGN run in ``work`` (its working directory), output in ``work/schematic2layout.log``."""

    work.mkdir(parents=True, exist_ok=True)
    command = [
        str(ALIGN_HOME / "general/bin/python"),
        str(ALIGN_HOME / "general/bin/schematic2layout.py"),
        str(design_dir),
        "-p",
        str(pdk_dir),
        "-w",
        str(work),
        "-s",
        design_dir.name,
        "-l",
        "INFO",
        "-v",
        "INFO",
        *args,
    ]
    log = work / "schematic2layout.log"
    # ALIGN_TIMEOUT (seconds, unset: none): its placer can search for hours on a large design;
    # the run and the PnR processes it starts stop together
    limit = float(os.environ["ALIGN_TIMEOUT"]) if os.environ.get("ALIGN_TIMEOUT") else None
    with log.open("w") as out:
        process = subprocess.Popen(
            command, cwd=work, env=env, stdout=out, stderr=subprocess.STDOUT, start_new_session=True
        )
        try:
            process.wait(timeout=limit)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait()
            raise RuntimeError(
                f"ALIGN stopped after {limit:g} s on {design_dir.name} {' '.join(args)}; {log}"
            ) from None
    done = process
    if done.returncode:
        tail = "\n".join(log.read_text().splitlines()[-15:])
        raise RuntimeError(f"ALIGN failed ({done.returncode}) on {design_dir.name} {' '.join(args)}; {log}:\n{tail}")


def run_align(
    design_dir: Path,
    pdk_dir: Path,
    work: Path,
    *,
    router: str | None = None,
    flow_stop: str | None = None,
) -> Path:
    """Run ALIGN on ``design_dir`` (``<name>.sp``, ``<name>.const.json``) with ``pdk_dir`` in
    ``work``; returns ``work``.

    ``router``: ALIGN's ``--router`` (None: ALIGN's default). ``flow_stop``: ALIGN's
    ``--flow_stop`` (e.g. ``"3_pnr:place"``).
    """

    design_dir, pdk_dir, work = design_dir.resolve(), pdk_dir.resolve(), work.resolve()
    name = design_dir.name
    floorplanned = '"Floorplan"' in (design_dir / f"{name}.const.json").read_text()
    lib = next((ALIGN_HOME / "_skbuild").rglob("libOsiCbc.so.3"), None)
    if lib is None:
        raise FileNotFoundError(f"no libOsiCbc.so.3 under {ALIGN_HOME / '_skbuild'}: is ALIGN built (ALIGN_HOME)?")
    env = dict(os.environ)
    env["LD_LIBRARY_PATH"] = os.pathsep.join(filter(None, (str(lib.parent), env.get("LD_LIBRARY_PATH"))))
    env.pop("STEMS_STD_DENSE", None)
    if floorplanned:
        env["STEMS_STD_DENSE"] = "1"  # standard cells in rows of their own
    args = [*(["--router", router] if router else []), *(["--flow_stop", flow_stop] if flow_stop else [])]
    _schematic2layout(design_dir, pdk_dir, work, args, env)
    return work


@dataclass(frozen=True)
class Drawing:
    """One cell for ALIGN to draw: ``<generator>().<method>(**arguments)`` of the PDK package,
    written to ``gds`` as the top cell ``top``."""

    generator: str
    method: str
    arguments: dict[str, Any]
    gds: Path
    top: str


def draw(pdk_dir: Path, drawings: list[Drawing]) -> list[Path]:
    """Draw generators of the generated ALIGN PDK ``pdk_dir`` (``make_pdk.py``), each to its GDS,
    in one run of ALIGN's own Python (``draw.py``). ALIGN's abstract layers and pin purpose stay
    in the files, as ALIGN writes them (``post.py``'s rule, ``abstract``, says which they are)."""

    first = drawings[0].gds
    first.parent.mkdir(parents=True, exist_ok=True)
    spec = first.with_suffix(".draw.json")
    cells = [{**asdict(drawing), "gds": str(drawing.gds.resolve())} for drawing in drawings]
    spec.write_text(json.dumps({"pdk_dir": str(pdk_dir.resolve()), "cells": cells}))
    lib = next((ALIGN_HOME / "_skbuild").rglob("libOsiCbc.so.3"), None)
    env = dict(os.environ)
    if lib is not None:
        env["LD_LIBRARY_PATH"] = os.pathsep.join(filter(None, (str(lib.parent), env.get("LD_LIBRARY_PATH"))))
    result = subprocess.run(
        [str(ALIGN_HOME / "general/bin/python"), str(Path(__file__).with_name("draw.py")), str(spec)],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    missing = [drawing for drawing in drawings if not drawing.gds.is_file()]
    if result.returncode or missing:
        raise RuntimeError(f"ALIGN could not draw {missing[:1] or drawings[:1]}: {result.stderr[-1500:]}")
    return [drawing.gds for drawing in drawings]


def drawn_only(layout, drawn: set[tuple[int, int]]) -> None:
    """A layout ALIGN drew, without ALIGN's own layers: its abstract ones (255, where the PDK draws
    nothing) and its pin and blockage purposes (datatypes 251, 253), as ``post.py`` leaves them out."""
    for info in list(layout.layer_infos()):
        if (info.layer == 255 and (info.layer, info.datatype) not in drawn) or info.datatype in (251, 253):
            layout.delete_layer(layout.layer(info))
