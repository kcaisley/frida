"""The latch's testbenches (``testbench``) and the one Spectre run of each (``simulate``).

The timing bench (``Bench.TIMING``) is a flip-flop and latch timing characterization:
complementary clocks, data that toggles once per cycle and crosses mid-supply a set offset before
every capturing edge (the rising edge of a flip-flop, the closing falling edge of a latch), an
initial reset, and output loads. Sweeping that offset finds setup and hold; the SR latches get set
and reset pulses on the same bench. An input the design does not use (a divider's d, a TSPC
circuit's clkb, rst without a reset, an SR latch's clocks and d, a clocked design's s and r) is
held at a fixed level by a DC source.

The upset bench (``Bench.UPSET``) is the radiation-hardness one: a latch takes a 1 and holds it,
and a double-exponential current pulse puts a charge on the storage node that then holds a 0 (the
C2MOS latch's inner node qb, loaded as on the timing bench; the DICE latch's ``x1``, internal and
unloaded), as a particle strike would; whether q flips, over the charge, is the latch's critical
charge.

``simulate`` runs either in Spectre (``+preset=mx``, one thread) and leaves Spectre's raw output on
disk: the signals in ``SAVES``, strobed every ``TbParams.waveform_sample_interval_s`` (the points
written; Spectre X chooses its own time steps).
"""

import importlib
import math
from pathlib import Path

import hdl21 as h
import hdl21.sim as hs
from hdl21.primitives import C, Vdc, Vpulse

from flow.circuit import spectre
from flow.circuit.ports import testbench_from_ports

from .params import CLOCKED_STYLES, UPSET_FALL_S, UPSET_NODE, UPSET_RISE_S, Bench, Style, TbParams
from .subckt import Nets, netlist

# what each run saves: every port but the supplies, each supply source's current, and the current
# of each input's source (flow.pipeline.read names them), the charge the inputs' drivers deliver
SAVES = (
    tuple(
        f"xtop.{net.name}"
        for net in Nets.signals.values()
        if net.vis == h.Visibility.PORT and net.usage not in (h.Usage.POWER, h.Usage.GROUND)
    )
    + tuple(f"xtop.v{net.name}:p" for net in Nets.signals.values() if net.usage == h.Usage.POWER)
    + tuple(
        f"xtop.v{net.name}:p"
        for net in Nets.signals.values()
        if net.vis == h.Visibility.PORT and net.direction == h.PortDir.INPUT
    )
)


