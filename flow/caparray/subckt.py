"""The capacitor array (CDAC) generator: a passive main/difference array of unit-length capacitors.

An array is four integers and an enum (``CapArrayConfig``): its DAC resolution ``n_dac``, binary
steps of total weight 2^n_dac - 1 units; its extra conversion cycles ``n_extra`` (0: binary); the
scheme that spends them, ``redun_strat``; and its capacitance, ``cap_scale``. Every scheme keeps
the binary total exactly: an extra cycle redistributes weight, it never adds capacitance.

- ``MSB_SPLIT``: the n_extra most significant binary weights each split into two halves;
- ``LSB_SPLIT``: the n_extra least significant binary weights of at least 2 (2, 4, ...,
  2^n_extra) each split into two halves, the LSB kept whole;
- ``MSB_REDIST``: FRIDA's paired overlay, a run of paired powers of two taken from the MSB and
  added to the stages from the third on (FRIDA-1's array is MSB_REDIST with 5 at n_dac = 11).

Each array's weights fall from the first stage to the last, and no stage weighs more than the
stages after it and the final comparison can correct (``tolerance_units`` >= 0), so every code is
reached.

The converter samples on its top plates and compares once before any capacitor switches: an
n_dac-step array serves an n_dac + 1 bit converter. Its capacitance is sized to its own full scale:
the reference across the switched plates' share of the top plate, which only its layout knows (the
fingers' tails and the ring's coupling to the shield load the top plate too). At that full scale
the converter's sampled noise, both sides' kT/C on the whole top plate, is 1/``cap_scale`` of its
quantization noise (``total_capacitance_f``); its switched capacitance is the switched share of
that top plate (``switched_capacitance_f``), and the unit that over the total weight
(``unit_capacitance_f``). ``flow.caparray.layout`` sizes each ADC array at the full scale its own
extraction measures; a netlist without a layout is an ideal array, all of its top plate switched,
at a 1 V reference.

``weights`` and ``driver_strengths`` are FRIDA-1's fabricated arrays' alone (lab scans, FRIDA-1's
layout checks, decoding archived captures): the design space never sets them. Its arrays' weights
are their scheme's, and their drivers are derived from their extracted plates
(``flow.capdriver.model.driver_strengths``).
"""

from enum import Enum
from itertools import pairwise

import hdl21 as h
from hdl21.prefix import f

from flow.circuit.ports import module_from_ports
from flow.momcap.subckt import PORTS as MOM_PORTS
from flow.momcap.subckt import MomCap, MomCapParams


class RedunStrat(Enum):
    """How an array spends its extra conversion cycles on the binary weight."""

    BINARY = 1
    MSB_SPLIT = 2
    LSB_SPLIT = 3
    MSB_REDIST = 4
    # aliases: the names archived measurements (FRIDA-1's captures) store these two under, read
    # back as the same members
    RDX2 = 1  # noqa: PIE796
    SUBRDX2_OVLY = 4  # noqa: PIE796


BOLTZMANN_J_PER_K = 1.380649e-23
TEMPERATURE_K = 300.0
# a netlist's array without a layout: ideal (all of its top plate switched, so its full scale is
# its reference) at 1 V
NOMINAL_REFERENCE_V = 1.0


@h.paramclass
class CapArrayConfig:
    """An array: its DAC resolution, its extra cycles and their scheme, and its capacitance."""

    n_dac = h.Param(dtype=int, desc="DAC resolution: binary steps of total weight 2^n_dac - 1 units", default=11)
    n_extra = h.Param(dtype=int, desc="Extra conversion cycles (0: binary)", default=5)
    redun_strat = h.Param(
        dtype=RedunStrat, desc="The scheme that spends the extra cycles", default=RedunStrat.MSB_REDIST
    )
    cap_scale = h.Param(
        dtype=int,
        desc="Switched capacitance a side, in kT/C minimums of an n_dac + 1 bit converter",
        default=1,
    )
    driver_strengths = h.Param(
        dtype=tuple[int, ...] | None,
        desc="FRIDA-1's fabricated C0-first drive bands (1, 2 or 4); None: derived from the array's plates "
        "(flow.capdriver.model.driver_strengths). The design space never sets it",
        default=None,
    )
    weights = h.Param(
        dtype=tuple[int, ...] | None,
        desc="FRIDA-1's fabricated C0-first weights (lab scans, its layout checks, archived captures); None: "
        "the scheme's. The design space never sets it",
        default=None,
    )

    def __post_init__(self) -> None:
        # every array the parameters admit builds (is_valid_caparray_config)
        if not is_valid_caparray_config(self):
            raise ValueError(f"no array has these parameters: {self}")


