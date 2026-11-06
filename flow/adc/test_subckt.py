"""Software-only tests for the ADC generator."""

import importlib.util
import shutil
from pathlib import Path

import hdl21 as h
import numpy as np
import pytest
from pydantic import ValidationError

from flow import capdac

from .params import Params
from .subckt import Adc, calc_ideal_capacitances, digital_net_aliases


def test_adc():
    """Verify ADC generator produces a valid module."""
    m = Adc(Params())
    assert m is not None


def test_invalid_adc_params_are_refused_when_made():
    """A resolution or an array no converter has, a converter of another resolution than its
    array's, or an array its netlist's legacy array cannot be (unit capacitors, another coarse
    weight): refused by the parameters' types (a comparator or a sampler of a zero size likewise,
    flow/comp and flow/samp's test_subckt.py)."""
    for make in (
        lambda: Params(adc_bits=0),
        lambda: capdac.Params(bits=7),
        lambda: capdac.Params(bits=15),
        lambda: capdac.Params(extra=-1),
        lambda: capdac.Params(weights=(1,) * 15),
        lambda: Params(adc_bits=10),
        lambda: Params(cdac=capdac.Params(weight_impl=capdac.WeightImpl.UNIT_CAPS)),
        lambda: Params(cdac=capdac.Params(coarse_weight=32)),
    ):
        with pytest.raises(ValidationError):
            make()


def test_adc_accepts_any_array_with_sixteen_physical_stages():
    params = Params(adc_bits=14, cdac=capdac.Params(bits=14, redundancy=capdac.Redundancy.LSB_SPLIT, extra=3))
    assert Adc(params).dac_state_p.width == 16


def test_ideal_capacitances_reproduce_the_generated_weights() -> None:
    cdac = capdac.Params()
    main_f, diff_f = calc_ideal_capacitances(cdac, 1.2)
    weights = capdac.Model.weights(cdac)
    np.testing.assert_allclose((main_f - diff_f) * sum(weights) / np.sum(main_f - diff_f), weights)


def _tsmc65_cells() -> bool:
    try:
        return importlib.util.find_spec("pdk.tsmc65.hdl21.cells") is not None
    except ModuleNotFoundError:
        return False


@pytest.mark.skipif(
    shutil.which("yosys") is None or not _tsmc65_cells(), reason="synthesizing the digital block needs yosys and TSMC65"
)
@pytest.mark.parametrize(("bits", "extra"), ((12, 0), (10, 2), (12, 6)))
def test_adc_at_any_stage_count_binds_a_synthesized_digital_block_c0_first(bits, extra):
    """Any array: the digital block synthesized for its stage count, register 0 on C0."""
    stages = bits - 1 + extra
    redundancy = capdac.Redundancy.MSB_REDIST if extra else capdac.Redundancy.BINARY
    module = Adc(Params(adc_bits=bits, cdac=capdac.Params(bits=bits, redundancy=redundancy, extra=extra)))
    assert module.dac_state_p.width == stages
    assert module.xdigital.of.module.name == f"adc_digital_n{stages}"
    for stage in range(stages):
        for port, signal in (("dac_astate_p", module.dac_astate_p), ("dac_state_n_main", module.dac_state_n)):
            connection = module.xdigital.conns[f"{port}[{stage}]"]
            assert connection.index == stage and connection.parent is signal
    assert sum(name.startswith("xcapdriver_") for name in module.instances) == 4


def test_adc_hierarchy_exports_without_duplicate_cell_names():
    """Both sides share one array definition, fresh for each top-level build."""
    module = Adc(Params())
    assert module.xcaparray_p.of is module.xcaparray_n.of
    assert module.xcapdriver_p_main.of is not Adc(Params()).xcapdriver_p_main.of
    package = h.to_proto(module)
    names = [cell.name for cell in package.modules]
    assert len(names) == len(set(names))


def test_adc_digital_port_order_matches_spice_subckt():
    """Keep the HDL21 declaration positionally identical to the synthesized block."""
    netlist = Path(__file__).resolve().parents[2] / "design/spice/adc_digital.sp"
    declaration = next(line for line in netlist.read_text().splitlines() if line.startswith(".SUBCKT adc_digital "))
    spice_ports = declaration.split()[2:]

    module = Adc(Params())
    hdl21_ports = [port.name for port in module.xdigital.of.module.port_list]

    assert hdl21_ports == spice_ports


@pytest.mark.parametrize("pin", ("seq_typo", "dac_state_p_main[16]", "dac_state_p_main"))
def test_digital_binding_rejects_unknown_pins_and_incompatible_widths(pin):
    module = h.ExternalModule(name="bad_digital", port_list=[h.Inout(name=pin)])
    with pytest.raises((KeyError, ValueError)):
        digital_net_aliases(module)


def test_adc_uses_comparator_clock_complement_and_separate_dac_supply():
    """Connect comparator and CDAC power domains without borrowing sampler timing."""
    module = Adc(Params())

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

    module = Adc(Params())

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
    module = Adc(Params())
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
