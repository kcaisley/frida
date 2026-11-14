"""The delay line and ring oscillator's testbench (``testbench``) and the one Spectre run of it
(``simulate``).

The testbench: a supply source, the rings' enable and a kick-start (switches holding the outputs
apart for a while after enable), the bias sources and output loads, and for a delay line a
complementary input clock. Every chain gets the same stimulus; a ring ignores the input clock and a
delay line the enable. One control voltage sets every analog control at once: ``vbn`` and ``vctrl``
to it and ``vbp`` to the supply minus it, so a starved stage's NMOS and PMOS starve alike.
``simulate`` runs it in Spectre (``+preset=mx``, one thread) and leaves Spectre's raw output on
disk: the signals in ``SAVES``, every ``TbParams.waveform_sample_interval_s`` (Spectre's step
bounded to it).
"""

import importlib
from pathlib import Path

import hdl21 as h
import hdl21.sim as hs
from hdl21.primitives import C, MosType, Vdc, Vpulse

from flow.circuit import spectre
from flow.circuit.ports import testbench_from_ports
from flow.layout.devices.mosfet.netlist import mos

from .params import TbParams
from .subckt import Nets, netlist

# what each run saves: every port but the supplies, and each supply source's current
# (flow.pipeline.read names them)
SAVES = tuple(
    f"xtop.{net.name}"
    for net in Nets.signals.values()
    if net.vis == h.Visibility.PORT and net.usage not in (h.Usage.POWER, h.Usage.GROUND)
) + tuple(f"xtop.v{net.name}:p" for net in Nets.signals.values() if net.usage == h.Usage.POWER)


def testbench(tb: TbParams) -> h.Module:
    """The testbench of one run: the chain ``tb.params`` at supply ``tb.vdd`` with ``tb.cload_f`` on
    each output, its input clock, its enable and kick-start, its controls at ``tb.vcont_v``."""

    bench, connections = testbench_from_ports(
        "DelayTb", {net.name: net for net in Nets.signals.values() if net.vis == h.Visibility.PORT}
    )
    vdd, vss = tb.vdd, bench.vss
    bench.vvdd = Vdc(dc=vdd)(p=bench.vdd, n=vss)
    # complementary rail-to-rail halves, the period's first quarter as delay
    edge = {"rise": tb.transition_time_s, "fall": tb.transition_time_s}
    width = float(tb.clock_period_s) / 2 - float(tb.transition_time_s)
    clock = {"period": tb.clock_period_s, "width": width, "delay": float(tb.clock_period_s) / 4, **edge}
    bench.vinp = Vpulse(v1=0.0, v2=vdd, **clock)(p=bench.inp, n=vss)
    bench.vinn = Vpulse(v1=vdd, v2=0.0, **clock)(p=bench.inn, n=vss)
    # the enable: en rises once and stays high (one pulse longer than the run)
    bench.ven = Vpulse(v1=0.0, v2=vdd, period=1.0, width=0.5, delay=tb.enable_delay_s, **edge)(p=bench.en, n=vss)
    bench.vinj = Vdc(dc=tb.vinj_v)(p=bench.inj, n=vss)
    bench.vvbn = Vdc(dc=tb.vcont_v)(p=bench.vbn, n=vss)
    bench.vvbp = Vdc(dc=float(vdd) - float(tb.vcont_v))(p=bench.vbp, n=vss)
    bench.vvctrl = Vdc(dc=tb.vcont_v)(p=bench.vctrl, n=vss)
    bench.cloadp = C(c=tb.cload_f)(p=bench.outp, n=vss)
    bench.cloadn = C(c=tb.cload_f)(p=bench.outn, n=vss)
    # the kick-start: from just after en rises, a PMOS switch holds outp
    # at vdd and an NMOS one outn at vss (each twice the output inverter's device), then lets go. A
    # coupled ring's enable leaves both chains alike, a state its main inverters hold against the
    # coupling ones; held apart, its outputs start it from a differential one.
    design = tb.params
    kick = {
        "period": 1.0,
        "width": tb.kick_time_s,
        "delay": float(tb.enable_delay_s) + 2 * float(tb.transition_time_s),
    }
    bench.kick, bench.kickb = h.Signal(), h.Signal()
    bench.vkick = Vpulse(v1=0.0, v2=vdd, **kick, **edge)(p=bench.kick, n=vss)
    bench.vkickb = Vpulse(v1=vdd, v2=0.0, **kick, **edge)(p=bench.kickb, n=vss)
    bench.mkickp = mos(tp=MosType.PMOS, vth=design.vth, w=2 * design.inv_p_w, l=design.inv_l)(
        d=bench.outp, g=bench.kickb, s=bench.vdd, b=bench.vdd
    )
    bench.mkickn = mos(tp=MosType.NMOS, vth=design.vth, w=2 * design.inv_n_w, l=design.inv_l)(
        d=bench.outn, g=bench.kick, s=vss, b=vss
    )
    bench.dut = netlist(tb.params)(**connections)
    return bench


def simulate(tb: TbParams, run_dir: Path) -> Path:
    """Run ``testbench(tb)`` in Spectre in ``run_dir``: its raw transient, in nutbin, on disk; the
    output strobed every ``tb.waveform_sample_interval_s``, the step bounded to it. One Spectre
    thread: a campaign runs one process per run."""

    pdk = importlib.import_module(f"pdk.{tb.pdk}")
    install = importlib.import_module(f"pdk.{tb.pdk}.hdl21.site").install
    run_dir.mkdir(parents=True, exist_ok=True)
    h.pdk.set_default(pdk.pdk_logic)
    bench = testbench(tb)
    h.pdk.compile(bench)
    interval = tb.waveform_sample_interval_s
    attrs = [
        *spectre.includes(install),
        *spectre.options(),
        hs.Save(list(SAVES)),
        hs.Tran(
            tstop=tb.stop_time_s,
            name="tran",
            options={"strobeperiod": interval, "maxstep": interval, "strobeoutput": "strobeonly"},
        ),
    ]
    spectre.run(bench, attrs, run_dir)
    return run_dir / "netlist.raw"
