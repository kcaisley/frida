"""Tests for the Calibre xACT CDAC capacitance parser."""

import json
from pathlib import Path

import pytest

from .pex import (
    parse_adc_cdac_pex,
    parse_cdac_pex,
    write_capacitance_table,
    write_comparison_table,
)


def test_parse_cdac_pex(tmp_path: Path) -> None:
    netlist = tmp_path / "cap.pex.netlist"
    netlist.write_text(
        r"""simulator lang=spectre
subckt cap ( CAP_TOPPLATE CAP_SHIELDPLATE CAP_BOTPLATE_MAIN\\<0\\> \\
 CAP_BOTPLATE_DIFF\\<0\\> )
c1 ( CAP_TOPPLATE CAP_BOTPLATE_MAIN\\<0\\> ) capacitor c=4.5f
c2 ( CAP_TOPPLATE CAP_BOTPLATE_DIFF\\<0\\> ) capacitor c=1.25f
c3 ( CAP_TOPPLATE CAP_SHIELDPLATE ) capacitor c=0.2f
c4 ( CAP_TOPPLATE 0 ) capacitor c=0.05f
c5 ( CAP_SHIELDPLATE 0 ) capacitor c=0.8f
c6 ( N_CAP_TOPPLATE_c_1_n N_CAP_BOTPLATE_MAIN\<0\>_c_2_n ) capacitor c=0.5f
c7 ( N_CAP_TOPPLATE_c_3_n N_CAP_TOPPLATE_c_4_n ) capacitor c=9f
ends cap
""",
        encoding="utf-8",
    )

    result = parse_cdac_pex(netlist, bit_count=1)

    assert result.main_ff == pytest.approx(5.0)
    assert result.diff_ff == pytest.approx(1.25)
    assert result.effective_ff == pytest.approx(3.75)
    assert result.topplate_total_ff == pytest.approx(6.5)
    assert result.shield_total_ff == pytest.approx(1.0)
    json_path, csv_path = write_capacitance_table(tmp_path, result)
    assert json_path.exists()
    assert "effective_ff" in csv_path.read_text(encoding="utf-8")


def test_parse_differential_adc_cdac_pex(tmp_path: Path) -> None:
    netlist = tmp_path / "adc.pex.netlist"
    netlist.write_text(
        r"""simulator lang=spectre
c1 ( VDAC_P DAC_DRIVE_BOTPLATE_MAIN_P\<0\> ) capacitor c=5f
c2 ( VDAC_P:1 DAC_DRIVE_BOTPLATE_DIFF_P\<0\>:2 ) capacitor c=1f
c3 ( N_VDAC_P_c_1_n N_DAC_DRIVE_BOTPLATE_MAIN_P\<0\>_c_2_n ) capacitor c=0.5f
c4 ( VDAC_N DAC_DRIVE_BOTPLATE_MAIN_N\<0\> ) capacitor c=7f
c5 ( VDAC_N:1 DAC_DRIVE_BOTPLATE_DIFF_N\<0\>:2 ) capacitor c=3f
c6 ( VDAC_P VSS_A ) capacitor c=0.2f
c7 ( VDAC_N N_VSS_DAC_c_1_n ) capacitor c=0.4f
""",
        encoding="utf-8",
    )

    result = parse_adc_cdac_pex(netlist, bit_count=1)

    assert result.main_by_bit_ff == pytest.approx((6.25,))
    assert result.diff_by_bit_ff == pytest.approx((2.0,))
    assert result.effective_ff == pytest.approx(4.25)
    assert result.topplate_shield_ff == pytest.approx(0.3)
    assert result.topplate_total_ff == pytest.approx(8.55)


def test_write_comparison_table_has_34_rows_for_16_bits(tmp_path: Path) -> None:
    source = tmp_path / "cap.pex.netlist"
    lines = []
    for bit in range(16):
        lines.extend(
            (
                f"c{bit}m ( CAP_TOPPLATE CAP_BOTPLATE_MAIN<{bit}> ) capacitor c={bit + 2}f",
                f"c{bit}d ( CAP_TOPPLATE CAP_BOTPLATE_DIFF<{bit}> ) capacitor c=1f",
            )
        )
    lines.append("cshield ( CAP_TOPPLATE CAP_SHIELDPLATE ) capacitor c=4f")
    source.write_text("\n".join(lines) + "\n", encoding="utf-8")
    result = parse_cdac_pex(source, bit_count=16)

    csv_path, json_path = write_comparison_table(tmp_path, {"one": result, "two": result})

    assert len(csv_path.read_text(encoding="utf-8").splitlines()) == 35
    assert list(json.loads(json_path.read_text(encoding="utf-8"))) == [
        *(f"main[{bit}]_ff" for bit in reversed(range(16))),
        *(f"diff[{bit}]_ff" for bit in reversed(range(16))),
        "main_plus_diff_total_ff",
        "shunt_dc_ff",
    ]
