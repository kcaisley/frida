"""The amplifier's testbench (``testbench``) and the one Spectre run of it (``simulate``).

The small-signal bench (``Bench.AC``): a balun puts the input common mode on both inputs and half
the AC stimulus on each, with opposite signs; bias references (a diode-connected copy of the
devices each bias drives, fed their current from a supply of its own, so the amplifier's supply
current is its own), fixed cascode biases, and a load capacitor on each output. A single-ended
amplifier sits open loop at the output its mirror sets. A fully differential one has no defined
output common mode of its own, so its bench adds an ideal common-mode feedback: the outputs'
average, against a target, steers the load bias. The run: the operating point, the AC response
(``ac``), the transfer functions from every source to ``outp`` (``xf``: the inputs, so the common
mode, and the supply, for the PSRR and CMRR) and the output noise (``noise``), on one sweep.

The large-signal benches, for a single-ended amplifier: ``outp`` drives ``inn`` (unity-gain
feedback), and ``inp`` steps up and back down about the common mode (``Bench.STEP``: slew rate,
settling, overshoot) or carries a sine (``Bench.SINE``: its harmonic distortion). A fully
differential amplifier would need a common-mode feedback circuit to swing that far: the ideal one
of the small-signal bench diverges. The run: a transient, its output every
``TbParams.waveform_sample_interval_s`` (Spectre's step bounded to it).

``simulate`` runs either in Spectre (``+preset=mx``, one thread) and leaves Spectre's raw output on
disk: the signals in ``SAVES`` that the amplifier has.
"""

import importlib
from pathlib import Path

import hdl21 as h
import hdl21.sim as hs
from hdl21.primitives import C, Idc, MosType, Vcvs, Vdc, Vpulse, Vsin

from flow.circuit import spectre
from flow.circuit.ports import testbench_from_ports
from flow.layout.devices.mosfet.netlist import mos

from .params import Bench, TbParams, Topology
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


def testbench(tb: TbParams) -> h.Module:
    """The amplifier testbench of one run: a balun on the inputs, biases from reference currents,
    output loads, and for a differential output an ideal common-mode feedback; or, with a step or
    a sine, ``outp`` fed back to ``inn`` and the stimulus on ``inp``."""

    bench, connections = testbench_from_ports(
        "OtaTb", {net.name: net for net in Nets.signals.values() if net.vis == h.Visibility.PORT}
    )
    vss = bench.vss
    bench.vvdd = Vdc(dc=tb.vdd)(p=bench.vdd, n=vss)
    if tb.bench is Bench.AC:
        # the balun: the common mode on both inputs, a 1 V differential AC stimulus split between them
        bench.vinp = Vdc(dc=tb.vin_cm_v, ac=0.5)(p=bench.inp, n=vss)
        bench.vinn = Vdc(dc=tb.vin_cm_v, ac=-0.5)(p=bench.inn, n=vss)
    else:
        if tb.bench is Bench.STEP:
            half, edge, period = float(tb.vin_step_v) / 2, float(tb.transition_time_s), float(tb.step_period_s)
            stimulus = Vpulse(
                v1=float(tb.vin_cm_v) - half,
                v2=float(tb.vin_cm_v) + half,
                delay=period / 4,
                width=period / 2 - edge,
                period=period,
                rise=edge,
                fall=edge,
            )
        else:
            stimulus = Vsin(voff=tb.vin_cm_v, vamp=tb.vin_amplitude_v, freq=tb.vin_frequency_hz, td=0.0, phase=0.0)
        bench.vinp = stimulus(p=bench.inp, n=vss)
        # [Razavi-Analog] Fig. 9.7, p. 350: the amplifier as a unity-gain buffer
        # unity-gain feedback: inn is outp
        bench.vinn = Vdc(dc=0.0)(p=bench.inn, n=bench.outp)
    for name, value in (("vcasn", tb.vcasn_v), ("vcasp", tb.vcasp_v)):
        bench.add(Vdc(dc=value)(p=getattr(bench, name), n=vss), name=f"v{name}")
    # the bias references: each bias a diode-connected copy of the
    # devices it drives, fed their current. An NMOS input's tail (and bottom sources) sit on vbn
    # and carry the bias current, its loads on vbp and half of it each (a folded cascode's top
    # sources one and a half: their fold's half and their bottom source's whole); a PMOS input's
    # tail sits on vbp.
    ota = tb.params
    current = tb.iss_a
    load_current = 1.5 * current if ota.topology == Topology.FOLDED else current / 2
    if ota.input_xtors == MosType.NMOS:
        (n_w, n_l, n_current), (p_w, p_l, p_current) = (
            (ota.tail_w, ota.tail_l, current),
            (ota.load_w, ota.load_l, load_current),
        )
    else:
        (n_w, n_l, n_current), (p_w, p_l, p_current) = (
            (ota.load_w, ota.load_l, load_current),
            (ota.tail_w, ota.tail_l, current),
        )
    single = tb.single_ended
    # a differential output's load bias is the feedback's starting point; the feedback drives vbp
    vbp_start = bench.vbp if single else bench.add(h.Signal(name="vbp_start"))
    # the references draw from their own supply, so the amplifier's is its own current
    bench.vddb = h.Signal()
    bench.vvddb = Vdc(dc=tb.vdd)(p=bench.vddb, n=vss)
    bench.mbn = mos(tp=MosType.NMOS, vth=ota.vth, w=n_w, l=n_l)(d=bench.vbn, g=bench.vbn, s=vss, b=vss)
    bench.ibn = Idc(dc=n_current)(p=bench.vddb, n=bench.vbn)
    bench.mbp = mos(tp=MosType.PMOS, vth=ota.vth, w=p_w, l=p_l)(d=vbp_start, g=vbp_start, s=bench.vddb, b=bench.vddb)
    bench.ibp = Idc(dc=p_current)(p=vbp_start, n=vss)
    if not single:
        # [Razavi-Analog] Fig. 9.44, p. 377: common-mode feedback
        # ideal common-mode feedback: vbp = its start + gain x (output average - target). A higher
        # load bias lowers one stage's output common mode and, through a second stage, raises it.
        bench.cm_half, bench.cm, bench.vocm = (h.Signal() for _ in range(3))
        bench.ecm_p = Vcvs(gain=0.5)(p=bench.cm_half, n=vss, cp=bench.outp, cn=vss)
        bench.ecm_n = Vcvs(gain=0.5)(p=bench.cm, n=bench.cm_half, cp=bench.outn, cn=vss)
        bench.vvocm = Vdc(dc=tb.vout_cm_v)(p=bench.vocm, n=vss)
        gain = -tb.cmfb_gain if ota.two_stage else tb.cmfb_gain
        bench.ecmfb = Vcvs(gain=gain)(p=bench.vbp, n=vbp_start, cp=bench.cm, cn=bench.vocm)
    bench.cloadp = C(c=tb.cload_f)(p=bench.outp, n=vss)
    bench.cloadn = C(c=tb.cload_f)(p=bench.outn, n=vss)
    bench.dut = netlist(ota)(**connections)
    return bench


