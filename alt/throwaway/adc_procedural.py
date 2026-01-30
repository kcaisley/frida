"""
SAR ADC block definition (procedural Substrate-style).

Translates blocks/adc.py to the procedural style.
Key challenges:
  - Hierarchical instantiation of child blocks with their own parameters
  - Dynamic IO - port count depends on n_cycles/n_adc
  - Child block parameters derived from parent topology (Cdac's n_dac/n_extra)
  - Each child block type has its own complex parameter set

Design approach:
  - ADC owns the top-level topology (n_cycles, n_adc)
  - Child blocks are passed as full instances, except:
    - Cdac: only non-derived params are exposed (n_dac/n_extra come from ADC)
  - Two instances of differential blocks (samp, cdac) can share config or differ
"""

from flow import block, Io, Input, Output, InOut, CellBuilder, TestbenchIo, Pvt
from flow import DynamicIo, Bus
from flow.pdk import Nfet, Pfet, Cap, Res, Vsource
from flow.sources import PwlStep
from flow.digital import ExternalCell  # For synthesized digital blocks
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

# Import child block definitions
from samp_python import Samp, SwitchType, SampIo
from comp_procedural import (
    Comp, CompIo,
    PreampDiffpair, PreampBias, CompStages,
    LatchPwrgateCtl, LatchPwrgateNode, LatchRstExternCtl, LatchRstInternCtl,
)
from cdac_procedural import (
    Cdac, RedunStrat, SplitStrat, CapType,
)

# Common Vth enum (also defined in child blocks, re-export for convenience)
class Vth(Enum):
    LVT = "lvt"
    SVT = "svt"


# =============================================================================
# IO (dynamic - port count depends on n_cycles/n_adc)
# =============================================================================

def make_adc_io(num_caps: int) -> type:
    """Factory to create ADC IO class with num_caps DAC state bus width."""
    class AdcIo(DynamicIo):
        # Clock/control signals
        clk_init = Input()
        clk_update = Input()
        clk_samp = Input()
        clk_samp_b = Input()
        dac_mode = Input()

        # Analog inputs
        vinp = InOut()  # vin+
        vinn = InOut()  # vin-

        # Supplies
        vdd_a = InOut()
        vss_a = InOut()
        vdd_d = InOut()
        vss_d = InOut()

        # DAC state bus inputs (from external SPI/controller)
        # 2 buses per side: astate and bstate, num_caps bits each
        dac_astate_p = Bus(Input(), width=num_caps)
        dac_astate_n = Bus(Input(), width=num_caps)
        dac_bstate_p = Bus(Input(), width=num_caps)
        dac_bstate_n = Bus(Input(), width=num_caps)

    return AdcIo


# =============================================================================
# CDAC Configuration (non-derived params only)
# =============================================================================
# Since Cdac's n_dac and n_extra are derived from ADC's n_adc and n_cycles,
# we expose only the "style" parameters that can be freely chosen.

@dataclass
class CdacConfig:
    """CDAC configuration parameters (excluding topology-derived n_dac/n_extra)."""
    redun_strat: RedunStrat = RedunStrat.RDX2
    split_strat: SplitStrat = SplitStrat.NO_SPLIT
    cap_type: CapType = CapType.MOM1
    vth: Vth = Vth.LVT

    def build_cdac(self, n_dac: int, n_extra: int) -> Cdac:
        """Construct full Cdac with derived topology params."""
        return Cdac(
            n_dac=n_dac,
            n_extra=n_extra,
            redun_strat=self.redun_strat,
            split_strat=self.split_strat,
            cap_type=self.cap_type,
            vth=self.vth,
        )


# =============================================================================
# Inverter (simple helper block)
# =============================================================================

class InvIo(Io):
    din = Input()
    dout = Output()
    vdd = InOut()
    vss = InOut()


@dataclass
class Inv:
    """Simple CMOS inverter."""
    wp: int = 2
    wn: int = 1
    l: int = 1
    vth: Vth = Vth.LVT

    def schematic(self, io, cell: CellBuilder):
        mp = cell.instantiate(Pfet(self.wp, self.l, self.vth), name="MP")
        mn = cell.instantiate(Nfet(self.wn, self.l, self.vth), name="MN")
        cell.connect(io.dout, mp.d, mn.d)
        cell.connect(io.din, mp.g, mn.g)
        cell.connect(io.vdd, mp.s, mp.b)
        cell.connect(io.vss, mn.s, mn.b)


