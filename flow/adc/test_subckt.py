"""Software-only tests for the ADC generator. Its DAC's sides are capdac's, resolved to the active
PDK's devices, so a test that builds the ADC binds TSMC65 (``tsmc65``, ``flow/conftest.py``) and a
PDK-free checkout (CI) skips it."""

import io
import random
import re
import shutil
import subprocess
from pathlib import Path

import hdl21 as h
import pytest
from pydantic import ValidationError

from flow import capdac
from flow.circuit.cells import DEFINITIONS, DRIVES, FUNCTIONS, generic_name
from flow.util.netlist import subcircuit_ports

from .params import Fabricated, Params, Presets, Sequencer
from .subckt import Nets, _control, _frida1_ports, _generated_aliases, _nets, _ports, _stage_selector, netlist


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
    pair between the rails on the one before it: an inverter cell of its own, or the chain's own
    pair of transistors (a chain drawn as one cell)."""
    node, count = chain.A, 0
    while node is not chain.Y:
        cells = [instance for instance in chain.instances.values() if instance.conns.get("A") is node]
        if cells:
            (cell,) = cells
            inverter = cell.of
            assert inverter.mn0.conns == {"d": inverter.Y, "g": inverter.A, "s": inverter.VSS, "b": inverter.VSS}
            assert inverter.mp0.conns == {"d": inverter.Y, "g": inverter.A, "s": inverter.VDD, "b": inverter.VDD}
            assert (cell.conns["VDD"], cell.conns["VSS"]) == (chain.VDD, chain.VSS)
            node = cell.conns["Y"]
        else:
            gates = [instance for instance in chain.instances.values() if instance.conns.get("g") is node]
            (mn,) = [m for m in gates if m.conns["s"] is chain.VSS and m.conns["b"] is chain.VSS]
            (mp,) = [m for m in gates if m.conns["s"] is chain.VDD and m.conns["b"] is chain.VDD]
            assert mn.conns["d"] is mp.conns["d"]
            node = mn.conns["d"]
        count += 1
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


def test_adc_hierarchy_exports_without_duplicate_cell_names(tsmc65):
    """Both sides share one array definition, fresh for each top-level build."""
    module = netlist(Params())
    assert module.xdac_p.of is module.xdac_n.of
    assert module.xdac_p.of is not netlist(Params()).xdac_p.of
    package = h.to_proto(module)
    names = [cell.name for cell in package.modules]
    assert len(names) == len(set(names))


def _cells_verilog() -> str:
    """Every generic cell (``flow.circuit.cells``) as a behavioral Verilog module, its ports the
    generic ones in order."""
    modules = []
    for function, (inputs, outputs) in FUNCTIONS.items():
        sequential = function in ("dff", "dffr", "latch")
        if function in DEFINITIONS:
            body = f"  assign Y = {DEFINITIONS[function].replace('!', '~')};"
        else:
            body = {
                "dff": "  always @(posedge CLK) Q <= D;",
                "dffr": "  always @(posedge CLK or negedge RN) if (!RN) Q <= 1'b0; else Q <= D;",
                "latch": "  always_latch if (EN) Q = D;",
                "tiehi": "  assign Y = 1'b1;",
                "tielo": "  assign Y = 1'b0;",
            }[function]
        for drive in DRIVES[function]:
            modules.append(
                "\n".join(
                    (
                        f"module {generic_name(function, drive)} ({', '.join((*inputs, *outputs, 'VDD', 'VSS'))});",
                        *(f"  input {pin};" for pin in inputs),
                        *(f"  output {'reg ' if sequential else ''}{pin};" for pin in outputs),
                        "  inout VDD, VSS;",
                        body,
                        "endmodule",
                    )
                )
            )
    return "\n".join(modules) + "\n"


_LINES = ("seq_init", "seq_samp", "seq_comp", "seq_logic", "en_init", "en_samp_p", "en_samp_n", "en_comp", "en_update")
_PRESETS = ("dac_mode", "dac_astate_p", "dac_bstate_p", "dac_astate_n", "dac_bstate_n")
_CLOCKS = ("clk_samp_p", "clk_samp_p_b", "clk_samp_n", "clk_samp_n_b", "clk_comp")


def _control_alone(param: Params, stages: int) -> h.Module:
    """The converter's control logic alone (``subckt._control``), the nets it reads and drives its
    ports; a shared stage selector (``Sequencer.SHARED``) beside it on the lines themselves."""
    Digital = h.Module(name="AdcDigital")
    ports = _ports(param, _nets(stages))
    for name in (*_LINES, *_PRESETS):
        if name in ports:
            Digital.add(h.Input(width=ports[name].width), name=name)
    Digital.comp_out_p, Digital.comp_out_n = h.Input(), h.Input()
    for name in (*_CLOCKS, "clk_comp_b", "comp_out"):
        Digital.add(h.Output(), name=name)
    Digital.dac_state_p, Digital.dac_state_n = h.Output(width=stages), h.Output(width=stages)
    Digital.vdd_d, Digital.vss_d = h.Inout(), h.Inout()
    if param.sequencer is Sequencer.SHARED:
        Digital.dac_cycle = h.Signal(width=stages)
        Digital.xselector = _stage_selector(stages)(
            clk_init=Digital.seq_init,
            clk_update=Digital.seq_logic,
            dac_cycle=Digital.dac_cycle,
            vdd_d=Digital.vdd_d,
            vss_d=Digital.vss_d,
        )
    _control(Digital, param, stages)
    return Digital


def _equivalence_bench(param: Params, stages: int, conversions: int, seed: int) -> str:
    """A testbench of FRIDA-1's RTL (design/hdl/adc_digital.v) beside the gate-level logic
    (``_control_alone``), both on the same lines: conversions of INIT (eight symbols, a LOGIC pulse
    in them), SAMP (sixteen) and a COMP and a LOGIC pulse for each decision, each conversion's
    enables, mode and preset states drawn at random (the enables of INIT and LOGIC held where the
    stage selector is shared: it runs on the lines themselves), each decision too, the
    comparator's outputs reset high between decisions; both compared twice a symbol."""
    rng = random.Random(seed)
    pins = param.presets is Presets.PINS
    shared = param.sequencer is Sequencer.SHARED
    tied = "".join(str(stage % 2) for stage in reversed(range(stages)))
    rtl_presets = {
        "dac_mode": "dac_mode" if pins else "1'b1",
        "dac_astate_p": "dac_astate_p" if pins else f"{stages}'b{tied}",
        "dac_astate_n": "dac_astate_n" if pins else f"{stages}'b{tied}",
        "dac_bstate_p": "dac_bstate_p",
        "dac_bstate_n": "dac_bstate_n",
    }

    def connect(names: tuple[str, ...], prefix: str = "") -> str:
        return ", ".join(f".{name}({prefix}{name})" for name in names)

    lines = [
        "module tb;",
        f"  reg {', '.join(f'{name} = 0' for name in _LINES)}, dac_mode = 1, comp_out_p = 0, comp_out_n = 1;",
        f"  reg [{stages - 1}:0] dac_astate_p = 0, dac_bstate_p = 0, dac_astate_n = 0, dac_bstate_n = 0;",
        "  supply1 vdd_d;",
        "  supply0 vss_d;",
        f"  wire {', '.join(f'r_{name}, g_{name}' for name in (*_CLOCKS, 'comp_out'))}, g_clk_comp_b;",
        f"  wire [{stages - 1}:0] r_p, r_n, g_p, g_n;",
        f"  adc_digital #(.N_STAGES({stages})) rtl ({connect(_LINES[:3])}, .seq_update(seq_logic),",
        f"    {connect(_LINES[4:])}, .dac_diffcaps(1'b1),",
        "    " + ", ".join(f".{name}({value})" for name, value in rtl_presets.items()) + ",",
        f"    .comp_out_p(comp_out_p), .comp_out_n(comp_out_n), {connect((*_CLOCKS, 'comp_out'), 'r_')},",
        "    .dac_state_p_main(r_p), .dac_state_n_main(r_n), .dac_state_p_diff(), .dac_state_n_diff(),",
        "    .dac_invert_p_main(), .dac_invert_p_diff(), .dac_invert_n_main(), .dac_invert_n_diff());",
        f"  AdcDigital dut ({connect(_LINES)}, {connect(_PRESETS) + ',' if pins else ''}",
        f"    .comp_out_p(comp_out_p), .comp_out_n(comp_out_n), {connect((*_CLOCKS, 'comp_out', 'clk_comp_b'), 'g_')},",
        "    .dac_state_p(g_p), .dac_state_n(g_n), .vdd_d(vdd_d), .vss_d(vss_d));",
        "  integer errors = 0, checks = 0;",
        "  task check; begin",
        "    checks = checks + 1;",
        "    if (" + " || ".join(f"r_{name} !== g_{name}" for name in (*_CLOCKS, "comp_out")),
        "        || g_clk_comp_b !== ~g_clk_comp || r_p !== g_p || r_n !== g_n) errors = errors + 1;",
        "  end endtask",
        "  initial begin",
    ]
    for _ in range(conversions):
        enables = [int(rng.random() < 0.85) for _ in range(5)]
        if shared:
            enables[0] = enables[4] = 1
        lines.append("    " + " ".join(f"{name} = {value};" for name, value in zip(_LINES[4:], enables, strict=True)))
        if pins:
            lines.append(f"    dac_mode = {int(rng.random() < 0.8)};")
            lines += [f"    {name} = {stages}'d{rng.getrandbits(stages)};" for name in _PRESETS[1:]]
        # each symbol: (INIT, SAMP, COMP, LOGIC) and the decision set or reset before it
        symbols = [((0, 0, 0, 0), None)]
        symbols += [((1, 0, 0, int(k in (4, 5))), None) for k in range(8)]
        symbols += [((0, int(k < 14), 0, 0), None) for k in range(16)]
        for _decision in range(stages + 1):
            decision = int(rng.random() < 0.5)
            symbols += [((0, 0, int(k < 4), int(k >= 4)), {1: decision, 5: 2}.get(k)) for k in range(8)]
        for (init, samp, comp_, logic), decided in symbols:
            if decided is not None:
                p, n = (1, 1) if decided == 2 else (decided, 1 - decided)
                lines.append(f"    comp_out_p = {p}; comp_out_n = {n};")
            lines.append(
                f"    seq_init = {init}; seq_samp = {samp}; seq_comp = {comp_}; seq_logic = {logic}; #1 check; #1 check;"
            )
    lines += ['    $display("CHECKS %0d ERRORS %0d", checks, errors);', "    $finish;", "  end", "endmodule"]
    return "\n".join(lines) + "\n"


