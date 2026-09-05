"""Repository-boundary checks for the C0-first ADC convention."""

from pathlib import Path

from flow.adc.sim import AdcTbParams
from flow.cdac import get_cdac_weights
from flow.scans.scan_adc import convert_dac_caps_to_adc_weights


def test_default_weights_and_decisions_are_chronological() -> None:
    weights = get_cdac_weights(AdcTbParams().dut.cdac)

    assert weights == [768, 512, 320, 192, 96, 64, 32, 24, 12, 10, 5, 4, 4, 2, 1, 1]
    assert convert_dac_caps_to_adc_weights(weights) == [
        1536,
        1024,
        640,
        384,
        192,
        128,
        64,
        48,
        24,
        20,
        10,
        8,
        8,
        4,
        2,
        2,
        1,
    ]


def test_static_spice_uses_c0_for_the_largest_cap_and_driver() -> None:
    repository = Path(__file__).resolve().parents[1]
    caparray = (repository / "design" / "spice" / "caparray.cdl").read_text(encoding="utf-8")
    capdriver = (repository / "design" / "spice" / "capdriver.cdl").read_text(encoding="utf-8")

    assert "Cmain0 cap_topplate cap_botplate_main[0] 619.2f" in caparray
    assert "Cmain15 cap_topplate cap_botplate_main[15] 26.4f" in caparray
    assert "Xxor0_0 dac_drive_invert dac_state[0] dac_drive[0]" in capdriver
    assert "Xxor15 dac_drive_invert dac_state[15] dac_drive[15]" in capdriver


def test_rtl_selects_register_zero_first() -> None:
    repository = Path(__file__).resolve().parents[1]
    source = (repository / "design" / "hdl" / "salogic.v").read_text(encoding="utf-8")

    assert "dac_cycle <= 16'h0001;" in source
    assert "dac_cycle <= dac_cycle << 1;" in source
    assert not (repository / "design" / "spice" / "frida_complete.cdl").exists()


def test_new_cores_translate_serialized_fields_to_internal_stage_zero() -> None:
    repository = Path(__file__).resolve().parents[1]
    for filename, index in (("frida_core.v", "i"), ("frida_core_1chan.v", "stage")):
        source = "".join((repository / "design" / "hdl" / filename).read_text(encoding="utf-8").split())
        assert f"shared_dac_astate_p[{index}]=spi_bits[63-{index}]" in source
        assert f"shared_dac_bstate_n[{index}]=spi_bits[15-{index}]" in source
