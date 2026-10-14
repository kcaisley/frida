"""Regenerate the six documentation diagrams from Verilog (flow/util/hdl2image.py).

From the repository root:
    python3 docs/images/netlistsvg/render.py
    python3 docs/images/netlistsvg/render.py preamp daq_core
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT))  # run with plain python3 from the repository root

from flow.util.hdl2image import ANALOG_SKIN, tcl_to_digital_svg, verilog_to_analog_svg

DIAGRAMS = ("preamp", "adc_digital", "adc_top", "daq_core", "frida_core_1adc", "spi_diagram")
ENV = os.environ.copy()
ENV["FONTCONFIG_FILE"] = str(HERE / "fonts.conf")


def run(*args: str) -> None:
    subprocess.run(args, check=True, cwd=ROOT, env=ENV)


def render(name: str) -> None:
    stem = name if name == "spi_diagram" else name + "_netlistsvg"
    svg = HERE / (stem + ".svg")
    netlist = svg.with_suffix(".json")
    if name == "preamp":
        verilog_to_analog_svg(HERE / "preamp_netlistsvg.v", svg, "preamp_netlistsvg", ANALOG_SKIN)
    else:
        tcl_to_digital_svg(HERE / (name + ".tcl"), netlist, svg)
    pdf = svg.with_suffix(".pdf")
    run("rsvg-convert", "-f", "pdf", "-o", str(pdf), str(svg))
    run("pdftocairo", "-png", "-singlefile", "-r", "160", str(pdf), str(svg.with_suffix("")))
    print(f"Created {netlist.name}, {svg.name}, {pdf.name}, {svg.with_suffix('.png').name}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("diagrams", nargs="*", help="diagram names; omit to regenerate all six")
    args = parser.parse_args()
    for name in args.diagrams:
        if name not in DIAGRAMS:
            parser.error(f"unknown diagram {name!r}; choose from {', '.join(DIAGRAMS)}")
    for name in args.diagrams or DIAGRAMS:
        render(name)


if __name__ == "__main__":
    main()
