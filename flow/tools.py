"""The tools the steps run, by name and version, as each step's outputs record them (``tool``):
Spectre's from its run's log, ALIGN's checkout, gdscheck's, KLayout's and KLayout-PEX's installs.
A version not found is None."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from functools import cache
from pathlib import Path
from typing import Any


@cache
def align() -> str | None:
    """ALIGN's commit (its checkout, ``ALIGN_HOME``), short."""
    from flow.layout.run import ALIGN_HOME

    found = subprocess.run(
        ["git", "-C", str(ALIGN_HOME), "rev-parse", "--short", "HEAD"], capture_output=True, text=True, check=False
    )
    return found.stdout.strip() or None


@cache
def gdscheck() -> str | None:
    """gdscheck's version (``gdscheck --version``)."""
    if not shutil.which("gdscheck"):
        return None
    found = subprocess.run(["gdscheck", "--version"], capture_output=True, text=True, check=False)
    return (found.stdout.split() or [None])[-1]


@cache
def klayout() -> str | None:
    """KLayout's version (its Python module's, which runs the LVS)."""
    import klayout as module

    return getattr(module, "__version__", None)


@cache
def kpex() -> str | None:
    """KLayout-PEX's version, in its own environment (``KPEX_HOME``)."""
    from flow.layout.kpex import KPEX_HOME

    python = KPEX_HOME / "bin" / "python"
    if not python.exists():
        return None
    script = "import importlib.metadata as m; print(m.version('klayout-pex'))"
    found = subprocess.run([str(python), "-c", script], capture_output=True, text=True, check=False, env={**os.environ})
    return found.stdout.strip() or None


def spectre(folder: Path) -> str | None:
    """Spectre's version, as a run's log under ``folder`` states it (``Version 24.1.0.078``)."""
    for log in sorted(folder.glob("*/spectre.log"))[:1]:
        found = re.search(r"^Version (\S+)", log.read_text(errors="replace")[:2000], re.MULTILINE)
        return found[1] if found else None
    return None


def of(step: str, outputs: dict[str, Any], out: Path) -> dict[str, Any] | None:
    """The tool ``step`` ran on an instance (``out``), by name and version: Spectre's for its
    simulations, the checker its outputs name for DRC and LVS (gdscheck and its mode, KLayout's
    LVS, Calibre), KLayout-PEX for its extraction; None where it ran none (skipped) or names its
    own (the layout's ALIGN)."""
    if outputs.get("skipped") or "tool" in outputs:
        return None
    if step in ("presim", "postsim", "circuit"):
        return {"name": "spectre", "version": spectre(out / step)}
    checker = str(outputs.get("checker") or outputs.get("lvs_checker") or outputs.get("extractor") or "")
    if step == "drc" and checker.startswith("gdscheck"):
        mode = checker.removeprefix("gdscheck").strip()
        return {"name": "gdscheck", "version": " · ".join(filter(None, (gdscheck(), mode)))}
    if step == "lvs" and "calibre" not in checker.lower():
        return {"name": "klayout-lvs", "version": klayout()}
    if step == "pex" and checker.startswith("KLayout-PEX"):
        return {"name": "klayout-pex", "version": kpex()}
    if "calibre" in checker.lower():
        return {"name": "calibre", "version": None}
    return None
