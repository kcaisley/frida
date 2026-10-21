"""FRIDA circuit generation, layout, simulation, analysis, and laboratory workflows."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path


def new_run(*parts: str) -> Path:
    """A fresh run directory, ``build/<parts...>/<YYYYmmdd_HHMMSS>`` in the repository, made."""

    stamp = datetime.now().astimezone().strftime("%Y%m%d_%H%M%S")
    run_dir = Path(__file__).resolve().parents[1].joinpath("build", *parts, stamp)
    run_dir.mkdir(parents=True, exist_ok=False)
    return run_dir
