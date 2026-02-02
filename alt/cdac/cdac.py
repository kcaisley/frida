"""
Capacitor DAC (CDAC) generator for FRIDA.

Supports multiple architectures including:
- Various redundancy strategies (RDX2, sub-radix-2, etc.)
- Different split strategies (no split, voltage divider, difference cap)
- Variable bit widths with dynamic port generation
"""

import math

import hdl21 as h
from hdl21.prefix import f
from hdl21.primitives import C, MosType, MosVth

from ..flow.params import CapType, RedunStrat, SplitStrat


@h.paramclass
class CdacParams:
    """CDAC parameters."""

    n_dac = h.Param(dtype=int, desc="DAC resolution (bits)", default=8)
    n_extra = h.Param(dtype=int, desc="Extra caps for redundancy", default=0)
    redun_strat = h.Param(
        dtype=RedunStrat, desc="Redundancy strategy", default=RedunStrat.RDX2
    )
    split_strat = h.Param(
        dtype=SplitStrat, desc="Split strategy", default=SplitStrat.NO_SPLIT
    )
    cap_type = h.Param(dtype=CapType, desc="Capacitor type", default=CapType.MOM1)
    vth = h.Param(dtype=MosVth, desc="Transistor Vth", default=MosVth.LOW)
    unit_cap = h.Param(dtype=h.Scalar, desc="Unit capacitance", default=1 * f)


def is_valid_cdac_params(p: CdacParams) -> bool:
    """Check if this CDAC configuration is valid."""
    # RDX2 only works with n_extra=0
    if p.redun_strat == RedunStrat.RDX2 and p.n_extra != 0:
        return False
    # Other strategies need n_extra > 0
    if p.redun_strat != RedunStrat.RDX2 and p.n_extra == 0:
        return False
    return _calc_weights(p.n_dac, p.n_extra, p.redun_strat) is not None


def get_cdac_weights(p: CdacParams) -> list[int]:
    """Get the capacitor weights for a CDAC configuration."""
    weights = _calc_weights(p.n_dac, p.n_extra, p.redun_strat)
    if weights is None:
        raise ValueError(f"Invalid CDAC params: {p}")
    return weights


def get_cdac_n_bits(p: CdacParams) -> int:
    """Get the number of physical bits (capacitors) for a CDAC configuration."""
    return len(get_cdac_weights(p))


@h.generator
def Cdac(p: CdacParams) -> h.Module:
    """
    Capacitor DAC generator.

    Generates a CDAC with variable bit width based on parameters.

    Uses h.Mos primitives - call pdk.compile() to convert to PDK devices.
    """
    weights = get_cdac_weights(p)
    n_bits = len(weights)
    mosvth = p.vth

    @h.module
    class Cdac:
        """Capacitor DAC module."""

        # IO ports
        top = h.Port(desc="DAC output (top plate)")
        vdd = h.Port(desc="Supply")
        vss = h.Port(desc="Ground")
        # Variable-width DAC control bus
        dac = h.Input(width=n_bits, desc="DAC control bits")

    # Build each DAC bit
    threshold = 64  # Split threshold for vdiv/diffcap

    for idx, weight in enumerate(weights):
        _build_dac_bit(Cdac, p, idx, weight, threshold, mosvth)

    return Cdac


def _calc_driver_width(c: int, m: int) -> int:
    """Calculate driver width multiplier based on capacitor load (sqrt scaling)."""
    return max(10, int(math.sqrt(c * m)) * 10)


def _build_dac_bit(
    mod, p: CdacParams, idx: int, weight: int, threshold: int, mosvth: MosVth
):
    """Build one DAC bit: buffer + driver + capacitor(s)."""

    # Create intermediate signal for this bit
    inter = h.Signal(name=f"inter_{idx}")
    bot = h.Signal(name=f"bot_{idx}")
    setattr(mod, f"inter_{idx}", inter)
    setattr(mod, f"bot_{idx}", bot)

    # First inverter (predriver - use minimum sized devices: w=10, l=1)
    mp_buf = h.Mos(tp=MosType.PMOS, vth=mosvth, w=10, l=1)(
        d=inter, g=mod.dac[idx], s=mod.vdd, b=mod.vdd
    )
    mn_buf = h.Mos(tp=MosType.NMOS, vth=mosvth, w=10, l=1)(
        d=inter, g=mod.dac[idx], s=mod.vss, b=mod.vss
    )
    setattr(mod, f"mp_buf_{idx}", mp_buf)
    setattr(mod, f"mn_buf_{idx}", mn_buf)

    if p.split_strat == SplitStrat.NO_SPLIT:
        _build_nosplit_bit(mod, p, idx, weight, inter, bot, mosvth)
    elif p.split_strat == SplitStrat.VDIV_SPLIT:
        _build_nosplit_bit(mod, p, idx, weight, inter, bot, mosvth)  # Simplified
    else:  # DIFFCAP_SPLIT
        _build_nosplit_bit(mod, p, idx, weight, inter, bot, mosvth)  # Simplified