# =============================================================================
# SAR Logic (digital black-box)
# =============================================================================

@dataclass
class SaLogic:
    """
    SAR Logic digital control block.

    This is a synthesized digital block - we just reference the external netlist.
    The schematic method instantiates it as an external cell.
    """
    n_bits: int

    def schematic(self, io, cell: CellBuilder):
        # Reference external synthesized netlist
        cell.instantiate(
            ExternalCell("salogic", library="digital"),
            **{pin: getattr(io, pin) for pin in io.pins()}
        )


# =============================================================================
# ADC Block
# =============================================================================

@dataclass
class Adc:
    """
    SAR ADC with configurable resolution and architecture.

    Hierarchy:
      ADC
      ├── SaLogic (digital SAR controller)
      ├── Cdac+ (positive side capacitor DAC)
      ├── Cdac- (negative side capacitor DAC)
      ├── Samp+ (positive side sampling switch)
      ├── Samp- (negative side sampling switch)
      ├── Comp (comparator)
      └── Inv (clock inverter)

    Topology parameters (n_cycles, n_adc) determine:
      - num_caps = n_dac + n_extra (physical capacitors per side)
      - n_dac = n_adc - 1 (DAC resolution)
      - n_extra = n_cycles - n_adc (redundant capacitors)
    """
    # Top-level topology
    n_cycles: int           # Number of SAR conversion cycles (8, 12, 14, 16, 18, 20)
    n_adc: int              # ADC resolution in bits (8, 12, 14)

    # Child block configurations
    # Samp: full instances for + and - sides (can differ or be same)
    samp_p: Samp = field(default_factory=lambda: Samp(SwitchType.TGATE, w=5, l=1))
    samp_n: Samp = field(default_factory=lambda: Samp(SwitchType.TGATE, w=5, l=1))

    # Comp: full instance
    comp: Comp = field(default_factory=lambda: Comp(
        preamp_diffpair=PreampDiffpair.NMOS_INPUT,
        preamp_bias=PreampBias.DYN_BIAS,
        comp_stages=CompStages.DOUBLE_STAGE,
        latch_pwrgate_ctl=LatchPwrgateCtl.SIGNALLED,
        latch_pwrgate_node=LatchPwrgateNode.INTERNAL,
        latch_rst_extern_ctl=LatchRstExternCtl.NO_RESET,
        latch_rst_intern_ctl=LatchRstInternCtl.SIGNALLED,
    ))

    # Cdac: only style params (n_dac/n_extra derived from ADC topology)
    # Both sides use same config by default; override cdac_n_config for asymmetric
    cdac_config: CdacConfig = field(default_factory=CdacConfig)
    cdac_n_config: Optional[CdacConfig] = None  # If None, uses cdac_config

    # Inv: clock inverter config
    inv: Inv = field(default_factory=Inv)

    # Derived fields (computed in __post_init__)
    _n_dac: int = field(init=False, repr=False)
    _n_extra: int = field(init=False, repr=False)
    _num_caps: int = field(init=False, repr=False)
    _io_class: type = field(init=False, repr=False)
    _cdac_p: Cdac = field(init=False, repr=False)
    _cdac_n: Cdac = field(init=False, repr=False)

    def __post_init__(self):
        # Derive CDAC topology from ADC params
        self._n_dac = self.n_adc - 1
        self._n_extra = self.n_cycles - self.n_adc
        self._num_caps = self._n_dac + self._n_extra

        # Validate
        if self._n_extra < 0:
            raise ValueError(f"n_cycles ({self.n_cycles}) must be >= n_adc ({self.n_adc})")

        # Build CDAC instances with derived topology
        self._cdac_p = self.cdac_config.build_cdac(self._n_dac, self._n_extra)
        cdac_n_cfg = self.cdac_n_config if self.cdac_n_config else self.cdac_config
        self._cdac_n = cdac_n_cfg.build_cdac(self._n_dac, self._n_extra)

        # Create IO class
        self._io_class = make_adc_io(self._num_caps)

    @property
    def num_caps(self) -> int:
        return self._num_caps

    def is_valid(self) -> bool:
        """Check if this ADC configuration is valid."""
        # Check derived params are reasonable
        if self._n_extra < 0:
            return False

        # Check child blocks are valid
        if not self._cdac_p.is_valid() or not self._cdac_n.is_valid():
            return False
        if not self.comp.is_valid():
            return False

        return True

    def schematic(self, io, cell: CellBuilder):
        """Generate ADC schematic."""
        if not self.is_valid():
            raise ValueError(f"Invalid ADC configuration: {self}")

        # Internal signals
        vdac_p = cell.signal("vdac_p")  # CDAC+ output / comp input
        vdac_n = cell.signal("vdac_n")  # CDAC- output / comp input
        comp_p = cell.signal("comp_p")  # Comparator output+
        comp_n = cell.signal("comp_n")  # Comparator output-
        clk_update_b = cell.signal("clk_update_b")  # Inverted update clock

        # DAC state signals (from salogic to CDACs)
        dac_state_p = [cell.signal(f"dac_state_p_{i}") for i in range(self._num_caps)]
        dac_state_n = [cell.signal(f"dac_state_n_{i}") for i in range(self._num_caps)]

        # =========================================================================
        # Clock inverter
        # =========================================================================
        self._build_clock_inverter(io, cell, clk_update_b)

        # =========================================================================
        # SAR Logic (digital controller)
        # =========================================================================
        self._build_salogic(io, cell, comp_p, comp_n, dac_state_p, dac_state_n)

        # =========================================================================
        # CDACs (capacitor DACs)
        # =========================================================================
        self._build_cdac(io, cell, "p", vdac_p, dac_state_p, self._cdac_p)
        self._build_cdac(io, cell, "n", vdac_n, dac_state_n, self._cdac_n)

        # =========================================================================
        # Sampling switches
        # =========================================================================
        self._build_sampler(io, cell, "p", vdac_p, self.samp_p)
        self._build_sampler(io, cell, "n", vdac_n, self.samp_n)

        # =========================================================================
        # Comparator
        # =========================================================================
        self._build_comparator(io, cell, vdac_p, vdac_n, comp_p, comp_n, clk_update_b)

    def _build_clock_inverter(self, io, cell, clk_update_b):
        """Build clock inverter for generating clk_update_b."""
        inv = cell.instantiate(self.inv, name="Xinv_clk")
        cell.connect(io.clk_update, inv.io.din)
        cell.connect(clk_update_b, inv.io.dout)
        cell.connect(io.vdd_d, inv.io.vdd)
        cell.connect(io.vss_d, inv.io.vss)

    def _build_salogic(self, io, cell, comp_p, comp_n, dac_state_p, dac_state_n):
        """Build SAR logic controller."""
        # Build pin mapping for salogic
        salogic_pins = {
            "clk_init": io.clk_init,
            "clk_update": io.clk_update,
            "dac_mode": io.dac_mode,
            "comp_p": comp_p,
            "comp_n": comp_n,
            "vdd_d": io.vdd_d,
            "vss_d": io.vss_d,
        }

        # Input state buses (from external controller)
        for i in range(self._num_caps):
            salogic_pins[f"dac_astate_p[{i}]"] = io.dac_astate_p[i]
            salogic_pins[f"dac_astate_n[{i}]"] = io.dac_astate_n[i]
            salogic_pins[f"dac_bstate_p[{i}]"] = io.dac_bstate_p[i]
            salogic_pins[f"dac_bstate_n[{i}]"] = io.dac_bstate_n[i]

        # Output state buses (to CDACs)
        for i in range(self._num_caps):
            salogic_pins[f"dac_state_p[{i}]"] = dac_state_p[i]
            salogic_pins[f"dac_state_n[{i}]"] = dac_state_n[i]

        cell.instantiate(
            ExternalCell("salogic", library="digital", params={"n_bits": self._num_caps}),
            name="Xsalogic",
            **salogic_pins
        )

    def _build_cdac(self, io, cell, side: str, vdac, dac_state: list, cdac: Cdac):
        """Build CDAC for one side (p or n)."""
        cdac_pins = {
            "top": vdac,
            "vdd": io.vdd_a,
            "vss": io.vss_a,
        }
        for i in range(self._num_caps):
            cdac_pins[f"dac[{i}]"] = dac_state[i]

        cell.instantiate(cdac, name=f"Xcdac_{side}", **cdac_pins)

    def _build_sampler(self, io, cell, side: str, vdac, samp: Samp):
        """Build sampling switch for one side (p or n)."""
        vin = io.vinp if side == "p" else io.vinn

        samp_inst = cell.instantiate(samp, name=f"Xsamp_{side}")
        cell.connect(vin, samp_inst.io.din)
        cell.connect(vdac, samp_inst.io.dout)
        cell.connect(io.clk_samp, samp_inst.io.clk)
        cell.connect(io.clk_samp_b, samp_inst.io.clk_b)
        cell.connect(io.vdd_a, samp_inst.io.vdd)
        cell.connect(io.vss_a, samp_inst.io.vss)

    def _build_comparator(self, io, cell, vdac_p, vdac_n, comp_p, comp_n, clk_update_b):
        """Build comparator."""
        comp_inst = cell.instantiate(self.comp, name="Xcomp")
        cell.connect(vdac_p, comp_inst.io.inp)
        cell.connect(vdac_n, comp_inst.io.inn)
        cell.connect(comp_p, comp_inst.io.outp)
        cell.connect(comp_n, comp_inst.io.outn)
        cell.connect(io.clk_update, comp_inst.io.clk)
        cell.connect(clk_update_b, comp_inst.io.clkb)
        cell.connect(io.vdd_a, comp_inst.io.vdd)
        cell.connect(io.vss_a, comp_inst.io.vss)


