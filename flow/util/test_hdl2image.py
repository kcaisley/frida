"""Software integration test for analog structural-Verilog rendering."""

import json
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from flow.util.hdl2image import ANALOG_SKIN, verilog_to_analog_svg


def test_verilog_to_analog_svg(tmp_path: Path) -> None:
    """Render recognized PDK-style NMOS and PMOS cells with analog symbols."""

    verilog = tmp_path / "inverter.v"
    verilog.write_text(
        """
(* blackbox *) module nfet(input d, input g, input s, input b); endmodule
(* blackbox *) module pfet(input d, input g, input s, input b); endmodule
module inverter(input vin, input vdd, input vss, output vout);
  pfet MP (.d(vout), .g(vin), .s(vdd), .b(vdd));
  nfet MN (.d(vout), .g(vin), .s(vss), .b(vss));
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
    """The preamp's sole gate inputs should be direct."""
    root = Path(__file__).resolve().parents[2]
    verilog = root / "docs/images/netlistsvg/preamp_netlistsvg.v"
    skin = ANALOG_SKIN
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

    clock_bit = module["ports"]["clk"]["bits"][0]
    clock_xy = port_xy("clk", "Y")
    assert clock_xy[1] == port_xy("MN3", "G")[1]
    clock_lines = [line for line in svg_root.findall(f"{{{svg_ns}}}line") if line.get("class") == f"net_{clock_bit}"]
    assert any(
        (float(line.get("x1")), float(line.get("y1"))) == clock_xy
        or (float(line.get("x2")), float(line.get("y2"))) == clock_xy
        for line in clock_lines
    )


def test_an_hdl21_gate_netlist_is_drawn_as_its_cells() -> None:
    """An hdl21 module of generic cells as netlistsvg's JSON, no synthesis: each cell its function's
    symbol in the digital skin (a latch, which the skin lacks, a box of its name), a bus bit a slice
    of its signal's bits, an instance of another module a box with its ports' directions, supplies
    left out."""
    import hdl21 as h

    from flow.circuit.cells import cell
    from flow.util.hdl2image import hdl21_to_json

    Inner = h.Module(name="Inner")
    Inner.a, Inner.y = h.Input(), h.Output()
    Top = h.Module(name="Top")
    Top.clk, Top.d = h.Input(), h.Input()
    Top.q = h.Output(width=2)
    Top.vdd, Top.vss = h.Inout(), h.Inout()
    Top.n = h.Signal()
    Top.Xinv = cell("inv", 2)(A=Top.d, Y=Top.n, VDD=Top.vdd, VSS=Top.vss)
    Top.Xff = cell("dff", 1)(D=Top.n, CLK=Top.clk, Q=Top.q[0], VDD=Top.vdd, VSS=Top.vss)
    Top.Xlatch = cell("latch", 1)(D=Top.n, EN=Top.clk, Q=Top.q[1], VDD=Top.vdd, VSS=Top.vss)
    Top.xinner = Inner(a=Top.n, y=Top.q[1])
    module = hdl21_to_json(Top)["modules"]["Top"]
    assert set(module["ports"]) == {"clk", "d", "q"}  # no supply
    q = module["ports"]["q"]["bits"]
    cells = module["cells"]
    assert [cells[name]["type"] for name in ("Xinv", "Xff", "Xlatch", "xinner")] == ["$_NOT_", "$dff", "latch", "Inner"]
    assert cells["Xff"]["connections"] == {
        "D": cells["Xinv"]["connections"]["Y"],
        "CLK": module["ports"]["clk"]["bits"],
        "Q": [q[0]],
    }
    assert cells["Xlatch"]["port_directions"] == {"D": "input", "EN": "input", "Q": "output"}
    assert cells["xinner"]["port_directions"] == {"a": "input", "y": "output"} and cells["xinner"]["connections"][
        "y"
    ] == [q[1]]
    assert "n" in module["netnames"] and "vdd" not in module["netnames"]
