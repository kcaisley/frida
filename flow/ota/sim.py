"""The amplifier's testbench (``testbench``) and the one Spectre run of it (``simulate``).

The bias network (every bench): each bias from copies of the devices it drives, at the nominal
input common mode, fed from a supply of its own (``vddb``, so that the amplifier's supply current
is its own). Every bench-biased device of the amplifier sits a saturation-voltage estimate from its
rail or from the device below it: the tail and the input pair through a replica of the pair on the
tail's reference, the cascodes from diode copies on those estimates, the load and top sources from
replica stacks. The nominal input common mode is the input pair's V_GS above the tail's estimate;
the tail carries ``TbParams.iss_a`` there. The biases stay at the nominal point whatever the inputs
do.

The small-signal bench (``Bench.AC``): a balun puts the input common mode on both inputs (the
nominal one, or ``TbParams.vin_cm_v``) and half the AC stimulus on each, with opposite signs, and a
load capacitor sits on each output. A single-ended amplifier sits open loop at the output its
mirror sets. A fully differential one has no defined output common mode of its own, so its bench
adds an ideal common-mode feedback: the outputs' average, against a target in the middle of the
output's swing, steers the load bias, which it holds between the rails. The run: the operating point (with each amplifier device's
V_DS and V_D,sat, and the tail's current), the AC response (``ac``), the transfer functions from
every source to the amplifier's output (``xf``: ``outp``, or ``outp`` minus ``outn``; a single-ended
amplifier's at the nominal point also to the input common mode, ``xf_vcm``) and the output noise
(``noise``), on one sweep.

The large-signal benches, for a single-ended amplifier: ``outp`` drives ``inn`` (unity-gain
feedback), and ``inp`` steps up and back down (``Bench.STEP``: slew rate, settling, overshoot) or
carries a sine (``Bench.SINE``: its harmonic distortion), each from the nominal input common mode
into the input pair's range. A fully differential amplifier would need a common-mode feedback
circuit to swing that far: the ideal one of the small-signal bench diverges. The run: a transient,
its output every ``TbParams.waveform_sample_interval_s``, Spectre's step bounded to it.

``simulate`` runs the small-signal bench in Spectre X (``+preset=mx``, one thread) and a unity-gain
transient in Spectre at its conservative error control, which bounds the time step (Spectre X
ignores a transient's ``maxstep``, and its mx error control leaves numerical harmonics in a sine's
spectrum near the amplifier's own), and leaves Spectre's raw output on disk: the signals in
``SAVES`` that the amplifier has.
"""

import importlib
from pathlib import Path

import hdl21 as h
import hdl21.sim as hs
from hdl21.primitives import C, Idc, MosType, Vcvs, Vdc, Vpulse, Vsin

from flow.circuit import spectre
from flow.circuit.ports import testbench_from_ports
from flow.layout.devices.mosfet.netlist import mos

from .params import Bench, Params, TbParams, Topology
from .subckt import Nets, netlist

# what a run saves: every port but the supplies, the nets marked to save inside the amplifier, and
# each supply source's current (flow.pipeline.read names them)
SAVES = tuple(
    name
    for net in Nets.signals.values()
    for name in (
        (f"xtop.{net.name}",)
        if net.vis == h.Visibility.PORT and net.usage not in (h.Usage.POWER, h.Usage.GROUND)
        else (f"xtop.dut.{net.name}",)
        if net.props.get("save")
        else ()
    )
) + tuple(f"xtop.v{net.name}:p" for net in Nets.signals.values() if net.usage == h.Usage.POWER)
# what the small-signal run also saves of each amplifier transistor at its operating point: V_DS and
# V_D,sat, and a tail's drain current (flow.pipeline.read keeps them as ``v["<device>:<value>"]``)
DEVICE_SAVES = ("vds", "vdsat")
TAIL_SAVES = ("ids",)
# [Razavi-Analog] Example 2.2, p. 18: a device stays saturated while its gate rises less than V_TH
# above its drain (an NMOS; a PMOS's drain less than |V_TH| above its gate)
# not in the reference texts: the bench puts each current source's drain the V_GS of a copy carrying
# a hundredth of its current past its gate; two decades down a copy sits near or below threshold,
# so the drain keeps the device saturated
SATURATION_CURRENT_RATIO = 100.0


