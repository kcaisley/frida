"""
Operational transconductance amplifier generator for FRIDA.

Supports, with an NMOS or PMOS input pair:
- The five-transistor amplifier: a tail, the input pair and a current-mirror load (single-ended)
- The telescopic cascode: cascoded input pair and current-source load (differential)
- The folded cascode: the input pair folded into cascoded current sources (differential)
- The self-biased complementary amplifier: NMOS and PMOS pairs whose tails one side's drain drives
- An optional common-source second stage on each output, with a Miller capacitor for simulation
"""

from enum import Enum, auto
from pathlib import Path

import hdl21 as h
from hdl21.prefix import f
from hdl21.primitives import C, MosType, MosVth

from flow.circuit.ports import module_from_ports
from flow.comp.subckt import _mos
from flow.comp.subckt import write_netlist as _write_netlist


class Topology(Enum):
    FIVE_T = auto()  # tail, input pair, current-mirror load: one output, outp
    TELESCOPIC = auto()  # tail, input pair, cascodes on both, current-source load: outp and outn
    FOLDED = auto()  # tail, input pair folded into cascoded current sources: outp and outn
    SELF_BIASED = auto()  # complementary pairs, both tails driven by one side's drain: outp


@h.paramclass
class OtaParams:
    """OTA parameters.

    Device sizing uses multiplier-based scaling:
    - w: Width multiplier (w=8 means 8×Wmin)
    - l: Length multiplier (l=1 means 1×Lmin)

    This approach allows the same design to be portable across PDKs.
    """

    # Topology parameters
    topology = h.Param(dtype=Topology, desc="Amplifier topology", default=Topology.FIVE_T)
    input_xtors = h.Param(dtype=MosType, desc="Input pair type (NMOS or PMOS)", default=MosType.NMOS)
    two_stage = h.Param(dtype=bool, desc="A common-source second stage on each output", default=False)
    miller = h.Param(dtype=h.Prefixed, desc="Miller capacitor of the second stage (0: none)", default=0 * f)

    # Device sizing (multipliers of Wmin/Lmin)
    in_w = h.Param(dtype=int, desc="Input pair width multiplier", default=16)
    in_l = h.Param(dtype=int, desc="Input pair length multiplier", default=2)
    tail_w = h.Param(dtype=int, desc="Tail width multiplier", default=16)
    tail_l = h.Param(dtype=int, desc="Tail length multiplier", default=4)
    load_w = h.Param(dtype=int, desc="Load (mirror or current source) width multiplier", default=16)
    load_l = h.Param(dtype=int, desc="Load length multiplier", default=4)
    cas_w = h.Param(dtype=int, desc="Cascode width multiplier", default=16)
    cas_l = h.Param(dtype=int, desc="Cascode length multiplier", default=1)
    stage2_w = h.Param(dtype=int, desc="Second-stage input width multiplier", default=16)
    stage2_l = h.Param(dtype=int, desc="Second-stage length multiplier", default=2)
    vth = h.Param(dtype=MosVth, desc="Device Vth", default=MosVth.LOW)


def is_valid_ota_params(param: OtaParams) -> bool:
    """Check if this amplifier is valid.

    The self-biased amplifier has both input types, so its input type is NMOS by convention. A
    Miller capacitor belongs to a second stage. Every size is positive.
    """
    sizes = (
        param.in_w,
        param.in_l,
        param.tail_w,
        param.tail_l,
        param.load_w,
        param.load_l,
        param.cas_w,
        param.cas_l,
        param.stage2_w,
        param.stage2_l,
    )
    if min(sizes) <= 0 or float(param.miller) < 0:
        return False
    if param.topology == Topology.SELF_BIASED and param.input_xtors != MosType.NMOS:
        return False
    return param.two_stage or float(param.miller) == 0


@h.bundle
class OtaNets:
    inp, inn = h.Input(), h.Input()
    outp, outn = h.Output(), h.Output()
    vbn = h.Input(desc="NMOS current-source bias (tail or bottom sources)")
    vbp = h.Input(desc="PMOS current-source bias (load or top sources)")
    vcasn, vcasp = h.Input(desc="NMOS cascode bias"), h.Input(desc="PMOS cascode bias")
    vdd = h.Power(direction=h.PortDir.INOUT)
    vss = h.Ground(direction=h.PortDir.INOUT)
    out1p, out1n = (h.Signal(props=h.Properties(inner={"save": True})) for _ in range(2))


