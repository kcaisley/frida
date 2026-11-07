"""The ADC's circuit: its nets (``Nets``, FRIDA's 16 stages; ``_nets`` at any count) and its
generator (``netlist``): a generated SAR converter, or a fabricated converter's black box.

A generated converter composes:

    netlist(Params(...))
    ├── xdigital (ExternalModule: FRIDA's hardened netlist at 16 stages, synthesized otherwise)
    ├── xdac_p / xdac_n (capdac.netlist: one side of the DAC each, its devices the active PDK's)
    ├── xsamp_p / xsamp_n (samp.netlist)
    ├── MP_clk_comp_b / MN_clk_comp_b (the comparator's clock complement)
    └── xcomp (comp.netlist)

A fabricated converter (``Params.fabricated``: FRIDA-1's, ``Fabricated``) is no regenerated
netlist: its ``netlist`` is a black box, the extraction's cell ``adc_12b_17step`` with the
tape-out's positional pins (``fixtures/frida1_ports.scs``) bound to the canonical nets
(``_frida1_ports``), no device inside. Its simulations take an extraction instead (``flow.adc.sim``)
and its area its layout (``flow.adc.layout``).

The digital block (``design/hdl/adc_digital.v``) at any number of stages is a SPICE netlist of the
PDK's standard cells (``_digital_netlist``: ``adc_digital/tsmc65/n12/adc_digital_n12.sp`` under
``MODELS_DIR``). FRIDA's 16 stages are the hardened OpenROAD netlist (``design/spice/adc_digital.sp``:
placed, clock-tree buffered and routed, from an earlier RTL that switched register 15 first). Any
other count is synthesized from the RTL at ``N_STAGES`` with yosys (on the PATH: the OSS CAD suite)
onto the PDK's standard cells, without placement or clock tree: flip-flops by ``dfflibmap``, the
logic by ABC into generic gates, each bound to the smallest cell of its function in the PDK's
generic map (``pdk.<pdk>.hdl21.cells.GENERIC``; ABC's own Liberty mapping misreads some libraries'
output pins), constants on its tie cells and ports that only alias another net behind its buffer.
Register 0 drives C0, as in the RTL. The netlist is cached beside the blocks' characterizations
(``flow.sweep.lookup.MODELS_DIR``), under ``adc_digital/``.

The converter's DAC is capdac's (``capdac.Params``): two of its sides, one module
(``capdac.netlist``) whose requests are resolved to the active PDK's devices, so the generated ADC
needs a PDK. Each side's states are the digital block's of that side, its top plate the one that
side's sampler holds and the comparator reads, and its supply the DAC's (``vdd_dac``, ``vss_dac``,
which also shield its capacitors). Its polarity is fixed: each stage's main plates follow its state
and its difference plates the complement (capdac's main chains do not invert, its difference chains
do), so the subtraction is wired in. The digital block's difference states and inversion controls
(``dac_state_<side>_diff``, ``dac_invert_<side>_<kind>``) drive nothing, and ``dac_diffcaps`` keeps
its pin with no effect: FRIDA-1's extracted view, its lab scans and the behavioral model keep its
other mode, the difference plates switching with the main ones. The bottom plates lie inside the
sides (``_generated_aliases``). One side's plates as a behavioral DAC gives them are capdac's
(``capdac.Model.plates_f``).

The probes' bindings (``flow.adc.sim`` saves and reads them): the generated converter's bottom
plates inside its DAC's sides (``_generated_aliases``), and FRIDA-1's extraction's positional pins
(``_frida1_ports``, ``_pex``) and RC terminals (``_frida1_terminals``), relative to the ADC
instance; these bindings never rename the IP itself.
"""

import gzip
import json
import os
import re
import shutil
import subprocess
import tempfile
from functools import cache
from pathlib import Path

import hdl21 as h
from hdl21.primitives import MosType

from flow import capdac, comp, samp
from flow.adc.params import Params
from flow.circuit.ports import module_from_ports, port_connections
from flow.layout.devices.device import active_pdk, resolve
from flow.layout.devices.mosfet.netlist import mos
from flow.sweep.lookup import MODELS_DIR
from flow.util.netlist import normalize_bus_pin, subcircuit_ports

