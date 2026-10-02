"""Render the documentation netlistsvg collection beside its inputs.

From the repository root:
    python docs/images/netlistsvg/render.py
    python docs/images/netlistsvg/render.py --comparisons

Pass one JSON and --output diagram.pdf to render an individual digital figure.
Requires Yosys, npx/netlistsvg 1.0.2, rsvg-convert, pdftocairo, and pdflatex.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from postprocess import postprocess
from prepare_digital_json import orient_inout_ports
from verilog_schematic import verilog_to_analog_svg

HERE = Path(__file__).resolve().parent
ENV = os.environ.copy()
ENV["FONTCONFIG_FILE"] = str(HERE / "examples/fonts.conf")
TEX_BIN = Path("/usr/local/texlive/2026/bin/x86_64-linux")
if TEX_BIN.is_dir():
    ENV["PATH"] = str(TEX_BIN) + os.pathsep + ENV.get("PATH", "")


def run(*args: str, cwd: Path = HERE) -> None:
    subprocess.run(args, check=True, cwd=cwd, env=ENV)


def export(svg: Path) -> None:
    run("rsvg-convert", "-f", "pdf", "-o", str(svg.with_suffix(".pdf")), str(svg))
    preview(svg.with_suffix(".pdf"))


def preview(pdf: Path) -> None:
    run("pdftocairo", "-png", "-singlefile", "-r", "160", str(pdf), str(pdf.with_suffix("")))


def digital(source: Path, output: Path) -> None:
    data = json.loads(source.read_text())
    # Draw the top module as blocks; retain the original hierarchy in the input.
    modules = data["modules"]
    top = next(
        (name for name, module in modules.items() if int(str(module.get("attributes", {}).get("top", "0")), 2)), None
    )
    if top is None:
        top = next(iter(modules))
    data["modules"] = {top: modules[top]}
    for cell in modules[top].get("cells", {}).values():
        if cell["type"].startswith("$paramod") and "\\" in cell["type"]:
            cell["type"] = cell["type"].split("\\")[-1]
    orient_inout_ports(data)
    output.parent.mkdir(parents=True, exist_ok=True)
    # Keep a presentation JSON next to the SVG so its bus annotations are reproducible.
    drawing_json = output.with_suffix(".render.json")
    drawing_json.write_text(json.dumps(data, indent=2) + "\n")
    svg = output.with_suffix(".svg")
    run("npx", "--yes", "netlistsvg@1.0.2", str(drawing_json), "--skin", str(HERE / "style.svg"), "-o", str(svg))
    postprocess(svg, drawing_json)
    export(svg)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("json", nargs="?", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--comparisons", action="store_true")
    parser.add_argument("--refresh-json", action="store_true", help="refresh current-source comparison JSON")
    args = parser.parse_args()
    if args.json:
        digital(args.json.resolve(), (args.output or args.json.with_suffix(".pdf")).resolve())
        return
    for source, stem in (
        ("adc_digital.json", "adc_digital_netlistsvg"),
        ("daq_core_netlistsvg.json", "daq_core_netlistsvg"),
        ("daq_core_netlistsvg_patched.json", "daq_core_netlistsvg_patched"),
        ("frida_core_1adc_netlistsvg.json", "frida_core_1adc_netlistsvg"),
        ("examples/digital_demo.json", "examples/digital_demo"),
        ("examples/generic_demo.json", "examples/generic_demo"),
    ):
        digital(HERE / source, HERE / (stem + ".pdf"))
    verilog_to_analog_svg(
        HERE / "preamp_netlistsvg.v", HERE / "preamp_custom.svg", "preamp_netlistsvg", HERE / "circuitikz_analog.svg"
    )
    export(HERE / "preamp_custom.svg")
    for stem in ("preamp_netlistsvg", "adc_top_netlistsvg"):
        pdf = HERE / (stem + ".pdf")
        if not pdf.exists():
            export(HERE / (stem + ".svg"))
        else:
            preview(pdf)
    for skin, stem in (("circuitikz_analog.svg", "analog_catalog"), ("style.svg", "digital_catalog")):
        run("rsvg-convert", "-f", "pdf", "-o", str(HERE / "examples" / (stem + ".pdf")), str(HERE / skin))
        preview(HERE / "examples" / (stem + ".pdf"))
    export(HERE / "spi_diagram.svg")
    for svg in (HERE / "examples").rglob("*.svg"):
        export(svg)
    for stem in ("preamp_test", "preamp_pmos"):
        with tempfile.TemporaryDirectory(prefix="frida-netlistsvg-tex-") as temporary:
            run(
                "pdflatex",
                "-interaction=nonstopmode",
                "-halt-on-error",
                "-output-directory",
                temporary,
                str(HERE / (stem + ".tex")),
            )
            (HERE / (stem + ".pdf")).write_bytes((Path(temporary) / (stem + ".pdf")).read_bytes())
        preview(HERE / (stem + ".pdf"))
    if args.comparisons:
        extra = ("--refresh-json",) if args.refresh_json else ()
        run(sys.executable, str(HERE / "comparisons/render.py"), *extra)


if __name__ == "__main__":
    main()
