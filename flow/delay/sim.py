"""The delay line and ring oscillator's testbench (``testbench``) and the one Spectre run of it
(``simulate``).

The testbench: the chain on its own supply source (``vvdd``), each output loaded by two more of the
chain's stages (the first one's output loaded by the second, as an inner node's next stage is), and
only the stimulus the chain takes: a ring's enable; a delay line's input clock, reaching it through
two of its own stages (one rail-to-rail clock for a single-ended line, complementary clocks for a
differential one); a starved chain's bias, the
PMOS heads' gate from a mirror of the NMOS feet's current; a tail chain's control. A port the chain
has no device on is tied to ground, and so is an injecting ring's injection input (no run drives
it). The driving stages, the load stages and the bias run on a bench supply of their own
(``vvddbench``), so ``vvdd``'s current is the chain's alone. ``simulate`` runs it in Spectre
(``+preset=mx``, one thread) and leaves Spectre's raw output on disk: the chain's ports and
``vvdd``'s current, a time point forced every ``TbParams.waveform_sample_interval_s``.
"""

import importlib
from pathlib import Path

import hdl21 as h
import hdl21.sim as hs
from hdl21.primitives import MosType, Vdc, Vpulse

from flow.circuit import spectre
from flow.circuit.ports import testbench_from_ports
from flow.layout.devices.mosfet.netlist import mos

from .params import Control, Params, TbParams
from .subckt import Nets, netlist


def testbench(tb: TbParams) -> h.Module:
    """The testbench of one run: the chain ``tb.params`` at supply ``tb.vdd``, each output loaded by
    two of its stages, its input clock through two of its stages (a line) or its enable (a ring),
    its controls at ``tb.vcont_v``."""

    bench, connections = testbench_from_ports(
        "DelayTb", {net.name: net for net in Nets.signals.values() if net.vis == h.Visibility.PORT}
    )
    design = tb.params
    vdd, vss = tb.vdd, bench.vss
    bench.vvdd = Vdc(dc=vdd)(p=bench.vdd, n=vss)
    # the driving stages', the load stages' and the bias's supply, at the chain's
    bench.vddbench = h.Signal()
    bench.vvddbench = Vdc(dc=vdd)(p=bench.vddbench, n=vss)
    # the ports the chain has no device on, tied to ground: no source drives a pin nothing loads
    unused = {
        *(("inp", "inn") if design.ring else ("en",)),
        *(() if design.differential else ("inn", "outn")),
        # an injecting ring's inj too: no run drives it, so its device only loads the first stage's outputs
        "inj",
        *(() if design.control is Control.STARVED else ("vbn", "vbp")),
        *(() if design.control is Control.TAIL else ("vctrl",)),
    }
    chain = {**connections, **dict.fromkeys(unused, vss)}
    # the chain's module; its driving and load stages share one where they are the same design (hdl21
    # names a generated module by its parameters and refuses two of one name)
    module = netlist(design)
    built = [(design, module)]
    edge = {"rise": tb.transition_time_s, "fall": tb.transition_time_s}
    if design.ring:
        # [Baker] Fig. 18.42, p. 556: the enable: en rises once and stays high (one pulse longer than
        # the run); [Baker] Eq. (11.11), p. 354 and [Razavi-PLL] Sec. 1.4.1, p. 12: an odd single-ended
        # ring starts by itself, so nothing else starts it; [Razavi-PLL] Sec. 4.9.3, Fig. 4.36, p. 130:
        # the cross-coupled inverters keep an even differential ring from latching up. While en is low the ring rests with its first stage's p
        # output high (and a differential ring's n output low: each stage's outputs complementary),
        # drawing no current; a ring that does not keep oscillating after en rises reads stopped
        bench.ven = Vpulse(v1=0.0, v2=vdd, period=1.0, width=0.5, delay=tb.enable_delay_s, **edge)(p=bench.en, n=vss)
    else:
        # a rail-to-rail clock (and its complement for a differential line), the period's first quarter
        # as delay, through two of the
        # line's own stages: [Razavi-PLL] Sec. 3.3.2, p. 74: inverters at a fan-out of one keep their
        # own rise and fall times, so the line's first stage sees the edge every later one sees
        width = float(tb.clock_period_s) / 2 - float(tb.transition_time_s)
        clock = {"period": tb.clock_period_s, "width": width, "delay": float(tb.clock_period_s) / 4, **edge}
        bench.clockp = h.Signal()
        bench.vclockp = Vpulse(v1=0.0, v2=vdd, **clock)(p=bench.clockp, n=vss)
        driven = {"inp": bench.clockp, "outp": bench.inp}
        if design.differential:
            bench.clockn = h.Signal()
            bench.vclockn = Vpulse(v1=vdd, v2=0.0, **clock)(p=bench.clockn, n=vss)
            driven |= {"inn": bench.clockn, "outn": bench.inn}
        driver = Params(**{**design.__dict__, "stages": 2})
        driving = module if driver == design else netlist(driver)
        built.append((driver, driving))
        bench.driver = driving(**{**chain, **driven, "vdd": bench.vddbench})
    if design.control is Control.STARVED:
        # [Baker] Fig. 19.14, p. 571: an NMOS at the control sets a current that a PMOS diode mirrors
        # into every head, each sized as the chain's starving devices, so that a stage's head carries
        # its foot's current ([Baker] Eqs. (19.20)-(19.22), p. 572: I_D4 = I_D1). On the bench supply:
        # [Baker] Eq. (19.27), p. 572: the mirror's power, counted, would double the VCO's; it is not
        bench.vvbn = Vdc(dc=tb.vcont_v)(p=bench.vbn, n=vss)
        bench.mbias_n = mos(tp=MosType.NMOS, vth=design.vth, w=design.starve_n_w, l=design.starve_l)(
            d=bench.vbp, g=bench.vbn, s=vss, b=vss
        )
        bench.mbias_p = mos(tp=MosType.PMOS, vth=design.vth, w=design.starve_p_w, l=design.starve_l)(
            d=bench.vbp, g=bench.vbp, s=bench.vddbench, b=bench.vddbench
        )
    if design.control is Control.TAIL:
        bench.vvctrl = Vdc(dc=tb.vcont_v)(p=bench.vctrl, n=vss)
    # [Razavi-PLL] Sec. 3.2, Fig. 3.10(a), pp. 70-71: the output buffered at a fan-out of one, its
    # input the following circuit's load; [Baker] Eq. (11.12), p. 355: each inner node's load is the
    # next stage's input, that stage's own output loaded by the stage after it. So the output drives
    # two more stages, the first one's output loaded by the second: [Razavi-Analog] Sec. 6.1.1,
    # Eq. (6.2), p. 174: a gate-drain capacitance loads its input by the far node's swing, so an open
    # far node would load the output otherwise than an inner node. A line's output sees what every
    # inner node sees; a ring's output also drives the ring's first stage, a fan-out of two there
    # ([Razavi-PLL] Sec. 3.2, p. 72, fn. 7)
    bench.loadp = h.Signal()
    loads = {"inp": bench.outp, "outp": bench.loadp, "en": vss}
    if design.differential:
        bench.loadn = h.Signal()
        loads |= {"inn": bench.outn, "outn": bench.loadn}
    load = Params(**{**design.__dict__, "stages": 2, "ring": False, "inject": False})
    loading = next((of for made, of in built if made == load), None) or netlist(load)
    bench.load = loading(**{**chain, **loads, "vdd": bench.vddbench})
    bench.dut = module(**chain)
    return bench