@pytest.mark.skipif(shutil.which("iverilog") is None, reason="the equivalence check runs Icarus Verilog")
@pytest.mark.parametrize("stages", (16, 9))
@pytest.mark.parametrize(
    "param",
    (Params(), Params(presets=Presets.TIED), Params(sequencer=Sequencer.SHARED)),
    ids=("pins", "tied", "shared"),
)
def test_the_synchronous_logic_is_frida1s_rtl(tmp_path: Path, param: Params, stages: int) -> None:
    """The gate-level synchronous logic (hdl21's Verilog of its generic cells, each a behavioral
    model) does what FRIDA-1's RTL does (design/hdl/adc_digital.v and its modules, with their
    behavioral cells), output for output, twice a symbol over conversions of random enables, modes,
    preset states and decisions; tied presets against the RTL at capdac's A state and the
    comparator's mode; a shared selector beside it on the lines."""
    hdl = Path(__file__).resolve().parents[2] / "design/hdl"
    text = io.StringIO()
    h.netlist(_control_alone(param, stages), text, fmt="verilog")
    files = {"dut.v": text.getvalue(), "cells.v": _cells_verilog(), "tb.v": _equivalence_bench(param, stages, 10, 7)}
    for name, content in files.items():
        (tmp_path / name).write_text(content)
    rtl = [hdl / f"{name}.v" for name in ("cells_behavioral", "clkgate", "sampdriver", "salogic", "adc_digital")]
    subprocess.run(
        ["iverilog", "-g2012", "-o", str(tmp_path / "sim"), *(str(tmp_path / name) for name in files), *map(str, rtl)],
        check=True,
    )
    result = subprocess.run(["vvp", "-n", str(tmp_path / "sim")], check=True, capture_output=True, text=True)
    checks, errors = map(int, re.search(r"CHECKS (\d+) ERRORS (\d+)", result.stdout).groups())
    assert checks == 2 * 10 * (1 + 8 + 16 + 8 * (stages + 1)) and errors == 0


