"""The ADC's digital block (``design/hdl/adc_digital.v``) at any number of stages, as a SPICE
netlist of the PDK's standard cells.

    path, cell = digital_netlist(12)  # build/models/adc_digital/tsmc65/n12/adc_digital_n12.sp

FRIDA's 16 stages are the hardened OpenROAD netlist (``design/spice/adc_digital.sp``: placed,
clock-tree buffered and routed, from an earlier RTL that switched register 15 first). Any other
count is synthesized from the RTL at ``N_STAGES`` with yosys (on the PATH: the OSS CAD suite)
onto the same TSMC65 LVT library, without placement or clock tree: flip-flops by ``dfflibmap``,
the logic by ABC into generic gates, bound to named cells by ``GATES`` (ABC's own Liberty reader
misnames this library's output pins, which loses every gate it maps), constants on tie cells and
ports that only alias another net behind a buffer. Register 0 drives C0, as in the RTL. The
netlist is cached under ``build/models/adc_digital/``.
"""

from __future__ import annotations

import gzip
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HARDENED = ROOT / "design/spice/adc_digital.sp"
SOURCES = tuple(
    ROOT / "design/hdl" / name for name in ("cells_tsmc65.v", "clkgate.v", "sampdriver.v", "salogic.v", "adc_digital.v")
)
CACHE = ROOT / "build/models/adc_digital"
# yosys's generic gates -> (library cell, its pin for each gate port)
GATES = {
    "$_BUF_": ("BUFFD1LVT", {"A": "I", "Y": "Z"}),
    "$_NOT_": ("INVD1LVT", {"A": "I", "Y": "ZN"}),
    "$_AND_": ("AN2D1LVT", {"A": "A1", "B": "A2", "Y": "Z"}),
    "$_NAND_": ("ND2D1LVT", {"A": "A1", "B": "A2", "Y": "ZN"}),
    "$_OR_": ("OR2D1LVT", {"A": "A1", "B": "A2", "Y": "Z"}),
    "$_NOR_": ("NR2D1LVT", {"A": "A1", "B": "A2", "Y": "ZN"}),
    "$_XOR_": ("XOR2D1LVT", {"A": "A1", "B": "A2", "Y": "Z"}),
    "$_XNOR_": ("XNR2D1LVT", {"A": "A1", "B": "A2", "Y": "ZN"}),
    "$_MUX_": ("MUX2D1LVT", {"A": "I0", "B": "I1", "S": "S", "Y": "Z"}),  # Y = S ? B : A
}


def digital_cell(stages: int) -> str:
    """The digital block's subcircuit name: FRIDA's at 16 stages, a synthesized one otherwise."""
    return "adc_digital" if stages == 16 else f"adc_digital_n{stages}"


def digital_netlist(stages: int, pdk: str = "tsmc65") -> tuple[Path, str]:
    """The digital block's SPICE netlist at ``stages`` and its subcircuit name, synthesized on
    first use."""
    if stages == 16:
        return HARDENED, digital_cell(stages)
    if pdk != "tsmc65":
        raise ValueError(f"the digital block is synthesized onto TSMC65's cells only, not {pdk}'s")
    if stages < 2:
        raise ValueError(f"the digital block needs at least two stages, not {stages}")
    cell = digital_cell(stages)
    path = CACHE / pdk / f"n{stages}" / f"{cell}.sp"
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        # another process may synthesize the same count: each writes its own and renames it in
        with tempfile.TemporaryDirectory(dir=path.parent) as work:
            text = _synthesize(stages, cell, Path(work))
            (Path(work) / path.name).write_text(text)
            os.replace(Path(work) / path.name, path)
    return path, cell


def _synthesize(stages: int, cell: str, work: Path) -> str:
    from pdk.tsmc65.hdl21.site import STANDARD_CELL_SPICE_NETLISTS
    from pdk.tsmc65.layout.paths import STD_LIBERTY

    if shutil.which("yosys") is None:
        raise FileNotFoundError("yosys is not on the PATH (the OSS CAD suite's bin)")
    liberty = work / "cells.lib"
    with gzip.open(STD_LIBERTY, "rb") as compressed:
        liberty.write_bytes(compressed.read())
    gates = work / "gates.v"
    gates.write_text(
        "".join(
            f"module \\{gate} ({', '.join(pins)});\n"
            + "".join(f"  {'output' if port == 'Y' else 'input'} {port};\n" for port in pins)
            + f"  {library} _TECHMAP_REPLACE_ ({', '.join(f'.{pin}({port})' for port, pin in pins.items())});\n"
            + "endmodule\n"
            for gate, (library, pins) in GATES.items()
        )
    )
    script = work / "synth.ys"
    script.write_text(
        "\n".join(
            (
                f"read_liberty -lib {liberty}",
                f"read_verilog -sv {' '.join(str(source) for source in SOURCES)}",
                f"chparam -set N_STAGES {stages} adc_digital",
                "hierarchy -check -top adc_digital",
                "synth -top adc_digital -flatten",
                f"dfflibmap -liberty {liberty}",
                "abc -g AND,NAND,OR,NOR,XOR,XNOR,MUX",
                f"techmap -map {gates}",
                "opt_clean -purge",
                "hilomap -singleton -hicell TIEHLVT Z -locell TIELLVT ZN",
                "insbuf -buf BUFFD1LVT I Z",
                "opt_clean -purge",
                "check -assert",
                f"write_json {work / 'netlist.json'}",
            )
        )
    )
    subprocess.run(["yosys", "-q", "-l", str(work / "yosys.log"), str(script)], check=True, capture_output=True)
    module = json.loads((work / "netlist.json").read_text())["modules"]["adc_digital"]
    pin_order = {}
    for netlist in STANDARD_CELL_SPICE_NETLISTS:
        for line in Path(netlist).read_text(errors="replace").splitlines():
            words = line.split()
            if len(words) > 2 and words[0].lower() == ".subckt":
                pin_order.setdefault(words[1], words[2:])
    # each bit's node: a port bit by its name, as OpenROAD writes them; an inner net by its id
    nodes: dict[int, str] = {}
    ports = []
    for name, port in module["ports"].items():
        for index, bit in enumerate(port["bits"]):
            node = name if len(port["bits"]) == 1 else f"{name}[{index}]"
            if not isinstance(bit, int) or bit in nodes:
                raise ValueError(f"{cell} port bit {node} is a constant or aliases {nodes.get(bit)}")
            nodes[bit] = node
            ports.append(node)
    lines = [f"* {cell}: design/hdl/adc_digital.v at N_STAGES={stages}, synthesized by flow.adc.digital", ""]
    lines.append(f".SUBCKT {cell} {' '.join(ports)} vdd_d vss_d")
    unconnected = 0
    for index, instance in enumerate(module["cells"].values()):
        connections = []
        for pin in pin_order[instance["type"]]:
            if pin == "VDD":
                connections.append("vdd_d")
            elif pin == "VSS":
                connections.append("vss_d")
            elif pin in instance["connections"]:
                (bit,) = instance["connections"][pin]
                if not isinstance(bit, int):
                    raise ValueError(f"{cell}: {instance['type']} pin {pin} is tied to {bit!r}, not a tie cell")
                connections.append(nodes.setdefault(bit, f"n{bit}"))
            else:  # an output nothing reads (a flip-flop's QN)
                unconnected += 1
                connections.append(f"nc{unconnected}")
        lines.append(f"X{index} {' '.join(connections)} {instance['type']}")
    lines += [f".ENDS {cell}", ""]
    return "\n".join(lines)
