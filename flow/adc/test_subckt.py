"""Software-only tests for the ADC generator."""

from pathlib import Path

import hdl21 as h
import pytest

from flow.caparray import CapArrayConfig, RedunStrat
from flow.comp import CompParams
from flow.samp import SampParams

from . import subckt
from .subckt import Adc, AdcParams, is_valid_adc_params


def test_adc():
    """Verify ADC generator produces a valid module."""
    assert is_valid_adc_params(AdcParams())
    m = Adc(AdcParams())
    assert m is not None


@pytest.mark.parametrize(
    "params",
    (
        AdcParams(adc_bits=0),
        AdcParams(cdac=CapArrayConfig(n_dac=0, n_extra=16)),
        AdcParams(cdac=CapArrayConfig(n_dac=17, n_extra=-1)),
        AdcParams(cdac=CapArrayConfig(n_extra=4)),
        AdcParams(cdac=CapArrayConfig(weights=(1,) * 15)),
        AdcParams(comp=CompParams(srlatch_n_w=0)),
        AdcParams(samp=SampParams(mos_w=0)),
    ),
)
def test_invalid_adc_params_fail_before_creating_a_module(params, monkeypatch):
    monkeypatch.setattr(subckt, "module_from_ports", lambda *_: pytest.fail("invalid ADC reached generation"))
    assert is_valid_adc_params(params) is False
    with pytest.raises(ValueError, match="Invalid ADC params"):
        Adc(params)


def test_adc_accepts_a_binary_array_with_sixteen_physical_stages():
    params = AdcParams(cdac=CapArrayConfig(n_dac=16, n_extra=0, redun_strat=RedunStrat.RDX2))
    assert is_valid_adc_params(params) is True
    assert Adc(params).dac_state_p.width == 16


def test_adc_hierarchy_exports_without_duplicate_cell_names():
    """Both sides share one array definition, fresh for each top-level build."""
    module = Adc(AdcParams())
    assert module.xcaparray_p.of is module.xcaparray_n.of
    assert module.xcapdriver_p_main.of is not Adc(AdcParams()).xcapdriver_p_main.of
    package = h.to_proto(module)
    names = [cell.name for cell in package.modules]
    assert len(names) == len(set(names))


def test_adc_digital_port_order_matches_spice_subckt():
    """Keep the HDL21 declaration positionally identical to the synthesized block."""
    netlist = Path(__file__).resolve().parents[2] / "design/spice/adc_digital.sp"
    declaration = next(line for line in netlist.read_text().splitlines() if line.startswith(".SUBCKT adc_digital "))
    spice_ports = declaration.split()[2:]

    module = Adc(AdcParams())
    hdl21_ports = [port.name for port in module.xdigital.of.module.port_list]

    assert hdl21_ports == spice_ports


def test_adc_uses_comparator_clock_complement_and_separate_dac_supply():
    """Connect comparator and CDAC power domains without borrowing sampler timing."""
    module = Adc(AdcParams())

    assert module.xdigital.conns["comp_out"] is module.comp_out
    assert module.xcomp.conns["clkb"] is module.clk_comp_b
    assert module.MP_clk_comp_b.conns["g"] is module.clk_comp
    assert module.MN_clk_comp_b.conns["g"] is module.clk_comp
    for side in ("p", "n"):
        assert module.instances[f"xcaparray_{side}"].conns["cap_shieldplate"] is module.vss_a
        for kind in ("main", "diff"):
            driver = module.instances[f"xcapdriver_{side}_{kind}"]
            assert driver.conns["vdd"] is module.vdd_dac
            assert driver.conns["vss"] is module.vss_dac


def test_adc_translates_the_legacy_digital_bus_only_at_its_boundary():
    """Connect legacy physical bit 15 to canonical stage C0."""

    module = Adc(AdcParams())

    for port, signal in (
        ("dac_astate_p", module.dac_astate_p),
        ("dac_bstate_p", module.dac_bstate_p),
        ("dac_astate_n", module.dac_astate_n),
        ("dac_bstate_n", module.dac_bstate_n),
        ("dac_state_p_main", module.dac_state_p),
        ("dac_state_n_main", module.dac_state_n),
    ):
        for stage in range(16):
            connection = module.xdigital.conns[f"{port}[{15 - stage}]"]
            assert connection.index == stage
            assert connection.parent is signal


def test_adc_bottom_plates_connect_passive_arrays_to_digital_controlled_drivers():
    module = Adc(AdcParams())
    assert sum(name.startswith("xcapdriver_") for name in module.instances) == 4
    assert sum(name.startswith("xcaparray_") for name in module.instances) == 2
    for side in ("p", "n"):
        array = module.instances[f"xcaparray_{side}"]
        assert array.conns["cap_topplate"] is module.namespace[f"vdac_{side}"]
        for kind, suffix in (("main", ""), ("diff", "_diff")):
            driver = module.instances[f"xcapdriver_{side}_{kind}"]
            bottom = module.namespace[f"dac_botplate_{side}{suffix}"]
            assert driver.conns["dac_drive"] is bottom
            assert driver.conns["dac_state"] is module.namespace[f"dac_state_{side}{suffix}"]
            assert driver.conns["dac_drive_invert"] is module.namespace[f"dac_invert_{side}_{kind}"]
            for stage in range(16):
                assert array.conns[f"cap_botplate_{kind}<{stage}>"] == bottom[stage]
                assert (
                    module.xdigital.conns[f"dac_state_{side}_{kind}[{15 - stage}]"] == driver.conns["dac_state"][stage]
                )
            assert module.xdigital.conns[f"dac_invert_{side}_{kind}"] is driver.conns["dac_drive_invert"]
