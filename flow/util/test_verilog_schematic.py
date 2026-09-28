"""Software integration test for analog structural-Verilog rendering."""

import json
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from flow.util.verilog_schematic import verilog_to_analog_svg


def test_verilog_to_analog_svg(tmp_path: Path) -> None:
    """Render recognized PDK-style NMOS and PMOS cells with analog symbols."""

    verilog = tmp_path / "inverter.v"
    verilog.write_text(
        """
(* blackbox *) module nch_lvt(input d, input g, input s, input b); endmodule
(* blackbox *) module pch_lvt(input d, input g, input s, input b); endmodule
module inverter(input vin, input vdd, input vss, output vout);
  pch_lvt MP (.d(vout), .g(vin), .s(vdd), .b(vdd));
  nch_lvt MN (.d(vout), .g(vin), .s(vss), .b(vss));
endmodule
"""
    )

    try:
        json_path, svg_path = verilog_to_analog_svg(verilog, tmp_path / "inverter.svg", "inverter")
    except FileNotFoundError as error:
        pytest.skip(str(error))

    data = json_path.read_text()
    svg = svg_path.read_text()
    assert '"type": "mos_p"' in data
    assert '"type": "mos_n"' in data
    assert 's:type="mos_p"' in svg
    assert 's:type="mos_n"' in svg


def test_custom_skin_places_single_gate_inputs_straight(tmp_path: Path) -> None:
    """The preamp's sole gate inputs should be direct, with the shared clock above."""
    root = Path(__file__).resolve().parents[2]
    verilog = root / "docs/images/preamp_netlistsvg.v"
    skin = root / "flow/util/skins/circuitikz_analog.svg"
    json_path, svg_path = verilog_to_analog_svg(verilog, tmp_path / "preamp.svg", "preamp_netlistsvg", skin)
    module = json.loads(json_path.read_text())["modules"]["preamp_netlistsvg"]
    svg_ns = "http://www.w3.org/2000/svg"
    skin_ns = "https://github.com/nturley/netlistsvg"
    svg_root = ET.parse(svg_path).getroot()
    groups = {group.get("id"): group for group in svg_root.findall(f"{{{svg_ns}}}g")}

    def port_xy(cell: str, pin: str) -> tuple[float, float]:
        group = groups[f"cell_{cell}"]
        x, y = map(float, group.get("transform", "").removeprefix("translate(").removesuffix(")").split(","))
        port = group.find(f"{{{svg_ns}}}g[@{{{skin_ns}}}pid='{pin}']")
        assert port is not None
        return x + float(port.get(f"{{{skin_ns}}}x")), y + float(port.get(f"{{{skin_ns}}}y"))

    for input_name, transistor in (("inn", "MN1"), ("inp", "MN2")):
        input_xy = port_xy(input_name, "Y")
        gate_xy = port_xy(transistor, "G")
        assert input_xy[1] == gate_xy[1]
        bit = module["ports"][input_name]["bits"][0]
        lines = [line for line in svg_root.findall(f"{{{svg_ns}}}line") if line.get("class") == f"net_{bit}"]
        assert len(lines) == 1
        assert (float(lines[0].get("x1")), float(lines[0].get("y1"))) == input_xy
        assert (float(lines[0].get("x2")), float(lines[0].get("y2"))) == gate_xy

    assert port_xy("clk", "Y")[1] < port_xy("MP1", "G")[1]
    assert port_xy("MP1", "G")[0] < port_xy("MP2", "G")[0]
