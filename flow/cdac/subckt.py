"""
Capacitor DAC (CDAC) generator for FRIDA.

Supports multiple architectures including:
- Various redundancy strategies (RDX2, sub-radix-2, etc.)
- Different split strategies (no split, voltage divider, difference cap)
- Variable bit widths with dynamic port generation
"""

from enum import Enum, auto

import hdl21 as h
from hdl21.prefix import f
from hdl21.primitives import C, MosType, MosVth

from flow.momcap.subckt import MomCap, MomCapParams


class RedunStrat(Enum):
    RDX2 = auto()
    SUBRDX2 = auto()
    SUBRDX2_LIM = auto()
    SUBRDX2_RDST = auto()
    RDX2_RPT = auto()
    SUBRDX2_OVLY = auto()  # Sub-radix-2 with paired overlay


class SplitStrat(Enum):
    NO_SPLIT = auto()
    VDIV_SPLIT = auto()
    DIFFCAP_SPLIT = auto()


class CapType(Enum):
    MOM1 = auto()
    MOM2 = auto()
    MOM3 = auto()


@h.paramclass
class CdacParams:
    """CDAC parameters."""

    n_dac = h.Param(dtype=int, desc="DAC resolution (bits)", default=11)
    n_extra = h.Param(dtype=int, desc="Extra caps for redundancy", default=5)
    redun_strat = h.Param(dtype=RedunStrat, desc="Redundancy strategy", default=RedunStrat.SUBRDX2_OVLY)
    split_strat = h.Param(dtype=SplitStrat, desc="Split strategy", default=SplitStrat.NO_SPLIT)
    cap_type = h.Param(dtype=CapType, desc="Capacitor type", default=CapType.MOM1)
    mos_vth = h.Param(dtype=MosVth, desc="Transistor Vth", default=MosVth.LOW)
    unit_cap = h.Param(dtype=h.Scalar, desc="Unit capacitance", default=1 * f)
    driver_p_w = h.Param(
        dtype=int,
        desc="Unit PMOS output-driver width multiplier",
        default=9,
    )
    driver_n_w = h.Param(
        dtype=int,
        desc="Unit NMOS output-driver width multiplier",
        default=7,
    )
    driver_strengths = h.Param(
        dtype=tuple[int, ...] | None,
        desc="Optional C0-first output-driver strengths in conversion-stage order",
        default=None,
    )
    weights = h.Param(
        dtype=tuple[int, ...] | None,
        desc="Explicit C0-first unit-capacitor weights in conversion-stage order",
        default=None,
    )


@h.paramclass
class CdacArrayParams:
    """Electrical parameters for the passive unit-length capacitor array."""

    cdac = h.Param(dtype=CdacParams, desc="CDAC electrical sizing", default=CdacParams())
    coarse_weight = h.Param(dtype=int, desc="Largest available unit-capacitor weight", default=64)
    active_layers = h.Param(dtype=tuple[int, ...], desc="Consecutive active metals, lowest first", default=(6,))
    unit_models = h.Param(
        dtype=tuple[h.Module, ...],
        desc="Optional PLUS/MINUS/BULK device model per active layer; empty selects ideal MOMs",
        default=(),
    )


def is_valid_cdac_params(p: CdacParams) -> bool:
    """Check if this CDAC configuration is valid."""
    if p.driver_p_w <= 0 or p.driver_n_w <= 0:
        return False
    if p.driver_strengths is not None:
        if len(p.driver_strengths) != p.n_dac + p.n_extra:
            return False
        if any(
            isinstance(strength, bool) or not isinstance(strength, int) or strength <= 0
            for strength in p.driver_strengths
        ):
            return False
    if p.weights is not None:
        return len(p.weights) == p.n_dac + p.n_extra and all(
            not isinstance(weight, bool) and isinstance(weight, int) and weight > 0 for weight in p.weights
        )
    # RDX2 only works with n_extra=0
    if p.redun_strat == RedunStrat.RDX2 and p.n_extra != 0:
        return False
    # Other strategies need n_extra > 0
    if p.redun_strat != RedunStrat.RDX2 and p.n_extra == 0:
        return False
    return _calc_weights(p.n_dac, p.n_extra, p.redun_strat) is not None


