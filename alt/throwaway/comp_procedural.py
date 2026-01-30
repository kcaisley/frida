"""
Comparator block definition (procedural Substrate-style).

Translates blocks/comp.py to the procedural style.
Key challenges:
  - 7 topology parameters with complex validity rules
  - NMOS/PMOS input swapping logic
  - Fixed ports, variable internal topology
"""

from flow import block, Io, Input, Output, InOut, CellBuilder, TestbenchIo, Pvt
from flow.pdk import Nfet, Pfet, Cap, Res, Vsource
from flow.sources import PwlStep  # Helper for stepped waveforms
from dataclasses import dataclass
from enum import Enum
from typing import Optional


# =============================================================================
# IO (fixed - doesn't change with topology)
# =============================================================================

class CompIo(Io):
    inp = Input()      # in+ renamed for Spectre/Verilog compatibility
    inn = Input()      # in-
    outp = Output()    # out+
    outn = Output()    # out-
    clk = Input()
    clkb = Input()
    vdd = InOut()
    vss = InOut()


# =============================================================================
# Topology Parameters
# =============================================================================

class PreampDiffpair(Enum):
    NMOS_INPUT = "nmosinput"
    PMOS_INPUT = "pmosinput"


class PreampBias(Enum):
    STD_BIAS = "stdbias"
    DYN_BIAS = "dynbias"


class CompStages(Enum):
    SINGLE_STAGE = "singlestage"
    DOUBLE_STAGE = "doublestage"


class LatchPwrgateCtl(Enum):
    CLOCKED = "clocked"
    SIGNALLED = "signalled"


class LatchPwrgateNode(Enum):
    EXTERNAL = "external"
    INTERNAL = "internal"


class LatchRstExternCtl(Enum):
    CLOCKED = "clocked"
    SIGNALLED = "signalled"
    NO_RESET = "noreset"


class LatchRstInternCtl(Enum):
    CLOCKED = "clocked"
    SIGNALLED = "signalled"


class Vth(Enum):
    LVT = "lvt"
    SVT = "svt"


# =============================================================================
# Block
# =============================================================================