@h.generator
def Ota(param: OtaParams) -> h.Module:
    """
    OTA generator.

    Generates five-transistor, telescopic, folded-cascode or self-biased amplifiers with an
    NMOS or PMOS input pair and an optional common-source second stage.

    Uses h.Mos primitives - call pdk.compile() to convert to PDK devices.
    """
    if not is_valid_ota_params(param):
        raise ValueError(f"Invalid OTA params: {param}")

    Ota = module_from_ports("Ota", OtaNets.signals)
    # the first stage drives the outputs, or the second stage's inputs out1p/out1n
    out1p, out1n = (Ota.out1p, Ota.out1n) if param.two_stage else (Ota.outp, Ota.outn)

    if param.topology == Topology.SELF_BIASED:
        _build_self_biased(Ota, param, out1p)
    else:
        _build_first_stage(Ota, param, out1p, out1n)
    if param.two_stage:
        sides = (
            ((out1p, Ota.outp, "p"),)
            if param.topology in (Topology.FIVE_T, Topology.SELF_BIASED)
            else (
                (out1p, Ota.outp, "p"),
                (out1n, Ota.outn, "n"),
            )
        )
        for inp, out, side in sides:
            _build_second_stage(Ota, param, inp, out, side)
    return Ota


def _build_first_stage(module, param: OtaParams, outp, outn):
    """The input pair on its tail and the topology's load. For an NMOS input everything sits as
    drawn below; a PMOS input mirrors it between the rails (types and bias nets swap)."""

    #  FIVE_T                 TELESCOPIC              FOLDED
    #  load ─┬─ load          load    load             top ──┬── top
    #   (mirror)              cas_p   cas_p            fold  │  fold ── cas_p ── out
    #  in_p  │  in_n          cas_n   cas_n          in_p/in_n         cas_n ── out
    #     tail                    tail                  tail            bottom

    diff = param.input_xtors
    other = MosType.PMOS if diff == MosType.NMOS else MosType.NMOS
    on_rail, load_rail = (module.vss, module.vdd) if diff == MosType.NMOS else (module.vdd, module.vss)
    tail_bias, load_bias = (module.vbn, module.vbp) if diff == MosType.NMOS else (module.vbp, module.vbn)
    cas_in, cas_load = (module.vcasn, module.vcasp) if diff == MosType.NMOS else (module.vcasp, module.vcasn)
    vth = param.vth
    module.tail = h.Signal()

    module.Mtail = _mos(tp=diff, vth=vth, w=param.tail_w, l=param.tail_l)(
        d=module.tail, g=tail_bias, s=on_rail, b=on_rail
    )

    if param.topology == Topology.FIVE_T:
        # inp's drain is the mirror's diode side, so outp (on inn's drain) follows inp
        module.mirror = h.Signal()
        module.Min_p = _mos(tp=diff, vth=vth, w=param.in_w, l=param.in_l)(
            d=module.mirror, g=module.inp, s=module.tail, b=on_rail
        )
        module.Min_n = _mos(tp=diff, vth=vth, w=param.in_w, l=param.in_l)(
            d=outp, g=module.inn, s=module.tail, b=on_rail
        )
        module.Mload_d = _mos(tp=other, vth=vth, w=param.load_w, l=param.load_l)(
            d=module.mirror, g=module.mirror, s=load_rail, b=load_rail
        )
        module.Mload = _mos(tp=other, vth=vth, w=param.load_w, l=param.load_l)(
            d=outp, g=module.mirror, s=load_rail, b=load_rail
        )
        return

    if param.topology == Topology.TELESCOPIC:
        # inp's side drives outn and inn's outp (each input inverts to its own side's output)
        for side, gate, out in (("p", module.inp, outn), ("n", module.inn, outp)):
            drain = module.add(h.Signal(name=f"in_{side}_drain"))
            load = module.add(h.Signal(name=f"load_{side}"))
            module.add(
                _mos(tp=diff, vth=vth, w=param.in_w, l=param.in_l)(d=drain, g=gate, s=module.tail, b=on_rail),
                name=f"Min_{side}",
            )
            module.add(
                _mos(tp=diff, vth=vth, w=param.cas_w, l=param.cas_l)(d=out, g=cas_in, s=drain, b=on_rail),
                name=f"Mcas_in_{side}",
            )
            module.add(
                _mos(tp=other, vth=vth, w=param.cas_w, l=param.cas_l)(d=out, g=cas_load, s=load, b=load_rail),
                name=f"Mcas_load_{side}",
            )
            module.add(
                _mos(tp=other, vth=vth, w=param.load_w, l=param.load_l)(d=load, g=load_bias, s=load_rail, b=load_rail),
                name=f"Mload_{side}",
            )
        return

    # FOLDED: each input drain folds into a current source from the load rail; its cascode (the
    # load's type) carries the difference to the output, over a cascoded source to the input rail
    for side, gate, out in (("p", module.inp, outn), ("n", module.inn, outp)):
        fold = module.add(h.Signal(name=f"fold_{side}"))
        bottom = module.add(h.Signal(name=f"bottom_{side}"))
        module.add(
            _mos(tp=diff, vth=vth, w=param.in_w, l=param.in_l)(d=fold, g=gate, s=module.tail, b=on_rail),
            name=f"Min_{side}",
        )
        module.add(
            _mos(tp=other, vth=vth, w=param.load_w, l=param.load_l)(d=fold, g=load_bias, s=load_rail, b=load_rail),
            name=f"Mtop_{side}",
        )
        module.add(
            _mos(tp=other, vth=vth, w=param.cas_w, l=param.cas_l)(d=out, g=cas_load, s=fold, b=load_rail),
            name=f"Mcas_fold_{side}",
        )
        module.add(
            _mos(tp=diff, vth=vth, w=param.cas_w, l=param.cas_l)(d=out, g=cas_in, s=bottom, b=on_rail),
            name=f"Mcas_bottom_{side}",
        )
        module.add(
            _mos(tp=diff, vth=vth, w=param.load_w, l=param.load_l)(d=bottom, g=tail_bias, s=on_rail, b=on_rail),
            name=f"Mbottom_{side}",
        )


