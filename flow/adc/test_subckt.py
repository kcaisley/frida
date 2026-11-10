"""Software-only tests for the ADC generator. Its DAC's sides are capdac's, resolved to the active
PDK's devices, so a test that builds the ADC binds TSMC65 (``tsmc65``, ``flow/conftest.py``) and a
PDK-free checkout (CI) skips it."""

import importlib.util
import io
import shutil
from pathlib import Path

import hdl21 as h
import pytest
from pydantic import ValidationError

from flow import capdac
from flow.util.netlist import subcircuit_ports

from .params import Fabricated, Params
from .subckt import Nets, _digital, _digital_aliases, _frida1_ports, _generated_aliases, netlist


def _loads(module: h.Module, signal: h.Signal) -> set[str]:
    """The instances of ``module`` connected to ``signal`` or a bit of it."""
    return {
        name
        for name, instance in module.instances.items()
        for net in instance.conns.values()
        if net is signal or (isinstance(net, h.Slice) and net.parent is signal)
    }


def _inversions(chain: h.Module) -> int:
    """How many inverters a driver's chain holds from its input to its output, each a complementary
    pair between the rails on the one before it."""
    node, count = chain.A, 0
    while node is not chain.Y:
        (cell,) = (instance for instance in chain.instances.values() if instance.conns["A"] is node)
        inverter = cell.of
        assert inverter.mn0.conns == {"d": inverter.Y, "g": inverter.A, "s": inverter.VSS, "b": inverter.VSS}
        assert inverter.mp0.conns == {"d": inverter.Y, "g": inverter.A, "s": inverter.VDD, "b": inverter.VDD}
        assert (cell.conns["VDD"], cell.conns["VSS"]) == (chain.VDD, chain.VSS)
        node, count = cell.conns["Y"], count + 1
    return count


def test_adc(tsmc65):
    """Verify ADC generator produces a valid module."""
    m = netlist(Params())
    assert m is not None


def test_the_adc_needs_a_pdk(monkeypatch: pytest.MonkeyPatch) -> None:
    """Its DAC's devices are the active PDK's: with none, it says so."""
    monkeypatch.setattr("flow.adc.subckt.active_pdk", lambda: None)
    with pytest.raises(RuntimeError, match="active PDK"):
        netlist(Params())


def test_invalid_adc_params_are_refused_when_made():
    """A resolution or an array no converter has, or a converter of another resolution than its
    array's: refused by the parameters' types (a comparator or a sampler of a zero size likewise,
    flow/comp and flow/samp's test_subckt.py)."""
    for make in (
        lambda: Params(adc_bits=0),
        lambda: capdac.Params(bits=7),
        lambda: capdac.Params(bits=15),
        lambda: capdac.Params(extra=-1),
        lambda: capdac.Params(weights=(1,) * 15),
        lambda: Params(adc_bits=10),
    ):
        with pytest.raises(ValidationError):
            make()


@pytest.mark.parametrize(
    "cdac",
    (
        capdac.Params(weights=(768, 512, 320, 192, 128, 64, 64, 64, 64, 64, 32, 16, 8, 4, 2, 1)),
        capdac.Params(weight_impl=capdac.WeightImpl.UNIT_CAPS),
        capdac.Params(coarse_weight=32),
    ),
    ids=("radix20", "unit_caps", "coarse32"),
)
def test_the_netlist_builds_any_array_of_capdacs(tsmc65, cdac):
    """Its DAC's sides are capdac's array of the converter's, whatever its weights and build: an
    array's own weights (the board's radix-2.0 flavor), unit capacitors, another coarse weight."""
    module = netlist(Params(cdac=cdac))
    assert module.xdac_p.of.name == capdac.netlist(cdac).name
    assert module.xdac_p.of.dac_state.width == len(capdac.Model.weights(cdac)) == module.dac_state_p.width


def test_adc_takes_a_sixteen_stage_array_of_another_resolution(tsmc65):
    params = Params(adc_bits=14, cdac=capdac.Params(bits=14, redundancy=capdac.Redundancy.LSB_SPLIT, extra=3))
    assert netlist(params).dac_state_p.width == 16


def _tsmc65_cells() -> bool:
    try:
        return importlib.util.find_spec("pdk.tsmc65.hdl21.cells") is not None
    except ModuleNotFoundError:
        return False