def test_adc_clocks_its_comparator_and_keeps_the_dac_on_its_own_supply(tsmc65):
    """The comparator's clock and its complement from the logic's cells, its output buffered out;
    the DAC's sides, their drivers and their capacitors' shields on the DAC's own supply."""
    module = netlist(Params())
    assert module.xcomp.conns["clk"] is module.clk_comp
    assert module.xcomp.conns["clkb"] is module.clk_comp_b
    assert module.Xcomp_clk_inv.conns["A"] is module.clk_comp
    assert module.Xcomp_clk_inv.conns["Y"] is module.clk_comp_b
    assert module.Xcomp_out_buf.conns["A"] is module.comp_out_p
    assert module.Xcomp_out_buf.conns["Y"] is module.comp_out
    for side in ("p", "n"):
        dac = module.instances[f"xdac_{side}"]
        assert dac.conns["vdd"] is module.vdd_dac
        assert dac.conns["vss"] is module.vss_dac


def test_each_side_of_the_dac_takes_the_logics_states_of_its_side(tsmc65):
    """Each side's stages switch on the SAR logic's states of that side, C0 on its C0; the
    comparator's N output decides the P side (crossed) and its P output the N side."""
    module = netlist(Params())
    assert module.xsalogic.conns["comp_p"] is module.comp_out_n
    assert module.xsalogic.conns["comp_n"] is module.comp_out_p
    for side in ("p", "n"):
        states = module.namespace[f"dac_state_{side}"]
        assert module.instances[f"xdac_{side}"].conns["dac_state"] is states
        assert module.xsalogic.conns[f"dac_state_{side}"] is states
        assert _loads(module, states) == {"xsalogic", f"xdac_{side}"}
    for unused in ("dac_diffcaps", "dac_state_p_diff", "dac_invert_p_main", "dac_cycle"):
        assert unused not in module.namespace


