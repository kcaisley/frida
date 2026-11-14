"""The follower's testbench (``testbench``) and the one Spectre run of it (``simulate``).

The testbench: the input a DC level, current-reference biases (a diode-connected copy of the
current-source device on each bias, fed the reference current from a supply of its own, so the
follower's supply current is its own) and a capacitive load. What it drives is the run's
``Stimulus``. ``INPUT``: 1 V of AC on the input, whose response is the gain; Spectre's ``xf`` adds
every source's transfer to the output: the supplies' (for the PSRR) and that of a test current of
0 A into the output (``itest``), the output impedance, where a flipped follower differs from a
plain one. ``STEP``: the input stepping up about its level and back down, whose transient gives
the slew rate of the edge that slews (a source follower pulls one way through its device,
settling linearly, and the other only with its bias current, slewing) and each edge's transition
time and settling; run at the bench's step and at half of it, which tells the two apart.
``simulate`` runs it in Spectre, on the kit's typical models at 25 C, and leaves the raw output on disk: the signals in ``SAVES``, from
the analyses in the netlist's order: the operating point every run starts from (``opdc``), then
the transfer functions (``xf``), where the run asks (``TbParams.dc_step_v``) the input's DC sweep
from ground to the supply (``dc``), and the AC response (``ac``); or, after ``opdc``, the transient
(``tran``), written at its strobes alone, every ``TbParams.waveform_sample_interval_s``.
"""

import importlib
from pathlib import Path

import hdl21 as h
import hdl21.sim as hs
from hdl21.primitives import C, Idc, MosType, Vdc, Vpulse

from flow.circuit import spectre
from flow.circuit.ports import testbench_from_ports
from flow.layout.devices.mosfet.netlist import mos

from .params import Stimulus, TbParams
from .subckt import Nets, netlist

# what each run saves: every port but the supplies, the nets marked to save inside the follower,
# and each supply source's current (flow.pipeline.read names them)
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
    """The follower testbench of one run: the follower ``tb.params`` at supply ``tb.vdd`` into
    ``tb.cload_f``, its bias references, and its input a DC level with the AC stimulus beside a test
    current of 0 A into the output (``Stimulus.INPUT``), or stepping up about ``tb.vin_v`` a quarter
    period in and back down three quarters in (``STEP``)."""

    bench, connections = testbench_from_ports(
        "FollowerTb", {net.name: net for net in Nets.signals.values() if net.vis == h.Visibility.PORT}
    )
    vss = bench.vss
    bench.vvdd = Vdc(dc=tb.vdd)(p=bench.vdd, n=vss)
    if tb.stimulus is Stimulus.STEP:
        # [Razavi-Analog] Eq. (9.58), p. 390 and Fig. 9.70, p. 391: a step's response, its slope in
        # proportion to the step where the circuit settles linearly, a ramp where it slews (the
        # bench's two step sizes, runs.testbenches); [Baker] Sec. 21.2.4, p. 703: a source
        # follower's current source alone discharges the load on one edge
        half, edge = float(tb.step_v) / 2, tb.transition_time_s
        bench.vvin = Vpulse(
            v1=float(tb.vin_v) - half,
            v2=float(tb.vin_v) + half,
            delay=float(tb.step_period_s) / 4,
            width=float(tb.step_period_s) / 2 - float(edge),
            period=tb.step_period_s,
            rise=edge,
            fall=edge,
        )(p=bench.vin, n=vss)
    else:
        # [Razavi-Analog] Eq. (3.8), Fig. 3.4, p. 48: the gain, the output per volt of input; into
        # C_L from an ideal source (R_S = 0) the follower's pole is g_m / (C_L + C_GS)
        # ([Razavi-Analog] Eqs. (6.55)-(6.56), p. 189), and its output impedance falls with
        # frequency from 1/g_m ([Razavi-Analog] Eq. (6.64), Fig. 6.28(b), p. 192)
        bench.vvin = Vdc(dc=tb.vin_v, ac=1.0)(p=bench.vin, n=vss)
        # the output test current: 0 A from ground into vout, whose transfer to vout (xf) is the
        # impedance the output node presents, the input at AC ground ([Razavi-Analog] Fig. 3.39,
        # p. 71: a test source at the output; not in the reference texts: a source of 0 A read
        # through Spectre's xf)
        bench.itest = Idc(dc=0.0)(p=vss, n=bench.vout)
    # the bias references: a diode-connected copy of the current-source device on each bias, fed
    # the reference current ([Razavi-Analog] Fig. 5.5(b), p. 136: the basic current mirror)
    follower = tb.params
    size = {"vth": follower.vth, "w": follower.bias_w, "l": follower.bias_l}
    # the references draw from their own supply, so the follower's is its own current (not in the
    # reference texts: the bench's convention; the PSRR takes one ripple on both supplies, as if
    # the references were ideal currents into diodes on the follower's supply,
    # analysis.analyze_transfer)
    bench.vddb = h.Signal()
    bench.vvddb = Vdc(dc=tb.vdd)(p=bench.vddb, n=vss)
    bench.mbn = mos(tp=MosType.NMOS, **size)(d=bench.vbn, g=bench.vbn, s=vss, b=vss)
    bench.ibn = Idc(dc=tb.iref_a)(p=bench.vddb, n=bench.vbn)
    bench.mbp = mos(tp=MosType.PMOS, **size)(d=bench.vbp, g=bench.vbp, s=bench.vddb, b=bench.vddb)
    bench.ibp = Idc(dc=tb.iref_a)(p=bench.vbp, n=vss)
    # [Razavi-Analog] Sec. 6.7.1, p. 204: the load capacitance C_L at the output node
    bench.cload = C(c=tb.cload_f)(p=bench.vout, n=vss)
    bench.dut = netlist(tb.params)(**connections)
    return bench


