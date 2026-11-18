"""The ADC's circuit: its nets (``Nets``, FRIDA's 16 stages; ``_nets`` at any count) and its
generator (``netlist``): a generated SAR converter, or a fabricated converter's black box.

A generated converter composes:

    netlist(Params(...))
    ├── its control logic's cells (``_control``): the sequencer's lines gated by their enables,
    │   the samplers' clocks, the comparator's clock and its complement, its output buffered
    ├── xsalogic (``_sar_logic``: a flip-flop a stage and side; its stage selector, xselector,
    │   inside it unless shared)
    ├── xdac_p / xdac_n (capdac.netlist: one side of the DAC each, its devices the active PDK's)
    ├── xsamp_p / xsamp_n (samp.netlist)
    └── xcomp (comp.netlist)

A fabricated converter (``Params.fabricated``: FRIDA-1's, ``Fabricated``) is no regenerated
netlist: its ``netlist`` is a black box, the extraction's cell ``adc_12b_17step`` with the
tape-out's positional pins (``fixtures/frida1_ports.scs``) bound to the canonical nets
(``_frida1_ports``), no device inside. Its simulations take an extraction instead (``flow.adc.sim``)
and its area its layout (``flow.adc.layout``).

The control logic is written at gate level here, of generic standard cells
(``flow.circuit.cells``: ``nand2_x1``, ``dff_x1``...) that the PDK's compile pass swaps for its
library's, so that it needs no synthesis, is the same circuit in every PDK and reads as one: hdl21
writes it as SPICE for the simulators and as Verilog for OpenROAD (``flow.adc.layout``), where its
hierarchy is flattened. Its variant is the design's (``Params``): who times a conversion
(``Control``), where the stage selector of a synchronous converter is (``Sequencer``: in it, or
outside, shared by converters in lockstep, its lines then the converter's inputs, ``dac_cycle``)
and whether its DAC states start from pins (``Presets``). The synchronous logic is FRIDA-1's
(``design/hdl/adc_digital.v``), output for output (flow/adc/test_subckt.py checks it against the
RTL): its latch-based clock gates (a latch and an AND), its enabled flip-flops (a multiplexer and a
plain flip-flop), its one-hot selector; its flip-flops of the smallest drive, which capdac's driver
chains are sized from. A net with more loads than a cell drives well is buffered (``_fanout``).

The converter's DAC is capdac's (``capdac.Params``): two of its sides, one module
(``capdac.netlist``) whose requests are resolved to the active PDK's devices, so the generated ADC
needs a PDK. Each side's states are the SAR logic's of that side, its top plate the one that
side's sampler holds and the comparator reads, and its supply the DAC's (``vdd_dac``, ``vss_dac``,
which also shield its capacitors). Its polarity is fixed: each stage's main plates follow its state
and its difference plates the complement (capdac's main chains do not invert, its difference chains
do), so the subtraction is wired in, and the generated converter has no ``dac_diffcaps`` and no
inversion controls: FRIDA-1's extracted view, its lab scans and the behavioral model keep that
other mode, the difference plates switching with the main ones. The bottom plates lie inside the
sides (``_generated_aliases``), and so do the difference states (each side's own input of them).
One side's plates as a behavioral DAC gives them are capdac's (``capdac.Model.plates_f``).

The probes' bindings (``flow.adc.sim`` saves and reads them): the generated converter's bottom
plates inside its DAC's sides (``_generated_aliases``), and FRIDA-1's extraction's positional pins
(``_frida1_ports``, ``_pex``) and RC terminals (``_frida1_terminals``), relative to the ADC
instance; these bindings never rename the IP itself.
"""

import re
from functools import cache
from pathlib import Path

import hdl21 as h

from flow import capdac, comp, samp
from flow.adc.params import Params, Presets, Sequencer
from flow.circuit.cells import cell
from flow.circuit.ports import module_from_ports, port_connections
from flow.layout.devices.device import active_pdk, resolve
from flow.util.netlist import normalize_bus_pin, subcircuit_ports

@cache
def _nets(stages: int):
    """Canonical C0-first nets of an ADC with ``stages`` capacitors a side (one bundle a count, so
    its signals compare equal everywhere). External ports and internal signals stay flat."""

    @h.bundle
    class AdcNets:
        vin_p, vin_n = (h.Input(props=h.Properties(inner={"save": True})) for _ in range(2))
        seq_init, seq_samp, seq_comp, seq_logic = (h.Clock(props=h.Properties(inner={"save": True})) for _ in range(4))
        en_init, en_samp_p, en_samp_n, en_comp, en_update = (h.Input() for _ in range(5))
        dac_mode, dac_diffcaps = h.Input(), h.Input()
        dac_astate_p, dac_bstate_p, dac_astate_n, dac_bstate_n = (h.Input(width=stages) for _ in range(4))
        dac_cycle = h.Input(width=stages)  # the stage selector's lines, where it is shared (Sequencer.SHARED)
        dac_state_p, dac_state_n = (h.Output(width=stages, props=h.Properties(inner={"save": True})) for _ in range(2))
        comp_out = h.Output(props=h.Properties(inner={"save": True}))
        vdd_a = h.Power(direction=h.PortDir.INOUT)
        vss_a = h.Ground(direction=h.PortDir.INOUT)
        vdd_d = h.Power(direction=h.PortDir.INOUT)
        vss_d = h.Ground(direction=h.PortDir.INOUT)
        vdd_dac = h.Power(direction=h.PortDir.INOUT)
        vss_dac = h.Ground(direction=h.PortDir.INOUT)
        clk_samp_p, clk_samp_p_b, clk_samp_n, clk_samp_n_b, clk_comp = (
            h.Signal(usage=h.Usage.CLOCK, props=h.Properties(inner={"save": True})) for _ in range(5)
        )
        clk_comp_b = h.Signal(usage=h.Usage.CLOCK)
        comp_out_p, comp_out_n, vdac_p, vdac_n = (h.Signal(props=h.Properties(inner={"save": True})) for _ in range(4))
        dac_state_p_diff, dac_state_n_diff = (
            h.Signal(width=stages, props=h.Properties(inner={"save": True})) for _ in range(2)
        )
        dac_botplate_p, dac_botplate_n, dac_botplate_p_diff, dac_botplate_n_diff = (
            h.Signal(width=stages, props=h.Properties(inner={"save": True})) for _ in range(4)
        )
        dac_invert_p_main, dac_invert_p_diff, dac_invert_n_main, dac_invert_n_diff = h.Signals(4)

    return AdcNets


# FRIDA's 16 stages: the fabricated converters and their bindings have no other count
Nets = _nets(16)


