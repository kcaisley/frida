"""Software integration test for analog structural-Verilog rendering."""

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
