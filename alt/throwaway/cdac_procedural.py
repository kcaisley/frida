"""
CDAC (Capacitor DAC) block definition (procedural Substrate-style).

Translates blocks/cdac.py to the procedural style.
Key challenges:
  - Variable port count based on n_dac parameter
  - Complex weight calculation algorithms
  - Different split strategies (nosplit, vdivsplit, diffcapsplit)
  - Driver sizing based on capacitor load
"""

from flow import block, Io, Input, Output, InOut, CellBuilder, TestbenchIo, Pvt
from flow import DynamicIo, Bus  # For variable-width ports
from flow.pdk import Nfet, Pfet, Cap, Res, Vsource
from flow.sources import PwlBits  # Helper for DAC bit pattern generation
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional
import math


# =============================================================================
# IO (dynamic - port count depends on n_dac)
# =============================================================================
# Unlike fixed IO, CDAC needs variable number of dac[i] ports.
# We use DynamicIo which generates ports at instantiation time.

def make_cdac_io(n_bits: int) -> type:
    """Factory to create CDAC IO class with n_bits dac ports."""
    class CdacIo(DynamicIo):
        top = InOut()
        vdd = InOut()
        vss = InOut()
        dac = Bus(Input(), width=n_bits)  # dac[0], dac[1], ..., dac[n_bits-1]
    return CdacIo


# =============================================================================
# Topology Parameters
# =============================================================================

class RedunStrat(Enum):
    RDX2 = "rdx2"              # Standard binary (2^n)
    SUBRDX2 = "subrdx2"        # Sub-radix-2 (radix = 2^(N/M))
    SUBRDX2_LIM = "subrdx2lim" # Sub-radix-2 with unit quantization
    SUBRDX2_RDST = "subrdx2rdst"  # Binary with MSB redistribution
    RDX2_RPT = "rdx2rpt"       # Binary with repeated capacitors


class SplitStrat(Enum):
    NO_SPLIT = "nosplit"           # All unit caps, m=weight
    VDIV_SPLIT = "vdivsplit"       # Voltage divider for fine bits
    DIFFCAP_SPLIT = "diffcapsplit" # Difference capacitor technique


class CapType(Enum):
    MOM1 = "cap_mom1"
    MOM2 = "cap_mom2"
    MOM3 = "cap_mom3"


class Vth(Enum):
    LVT = "lvt"
    SVT = "svt"


# =============================================================================
# Block
# =============================================================================

