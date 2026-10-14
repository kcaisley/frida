"""Run ALIGN (``schematic2layout.py``) on one design directory with an ALIGN PDK directory.

ALIGN cannot run in frida's environment (it needs ``pydantic<2`` and its compiled placer and
router): it runs from its own install, ``ALIGN_HOME`` (default
/local/kcaisley/layout-eval/ALIGN-public), with that install's Python, as a subprocess. Its
``LD_LIBRARY_PATH`` starts with the directory of the install's ``libOsiCbc.so.3`` (under
``_skbuild``). A design with a Floorplan constraint runs with ``STEMS_STD_DENSE=1``: the
generators in the PDK directory (align/pdk) then draw standard cells for rows of their own.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

from flow.layout.align.one_axis import one_axis as single_axis

ALIGN_HOME = Path(os.environ.get("ALIGN_HOME", "/local/kcaisley/layout-eval/ALIGN-public"))


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
    with log.open("w") as out:
        done = subprocess.run(command, cwd=work, env=env, stdout=out, stderr=subprocess.STDOUT, check=False)
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
    one_axis: bool = False,
) -> Path:
    """Run ALIGN on ``design_dir`` (``<name>.sp``, ``<name>.const.json``) with ``pdk_dir`` in
    ``work``; returns ``work``.

    ``router``: ALIGN's ``--router`` (None: ALIGN's default). ``flow_stop``: ALIGN's
    ``--flow_stop`` (e.g. ``"3_pnr:place"``). ``one_axis``: for a design without a Floorplan
    constraint, first run ALIGN to its primitives (``work/pass1``) and merge its symmetry groups
    onto one axis (one_axis.py, ``work/design/<name>``) for the second pass.
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
    if one_axis and not floorplanned:
        pass1 = work / "pass1"
        shutil.rmtree(pass1, ignore_errors=True)
        _schematic2layout(design_dir, pdk_dir, pass1, ["--flow_stop", "2_primitives"], env)
        design_dir = single_axis(design_dir, pass1, work / "design" / name)
    args = [*(["--router", router] if router else []), *(["--flow_stop", flow_stop] if flow_stop else [])]
    _schematic2layout(design_dir, pdk_dir, work, args, env)
    return work