def _stages(param: Params) -> int:
    """The capacitors a side, each switched by one decision (one more decision resolves the last)."""
    return len(capdac.Model.weights(param.cdac))


# A fresh ADC every call: its DAC's requests are resolved to the active PDK's devices in place.
@h.generator(enable_cache=False)
def netlist(param: Params) -> h.Module:
    """The converter of ``param``: a fabricated one's black box (``_black_box``), or the generated
    SAR converter, digital control with its analog blocks (the DAC's two sides, the samplers, the
    comparator).

    Its stage count follows the array; its control logic is its variant's (``_control``).

    The DAC's two sides are capdac's array, one module (``capdac.netlist``) resolved once to the
    active PDK's devices: ``xdac_p`` switched by the SAR logic's P states (``dac_state_p``) on
    the P top plate, ``xdac_n`` by its N states on the N top plate, both between ``vdd_dac`` and
    ``vss_dac``. Its polarity is fixed, the difference plates switching opposite the main ones (no
    ``dac_diffcaps``, no inversion controls). Each side's sensed main plates (capdac's ``dac_plate``)
    are the ADC's ``dac_plate_p`` and ``dac_plate_n``, which nothing reads yet. The canonical bottom
    plates are the sides' own
    (``_generated_aliases``), not the ADC's nets.
    """
    if param.fabricated is not None:
        return _black_box()
    pdk = active_pdk()
    if pdk is None:
        raise RuntimeError("the ADC's DAC is capdac's, its devices the active PDK's, and none is set")
    stages = _stages(param)
    nets = _nets(stages)
    Adc = module_from_ports("Adc", _ports(param, nets))
    _control(Adc, param, stages)

    # both sides one array, resolved once
    dac = capdac.netlist(param.cdac)
    resolve(dac, pdk)
    sampler = samp.netlist(param.samp)
    for side, vin, top, state, clk, clk_b in (
        ("p", Adc.vin_p, Adc.vdac_p, Adc.dac_state_p, Adc.clk_samp_p, Adc.clk_samp_p_b),
        ("n", Adc.vin_n, Adc.vdac_n, Adc.dac_state_n, Adc.clk_samp_n, Adc.clk_samp_n_b),
    ):
        # a side of difference strips takes its states at its difference drivers too: the same states;
        # its sensed main plates (``dac_plate``, a self-timed control's) on nets of their own, which
        # nothing reads yet
        far = {"dac_state_diff": state} if "dac_state_diff" in dac.ports else {}
        sensed = Adc.add(h.Signal(width=dac.ports["dac_plate"].width), name=f"dac_plate_{side}")
        Adc.add(
            dac(dac_state=state, dac_plate=sensed, vdac=top, vdd=Adc.vdd_dac, vss=Adc.vss_dac, **far),
            name=f"xdac_{side}",
        )
        Adc.add(sampler(vin=vin, vout=top, clk=clk, clk_b=clk_b, vdd=Adc.vdd_a, vss=Adc.vss_a), name=f"xsamp_{side}")

    # Instantiate comparator
    comparator = comp.netlist(param.comp)
    Adc.xcomp = comparator(
        **port_connections(
            comparator.ports,
            Adc,
            inp=Adc.vdac_p,
            inn=Adc.vdac_n,
            outp=Adc.comp_out_p,
            outn=Adc.comp_out_n,
            clk=Adc.clk_comp,
            clkb=Adc.clk_comp_b,
            vdd=Adc.vdd_a,
            vss=Adc.vss_a,
        )
    )

    return Adc


def _generated_aliases(adc: h.Module, nets=Nets) -> dict[h.Signal | h.Slice, str | None]:
    """The generated ADC's (``adc``, a ``netlist``) canonical bottom plates (``nets``'
    ``dac_botplate`` buses, ``_nets`` of its stage count), which lie inside its DAC's sides: each
    side's main and difference plates, capdac's ``main_<stage>`` and ``diff_<stage>``
    (``capdac.netlist``), relative to the ADC instance (``xdac_p.main_0``); None where the side has
    no such plate (unit capacitors have no difference plates)."""
    aliases: dict[h.Signal | h.Slice, str | None] = {}
    for side in ("p", "n"):
        dac = adc.instances[f"xdac_{side}"]
        for kind, bus in (
            ("main", getattr(nets, f"dac_botplate_{side}")),
            ("diff", getattr(nets, f"dac_botplate_{side}_diff")),
        ):
            for stage in range(bus.width):
                plate = f"{kind}_{stage}"
                aliases[bus[stage]] = f"{dac.name}.{plate}" if plate in dac.of.namespace else None
        # its difference states: the side's own input of them, where it has difference plates
        bus = getattr(nets, f"dac_state_{side}_diff")
        diff = "dac_state_diff" in dac.of.ports
        for stage in range(bus.width):
            aliases[bus[stage]] = f"{dac.name}.dac_state_diff_{stage}" if diff else None
    return aliases


# A fabricated converter: its black box, its extraction's pins and its RC terminals


@cache
def _fabricated() -> h.ExternalModule:
    """FRIDA-1's converter as its extraction declares it: the cell ``adc_12b_17step`` with the
    tape-out's positional pins (``fixtures/frida1_ports.scs``), nothing inside."""
    return _pex(Path(__file__).parent / "fixtures" / "frida1_ports.scs", "adc_12b_17step")


def _black_box() -> h.Module:
    """A fabricated converter's ``netlist``: the canonical ports its extraction has (``Nets``' ports
    but the DAC states it does not bring out), each bound to its pin of the extraction's cell
    (``_fabricated``, ``_frida1_ports``)."""
    ports = _frida1_ports()
    selected = {net.parent if isinstance(net, h.Slice) else net for net in ports}
    Adc = module_from_ports("Adc", {name: net for name, net in Nets.signals.items() if net in selected})
    Adc.xadc = _fabricated()()(
        **{
            physical: Adc.namespace[net.parent.name][net.index] if isinstance(net, h.Slice) else Adc.namespace[net.name]
            for net, physical in ports.items()
        }
    )
    return Adc


def _pex(netlist_path: Path, cell: str) -> h.ExternalModule:
    """An extraction's cell ``cell`` of ``netlist_path``, declared from its actual positional
    header."""
    pins = [normalize_bus_pin(pin) for pin in subcircuit_ports(netlist_path.read_text(), cell)]
    if len(pins) != len(set(pins)):
        raise ValueError(f"Duplicate external pins in {cell}")
    return h.ExternalModule(name=cell, port_list=[h.Inout(name=pin) for pin in pins])