@h.paramclass
class _ClampParams:
    """A voltage-controlled voltage source's gain and its output's limits (Spectre's vcvs)."""

    gain = h.Param(dtype=float, desc="Gain (V/V)")
    min = h.Param(dtype=float, desc="Lowest output voltage (V)")
    max = h.Param(dtype=float, desc="Highest output voltage (V)")


# Spectre's own voltage-controlled voltage source, its output held between two limits: the ideal
# feedback's last stage, which saturates at the rails as a real one would
_Clamp = h.ExternalModule(
    name="vcvs",
    port_list=[h.Inout(name=name) for name in ("p", "n", "ps", "ns")],
    paramtype=_ClampParams,
    desc="Spectre vcvs with output limits",
)


class _Network:
    """The bias network under construction on a bench: its devices are copies (``tp``, a size as
    width and length multiples) of the amplifier's, at its threshold flavour ``vth``, fed from the
    reference supply."""

    def __init__(self, bench: h.Module, vth) -> None:
        self.bench, self.vth = bench, vth

    def rail(self, tp: MosType) -> h.Signal:
        """A device type's source rail: ground for an NMOS, the reference supply for a PMOS."""
        return self.bench.vss if tp is MosType.NMOS else self.bench.vddb

    def device(self, name: str, tp: MosType, size: tuple[int, int], d, g, s) -> None:
        """A copy of an amplifier device, its body on its type's rail."""
        self.bench.add(mos(tp=tp, vth=self.vth, w=size[0], l=size[1])(d=d, g=g, s=s, b=self.rail(tp)), name=name)

    def current(self, name: str, tp: MosType, node, value: float) -> None:
        """A reference current into ``node`` from the reference supply (for an NMOS above it) or out
        of it into ground (for a PMOS below it)."""
        bench = self.bench
        feed = (bench.vddb, node) if tp is MosType.NMOS else (node, bench.vss)
        bench.add(Idc(dc=value)(p=feed[0], n=feed[1]), name=name)

    def node(self, name: str, given=None) -> h.Signal:
        """A new node of the network, or the bench's net ``given``."""
        return self.bench.add(h.Signal(name=name)) if given is None else given

    def diode(self, name: str, tp: MosType, size: tuple[int, int], value: float, source, given=None) -> h.Signal:
        """A diode-connected copy carrying ``value`` from ``source`` (its rail, or a node the network
        holds): its gate and drain."""
        node = self.node(name, given)
        self.device(f"M{name}", tp, size, node, node, source)
        self.current(f"i{name}", tp, node, value)
        return node

    def drain(self, name: str, tp: MosType, gate, low) -> h.Signal:
        """A node at the drain level that keeps a device of gate ``gate`` saturated
        (``SATURATION_CURRENT_RATIO``): the gate less (an NMOS) or plus (a PMOS) the V_GS of its
        copy at a hundredth of its current, whose drain is ``low``. An NMOS's drain is to stay above
        it, a PMOS's below it."""
        node = self.node(name)
        self.bench.add(Vcvs(gain=1.0)(p=node, n=self.rail(tp), cp=gate, cn=low), name=f"e{name}")
        return node

    def average(self, name: str, first, second) -> h.Signal:
        """A node at the average of two nodes' voltages: half of each, stacked."""
        bench, part, node = self.bench, self.node(f"{name}_part"), self.node(name)
        bench.add(Vcvs(gain=0.5)(p=part, n=bench.vss, cp=first, cn=bench.vss), name=f"e{name}_part")
        bench.add(Vcvs(gain=0.5)(p=node, n=part, cp=second, cn=bench.vss), name=f"e{name}")
        return node

    def pair(self, name: str, tp: MosType, pair: tuple[int, int], tail: tuple[int, int], vcm, value: float, given=None):
        """[Razavi-Analog] Example 5.6, Fig. 5.20(b), p. 145: a replica of the input pair (gates on
        ``vcm``) on a copy of the tail, the reference ``value`` into the pair's drains and the
        tail copy's gate on them, so that the copy sits at the tail's V_DS: the tail's gate."""
        gate, source = self.node(f"{name}_gate", given), self.node(f"{name}_source")
        for side in ("p", "n"):
            self.device(f"M{name}_in_{side}", tp, pair, gate, vcm, source)
        self.device(f"M{name}_tail", tp, tail, source, gate, self.rail(tp))
        self.current(f"i{name}", tp, gate, value)
        return gate

    def stack(
        self,
        name: str,
        tp: MosType,
        size: tuple[int, int],
        cascode: tuple[int, int],
        vcas,
        value: float,
        drawn=0.0,
        given=None,
    ) -> h.Signal:
        """[Razavi-Analog] Fig. 5.18(b), p. 144: a copy of a current source under a copy of its
        cascode (gate ``vcas``), the source copy's gate on the cascode copy's drain, carrying
        ``value`` through both and ``drawn`` besides from the node between them: the source's gate."""
        gate, middle = self.node(f"{name}_gate", given), self.node(f"{name}_middle")
        self.device(f"M{name}", tp, size, middle, gate, self.rail(tp))
        self.device(f"M{name}_cas", tp, cascode, gate, vcas, middle)
        self.current(f"i{name}", tp, gate, value)
        if drawn:
            self.current(f"i{name}_drawn", tp, middle, drawn)
        return gate