@pytest.mark.parametrize(
    ("param", "absent", "present"),
    (
        (Params(), {"dac_cycle"}, {"dac_mode", "dac_astate_p", "dac_bstate_n"}),
        (Params(presets=Presets.TIED), {"dac_mode", "dac_astate_p", "dac_bstate_n", "dac_cycle"}, set()),
        (Params(sequencer=Sequencer.SHARED), set(), {"dac_cycle", "dac_mode"}),
    ),
    ids=("pins", "tied", "shared"),
)
def test_each_variant_has_its_own_pins(tsmc65, param: Params, absent: set, present: set) -> None:
    """Tied presets take no preset pins; a shared stage selector's lines are the converter's inputs
    and its SAR logic holds no selector; a local one is inside the SAR logic. The logic is generic
    cells alone."""
    module = netlist(param)
    assert not absent & set(module.ports) and present <= set(module.ports)
    logic = module.xsalogic.of
    assert ("xselector" in logic.instances) == (param.sequencer is Sequencer.LOCAL)
    calls = [instance.of for instance in logic.instances.values() if isinstance(instance.of, h.ExternalModuleCall)]
    generic = {generic_name(function, drive) for function in FUNCTIONS for drive in DRIVES[function]}
    assert {call.module.name for call in calls} <= generic


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
    main plates from its state, an odd count its difference plates (difference capacitors alone),
    from the side's own input of the states there, which the converter ties to the same states."""
    module = netlist(Params(adc_bits=cdac.bits, cdac=cdac))
    for side in ("p", "n"):
        instance = module.instances[f"xdac_{side}"]
        dac = instance.of
        if cdac.weight_impl is capdac.WeightImpl.DIFFERENCE_CAPS:
            assert instance.conns["dac_state_diff"] is instance.conns["dac_state"]
        for stage in range(len(capdac.Model.weights(cdac))):
            main = dac.instances[f"drive_main_{stage}"]
            assert main.conns["A"] == dac.dac_state[stage] and main.conns["Y"] is dac.namespace[f"main_{stage}"]
            assert _inversions(main.of) % 2 == 0
            diff = dac.instances.get(f"drive_diff_{stage}")
            assert (diff is None) == (cdac.weight_impl is capdac.WeightImpl.UNIT_CAPS)
            if diff is not None:
                assert diff.conns["A"] == dac.dac_state_diff[stage]
                assert diff.conns["Y"] is dac.namespace[f"diff_{stage}"]
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
    # the canonical ports it brings out: every one but the DAC states and a shared selector's lines
    assert set(module.ports) == {name for name, net in Nets.signals.items() if net.vis == h.Visibility.PORT} - {
        "dac_state_p",
        "dac_state_n",
        "dac_cycle",
    }
    # the same black box for every flavor, one declaration
    assert netlist(Fabricated.FRIDA1_2LAYER_RADIX20.params).instances["xadc"].of.module is box.of.module