@block(io=CompIo)
@dataclass
class Comp:
    # Topology parameters
    preamp_diffpair: PreampDiffpair
    preamp_bias: PreampBias
    comp_stages: CompStages
    latch_pwrgate_ctl: LatchPwrgateCtl
    latch_pwrgate_node: LatchPwrgateNode
    latch_rst_extern_ctl: LatchRstExternCtl
    latch_rst_intern_ctl: LatchRstInternCtl

    # Device parameters - each group can have independent Vth
    diffpair_w: int = 4
    diffpair_vth: Vth = Vth.LVT      # Input pair: often LVT for speed

    tail_w: int = 2
    tail_l: int = 2
    tail_vth: Vth = Vth.SVT          # Tail: often SVT for lower leakage

    rst_w: int = 2
    rst_vth: Vth = Vth.LVT           # Reset switches

    latch_w: int = 2
    latch_vth: Vth = Vth.LVT         # Latch devices

    def is_valid(self) -> bool:
        """Check if this topology combination is valid."""
        if self.comp_stages == CompStages.SINGLE_STAGE:
            # For single stage, latch params don't matter - only generate canonical combo
            return (
                self.latch_pwrgate_ctl == LatchPwrgateCtl.CLOCKED and
                self.latch_pwrgate_node == LatchPwrgateNode.EXTERNAL and
                self.latch_rst_extern_ctl == LatchRstExternCtl.CLOCKED and
                self.latch_rst_intern_ctl == LatchRstInternCtl.CLOCKED
            )
        else:  # DOUBLE_STAGE
            # External reset only valid if powergate is external
            if self.latch_pwrgate_node == LatchPwrgateNode.INTERNAL:
                return self.latch_rst_extern_ctl == LatchRstExternCtl.NO_RESET
            return True

    def schematic(self, io, cell: CellBuilder):
        """
        Generate comparator schematic.

        Strategy: Build assuming NMOS input, then swap if PMOS input.
        This keeps the logic cleaner than duplicating everything.
        """
        if not self.is_valid():
            raise ValueError(f"Invalid topology combination: {self}")

        # Internal signals
        tail = cell.signal("tail")
        outp_int = cell.signal("outp_int")  # Internal output before any buffering
        outn_int = cell.signal("outn_int")

        # Will be swapped if PMOS input
        rail_top = io.vdd
        rail_bot = io.vss
        clk_on = io.clk      # Clock that turns things ON
        clk_off = io.clkb    # Clock that turns things OFF

        # Build circuit assuming NMOS input diff pair
        self._build_preamp(io, cell, tail, outp_int, outn_int, rail_top, rail_bot, clk_on, clk_off)
        self._build_latch(io, cell, outp_int, outn_int, rail_top, rail_bot, clk_on, clk_off)

    def _build_preamp(self, io, cell, tail, outp_int, outn_int, rail_top, rail_bot, clk_on, clk_off):
        """Build input differential pair and load devices."""
        # Differential pair (NMOS for NMOS_INPUT, will be swapped later for PMOS_INPUT)
        is_nmos_input = self.preamp_diffpair == PreampDiffpair.NMOS_INPUT
        FetDiff = Nfet if is_nmos_input else Pfet
        FetLoad = Pfet if is_nmos_input else Nfet
        diff_rail = rail_bot if is_nmos_input else rail_top
        load_rail = rail_top if is_nmos_input else rail_bot

        # Diff pair - uses diffpair_vth
        mdiff_p = cell.instantiate(FetDiff(self.diffpair_w, 1, self.diffpair_vth), name="M_preamp_diff_p")
        mdiff_n = cell.instantiate(FetDiff(self.diffpair_w, 1, self.diffpair_vth), name="M_preamp_diff_n")
        cell.connect(outn_int, mdiff_p.d)  # Cross-coupled: in+ drives out-
        cell.connect(io.inp, mdiff_p.g)
        cell.connect(tail, mdiff_p.s)
        cell.connect(diff_rail, mdiff_p.b)

        cell.connect(outp_int, mdiff_n.d)
        cell.connect(io.inn, mdiff_n.g)
        cell.connect(tail, mdiff_n.s)
        cell.connect(diff_rail, mdiff_n.b)

        # Tail current source - uses tail_vth
        if self.preamp_bias == PreampBias.STD_BIAS:
            mtail = cell.instantiate(FetDiff(self.tail_w, self.tail_l, self.tail_vth), name="M_preamp_tail")
            cell.connect(tail, mtail.d)
            cell.connect(clk_on if is_nmos_input else clk_off, mtail.g)
            cell.connect(diff_rail, mtail.s)
            cell.connect(diff_rail, mtail.b)

        elif self.preamp_bias == PreampBias.DYN_BIAS:
            # Dynamic biasing with capacitor
            vcap = cell.signal("vcap")
            mtail = cell.instantiate(FetDiff(self.tail_w, self.tail_l, self.tail_vth), name="M_preamp_tail")
            cell.connect(tail, mtail.d)
            cell.connect(clk_on if is_nmos_input else clk_off, mtail.g)
            cell.connect(vcap, mtail.s)
            cell.connect(diff_rail, mtail.b)

            mbias = cell.instantiate(FetDiff(self.tail_w, self.tail_l, self.tail_vth), name="M_preamp_bias")
            cell.connect(vcap, mbias.d)
            cell.connect(clk_on if is_nmos_input else clk_off, mbias.g)
            cell.connect(diff_rail, mbias.s)
            cell.connect(diff_rail, mbias.b)

            cbias = cell.instantiate(Cap(1e-15), name="C_preamp_bias")
            cell.connect(vcap, cbias.p)
            cell.connect(load_rail, cbias.n)

        # Load/reset devices - uses rst_vth
        mrst_p = cell.instantiate(FetLoad(self.rst_w, 1, self.rst_vth), name="M_preamp_rst_p")
        mrst_n = cell.instantiate(FetLoad(self.rst_w, 1, self.rst_vth), name="M_preamp_rst_n")
        cell.connect(outn_int, mrst_p.d)
        cell.connect(clk_off if is_nmos_input else clk_on, mrst_p.g)
        cell.connect(load_rail, mrst_p.s)
        cell.connect(load_rail, mrst_p.b)

        cell.connect(outp_int, mrst_n.d)
        cell.connect(clk_off if is_nmos_input else clk_on, mrst_n.g)
        cell.connect(load_rail, mrst_n.s)
        cell.connect(load_rail, mrst_n.b)

    def _build_latch(self, io, cell, outp_int, outn_int, rail_top, rail_bot, clk_on, clk_off):
        """Build latch stage (single or double stage)."""
        if self.comp_stages == CompStages.SINGLE_STAGE:
            self._build_single_stage_latch(io, cell, outp_int, outn_int, rail_top, rail_bot, clk_on, clk_off)
        else:
            self._build_double_stage_latch(io, cell, outp_int, outn_int, rail_top, rail_bot, clk_on, clk_off)

    def _build_single_stage_latch(self, io, cell, outp_int, outn_int, rail_top, rail_bot, clk_on, clk_off):
        """Strong-arm style: cross-coupled latch directly on preamp outputs."""
        is_nmos_input = self.preamp_diffpair == PreampDiffpair.NMOS_INPUT

        # In single-stage, preamp outputs ARE the final outputs
        cell.connect(io.outp, outp_int)
        cell.connect(io.outn, outn_int)

        # Cross-coupled PMOS (for NMOS input; swapped for PMOS input)
        FetTop = Pfet if is_nmos_input else Nfet
        FetBot = Nfet if is_nmos_input else Pfet
        top_rail = rail_top if is_nmos_input else rail_bot
        bot_rail = rail_bot if is_nmos_input else rail_top

        ma_p = cell.instantiate(FetTop(self.latch_w, 1, self.latch_vth), name="Ma_latch_p")
        ma_n = cell.instantiate(FetTop(self.latch_w, 1, self.latch_vth), name="Ma_latch_n")
        cell.connect(io.outn, ma_p.d)
        cell.connect(io.outp, ma_p.g)
        cell.connect(top_rail, ma_p.s)
        cell.connect(top_rail, ma_p.b)

        cell.connect(io.outp, ma_n.d)
        cell.connect(io.outn, ma_n.g)
        cell.connect(top_rail, ma_n.s)
        cell.connect(top_rail, ma_n.b)

        # Cross-coupled NMOS
        mb_p = cell.instantiate(FetBot(self.latch_w, 1, self.latch_vth), name="Mb_latch_p")
        mb_n = cell.instantiate(FetBot(self.latch_w, 1, self.latch_vth), name="Mb_latch_n")
        cell.connect(io.outn, mb_p.d)
        cell.connect(io.outp, mb_p.g)
        cell.connect(bot_rail, mb_p.s)
        cell.connect(bot_rail, mb_p.b)

        cell.connect(io.outp, mb_n.d)
        cell.connect(io.outn, mb_n.g)
        cell.connect(bot_rail, mb_n.s)
        cell.connect(bot_rail, mb_n.b)

        # Clocked reset
        mrst_p = cell.instantiate(FetTop(self.latch_w, 1, self.latch_vth), name="M_latch_int_rst_p")
        mrst_n = cell.instantiate(FetTop(self.latch_w, 1, self.latch_vth), name="M_latch_int_rst_n")
        cell.connect(io.outn, mrst_p.d)
        cell.connect(clk_off, mrst_p.g)
        cell.connect(top_rail, mrst_p.s)
        cell.connect(top_rail, mrst_p.b)

        cell.connect(io.outp, mrst_n.d)
        cell.connect(clk_off, mrst_n.g)
        cell.connect(top_rail, mrst_n.s)
        cell.connect(top_rail, mrst_n.b)

    def _build_double_stage_latch(self, io, cell, outp_int, outn_int, rail_top, rail_bot, clk_on, clk_off):
        """Two-stage: preamp feeds separate latch with output buffers."""
        is_nmos_input = self.preamp_diffpair == PreampDiffpair.NMOS_INPUT

        FetTop = Pfet if is_nmos_input else Nfet
        FetBot = Nfet if is_nmos_input else Pfet
        top_rail = rail_top if is_nmos_input else rail_bot
        bot_rail = rail_bot if is_nmos_input else rail_top

        # Internal latch nodes
        latch_p = cell.signal("latch_p")
        latch_n = cell.signal("latch_n")
        latch_vdd = cell.signal("latch_vdd")
        latch_vss = cell.signal("latch_vss")

        # Core cross-coupled latch - uses latch_vth
        ma_p = cell.instantiate(FetTop(self.latch_w, 1, self.latch_vth), name="Ma_latch_p")
        ma_n = cell.instantiate(FetTop(self.latch_w, 1, self.latch_vth), name="Ma_latch_n")
        cell.connect(latch_n, ma_p.d)
        cell.connect(latch_p, ma_p.g)
        cell.connect(latch_vdd, ma_p.s)
        cell.connect(top_rail, ma_p.b)

        cell.connect(latch_p, ma_n.d)
        cell.connect(latch_n, ma_n.g)
        cell.connect(latch_vdd, ma_n.s)
        cell.connect(top_rail, ma_n.b)

        mb_p = cell.instantiate(FetBot(self.latch_w, 1, self.latch_vth), name="Mb_latch_p")
        mb_n = cell.instantiate(FetBot(self.latch_w, 1, self.latch_vth), name="Mb_latch_n")
        cell.connect(latch_n, mb_p.d)
        cell.connect(latch_p, mb_p.g)
        cell.connect(latch_vss, mb_p.s)
        cell.connect(bot_rail, mb_p.b)

        cell.connect(latch_p, mb_n.d)
        cell.connect(latch_n, mb_n.g)
        cell.connect(latch_vss, mb_n.s)
        cell.connect(bot_rail, mb_n.b)

        # Preamp to latch connection
        m_conn_p = cell.instantiate(FetBot(self.latch_w, 1, self.latch_vth), name="M_preamp_to_latch_p")
        m_conn_n = cell.instantiate(FetBot(self.latch_w, 1, self.latch_vth), name="M_preamp_to_latch_n")
        cell.connect(latch_n, m_conn_p.d)
        cell.connect(outn_int, m_conn_p.g)
        cell.connect(bot_rail, m_conn_p.s)
        cell.connect(bot_rail, m_conn_p.b)

        cell.connect(latch_p, m_conn_n.d)
        cell.connect(outp_int, m_conn_n.g)
        cell.connect(bot_rail, m_conn_n.s)
        cell.connect(bot_rail, m_conn_n.b)

        # Powergate configuration
        self._build_powergate(cell, latch_vdd, latch_vss, latch_p, latch_n,
                              top_rail, bot_rail, clk_on, clk_off, is_nmos_input)

        # Internal reset
        self._build_internal_reset(cell, latch_p, latch_n, latch_vss,
                                   bot_rail, clk_on, clk_off, is_nmos_input)

        # Output buffers
        self._build_output_buffers(io, cell, latch_p, latch_n, top_rail, bot_rail, is_nmos_input)

    def _build_powergate(self, cell, latch_vdd, latch_vss, latch_p, latch_n,
                         top_rail, bot_rail, clk_on, clk_off, is_nmos_input):
        """Build powergate based on configuration."""
        FetTop = Pfet if is_nmos_input else Nfet
        FetBot = Nfet if is_nmos_input else Pfet

        if self.latch_pwrgate_node == LatchPwrgateNode.EXTERNAL:
            # Powergate at supply side
            gate_sig = clk_off if self.latch_pwrgate_ctl == LatchPwrgateCtl.CLOCKED else latch_n
            gate_sig2 = clk_off if self.latch_pwrgate_ctl == LatchPwrgateCtl.CLOCKED else latch_p

            mpg_p = cell.instantiate(FetTop(self.latch_w, 1, self.latch_vth), name="M_latch_ext_pg_p")
            mpg_n = cell.instantiate(FetTop(self.latch_w, 1, self.latch_vth), name="M_latch_ext_pg_n")
            cell.connect(latch_vdd, mpg_p.d)
            cell.connect(gate_sig, mpg_p.g)
            cell.connect(top_rail, mpg_p.s)
            cell.connect(top_rail, mpg_p.b)

            cell.connect(latch_vdd, mpg_n.d)
            cell.connect(gate_sig2, mpg_n.g)
            cell.connect(top_rail, mpg_n.s)
            cell.connect(top_rail, mpg_n.b)

            # External reset (if enabled)
            if self.latch_rst_extern_ctl != LatchRstExternCtl.NO_RESET:
                rst_gate = clk_off if self.latch_rst_extern_ctl == LatchRstExternCtl.CLOCKED else latch_n
                rst_gate2 = clk_off if self.latch_rst_extern_ctl == LatchRstExternCtl.CLOCKED else latch_p

                mrst_p = cell.instantiate(FetTop(self.latch_w, 1, self.latch_vth), name="M_latch_ext_rst_p")
                mrst_n = cell.instantiate(FetTop(self.latch_w, 1, self.latch_vth), name="M_latch_ext_rst_n")
                cell.connect(latch_n, mrst_p.d)
                cell.connect(rst_gate, mrst_p.g)
                cell.connect(latch_vdd, mrst_p.s)
                cell.connect(top_rail, mrst_p.b)

                cell.connect(latch_p, mrst_n.d)
                cell.connect(rst_gate2, mrst_n.g)
                cell.connect(latch_vdd, mrst_n.s)
                cell.connect(top_rail, mrst_n.b)

            # Direct VSS connection
            mvss_p = cell.instantiate(FetBot(self.latch_w, 1, self.latch_vth), name="M_latch_vss_conn_p")
            mvss_n = cell.instantiate(FetBot(self.latch_w, 1, self.latch_vth), name="M_latch_vss_conn_n")
            cell.connect(latch_vss, mvss_p.d)
            cell.connect(top_rail, mvss_p.g)  # Always on
            cell.connect(bot_rail, mvss_p.s)
            cell.connect(bot_rail, mvss_p.b)

            cell.connect(latch_vss, mvss_n.d)
            cell.connect(top_rail, mvss_n.g)
            cell.connect(bot_rail, mvss_n.s)
            cell.connect(bot_rail, mvss_n.b)

        else:  # INTERNAL powergate
            # Direct VDD connection
            mvdd_p = cell.instantiate(FetTop(self.latch_w, 1, self.latch_vth), name="M_latch_vdd_conn_p")
            mvdd_n = cell.instantiate(FetTop(self.latch_w, 1, self.latch_vth), name="M_latch_vdd_conn_n")
            cell.connect(latch_vdd, mvdd_p.d)
            cell.connect(bot_rail, mvdd_p.g)  # Always on
            cell.connect(top_rail, mvdd_p.s)
            cell.connect(top_rail, mvdd_p.b)

            cell.connect(latch_vdd, mvdd_n.d)
            cell.connect(bot_rail, mvdd_n.g)
            cell.connect(top_rail, mvdd_n.s)
            cell.connect(top_rail, mvdd_n.b)

            # Powergate at VSS side
            if self.latch_pwrgate_ctl == LatchPwrgateCtl.CLOCKED:
                mpg = cell.instantiate(FetBot(self.latch_w, 1, self.latch_vth), name="M_latch_int_pg")
                cell.connect(latch_vss, mpg.d)
                cell.connect(clk_on, mpg.g)
                cell.connect(bot_rail, mpg.s)
                cell.connect(bot_rail, mpg.b)
            else:  # SIGNALLED
                latch_vss_p = cell.signal("latch_vss_p")
                latch_vss_n = cell.signal("latch_vss_n")

                mpg_p = cell.instantiate(FetBot(self.latch_w, 1, self.latch_vth), name="M_latch_int_pg_p")
                mpg_n = cell.instantiate(FetBot(self.latch_w, 1, self.latch_vth), name="M_latch_int_pg_n")
                cell.connect(latch_vss_p, mpg_p.d)
                cell.connect(latch_p, mpg_p.g)
                cell.connect(bot_rail, mpg_p.s)
                cell.connect(bot_rail, mpg_p.b)

                cell.connect(latch_vss_n, mpg_n.d)
                cell.connect(latch_n, mpg_n.g)
                cell.connect(bot_rail, mpg_n.s)
                cell.connect(bot_rail, mpg_n.b)

    def _build_internal_reset(self, cell, latch_p, latch_n, latch_vss,
                               bot_rail, clk_on, clk_off, is_nmos_input):
        """Build internal reset devices."""
        FetBot = Nfet if is_nmos_input else Pfet

        if self.latch_rst_intern_ctl == LatchRstInternCtl.CLOCKED:
            gate = clk_off
        else:  # SIGNALLED
            gate = latch_n  # Self-resetting

        mrst_p = cell.instantiate(FetBot(self.latch_w, 1, self.latch_vth), name="M_latch_int_rst_p")
        mrst_n = cell.instantiate(FetBot(self.latch_w, 1, self.latch_vth), name="M_latch_int_rst_n")
        cell.connect(latch_n, mrst_p.d)
        cell.connect(gate, mrst_p.g)
        cell.connect(latch_vss, mrst_p.s)
        cell.connect(bot_rail, mrst_p.b)

        gate2 = clk_off if self.latch_rst_intern_ctl == LatchRstInternCtl.CLOCKED else latch_p
        cell.connect(latch_p, mrst_n.d)
        cell.connect(gate2, mrst_n.g)
        cell.connect(latch_vss, mrst_n.s)
        cell.connect(bot_rail, mrst_n.b)

    def _build_output_buffers(self, io, cell, latch_p, latch_n, top_rail, bot_rail, is_nmos_input):
        """Build output buffer inverters."""
        FetTop = Pfet if is_nmos_input else Nfet
        FetBot = Nfet if is_nmos_input else Pfet

        # Buffer for outp (driven by latch_n)
        ma_out_p = cell.instantiate(FetTop(self.latch_w, 1, self.latch_vth), name="Ma_latch_out_p")
        mb_out_p = cell.instantiate(FetBot(self.latch_w, 1, self.latch_vth), name="Mb_latch_out_p")
        cell.connect(io.outn, ma_out_p.d)
        cell.connect(latch_n, ma_out_p.g)
        cell.connect(top_rail, ma_out_p.s)
        cell.connect(top_rail, ma_out_p.b)

        cell.connect(io.outn, mb_out_p.d)
        cell.connect(latch_n, mb_out_p.g)
        cell.connect(bot_rail, mb_out_p.s)
        cell.connect(bot_rail, mb_out_p.b)

        # Buffer for outn
        ma_out_n = cell.instantiate(FetTop(self.latch_w, 1, self.latch_vth), name="Ma_latch_out_n")
        mb_out_n = cell.instantiate(FetBot(self.latch_w, 1, self.latch_vth), name="Mb_latch_out_n")
        cell.connect(io.outp, ma_out_n.d)
        cell.connect(latch_p, ma_out_n.g)
        cell.connect(top_rail, ma_out_n.s)
        cell.connect(top_rail, ma_out_n.b)

        cell.connect(io.outp, mb_out_n.d)
        cell.connect(latch_p, mb_out_n.g)
        cell.connect(bot_rail, mb_out_n.s)
        cell.connect(bot_rail, mb_out_n.b)