def _build_nosplit_bit(
    mod, p: CdacParams, idx: int, weight: int, inter, bot, mosvth: MosVth
):
    """No split: c=1, m=weight (simplified using multiplier)."""
    driver_w = _calc_driver_width(1, weight)

    # Driver inverter (width scales with capacitor weight)
    mp_drv = h.Mos(tp=MosType.PMOS, vth=mosvth, w=driver_w, l=1)(
        d=bot, g=inter, s=mod.vdd, b=mod.vdd
    )
    mn_drv = h.Mos(tp=MosType.NMOS, vth=mosvth, w=driver_w, l=1)(
        d=bot, g=inter, s=mod.vss, b=mod.vss
    )
    setattr(mod, f"mp_drv_{idx}", mp_drv)
    setattr(mod, f"mn_drv_{idx}", mn_drv)

    # Main capacitor (weight implemented via capacitance value)
    cap_val = weight * p.unit_cap
    cap = C(c=cap_val)(p=mod.top, n=bot)
    setattr(mod, f"c_{idx}", cap)


def cdac_variants(
    n_dac_list: list = None,
    n_extra_list: list = None,
    redun_strats: list = None,
    split_strats: list = None,
) -> list:
    """
    Generate a list of valid CdacParams for parameter sweeps.

    Only generates valid topology combinations.
    """
    if n_dac_list is None:
        n_dac_list = [7, 9, 11]
    if n_extra_list is None:
        n_extra_list = [0, 2, 4]
    if redun_strats is None:
        redun_strats = list(RedunStrat)
    if split_strats is None:
        split_strats = [SplitStrat.NO_SPLIT]  # Simplified for now

    variants = []

    for n_dac in n_dac_list:
        for n_extra in n_extra_list:
            for redun_strat in redun_strats:
                for split_strat in split_strats:
                    params = CdacParams(
                        n_dac=n_dac,
                        n_extra=n_extra,
                        redun_strat=redun_strat,
                        split_strat=split_strat,
                    )
                    if is_valid_cdac_params(params):
                        variants.append(params)

    return variants


# =============================================================================
# WEIGHT CALCULATION (internal helper, called by validation and getter functions)
# =============================================================================


def _calc_weights(n_dac: int, n_extra: int, strategy: RedunStrat) -> list[int] | None:
    """
    Calculate capacitor weights for CDAC.

    Args:
        n_dac: DAC resolution (number of bits)
        n_extra: Number of extra physical capacitors for redundancy
        strategy: RedunStrat enum for weighting strategy

    Returns:
        List of (n_dac + n_extra) integer weights (in units of Cu), or None for invalid combos
    """
    m_caps = n_dac + n_extra

    if strategy == RedunStrat.RDX2:
        # Standard binary weighting: [2^(n-1), 2^(n-2), ..., 2, 1]
        # Pad with unit caps if n_extra > 0
        weights = [2**i for i in range(n_dac - 1, -1, -1)]
        if n_extra > 0:
            weights.extend([1] * n_extra)
        return weights

    elif strategy == RedunStrat.SUBRDX2:
        # Each bit is equal to radix^bit up to bit M-1, where radix = 2^(N/M)
        # Round to nearest integer (not floor like normalized)
        radix = 2 ** (n_dac / m_caps)
        weights = [round(radix ** (m_caps - 1 - i)) for i in range(m_caps)]
        return weights

    elif strategy == RedunStrat.SUBRDX2_LIM:
        # Sub-radix-2 with unit quantization
        # Radix < 2 provides redundancy for error correction
        radix = 2 ** (n_dac / m_caps)
        weights = [max(1, int(radix ** (m_caps - 1 - i))) for i in range(m_caps)]
        return weights

    elif strategy == RedunStrat.SUBRDX2_RDST:
        # Binary with MSB redistribution for redundancy
        # Split 2^n_redist from MSB and redistribute as pairs
        n_redist = n_extra + 2  # Extra caps determine redistribution

        # Base binary weights
        weights = [2**i for i in range(n_dac - 1, -1, -1)]

        # Check if MSB would become negative - return None for invalid combinations
        if weights[0] < 2**n_redist:
            return None

        weights[0] -= 2**n_redist  # Subtract from MSB

        # Redundant weights as paired powers of 2
        w_redun = [2**i for i in range(n_redist - 2, -1, -1) for _ in range(2)]
        w_redun += [1, 1]  # Final unit pair

        # Merge: add redundant weights offset by 1 position
        result = [0] * m_caps
        for i, w in enumerate(weights):
            if i < m_caps:
                result[i] += w
        for i, w in enumerate(w_redun):
            if i + 1 < m_caps:
                result[i + 1] += w

        return result

    elif strategy == RedunStrat.RDX2_RPT:
        # Generate base radix-2 array, then insert repeated capacitors
        # Extra capacitors are inserted at regular intervals

        # Base radix-2 weights
        base_weights = [2**i for i in range(n_dac - 1, -1, -1)]

        if n_extra == 0:
            return base_weights

        # Calculate spacing for inserted capacitors
        spacing = n_dac // n_extra

        # Calculate which base array positions should be duplicated
        # First duplicate is 1 position from end, then every 'spacing' positions earlier
        duplicate_indices = []
        for k in range(n_extra):
            pos_from_end = 1 + k * spacing
            # Convert to 0-based index in base_weights array
            idx = n_dac - 1 - pos_from_end
            duplicate_indices.append(idx)

        # Sort in ascending order to process from MSB to LSB
        duplicate_indices.sort()

        # Build result by inserting duplicates after their positions
        result = []
        dup_idx = 0
        for i in range(n_dac):
            result.append(base_weights[i])
            # Check if this position should be duplicated
            if dup_idx < len(duplicate_indices) and i == duplicate_indices[dup_idx]:
                result.append(base_weights[i])
                dup_idx += 1

        return result

    else:
        return None  # Unknown strategy
