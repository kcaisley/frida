"""The comparator's testbench (``testbench``) and the one Spectre run of it (``simulate``).

The testbench drives the comparator's inputs from a common mode and a differential source through
the run's source resistance onto its source capacitance a side, clocks it, loads its outputs, and
steps the inputs at each decision's cycle start (``TbParams.trial_point``). ``simulate`` runs it in
Spectre (``+preset=mx``, one thread) and leaves Spectre's raw output on disk: the signals in
``SAVES``, every ``TbParams.waveform_sample_interval_s`` (Spectre's step bounded to it), or on
Spectre's own steps where the run asks for those.
"""

import importlib
from pathlib import Path

import hdl21 as h
import hdl21.sim as hs
from hdl21.primitives import C, R, Vdc, Vpulse, Vpwl
from vlsirtools.spice import ResultFormat, SimError, SimOptions, SupportedSimulators

from flow.circuit.ports import testbench_from_ports

from .params import TbParams
from .subckt import Nets, netlist

# what each run saves: every port but the supplies, the nets marked to save inside the comparator,
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
    """The comparator testbench of one run: the comparator ``tb.params`` at supply ``tb.vdd``, its
    inputs stepped through ``tb.points`` in the order ``tb.trial_point``."""

    bench, connections = testbench_from_ports(
        "CompTb", {net.name: net for net in Nets.signals.values() if net.vis == h.Visibility.PORT}
    )
    bench.vin_cm, bench.vin_diff = h.Signals(2)
    bench.vin = h.Diff()
    bench.vvdd = Vdc(dc=tb.vdd)(p=bench.vdd, n=bench.vss)
    bench.rsrc_p = R(r=tb.source_resistance_ohm)(p=bench.vin.p, n=bench.inp)
    bench.rsrc_n = R(r=tb.source_resistance_ohm)(p=bench.vin.n, n=bench.inn)
    bench.csrc_p = C(c=tb.source_capacitance_f)(p=bench.inp, n=bench.vss)
    bench.csrc_n = C(c=tb.source_capacitance_f)(p=bench.inn, n=bench.vss)
    for port in Nets.signals.values():
        if port.usage != h.Usage.CLOCK:
            continue
        complement = port is Nets.clkb
        net = connections[port.name]
        bench.add(
            Vpulse(
                v1=tb.vdd if complement else 0.0,
                v2=0.0 if complement else tb.vdd,
                period=tb.cycle_s,
                width=tb.evaluation_time_s,
                rise=tb.transition_time_s,
                fall=tb.transition_time_s,
                delay=tb.reset_time_s,
            )(p=net, n=bench.vss),
            name=f"v{net.name}",
        )
    bench.cload_p = C(c=tb.output_load_f)(p=bench.outp, n=bench.vss)
    bench.cload_n = C(c=tb.output_load_f)(p=bench.outn, n=bench.vss)
    bench.dut = netlist(tb.params)(**connections)
    # each decision's input, stepped at its cycle's start (in the reset)
    schedule = [tb.points[point] for point in tb.trial_point]
    for name, values in (("vin_cm", [cm for cm, _ in schedule]), ("vin_diff", [diff for _, diff in schedule])):
        bench.add(
            Vpwl(
                wave=h.Pwl.steps(
                    values=values, dwell=tb.cycle_s, transition=tb.transition_time_s, transition_at="start"
                )
            )(p=getattr(bench, name), n=bench.vss),
            name=f"v{name}",
        )
    bench.evin_p = h.Vcvs(gain=0.5)(p=bench.vin.p, n=bench.vin_cm, cp=bench.vin_diff, cn=bench.vss)
    bench.evin_n = h.Vcvs(gain=-0.5)(p=bench.vin.n, n=bench.vin_cm, cp=bench.vin_diff, cn=bench.vss)
    return bench


def simulate(tb: TbParams, run_dir: Path) -> Path:
    """Run ``testbench(tb)`` in Spectre in ``run_dir``: its raw transient, in nutbin, on disk.

    Transient noise where ``tb.noise`` (down to the run's length, up to 25 GHz, seed 1); the output
    strobed every ``tb.waveform_sample_interval_s``, the step bounded to it (Spectre's own steps
    where None). One Spectre thread: a campaign runs one process per run.
    """

    pdk = importlib.import_module(f"pdk.{tb.pdk}")
    install = importlib.import_module(f"pdk.{tb.pdk}.hdl21.site").install
    run_dir.mkdir(parents=True, exist_ok=True)
    h.pdk.set_default(pdk.pdk_logic)
    bench = testbench(tb)
    h.pdk.compile(bench)
    options = {}
    if tb.waveform_sample_interval_s is not None:
        options = {
            "strobeperiod": tb.waveform_sample_interval_s,
            "maxstep": tb.waveform_sample_interval_s,
            "strobeoutput": "strobeonly",
        }
    if tb.noise:
        options.update(noisefmin=1.0 / tb.stop_s, noisefmax="25G", noiseseed=1)
    attrs = [
        install.include(h.pdk.Corner.TYP),
        # what else the PDK's simulations take, in this order: TSMC's pre-simulation settings, the
        # device names its netlists use (pdk/<name>/hdl21)
        *(getattr(install, name)() for name in ("include_pre_simulation", "include_devices") if hasattr(install, name)),
        hs.Options(name="temp", value=25.0),
        hs.Options(name="save", value="selected"),
        hs.Save(list(SAVES)),
        hs.Tran(tstop=tb.stop_s, name="tran", noise=tb.noise, options=options),
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