# =============================================================================
# Variant Generation
# =============================================================================

def generate_all_variants() -> list[Comp]:
    """Generate all valid topology combinations."""
    variants = []
    for preamp_diffpair in PreampDiffpair:
        for preamp_bias in PreampBias:
            for comp_stages in CompStages:
                for latch_pwrgate_ctl in LatchPwrgateCtl:
                    for latch_pwrgate_node in LatchPwrgateNode:
                        for latch_rst_extern_ctl in LatchRstExternCtl:
                            for latch_rst_intern_ctl in LatchRstInternCtl:
                                for diffpair_w in [4, 8]:
                                    for tail_w in [2, 4]:
                                        for latch_w in [1, 2, 4]:
                                            comp = Comp(
                                                preamp_diffpair=preamp_diffpair,
                                                preamp_bias=preamp_bias,
                                                comp_stages=comp_stages,
                                                latch_pwrgate_ctl=latch_pwrgate_ctl,
                                                latch_pwrgate_node=latch_pwrgate_node,
                                                latch_rst_extern_ctl=latch_rst_extern_ctl,
                                                latch_rst_intern_ctl=latch_rst_intern_ctl,
                                                diffpair_w=diffpair_w,
                                                tail_w=tail_w,
                                                latch_w=latch_w,
                                            )
                                            if comp.is_valid():
                                                variants.append(comp)
    return variants