def testbench(tb: TbParams) -> h.Module:
    """The latch testbench of one run: complementary clocks, data a set offset before each
    capturing edge, an initial reset pulse, and set and reset pulses for an SR latch, each input the
    design does not use at a fixed level; or, on the upset bench, d high and the latch open until
    ``tb.write_time_s``, then holding. q and qb carry ``tb.cload_f`` on both benches."""

    bench, connections = testbench_from_ports(
        "LatchTb", {net.name: net for net in Nets.signals.values() if net.vis == h.Visibility.PORT}
    )
    vdd, vss, design = tb.vdd, bench.vss, tb.params
    # not in the reference texts: every pulse ramps linearly over transition_time_s, Spectre's rise
    # and fall, 0 to 100 %, so its 10 to 90 % time is 0.8 times it
    # [Baker] Fig. 10.9, p. 333: t_r, an input's rise time between its 10 % and 90 % points
    transition = float(tb.transition_time_s)
    edge = {"rise": transition, "fall": transition}
    clock, data = float(tb.clock_period_s), float(tb.data_period_s)
    clocked = design.style in CLOCKED_STYLES
    bench.vvdd = Vdc(dc=vdd)(p=bench.vdd, n=vss)
    bench.cloadq = C(c=tb.cload_f)(p=bench.q, n=vss)
    bench.cloadqb = C(c=tb.cload_f)(p=bench.qb, n=vss)
    bench.dut = netlist(design)(**connections)
    if tb.bench is Bench.UPSET:
        # open while d is high, closed from write_time_s on; the strike itself is a literal (``simulate``)
        hold = {"period": 1.0, "width": 0.5, "delay": float(tb.write_time_s), **edge}
        bench.vclk = Vpulse(v1=vdd, v2=0.0, **hold)(p=bench.clk, n=vss)
        bench.vclkb = Vpulse(v1=0.0, v2=vdd, **hold)(p=bench.clkb, n=vss)
        for name, net in (("vd", bench.d), ("vrst", bench.rst), ("vs", bench.s), ("vr", bench.r)):
            bench.add(Vdc(dc=vdd if name == "vd" else 0.0)(p=net, n=vss), name=name)
        return bench
    # [Baker] Sec. 13.3, p. 400: a flip-flop needs fast clock edges, so ideal sources drive the clocks
    # [Razavi-PLL] Fig. 15.12, p. 460: complementary clocks overlap during their edges; here of
    # zero skew, the edges alone overlapping
    # Spectre's width is the flat top between the edges: T/2 - t_r of it leaves the clock high for
    # half the period between its mid-supply crossings, a 50 % duty cycle
    high = clock / 2 - transition
    if clocked:
        bench.vclk = Vpulse(v1=0.0, v2=vdd, period=clock, width=high, delay=clock / 2, **edge)(p=bench.clk, n=vss)
    else:
        bench.vclk = Vdc(dc=0.0)(p=bench.clk, n=vss)
    if clocked and design.style is not Style.TSPC:
        bench.vclkb = Vpulse(v1=vdd, v2=0.0, period=clock, width=high, delay=clock / 2, **edge)(p=bench.clkb, n=vss)
    else:
        bench.vclkb = Vdc(dc=0.0)(p=bench.clkb, n=vss)
    if clocked and not design.divider:
        # the capturing edge's mid-supply time: a flip-flop's rising edge, a latch's falling (closing) one
        capture = clock / 2 + transition / 2 + (0.0 if design.flop else clock / 2)
        first = max(1, math.ceil((float(tb.reset_time_s) + transition + float(tb.data_offset_s) - capture) / clock))
        # [Baker] Fig. 13.25, p. 401: setup, d applied t_s before the clock edge
        # [Baker] Fig. 13.26, p. 402: hold, d held t_h after it (a negative offset: d changes after it)
        # data toggles once per cycle, each mid-supply crossing data_offset_s before a capturing edge
        bench.vd = Vpulse(
            v1=0.0,
            v2=vdd,
            period=2 * clock,
            width=clock - transition,
            delay=capture + first * clock - float(tb.data_offset_s) - transition / 2,
            **edge,
        )(p=bench.d, n=vss)
    else:
        bench.vd = Vdc(dc=0.0)(p=bench.d, n=vss)
    if design.reset:
        rst = Vpulse(v1=vdd, v2=0.0, period=1.0, width=0.5, delay=tb.reset_time_s, **edge)
        bench.vrst = rst(p=bench.rst, n=vss)
    else:
        bench.vrst = Vdc(dc=0.0)(p=bench.rst, n=vss)
    # [Baker] Fig. 13.13, p. 395: a NAND latch's inputs are active low
    # [Baker] Fig. 13.14, p. 396: a NOR latch's inputs are active high
    # set and reset pulses, a quarter period each and half a period apart (active low for a NAND latch)
    active, idle = (0.0, vdd) if design.style is Style.SR_NAND else (vdd, 0.0)
    for name, net, delay in (("vs", bench.s, data / 4), ("vr", bench.r, 3 * data / 4)):
        source = (
            Vdc(dc=0.0) if clocked else Vpulse(v1=idle, v2=active, period=data, width=data / 4, delay=delay, **edge)
        )
        bench.add(source(p=net, n=vss), name=name)
    return bench


def simulate(tb: TbParams, run_dir: Path) -> Path:
    """Run ``testbench(tb)`` in Spectre in ``run_dir``: its raw transient, in nutbin, on disk (the
    reset, then ``tb.cycles`` clock cycles; an SR latch: three set and reset periods; the upset
    bench: twice the strike time, ``tb.stop_s``); the output strobed every
    ``tb.waveform_sample_interval_s``, those points alone written. One Spectre thread: a campaign
    runs one process per run."""

    pdk = importlib.import_module(f"pdk.{tb.pdk}")
    install = importlib.import_module(f"pdk.{tb.pdk}.hdl21.site").install
    run_dir.mkdir(parents=True, exist_ok=True)
    h.pdk.set_default(pdk.pdk_logic)
    bench = testbench(tb)
    h.pdk.compile(bench)
    interval = tb.waveform_sample_interval_s
    attrs = [*spectre.includes(install), *spectre.options(), hs.Save(list(SAVES))]
    if tb.bench is Bench.UPSET:
        # not in the reference texts: a particle strike as a double-exponential current,
        # amplitude_a (e^{-t / tau2} - e^{-t / tau1}) from the strike time (the single-event upset
        # literature); its integral, the charge, is amplitude_a (tau2 - tau1). hdl21 has no
        # exponential source
        amplitude_a = float(tb.charge_c) / (UPSET_FALL_S - UPSET_RISE_S)
        strike = float(tb.upset_time_s)
        attrs.append(
            h.Literal(
                f"iupset (xtop.dut.{UPSET_NODE[tb.params.style]} 0) isource type=exp val0=0 val1={-amplitude_a:g} "
                f"td1={strike:g} tau1={UPSET_RISE_S:g} td2={strike:g} tau2={UPSET_FALL_S:g}"
            )
        )
    attrs.append(
        hs.Tran(
            tstop=tb.stop_s,
            name="tran",
            options={"strobeperiod": interval, "strobeoutput": "strobeonly"},
        )
    )
    spectre.run(bench, attrs, run_dir)
    return run_dir / "netlist.raw"
