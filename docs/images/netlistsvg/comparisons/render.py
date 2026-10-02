"""Regenerate the analog and digital netlistsvg A/B bundle.

Run from this directory: python render.py
The analog comparison uses the current structural preamp Verilog. Digital
comparisons use archived and current-source JSON, with DAQ limited to its top
module and parameterized block type names shortened for a readable figure.
Both sides of each digital comparison receive exactly the same input JSON.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path

HERE = Path(__file__).resolve().parent
ASSETS = HERE.parent
FRIDA = ASSETS.parents[2]
SKIN_TREE = FRIDA
SKIN = ASSETS / "style.svg"
IMAGES = ASSETS
CASES = (
    ("adc_digital", IMAGES / "adc_digital.json", "ADC digital, archived"),
    ("daq_core", IMAGES / "daq_core_netlistsvg.json", "DAQ core, archived"),
    ("frida_core_1adc", IMAGES / "frida_core_1adc_netlistsvg.json", "FRIDA core, one ADC"),
    ("daq_core_patched", IMAGES / "daq_core_netlistsvg_patched.json", "DAQ core, patched JSON"),
    ("adc_digital_current", HERE / "adc_digital/current_full.json", "ADC digital, current Verilog"),
    ("daq_core_current", HERE / "daq_core/current_full.json", "DAQ core, current Verilog"),
)


def run(*args: str, cwd: Path) -> None:
    subprocess.run(args, cwd=cwd, check=True)


def generate_current_json() -> None:
    jobs = (
        (
            "adc_digital",
            (
                "read_verilog design/hdl/adc_digital.v design/hdl/clkgate.v "
                "design/hdl/salogic.v design/hdl/sampdriver.v design/hdl/cells_behavioral.v; "
                "prep -top adc_digital"
            ),
        ),
        (
            "daq_core",
            "read_verilog -I libs/basil/basil/firmware/modules design/fpga/daq_core.v; prep -top daq_core",
        ),
    )
    for folder, command in jobs:
        destination = HERE / folder
        destination.mkdir(parents=True, exist_ok=True)
        run(
            "yosys",
            "-Q",
            "-T",
            "-l",
            str(destination / "current_yosys.log"),
            "-p",
            f"{command}; write_json {destination / 'current_full.json'}",
            cwd=FRIDA,
        )


def prepare_input(source: Path, output: Path) -> None:
    data = json.loads(source.read_text())
    if source.name.endswith("_patched.json"):
        original = json.loads(source.with_name(source.name.replace("_patched.json", ".json")).read_text())
        # The archived patch changed bidirectional pins to inputs. Recover
        # their source directions before choosing a diagram side for them.
        for name, module in data["modules"].items():
            reference = original["modules"].get(name, {})
            for pin, port in module.get("ports", {}).items():
                if reference.get("ports", {}).get(pin, {}).get("direction") == "inout":
                    port["direction"] = "inout"
            for cell_name, cell in module.get("cells", {}).items():
                reference_cell = reference.get("cells", {}).get(cell_name, {})
                for pin, direction in reference_cell.get("port_directions", {}).items():
                    if direction == "inout":
                        cell["port_directions"][pin] = "inout"
    if "daq_core" in data["modules"]:
        module = data["modules"]["daq_core"]
        data = {"creator": data.get("creator", "Yosys"), "modules": {"daq_core": module}}
    elif source.name == "current_full.json" and "adc_digital" in data["modules"]:
        module = data["modules"]["adc_digital"]
        data = {"creator": data.get("creator", "Yosys"), "modules": {"adc_digital": module}}
    for module in data["modules"].values():
        for cell in module["cells"].values():
            if cell["type"].startswith("$paramod") and "\\" in cell["type"]:
                cell["type"] = cell["type"].split("\\")[-1]
    output.write_text(json.dumps(data, indent=2) + "\n")
    run("python", str(ASSETS / "prepare_digital_json.py"), str(output), str(output), cwd=HERE)


def pad_canvas(svg: Path) -> None:
    """Allow for pin text outside netlistsvg's geometry-based canvas."""
    ET.register_namespace("", "http://www.w3.org/2000/svg")
    ET.register_namespace("s", "https://github.com/nturley/netlistsvg")
    tree = ET.parse(svg)
    root = tree.getroot()
    width, height = float(root.attrib["width"]), float(root.attrib["height"])
    left, right, top, bottom = 110, 110, 24, 24
    root.set("viewBox", f"{-left} {-top} {width + left + right:g} {height + top + bottom:g}")
    root.set("width", f"{width + left + right:g}")
    root.set("height", f"{height + top + bottom:g}")
    tree.write(svg, encoding="unicode")