# =============================================================================
# Variant Generation
# =============================================================================

def generate_all_variants() -> list[Adc]:
    """Generate all valid ADC topology combinations."""
    variants = []

    # Top-level topology sweep
    for n_cycles in [8, 12, 14, 16, 18, 20]:
        for n_adc in [8, 12, 14]:
            if n_cycles < n_adc:
                continue  # Invalid: need at least n_adc cycles

            # CDAC configuration sweep
            for redun_strat in RedunStrat:
                for split_strat in SplitStrat:
                    # Comp configuration sweep (simplified - just key variants)
                    for comp_stages in CompStages:
                        for preamp_bias in PreampBias:
                            try:
                                adc = Adc(
                                    n_cycles=n_cycles,
                                    n_adc=n_adc,
                                    cdac_config=CdacConfig(
                                        redun_strat=redun_strat,
                                        split_strat=split_strat,
                                    ),
                                    comp=Comp(
                                        preamp_diffpair=PreampDiffpair.NMOS_INPUT,
                                        preamp_bias=preamp_bias,
                                        comp_stages=comp_stages,
                                        latch_pwrgate_ctl=LatchPwrgateCtl.CLOCKED,
                                        latch_pwrgate_node=LatchPwrgateNode.EXTERNAL,
                                        latch_rst_extern_ctl=LatchRstExternCtl.CLOCKED,
                                        latch_rst_intern_ctl=LatchRstInternCtl.CLOCKED,
                                    ),
                                )
                                if adc.is_valid():
                                    variants.append(adc)
                            except ValueError:
                                pass  # Invalid combination

    return variants