@dataclass
class Cdac:
    """
    Capacitor DAC with configurable resolution and architecture.

    Note: This block uses dynamic IO - the number of dac ports depends on n_dac.
    The @block decorator is applied dynamically in __post_init__.
    """
    # Topology parameters
    n_dac: int           # DAC resolution (7, 9, 11, 13)
    n_extra: int         # Extra caps for redundancy (0, 2, 4, 6)
    redun_strat: RedunStrat
    split_strat: SplitStrat

    # Device parameters
    cap_type: CapType = CapType.MOM1
    vth: Vth = Vth.LVT

    # Derived
    _weights: list[int] = field(default_factory=list, init=False, repr=False)
    _io_class: type = field(default=None, init=False, repr=False)

    def __post_init__(self):
        # Calculate weights and validate
        weights = Cdac._calc_weights(self.n_dac, self.n_extra, self.redun_strat)
        if weights is None:
            raise ValueError(f"Invalid combination: n_dac={self.n_dac}, n_extra={self.n_extra}, "
                           f"redun_strat={self.redun_strat}")
        self._weights = weights
        self._io_class = make_cdac_io(len(weights))

    @property
    def n_bits(self) -> int:
        return len(self._weights)

    # -------------------------------------------------------------------------
    # Internal helpers for schematic generation
    # -------------------------------------------------------------------------

    @staticmethod
    def _calc_weights(n_dac: int, n_extra: int, strategy: RedunStrat) -> Optional[list[int]]:
        """
        Calculate capacitor weights for CDAC.

        Args:
            n_dac: DAC resolution (number of bits)
            n_extra: Number of extra physical capacitors for redundancy
            strategy: Weight distribution strategy

        Returns:
            List of (n_dac + n_extra) integer weights, or None for invalid combos
        """
        m_caps = n_dac + n_extra

        if strategy == RedunStrat.RDX2:
            # Standard binary: [2^(n-1), ..., 2, 1]
            weights = [2**i for i in range(n_dac - 1, -1, -1)]
            if n_extra > 0:
                weights.extend([1] * n_extra)
            return weights

        elif strategy == RedunStrat.SUBRDX2:
            # Sub-radix-2: radix^(M-1-i) for each cap
            radix = 2 ** (n_dac / m_caps)
            return [round(radix ** (m_caps - 1 - i)) for i in range(m_caps)]

        elif strategy == RedunStrat.SUBRDX2_LIM:
            # Sub-radix-2 with unit quantization (floor, min 1)
            radix = 2 ** (n_dac / m_caps)
            return [max(1, int(radix ** (m_caps - 1 - i))) for i in range(m_caps)]

        elif strategy == RedunStrat.SUBRDX2_RDST:
            # Binary with MSB redistribution
            n_redist = n_extra + 2
            weights = [2**i for i in range(n_dac - 1, -1, -1)]

            if weights[0] < 2**n_redist:
                return None  # Invalid: MSB would go negative

            weights[0] -= 2**n_redist

            # Redundant weights as paired powers of 2
            w_redun = [2**i for i in range(n_redist - 2, -1, -1) for _ in range(2)]
            w_redun += [1, 1]

            # Merge
            result = [0] * m_caps
            for i, w in enumerate(weights):
                if i < m_caps:
                    result[i] += w
            for i, w in enumerate(w_redun):
                if i + 1 < m_caps:
                    result[i + 1] += w

            return result

        elif strategy == RedunStrat.RDX2_RPT:
            # Binary with repeated capacitors at regular intervals
            base_weights = [2**i for i in range(n_dac - 1, -1, -1)]

            if n_extra == 0:
                return base_weights

            spacing = n_dac // n_extra
            duplicate_indices = sorted([n_dac - 1 - (1 + k * spacing) for k in range(n_extra)])

            result = []
            dup_idx = 0
            for i in range(n_dac):
                result.append(base_weights[i])
                if dup_idx < len(duplicate_indices) and i == duplicate_indices[dup_idx]:
                    result.append(base_weights[i])
                    dup_idx += 1

            return result

        return None

    @staticmethod
    def _self._calc_driver_width(c: int, m: int) -> int:
        """Calculate driver width based on capacitor load (sqrt scaling)."""
        return max(1, int(math.sqrt(c * m)))

    # -------------------------------------------------------------------------

    def is_valid(self) -> bool:
        """Check if this topology combination is valid."""
        # rdx2 only works with n_extra=0
        if self.redun_strat == RedunStrat.RDX2 and self.n_extra != 0:
            return False
        # Other strategies need n_extra > 0
        if self.redun_strat != RedunStrat.RDX2 and self.n_extra == 0:
            return False
        return Cdac._calc_weights(self.n_dac, self.n_extra, self.redun_strat) is not None

    def schematic(self, io, cell: CellBuilder):
        """Generate CDAC schematic."""
        threshold = 64  # Split threshold

        # Build resistor ladder for vdiv split
        if self.split_strat == SplitStrat.VDIV_SPLIT:
            self._build_resistor_ladder(cell, n_taps=64)

        # Build each DAC bit
        for idx, weight in enumerate(self._weights):
            self._build_dac_bit(io, cell, idx, weight, threshold)

    def _build_resistor_ladder(self, cell: CellBuilder, n_taps: int):
        """Build resistor voltage divider for fine-bit implementation."""
        for i in range(n_taps):
            if i == 0:
                top_node = cell.io.vdd
            else:
                top_node = cell.signal(f"tap_{i}")

            if i == n_taps - 1:
                bot_node = cell.io.vss
            else:
                bot_node = cell.signal(f"tap_{i + 1}")

            cell.instantiate(Res(4), name=f"R{i}", p=top_node, n=bot_node)

    def _build_dac_bit(self, io, cell: CellBuilder, idx: int, weight: int, threshold: int):
        """Build one DAC bit: buffer + driver + capacitor(s)."""
        vth = self.vth
        dac_in = io.dac[idx]
        inter = cell.signal(f"inter_{idx}")
        bot = cell.signal(f"bot_{idx}")

        # First inverter (predriver - always unit sized)
        mp_buf = cell.instantiate(Pfet(1, 1, vth), name=f"MPbuf{idx}")
        mn_buf = cell.instantiate(Nfet(1, 1, vth), name=f"MNbuf{idx}")
        cell.connect(inter, mp_buf.d, mn_buf.d)
        cell.connect(dac_in, mp_buf.g, mn_buf.g)
        cell.connect(io.vdd, mp_buf.s, mp_buf.b)
        cell.connect(io.vss, mn_buf.s, mn_buf.b)

        if self.split_strat == SplitStrat.NO_SPLIT:
            self._build_nosplit_bit(io, cell, idx, weight, inter, bot)

        elif self.split_strat == SplitStrat.VDIV_SPLIT:
            self._build_vdivsplit_bit(io, cell, idx, weight, inter, bot, threshold)

        elif self.split_strat == SplitStrat.DIFFCAP_SPLIT:
            self._build_diffcapsplit_bit(io, cell, idx, weight, inter, bot, threshold)

    def _build_nosplit_bit(self, io, cell, idx: int, weight: int, inter, bot):
        """No split: c=1, m=weight."""
        vth = self.vth
        driver_w = self._calc_driver_width(1, weight)

        mp_drv = cell.instantiate(Pfet(driver_w, 1, vth), name=f"MPdrv{idx}")
        mn_drv = cell.instantiate(Nfet(driver_w, 1, vth), name=f"MNdrv{idx}")
        cell.connect(bot, mp_drv.d, mn_drv.d)
        cell.connect(inter, mp_drv.g, mn_drv.g)
        cell.connect(io.vdd, mp_drv.s, mp_drv.b)
        cell.connect(io.vss, mn_drv.s, mn_drv.b)

        # Main capacitor array
        cell.instantiate(Cap(1e-15, m=weight, cap_type=self.cap_type),
                         name=f"Cmain{idx}", p=io.top, n=bot)

    def _build_vdivsplit_bit(self, io, cell, idx: int, weight: int, inter, bot, threshold: int):
        """Voltage divider split: coarse caps + fine via resistor tap."""
        vth = self.vth
        quotient = weight // threshold
        remainder = weight % threshold

        if quotient > 0:
            # Main (coarse) capacitor
            driver_w = self._calc_driver_width(threshold, quotient)
            mp_drv = cell.instantiate(Pfet(driver_w, 1, vth), name=f"MPdrv{idx}")
            mn_drv = cell.instantiate(Nfet(driver_w, 1, vth), name=f"MNdrv{idx}")
            cell.connect(bot, mp_drv.d, mn_drv.d)
            cell.connect(inter, mp_drv.g, mn_drv.g)
            cell.connect(io.vdd, mp_drv.s, mp_drv.b)
            cell.connect(io.vss, mn_drv.s, mn_drv.b)

            cell.instantiate(Cap(threshold * 1e-15, m=quotient, cap_type=self.cap_type),
                             name=f"Cmain{idx}", p=io.top, n=bot)

        if remainder > 0:
            # Fine capacitor driven from resistor tap
            tap_node = cell.signal(f"tap_{remainder}")
            bot_rdiv = cell.signal(f"bot_rdiv_{idx}")
            driver_w = self._calc_driver_width(1, 1)

            mp_rdiv = cell.instantiate(Pfet(driver_w, 1, vth), name=f"MPrdiv{idx}")
            mn_rdiv = cell.instantiate(Nfet(driver_w, 1, vth), name=f"MNrdiv{idx}")
            cell.connect(bot_rdiv, mp_rdiv.d, mn_rdiv.d)
            cell.connect(inter, mp_rdiv.g, mn_rdiv.g)
            cell.connect(tap_node, mp_rdiv.s, mp_rdiv.b)  # Reduced voltage swing
            cell.connect(io.vss, mn_rdiv.s, mn_rdiv.b)

            cell.instantiate(Cap(1e-15, m=1, cap_type=self.cap_type),
                             name=f"Cfine{idx}", p=io.top, n=bot_rdiv)

    def _build_diffcapsplit_bit(self, io, cell, idx: int, weight: int, inter, bot, threshold: int):
        """Difference capacitor split: main + diff caps for fine resolution."""
        vth = self.vth
        quotient = weight // threshold
        remainder = weight % threshold

        if quotient > 0:
            # Coarse capacitor
            driver_w = self._calc_driver_width(threshold, quotient)
            mp_drv = cell.instantiate(Pfet(driver_w, 1, vth), name=f"MPdrv{idx}")
            mn_drv = cell.instantiate(Nfet(driver_w, 1, vth), name=f"MNdrv{idx}")
            cell.connect(bot, mp_drv.d, mn_drv.d)
            cell.connect(inter, mp_drv.g, mn_drv.g)
            cell.connect(io.vdd, mp_drv.s, mp_drv.b)
            cell.connect(io.vss, mn_drv.s, mn_drv.b)

            cell.instantiate(Cap(threshold * 1e-15, m=quotient, cap_type=self.cap_type),
                             name=f"Cmain{idx}", p=io.top, n=bot)

            # Difference cap from intermediate node
            cell.instantiate(Cap(1e-15, m=quotient, cap_type=self.cap_type),
                             name=f"Cdiff{idx}", p=io.top, n=inter)

        if remainder > 0:
            # Fine caps using difference technique
            # Effective weight = (c_main - c_diff) where both are driven
            c_main = threshold + 1 + remainder
            c_diff = threshold + 1 - remainder

            if quotient == 0:
                # Need to add driver if no coarse part
                driver_w = self._calc_driver_width(c_main, 1)
                mp_drv = cell.instantiate(Pfet(driver_w, 1, vth), name=f"MPdrv{idx}")
                mn_drv = cell.instantiate(Nfet(driver_w, 1, vth), name=f"MNdrv{idx}")
                cell.connect(bot, mp_drv.d, mn_drv.d)
                cell.connect(inter, mp_drv.g, mn_drv.g)
                cell.connect(io.vdd, mp_drv.s, mp_drv.b)
                cell.connect(io.vss, mn_drv.s, mn_drv.b)

            cell.instantiate(Cap(c_main * 1e-15, m=1, cap_type=self.cap_type),
                             name=f"Cmain_fine{idx}", p=io.top, n=bot)
            cell.instantiate(Cap(c_diff * 1e-15, m=1, cap_type=self.cap_type),
                             name=f"Cdiff_fine{idx}", p=io.top, n=inter)


