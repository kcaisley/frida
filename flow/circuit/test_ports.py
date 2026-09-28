"""Reject naming/ wiring mistakes before launching an external simulator."""

import hdl21 as h
import pytest

from .ports import module_from_ports, port_connections, scalar_connections
from .ports import testbench_from_ports as make_testbench


@h.bundle
class Pins:
    data = h.Input(width=3)
    clock = h.Clock()
    vdd = h.Power(direction=h.PortDir.INOUT)
    vss_a, vss_d = h.Ground(), h.Ground()


def test_testbench_copies_metadata_and_ties_only_grounds():
    tb, connections = make_testbench("tb", Pins.signals)
    dut = module_from_ports("dut", Pins.signals)
    assert connections["vss_a"] is connections["vss_d"] is tb.vss
    assert connections["vdd"] is tb.vdd
    assert tb.clock.usage == dut.clock.usage == h.Usage.CLOCK
    assert tb.data.width == dut.data.width == 3
    assert tb.data is not dut.data and dut.data is not Pins.data
    assert set(tb.ports) == {"vss"}
    assert dut.data.direction == h.PortDir.INPUT
    tb.clock.props["simulation"] = True
    assert "simulation" not in dut.clock.props and "simulation" not in Pins.clock.props


@pytest.mark.parametrize("renames", ({"clcok": "clk"}, {"clock": "data"}, {"clock": "vss"}, {"vss_a": "gnd"}))
def test_testbench_rejects_unknown_or_colliding_renames(renames):
    with pytest.raises(ValueError):
        make_testbench("tb", Pins.signals, renames=renames)


def test_connections_reject_unknown_missing_and_wrong_width():
    module = module_from_ports("dut", Pins.signals)
    with pytest.raises(ValueError, match="Unknown port"):
        port_connections(Pins.signals, module, clcok=module.clock)
    with pytest.raises(ValueError, match="expects width 3"):
        port_connections(Pins.signals, module, data=module.clock)
    with pytest.raises(KeyError, match="data"):
        port_connections(Pins.signals, h.Module())
    with pytest.raises(ValueError, match="differs from its declaration"):
        module_from_ports("dut", {"datta": Pins.data})


@pytest.mark.parametrize("reverse,indices", ((False, (2, 1, 0)), (True, (0, 1, 2))))
def test_scalar_adapter_preserves_bus_order_and_physical_bits(reverse, indices):
    bus = h.Signal(width=3)
    mapping = scalar_connections({"bus": bus}, reverse=reverse)
    assert tuple(mapping) == ("bus_2", "bus_1", "bus_0")
    assert tuple(net.index for net in mapping.values()) == indices


def test_scalar_adapter_rejects_ambiguous_bus_and_scalar_names():
    with pytest.raises(ValueError, match="collide"):
        scalar_connections({"bus": h.Signal(width=2), "bus_0": h.Signal()})


@pytest.mark.parametrize("block", ("adc", "comp", "samp"))
def test_generated_save_maps_reference_existing_nets_and_source_terminals(block):
    from importlib import import_module

    sim = import_module(f"flow.{block}.sim")
    name = block.capitalize()
    tb = getattr(sim, f"{name}Tb")(getattr(sim, f"{name}TbParams")())
    saved = sim.adc_signal_names(tb, "hdl21gen") if block == "adc" else getattr(sim, f"{block}_signal_names")()
    assert len(set(saved.values())) == len(saved)
    for raw in saved:
        if raw == "time":
            continue
        top, *hierarchy, node = raw.split(".")
        assert top == "xtop"
        module = tb
        for instance in hierarchy:
            module = module.instances[instance].of
        if ":" in node:
            instance, terminal = node.split(":")
            assert terminal in module.instances[instance].conns
        else:
            names = scalar_connections({**module.ports, **module.signals})
            assert node in names, raw