@pytest.mark.skipif(
    shutil.which("yosys") is None or not _tsmc65_cells(), reason="synthesizing the digital block needs yosys and TSMC65"
)
@pytest.mark.parametrize(("bits", "extra"), ((12, 0), (10, 2), (12, 6)))
def test_adc_at_any_stage_count_binds_a_synthesized_digital_block_c0_first(tsmc65, bits, extra):
    """Any array: the digital block synthesized for its stage count, register 0 on C0."""
    stages = bits - 1 + extra
    redundancy = capdac.Redundancy.MSB_REDIST if extra else capdac.Redundancy.BINARY
    module = netlist(Params(adc_bits=bits, cdac=capdac.Params(bits=bits, redundancy=redundancy, extra=extra)))
    assert module.dac_state_p.width == stages
    assert module.xdigital.of.module.name == f"adc_digital_n{stages}"
    for stage in range(stages):
        for port, signal in (("dac_astate_p", module.dac_astate_p), ("dac_state_n_main", module.dac_state_n)):
            connection = module.xdigital.conns[f"{port}[{stage}]"]
            assert connection.index == stage and connection.parent is signal
    assert sum(name.startswith("xdac_") for name in module.instances) == 2


def test_adc_hierarchy_exports_without_duplicate_cell_names(tsmc65):
    """Both sides share one array definition, fresh for each top-level build."""
    module = netlist(Params())
    assert module.xdac_p.of is module.xdac_n.of
    assert module.xdac_p.of is not netlist(Params()).xdac_p.of
    package = h.to_proto(module)
    names = [cell.name for cell in package.modules]
    assert len(names) == len(set(names))


def test_adc_digital_port_order_matches_spice_subckt():
    """Keep the HDL21 declaration positionally identical to the synthesized block."""
    spice = Path(__file__).resolve().parents[2] / "design/spice/adc_digital.sp"
    declaration = next(line for line in spice.read_text().splitlines() if line.startswith(".SUBCKT adc_digital "))
    spice_ports = declaration.split()[2:]

    hdl21_ports = [port.name for port in _digital(16).port_list]

    assert hdl21_ports == spice_ports


@pytest.mark.parametrize("pin", ("seq_typo", "dac_state_p_main[16]", "dac_state_p_main"))
def test_digital_binding_rejects_unknown_pins_and_incompatible_widths(pin):
    module = h.ExternalModule(name="bad_digital", port_list=[h.Inout(name=pin)])
    with pytest.raises((KeyError, ValueError)):
        _digital_aliases(module)


def test_adc_uses_comparator_clock_complement_and_separate_dac_supply(tsmc65):
    """Connect comparator and CDAC power domains without borrowing sampler timing: the DAC's
    sides, their drivers and their capacitors' shields, on the DAC's own supply."""
    module = netlist(Params())

    assert module.xdigital.conns["comp_out"] is module.comp_out
    assert module.xcomp.conns["clkb"] is module.clk_comp_b
    assert module.MP_clk_comp_b.conns["g"] is module.clk_comp
    assert module.MN_clk_comp_b.conns["g"] is module.clk_comp
    for side in ("p", "n"):
        dac = module.instances[f"xdac_{side}"]
        assert dac.conns["vdd"] is module.vdd_dac
        assert dac.conns["vss"] is module.vss_dac


def test_adc_translates_the_legacy_digital_bus_only_at_its_boundary(tsmc65):
    """Connect legacy physical bit 15 to canonical stage C0."""

    module = netlist(Params())

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


def test_each_side_of_the_dac_takes_the_digital_blocks_states_of_its_side(tsmc65):
    """Each side's stages switch on the digital block's states of that side, C0 on its C0; its
    difference states and inversion controls drive nothing (the polarity is wired in)."""
    module = netlist(Params())
    for side in ("p", "n"):
        states = module.namespace[f"dac_state_{side}"]
        assert module.instances[f"xdac_{side}"].conns["dac_state"] is states
        assert _loads(module, states) == {"xdigital", f"xdac_{side}"}
        for stage in range(16):
            connection = module.xdigital.conns[f"dac_state_{side}_main[{15 - stage}]"]
            assert connection.parent is states and connection.index == stage
        for unused in (f"dac_state_{side}_diff", f"dac_invert_{side}_main", f"dac_invert_{side}_diff"):
            assert _loads(module, module.namespace[unused]) == {"xdigital"}
    assert _loads(module, module.dac_diffcaps) == {"xdigital"}


def test_the_comparator_and_samplers_sit_on_their_sides_top_plates(tsmc65):
    """Each side's top plate: its DAC side's, its sampler's output and one comparator input."""
    module = netlist(Params())
    for side, comparator_input in (("p", "inp"), ("n", "inn")):
        top = module.namespace[f"vdac_{side}"]
        assert module.instances[f"xdac_{side}"].conns["vdac"] is top
        assert module.instances[f"xsamp_{side}"].conns["vout"] is top
        assert module.instances[f"xsamp_{side}"].conns["vin"] is module.namespace[f"vin_{side}"]
        assert module.xcomp.conns[comparator_input] is top
        assert _loads(module, top) == {f"xdac_{side}", f"xsamp_{side}", "xcomp"}


