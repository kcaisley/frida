"""The comparator's testbench (``testbench``) and the one Spectre run of it (``simulate``).

The testbench drives the comparator's inputs from a common mode and a differential source through
the run's source resistance onto its source capacitance a side, clocks it, loads its outputs, and
steps the inputs at each decision's cycle start (``TbParams.trial_point``). ``simulate`` runs it in
Spectre (Spectre X, ``+preset=mx``, one thread; classic Spectre where the run needs its accuracy,
``TbParams.accuracy``) and leaves Spectre's raw output on disk: the signals in ``SAVES`` (and each
device's operating-point values where the run asks for them), every
``TbParams.waveform_sample_interval_s``, or on Spectre's own steps where the run asks for those.
"""

import importlib
import math
from pathlib import Path

import hdl21 as h
import hdl21.sim as hs
from hdl21.primitives import C, MosType, R, Vdc, Vpulse, Vpwl

from flow.circuit import oppoint, spectre
from flow.circuit.ports import testbench_from_ports
from flow.layout.devices.device import active_pdk
from flow.layout.devices.moscap.table import density as gate_density
from flow.layout.devices.mosfet.netlist import mos

from .params import CHARGE_METER, CHARGE_METER_F, ClockDrive, TbParams
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
# the supply's charge meter (params.CHARGE_METER_F, where its definition is): the supply source's
# current mirrored at unity gain onto a capacitor that starts empty, at the top level, where
# Spectre's current-controlled source finds the source by name
METER = (
    f"c{CHARGE_METER} ({CHARGE_METER} 0) capacitor c={CHARGE_METER_F} ic=0\n"
    f"f{CHARGE_METER} ({CHARGE_METER} 0) cccs probe=xtop.vvdd gain=1"
)


def testbench(tb: TbParams) -> h.Module:
    """The comparator testbench of one run: the comparator ``tb.params`` at supply ``tb.vdd``, its
    inputs stepped through ``tb.points`` in the order ``tb.trial_point``, its clocks driven as
    ``tb.clock_drive`` says: each from its own chain on the comparator's supply (``CHAINS``; a
    clock with no gate of the comparator on it has no chain, and stays on its source), or
    clk's chain on a supply of its own, ``vdd_clock`` (no charge of it metered), and clkb from clk
    through the converter's one inverter on the comparator's supply (``CONVERTER``)."""

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
    converter = tb.clock_drive is ClockDrive.CONVERTER
    if converter:
        # not in the reference texts: the supply of clk's chain where the converter drives the
        # clocks, taken equal to the comparator's (tb.vdd); in the converter clk comes from its
        # digital supply and the clkb inverter is on the comparator's (flow.adc.subckt). Holds
        # where the two supplies are one voltage
        bench.vdd_clock = h.Signal()
        bench.vvdd_clock = Vdc(dc=tb.vdd)(p=bench.vdd_clock, n=bench.vss)
        clk, clkb = connections[Nets.clk.name], connections[Nets.clkb.name]
        width, length = tb.clkb_inverter
        for tp, rail in ((MosType.PMOS, bench.vdd), (MosType.NMOS, bench.vss)):
            bench.add(
                mos(tp=tp, vth=tb.params.vth, w=width, l=length)(d=clkb, g=clk, s=rail, b=rail),
                name=f"m{clkb.name}_inverter_{tp.name.lower()}",
            )
    for port in Nets.signals.values():
        if port.usage != h.Usage.CLOCK or (converter and port is Nets.clkb):
            continue
        net = connections[port.name]
        # the source drives the chain's first inverter (or, without a chain, the clock itself); an
        # odd chain inverts, so its source is the complement
        sizes = chains.get(port.name, [])
        driven = net if not sizes else bench.add(h.Signal(name=f"{net.name}_source"))
        complement = (port is Nets.clkb) != (len(sizes) % 2 == 1)
        supply = bench.vdd_clock if converter else bench.vdd
        node = driven
        for index, size in enumerate(sizes):
            out = net if index == len(sizes) - 1 else bench.add(h.Signal(name=f"{net.name}_stage{index}"))
            for tp, rail, units in ((MosType.PMOS, supply, unit[1]), (MosType.NMOS, bench.vss, unit[0])):
                bench.add(
                    mos(tp=tp, vth=tb.params.vth, w=max(1, round(size * units)), l=1)(d=out, g=node, s=rail, b=rail),
                    name=f"m{net.name}_{index}_{tp.name.lower()}",
                )
            node = out
        # not in the reference texts: the clock as its source drives it, low (reset) for
        # tb.reset_time_s, then high: the pulse's width, its flat top, is tb.evaluation_time_s and
        # its edges tb.transition_time_s each, so at mid-swing the source is high for the
        # evaluation and a transition, and its fall lands a transition into the next cycle; the
        # comparator's own clock follows by its chain's delay. The input's step and every
        # per-cycle window (analysis: a cycle's charge, the kickback's) are placed against that
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
    # not in the reference texts: each decision's input, stepped over the first transition of its
    # cycle, while the previous decision is still held (the source clock falls a transition into
    # the cycle, the comparator's behind its chain later still); the previous decision was read
    # before it (TbParams.decision_time_s). Holds for a comparator that has decided by the read
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
    # [Razavi-Analog] Sec. 4.2, p. 103: the two inputs about their common-mode level, V_in,CM
    # plus and minus half their difference
    # V_in,CM: vin_cm; V_in1 - V_in2: vin_diff; V_in1, V_in2: vin.p, vin.n, which reach the
    # comparator's inp, inn through the source's resistance
    bench.evin_p = h.Vcvs(gain=0.5)(p=bench.vin.p, n=bench.vin_cm, cp=bench.vin_diff, cn=bench.vss)
    bench.evin_n = h.Vcvs(gain=-0.5)(p=bench.vin.n, n=bench.vin_cm, cp=bench.vin_diff, cn=bench.vss)
    return bench