def _bias(bench: h.Module, tb: TbParams) -> dict[str, h.Signal]:
    """The bias network of ``tb``'s amplifier on ``bench``: the nominal input common mode
    (``bench.vcm``) and each bias the amplifier uses, by its port's name (``vbn``, ``vbp``,
    ``vcasn``, ``vcasp``); a differential amplifier's load bias before the feedback (``vbp_start``)
    and the feedback's target (``vocm``).

    Each current source's drain level comes in two passes, feed-forward: a diode copy's V_GS gives
    a first level, a replica at that level the gate the source takes there (above its diode's, the
    drain being lower), and that gate the final level; the source then sits at the final level, at
    a gate no higher than the replica's, so saturated."""

    ota, current = tb.params, tb.iss_a
    net, vss, vddb = _Network(bench, ota.vth), bench.vss, bench.vddb
    tail, pair, load, cascode = (
        (ota.tail_w, ota.tail_l),
        (ota.in_w, ota.in_l),
        (ota.load_w, ota.load_l),
        (ota.cas_w, ota.cas_l),
    )
    bench.vcm = h.Signal()
    if ota.topology is Topology.SELF_BIASED:
        # its own drains bias its tails: the bench holds its inputs at mid-supply alone
        bench.ecm = Vcvs(gain=0.5)(p=bench.vcm, n=vss, cp=vddb, cn=vss)
        return {}
    nmos = ota.input_xtors is MosType.NMOS
    diff, other = (MosType.NMOS, MosType.PMOS) if nmos else (MosType.PMOS, MosType.NMOS)

    # the tail: a first level from its diode copy, the pair's V_GS above it, a replica of the pair
    # there; the final level from the replica's gate, the input common mode the pair's V_GS above
    # [Razavi-Analog] Eq. (4.1), p. 105: the input common mode a V_GS1 above the tail's drain level
    tail_low = net.diode("tail_low", diff, tail, current / SATURATION_CURRENT_RATIO, net.rail(diff))
    tail_full = net.diode("tail_full", diff, tail, current, net.rail(diff))
    first = net.diode("cm_first", diff, pair, current / 2, net.drain("tail_first", diff, tail_full, tail_low))
    first = net.pair("tail_first", diff, pair, tail, first, current)
    tail_drain = net.drain("tail_drain", diff, first, tail_low)
    net.diode("cm", diff, pair, current / 2, tail_drain, bench.vcm)
    tail_bias = net.pair("tail", diff, pair, tail, bench.vcm, current, bench.vbn if nmos else bench.vbp)
    biases = {"vbn" if nmos else "vbp": tail_bias}
    if ota.topology is Topology.FIVE_T:
        return biases

    # the cascodes and the load side: an NMOS input, the differential amplifiers (Params)
    if ota.topology is Topology.TELESCOPIC:
        # [Razavi-Analog] Sec. 9.2.1, Fig. 9.9, p. 351: the input pair's drain kept saturated, the
        # input cascode's gate a V_GS above it
        in_low = net.diode("in_low", diff, pair, current / 2 / SATURATION_CURRENT_RATIO, net.rail(diff))
        in_drain = net.drain("in_drain", diff, bench.vcm, in_low)
        net.diode("cas_in", diff, cascode, current / 2, in_drain, bench.vcasn)
        # the load's drain kept saturated, the load cascode's gate a V_GS below it, and the load's gate
        # from a replica of the two
        source, value, drawn = load, current / 2, 0.0
    else:
        # FOLDED: the bottom sources copy the tail by width at the tail's gate, the bottom cascode's
        # gate a V_GS above their drain level; the top sources carry their fold's half of the tail
        # current and their bottom source's, their fold cascode the bottom source's
        value = current * ota.load_w / ota.tail_w
        bottom_low = net.diode("bottom_low", diff, load, value / SATURATION_CURRENT_RATIO, net.rail(diff))
        in_drain = net.drain("bottom_drain", diff, tail_bias, bottom_low)
        net.diode("cas_bottom", diff, cascode, value, in_drain, bench.vcasn)
        source, drawn = load, current / 2
    low = net.diode("load_low", other, source, (value + drawn) / SATURATION_CURRENT_RATIO, vddb)
    full = net.diode("load_full", other, source, value + drawn, vddb)
    vcas = net.diode("cas_load_first", other, cascode, value, net.drain("load_first", other, full, low))
    first = net.stack("load_first", other, source, cascode, vcas, value, drawn)
    load_drain = net.drain("load_drain", other, first, low)
    net.diode("cas_load", other, cascode, value, load_drain, bench.vcasp)
    start = net.stack("load", other, source, cascode, bench.vcasp, value, drawn)
    if ota.two_stage:
        # a second stage's output swings between its gain device and its current source: mid-supply
        target = net.node("vocm")
        bench.evocm = Vcvs(gain=0.5)(p=target, n=vss, cp=vddb, cn=vss)
    else:
        # the output swings between the two cascodes' sources: its middle
        target = net.average("vocm", in_drain, load_drain)
    return biases | {"vcasn": bench.vcasn, "vcasp": bench.vcasp, "vbp_start": start, "vocm": target}