# =============================================================================
# Variant Generation
# =============================================================================

def generate_all_variants() -> list[Cdac]:
    """Generate all valid CDAC topology combinations."""
    variants = []

    for n_dac in [7, 9, 11, 13]:
        for n_extra in [0, 2, 4, 6]:
            for redun_strat in RedunStrat:
                for split_strat in SplitStrat:
                    for cap_type in CapType:
                        try:
                            cdac = Cdac(
                                n_dac=n_dac,
                                n_extra=n_extra,
                                redun_strat=redun_strat,
                                split_strat=split_strat,
                                cap_type=cap_type,
                            )
                            if cdac.is_valid():
                                variants.append(cdac)
                        except ValueError:
                            # Invalid combination
                            pass

    return variants


# =============================================================================
# Testbench
# =============================================================================

@dataclass
class CdacTb:
    """
    CDAC testbench - sweeps through key DAC codes.

    Note: IO and schematic depend on DUT's n_bits, so this is also dynamic.
    """
    pvt: Pvt
    dut: Cdac

    def schematic(self, io, cell: CellBuilder):
        vdd = cell.signal("vdd")
        top = cell.signal("top")

        # Power
        cell.instantiate(Vsource.dc(self.pvt.voltage), p=vdd, n=io.vss)

        # DAC input sources - sweep through key codes
        # Codes: 0, 1/4, 1/2, 3/4, full_scale
        max_code = (1 << self.dut.n_dac) - 1
        test_codes = [0, max_code // 4, max_code // 2, 3 * max_code // 4, max_code]

        for i in range(self.dut.n_bits):
            # Generate PWL waveform for this bit across all test codes
            bit_mask = 1 << i
            cell.instantiate(
                Vsource.pwl(PwlBits(
                    codes=test_codes,
                    bit_index=i,
                    v_high=self.pvt.voltage,
                    t_per_code=100e-9,
                )),
                p=cell.signal(f"dac_{i}"),
                n=io.vss
            )

        # Load capacitor
        cell.instantiate(Cap(100e-15), p=top, n=io.vss)

        # DUT - connect dynamically based on n_bits
        dut_pins = {"top": top, "vdd": vdd, "vss": io.vss}
        for i in range(self.dut.n_bits):
            dut_pins[f"dac[{i}]"] = cell.signal(f"dac_{i}")

        cell.instantiate(self.dut, **dut_pins)

        return top  # probe node


# =============================================================================
# Analyses & Measures
# =============================================================================

analyses = {
    "tran": {"stop": 500e-9, "step": 0.1e-9},
}

measures = {
    "inl_max_lsb": lambda out, n_dac: out.cdac_inl_max("top", n_dac),
    "dnl_max_lsb": lambda out, n_dac: out.cdac_dnl_max("top", n_dac),
    "settling_ns": lambda out: out.settling_time("top", tol=0.01),
    "glitch_mV": lambda out: out.glitch_amplitude("top"),
}


# =============================================================================
# Helper: PWL source generators (would live in flow/sources.py)
# =============================================================================

@dataclass
class PwlStep:
    """
    Generate PWL points for a stepping waveform.

    Can specify either:
      - vstart + vstep + count (step by fixed amount)
      - vstart + vstop + count (interpolate between endpoints)
    """
    vstart: float
    tstep: float
    count: int
    trise: float = 1e-12
    vstep: Optional[float] = None
    vstop: Optional[float] = None

    def to_pwl_points(self) -> list[tuple[float, float]]:
        """Convert to list of (time, voltage) points."""
        points = []
        t = 0

        for i in range(self.count):
            if self.vstep is not None:
                v = self.vstart + i * self.vstep
            elif self.vstop is not None:
                v = self.vstart + (self.vstop - self.vstart) * i / (self.count - 1)
            else:
                v = self.vstart

            # Start of plateau
            points.append((t, v))
            # End of plateau (before rise to next level)
            t += self.tstep - self.trise
            points.append((t, v))
            # After rise
            t += self.trise

        return points


@dataclass
class PwlBits:
    """
    Generate PWL points for a single DAC bit across multiple codes.
    """
    codes: list[int]
    bit_index: int
    v_high: float
    t_per_code: float
    v_low: float = 0.0
    trise: float = 1e-12

    def to_pwl_points(self) -> list[tuple[float, float]]:
        """Convert to list of (time, voltage) points."""
        points = []
        t = 0
        bit_mask = 1 << self.bit_index

        for code in self.codes:
            v = self.v_high if (code & bit_mask) else self.v_low
            points.append((t, v))
            t += self.t_per_code - self.trise
            points.append((t, v))
            t += self.trise

        return points
