"""The latch's testbenches (``testbench``) and the one Spectre run of each (``simulate``).

The timing bench (``Bench.TIMING``) is a flip-flop and latch timing characterization:
complementary clocks, data that toggles once per cycle and crosses mid-supply a set offset before
every capturing edge (the rising edge of a flip-flop, the closing falling edge of a latch), an
initial reset, and output loads. Sweeping that offset finds setup and hold; the SR latches get set
and reset pulses on the same bench, and a divider ignores the data.

The upset bench (``Bench.UPSET``) is the radiation-hardness one: a latch takes a 1 and holds it,
and a double-exponential current pulse puts a charge on the storage node that then holds a 0 (the
C2MOS latch's inner node, the DICE latch's ``x1``, neither loaded), as a particle strike would;
whether q flips, over the charge, is the latch's critical charge.

``simulate`` runs either in Spectre (``+preset=mx``, one thread) and leaves Spectre's raw output on
disk: the signals in ``SAVES``, every ``TbParams.waveform_sample_interval_s`` (Spectre's step
bounded to it).
"""

import importlib
import math
from pathlib import Path

import hdl21 as h
import hdl21.sim as hs
from hdl21.primitives import C, Vdc, Vpulse

from flow.circuit import spectre
from flow.circuit.ports import testbench_from_ports

from .params import UPSET_FALL_S, UPSET_NODE, UPSET_RISE_S, Bench, Style, TbParams
from .subckt import Nets, netlist

# what each run saves: every port but the supplies, and each supply source's current
# (flow.pipeline.read names them)
SAVES = tuple(
    f"xtop.{net.name}"
    for net in Nets.signals.values()
    if net.vis == h.Visibility.PORT and net.usage not in (h.Usage.POWER, h.Usage.GROUND)
) + tuple(f"xtop.v{net.name}:p" for net in Nets.signals.values() if net.usage == h.Usage.POWER)


def testbench(tb: TbParams) -> h.Module:
    """The latch testbench of one run: complementary clocks, data a set offset before each
    capturing edge, an initial reset pulse, and set and reset pulses for an SR latch; or, on the
    upset bench, d high and the latch open for the first nanosecond, then holding."""

    bench, connections = testbench_from_ports(
        "LatchTb", {net.name: net for net in Nets.signals.values() if net.vis == h.Visibility.PORT}
    )
    vdd, vss = tb.vdd, bench.vss
    transition = float(tb.transition_time_s)
    edge = {"rise": transition, "fall": transition}
    clock, data = float(tb.clock_period_s), float(tb.data_period_s)
    bench.vvdd = Vdc(dc=vdd)(p=bench.vdd, n=vss)
    if tb.bench is Bench.UPSET:
        # open while d is high, closed from 1 ns on; the strike itself is a literal (``simulate``)
        hold = {"period": 1.0, "width": 0.5, "delay": 1e-9, **edge}
        bench.vclk = Vpulse(v1=vdd, v2=0.0, **hold)(p=bench.clk, n=vss)
        bench.vclkb = Vpulse(v1=0.0, v2=vdd, **hold)(p=bench.clkb, n=vss)
        for name, net in (("vd", bench.d), ("vrst", bench.rst), ("vs", bench.s), ("vr", bench.r)):
            bench.add(Vdc(dc=vdd if name == "vd" else 0.0)(p=net, n=vss), name=name)
        # q loaded as on the timing bench, qb not: it is the C2MOS latch's storage node, and a load
        # there would raise the charge a strike needs over the DICE latch's unloaded x1
        bench.cloadq = C(c=tb.cload_f)(p=bench.q, n=vss)
        bench.dut = netlist(tb.params)(**connections)
        return bench
    bench.vclk = Vpulse(v1=0.0, v2=vdd, period=clock, width=clock / 2, delay=clock / 2, **edge)(p=bench.clk, n=vss)
    bench.vclkb = Vpulse(v1=vdd, v2=0.0, period=clock, width=clock / 2, delay=clock / 2, **edge)(p=bench.clkb, n=vss)
    # the capturing edge's mid-supply time: a flip-flop's rising edge, a latch's falling (closing) one
    capture = clock / 2 + transition / 2 + (0.0 if tb.params.flop else clock / 2 + transition)
    first = max(1, math.ceil((float(tb.reset_time_s) + transition + float(tb.data_offset_s) - capture) / clock))
    # data toggles once per cycle, each mid-supply crossing data_offset_s before a capturing edge
    bench.vd = Vpulse(
        v1=0.0,
        v2=vdd,
        period=2 * clock,
        width=clock - transition,
        delay=capture + first * clock - float(tb.data_offset_s) - transition / 2,
        **edge,
    )(p=bench.d, n=vss)
    bench.vrst = Vpulse(v1=vdd, v2=0.0, period=1.0, width=0.5, delay=tb.reset_time_s, **edge)(p=bench.rst, n=vss)
    # set and reset pulses, a quarter period each and half a period apart (active low for a NAND latch)
    active, idle = (0.0, vdd) if tb.params.style is Style.SR_NAND else (vdd, 0.0)
    for name, net, delay in (("vs", bench.s, data / 4), ("vr", bench.r, 3 * data / 4)):
        bench.add(Vpulse(v1=idle, v2=active, period=data, width=data / 4, delay=delay, **edge)(p=net, n=vss), name=name)
    bench.cloadq = C(c=tb.cload_f)(p=bench.q, n=vss)
    bench.cloadqb = C(c=tb.cload_f)(p=bench.qb, n=vss)
    bench.dut = netlist(tb.params)(**connections)
    return bench


def simulate(tb: TbParams, run_dir: Path) -> Path:
    """Run ``testbench(tb)`` in Spectre in ``run_dir``: its raw transient, in nutbin, on disk (the
    reset, then ``tb.cycles`` clock cycles; an SR latch: three set and reset periods; the upset
    bench: twice the strike time, ``tb.stop_s``); the output strobed every
    ``tb.waveform_sample_interval_s``, the step bounded to it. One Spectre thread: a campaign runs
    one process per run."""

    pdk = importlib.import_module(f"pdk.{tb.pdk}")
    install = importlib.import_module(f"pdk.{tb.pdk}.hdl21.site").install
    run_dir.mkdir(parents=True, exist_ok=True)
    h.pdk.set_default(pdk.pdk_logic)
    bench = testbench(tb)
    h.pdk.compile(bench)
    interval = tb.waveform_sample_interval_s
    attrs = [*spectre.includes(install), *spectre.options(), hs.Save(list(SAVES))]
    if tb.bench is Bench.UPSET:
        # the double exponential into the storage node: its charge is the peak times the
        # difference of the time constants; hdl21 has no exponential source
        peak = float(tb.charge_c) / (UPSET_FALL_S - UPSET_RISE_S)
        strike = float(tb.upset_time_s)
        attrs.append(
            h.Literal(
                f"iupset (xtop.dut.{UPSET_NODE[tb.params.style]} 0) isource type=exp val0=0 val1={-peak:g} "
                f"td1={strike:g} tau1={UPSET_RISE_S:g} td2={strike:g} tau2={UPSET_FALL_S:g}"
            )
        )
    attrs.append(
        hs.Tran(
            tstop=tb.stop_s,
            name="tran",
            options={"strobeperiod": interval, "maxstep": interval, "strobeoutput": "strobeonly"},
        )
    )
    spectre.run(bench, attrs, run_dir)
    return run_dir / "netlist.raw"