def comparison_tex(title: str) -> str:
    return rf"""\documentclass[11pt]{{article}}
\usepackage[paperwidth=594mm,paperheight=320mm,margin=12mm]{{geometry}}
\usepackage{{graphicx}}
\pagestyle{{empty}}
\begin{{document}}
\begin{{center}}
{{\Large\bfseries {title}}}\par\vspace{{8mm}}
\begin{{minipage}}[t]{{0.49\textwidth}}\vspace{{0pt}}\centering
{{\large A: netlistsvg default}}\par\vspace{{4mm}}
\includegraphics[width=\linewidth,height=0.86\textheight,keepaspectratio]{{old.pdf}}
\end{{minipage}}\hfill
\begin{{minipage}}[t]{{0.49\textwidth}}\vspace{{0pt}}\centering
{{\large B: FRIDA digital skin}}\par\vspace{{4mm}}
\includegraphics[width=\linewidth,height=0.86\textheight,keepaspectratio]{{new.pdf}}
\end{{minipage}}
\end{{center}}
\end{{document}}
"""


def render_digital(folder: str, source: Path, title: str) -> None:
    destination = HERE / folder
    destination.mkdir(parents=True, exist_ok=True)
    prepare_input(source, destination / "input.json")
    for name, skin_args in (("old", ()), ("new", ("--skin", str(SKIN)))):
        run(
            "npx",
            "--yes",
            "netlistsvg@1.0.2",
            "input.json",
            "-o",
            f"{name}.svg",
            *skin_args,
            cwd=destination,
        )
        if name == "new":
            run(
                "python",
                str(ASSETS / "postprocess.py"),
                f"{name}.svg",
                "input.json",
                cwd=destination,
            )
        pad_canvas(destination / f"{name}.svg")
        run("rsvg-convert", "-f", "pdf", "-o", f"{name}.pdf", f"{name}.svg", cwd=destination)
        run("pdftocairo", "-png", "-singlefile", "-r", "100", f"{name}.pdf", name, cwd=destination)

    checked_in = IMAGES / source.name.removesuffix(".json").removesuffix("_patched").replace(
        "adc_digital", "adc_digital_netlistsvg"
    )
    checked_in = checked_in.with_suffix(".pdf")
    if checked_in.is_file() and not (destination / "checked_in.pdf").exists():
        shutil.copy2(checked_in, destination / "checked_in.pdf")
    (destination / "comparison.tex").write_text(comparison_tex(title))
    run("pdflatex", "-interaction=nonstopmode", "-halt-on-error", "comparison.tex", cwd=destination)
    run("pdftocairo", "-png", "-singlefile", "-r", "90", "comparison.pdf", "comparison", cwd=destination)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--refresh-json", action="store_true", help="rebuild current-source JSON with Yosys")
    args = parser.parse_args()
    if args.refresh_json:
        generate_current_json()
    analog_source = ASSETS / "preamp_comparison"
    run("python", "render.py", cwd=analog_source)
    analog_destination = HERE / "analog"
    analog_destination.mkdir(parents=True, exist_ok=True)
    for name in (
        "comparison.pdf",
        "comparison.png",
        "comparison.tex",
        "fsic_original.pdf",
        "fsic_original.svg",
        "new_style.pdf",
        "new_style.svg",
        "new_style.png",
        "old_auto.pdf",
        "old_auto.svg",
        "preamp_netlistsvg.v",
    ):
        shutil.copy2(analog_source / name, analog_destination / name)
    run(
        "rsvg-convert",
        "-f",
        "pdf",
        "-o",
        "analog_catalog.pdf",
        str(ASSETS / "circuitikz_analog.svg"),
        cwd=analog_destination,
    )
    run(
        "pdftocairo", "-png", "-singlefile", "-r", "120", "analog_catalog.pdf", "analog_catalog", cwd=analog_destination
    )
    for case in CASES:
        render_digital(*case)
    (HERE / "README.md").write_text(
        "# Netlistsvg A/B renderings\n\n"
        "Run `python render.py` from this directory to regenerate every comparison.\n\n"
        "`analog/comparison.pdf` compares the curated FSIC preamp figure with the new\n"
        "skin; `analog/analog_catalog.pdf` shows the full analog symbol kit.\n"
        "Digital A/B figures render the same JSON with netlistsvg's default\n"
        "and FRIDA skins. DAQ inputs retain only the top module and shorten\n"
        "generated `$paramod` type names. All `inout` block pins are mapped\n"
        "to right-side `output` ports for presentation, since netlistsvg lacks\n"
        "bidirectional placement by `prepare_digital_json.py`. The archived\n"
        "patched JSON had already turned `inout` pins into inputs; this script\n"
        "restores those directions from the unpatched JSON first.\n"
        "The original and patched DAQ inputs become\n"
        "identical after that mapping, so their A/B pages match exactly.\n"
        "Current-source figures regenerate JSON from `design/hdl/adc_digital.v`\n"
        "and `design/fpga/daq_core.v` with Yosys. The archived DAQ JSON has\n"
        "24 top ports and one GPIO; current Verilog has 33 ports and three.\n"
        "The current and archived ADC digital top-level renders are identical.\n"
        "The FRIDA skin adds bus widths to block pins and terminals and draws a\n"
        "diagonal width tick on each bus without changing the routing stroke.\n"
        "`checked_in.pdf` retains the original documentation figure where present.\n"
    )


if __name__ == "__main__":
    main()
