"""Put bidirectional Yosys ports on the right in netlistsvg block diagrams.

netlistsvg has input and output sides but no bidirectional side. The source
JSON is unchanged; this presentation copy places every ``inout`` block pin
and top-level terminal with the outputs.

    python flow/util/skins/prepare_digital_json.py source.json render.json
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def orient_inout_ports(netlist: dict) -> dict:
    for module in netlist["modules"].values():
        for port in module.get("ports", {}).values():
            if port["direction"] == "inout":
                port["direction"] = "output"
        for cell in module.get("cells", {}).values():
            for pin, direction in cell.get("port_directions", {}).items():
                if direction == "inout":
                    cell["port_directions"][pin] = "output"
    return netlist


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    netlist = orient_inout_ports(json.loads(args.source.read_text()))
    args.output.write_text(json.dumps(netlist, indent=2) + "\n")


if __name__ == "__main__":
    main()
