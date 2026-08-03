"""Render structural Verilog as an analog netlistsvg schematic.

The input Verilog should describe analog primitives as black-box cells. MOS
cell types named ``mos_n``/``nmos``/``nch*`` and
``mos_p``/``pmos``/``pch*`` are normalized to analog symbols. Bulk terminals
are omitted from the drawing to keep shared supply rails readable.

Run from the repository root with:

    uv run python -m flow.util.verilog_schematic input.v --top Comp -o comp.svg
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import tempfile
from pathlib import Path

_MOS_SKIN = r"""
<g s:type="mos_n" s:width="48" s:height="58" transform="translate(15,350)">
  <s:alias val="mos_n"/><s:alias val="nmos"/>
  <text x="44" y="27" s:attribute="ref" class="$cell_id">MN</text>
  <path d="M24,12 V46 M30,13 V45" class="symbol $cell_id"/>
  <path d="M0,29 H24 M38,0 V18 H30 M30,40 H38 V58" class="connect $cell_id"/>
  <g s:x="38" s:y="0" s:pid="D" s:position="top"/>
  <g s:x="0" s:y="29" s:pid="G" s:position="left"/>
  <g s:x="38" s:y="58" s:pid="S" s:position="bottom"/>
</g>
<g s:type="mos_p" s:width="48" s:height="58" transform="translate(75,350)">
  <s:alias val="mos_p"/><s:alias val="pmos"/>
  <text x="44" y="27" s:attribute="ref" class="$cell_id">MP</text>
  <path d="M26,12 V46 M32,13 V45" class="symbol $cell_id"/>
  <path d="M0,29 H20 M38,0 V18 H32 M32,40 H38 V58" class="connect $cell_id"/>
  <circle cx="23" cy="29" r="3" class="gatebubble $cell_id"/>
  <g s:x="38" s:y="58" s:pid="D" s:position="bottom"/>
  <g s:x="0" s:y="29" s:pid="G" s:position="left"/>
  <g s:x="38" s:y="0" s:pid="S" s:position="top"/>
</g>
"""


def verilog_to_analog_svg(verilog_path: Path, output_path: Path, top: str) -> tuple[Path, Path]:
    """Convert one structural Verilog module to netlistsvg JSON and analog SVG."""

    if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_$]*", top) is None:
        raise ValueError(f"invalid Verilog top-module name {top!r}")
    verilog_path = verilog_path.resolve()
    output_path = output_path.resolve()
    json_path = output_path.with_suffix(".json")
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="frida-netlistsvg-") as temporary_directory:
        temporary_path = Path(temporary_directory)
        yosys_json = temporary_path / "yosys.json"
        yosys_script = f'read_verilog -sv "{verilog_path}"; hierarchy -check -top {top}; write_json "{yosys_json}"'
        subprocess.run(["yosys", "-q", "-p", yosys_script], check=True)

        data = json.loads(yosys_json.read_text())
        if top not in data.get("modules", {}):
            raise ValueError(f"top module {top!r} was not emitted by Yosys")

        for module in data["modules"].values():
            for port in module.get("ports", {}).values():
                if port.get("direction") not in ("input", "output"):
                    port["direction"] = "input"

            for cell in module.get("cells", {}).values():
                cell_type = str(cell.get("type", ""))
                normalized_type = cell_type.lower().lstrip("\\")
                if normalized_type in ("mos_n", "nmos") or normalized_type.startswith(("nch", "nfet")):
                    cell["type"] = "mos_n"
                elif normalized_type in ("mos_p", "pmos") or normalized_type.startswith(("pch", "pfet")):
                    cell["type"] = "mos_p"
                else:
                    continue

                connections = cell.get("connections", {})
                cell["connections"] = {
                    name.upper(): bits for name, bits in connections.items() if name.lower() in {"d", "g", "s"}
                }
                cell["port_directions"] = {
                    name.upper(): "output" if name.lower() == "d" else "input"
                    for name in connections
                    if name.lower() in {"d", "g", "s"}
                }
                parameters = cell.get("parameters", {})
                if parameters:
                    cell.setdefault("attributes", {})["value"] = " ".join(
                        f"{name}={value}"
                        for name, value in sorted(parameters.items())
                        if name.lower() in ("w", "l", "m")
                    )

        json_path.write_text(json.dumps(data, indent=2) + "\n")

        locator = subprocess.run(
            [
                "npx",
                "--yes",
                "--package",
                "netlistsvg",
                "sh",
                "-c",
                'readlink -f "$(command -v netlistsvg)"',
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        executable = Path(locator.stdout.strip())
        package_path = executable.parent.parent
        analog_skin = package_path / "lib" / "analog.svg"
        if not analog_skin.is_file():
            raise FileNotFoundError(f"netlistsvg analog skin not found at {analog_skin}")
        skin_text = analog_skin.read_text()
        skin_path = temporary_path / "analog_mos.svg"
        skin_path.write_text(skin_text.replace("</svg>", _MOS_SKIN + "\n</svg>"))

        subprocess.run(
            ["node", str(executable), str(json_path), "-o", str(output_path), "--skin", str(skin_path)],
            check=True,
        )

    return json_path, output_path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("verilog", type=Path, help="structural Verilog input")
    parser.add_argument("--top", required=True, help="top-level Verilog module")
    parser.add_argument("-o", "--output", required=True, type=Path, help="output SVG path")
    args = parser.parse_args()

    json_path, svg_path = verilog_to_analog_svg(args.verilog, args.output, args.top)
    print(f"Created {json_path}")
    print(f"Created {svg_path}")


if __name__ == "__main__":
    main()