@pytest.mark.parametrize("impl", list(capdac.WeightImpl), ids=lambda impl: impl.name.lower())
def test_no_xor_or_capdriver_cell_remains(tsmc65, impl):
    """The DAC is capdac's capacitors and inverter chains alone: no clock XOR, no legacy driver or
    array, in the hierarchy or in its netlist compiled in the PDK."""
    module = netlist(Params(cdac=capdac.Params(weight_impl=impl)))
    names = set()

    def walk(parent: h.Module) -> None:
        for instance in parent.instances.values():
            target = instance.of
            names.add(target.module.name if isinstance(target, h.ExternalModuleCall) else target.name)
            if isinstance(target, h.Module):
                walk(target)

    walk(module)
    h.pdk.compile(module)
    text = io.StringIO()
    h.netlist(module, text, fmt="spectre")
    for name in (*names, text.getvalue()):
        assert not any(cell in name.lower() for cell in ("xor", "capdriver", "caparray")), name


@pytest.mark.parametrize(
    "cdac",
    (
        capdac.Params(),
        capdac.Params(bits=14, redundancy=capdac.Redundancy.LSB_SPLIT, extra=4),
        capdac.Params(weight_impl=capdac.WeightImpl.UNIT_CAPS),
    ),
    ids=("frida1", "14b_lsb_split4_x2", "unit_caps"),
)
def test_every_main_chain_is_non_inverting_and_every_difference_chain_inverting(tsmc65, cdac):
    """The polarity is fixed in each side's drivers: an even count of inverters drives each stage's
    main plates from its state, an odd count its difference plates (difference capacitors alone)."""
    module = netlist(Params(adc_bits=cdac.bits, cdac=cdac))
    for side in ("p", "n"):
        dac = module.instances[f"xdac_{side}"].of
        for stage in range(len(capdac.Model.weights(cdac))):
            main = dac.instances[f"drive_main_{stage}"]
            assert main.conns["A"] == dac.dac_state[stage] and main.conns["Y"] is dac.namespace[f"main_{stage}"]
            assert _inversions(main.of) % 2 == 0
            diff = dac.instances.get(f"drive_diff_{stage}")
            assert (diff is None) == (cdac.weight_impl is capdac.WeightImpl.UNIT_CAPS)
            if diff is not None:
                assert diff.conns["A"] == dac.dac_state[stage] and diff.conns["Y"] is dac.namespace[f"diff_{stage}"]
                assert _inversions(diff.of) % 2 == 1


@pytest.mark.parametrize("impl", list(capdac.WeightImpl), ids=lambda impl: impl.name.lower())
def test_the_bottom_plates_are_the_sides_own(tsmc65, impl):
    """The generated ADC holds no bottom plates of its own: the canonical ones are its sides'
    plates, a unit-capacitor array's main plates alone."""
    unit = impl is capdac.WeightImpl.UNIT_CAPS
    module = netlist(Params(cdac=capdac.Params(weight_impl=impl)))
    aliases = _generated_aliases(module)
    for side in ("p", "n"):
        for kind, suffix in (("main", ""), ("diff", "_diff")):
            assert f"dac_botplate_{side}{suffix}" not in module.namespace
            for stage in range(16):
                plate = None if unit and kind == "diff" else f"xdac_{side}.{kind}_{stage}"
                assert aliases[getattr(Nets, f"dac_botplate_{side}{suffix}")[stage]] == plate


@pytest.mark.parametrize("fabricated", list(Fabricated), ids=lambda member: member.name.lower())
def test_a_fabricated_converter_is_its_extractions_black_box(fabricated):
    """No regenerated FRIDA-1: its netlist is the extraction's cell ``adc_12b_17step`` with the
    tape-out's pins in their order (the fixture header), each bound to its canonical port
    (``_frida1_ports``), nothing inside; it needs no PDK."""
    module = netlist(fabricated.params)
    (box,) = module.instances.values()
    assert box.of.module.name == "adc_12b_17step"
    header = Path(__file__).parent / "fixtures" / "frida1_ports.scs"
    pins = tuple(port.name for port in box.of.module.port_list)
    assert pins == subcircuit_ports(header.read_text(), "adc_12b_17step")
    ports = _frida1_ports()
    assert sorted(pins) == sorted(ports.values())
    for net, pin in ports.items():
        bound = box.conns[pin]
        if isinstance(net, h.Slice):
            assert bound.parent is module.namespace[net.parent.name] and bound.index == net.index
        else:
            assert bound is module.namespace[net.name]
    # the canonical ports it brings out: every one but the DAC states
    assert set(module.ports) == {name for name, net in Nets.signals.items() if net.vis == h.Visibility.PORT} - {
        "dac_state_p",
        "dac_state_n",
    }
    # the same black box for every flavor, one declaration
    assert netlist(Fabricated.FRIDA1_2LAYER_RADIX20.params).instances["xadc"].of.module is box.of.module
