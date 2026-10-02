"""Regenerate six diagrams from Verilog using the custom netlistsvg skins.

From the repository root:
    python3 docs/images/netlistsvg/render.py
    python3 docs/images/netlistsvg/render.py preamp daq_core
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
from pathlib import Path

from postprocess import postprocess
from prepare_digital_json import orient_inout_ports
from verilog_schematic import verilog_to_analog_svg

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
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
        verilog_to_analog_svg(HERE / "preamp_netlistsvg.v", svg, "preamp_netlistsvg", HERE / "circuitikz_analog.svg")
    else:
        run("yosys", "-Q", "-q", "-c", str(HERE / (name + ".tcl")))
        # netlistsvg needs input/output directions and readable parameterized cell names.
        data = orient_inout_ports(json.loads(netlist.read_text()))
        for module in data["modules"].values():
            for cell in module.get("cells", {}).values():
                if cell["type"].startswith("$paramod") and "\\" in cell["type"]:
                    cell["type"] = cell["type"].split("\\")[-1]
        netlist.write_text(json.dumps(data, indent=2) + "\n")
        run("npx", "--yes", "netlistsvg@1.0.2", str(netlist), "--skin", str(HERE / "style.svg"), "-o", str(svg))
        postprocess(svg, netlist)
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