def binary_weights(n_dac: int) -> list[int]:
    """The n_dac-step binary DAC's weights, C0 (the MSB) first."""
    return [2**i for i in range(n_dac - 1, -1, -1)]


def tolerance_units(weights: list[int] | tuple[int, ...]) -> list[int]:
    """Each stage's tolerance in units, C0 first: the error its decision may make and the stages
    after it and the final comparison still correct, sum_{j>k} w_j + 1 - w_k (binary: 0 at every
    stage). None negative: every code is reached."""
    later = 0
    tolerances = []
    for weight in reversed(weights):
        tolerances.append(later + 1 - weight)
        later += weight
    return tolerances[::-1]


def _split(n_dac: int, stages: range) -> list[int]:
    """Binary weights with those at ``stages`` (C0 first) each split into two halves."""
    return [
        w for k, weight in enumerate(binary_weights(n_dac)) for w in ((weight // 2,) * 2 if k in stages else (weight,))
    ]


def _msb_redist(n_dac: int, n_extra: int) -> list[int]:
    """FRIDA's paired overlay: the last n_dac + n_extra - 2 of the paired powers of two
    ..., 16, 16, 8, 8 ending 4, 4, 4, 2, 1, 1 (an even count) or 4, 4, 2, 2, 2, 1, 1 (odd) added to
    the stages from the third on and their sum taken from the MSB (FRIDA-1's 768, 512, 320, ... at
    n_dac = 11, n_extra = 5)."""
    length = n_dac + n_extra - 2
    pairs = [weight for power in range(n_dac + 1, 2, -1) for weight in (2**power, 2**power)]
    overlay = (pairs + ([4, 4, 4, 2, 1, 1] if length % 2 == 0 else [4, 4, 2, 2, 2, 1, 1]))[-length:]
    if len(overlay) < length:
        return []
    weights = binary_weights(n_dac) + [0] * n_extra
    weights[0] -= sum(overlay)
    for stage, weight in enumerate(overlay, start=2):
        weights[stage] += weight
    return weights


def _calc_weights(n_dac: int, n_extra: int, strategy: RedunStrat) -> list[int] | None:
    """The C0-first weights of the n_dac-step array with n_extra extra cycles by ``strategy``, or
    None where the scheme cannot: binary has none, every other scheme at least one, and the result
    must keep the binary total, fall from stage to stage and tolerate no negative error."""
    if n_dac < 1 or n_extra < 0 or (n_extra == 0) != (strategy == RedunStrat.BINARY):
        return None
    if strategy == RedunStrat.BINARY:
        weights = binary_weights(n_dac)
    elif strategy == RedunStrat.MSB_SPLIT:
        weights = _split(n_dac, range(n_extra))
    elif strategy == RedunStrat.LSB_SPLIT:
        weights = _split(n_dac, range(n_dac - 1 - n_extra, n_dac - 1))
    elif strategy == RedunStrat.MSB_REDIST:
        weights = _msb_redist(n_dac, n_extra)
    else:
        return None
    if (
        len(weights) != n_dac + n_extra
        or min(weights) < 1
        or sum(weights) != 2**n_dac - 1
        or any(a < b for a, b in pairwise(weights))
        or min(tolerance_units(weights)) < 0
    ):
        return None
    return weights


def is_valid_caparray_config(p: CapArrayConfig) -> bool:
    """Whether an array has these parameters (``CapArrayConfig`` refuses any other): a positive
    resolution and capacitance scale, no negative extra cycles, the scheme's weights for them (binary
    has none, every other scheme at least one), and a weight and a drive each where given."""
    if p.n_dac < 1 or p.n_extra < 0:
        return False
    if isinstance(p.cap_scale, bool) or not isinstance(p.cap_scale, int) or p.cap_scale < 1:
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
    return _calc_weights(p.n_dac, p.n_extra, p.redun_strat) is not None


def get_caparray_weights(p: CapArrayConfig) -> list[int]:
    """Return C0-first capacitor weights in chronological conversion order.

    Stage zero is the first-switched and largest capacitor. The last element
    is the final switched capacitor; the terminal BOUT decision has no CDAC
    element and is therefore not included here.
    """
    weights = list(p.weights) if p.weights is not None else _calc_weights(p.n_dac, p.n_extra, p.redun_strat)
    if weights is None or not is_valid_caparray_config(p):
        raise ValueError(f"Invalid CDAC params: {p}")
    return weights


@h.paramclass
class CapArrayParams:
    """Electrical parameters for the passive unit-length capacitor array."""

    cdac = h.Param(dtype=CapArrayConfig, desc="CDAC electrical sizing", default=CapArrayConfig())
    unit_cap = h.Param(
        dtype=h.Scalar | None,
        desc="Unit capacitance (a weight's main less difference); None: the config's (unit_capacitance_f)",
        default=None,
    )
    coarse_weight = h.Param(dtype=int, desc="Largest available unit-capacitor weight", default=64)
    active_layers = h.Param(dtype=tuple[int, ...], desc="Consecutive active metals, lowest first", default=(6,))
    unit_models = h.Param(
        dtype=tuple[h.Module, ...],
        desc="Optional PLUS/MINUS/BULK device model per active layer; empty selects ideal MOMs",
        default=(),
    )
    stack_model = h.Param(
        dtype=h.ExternalModule | None,
        desc="Optional parameterized PLUS/MINUS/BULK model for the complete stack",
        default=None,
    )
    tail_cap = h.Param(
        dtype=h.Scalar | None,
        desc="Capacitance of each minimum-length finger; None preserves the historical half-unit tail",
        default=None,
    )
    unary_rows = h.Param(
        dtype=bool,
        desc="Each chunk of the coarse weight a unary row: one main finger of the coarse weight in units, no "
        "difference finger (flow.caparray.layout.UnitLengthCapFamilyParams.unary_length)",
        default=False,
    )


def total_capacitance_f(adc_bits: int, full_scale_v: float, cap_scale: int = 1) -> float:
    """The top-plate capacitance a side at which an ``adc_bits`` converter's sampled noise, both
    sides' kT/C (2 kT / C), is 1/``cap_scale`` of its quantization noise, LSB^2 / 12 with
    LSB = 2 FS / 2^N at its differential full scale +-``full_scale_v``:
    C = cap_scale 24 kT / LSB^2 = cap_scale 6 kT 4^N / FS^2."""
    lsb_v = 2 * full_scale_v / 2**adc_bits
    return cap_scale * 24 * BOLTZMANN_J_PER_K * TEMPERATURE_K / lsb_v**2


def switched_capacitance_f(
    p: CapArrayConfig, full_scale_v: float = NOMINAL_REFERENCE_V, reference_v: float = NOMINAL_REFERENCE_V
) -> float:
    """The array's switched capacitance a side (main less difference): the switched share,
    FS / reference, of the top plate at which its n_dac + 1 bit converter's kT/C is 1/``cap_scale``
    of its quantization noise at that full scale (``total_capacitance_f``),
    cap_scale 6 kT 4^N / (FS reference). By default an ideal array at 1 V (26 fF at 10 bits x1,
    6.7 pF at 14); the layout passes the PDK's reference and the full scale the array's extraction
    gives it."""
    return total_capacitance_f(p.n_dac + 1, full_scale_v, p.cap_scale) * full_scale_v / reference_v


def unit_capacitance_f(
    p: CapArrayConfig, full_scale_v: float = NOMINAL_REFERENCE_V, reference_v: float = NOMINAL_REFERENCE_V
) -> float:
    """The unit capacitance, a weight's main less difference capacitance: the switched capacitance
    (``switched_capacitance_f``) over the total weight (2^n_dac - 1 units for every scheme; 51 aF at
    10 bits x1 for the ideal array at 1 V)."""
    return switched_capacitance_f(p, full_scale_v, reference_v) / sum(get_caparray_weights(p))


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


def is_valid_caparray_params(p: CapArrayParams) -> bool:
    """Check passive-array sizing and its coarse unit family."""

    if p.tail_cap is not None and float(p.tail_cap) < 0:
        return False
    if not isinstance(p.unary_rows, bool):
        return False
    if isinstance(p.coarse_weight, bool) or not isinstance(p.coarse_weight, int) or p.coarse_weight <= 0:
        return False
    if not p.active_layers or any(isinstance(layer, bool) or layer < 1 for layer in p.active_layers):
        return False
    if p.active_layers != tuple(range(p.active_layers[0], p.active_layers[-1] + 1)):
        return False
    if p.stack_model is not None and (
        p.unit_models
        or tuple(p.stack_model.ports) != tuple(MOM_PORTS)
        or any(port.width != 1 for port in p.stack_model.ports.values())
        or p.stack_model.paramtype is not MomCapParams
    ):
        return False
    if p.unit_models and (
        len(p.unit_models) != len(p.active_layers)
        or any(
            tuple(model.ports) != tuple(MOM_PORTS) or any(port.width != 1 for port in model.ports.values())
            for model in p.unit_models
        )
    ):
        return False
    return is_valid_caparray_config(p.cdac)


@h.bundle
class ArrayPlates:
    cap_topplate = h.Inout()
    cap_shieldplate = h.Inout()


def array_ports(n_stages: int) -> dict[str, h.Signal]:
    """Physical main/diff plate names, in the layout and extraction pin order."""
    ports = dict(ArrayPlates.signals)
    for kind in ("main", "diff"):
        for stage in range(n_stages):
            name = f"cap_botplate_{kind}<{stage}>"
            ports[name] = h.Inout(name=name)
    return ports


@h.generator
def CapArray(p: CapArrayParams) -> h.Module:
    """Generate an arbitrary-width passive main/diff unit-length array."""

    if not is_valid_caparray_params(p):
        raise ValueError(f"Invalid CDAC array params: {p}")
    weights = get_caparray_weights(p.cdac)
    partitions = _calc_weight_partitions(weights, p.coarse_weight)
    n_caps = len(weights)
    unit_cap = unit_capacitance_f(p.cdac) * 1e15 * f if p.unit_cap is None else p.unit_cap
    tail_cap = unit_cap / 2 if p.tail_cap is None else p.tail_cap

    CapArray = module_from_ports("CapArray", array_ports(n_caps))
    bottom_plates = {
        kind: tuple(net for name, net in CapArray.ports.items() if name.startswith(f"cap_botplate_{kind}<"))
        for kind in ("main", "diff")
    }

    for stage, chunks in enumerate(partitions):
        for chunk_index, chunk in enumerate(chunks):
            # a unary row: its main finger the coarse weight in units, no difference finger
            unary = p.unary_rows and chunk == p.coarse_weight
            kinds = (("main", 1),) if unary else (("main", 1), ("diff", -1))
            if p.stack_model is not None:
                for kind, sign in kinds:
                    value = unit_cap * chunk if unary else unit_cap * ((p.coarse_weight + sign * chunk) / 2) + tail_cap
                    setattr(
                        CapArray,
                        f"{kind}_{stage}_{chunk_index}",
                        p.stack_model(MomCapParams(c=value))(
                            PLUS=CapArray.cap_topplate,
                            MINUS=bottom_plates[kind][stage],
                            BULK=CapArray.cap_shieldplate,
                        ),
                    )
                continue
            for layer_index, layer in enumerate(p.active_layers):
                for kind, sign in kinds:
                    # unit_cap specifies the total logical unit across the
                    # stack. Equal ideal shares preserve that electrical sizing;
                    # actual per-layer capacitances are measured by PEX.
                    finger = unit_cap * chunk if unary else unit_cap * ((p.coarse_weight + sign * chunk) / 2) + tail_cap
                    value = finger / len(p.active_layers)
                    unit = p.unit_models[layer_index] if p.unit_models else MomCap(MomCapParams(c=value))
                    setattr(
                        CapArray,
                        f"{kind}_{stage}_{chunk_index}_m{layer}",
                        h.Instance(of=unit)(
                            PLUS=CapArray.cap_topplate,
                            MINUS=bottom_plates[kind][stage],
                            BULK=CapArray.cap_shieldplate,
                        ),
                    )
    return CapArray


# Weight Calculation