def _build_self_biased(module, param: OtaParams, out):
    """A complementary amplifier biasing itself: NMOS and PMOS input pairs on their own tails,
    inp's drains (``tail_g``) driving both tails' gates; the output on inn's drains."""

    module.tail_n, module.tail_p, module.tail_g = h.Signal(), h.Signal(), h.Signal()
    vth = param.vth
    module.Mtail_n = _mos(tp=MosType.NMOS, vth=vth, w=param.tail_w, l=param.tail_l)(
        d=module.tail_n, g=module.tail_g, s=module.vss, b=module.vss
    )
    module.Mtail_p = _mos(tp=MosType.PMOS, vth=vth, w=2 * param.tail_w, l=param.tail_l)(
        d=module.tail_p, g=module.tail_g, s=module.vdd, b=module.vdd
    )
    for tp, tail, rail, w in (
        (MosType.NMOS, module.tail_n, module.vss, param.in_w),
        (MosType.PMOS, module.tail_p, module.vdd, 2 * param.in_w),
    ):
        pol = "n" if tp == MosType.NMOS else "p"
        module.add(
            _mos(tp=tp, vth=vth, w=w, l=param.in_l)(d=module.tail_g, g=module.inp, s=tail, b=rail),
            name=f"Min_p_{pol}",
        )
        module.add(_mos(tp=tp, vth=vth, w=w, l=param.in_l)(d=out, g=module.inn, s=tail, b=rail), name=f"Min_n_{pol}")


def _build_second_stage(module, param: OtaParams, inp, out, side: str):
    """A common-source stage from a first-stage output: the input pair's type gains (its gate on
    the first stage's load side), a current source of the other type from vbn or vbp, and the
    Miller capacitor across it."""

    # the first stage's output sits near its load rail: the second stage's gain device is the load's type
    gain = MosType.PMOS if param.input_xtors == MosType.NMOS else MosType.NMOS
    source = MosType.NMOS if gain == MosType.PMOS else MosType.PMOS
    gain_rail, source_rail = (module.vdd, module.vss) if gain == MosType.PMOS else (module.vss, module.vdd)
    bias = module.vbn if source == MosType.NMOS else module.vbp
    module.add(
        _mos(tp=gain, vth=param.vth, w=param.stage2_w, l=param.stage2_l)(d=out, g=inp, s=gain_rail, b=gain_rail),
        name=f"Mstage2_{side}",
    )
    module.add(
        _mos(tp=source, vth=param.vth, w=param.stage2_w, l=param.load_l)(d=out, g=bias, s=source_rail, b=source_rail),
        name=f"Mstage2_src_{side}",
    )
    if float(param.miller) > 0:
        module.add(C(c=param.miller)(p=out, n=inp), name=f"Cmiller_{side}")


def write_netlist(params: OtaParams, path: Path, pdk) -> Path:
    """The amplifier after ``pdk``'s compile, as one flat SPICE subcircuit named after ``path``
    (``flow.comp.subckt.write_netlist``: devices fingered to the row cells in whole unit widths)."""

    return _write_netlist(params, path, pdk, generator=Ota, nets=OtaNets)


# ==== Named amplifiers ====

CASES = {
    # five-transistor amplifier, NMOS input (Usb2Phy NmosOpAmp5T, BAG diffamp)
    "five_t": OtaParams(),
    # five-transistor amplifier, PMOS input (Usb2Phy PmosOpAmp5T)
    "five_t_pmos": OtaParams(input_xtors=MosType.PMOS),
    # telescopic cascode, NMOS input (CT-DS stage1_telescopic_amplifier)
    "telescopic": OtaParams(topology=Topology.TELESCOPIC),
    # folded cascode, NMOS input (Usb2Phy Fcasc, without its bias network)
    "folded": OtaParams(topology=Topology.FOLDED),
    # self-biased complementary amplifier (bag3_analog diffamp_self_biased)
    "self_biased": OtaParams(topology=Topology.SELF_BIASED),
    # telescopic first stage with common-source second stages (CT-DS two_stage_amplifier, no Miller RC)
    "two_stage": OtaParams(topology=Topology.TELESCOPIC, two_stage=True),
}