def _saves(tb: TbParams) -> list[str]:
    """The signals of ``SAVES`` the amplifier of ``tb`` has: no ``outn`` (nor its first stage's)
    of a single-ended one, which leaves it floating, and no first-stage outputs without a second
    stage."""
    absent = {"outn", "out1n"} if tb.single_ended else set()
    if not tb.params.two_stage:
        absent |= {"out1p", "out1n"}
    return [name for name in SAVES if name.rsplit(".", 1)[-1] not in absent]


def simulate(tb: TbParams, run_dir: Path) -> Path:
    """Run ``testbench(tb)`` in Spectre in ``run_dir`` and leave its raw output on disk: the
    small-signal bench's operating point, AC response (``ac``), output noise (``noise``) and
    transfer functions to ``outp`` (``xf``), on one sweep, in PSF ASCII (a directory); or a
    unity-gain bench's transient, in nutbin, strobed every ``tb.waveform_sample_interval_s``, the
    step bounded to it. One Spectre thread: a campaign runs one process per run."""

    pdk = importlib.import_module(f"pdk.{tb.pdk}")
    install = importlib.import_module(f"pdk.{tb.pdk}.hdl21.site").install
    run_dir.mkdir(parents=True, exist_ok=True)
    h.pdk.set_default(pdk.pdk_logic)
    bench = testbench(tb)
    h.pdk.compile(bench)
    attrs = [*spectre.includes(install), *spectre.options(), hs.Save(_saves(tb))]
    if tb.bench is Bench.AC:
        # the AC and noise analyses share one sweep (npts: points per decade)
        sweep = hs.LogSweep(start=tb.fstart_hz, stop=tb.fstop_hz, npts=tb.points_per_decade)
        attrs += [
            hs.Ac(sweep=sweep, name="ac"),
            hs.Noise(
                output=bench.outp if tb.single_ended else (bench.outp, bench.outn),
                input_source=bench.vinp,
                sweep=sweep,
                name="noise",
            ),
            # every source's transfer to outp on the same sweep; hdl21 has no transfer-function analysis
            h.Literal(f"xf (xtop.outp 0) xf start={tb.fstart_hz:g} stop={tb.fstop_hz:g} dec={tb.points_per_decade}"),
        ]
    else:
        interval = tb.waveform_sample_interval_s
        attrs.append(
            hs.Tran(
                tstop=tb.stop_s,
                name="tran",
                options={"strobeperiod": interval, "maxstep": interval, "strobeoutput": "strobeonly"},
            )
        )
    spectre.run(bench, attrs, run_dir)
    return run_dir / "netlist.raw"
