"""
Clock conditioning generator for FRIDA.

Supports, from the PDK's library cells (inverters, NOR2, NAND2):
- Non-overlapping two-phase clocks: two NOR gates, each fed back the other's delayed output
- A rising-edge pulse: a NOR of clkb and clk through an inverter delay chain
- A glitch-free clock gate: en held by a latch while clk is high, gating clk in a NAND
"""

from enum import Enum, auto
from pathlib import Path

import hdl21 as h

from flow.circuit.devices import Inverter, LogicCellParams, Nand2, Nor2
from flow.circuit.devices import write_netlist as _write_netlist
from flow.circuit.ports import module_from_ports
from flow.latch.subckt import LatchParams, _build_latch


class Function(Enum):
    NONOVERLAP = auto()  # outp, outn: two clock phases that never overlap
    PULSE = auto()  # outp: a pulse at each rising clk edge, as long as the delay chain; outn its complement
    GATE = auto()  # outp: clk while en (held through the clock's high phase), outn its complement


@h.paramclass
class ClkgenParams:
    """Clock conditioning parameters: the function and the delay chain's length in inverter pairs."""

    function = h.Param(dtype=Function, desc="Clock function", default=Function.NONOVERLAP)
    delay = h.Param(dtype=int, desc="Inverter pairs in each delay chain", default=1)
    drive = h.Param(dtype=int, desc="Output inverter drive: 1, 4 or 8", default=4)


def is_valid_clkgen_params(param: ClkgenParams) -> bool:
    """Check if this clock function is valid: at least one inverter pair, a library drive."""
    return param.delay >= 1 and param.drive in (1, 4, 8)


@h.bundle
class ClkgenNets:
    clk, clkb = h.Clock(), h.Clock()
    en = h.Input(desc="Clock gate enable")
    outp, outn = h.Output(), h.Output()
    vdd = h.Power(direction=h.PortDir.INOUT)
    vss = h.Ground(direction=h.PortDir.INOUT)


@h.generator
def Clkgen(param: ClkgenParams) -> h.Module:
    """
    Clock conditioning generator.

    Generates non-overlapping two-phase clocks, a rising-edge pulse, or a glitch-free clock
    gate, its logic the PDK's library cells (generic cells, mapped by the PDK's compile).
    """
    if not is_valid_clkgen_params(param):
        raise ValueError(f"Invalid clock generator params: {param}")

    Clkgen = module_from_ports("Clkgen", ClkgenNets.signals)
    supplies = {"VDD": Clkgen.vdd, "VSS": Clkgen.vss}

    def chain(name: str, inp, out):  # 2 x delay inverters from inp to out (no inversion)
        nodes = [inp, *(Clkgen.add(h.Signal(name=f"{name}{k}")) for k in range(1, 2 * param.delay)), out]
        for k in range(2 * param.delay):
            Clkgen.add(Inverter(LogicCellParams(drive=1))(A=nodes[k], Y=nodes[k + 1], **supplies), name=f"X{name}{k}")

    if param.function == Function.NONOVERLAP:
        # each phase: NOR of its clock and the other phase, delayed; a phase rises only after the other fell
        Clkgen.midp, Clkgen.midn = h.Signal(), h.Signal()
        Clkgen.Xnor_p = Nor2(LogicCellParams(drive=2))(A=Clkgen.clkb, B=Clkgen.outn, Y=Clkgen.midp, **supplies)
        Clkgen.Xnor_n = Nor2(LogicCellParams(drive=2))(A=Clkgen.clk, B=Clkgen.outp, Y=Clkgen.midn, **supplies)
        chain("dly_p", Clkgen.midp, Clkgen.outp)
        chain("dly_n", Clkgen.midn, Clkgen.outn)
        return Clkgen

    if param.function == Function.PULSE:
        # high while clk is high and its delayed copy still low: NOR(clkb, delayed clk)
        Clkgen.clk_d = h.Signal(desc="Delayed clk")
        chain("dly", Clkgen.clk, Clkgen.clk_d)
        Clkgen.Xnor = Nor2(LogicCellParams(drive=2))(A=Clkgen.clkb, B=Clkgen.clk_d, Y=Clkgen.outp, **supplies)
        Clkgen.Xout = Inverter(LogicCellParams(drive=param.drive))(A=Clkgen.outp, Y=Clkgen.outn, **supplies)
        return Clkgen

    # GATE: a latch transparent while clk is low holds en through the high phase, so outp cannot glitch
    Clkgen.en_l, Clkgen.en_lb = h.Signal(desc="Latched enable"), h.Signal()
    _build_latch(Clkgen, LatchParams(), "", Clkgen.en, Clkgen.clkb, Clkgen.clk, Clkgen.en_lb, Clkgen.en_l)
    Clkgen.Xnand = Nand2(LogicCellParams(drive=1))(A=Clkgen.clk, B=Clkgen.en_l, Y=Clkgen.outn, **supplies)
    Clkgen.Xout = Inverter(LogicCellParams(drive=param.drive))(A=Clkgen.outn, Y=Clkgen.outp, **supplies)
    return Clkgen


def write_netlist(params: ClkgenParams, path: Path, pdk) -> Path:
    """The clock generator after ``pdk``'s compile, as one flat SPICE subcircuit named after
    ``path`` (``flow.circuit.devices.write_netlist``: its logic cells written as the PDK's library cells)."""

    return _write_netlist(params, path, pdk, generator=Clkgen, nets=ClkgenNets)


# ==== Named clock functions ====

CASES = {
    # non-overlapping two-phase clocks
    "nonoverlap": ClkgenParams(),
    # rising-edge pulse
    "pulse": ClkgenParams(function=Function.PULSE, delay=4),
    # glitch-free clock gate
    "gate": ClkgenParams(function=Function.GATE),
}