def generate_quick_variants() -> list[Adc]:
    """Generate a smaller set of representative variants for quick testing."""
    variants = []

    for n_cycles, n_adc in [(8, 8), (12, 10), (14, 12)]:
        for redun_strat in [RedunStrat.RDX2, RedunStrat.SUBRDX2_LIM]:
            try:
                adc = Adc(
                    n_cycles=n_cycles,
                    n_adc=n_adc,
                    cdac_config=CdacConfig(redun_strat=redun_strat),
                )
                if adc.is_valid():
                    variants.append(adc)
            except ValueError:
                pass

    return variants


# =============================================================================
# Testbench
# =============================================================================

@dataclass
class AdcTb:
    """
    ADC testbench - runs 2 complete conversions at 10 Msps.

    Timing: 10ns settling + 2x 100ns conversions = 210ns total
    """
    pvt: Pvt
    dut: Adc

    def schematic(self, io, cell: CellBuilder):
        # Power supplies
        vdd_a = cell.signal("vdd_a")
        vss_a = cell.signal("vss_a")
        vdd_d = cell.signal("vdd_d")
        vss_d = cell.signal("vss_d")

        cell.instantiate(Vsource.dc(self.pvt.voltage), name="Vvdd_a", p=vdd_a, n=io.vss)
        cell.instantiate(Vsource.dc(0), name="Vvss_a", p=vss_a, n=io.vss)
        cell.instantiate(Vsource.dc(self.pvt.voltage), name="Vvdd_d", p=vdd_d, n=io.vss)
        cell.instantiate(Vsource.dc(0), name="Vvss_d", p=vss_d, n=io.vss)

        # Differential input signals - ramping voltages
        vinp = cell.signal("vinp")
        vinn = cell.signal("vinn")

        # Ramp from ~0.9V to ~0.85V (normalized to supply)
        cell.instantiate(
            Vsource.pwl([(0, 0.917 * self.pvt.voltage), (210e-9, 0.875 * self.pvt.voltage)]),
            name="Vvinp", p=vinp, n=io.vss
        )
        # Ramp from ~0.65V to ~0.7V
        cell.instantiate(
            Vsource.pwl([(0, 0.667 * self.pvt.voltage), (210e-9, 0.708 * self.pvt.voltage)]),
            name="Vvinn", p=vinn, n=io.vss
        )

        # Clock and control signals
        clk_init = cell.signal("clk_init")
        clk_update = cell.signal("clk_update")
        clk_samp = cell.signal("clk_samp")
        clk_samp_b = cell.signal("clk_samp_b")
        dac_mode = cell.signal("dac_mode")

        # Sequencer timing (see blocks/adc.py for timing details)
        cell.instantiate(
            Vsource.pulse(0, self.pvt.voltage, delay=10e-9, width=4.8e-9, period=100e-9),
            name="Vclk_init", p=clk_init, n=io.vss
        )
        cell.instantiate(
            Vsource.pulse(0, self.pvt.voltage, delay=27.5e-9, width=2.4e-9, period=5e-9),
            name="Vclk_update", p=clk_update, n=io.vss
        )
        cell.instantiate(
            Vsource.pulse(0, self.pvt.voltage, delay=15e-9, width=9.8e-9, period=100e-9),
            name="Vclk_samp", p=clk_samp, n=io.vss
        )
        cell.instantiate(
            Vsource.pulse(self.pvt.voltage, 0, delay=15e-9, width=9.8e-9, period=100e-9),
            name="Vclk_samp_b", p=clk_samp_b, n=io.vss
        )
        cell.instantiate(
            Vsource.dc(self.pvt.voltage),  # SAR mode
            name="Vdac_mode", p=dac_mode, n=io.vss
        )

        # DAC state buses - all tied high for normal SAR operation
        dac_astate_p = [cell.signal(f"dac_astate_p_{i}") for i in range(self.dut.num_caps)]
        dac_astate_n = [cell.signal(f"dac_astate_n_{i}") for i in range(self.dut.num_caps)]
        dac_bstate_p = [cell.signal(f"dac_bstate_p_{i}") for i in range(self.dut.num_caps)]
        dac_bstate_n = [cell.signal(f"dac_bstate_n_{i}") for i in range(self.dut.num_caps)]

        for i in range(self.dut.num_caps):
            cell.instantiate(Vsource.dc(self.pvt.voltage), name=f"Vastate_p_{i}",
                            p=dac_astate_p[i], n=io.vss)
            cell.instantiate(Vsource.dc(self.pvt.voltage), name=f"Vastate_n_{i}",
                            p=dac_astate_n[i], n=io.vss)
            cell.instantiate(Vsource.dc(self.pvt.voltage), name=f"Vbstate_p_{i}",
                            p=dac_bstate_p[i], n=io.vss)
            cell.instantiate(Vsource.dc(self.pvt.voltage), name=f"Vbstate_n_{i}",
                            p=dac_bstate_n[i], n=io.vss)

        # Build DUT pin mapping
        dut_pins = {
            "clk_init": clk_init,
            "clk_update": clk_update,
            "clk_samp": clk_samp,
            "clk_samp_b": clk_samp_b,
            "dac_mode": dac_mode,
            "vinp": vinp,
            "vinn": vinn,
            "vdd_a": vdd_a,
            "vss_a": vss_a,
            "vdd_d": vdd_d,
            "vss_d": vss_d,
        }

        for i in range(self.dut.num_caps):
            dut_pins[f"dac_astate_p[{i}]"] = dac_astate_p[i]
            dut_pins[f"dac_astate_n[{i}]"] = dac_astate_n[i]
            dut_pins[f"dac_bstate_p[{i}]"] = dac_bstate_p[i]
            dut_pins[f"dac_bstate_n[{i}]"] = dac_bstate_n[i]

        cell.instantiate(self.dut, name="Xadc", **dut_pins)

        return vinp, vinn  # probe nodes