# =============================================================================
# Testbench
# =============================================================================

@block(io=TestbenchIo)
@dataclass
class CompTb:
    pvt: Pvt
    dut: Comp

    def schematic(self, io, cell: CellBuilder):
        vdd = cell.signal("vdd")
        vcm = cell.signal("vcm")
        inp = cell.signal("inp")
        inn = cell.signal("inn")
        outp = cell.signal("outp")
        outn = cell.signal("outn")
        clk = cell.signal("clk")
        clkb = cell.signal("clkb")
        vin_src = cell.signal("vin_src")
        vref_src = cell.signal("vref_src")

        # Power supplies
        cell.instantiate(Vsource.dc(self.pvt.voltage), p=vdd, n=io.vss)

        # Common-mode voltage: 5 levels from 0.3V to 0.7V
        # PwlStep generates the actual PWL points from step parameters
        cell.instantiate(Vsource.pwl(PwlStep(
            vstart=0.3, vstep=0.1, tstep=1100e-9, count=5, trise=0.1e-9
        )), p=vcm, n=io.vss)

        # Differential inputs: sweep -5mV to +5mV around CM
        cell.instantiate(Vsource.pwl(PwlStep(
            vstart=-0.005, vstop=0.005, tstep=100e-9, count=55, trise=0.1e-9
        )), p=vin_src, n=vcm)

        cell.instantiate(Vsource.pwl(PwlStep(
            vstart=0.005, vstop=-0.005, tstep=100e-9, count=55, trise=0.1e-9
        )), p=vref_src, n=vcm)

        # Source impedance
        cell.instantiate(Res(1000), p=vin_src, n=inp)
        cell.instantiate(Cap(100e-15), p=inp, n=io.vss)
        cell.instantiate(Res(1000), p=vref_src, n=inn)
        cell.instantiate(Cap(100e-15), p=inn, n=io.vss)

        # Clocks
        cell.instantiate(Vsource.pulse(0, self.pvt.voltage, period=10e-9, width=4e-9,
                                        delay=0.5e-9, rise=0.1e-9, fall=0.1e-9), p=clk, n=io.vss)
        cell.instantiate(Vsource.pulse(self.pvt.voltage, 0, period=10e-9, width=4e-9,
                                        delay=0.5e-9, rise=0.1e-9, fall=0.1e-9), p=clkb, n=io.vss)

        # Output loading
        cell.instantiate(Cap(10e-15), p=outp, n=io.vss)
        cell.instantiate(Cap(10e-15), p=outn, n=io.vss)

        # DUT
        cell.instantiate(self.dut,
                         inp=inp, inn=inn, outp=outp, outn=outn,
                         clk=clk, clkb=clkb, vdd=vdd, vss=io.vss)

        return outp, outn  # probe nodes


# =============================================================================
# Analyses & Measures
# =============================================================================

analyses = {
    "tran": {"stop": 5.5e-6, "step": 1e-10},
    "mc_tran": {"stop": 5.5e-6, "step": 1e-10, "monte_carlo": {"runs": 10, "seed": 12345, "vary": "mismatch"}},
}

measures = {
    "offset_mV": lambda out: out.comp_offset("inp", "inn", "outp", "outn"),
    "noise_sigma_mV": lambda out: out.comp_noise_sigma("inp", "inn", "outp", "outn"),
    "delay_ns": lambda out: out.comp_delay("clk", "outp", "outn"),
    "settling_ns": lambda out: out.settling_time("outp", "outn", tol=0.01),
    "overshoot_pct": lambda out: out.overshoot("outp", "outn"),
    "power_uW": lambda out: out.avg_power("vdd"),
    "slew_Vns": lambda out: out.slew_rate("outp"),
}