def simulate(tb: TbParams, run_dir: Path) -> Path:
    """Run ``testbench(tb)`` in Spectre in ``run_dir``: its raw transient, in nutbin, on disk; every
    port of the chain that is not tied to ground or a supply and ``vvdd``'s current, a time point
    forced every ``tb.waveform_sample_interval_s`` (Spectre X's error control sets the steps between
    them). One Spectre thread: a campaign runs one process per run."""

    pdk = importlib.import_module(f"pdk.{tb.pdk}")
    install = importlib.import_module(f"pdk.{tb.pdk}.hdl21.site").install
    run_dir.mkdir(parents=True, exist_ok=True)
    h.pdk.set_default(pdk.pdk_logic)
    bench = testbench(tb)
    # what the run saves (flow.pipeline.read names them): the chain's driven and driving ports, and
    # the chain's supply current
    saves = [
        f"xtop.{name}"
        for name, net in bench.dut.conns.items()
        if net is not bench.vss and Nets.signals[name].usage not in (h.Usage.POWER, h.Usage.GROUND)
    ] + ["xtop.vvdd:p"]
    h.pdk.compile(bench)
    interval = tb.waveform_sample_interval_s
    # not in the reference texts: the typical process corner at 25 C (the flow's defaults), one corner
    # for every run
    attrs = [
        *spectre.includes(install),
        *spectre.options(),
        hs.Save(saves),
        hs.Tran(
            tstop=tb.stop_time_s,
            name="tran",
            options={"strobeperiod": interval, "strobeoutput": "strobeonly"},
        ),
    ]
    spectre.run(bench, attrs, run_dir)
    return run_dir / "netlist.raw"