# =============================================================================
# Analyses & Measures
# =============================================================================

analyses = {
    "tran": {"stop": 210e-9, "step": 0.1e-9},
}

measures = {
    "inl_max_lsb": lambda out, n_adc: out.adc_inl_max("vinp", "vinn", "comp_p", n_adc),
    "dnl_max_lsb": lambda out, n_adc: out.adc_dnl_max("vinp", "vinn", "comp_p", n_adc),
    "enob": lambda out, n_adc: out.adc_enob("vinp", "vinn", "comp_p", n_adc),
    "power_uW": lambda out: out.avg_power("vdd_a", "vdd_d"),
}


# =============================================================================
# Usage Examples
# =============================================================================

def example_basic():
    """Basic 8-bit ADC with defaults."""
    return Adc(n_cycles=8, n_adc=8)


def example_12bit_redundant():
    """12-bit ADC with sub-radix-2 redundancy and voltage divider split."""
    return Adc(
        n_cycles=14,
        n_adc=12,
        cdac_config=CdacConfig(
            redun_strat=RedunStrat.SUBRDX2_LIM,
            split_strat=SplitStrat.VDIV_SPLIT,
            cap_type=CapType.MOM2,
        ),
    )


def example_high_speed():
    """High-speed ADC with optimized comparator and TGATE samplers."""
    return Adc(
        n_cycles=8,
        n_adc=8,
        samp_p=Samp(SwitchType.TGATE, w=10, l=1, vth=Vth.LVT),
        samp_n=Samp(SwitchType.TGATE, w=10, l=1, vth=Vth.LVT),
        comp=Comp(
            preamp_diffpair=PreampDiffpair.NMOS_INPUT,
            preamp_bias=PreampBias.DYN_BIAS,
            comp_stages=CompStages.SINGLE_STAGE,
            latch_pwrgate_ctl=LatchPwrgateCtl.CLOCKED,
            latch_pwrgate_node=LatchPwrgateNode.EXTERNAL,
            latch_rst_extern_ctl=LatchRstExternCtl.CLOCKED,
            latch_rst_intern_ctl=LatchRstInternCtl.CLOCKED,
            diffpair_w=8,
            diffpair_vth=Vth.LVT,
            tail_vth=Vth.LVT,
            latch_vth=Vth.LVT,
        ),
    )