# the digital block: its netlist at FRIDA's 16 stages, its RTL and its synthesis cache
_ROOT = Path(__file__).resolve().parents[2]
_HARDENED = _ROOT / "design/spice/adc_digital.sp"
_SOURCES = tuple(
    _ROOT / "design/hdl" / name
    for name in ("cells_tsmc65.v", "clkgate.v", "sampdriver.v", "salogic.v", "adc_digital.v")
)
_CACHE = MODELS_DIR / "adc_digital"
# yosys's generic gates -> the generic function whose smallest cell the PDK's map gives it; the
# generic pins are yosys's ports (A, B, S in, Y out; mux2's Y = S ? B : A, as $_MUX_'s)
_GATES = {
    "$_BUF_": "buf",
    "$_NOT_": "inv",
    "$_AND_": "and2",
    "$_NAND_": "nand2",
    "$_OR_": "or2",
    "$_NOR_": "nor2",
    "$_XOR_": "xor2",
    "$_XNOR_": "xnor2",
    "$_MUX_": "mux2",
}


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

    Its stage count follows the array: at FRIDA's 16 the digital block is the fabricated, hardened
    netlist; at any other count the same RTL is synthesized for it (``_digital_netlist``).

    The DAC's two sides are capdac's array, one module (``capdac.netlist``) resolved once to the
    active PDK's devices: ``xdac_p`` switched by the digital block's P states (``dac_state_p``) on
    the P top plate, ``xdac_n`` by its N states on the N top plate, both between ``vdd_dac`` and
    ``vss_dac``. Its polarity is fixed, the difference plates switching opposite the main ones, so
    ``dac_diffcaps`` has no effect here and the digital block's inversion controls drive nothing.
    The canonical bottom plates are the sides' own (``_generated_aliases``), not the ADC's nets.
    """
    if param.fabricated is not None:
        return _black_box()
    pdk = active_pdk()
    if pdk is None:
        raise RuntimeError("the ADC's DAC is capdac's, its devices the active PDK's, and none is set")
    stages = _stages(param)
    nets = _nets(stages)
    # every canonical net but the bottom plates, which are the DAC's sides' own
    plates = {
        net.name
        for net in (nets.dac_botplate_p, nets.dac_botplate_n, nets.dac_botplate_p_diff, nets.dac_botplate_n_diff)
    }
    Adc = module_from_ports("Adc", {name: net for name, net in nets.signals.items() if name not in plates})
    digital = _digital(stages)
    Adc.xdigital = digital()(
        **{
            physical: Adc.namespace[net.parent.name][net.index] if isinstance(net, h.Slice) else Adc.namespace[net.name]
            for net, physical in _digital_aliases(digital, nets).items()
        }
    )

    # The generated comparator consumes both clock polarities, whereas the
    # synthesized digital block exposes only ``clk_comp``. Generate its true
    # complement locally instead of borrowing an unrelated sampling clock.
    # fingered as an analog device of the row cells (``mos``), as the comparator's own
    Adc.MP_clk_comp_b = mos(tp=MosType.PMOS, vth=param.comp.vth, w=10, l=1)(
        d=Adc.clk_comp_b,
        g=Adc.clk_comp,
        s=Adc.vdd_a,
        b=Adc.vdd_a,
    )
    Adc.MN_clk_comp_b = mos(tp=MosType.NMOS, vth=param.comp.vth, w=10, l=1)(
        d=Adc.clk_comp_b,
        g=Adc.clk_comp,
        s=Adc.vss_a,
        b=Adc.vss_a,
    )

    # both sides one array, resolved once
    dac = capdac.netlist(param.cdac)
    resolve(dac, pdk)
    sampler = samp.netlist(param.samp)
    for side, vin, top, state, clk, clk_b in (
        ("p", Adc.vin_p, Adc.vdac_p, Adc.dac_state_p, Adc.clk_samp_p, Adc.clk_samp_p_b),
        ("n", Adc.vin_n, Adc.vdac_n, Adc.dac_state_n, Adc.clk_samp_n, Adc.clk_samp_n_b),
    ):
        Adc.add(dac(dac_state=state, vdac=top, vdd=Adc.vdd_dac, vss=Adc.vss_dac), name=f"xdac_{side}")
        Adc.add(sampler(din=vin, dout=top, clk=clk, clk_b=clk_b, vdd=Adc.vdd_a, vss=Adc.vss_a), name=f"xsamp_{side}")

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
    state."""
    renamed = {Nets.seq_logic: "seq_update"}
    aliases = {}
    for net in Nets.signals.values():
        if net.vis != h.Visibility.PORT or net in (Nets.dac_state_p, Nets.dac_state_n):
            continue
        if net.width == 1:
            aliases[net] = renamed.get(net, net.name)
        else:
            for bit in range(net.width):
                aliases[net[bit]] = f"{net.name}_{net.width - 1 - bit}"
    return aliases


