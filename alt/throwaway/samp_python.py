"""
Sampling Switch block definition.

This is what you'd actually write for each of your 30-40 blocks.
Framework code lives in flow/ and is imported.
"""

from flow import block, Io, Input, Output, InOut, CellBuilder, TestbenchIo, Pvt
from flow.pdk import Nfet, Pfet, Capacitor, Vsource
from dataclasses import dataclass
from enum import Enum


# =============================================================================
# IO
# =============================================================================

class SampIo(Io):
    din = Input()
    dout = Output()
    clk = Input()
    clk_b = Input()
    vdd = InOut()
    vss = InOut()


# =============================================================================
# Parameters
# =============================================================================

class SwitchType(Enum):
    NMOS = "nmos"
    PMOS = "pmos"
    TGATE = "tgate"


class Vth(Enum):
    LVT = "lvt"
    SVT = "svt"


# =============================================================================
# Block
# =============================================================================

@block(io=SampIo)
@dataclass
class Samp:
    switch_type: SwitchType
    w: int
    l: int
    vth: Vth = Vth.LVT

    def schematic(self, io, cell: CellBuilder):
        if self.switch_type == SwitchType.NMOS:
            mn = cell.instantiate(Nfet(self.w, self.l, self.vth))
            cell.connect(io.dout, mn.d)
            cell.connect(io.clk, mn.g)
            cell.connect(io.din, mn.s)
            cell.connect(io.vss, mn.b)

        elif self.switch_type == SwitchType.PMOS:
            mp = cell.instantiate(Pfet(self.w, self.l, self.vth))
            cell.connect(io.dout, mp.d)
            cell.connect(io.clk_b, mp.g)
            cell.connect(io.din, mp.s)
            cell.connect(io.vdd, mp.b)

        elif self.switch_type == SwitchType.TGATE:
            mn = cell.instantiate(Nfet(self.w, self.l, self.vth))
            mp = cell.instantiate(Pfet(self.w, self.l, self.vth))
            cell.connect(io.dout, mn.d, mp.d)
            cell.connect(io.clk, mn.g)
            cell.connect(io.clk_b, mp.g)
            cell.connect(io.din, mn.s, mp.s)
            cell.connect(io.vss, mn.b)
            cell.connect(io.vdd, mp.b)


# =============================================================================
# Sweeps
# =============================================================================

variants = [
    Samp(switch_type, w, l, vth)
    for switch_type in SwitchType
    for w in [5, 10, 20, 40]
    for l in [1, 2]
    for vth in Vth
]


# =============================================================================
# Testbench
# =============================================================================

@block(io=TestbenchIo)
@dataclass
class SampTb:
    pvt: Pvt
    dut: Samp

    def schematic(self, io, cell: CellBuilder):
        vdd = cell.signal("vdd")
        clk = cell.signal("clk")
        clk_b = cell.signal("clk_b")
        din = cell.signal("din")
        dout = cell.signal("dout")

        cell.instantiate(Vsource.dc(self.pvt.voltage), p=vdd, n=io.vss)
        cell.instantiate(Vsource.pulse(0, self.pvt.voltage, period=100e-9, width=50e-9), p=clk, n=io.vss)
        cell.instantiate(Vsource.pulse(self.pvt.voltage, 0, period=100e-9, width=50e-9), p=clk_b, n=io.vss)
        cell.instantiate(Vsource.dc(0.5), p=din, n=io.vss)
        cell.instantiate(Capacitor(1e-12), p=dout, n=io.vss)

        cell.instantiate(self.dut, din=din, dout=dout, clk=clk, clk_b=clk_b, vdd=vdd, vss=io.vss)

        return dout  # probe node


# =============================================================================
# Analyses & Measures
# =============================================================================

analyses = {
    "tran": {"stop": 326e-9, "step": 0.1e-9}
}

measures = {
    "ron_ohm": lambda out: out.on_resistance("din", "dout", "clk"),
    "settling_ns": lambda out: out.settling_time("dout", tol=0.01),
    "charge_injection_mv": lambda out: out.charge_injection("dout", "clk"),
}
