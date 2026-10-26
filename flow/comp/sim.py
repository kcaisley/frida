"""The comparator's testbench (``testbench``) and the one Spectre run of it (``simulate``).

The testbench drives the comparator's inputs from a common mode and a differential source through
the run's source resistance onto its source capacitance a side, clocks it, loads its outputs, and
steps the inputs at each decision's cycle start (``TbParams.trial_point``). ``simulate`` runs it in
Spectre (``+preset=mx``, one thread) and leaves Spectre's raw output on disk: the signals in
``SAVES``, every ``TbParams.waveform_sample_interval_s`` (Spectre's step bounded to it), or on
Spectre's own steps where the run asks for those.
"""

import importlib
import math
from pathlib import Path

import hdl21 as h
import hdl21.sim as hs
from hdl21.primitives import C, MosType, R, Vdc, Vpulse, Vpwl
from vlsirtools.spice import ResultFormat, SimError, SimOptions, SupportedSimulators

from flow.circuit.devices import mos
from flow.circuit.ports import testbench_from_ports

from .params import CHARGE_METER, CHARGE_METER_F, TbParams
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
# the supply's charge meter (params.CHARGE_METER_F): the supply source's current mirrored onto a
# capacitor, at the top level, where Spectre's current-controlled source finds the source by name
METER = (
    f"c{CHARGE_METER} ({CHARGE_METER} 0) capacitor c={CHARGE_METER_F} ic=0\n"
    f"f{CHARGE_METER} ({CHARGE_METER} 0) cccs probe=xtop.vvdd gain=1"
)


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
    chains, unit = _clock_chains(tb)
    for port in Nets.signals.values():
        if port.usage != h.Usage.CLOCK:
            continue
        net = connections[port.name]
        # the source drives the chain's first inverter (or, without a chain, the clock itself); an
        # odd chain inverts, so its source is the complement
        sizes = chains.get(port.name, [])
        driven = net if not sizes else bench.add(h.Signal(name=f"{net.name}_source"))
        complement = (port is Nets.clkb) != (len(sizes) % 2 == 1)
        node = driven
        for index, size in enumerate(sizes):
            out = net if index == len(sizes) - 1 else bench.add(h.Signal(name=f"{net.name}_stage{index}"))
            for tp, rail, units in ((MosType.PMOS, bench.vdd, unit[1]), (MosType.NMOS, bench.vss, unit[0])):
                bench.add(
                    mos(tp=tp, vth=tb.params.vth, w=max(1, round(size * units)), l=1)(d=out, g=node, s=rail, b=rail),
                    name=f"m{net.name}_{index}_{tp.name.lower()}",
                )
            node = out
        bench.add(
            Vpulse(
                v1=tb.vdd if complement else 0.0,
                v2=0.0 if complement else tb.vdd,
                period=tb.cycle_s,
                width=tb.evaluation_time_s,
                rise=tb.transition_time_s,
                fall=tb.transition_time_s,
                delay=tb.reset_time_s,
            )(p=driven, n=bench.vss),
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


def _clock_chains(tb: TbParams) -> tuple[dict[str, list[float]], tuple[int, int]]:
    """Each clock's inverter chain (``TbParams.clock_fanout``), by its port: the stages' sizes in unit
    inverters, first to last, as many stages on both clocks; and the unit inverter's NMOS and PMOS
    widths, the active PDK's logic fingers. The last stage's input is ``clock_last_fanout`` times
    smaller than the clocked gates (their area times the PDK's gate capacitance per unit device),
    the stages before it shrinking by at most ``clock_fanout`` each to one unit inverter. No chains
    without a fanout."""

    pdk = h.pdk.default()
    fingers = getattr(pdk, "MOS_FINGER_UNITS", None) or {"logic_n": 1, "logic_p": 2}
    unit = (int(fingers["logic_n"]), int(fingers["logic_p"]))
    if tb.clock_fanout is None:
        return {}, unit
    density = getattr(pdk, "MOS_CAP_FF", None) or {"n": 0.1, "p": 0.1}
    load = {"clk": 0.0, "clkb": 0.0}
    # a fresh module: an earlier run's compile turned the cached one's devices into the PDK's
    netlist.Cache.reset()
    for inst in netlist(tb.params).instances.values():
        gate, device = inst.conns.get("g"), getattr(inst.of, "params", None)
        if gate is not None and gate.name in load and hasattr(device, "tp"):
            kind = "n" if device.tp == MosType.NMOS else "p"
            load[gate.name] += float(device.w) * float(device.l) * density[kind]
    unit_f = unit[0] * density["n"] + unit[1] * density["p"]
    last = {name: max(1.0, value / float(tb.clock_last_fanout) / unit_f) for name, value in load.items()}
    count = 1 + max(math.ceil(math.log(size) / math.log(float(tb.clock_fanout)) - 1e-9) for size in last.values())
    return {name: [size ** (i / max(count - 1, 1)) for i in range(count)] for name, size in last.items()}, unit


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
        h.Literal(METER),
        hs.Save([*SAVES, CHARGE_METER]),
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