def _frida1_ports() -> dict[h.Signal | h.Slice, str]:
    """FRIDA-1's extraction's scalar pins of the canonical ports (``Nets``), C0 first in Python: the
    fabricated macro's buses are C15 first, its LOGIC line ``seq_update``; it brings out no DAC
    state and has no shared stage selector's lines."""
    renamed = {Nets.seq_logic: "seq_update"}
    aliases = {}
    for net in Nets.signals.values():
        if net.vis != h.Visibility.PORT or net in (Nets.dac_state_p, Nets.dac_state_n, Nets.dac_cycle):
            continue
        if net.width == 1:
            aliases[net] = renamed.get(net, net.name)
        else:
            for bit in range(net.width):
                aliases[net[bit]] = f"{net.name}_{net.width - 1 - bit}"
    return aliases


# The control logic: gate level, generic standard cells (``flow.circuit.cells``) that the PDK's
# compile pass swaps for its library's, every cell on the digital supply


def _ports(param: Params, nets=Nets) -> dict[str, h.Signal]:
    """The generated converter's own nets (``nets``: ``_nets`` of its stage count): its ports, its
    variant's (``Presets.TIED`` has no preset pins, ``Sequencer.SHARED`` takes the stage selector's
    lines), and the inner nets it holds itself; not its bottom plates (its DAC's sides'), the
    difference states (its sides' own inputs of the states) or FRIDA-1's inversion controls and
    ``dac_diffcaps`` (its polarity is fixed)."""
    skip = {
        nets.dac_botplate_p,
        nets.dac_botplate_n,
        nets.dac_botplate_p_diff,
        nets.dac_botplate_n_diff,
        nets.dac_state_p_diff,
        nets.dac_state_n_diff,
        nets.dac_invert_p_main,
        nets.dac_invert_p_diff,
        nets.dac_invert_n_main,
        nets.dac_invert_n_diff,
        nets.dac_diffcaps,
    }
    if param.presets is Presets.TIED:
        skip |= {nets.dac_astate_p, nets.dac_bstate_p, nets.dac_astate_n, nets.dac_bstate_n, nets.dac_mode}
    if param.sequencer is Sequencer.LOCAL:
        skip.add(nets.dac_cycle)
    return {name: net for name, net in nets.signals.items() if net not in skip}


def _cell(module: h.Module, name: str, function: str, drive: int = 1, **pins: h.Signal | h.Slice) -> None:
    """The generic cell ``function`` of ``drive`` in ``module``, as ``name``, on its digital supply."""
    module.add(cell(function, drive)(**pins, VDD=module.vdd_d, VSS=module.vss_d), name=name)


def _net(module: h.Module, name: str) -> h.Signal:
    return module.add(h.Signal(), name=name)