def get_cdac_weights(p: CdacParams) -> list[int]:
    """Return C0-first capacitor weights in chronological conversion order.

    Stage zero is the first-switched and largest capacitor. The last element
    is the final switched capacitor; the terminal BOUT decision has no CDAC
    element and is therefore not included here.
    """
    if p.weights is not None:
        if not is_valid_cdac_params(p):
            raise ValueError(
                f"Explicit CDAC weights must contain exactly n_dac + n_extra = {p.n_dac + p.n_extra} positive integers"
            )
        return list(p.weights)
    weights = _calc_weights(p.n_dac, p.n_extra, p.redun_strat)
    if weights is None:
        raise ValueError(f"Invalid CDAC params: {p}")
    return weights


def _calc_weight_partitions(weights: list[int], coarse_weight: int) -> list[list[int]]:
    """Split arbitrary electrical weights into coarse units and one fine remainder."""

    if isinstance(coarse_weight, bool) or not isinstance(coarse_weight, int) or coarse_weight <= 0:
        raise ValueError("coarse_weight must be a positive integer")
    if any(isinstance(weight, bool) or not isinstance(weight, int) or weight <= 0 for weight in weights):
        raise ValueError("weights must contain positive integers")
    partitions: list[list[int]] = []
    for weight in weights:
        chunks = [coarse_weight] * (weight // coarse_weight)
        if remainder := weight % coarse_weight:
            chunks.append(remainder)
        partitions.append(chunks)
    return partitions


def is_valid_cdac_array_params(p: CdacArrayParams) -> bool:
    """Check passive-array sizing and its coarse unit family."""

    if isinstance(p.coarse_weight, bool) or not isinstance(p.coarse_weight, int) or p.coarse_weight <= 0:
        return False
    if not p.active_layers or any(isinstance(layer, bool) or layer < 1 for layer in p.active_layers):
        return False
    if p.active_layers != tuple(range(p.active_layers[0], p.active_layers[-1] + 1)):
        return False
    if p.unit_models and (
        len(p.unit_models) != len(p.active_layers)
        or any(
            tuple(model.ports) != ("PLUS", "MINUS", "BULK") or any(port.width != 1 for port in model.ports.values())
            for model in p.unit_models
        )
    ):
        return False
    return is_valid_cdac_params(p.cdac)


@h.generator
def CdacArray(p: CdacArrayParams) -> h.Module:
    """Generate an arbitrary-width passive main/diff unit-length array."""

    if not is_valid_cdac_array_params(p):
        raise ValueError(f"Invalid CDAC array params: {p}")
    weights = get_cdac_weights(p.cdac)
    partitions = _calc_weight_partitions(weights, p.coarse_weight)
    n_caps = len(weights)

    @h.module
    class CdacArray:
        cap_topplate = h.Inout(desc="Common capacitor top plate")
        cap_shieldplate = h.Inout(desc="Grounded lower shield")

    for kind in ("main", "diff"):
        for stage in range(n_caps):
            name = f"cap_botplate_{kind}<{stage}>"
            setattr(CdacArray, name, h.Inout(name=name, desc=f"C{stage} {kind} bottom plate"))

    for stage, chunks in enumerate(partitions):
        for chunk_index, chunk in enumerate(chunks):
            for layer_index, layer in enumerate(p.active_layers):
                for kind, sign in (("main", 1), ("diff", -1)):
                    # unit_cap specifies the total logical unit across the
                    # stack. Equal ideal shares preserve that electrical sizing;
                    # actual per-layer capacitances are measured by PEX.
                    value = p.cdac.unit_cap * ((p.coarse_weight + 1 + sign * chunk) / (2 * len(p.active_layers)))
                    # HDL21 adds parameter constructors dynamically via @paramclass.
                    unit = p.unit_models[layer_index] if p.unit_models else MomCap(MomCapParams(c=value))  # ty: ignore[unknown-argument]
                    setattr(
                        CdacArray,
                        f"{kind}_{stage}_{chunk_index}_m{layer}",
                        h.Instance(of=unit)(
                            PLUS=CdacArray.cap_topplate,
                            MINUS=getattr(CdacArray, f"cap_botplate_{kind}<{stage}>"),
                            BULK=CdacArray.cap_shieldplate,
                        ),
                    )
    return CdacArray


@h.generator
def Cdac(param: CdacParams) -> h.Module:
    """
    Capacitor DAC generator.

    Generates a CDAC with variable bit width based on parameters.

    Uses h.Mos primitives - call pdk.compile() to convert to PDK devices.
    """
    if not is_valid_cdac_params(param):
        raise ValueError(f"Invalid CDAC params: {param}")

    weights = get_cdac_weights(param)
    n_stages = len(weights)
    if param.driver_strengths is None:
        # Match the fabricated FRIDA driver bands: the two largest capacitors
        # use 4× output stages, the next two use 2×, and all others use 1×.
        driver_strengths = (4, 4, 2, 2)[:n_stages] + (1,) * max(0, n_stages - 4)
    else:
        driver_strengths = param.driver_strengths

    @h.module
    class Cdac:
        """Capacitor DAC module."""

        # IO ports
        top = h.Inout(desc="DAC output (top plate)")
        vdd = h.Inout(desc="Supply")
        vss = h.Inout(desc="Ground")
        # Variable-width DAC control bus
        dac = h.Input(width=n_stages, desc="C0-first DAC stage controls")

    # Build each DAC bit
    threshold = 64  # Split threshold for vdiv/diffcap

    # Every generated bus uses conversion-stage indices: stage zero is the
    # first register and the largest capacitor. Numeric bus significance is
    # deliberately not used to describe these non-binary redundant weights.
    for stage, weight, driver_strength in zip(
        range(n_stages),
        weights,
        driver_strengths,
        strict=True,
    ):
        _build_dac_bit(Cdac, param, stage, weight, driver_strength, threshold)

    return Cdac


def _build_dac_bit(
    mod,
    param: CdacParams,
    stage: int,
    weight: int,
    driver_strength: int,
    threshold: int,
):
    """Build one chronological DAC stage."""

    # Create intermediate signal for this bit
    inter = h.Signal(name=f"inter_{stage}")
    bot = h.Signal(name=f"bot_{stage}")
    setattr(mod, f"inter_{stage}", inter)
    setattr(mod, f"bot_{stage}", bot)

    # First inverter (predriver - use minimum sized devices: w=10, l=1)
    MP_buf = h.Mos(tp=MosType.PMOS, vth=param.mos_vth, w=10, l=1)(d=inter, g=mod.dac[stage], s=mod.vdd, b=mod.vdd)
    MN_buf = h.Mos(tp=MosType.NMOS, vth=param.mos_vth, w=10, l=1)(d=inter, g=mod.dac[stage], s=mod.vss, b=mod.vss)
    setattr(mod, f"MP_buf_{stage}", MP_buf)
    setattr(mod, f"MN_buf_{stage}", MN_buf)

    if param.split_strat == SplitStrat.NO_SPLIT:
        _build_nosplit_bit(mod, param, stage, weight, driver_strength, inter, bot)
    elif param.split_strat == SplitStrat.VDIV_SPLIT:
        _build_nosplit_bit(mod, param, stage, weight, driver_strength, inter, bot)  # Simplified
    else:  # DIFFCAP_SPLIT
        _build_nosplit_bit(mod, param, stage, weight, driver_strength, inter, bot)  # Simplified


def _build_nosplit_bit(
    mod,
    param: CdacParams,
    stage: int,
    weight: int,
    driver_strength: int,
    inter,
    bot,
):
    """No split: c=1, m=weight (simplified using multiplier)."""

    # Approximate the fabricated XOR output stage with portable transistors.
    # Strength changes in three discrete bands instead of scaling continuously
    # with capacitor weight.
    MP_drv = h.Mos(
        tp=MosType.PMOS,
        vth=param.mos_vth,
        w=param.driver_p_w * driver_strength,
        l=1,
    )(d=bot, g=inter, s=mod.vdd, b=mod.vdd)
    MN_drv = h.Mos(
        tp=MosType.NMOS,
        vth=param.mos_vth,
        w=param.driver_n_w * driver_strength,
        l=1,
    )(d=bot, g=inter, s=mod.vss, b=mod.vss)
    setattr(mod, f"MP_drv_{stage}", MP_drv)
    setattr(mod, f"MN_drv_{stage}", MN_drv)

    # Main capacitor (weight implemented via capacitance value)
    cap_val = weight * param.unit_cap
    Cap = C(c=cap_val)(p=mod.top, n=bot)
    setattr(mod, f"C_{stage}", Cap)


# Weight Calculation


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
        # Binary with largest-stage redistribution for redundancy
        # Split 2^n_redist from C0 and redistribute as pairs
        n_redist = n_extra + 2  # Extra caps determine redistribution

        # Base binary weights
        weights = [2**i for i in range(n_dac - 1, -1, -1)]

        # Check if C0 would become negative.
        if weights[0] < 2**n_redist:
            return None

        weights[0] -= 2**n_redist

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

        # Process duplicate locations from early to late conversion stage.
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

    elif strategy == RedunStrat.SUBRDX2_OVLY:
        # Sub-radix-2 with paired overlay sequence.
        # Returns FRIDA 65nm weights [768,512,320,...] when n_dac=11, n_extra=5.
        #
        # Algorithm:
        # 1. Base overlay sequence: pairs of powers of 2 from high to low
        #    ...64,64, 32,32, 16,16, 8,8, 4,4, 2,2, 1,1, 1,1
        # 2. For even overlay_len: merge (2+2)->4 and (1+1)->2
        #    Tail becomes: [4, 4, 4, 2, 1, 1]
        # 3. For odd overlay_len: merge only (1+1)->2
        #    Tail becomes: [4, 4, 2, 2, 2, 1, 1]
        # 4. Take last overlay_len elements
        # 5. Subtract the sum from C0, then add the overlay at stage 2

        if n_extra == 0:
            # No redundancy, pure radix-2
            return [2**i for i in range(n_dac - 1, -1, -1)]

        overlay_len = n_dac + n_extra - 2

        # Build overlay sequences (extend high enough for any practical use)
        # Even: merge (2+2)->4 and (1+1)->2, tail = [4,4,4,2,1,1]
        # Odd: merge only (1+1)->2, tail = [4,4,2,2,2,1,1]
        overlay_even = []
        overlay_odd = []
        for power in range(20, 2, -1):  # 2^20 down to 2^3=8
            overlay_even.extend([2**power, 2**power])
            overlay_odd.extend([2**power, 2**power])
        overlay_even.extend([4, 4, 4, 2, 1, 1])
        overlay_odd.extend([4, 4, 2, 2, 2, 1, 1])

        if overlay_len % 2 == 0:
            overlay = overlay_even[-overlay_len:]
        else:
            overlay = overlay_odd[-overlay_len:]

        overlay_sum = sum(overlay)
        base = [2**i for i in range(n_dac - 1, -1, -1)]

        result = [0] * m_caps
        result[0] = base[0] - overlay_sum
        for i in range(1, n_dac):
            result[i] = base[i]
        for i, val in enumerate(overlay):
            result[i + 2] += val

        return result

    else:
        return None  # Unknown strategy