def simulate(tb: TbParams, run_dir: Path) -> Path:
    """Run ``testbench(tb)`` in Spectre in ``run_dir``, its raw output, in nutbin, left on disk:
    after the operating point every run starts from (``opdc``), the step's transient to
    ``tb.tran_stop_s`` (``tran``), written at its strobes alone (``strobeperiod``
    ``tb.waveform_sample_interval_s``, ``strobeoutput=strobeonly``); else, in the netlist's order,
    every source's transfer to ``vout`` (``xf``: the supplies', the output test current's), where
    ``tb.dc_step_v`` is not 0 the input's DC sweep (``dc``), and the AC response (``ac``). One
    Spectre thread: a campaign runs one process per run."""

    pdk = importlib.import_module(f"pdk.{tb.pdk}")
    install = importlib.import_module(f"pdk.{tb.pdk}.hdl21.site").install
    run_dir.mkdir(parents=True, exist_ok=True)
    h.pdk.set_default(pdk.pdk_logic)
    bench = testbench(tb)
    h.pdk.compile(bench)
    # the kit's typical models (spectre.includes' default corner) at 25 C (spectre.options')
    attrs = [*spectre.includes(install), *spectre.options(), hs.Save(list(SAVES))]
    if tb.stimulus is Stimulus.STEP:
        interval = tb.waveform_sample_interval_s
        attrs.append(
            # the output written at the strobes alone; Spectre X chooses its own steps (it disables
            # maxstep)
            hs.Tran(
                tstop=tb.tran_stop_s,
                name="tran",
                options={"strobeperiod": interval, "strobeoutput": "strobeonly"},
            )
        )
    else:
        attrs += [
            # VLSIR's npts: points per decade
            hs.Ac(sweep=hs.LogSweep(start=tb.fstart_hz, stop=tb.fstop_hz, npts=tb.points_per_decade), name="ac"),
            # every source's transfer to vout; hdl21 has no transfer-function analysis
            # ([Baker] Fig. 24.27, p. 820: the supply's AC gain to the output, for the PSRR)
            # the limits written in full, as hs.Ac writes its own, so both sweep the same points
            h.Literal(f"xf (xtop.vout 0) xf start={tb.fstart_hz!r} stop={tb.fstop_hz!r} dec={tb.points_per_decade}"),
        ]
        if tb.dc_step_v:
            # the input swept in DC from ground to the supply: the output over it (Sweep.x the input),
            # the follower's input-output characteristic ([Razavi-Analog] Fig. 3.34(c), p. 68;
            # [Baker] Fig. 21.42, p. 705)
            attrs.append(
                h.Literal(f"dc dc dev=xtop.vvin param=dc start=0 stop={float(tb.vdd)!r} step={tb.dc_step_v!r}")
            )
    spectre.run(bench, attrs, run_dir)
    return run_dir / "netlist.raw"