def _fanout(module: h.Module, name: str, source: h.Signal | h.Slice, loads: int, group: int = 8) -> list:
    """The net each of ``loads`` loads of ``source`` takes: ``source`` itself where ``group`` loads
    or fewer share it, else a buffer (x4) for each ``group`` of them, the loads in order."""
    if loads <= group:
        return [source] * loads
    nets = []
    for k in range(-(-loads // group)):
        branch = _net(module, f"{name}_b{k}")
        _cell(module, f"X{name}_b{k}", "buf", 4, A=source, Y=branch)
        nets += [branch] * min(group, loads - k * group)
    return nets


def _clock_gate(module: h.Module, name: str, clock, enable, gated) -> None:
    """A latch-based clock gate: the enable latched while the clock is low, ANDed with the clock,
    so that a change of the enable never cuts or makes a pulse."""
    low, held = _net(module, f"{name}_ck_b"), _net(module, f"{name}_en_q")
    _cell(module, f"X{name}_inv", "inv", 1, A=clock, Y=low)
    _cell(module, f"X{name}_latch", "latch", 1, D=enable, EN=low, Q=held)
    _cell(module, f"X{name}_and", "and2", 2, A=clock, B=held, Y=gated)


def _stage_selector(stages: int) -> h.Module:
    """The synchronous stage selector, a one-hot shift register: the first stage's flip-flop set and
    the others cleared at a LOGIC edge while INIT is high, the one stage shifted on at each other
    LOGIC edge, so that stage ``k`` is selected at the ``k``-th edge after INIT. In the converter
    (``Sequencer.LOCAL``) on its gated lines; outside it (``Sequencer.SHARED``), one for every
    converter on the same lines, on the lines themselves."""
    Selector = h.Module(name="StageSelector")
    Selector.clk_init, Selector.clk_update = h.Input(), h.Input(usage=h.Usage.CLOCK)
    Selector.dac_cycle = h.Output(width=stages)
    Selector.vdd_d = h.Power(direction=h.PortDir.INOUT)
    Selector.vss_d = h.Ground(direction=h.PortDir.INOUT)
    first_b = _net(Selector, "init_b")
    _cell(Selector, "Xinit_inv", "inv", 2, A=Selector.clk_init, Y=first_b)
    clocks = _fanout(Selector, "clk", Selector.clk_update, stages)
    cleared = _fanout(Selector, "init_b", first_b, stages - 1)
    for stage in range(stages):
        if stage == 0:
            data = Selector.clk_init
        else:
            data = _net(Selector, f"next_{stage}")
            _cell(Selector, f"Xnext_{stage}", "and2", 1, A=cleared[stage - 1], B=Selector.dac_cycle[stage - 1], Y=data)
        _cell(Selector, f"Xcycle_{stage}", "dff", 1, D=data, CLK=clocks[stage], Q=Selector.dac_cycle[stage])
    return Selector


def _sar_logic(param: Params, stages: int) -> h.Module:
    """The synchronous SAR logic (``Control.SYNC``): a flip-flop a stage and side holding its DAC
    state, loaded at each LOGIC edge (``clk_update``) where its stage is enabled, with the stage's
    A state while INIT is high (``clk_init``: every stage enabled), else with the comparator's
    decision (``comp_p`` for the P side: its N output, crossed) in the stage the selector selects,
    or (``dac_mode`` low, every stage enabled) with its B state. FRIDA-1's ``salogic.v``, its
    enabled flip-flops each a multiplexer before a plain one. With ``Presets.TIED`` the A state is
    capdac's (alternating from 0), tied in each stage's gates, and there is no B state."""
    pins = param.presets is Presets.PINS
    Logic = h.Module(name="SarLogic")
    Logic.clk_init, Logic.clk_update = h.Input(), h.Input(usage=h.Usage.CLOCK)
    Logic.comp_p, Logic.comp_n = h.Input(), h.Input()
    if pins:
        Logic.dac_mode = h.Input()
        for name in ("dac_astate_p", "dac_bstate_p", "dac_astate_n", "dac_bstate_n"):
            Logic.add(h.Input(width=stages), name=name)
    Logic.dac_state_p, Logic.dac_state_n = h.Output(width=stages), h.Output(width=stages)
    Logic.vdd_d = h.Power(direction=h.PortDir.INOUT)
    Logic.vss_d = h.Ground(direction=h.PortDir.INOUT)
    if param.sequencer is Sequencer.SHARED:
        Logic.dac_cycle = h.Input(width=stages)
        cycle = Logic.dac_cycle
    else:
        cycle = Logic.add(h.Signal(width=stages), name="dac_cycle")
        Logic.xselector = _stage_selector(stages)(
            clk_init=Logic.clk_init,
            clk_update=Logic.clk_update,
            dac_cycle=cycle,
            vdd_d=Logic.vdd_d,
            vss_d=Logic.vss_d,
        )

    init_b = _net(Logic, "init_b")
    _cell(Logic, "Xinit_inv", "inv", 2, A=Logic.clk_init, Y=init_b)
    per_stage = 3 if pins else 1  # the nets of a stage clk_init feeds: two multiplexers and the enable
    init = _fanout(Logic, "init", Logic.clk_init, per_stage * stages)
    clocks = _fanout(Logic, "clk", Logic.clk_update, 2 * stages)
    comps = {side: _fanout(Logic, f"comp_{side}", getattr(Logic, f"comp_{side}"), stages) for side in "pn"}
    if pins:
        mode_b = _net(Logic, "mode_b")
        _cell(Logic, "Xmode_inv", "inv", 1, A=Logic.dac_mode, Y=mode_b)
        modes = _fanout(Logic, "mode", Logic.dac_mode, 2 * stages)
        modes_b = _fanout(Logic, "mode_b", mode_b, stages)
    else:
        cleared = _fanout(Logic, "init_b", init_b, stages)
    for stage in range(stages):
        enable = _net(Logic, f"en_{stage}")
        if pins:
            # every stage while INIT is high or the B state is chosen, else the selected one
            _cell(Logic, f"Xen_{stage}", "or3", 1, A=init[per_stage * stage], B=modes_b[stage], C=cycle[stage], Y=enable)
        else:
            _cell(Logic, f"Xen_{stage}", "or2", 1, A=init[per_stage * stage], B=cycle[stage], Y=enable)
        for k, side in enumerate("pn"):
            state = getattr(Logic, f"dac_state_{side}")[stage]
            comp_ = comps[side][stage]
            data = _net(Logic, f"d_{side}_{stage}")
            if pins:
                decided = _net(Logic, f"m_{side}_{stage}")
                _cell(
                    Logic,
                    f"Xmode_{side}_{stage}",
                    "mux2",
                    1,
                    A=getattr(Logic, f"dac_bstate_{side}")[stage],
                    B=comp_,
                    S=modes[2 * stage + k],
                    Y=decided,
                )
                _cell(
                    Logic,
                    f"Xpreset_{side}_{stage}",
                    "mux2",
                    1,
                    A=decided,
                    B=getattr(Logic, f"dac_astate_{side}")[stage],
                    S=init[per_stage * stage + 1 + k],
                    Y=data,
                )
            elif stage % 2:  # capdac's A state 1: the decision, or 1 while INIT is high
                _cell(Logic, f"Xpreset_{side}_{stage}", "or2", 1, A=init[stage], B=comp_, Y=data)
            else:  # A state 0: the decision, or 0 while INIT is high
                _cell(Logic, f"Xpreset_{side}_{stage}", "and2", 1, A=cleared[stage], B=comp_, Y=data)
            loaded = _net(Logic, f"q_{side}_{stage}")
            _cell(Logic, f"Xhold_{side}_{stage}", "mux2", 1, A=state, B=data, S=enable, Y=loaded)
            _cell(Logic, f"Xstate_{side}_{stage}", "dff", 1, D=loaded, CLK=clocks[2 * stage + k], Q=state)
    return Logic


def _control(Adc: h.Module, param: Params, stages: int) -> None:
    """The converter's control logic into ``Adc`` (its variant's, ``Params.control``): the
    sequencer's lines gated by their enables (``_clock_gate``), the samplers' clocks and their
    complements, the comparator's clock and its complement, the comparator's output buffered out,
    and the SAR logic (``xsalogic``: ``_sar_logic``). Every cell on the digital supply."""
    raw = {line: _net(Adc, f"clk_{line}_g") for line in ("samp_p", "samp_n", "comp")}
    clk_init, clk_update = _net(Adc, "clk_init"), _net(Adc, "clk_update")
    for name, line, enable, gated in (
        ("gate_init", Adc.seq_init, Adc.en_init, clk_init),
        ("gate_samp_p", Adc.seq_samp, Adc.en_samp_p, raw["samp_p"]),
        ("gate_samp_n", Adc.seq_samp, Adc.en_samp_n, raw["samp_n"]),
        ("gate_comp", Adc.seq_comp, Adc.en_comp, raw["comp"]),
        ("gate_update", Adc.seq_logic, Adc.en_update, clk_update),
    ):
        _clock_gate(Adc, name, line, enable, gated)
    for side in "pn":
        _cell(Adc, f"Xsamp_{side}_buf", "buf", 4, A=raw[f"samp_{side}"], Y=getattr(Adc, f"clk_samp_{side}"))
        _cell(Adc, f"Xsamp_{side}_inv", "inv", 4, A=raw[f"samp_{side}"], Y=getattr(Adc, f"clk_samp_{side}_b"))
    _cell(Adc, "Xcomp_clk_buf", "buf", 4, A=raw["comp"], Y=Adc.clk_comp)
    _cell(Adc, "Xcomp_clk_inv", "inv", 4, A=Adc.clk_comp, Y=Adc.clk_comp_b)
    _cell(Adc, "Xcomp_out_buf", "buf", 2, A=Adc.comp_out_p, Y=Adc.comp_out)
    logic = _sar_logic(param, stages)
    connections = {
        name: getattr(Adc, name)
        for name in ("dac_mode", "dac_astate_p", "dac_bstate_p", "dac_astate_n", "dac_bstate_n", "dac_cycle")
        if name in logic.ports
    }
    Adc.xsalogic = logic(
        clk_init=clk_init,
        clk_update=clk_update,
        comp_p=Adc.comp_out_n,
        comp_n=Adc.comp_out_p,
        dac_state_p=Adc.dac_state_p,
        dac_state_n=Adc.dac_state_n,
        vdd_d=Adc.vdd_d,
        vss_d=Adc.vss_d,
        **connections,
    )


def _frida1_terminals() -> dict[h.Signal | h.Slice, str]:
    """FRIDA-1's extraction's RC terminals of the canonical observations (``Nets``' and the
    comparator's, ``comp.Nets``): the device terminal each net is read at, relative to the ADC
    instance. The fabricated bus is C15 first."""
    return {
        Nets.vdac_p: "N_VDAC_P_XXsampswitch_p/MM0_d",
        Nets.vdac_n: "N_VDAC_N_XXsampswitch_n/MM0_d",
        Nets.clk_samp_p: "N_CLK_SAMP_P_XXsampswitch_p/MM0_g",
        Nets.clk_samp_p_b: "N_CLK_SAMP_P_B_XXsampswitch_p/MM1_g",
        Nets.clk_samp_n: "N_CLK_SAMP_N_XXsampswitch_n/MM0_g",
        Nets.clk_samp_n_b: "N_CLK_SAMP_N_B_XXsampswitch_n/MM1_g",
        Nets.clk_comp: "N_CLK_COMP_XXcomp/XXLATCH/MMM0_g",
        Nets.comp_out_p: "N_COMP_OUT_P_XXcomp/XXI3/XXI46/MM_u2_1_d",
        Nets.comp_out_n: "N_COMP_OUT_N_XXcomp/XXI3/XXI47/MM_u2_1_d",
        comp.Nets.latch_p: "N_XXCOMP/COMP_P_XXcomp/XXLATCH/MMM4_d",
        comp.Nets.latch_n: "N_XXCOMP/COMP_N_XXcomp/XXLATCH/MMM3_d",
        comp.Nets.input_p_drain: "N_XXCOMP/XXLATCH/NET031_XXcomp/XXLATCH/MMM1_d",
        comp.Nets.input_n_drain: "N_XXCOMP/XXLATCH/NET037_XXcomp/XXLATCH/MMM2_d",
        Nets.dac_state_p[0]: "N_DAC_STATE_P_MAIN<15>_XXcapdriver_p_main/XXxor15_0/MMM_u2_1-M_u3_g",
        Nets.dac_botplate_p[0]: "N_DAC_DRIVE_BOTPLATE_MAIN_P<15>_XXcapdriver_p_main/XXxor15_0/MMM_u4_1-M_u3_d",
        Nets.dac_state_p_diff[0]: "N_DAC_STATE_P_DIFF<15>_XXcapdriver_p_diff/XXxor15_0/MMM_u2_1-M_u3_g",
        Nets.dac_botplate_p_diff[0]: "N_DAC_DRIVE_BOTPLATE_DIFF_P<15>_XXcapdriver_p_diff/XXxor15_0/MMM_u4_1-M_u3_d",
        Nets.dac_state_n[0]: "N_DAC_STATE_N_MAIN<15>_XXcapdriver_n_main/XXxor15_0/MMM_u2_1-M_u3_g",
        Nets.dac_botplate_n[0]: "N_DAC_DRIVE_BOTPLATE_MAIN_N<15>_XXcapdriver_n_main/XXxor15_0/MMM_u4_1-M_u3_d",
        Nets.dac_state_n_diff[0]: "N_DAC_STATE_N_DIFF<15>_XXcapdriver_n_diff/XXxor15_0/MMM_u2_1-M_u3_g",
        Nets.dac_botplate_n_diff[0]: "N_DAC_DRIVE_BOTPLATE_DIFF_N<15>_XXcapdriver_n_diff/XXxor15_0/MMM_u4_1-M_u3_d",
        Nets.dac_state_p[1]: "N_DAC_STATE_P_MAIN<14>_XXcapdriver_p_main/XXxor14_0/MMM_u2_1-M_u3_g",
        Nets.dac_botplate_p[1]: "N_DAC_DRIVE_BOTPLATE_MAIN_P<14>_XXcapdriver_p_main/XXxor14_0/MMM_u4_1-M_u3_d",
        Nets.dac_state_p_diff[1]: "N_DAC_STATE_P_DIFF<14>_XXcapdriver_p_diff/XXxor14_0/MMM_u2_1-M_u3_g",
        Nets.dac_botplate_p_diff[1]: "N_DAC_DRIVE_BOTPLATE_DIFF_P<14>_XXcapdriver_p_diff/XXxor14_0/MMM_u4_1-M_u3_d",
        Nets.dac_state_n[1]: "N_DAC_STATE_N_MAIN<14>_XXcapdriver_n_main/XXxor14_0/MMM_u2_1-M_u3_g",
        Nets.dac_botplate_n[1]: "N_DAC_DRIVE_BOTPLATE_MAIN_N<14>_XXcapdriver_n_main/XXxor14_0/MMM_u4_1-M_u3_d",
        Nets.dac_state_n_diff[1]: "N_DAC_STATE_N_DIFF<14>_XXcapdriver_n_diff/XXxor14_0/MMM_u2_1-M_u3_g",
        Nets.dac_botplate_n_diff[1]: "N_DAC_DRIVE_BOTPLATE_DIFF_N<14>_XXcapdriver_n_diff/XXxor14_0/MMM_u4_1-M_u3_d",
        Nets.dac_state_p[2]: "N_DAC_STATE_P_MAIN<13>_XXcapdriver_p_main/XXxor13/MMM_u2_1-M_u3_g",
        Nets.dac_botplate_p[2]: "N_DAC_DRIVE_BOTPLATE_MAIN_P<13>_XXcapdriver_p_main/XXxor13/MMM_u4_1-M_u3_d",
        Nets.dac_state_p_diff[2]: "N_DAC_STATE_P_DIFF<13>_XXcapdriver_p_diff/XXxor13/MMM_u2_1-M_u3_g",
        Nets.dac_botplate_p_diff[2]: "N_DAC_DRIVE_BOTPLATE_DIFF_P<13>_XXcapdriver_p_diff/XXxor13/MMM_u4_1-M_u3_d",
        Nets.dac_state_n[2]: "N_DAC_STATE_N_MAIN<13>_XXcapdriver_n_main/XXxor13/MMM_u2_1-M_u3_g",
        Nets.dac_botplate_n[2]: "N_DAC_DRIVE_BOTPLATE_MAIN_N<13>_XXcapdriver_n_main/XXxor13/MMM_u4_1-M_u3_d",
        Nets.dac_state_n_diff[2]: "N_DAC_STATE_N_DIFF<13>_XXcapdriver_n_diff/XXxor13/MMM_u2_1-M_u3_g",
        Nets.dac_botplate_n_diff[2]: "N_DAC_DRIVE_BOTPLATE_DIFF_N<13>_XXcapdriver_n_diff/XXxor13/MMM_u4_1-M_u3_d",
        Nets.dac_state_p[3]: "N_DAC_STATE_P_MAIN<12>_XXcapdriver_p_main/XXxor12/MMM_u2_1-M_u3_g",
        Nets.dac_botplate_p[3]: "N_DAC_DRIVE_BOTPLATE_MAIN_P<12>_XXcapdriver_p_main/XXxor12/MMM_u4_1-M_u3_d",
        Nets.dac_state_p_diff[3]: "N_DAC_STATE_P_DIFF<12>_XXcapdriver_p_diff/XXxor12/MMM_u2_1-M_u3_g",
        Nets.dac_botplate_p_diff[3]: "N_DAC_DRIVE_BOTPLATE_DIFF_P<12>_XXcapdriver_p_diff/XXxor12/MMM_u4_1-M_u3_d",
        Nets.dac_state_n[3]: "N_DAC_STATE_N_MAIN<12>_XXcapdriver_n_main/XXxor12/MMM_u2_1-M_u3_g",
        Nets.dac_botplate_n[3]: "N_DAC_DRIVE_BOTPLATE_MAIN_N<12>_XXcapdriver_n_main/XXxor12/MMM_u4_1-M_u3_d",
        Nets.dac_state_n_diff[3]: "N_DAC_STATE_N_DIFF<12>_XXcapdriver_n_diff/XXxor12/MMM_u2_1-M_u3_g",
        Nets.dac_botplate_n_diff[3]: "N_DAC_DRIVE_BOTPLATE_DIFF_N<12>_XXcapdriver_n_diff/XXxor12/MMM_u4_1-M_u3_d",
        Nets.dac_state_p[4]: "N_DAC_STATE_P_MAIN<11>_XXcapdriver_p_main/XXxor11/MMM_u2-M_u3_g",
        Nets.dac_botplate_p[4]: "N_DAC_DRIVE_BOTPLATE_MAIN_P<11>_XXcapdriver_p_main/XXxor11/MMM_u4_1-M_u3_d",
        Nets.dac_state_p_diff[4]: "N_DAC_STATE_P_DIFF<11>_XXcapdriver_p_diff/XXxor11/MMM_u2-M_u3_g",
        Nets.dac_botplate_p_diff[4]: "N_DAC_DRIVE_BOTPLATE_DIFF_P<11>_XXcapdriver_p_diff/XXxor11/MMM_u4_1-M_u3_d",
        Nets.dac_state_n[4]: "N_DAC_STATE_N_MAIN<11>_XXcapdriver_n_main/XXxor11/MMM_u2-M_u3_g",
        Nets.dac_botplate_n[4]: "N_DAC_DRIVE_BOTPLATE_MAIN_N<11>_XXcapdriver_n_main/XXxor11/MMM_u4_1-M_u3_d",
        Nets.dac_state_n_diff[4]: "N_DAC_STATE_N_DIFF<11>_XXcapdriver_n_diff/XXxor11/MMM_u2-M_u3_g",
        Nets.dac_botplate_n_diff[4]: "N_DAC_DRIVE_BOTPLATE_DIFF_N<11>_XXcapdriver_n_diff/XXxor11/MMM_u4_1-M_u3_d",
        Nets.dac_state_p[5]: "N_DAC_STATE_P_MAIN<10>_XXcapdriver_p_main/XXxor10/MMM_u2-M_u3_g",
        Nets.dac_botplate_p[5]: "N_DAC_DRIVE_BOTPLATE_MAIN_P<10>_XXcapdriver_p_main/XXxor10/MMM_u4_1-M_u3_d",
        Nets.dac_state_p_diff[5]: "N_DAC_STATE_P_DIFF<10>_XXcapdriver_p_diff/XXxor10/MMM_u2-M_u3_g",
        Nets.dac_botplate_p_diff[5]: "N_DAC_DRIVE_BOTPLATE_DIFF_P<10>_XXcapdriver_p_diff/XXxor10/MMM_u4_1-M_u3_d",
        Nets.dac_state_n[5]: "N_DAC_STATE_N_MAIN<10>_XXcapdriver_n_main/XXxor10/MMM_u2-M_u3_g",
        Nets.dac_botplate_n[5]: "N_DAC_DRIVE_BOTPLATE_MAIN_N<10>_XXcapdriver_n_main/XXxor10/MMM_u4_1-M_u3_d",
        Nets.dac_state_n_diff[5]: "N_DAC_STATE_N_DIFF<10>_XXcapdriver_n_diff/XXxor10/MMM_u2-M_u3_g",
        Nets.dac_botplate_n_diff[5]: "N_DAC_DRIVE_BOTPLATE_DIFF_N<10>_XXcapdriver_n_diff/XXxor10/MMM_u4_1-M_u3_d",
        Nets.dac_state_p[6]: "N_DAC_STATE_P_MAIN<9>_XXcapdriver_p_main/XXxor9/MMM_u2-M_u3_g",
        Nets.dac_botplate_p[6]: "N_DAC_DRIVE_BOTPLATE_MAIN_P<9>_XXcapdriver_p_main/XXxor9/MMM_u4_1-M_u3_d",
        Nets.dac_state_p_diff[6]: "N_DAC_STATE_P_DIFF<9>_XXcapdriver_p_diff/XXxor9/MMM_u2-M_u3_g",
        Nets.dac_botplate_p_diff[6]: "N_DAC_DRIVE_BOTPLATE_DIFF_P<9>_XXcapdriver_p_diff/XXxor9/MMM_u4_1-M_u3_d",
        Nets.dac_state_n[6]: "N_DAC_STATE_N_MAIN<9>_XXcapdriver_n_main/XXxor9/MMM_u2-M_u3_g",
        Nets.dac_botplate_n[6]: "N_DAC_DRIVE_BOTPLATE_MAIN_N<9>_XXcapdriver_n_main/XXxor9/MMM_u4_1-M_u3_d",
        Nets.dac_state_n_diff[6]: "N_DAC_STATE_N_DIFF<9>_XXcapdriver_n_diff/XXxor9/MMM_u2-M_u3_g",
        Nets.dac_botplate_n_diff[6]: "N_DAC_DRIVE_BOTPLATE_DIFF_N<9>_XXcapdriver_n_diff/XXxor9/MMM_u4_1-M_u3_d",
        Nets.dac_state_p[7]: "N_DAC_STATE_P_MAIN<8>_XXcapdriver_p_main/XXxor8/MMM_u2-M_u3_g",
        Nets.dac_botplate_p[7]: "N_DAC_DRIVE_BOTPLATE_MAIN_P<8>_XXcapdriver_p_main/XXxor8/MMM_u4_1-M_u3_d",
        Nets.dac_state_p_diff[7]: "N_DAC_STATE_P_DIFF<8>_XXcapdriver_p_diff/XXxor8/MMM_u2-M_u3_g",
        Nets.dac_botplate_p_diff[7]: "N_DAC_DRIVE_BOTPLATE_DIFF_P<8>_XXcapdriver_p_diff/XXxor8/MMM_u4_1-M_u3_d",
        Nets.dac_state_n[7]: "N_DAC_STATE_N_MAIN<8>_XXcapdriver_n_main/XXxor8/MMM_u2-M_u3_g",
        Nets.dac_botplate_n[7]: "N_DAC_DRIVE_BOTPLATE_MAIN_N<8>_XXcapdriver_n_main/XXxor8/MMM_u4_1-M_u3_d",
        Nets.dac_state_n_diff[7]: "N_DAC_STATE_N_DIFF<8>_XXcapdriver_n_diff/XXxor8/MMM_u2-M_u3_g",
        Nets.dac_botplate_n_diff[7]: "N_DAC_DRIVE_BOTPLATE_DIFF_N<8>_XXcapdriver_n_diff/XXxor8/MMM_u4_1-M_u3_d",
        Nets.dac_state_p[8]: "N_DAC_STATE_P_MAIN<7>_XXcapdriver_p_main/XXxor7/MMM_u2-M_u3_g",
        Nets.dac_botplate_p[8]: "N_DAC_DRIVE_BOTPLATE_MAIN_P<7>_XXcapdriver_p_main/XXxor7/MMM_u4_1-M_u3_d",
        Nets.dac_state_p_diff[8]: "N_DAC_STATE_P_DIFF<7>_XXcapdriver_p_diff/XXxor7/MMM_u2-M_u3_g",
        Nets.dac_botplate_p_diff[8]: "N_DAC_DRIVE_BOTPLATE_DIFF_P<7>_XXcapdriver_p_diff/XXxor7/MMM_u4_1-M_u3_d",
        Nets.dac_state_n[8]: "N_DAC_STATE_N_MAIN<7>_XXcapdriver_n_main/XXxor7/MMM_u2-M_u3_g",
        Nets.dac_botplate_n[8]: "N_DAC_DRIVE_BOTPLATE_MAIN_N<7>_XXcapdriver_n_main/XXxor7/MMM_u4_1-M_u3_d",
        Nets.dac_state_n_diff[8]: "N_DAC_STATE_N_DIFF<7>_XXcapdriver_n_diff/XXxor7/MMM_u2-M_u3_g",
        Nets.dac_botplate_n_diff[8]: "N_DAC_DRIVE_BOTPLATE_DIFF_N<7>_XXcapdriver_n_diff/XXxor7/MMM_u4_1-M_u3_d",
        Nets.dac_state_p[9]: "N_DAC_STATE_P_MAIN<6>_XXcapdriver_p_main/XXxor6/MMM_u2-M_u3_g",
        Nets.dac_botplate_p[9]: "N_DAC_DRIVE_BOTPLATE_MAIN_P<6>_XXcapdriver_p_main/XXxor6/MMM_u4_1-M_u3_d",
        Nets.dac_state_p_diff[9]: "N_DAC_STATE_P_DIFF<6>_XXcapdriver_p_diff/XXxor6/MMM_u2-M_u3_g",
        Nets.dac_botplate_p_diff[9]: "N_DAC_DRIVE_BOTPLATE_DIFF_P<6>_XXcapdriver_p_diff/XXxor6/MMM_u4_1-M_u3_d",
        Nets.dac_state_n[9]: "N_DAC_STATE_N_MAIN<6>_XXcapdriver_n_main/XXxor6/MMM_u2-M_u3_g",
        Nets.dac_botplate_n[9]: "N_DAC_DRIVE_BOTPLATE_MAIN_N<6>_XXcapdriver_n_main/XXxor6/MMM_u4_1-M_u3_d",
        Nets.dac_state_n_diff[9]: "N_DAC_STATE_N_DIFF<6>_XXcapdriver_n_diff/XXxor6/MMM_u2-M_u3_g",
        Nets.dac_botplate_n_diff[9]: "N_DAC_DRIVE_BOTPLATE_DIFF_N<6>_XXcapdriver_n_diff/XXxor6/MMM_u4_1-M_u3_d",
        Nets.dac_state_p[10]: "N_DAC_STATE_P_MAIN<5>_XXcapdriver_p_main/XXxor5/MMM_u2-M_u3_g",
        Nets.dac_botplate_p[10]: "N_DAC_DRIVE_BOTPLATE_MAIN_P<5>_XXcapdriver_p_main/XXxor5/MMM_u4_1-M_u3_d",
        Nets.dac_state_p_diff[10]: "N_DAC_STATE_P_DIFF<5>_XXcapdriver_p_diff/XXxor5/MMM_u2-M_u3_g",
        Nets.dac_botplate_p_diff[10]: "N_DAC_DRIVE_BOTPLATE_DIFF_P<5>_XXcapdriver_p_diff/XXxor5/MMM_u4_1-M_u3_d",
        Nets.dac_state_n[10]: "N_DAC_STATE_N_MAIN<5>_XXcapdriver_n_main/XXxor5/MMM_u2-M_u3_g",
        Nets.dac_botplate_n[10]: "N_DAC_DRIVE_BOTPLATE_MAIN_N<5>_XXcapdriver_n_main/XXxor5/MMM_u4_1-M_u3_d",
        Nets.dac_state_n_diff[10]: "N_DAC_STATE_N_DIFF<5>_XXcapdriver_n_diff/XXxor5/MMM_u2-M_u3_g",
        Nets.dac_botplate_n_diff[10]: "N_DAC_DRIVE_BOTPLATE_DIFF_N<5>_XXcapdriver_n_diff/XXxor5/MMM_u4_1-M_u3_d",
        Nets.dac_state_p[11]: "N_DAC_STATE_P_MAIN<4>_XXcapdriver_p_main/XXxor4/MMM_u2-M_u3_g",
        Nets.dac_botplate_p[11]: "N_DAC_DRIVE_BOTPLATE_MAIN_P<4>_XXcapdriver_p_main/XXxor4/MMM_u4_1-M_u3_d",
        Nets.dac_state_p_diff[11]: "N_DAC_STATE_P_DIFF<4>_XXcapdriver_p_diff/XXxor4/MMM_u2-M_u3_g",
        Nets.dac_botplate_p_diff[11]: "N_DAC_DRIVE_BOTPLATE_DIFF_P<4>_XXcapdriver_p_diff/XXxor4/MMM_u4_1-M_u3_d",
        Nets.dac_state_n[11]: "N_DAC_STATE_N_MAIN<4>_XXcapdriver_n_main/XXxor4/MMM_u2-M_u3_g",
        Nets.dac_botplate_n[11]: "N_DAC_DRIVE_BOTPLATE_MAIN_N<4>_XXcapdriver_n_main/XXxor4/MMM_u4_1-M_u3_d",
        Nets.dac_state_n_diff[11]: "N_DAC_STATE_N_DIFF<4>_XXcapdriver_n_diff/XXxor4/MMM_u2-M_u3_g",
        Nets.dac_botplate_n_diff[11]: "N_DAC_DRIVE_BOTPLATE_DIFF_N<4>_XXcapdriver_n_diff/XXxor4/MMM_u4_1-M_u3_d",
        Nets.dac_state_p[12]: "N_DAC_STATE_P_MAIN<3>_XXcapdriver_p_main/XXxor3/MMM_u2-M_u3_g",
        Nets.dac_botplate_p[12]: "N_DAC_DRIVE_BOTPLATE_MAIN_P<3>_XXcapdriver_p_main/XXxor3/MMM_u4_1-M_u3_d",
        Nets.dac_state_p_diff[12]: "N_DAC_STATE_P_DIFF<3>_XXcapdriver_p_diff/XXxor3/MMM_u2-M_u3_g",
        Nets.dac_botplate_p_diff[12]: "N_DAC_DRIVE_BOTPLATE_DIFF_P<3>_XXcapdriver_p_diff/XXxor3/MMM_u4_1-M_u3_d",
        Nets.dac_state_n[12]: "N_DAC_STATE_N_MAIN<3>_XXcapdriver_n_main/XXxor3/MMM_u2-M_u3_g",
        Nets.dac_botplate_n[12]: "N_DAC_DRIVE_BOTPLATE_MAIN_N<3>_XXcapdriver_n_main/XXxor3/MMM_u4_1-M_u3_d",
        Nets.dac_state_n_diff[12]: "N_DAC_STATE_N_DIFF<3>_XXcapdriver_n_diff/XXxor3/MMM_u2-M_u3_g",
        Nets.dac_botplate_n_diff[12]: "N_DAC_DRIVE_BOTPLATE_DIFF_N<3>_XXcapdriver_n_diff/XXxor3/MMM_u4_1-M_u3_d",
        Nets.dac_state_p[13]: "N_DAC_STATE_P_MAIN<2>_XXcapdriver_p_main/XXxor2/MMM_u2-M_u3_g",
        Nets.dac_botplate_p[13]: "N_DAC_DRIVE_BOTPLATE_MAIN_P<2>_XXcapdriver_p_main/XXxor2/MMM_u4_1-M_u3_d",
        Nets.dac_state_p_diff[13]: "N_DAC_STATE_P_DIFF<2>_XXcapdriver_p_diff/XXxor2/MMM_u2-M_u3_g",
        Nets.dac_botplate_p_diff[13]: "N_DAC_DRIVE_BOTPLATE_DIFF_P<2>_XXcapdriver_p_diff/XXxor2/MMM_u4_1-M_u3_d",
        Nets.dac_state_n[13]: "N_DAC_STATE_N_MAIN<2>_XXcapdriver_n_main/XXxor2/MMM_u2-M_u3_g",
        Nets.dac_botplate_n[13]: "N_DAC_DRIVE_BOTPLATE_MAIN_N<2>_XXcapdriver_n_main/XXxor2/MMM_u4_1-M_u3_d",
        Nets.dac_state_n_diff[13]: "N_DAC_STATE_N_DIFF<2>_XXcapdriver_n_diff/XXxor2/MMM_u2-M_u3_g",
        Nets.dac_botplate_n_diff[13]: "N_DAC_DRIVE_BOTPLATE_DIFF_N<2>_XXcapdriver_n_diff/XXxor2/MMM_u4_1-M_u3_d",
        Nets.dac_state_p[14]: "N_DAC_STATE_P_MAIN<1>_XXcapdriver_p_main/XXxor1/MMM_u2-M_u3_g",
        Nets.dac_botplate_p[14]: "N_DAC_DRIVE_BOTPLATE_MAIN_P<1>_XXcapdriver_p_main/XXxor1/MMM_u4_1-M_u3_d",
        Nets.dac_state_p_diff[14]: "N_DAC_STATE_P_DIFF<1>_XXcapdriver_p_diff/XXxor1/MMM_u2-M_u3_g",
        Nets.dac_botplate_p_diff[14]: "N_DAC_DRIVE_BOTPLATE_DIFF_P<1>_XXcapdriver_p_diff/XXxor1/MMM_u4_1-M_u3_d",
        Nets.dac_state_n[14]: "N_DAC_STATE_N_MAIN<1>_XXcapdriver_n_main/XXxor1/MMM_u2-M_u3_g",
        Nets.dac_botplate_n[14]: "N_DAC_DRIVE_BOTPLATE_MAIN_N<1>_XXcapdriver_n_main/XXxor1/MMM_u4_1-M_u3_d",
        Nets.dac_state_n_diff[14]: "N_DAC_STATE_N_DIFF<1>_XXcapdriver_n_diff/XXxor1/MMM_u2-M_u3_g",
        Nets.dac_botplate_n_diff[14]: "N_DAC_DRIVE_BOTPLATE_DIFF_N<1>_XXcapdriver_n_diff/XXxor1/MMM_u4_1-M_u3_d",
        Nets.dac_state_p[15]: "N_DAC_STATE_P_MAIN<0>_XXcapdriver_p_main/XXxor0/MMM_u2-M_u3_g",
        Nets.dac_botplate_p[15]: "N_DAC_DRIVE_BOTPLATE_MAIN_P<0>_XXcapdriver_p_main/XXxor0/MMM_u4_1-M_u3_d",
        Nets.dac_state_p_diff[15]: "N_DAC_STATE_P_DIFF<0>_XXcapdriver_p_diff/XXxor0/MMM_u2-M_u3_g",
        Nets.dac_botplate_p_diff[15]: "N_DAC_DRIVE_BOTPLATE_DIFF_P<0>_XXcapdriver_p_diff/XXxor0/MMM_u4_1-M_u3_d",
        Nets.dac_state_n[15]: "N_DAC_STATE_N_MAIN<0>_XXcapdriver_n_main/XXxor0/MMM_u2-M_u3_g",
        Nets.dac_botplate_n[15]: "N_DAC_DRIVE_BOTPLATE_MAIN_N<0>_XXcapdriver_n_main/XXxor0/MMM_u4_1-M_u3_d",
        Nets.dac_state_n_diff[15]: "N_DAC_STATE_N_DIFF<0>_XXcapdriver_n_diff/XXxor0/MMM_u2-M_u3_g",
        Nets.dac_botplate_n_diff[15]: "N_DAC_DRIVE_BOTPLATE_DIFF_N<0>_XXcapdriver_n_diff/XXxor0/MMM_u4_1-M_u3_d",
    }