def _clock_chains(tb: TbParams) -> tuple[dict[str, list[float]], tuple[int, int]]:
    """Each clock's inverter chain (``TbParams.clock_fanout``), by its port: the stages' sizes in unit
    inverters, first to last, as many stages on both clocks; and the unit inverter's NMOS and PMOS
    widths, the active PDK's logic fingers. The last stage's input is ``clock_last_fanout`` times
    smaller than the clocked gates (their area times the PDK's measured gate capacitance,
    ``flow.layout.devices.moscap``), the stages before it shrinking by at most ``clock_fanout``
    each to one unit inverter. A clock with no gate of the comparator on it has no chain (its
    energy would be counted for driving nothing). No chains without a fanout; as the converter
    drives the clocks (``ClockDrive.CONVERTER``), clk's alone, its gates the converter's clkb
    inverter's too."""

    pdk = h.pdk.default()
    # [Baker] Example 11.8, pp. 360-361: a buffer's first inverter, its PMOS twice its NMOS (20/10)
    # the unit inverter of the chains: the PDK's logic fingers, and W_P = 2 W_N where it gives none
    fingers = getattr(pdk, "MOS_FINGER_UNITS", None) or {"logic_n": 1, "logic_p": 2}
    unit = (int(fingers["logic_n"]), int(fingers["logic_p"]))
    if tb.clock_fanout is None:
        return {}, unit
    density = gate_density(active_pdk())
    # [Baker] Eq. (11.19), p. 360: the load a buffer drives, C_load
    # C_load: each clock's gates in the comparator, their area (in unit widths by minimum
    # lengths, as Params gives them) times the PDK's measured gate capacitance of a unit, by
    # device type. The gate oxide alone: no wiring, and none of the overlap to drains that swing,
    # so the charge a driver delivers an edge is more; it only sets a ratio here, against the
    # last stage's input (unit_f), counted the same way
    load = {"clk": 0.0, "clkb": 0.0}
    # a fresh module: an earlier run's compile turned the cached one's devices into the PDK's
    netlist.Cache.reset()
    for inst in netlist(tb.params).instances.values():
        gate, device = inst.conns.get("g"), getattr(inst.of, "params", None)
        if gate is not None and gate.name in load and hasattr(device, "tp"):
            kind = "n" if device.tp == MosType.NMOS else "p"
            load[gate.name] += float(device.w) * float(device.l) * density[kind]
    if tb.clock_drive is ClockDrive.CONVERTER:
        width, length = tb.clkb_inverter
        load = {"clk": load["clk"] + width * length * (density["n"] + density["p"])}
    # [Baker] Eq. (11.20), p. 360: a buffer's taper, A = (C_load / C_in1)^(1/N)
    # C_in1: unit_f, the unit inverter's input; C_load: here the last stage's input, the clocked
    # gates over clock_last_fanout, in unit inverters (last); N: count - 1, the stages after the
    # first, the fewest that keep A = last^(1 / N) at or below clock_fanout; the stages' sizes
    # A^i, i = 0 to N. Both clocks take the larger count, so that their edges stay matched.
    # not in the reference texts: the two values (params.CLOCK_FANOUT, CLOCK_LAST_FANOUT), the
    # last stage at a fanout of its own where the source's drives A times its input (Eq. (11.19)),
    # and no chain on a clock without a gate. Holds for a load of at least one unit inverter at
    # the last fanout (a smaller one takes unit inverters)
    unit_f = unit[0] * density["n"] + unit[1] * density["p"]
    last = {name: max(1.0, value / float(tb.clock_last_fanout) / unit_f) for name, value in load.items() if value > 0}
    if not last:
        return {}, unit
    count = 1 + max(math.ceil(math.log(size) / math.log(float(tb.clock_fanout)) - 1e-9) for size in last.values())
    return {name: [size ** (i / max(count - 1, 1)) for i in range(count)] for name, size in last.items()}, unit