def testbench(tb: TbParams) -> h.Module:
    """The amplifier testbench of one run: the bias network, a balun on the inputs and the output
    loads, for a differential output an ideal common-mode feedback; or, with a step or a sine,
    ``outp`` fed back to ``inn`` and the stimulus on ``inp``."""

    ports = {net.name: net for net in Nets.signals.values() if net.vis == h.Visibility.PORT}
    bench, connections = testbench_from_ports("OtaTb", ports)
    vss = bench.vss
    bench.vvdd = Vdc(dc=tb.vdd)(p=bench.vdd, n=vss)
    # the references draw from their own supply, so the amplifier's is its own current
    bench.vddb = h.Signal()
    bench.vvddb = Vdc(dc=tb.vdd)(p=bench.vddb, n=vss)
    biases = _bias(bench, tb)
    single = tb.single_ended
    if not single:
        # [Razavi-Analog] Sec. 9.7.1, Fig. 9.44, p. 377: common-mode feedback
        # ideal common-mode feedback: vbp = its start + gain x (output average - target). A higher
        # load bias lowers one stage's output common mode and, through a second stage, raises it.
        bench.cm_half, bench.cm, bench.vbp_copy, bench.vbp_free = (h.Signal() for _ in range(4))
        # the outputs' average: half of each, stacked
        bench.ecm_p = Vcvs(gain=0.5)(p=bench.cm_half, n=vss, cp=bench.outp, cn=vss)
        bench.ecm_n = Vcvs(gain=0.5)(p=bench.cm, n=bench.cm_half, cp=bench.outn, cn=vss)
        gain = -tb.cmfb_gain if tb.params.two_stage else tb.cmfb_gain
        # the start copied onto a node of its own, so that the feedback's output loads the copy, not
        # the bias network's replica; the sum unbounded on a node of the feedback's alone, then held
        # between the rails on vbp
        bench.evbp_copy = Vcvs(gain=1.0)(p=bench.vbp_copy, n=vss, cp=biases["vbp_start"], cn=vss)
        bench.ecmfb = Vcvs(gain=gain)(p=bench.vbp_free, n=bench.vbp_copy, cp=bench.cm, cn=biases["vocm"])
        bench.ecmfb_clamp = _Clamp(_ClampParams(gain=1.0, min=0.0, max=float(tb.vdd)))(
            p=bench.vbp, n=vss, ps=bench.vbp_free, ns=vss
        )
        biases["vbp"] = bench.vbp
    # a bias port the amplifier leaves unused sits on ground, its bench net unused, as does a
    # single-ended amplifier's outn
    for name in ("vbn", "vbp", "vcasn", "vcasp"):
        connections[name] = biases.get(name, vss)
    if single:
        connections["outn"] = vss
    if tb.bench is Bench.AC:
        # the balun: the common mode on both inputs, a 1 V differential AC stimulus split between them
        base, level = (bench.vcm, 0.0) if tb.vin_cm_v is None else (vss, float(tb.vin_cm_v))
        bench.vinp = Vdc(dc=level, ac=0.5)(p=bench.inp, n=base)
        bench.vinn = Vdc(dc=level, ac=-0.5)(p=bench.inn, n=base)
    else:
        low = tb.vin_low_offset_v
        if tb.bench is Bench.STEP:
            # [Razavi-Analog] Sec. 9.9, Fig. 9.70, p. 391: a large input step, the output slewing
            edge, period = float(tb.transition_time_s), float(tb.step_period_s)
            stimulus = Vpulse(
                v1=low,
                v2=low + float(tb.vin_step_v),
                delay=period / 4,
                width=period / 2 - edge,
                period=period,
                rise=edge,
                fall=edge,
            )
        else:
            # [Razavi-Analog] Sec. 14.1.1, Eq. (14.8), p. 579: a sinusoid at the input, the output's harmonics measured
            amplitude = float(tb.vin_amplitude_v)
            stimulus = Vsin(voff=low + amplitude, vamp=amplitude, freq=tb.vin_frequency_hz, td=0.0, phase=0.0)
        # the stimulus rides on the nominal input common mode
        bench.vinp = stimulus(p=bench.inp, n=bench.vcm)
        # [Razavi-Analog] Example 9.4, Fig. 9.7, p. 350: the amplifier as a unity-gain buffer
        # unity-gain feedback: inn is outp
        bench.vinn = Vdc(dc=0.0)(p=bench.inn, n=bench.outp)
    bench.cloadp = C(c=tb.cload_f)(p=bench.outp, n=vss)
    if not single:
        bench.cloadn = C(c=tb.cload_f)(p=bench.outn, n=vss)
    bench.dut = netlist(tb.params)(**connections)
    return bench