def example_low_power():
    """Low-power ADC with SVT devices and NMOS-only samplers."""
    return Adc(
        n_cycles=10,
        n_adc=10,
        samp_p=Samp(SwitchType.NMOS, w=2, l=1, vth=Vth.SVT),
        samp_n=Samp(SwitchType.NMOS, w=2, l=1, vth=Vth.SVT),
        comp=Comp(
            preamp_diffpair=PreampDiffpair.NMOS_INPUT,
            preamp_bias=PreampBias.STD_BIAS,
            comp_stages=CompStages.DOUBLE_STAGE,
            latch_pwrgate_ctl=LatchPwrgateCtl.SIGNALLED,
            latch_pwrgate_node=LatchPwrgateNode.INTERNAL,
            latch_rst_extern_ctl=LatchRstExternCtl.NO_RESET,
            latch_rst_intern_ctl=LatchRstInternCtl.SIGNALLED,
            diffpair_w=2,
            diffpair_vth=Vth.SVT,
            tail_vth=Vth.SVT,
            rst_vth=Vth.SVT,
            latch_vth=Vth.SVT,
        ),
        cdac_config=CdacConfig(
            redun_strat=RedunStrat.RDX2,
            vth=Vth.SVT,
        ),
    )


def example_asymmetric_cdac():
    """ADC with different CDAC configurations for + and - sides."""
    return Adc(
        n_cycles=12,
        n_adc=10,
        cdac_config=CdacConfig(
            redun_strat=RedunStrat.SUBRDX2_LIM,
            split_strat=SplitStrat.DIFFCAP_SPLIT,
        ),
        cdac_n_config=CdacConfig(
            redun_strat=RedunStrat.SUBRDX2_LIM,
            split_strat=SplitStrat.NO_SPLIT,  # Different strategy for - side
        ),
    )
