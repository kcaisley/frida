"""The sampler's testbench (``testbench``) and the one Spectre run of it (``simulate``).

The testbench drives complementary clocks (tracking while ``clk`` is high, the complement
``clock_skew_s`` later), an input and a load capacitor. With an input step the input toggles by
that step once per period, in the middle of each hold phase, so every track phase settles from a
known step and every hold phase shows the charge the switch dumps on opening (the pedestal), the
droop, and the input's feedthrough to the held output; with a track step as well the input steps
onto its level in the middle of each track phase, the switch closed and its gate settled (its
time constant and the switch's on-resistance). With a sine the held samples carry the switch's distortion. With a DAC step half the load
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
BOOST_SAVES = tuple(
    f"xtop.dut.{net}" for net in ("gate", "boot_top", "boot_bot", "gate_ctl", "gate_top", "gate_mid", "gate_off")
)


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
        # not in the reference texts: the bench's input, low for one period and high for the next,
        # each change in the middle of a hold phase: it starts t_delay + t_high + (T - t_high) / 2 -
        # (t_slew - t_edge) / 2 into the run and again every period
        # Terms: T tb.clock_period_s, t_high tb.clock_high_time_s, t_edge the clock's transition
        #   time, t_slew the change's own (the clock's unless tb.input_transition_time_s is given),
        #   t_delay tb.clock_delay_s.
        # Holds for: a change shorter than the hold phase (TbParams refuses a longer one), so that
        #   it is over before the next track phase.
        slew = float(edge if tb.input_transition_time_s is None else tb.input_transition_time_s)
        base = bench.vss
        if float(tb.track_step_v) != 0.0:
            bench.vstep = h.Signal()
            base = bench.vstep
        bench.vvin = Vpulse(
            v1=float(tb.input_voltage) - float(tb.input_step_v) / 2,
            v2=float(tb.input_voltage) + float(tb.input_step_v) / 2,
            period=2 * period,
            width=period - (slew - edge),
            rise=slew,
            fall=slew,
            delay=float(tb.clock_delay_s) + high + (period - high) / 2 - (slew - edge) / 2,
        )(p=bench.vin, n=base)
        if float(tb.track_step_v) != 0.0:
            # not in the reference texts: a second source in series, low until the middle of the
            # first track phase (its edge centred t_delay + t_edge + t_high / 2 into the run), then
            # high for a period and low for the next: with both steps equal the input reaches
            # input_voltage in the middle of every track phase, from below and from above in turn,
            # and leaves it in the middle of every hold phase
            # Terms: as above; the clock is high from t_delay + t_edge for t_high.
            # Holds for: a switch whose gate drive has settled by the middle of the track phase
            #   (flow.samp.analysis.analyze_track reads its time constant after this step).
            bench.vvstep = Vpulse(
                v1=-float(tb.track_step_v) / 2,
                v2=float(tb.track_step_v) / 2,
                period=2 * period,
                width=period - edge,
                rise=edge,
                fall=edge,
                delay=float(tb.clock_delay_s) + (edge + high) / 2,
            )(p=base, n=bench.vss)
    if float(tb.dac_step_v) == 0.0:
        bench.cload = C(c=tb.cload)(p=bench.vout, n=bench.vss)
    else:
        # [Razavi-ADC] Eq. (3.65), p. 44: a capacitive divider, V_A = C_b / (C_b + C_p) V_in
        # Terms: C_b ``cdac`` and C_p ``cload``, each half the load; V_in the source ``vdac``'s step
        #   of twice dac_step_v, so the held output (V_A, vout) steps by dac_step_v: a quarter into
        #   each hold phase, and back a quarter before the next track phase.
        # Ours against the source: the two halves in parallel still load the tracking switch
        #   with tb.cload.
        # Holds for: the switch off (vout floating); a held output moved as the DAC's first step
        #   moves it.
        # not in the reference texts: the DAC step's timing: t_hold = T - t_high - 2 t_edge is the
        # hold between the clock's edges; the step rises t_hold / 4 into it and falls t_hold / 4
        # before its end
        # Terms: T, t_high, t_edge as the input's above.
        # Holds for: a hold longer than four clock edges.
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