def _devices(params: Params) -> list[str]:
    """The amplifier's transistors by instance name (every device but a Miller capacitor)."""
    return [name for name in netlist(params).instances if name.startswith("M")]


def _saves(tb: TbParams) -> list[str]:
    """The signals of ``SAVES`` the amplifier of ``tb`` has: no ``outn`` (nor its first stage's)
    of a single-ended one, which leaves it floating, no bias it leaves unused, and no first-stage
    outputs without a second stage; in the small-signal run, each transistor's V_DS and V_D,sat and
    each tail's current (``DEVICE_SAVES``, ``TAIL_SAVES``)."""
    ota = tb.params
    absent = {"outn", "out1n"} if tb.single_ended else set()
    if not ota.two_stage:
        absent |= {"out1p", "out1n"}
    if ota.topology is Topology.SELF_BIASED:
        absent |= {"vbn", "vbp", "vcasn", "vcasp"}
    elif ota.topology is Topology.FIVE_T:
        absent |= {"vbp" if ota.input_xtors is MosType.NMOS else "vbn", "vcasn", "vcasp"}
    found = [name for name in SAVES if name.rsplit(".", 1)[-1] not in absent]
    if tb.bench is Bench.AC:
        for device in _devices(ota):
            values = DEVICE_SAVES + (TAIL_SAVES if device.startswith("Mtail") else ())
            found += [f"xtop.dut.{device}:{value}" for value in values]
    return found