def simulate(tb: TbParams, run_dir: Path) -> Path:
    """Run ``testbench(tb)`` in Spectre in ``run_dir``: its raw transient on disk (nutbin; PSF
    ASCII where it saves device values).

    Its models at ``tb.corner`` and ``tb.temperature_c``. Transient noise where ``tb.noise`` (down to
    the run's length, up to ``tb.noise_fmax_hz``, seed 1); the output strobed every
    ``tb.waveform_sample_interval_s`` (Spectre's own steps where None). A run that needs accuracy
    (``tb.accuracy``) in classic Spectre at its conservative error preset, its step bounded to the
    strobe (a timing run at the tolerances [Razavi-ADC] Sec. 7.6 sets too); every other in Spectre X, which bounds no
    step. Each device's operating-point values saved where ``tb.device_values``. One Spectre thread:
    a campaign runs one process per run.
    """

    pdk = importlib.import_module(f"pdk.{tb.pdk}")
    install = importlib.import_module(f"pdk.{tb.pdk}.hdl21.site").install
    run_dir.mkdir(parents=True, exist_ok=True)
    h.pdk.set_default(pdk.pdk_logic)
    devices = oppoint.mos_devices(netlist(tb.params)) if tb.device_values else {}
    bench = testbench(tb)
    h.pdk.compile(bench)
    includes = spectre.includes(install, tb.corner)
    classic = tb.accuracy is not None
    # not in the reference texts: the simulator's settings (frida's own; the source sets
    # tolerances alone, below): the output strobed every tb.waveform_sample_interval_s; where the
    # run needs accuracy, classic Spectre's conservative preset and no step longer than the
    # strobe, so that every output point is a solved one
    options: dict[str, float | str] = {}
    if tb.waveform_sample_interval_s is not None:
        options = {"strobeperiod": tb.waveform_sample_interval_s, "strobeoutput": "strobeonly"}
        if classic:
            options["maxstep"] = tb.waveform_sample_interval_s
    if classic:
        options["errpreset"] = "conservative"
    if tb.noise:
        # not in the reference texts: transient noise's band, from one over the run's length (the
        # slowest noise a run can show) to tb.noise_fmax_hz (params: why 100 GHz), one seed
        options.update(noisefmin=1.0 / tb.stop_s, noisefmax=tb.noise_fmax_hz, noiseseed=1)
    tolerances = []
    if tb.accuracy is spectre.Accuracy.TIMING:
        # [Razavi-ADC] Sec. 7.6, p. 136: the simulator's tolerances for a delay near metastability
        # (delays a few picoseconds apart): reltol, vabstol (V), iabstol (A)
        # the source's three values, for the runs marked Accuracy.TIMING (the delay curves)
        tolerances = [
            hs.Options(name=name, value=value)
            for name, value in (("reltol", 1e-6), ("vabstol", 1e-6), ("iabstol", 1e-12))
        ]
    attrs = [
        *includes,
        *spectre.options(tb.temperature_c),
        *tolerances,
        h.Literal(METER),
        hs.Save([*SAVES, CHARGE_METER, *oppoint.saves(devices, bench, includes)]),
        hs.Tran(tstop=tb.stop_s, name="tran", noise=tb.noise, options=options),
    ]
    spectre.run(bench, attrs, run_dir, fast=not classic, accuracy=tb.accuracy)
    return run_dir / "netlist.raw"