# The digital block: its netlist at a stage count and its pins bound to the canonical nets


def _digital_cell(stages: int) -> str:
    """The digital block's subcircuit name: FRIDA's at 16 stages, a synthesized one otherwise."""
    return "adc_digital" if stages == 16 else f"adc_digital_n{stages}"


def _digital_netlist(stages: int, pdk: str = "tsmc65") -> tuple[Path, str]:
    """The digital block's SPICE netlist at ``stages`` and its subcircuit name, synthesized on
    first use."""
    if stages == 16:
        return _HARDENED, _digital_cell(stages)
    if pdk != "tsmc65":
        raise ValueError(f"the digital block is synthesized onto TSMC65's cells only, not {pdk}'s")
    if stages < 2:
        raise ValueError(f"the digital block needs at least two stages, not {stages}")
    cell = _digital_cell(stages)
    path = _CACHE / pdk / f"n{stages}" / f"{cell}.sp"
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        # another process may synthesize the same count: each writes its own and renames it in
        with tempfile.TemporaryDirectory(dir=path.parent) as work:
            text = _synthesize(stages, cell, Path(work))
            (Path(work) / path.name).write_text(text)
            os.replace(Path(work) / path.name, path)
    return path, cell


def _digital(stages: int = 16) -> h.ExternalModule:
    """The digital block at ``stages`` (``_digital_netlist``) with its netlist's exact scalar pin
    order."""
    path, cell = _digital_netlist(stages)
    return h.ExternalModule(
        name=cell, port_list=[h.Inout(name=pin) for pin in subcircuit_ports(path.read_text(), cell)]
    )


def _digital_aliases(module: h.ExternalModule, nets=Nets) -> dict[h.Signal | h.Slice, str]:
    """Bind every digital pin to its canonical ADC net (``nets``: ``_nets`` of its stage count).
    FRIDA's hardened netlist predates the C0-first RTL: its physical bit 15 is C0. A synthesized
    netlist follows the RTL: its bit 0 is."""
    reversed_bits = module.name == _digital_cell(16)
    renamed = {
        nets.seq_logic: "seq_update",
        nets.dac_state_p: "dac_state_p_main",
        nets.dac_state_n: "dac_state_n_main",
    }
    by_physical_name = {renamed.get(net, net.name): net for net in nets.signals.values()}
    aliases = {}
    for pin in module.port_list:
        if match := re.fullmatch(r"(.+)\[(\d+)\]", pin.name):
            net = by_physical_name[match[1]]
            index = net.width - 1 - int(match[2]) if reversed_bits else int(match[2])
            if not 0 <= index < net.width:
                raise ValueError(f"Digital pin {pin.name} exceeds canonical width {net.width}")
            canonical = net[index]
        else:
            canonical = by_physical_name[pin.name]
            if canonical.width != pin.width:
                raise ValueError(f"Digital pin width differs from {canonical.name}")
        if canonical in aliases:
            raise ValueError(f"Duplicate digital binding for {canonical}")
        aliases[canonical] = pin.name
    return aliases


def _library_cell(library, function: str) -> tuple[str, dict[str, str]]:
    """The smallest cell of a generic function in the PDK's map, and its pin for each generic pin."""
    drives = sorted(int(name.rsplit("_x", 1)[1]) for name in library.GENERIC if name.rsplit("_x", 1)[0] == function)
    target, pins, _high, _low = library.GENERIC[f"{function}_x{drives[0]}"]
    return target, {generic: pin for pin, generic in pins.items()}


