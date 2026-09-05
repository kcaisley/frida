"""Software-only tests for the ADC generator."""

from pathlib import Path

from .subckt import Adc, AdcParams, Frida1AdcDigital


def test_adc():
    """Verify ADC generator produces a valid module."""
    m = Adc(AdcParams())
    assert m is not None


def test_adc_digital_port_order_matches_spice_subckt():
    """Keep the HDL21 declaration positionally identical to the synthesized block."""
    netlist = Path(__file__).resolve().parents[2] / "design/spice/adc_digital.sp"
    declaration = next(line for line in netlist.read_text().splitlines() if line.startswith(".SUBCKT adc_digital "))
    spice_ports = declaration.split()[2:]

    hdl21_ports = []
    for port in Frida1AdcDigital.port_list:
        if port.width == 1:
            hdl21_ports.append(port.name)
        else:
            hdl21_ports.extend(f"{port.name}[{index}]" for index in reversed(range(port.width)))

    assert hdl21_ports == spice_ports


def test_adc_uses_comparator_clock_complement_and_separate_dac_supply():
    """Connect comparator and CDAC power domains without borrowing sampler timing."""
    module = Adc(AdcParams())

    assert module.xdigital.conns["comp_out"] is module.comp_out
    assert module.xcomp.conns["clkb"] is module.clk_comp_b
    assert module.MP_clk_comp_b.conns["g"] is module.clk_comp
    assert module.MN_clk_comp_b.conns["g"] is module.clk_comp
    assert module.xcdac_p.conns["vdd"] is module.vdd_dac
    assert module.xcdac_p.conns["vss"] is module.vss_dac
    assert module.xcdac_n.conns["vdd"] is module.vdd_dac
    assert module.xcdac_n.conns["vss"] is module.vss_dac


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
        parts = module.xdigital.conns[port].parts
        assert [part.index for part in parts] == list(range(16))
        assert all(part.parent is signal for part in parts)