def simulate(tb: TbParams, run_dir: Path) -> Path:
    """Run ``testbench(tb)`` in Spectre in ``run_dir`` and leave its raw output on disk: the
    small-signal bench's operating point, AC response (``ac``), output noise (``noise``) and
    transfer functions to the amplifier's output (``xf``), on one sweep, in PSF ASCII (a
    directory), in Spectre X; or a unity-gain bench's transient, in nutbin, strobed every
    ``tb.waveform_sample_interval_s``, in Spectre at conservative error control, the step bounded
    to the strobe interval. One Spectre thread: a campaign runs one process per run."""

    pdk = importlib.import_module(f"pdk.{tb.pdk}")
    install = importlib.import_module(f"pdk.{tb.pdk}.hdl21.site").install
    run_dir.mkdir(parents=True, exist_ok=True)
    h.pdk.set_default(pdk.pdk_logic)
    bench = testbench(tb)
    h.pdk.compile(bench)
    # the bias network's and the feedback's ideal sources make the DC matrix's pivots poor: Spectre's
    # pivot check, which its notice recommends
    pivots = hs.Options(name="dc_pivot_check", value="yes")
    attrs = [*spectre.includes(install), *spectre.options(), pivots, hs.Save(_saves(tb))]
    if tb.bench is Bench.AC:
        # the AC and noise analyses share one sweep (npts: points per decade)
        sweep = hs.LogSweep(start=tb.fstart_hz, stop=tb.fstop_hz, npts=tb.points_per_decade)
        output = "xtop.outp 0" if tb.single_ended else "xtop.outp xtop.outn"
        span = f"start={tb.fstart_hz:g} stop={tb.fstop_hz:g} dec={tb.points_per_decade}"
        attrs += [
            hs.Ac(sweep=sweep, name="ac"),
            hs.Noise(
                output=bench.outp if tb.single_ended else (bench.outp, bench.outn),
                input_source=bench.vinp,
                sweep=sweep,
                name="noise",
            ),
            # every source's transfer to the output on the same sweep; hdl21 has no transfer-function analysis
            h.Literal(f"xf ({output}) xf {span}"),
        ]
        if tb.single_ended and tb.vin_cm_v is None:
            # and to the nominal input common mode the inputs ride on, which the supplies move: the
            # PSRR holds the inputs (flow.ota.analysis)
            attrs.append(h.Literal(f"xf_vcm (xtop.vcm 0) xf {span}"))
    else:
        interval = tb.waveform_sample_interval_s
        # Spectre (not Spectre X, which disables maxstep: SPECTRE-592) at conservative error
        # control, the step no longer than the strobe interval: a sine's harmonics lie far below
        # its fundamental, under the error the mx preset tolerates
        options = {
            "strobeperiod": interval,
            "maxstep": interval,
            "strobeoutput": "strobeonly",
            "errpreset": "conservative",
        }
        attrs.append(hs.Tran(tstop=tb.stop_s, name="tran", options=options))
    spectre.run(bench, attrs, run_dir, fast=tb.bench is Bench.AC)
    return run_dir / "netlist.raw"