def _synthesize(stages: int, cell: str, work: Path) -> str:
    from pdk.tsmc65.hdl21 import cells as library
    from pdk.tsmc65.hdl21.site import STANDARD_CELL_SPICE_NETLISTS
    from pdk.tsmc65.layout.paths import STD_LIBERTY

    if shutil.which("yosys") is None:
        raise FileNotFoundError("yosys is not on the PATH (the OSS CAD suite's bin)")
    liberty = work / "cells.lib"
    with gzip.open(STD_LIBERTY, "rb") as compressed:
        liberty.write_bytes(compressed.read())
    gates = work / "gates.v"
    maps = {gate: _library_cell(library, function) for gate, function in _GATES.items()}
    gates.write_text(
        "".join(
            f"module \\{gate} ({', '.join(port for port in ports if port not in ('VDD', 'VSS'))});\n"
            + "".join(
                f"  {'output' if port == 'Y' else 'input'} {port};\n" for port in ports if port not in ("VDD", "VSS")
            )
            + f"  {target} _TECHMAP_REPLACE_ ("
            + ", ".join(f".{pin}({port})" for port, pin in ports.items() if port not in ("VDD", "VSS"))
            + ");\n"
            + "endmodule\n"
            for gate, (target, ports) in maps.items()
        )
    )
    tie_high, high = _library_cell(library, "tiehi")
    tie_low, low = _library_cell(library, "tielo")
    buffer, buffer_pins = _library_cell(library, "buf")
    script = work / "synth.ys"
    script.write_text(
        "\n".join(
            (
                f"read_liberty -lib {liberty}",
                f"read_verilog -sv {' '.join(str(source) for source in _SOURCES)}",
                f"chparam -set N_STAGES {stages} adc_digital",
                "hierarchy -check -top adc_digital",
                "synth -top adc_digital -flatten",
                f"dfflibmap -liberty {liberty}",
                "abc -g AND,NAND,OR,NOR,XOR,XNOR,MUX",
                f"techmap -map {gates}",
                "opt_clean -purge",
                f"hilomap -singleton -hicell {tie_high} {high['Y']} -locell {tie_low} {low['Y']}",
                f"insbuf -buf {buffer} {buffer_pins['A']} {buffer_pins['Y']}",
                "opt_clean -purge",
                "check -assert",
                f"write_json {work / 'netlist.json'}",
            )
        )
    )
    subprocess.run(["yosys", "-q", "-l", str(work / "yosys.log"), str(script)], check=True, capture_output=True)
    module = json.loads((work / "netlist.json").read_text())["modules"]["adc_digital"]
    pin_order = {}
    for netlist in STANDARD_CELL_SPICE_NETLISTS:
        for line in Path(netlist).read_text(errors="replace").splitlines():
            words = line.split()
            if len(words) > 2 and words[0].lower() == ".subckt":
                pin_order.setdefault(words[1], words[2:])
    # each bit's node: a port bit by its name, as OpenROAD writes them; an inner net by its id
    nodes: dict[int, str] = {}
    ports = []
    for name, port in module["ports"].items():
        for index, bit in enumerate(port["bits"]):
            node = name if len(port["bits"]) == 1 else f"{name}[{index}]"
            if not isinstance(bit, int) or bit in nodes:
                raise ValueError(f"{cell} port bit {node} is a constant or aliases {nodes.get(bit)}")
            nodes[bit] = node
            ports.append(node)
    lines = [f"* {cell}: design/hdl/adc_digital.v at N_STAGES={stages}, synthesized by flow.adc.subckt", ""]
    lines.append(f".SUBCKT {cell} {' '.join(ports)} vdd_d vss_d")
    unconnected = 0
    for index, instance in enumerate(module["cells"].values()):
        connections = []
        for pin in pin_order[instance["type"]]:
            if pin == "VDD":
                connections.append("vdd_d")
            elif pin == "VSS":
                connections.append("vss_d")
            elif pin in instance["connections"]:
                (bit,) = instance["connections"][pin]
                if not isinstance(bit, int):
                    raise ValueError(f"{cell}: {instance['type']} pin {pin} is tied to {bit!r}, not a tie cell")
                connections.append(nodes.setdefault(bit, f"n{bit}"))
            else:  # an output nothing reads (a flip-flop's QN)
                unconnected += 1
                connections.append(f"nc{unconnected}")
        lines.append(f"X{index} {' '.join(connections)} {instance['type']}")
    lines += [f".ENDS {cell}", ""]
    return "\n".join(lines)


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
