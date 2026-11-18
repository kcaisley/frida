"""The sampler's testbench (``testbench``) and the one Spectre run of it (``simulate``).

The testbench drives complementary clocks (tracking while ``clk`` is high, the complement
``clock_skew_s`` later), an input and a load capacitor. With an input step the input toggles by
that step once per period, in the middle of each hold phase, so every track phase settles from a
known step (its time constant and the switch's resistance) and every hold phase shows the charge
the switch dumps on opening (the pedestal), the droop, and the input's feedthrough to the held
output. With a sine the held samples carry the switch's distortion. With a DAC step half the load
is driven so that the held output steps as the DAC's first step steps it. ``simulate`` runs it in
classic Spectre: its pedestals, residues and droops are small differences of large signals and its
sine's harmonics distortion, which Spectre X's error control sets wrong (``spectre.Accuracy``); its
transient at the conservative error preset, Spectre's raw output left on disk: the signals in
``SAVES`` (and a bootstrap's boosted nodes, ``BOOST_SAVES``) every
``TbParams.waveform_sample_interval_s``, Spectre's step bounded to it; where the run asks
(``TbParams.oppoint``), every transistor's operating values.
"""

import importlib
from pathlib import Path

import hdl21 as h
import hdl21.sim as hs
from hdl21.primitives import C, Vdc, Vpulse, Vsin

from flow.circuit import oppoint, spectre
from flow.circuit.ports import testbench_from_ports

from .params import Stimulus, SwitchType, TbParams
from .subckt import Nets, netlist

# what each run saves: every port but the supplies, the nets marked to save inside the switch, and
# each supply's and each clock's source current (flow.pipeline.read names them)
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
) + tuple(f"xtop.v{net.name}:p" for net in Nets.signals.values() if net.usage in (h.Usage.POWER, h.Usage.CLOCK))
# a bootstrapped switch's boosted gate, its boost capacitor's plates and its helpers' nodes
BOOST_SAVES = tuple(f"xtop.dut.{net}" for net in ("gate", "boot_top", "boot_bot", "gate_ctl", "gate_mid", "gate_off"))


def testbench(tb: TbParams) -> h.Module:
    """The sampler testbench of one run: the switch ``tb.params`` at supply ``tb.vdd`` into
    ``tb.cload``, its complementary clocks, its input level, stepped input or sine."""

    bench, connections = testbench_from_ports(
        "SampTb", {net.name: net for net in Nets.signals.values() if net.vis == h.Visibility.PORT}
    )
    bench.vvdd = Vdc(dc=tb.vdd)(p=bench.vdd, n=bench.vss)
    period, high, edge = float(tb.clock_period_s), float(tb.clock_high_time_s), float(tb.clock_transition_time_s)
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
                delay=float(tb.clock_delay_s) + (float(tb.clock_skew_s) if complement else 0.0),
            )(p=net, n=bench.vss),
            name=f"v{net.name}",
        )
    if tb.stimulus is Stimulus.SINE:
        bench.vvin = Vsin(
            voff=tb.input_voltage, vamp=tb.sine_amplitude_v, freq=tb.sine_frequency_hz, td=0.0, phase=0.0
        )(p=bench.vin, n=bench.vss)
    elif float(tb.input_step_v) == 0.0:
        bench.vvin = Vdc(dc=tb.input_voltage)(p=bench.vin, n=bench.vss)
    else:
        # low for one period, high for the next, each change in the middle of a hold phase
        bench.vvin = Vpulse(
            v1=float(tb.input_voltage) - float(tb.input_step_v) / 2,
            v2=float(tb.input_voltage) + float(tb.input_step_v) / 2,
            period=2 * period,
            width=period,
            rise=tb.clock_transition_time_s,
            fall=tb.clock_transition_time_s,
            delay=float(tb.clock_delay_s) + high + (period - high) / 2,
        )(p=bench.vin, n=bench.vss)
    if float(tb.dac_step_v) == 0.0:
        bench.cload = C(c=tb.cload)(p=bench.vout, n=bench.vss)
    else:
        # half the load on a source stepping by twice the step, so the held output steps by
        # dac_step_v: a quarter into each hold phase, and back a quarter before the next track phase
        bench.vdac = h.Signal()
        hold = period - high - 2 * edge
        bench.cload = C(c=float(tb.cload) / 2)(p=bench.vout, n=bench.vss)
        bench.cdac = C(c=float(tb.cload) / 2)(p=bench.vout, n=bench.vdac)
        bench.vvdac = Vpulse(
            v1=0.0,
            v2=2 * float(tb.dac_step_v),
            period=period,
            width=hold / 2 - edge,
            rise=edge,
            fall=edge,
            delay=float(tb.clock_delay_s) + high + 2 * edge + hold / 4,
        )(p=bench.vdac, n=bench.vss)
    bench.dut = netlist(tb.params)(**connections)
    return bench


def simulate(tb: TbParams, run_dir: Path) -> Path:
    """Run ``testbench(tb)`` in classic Spectre in ``run_dir``, marked for the accuracy its figures
    need (a sine's harmonics, else small differences of large signals), its raw transient on disk:
    the output strobed every ``tb.waveform_sample_interval_s``, the step bounded to it, at the
    conservative error preset; at ``tb.corner`` and ``tb.temperature_c``, at ``tb.gmin_s`` where
    given; with ``tb.oppoint`` every transistor's operating values beside the signals."""

    pdk = importlib.import_module(f"pdk.{tb.pdk}")
    install = importlib.import_module(f"pdk.{tb.pdk}.hdl21.site").install
    run_dir.mkdir(parents=True, exist_ok=True)
    h.pdk.set_default(pdk.pdk_logic)
    devices = oppoint.mos_devices(netlist(tb.params)) if tb.oppoint else {}
    bench = testbench(tb)
    h.pdk.compile(bench)
    includes = spectre.includes(install, tb.corner)
    boost = BOOST_SAVES if tb.params.switch_type is SwitchType.BOOTSTRAP else ()
    interval = tb.waveform_sample_interval_s
    attrs = [
        *includes,
        *spectre.options(tb.temperature_c),
        *([] if tb.gmin_s is None else [hs.Options(name="gmin", value=tb.gmin_s)]),
        hs.Save([*SAVES, *boost, *(oppoint.saves(devices, bench, includes) if devices else ())]),
        hs.Tran(
            tstop=tb.stop_s,
            name="tran",
            options={
                "strobeperiod": interval,
                "maxstep": interval,
                "strobeoutput": "strobeonly",
                "errpreset": "conservative",
            },
        ),
    ]
    mark = spectre.Accuracy.DISTORTION if tb.stimulus is Stimulus.SINE else spectre.Accuracy.SMALL_DIFFERENCE
    spectre.run(bench, attrs, run_dir, fast=False, accuracy=mark)
    return run_dir / "netlist.raw"
