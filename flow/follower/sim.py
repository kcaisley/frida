"""The follower's testbench (``testbench``) and the one Spectre run of it (``simulate``).

The testbench: the input a DC level, current-reference biases (a diode-connected copy of the
current-source device on each bias, fed the reference current from a supply of its own, so the
follower's supply current is its own) and a capacitive load. What it drives is the run's
``Stimulus``. ``INPUT``: 1 V of AC on the input, whose response is the gain; Spectre's ``xf`` adds
every source's transfer to the output (the supply's, for the PSRR). ``OUTPUT``: the AC on a test
current into the output instead (1 V through a large resistor, its DC blocked), whose response
gives the output impedance, where a flipped follower differs from a plain one. ``STEP``: the input
stepping up about its level and back down, whose transient gives the slew rates (a source follower
pulls one way through its device, the other only with its bias current). ``simulate`` runs it in
Spectre and leaves the raw output on disk: the signals in ``SAVES``; the operating point every run
starts from (``opdc``), then the AC response (``ac``) and the transfer functions (``xf``), or the
transient, every ``TbParams.waveform_sample_interval_s`` (Spectre's step bounded to it).
"""

import importlib
from pathlib import Path

import hdl21 as h
import hdl21.sim as hs
from hdl21.primitives import C, Idc, MosType, R, Vdc, Vpulse

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
    ``tb.cload_f``, its bias references, and its input a DC level with the AC stimulus
    (``Stimulus.INPUT``), without it beside the test current into the output (``OUTPUT``), or
    stepping up about ``tb.vin_v`` a quarter period in and back down three quarters in (``STEP``)."""

    bench, connections = testbench_from_ports(
        "FollowerTb", {net.name: net for net in Nets.signals.values() if net.vis == h.Visibility.PORT}
    )
    vss = bench.vss
    bench.vvdd = Vdc(dc=tb.vdd)(p=bench.vdd, n=vss)
    if tb.stimulus is Stimulus.STEP:
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
        bench.vvin = Vdc(dc=tb.vin_v, ac=0.0 if tb.stimulus is Stimulus.OUTPUT else 1.0)(p=bench.vin, n=vss)
    # the bias references: a diode-connected copy of the current-source device on each bias, fed
    # the reference current
    follower = tb.params
    size = {"vth": follower.vth, "w": follower.bias_w, "l": follower.bias_l}
    # the references draw from their own supply, so the follower's is its own current
    bench.vddb = h.Signal()
    bench.vvddb = Vdc(dc=tb.vdd)(p=bench.vddb, n=vss)
    bench.mbn = mos(tp=MosType.NMOS, **size)(d=bench.vbn, g=bench.vbn, s=vss, b=vss)
    bench.ibn = Idc(dc=tb.iref_a)(p=bench.vddb, n=bench.vbn)
    bench.mbp = mos(tp=MosType.PMOS, **size)(d=bench.vbp, g=bench.vbp, s=bench.vddb, b=bench.vddb)
    bench.ibp = Idc(dc=tb.iref_a)(p=bench.vbp, n=vss)
    bench.cload = C(c=tb.cload_f)(p=bench.vout, n=vss)
    if tb.stimulus is Stimulus.OUTPUT:
        # the output test current: 1 V of AC through a large resistor, its DC blocked by 1 F, into
        # vout. VLSIR writes a controlled current source's gain under a name Spectre ignores.
        bench.test, bench.test_dc = h.Signal(), h.Signal()
        bench.vtest = Vdc(dc=0.0, ac=1.0)(p=bench.test, n=vss)
        bench.ctest = C(c=1.0)(p=bench.test, n=bench.test_dc)
        bench.rtest = R(r=tb.test_resistance_ohm)(p=bench.test_dc, n=bench.vout)
    bench.dut = netlist(tb.params)(**connections)
    return bench


def simulate(tb: TbParams, run_dir: Path) -> Path:
    """Run ``testbench(tb)`` in Spectre in ``run_dir``, its raw output, in nutbin, left on disk:
    the step's transient over one period (``tran``), strobed every
    ``tb.waveform_sample_interval_s``, the step bounded to it; else the AC response (``ac``) and
    every source's transfer to ``vout`` (``xf``), after the operating point every run starts from
    (``opdc``). One Spectre thread: a campaign runs one process per run."""

    pdk = importlib.import_module(f"pdk.{tb.pdk}")
    install = importlib.import_module(f"pdk.{tb.pdk}.hdl21.site").install
    run_dir.mkdir(parents=True, exist_ok=True)
    h.pdk.set_default(pdk.pdk_logic)
    bench = testbench(tb)
    h.pdk.compile(bench)
    attrs = [*spectre.includes(install), *spectre.options(), hs.Save(list(SAVES))]
    if tb.stimulus is Stimulus.STEP:
        interval = tb.waveform_sample_interval_s
        attrs.append(
            hs.Tran(
                tstop=tb.step_period_s,
                name="tran",
                options={"strobeperiod": interval, "maxstep": interval, "strobeoutput": "strobeonly"},
            )
        )
    else:
        attrs += [
            # VLSIR's npts: points per decade
            hs.Ac(sweep=hs.LogSweep(start=tb.fstart_hz, stop=tb.fstop_hz, npts=tb.points_per_decade), name="ac"),
            # every source's transfer to vout; hdl21 has no transfer-function analysis
            h.Literal(f"xf (xtop.vout 0) xf start={tb.fstart_hz:g} stop={tb.fstop_hz:g} dec={tb.points_per_decade}"),
        ]
    spectre.run(bench, attrs, run_dir)
    return run_dir / "netlist.raw"
