"""The sampler's testbench (``testbench``) and the one Spectre run of it (``simulate``).

The testbench drives complementary clocks (tracking while ``clk`` is high), an input level and a
load capacitor. With an input step the input toggles by that step once per period, in the middle
of each hold phase, so every track phase settles from a known step (its time constant and the
switch's resistance) and every hold phase shows the charge the switch dumps on opening (the
pedestal), the droop, and the input's feedthrough to the held output. ``simulate`` runs it in
Spectre (``+preset=mx``, one thread) and leaves Spectre's raw output on disk: the signals in
``SAVES``, every ``TbParams.waveform_sample_interval_s`` (Spectre's step bounded to it).
"""

import importlib
from pathlib import Path

import hdl21 as h
import hdl21.sim as hs
from hdl21.primitives import C, Vdc, Vpulse
from vlsirtools.spice import ResultFormat, SimError, SimOptions, SupportedSimulators

from flow.circuit.ports import testbench_from_ports

from .params import TbParams
from .subckt import Nets, netlist

# what each run saves: every port but the supplies, the nets marked to save inside the switch, and
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
    """The sampler testbench of one run: the switch ``tb.params`` at supply ``tb.vdd`` into
    ``tb.cload``, its complementary clocks, its input level or stepped input."""

    bench, connections = testbench_from_ports(
        "SampTb", {net.name: net for net in Nets.signals.values() if net.vis == h.Visibility.PORT}
    )
    bench.vvdd = Vdc(dc=tb.vdd)(p=bench.vdd, n=bench.vss)
    for port in Nets.signals.values():
        if port.usage != h.Usage.CLOCK:
            continue
        complement = port is Nets.clk_b
        net = connections[port.name]
        bench.add(
            Vpulse(
                v1=tb.vdd if complement else 0.0,
                v2=0.0 if complement else tb.vdd,
                period=tb.clock_period_s,
                width=tb.clock_high_time_s,
                rise=tb.clock_transition_time_s,
                fall=tb.clock_transition_time_s,
                delay=tb.clock_delay_s,
            )(p=net, n=bench.vss),
            name=f"v{net.name}",
        )
    if float(tb.input_step_v) == 0.0:
        bench.vdin = Vdc(dc=tb.input_voltage)(p=bench.din, n=bench.vss)
    else:
        # low for one period, high for the next, each change in the middle of a hold phase
        period, high = float(tb.clock_period_s), float(tb.clock_high_time_s)
        bench.vdin = Vpulse(
            v1=float(tb.input_voltage) - float(tb.input_step_v) / 2,
            v2=float(tb.input_voltage) + float(tb.input_step_v) / 2,
            period=2 * period,
            width=period,
            rise=tb.clock_transition_time_s,
            fall=tb.clock_transition_time_s,
            delay=float(tb.clock_delay_s) + high + (period - high) / 2,
        )(p=bench.din, n=bench.vss)
    bench.cload = C(c=tb.cload)(p=bench.dout, n=bench.vss)
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
        install.include(h.pdk.Corner.TYP),
        # what else the PDK's simulations take, in this order: TSMC's pre-simulation settings, the
        # device names its netlists use (pdk/<name>/hdl21)
        *(getattr(install, name)() for name in ("include_pre_simulation", "include_devices") if hasattr(install, name)),
        hs.Options(name="temp", value=25.0),
        hs.Options(name="save", value="selected"),
        hs.Save(list(SAVES)),
        hs.Tran(
            tstop=tb.stop_s,
            name="tran",
            options={"strobeperiod": interval, "maxstep": interval, "strobeoutput": "strobeonly"},
        ),
    ]
    try:
        hs.Sim(tb=bench, attrs=attrs).run(
            SimOptions(
                simulator=SupportedSimulators.SPECTRE,
                fmt=ResultFormat.NONE,
                rundir=run_dir,
                simulator_args=(
                    *("-format", "nutbin", "+preset=mx", "+mt=1"),
                    *("+lqtimeout", "3600", "+escchars", "+log", "spectre.log"),
                ),
            )
        )
    except SimError as error:
        # the simulator's error holds its simulation, which cannot cross back from a worker process
        raise RuntimeError(f"Spectre failed in {run_dir}: {error}") from None
    return run_dir / "netlist.raw"
