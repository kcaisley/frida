"""Render the FSIC preamp beside the new skin from the current Verilog.

Regenerate from this directory with: python render.py
The checked-in FSIC SVG/PDF are curated; old_auto is a separate, fully
automatic rendering of the same Verilog for a more controlled skin comparison.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
ASSETS = HERE.parent
FRIDA = ASSETS.parents[2]
SKIN_TREE = FRIDA
INPUT = ASSETS / "preamp_netlistsvg.v"
SKIN = ASSETS / "circuitikz_analog.svg"


def run(*args: str, cwd: Path = HERE, env: dict[str, str] | None = None) -> None:
    subprocess.run(args, cwd=cwd, env=env, check=True)


def main() -> None:
    HERE.mkdir(parents=True, exist_ok=True)
    shutil.copy2(INPUT, HERE / INPUT.name)
    shutil.copy2(ASSETS / "preamp_netlistsvg.svg", HERE / "fsic_original.svg")
    shutil.copy2(ASSETS / "preamp_netlistsvg.pdf", HERE / "fsic_original.pdf")
    shutil.copy2(ASSETS / "examples/fonts.conf", HERE / "fonts.conf")

    for name, extra in (("old_auto", ()), ("new_style", ("--skin", str(SKIN)))):
        run(
            "python",
            str(ASSETS / "verilog_schematic.py"),
            str(HERE / INPUT.name),
            "--top",
            "preamp_netlistsvg",
            "-o",
            str(HERE / f"{name}.svg"),
            *extra,
            cwd=SKIN_TREE,
        )

    env = os.environ.copy()
    env["FONTCONFIG_FILE"] = str(HERE / "fonts.conf")
    for name in ("old_auto", "new_style"):
        run("rsvg-convert", "-f", "pdf", "-o", f"{name}.pdf", f"{name}.svg", env=env)
    for name in ("fsic_original", "old_auto", "new_style"):
        run("pdftocairo", "-png", "-singlefile", "-r", "160", f"{name}.pdf", name, env=env)
    run("pdflatex", "-interaction=nonstopmode", "-halt-on-error", "comparison.tex", env=env)
    run("pdftocairo", "-png", "-singlefile", "-r", "110", "comparison.pdf", "comparison", env=env)


if __name__ == "__main__":
    main()
