"""The charge-sensitive amplifier's testbench (``testbench``) and the one Spectre run of it
(``simulate``).

The testbench: the input loaded by the detector capacitance, the charge injected through a small
capacitor by a voltage step, the output loaded by the discriminator's input. The load's and the
Krummenacher tail's biases are diode-connected copies of their devices fed the bias currents from a
supply of their own. The cascode's is a copy fed the load current standing a little off the input
device's rail, so that the input device keeps that much of a drain-source voltage; the continuous
feedback's gate a copy of the feedback device fed its current standing on a copy of the input
device, so that at rest the feedback device carries that current from the input's level. The reset
switch is closed until well before the charge arrives. The charge has the sign that moves the
output away from the input device's rail: electrons into an NMOS input, holes into a PMOS one.
What the run drives is its ``Stimulus``: the charge (``CHARGE``), whose transient is the response;
or no charge (``NOISE``), whose noise analysis gives the output noise, which over the response to a
known charge is the ENC.

``simulate`` runs it in Spectre and leaves the raw output on disk: the signals in ``SAVES``, after
the operating point every run starts from (``opdc``), the transient (``tran``, every
``TbParams.waveform_sample_interval_s``) or the output noise (``noise``).
"""

import importlib
from pathlib import Path

import hdl21 as h
import hdl21.sim as hs
from hdl21.primitives import C, Idc, MosType, Vdc, Vpulse

from flow.circuit import spectre
from flow.circuit.ports import testbench_from_ports
from flow.layout.devices.mosfet.netlist import mos

from .params import Feedback, Stimulus, TbParams
from .subckt import Nets, netlist

# what each run saves: every port but the supplies, the nets marked to save inside the amplifier,
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


def _reference(
    bench: h.Module, tb: TbParams, tp: MosType, size: dict[str, int], gate: h.Signal, current: float, source=None
) -> tuple[h.Instance, h.Instance]:
    """A diode-connected copy fed ``current``: from the reference supply into an NMOS, from a PMOS
    to ground; its source on its rail unless given."""
    vss, vddb = bench.vss, bench.vddb
    rail = vss if tp == MosType.NMOS else vddb
    device = mos(tp=tp, vth=tb.params.vth, **size)(d=gate, g=gate, s=rail if source is None else source, b=rail)
    feed = Idc(dc=current)(p=vddb, n=gate) if tp == MosType.NMOS else Idc(dc=current)(p=gate, n=vss)
    return device, feed


def testbench(tb: TbParams) -> h.Module:
    """The amplifier testbench of one run: the detector and injection capacitors on the input, the
    load on the output, current-reference biases, the cascode and reference voltages, the
    feedback's bias or reset; the injection step (``Stimulus.CHARGE``), or a DC injection node
    (``Stimulus.NOISE``)."""

    bench, connections = testbench_from_ports(
        "CsaTb", {net.name: net for net in Nets.signals.values() if net.vis == h.Visibility.PORT}
    )
    csa, vss = tb.params, bench.vss
    nmos_input = csa.input_xtors == MosType.NMOS
    other = MosType.PMOS if nmos_input else MosType.NMOS
    bench.vvdd = Vdc(dc=tb.vdd)(p=bench.vdd, n=vss)
    bench.vvref = Vdc(dc=tb.vref_v)(p=bench.vref, n=vss)

    # the bias references draw from their own supply, so the amplifier's is its own current
    bench.vddb = h.Signal()
    bench.vvddb = Vdc(dc=tb.vdd)(p=bench.vddb, n=vss)

    bench.mload, bench.iload = _reference(bench, tb, other, {"w": csa.load_w, "l": csa.load_l}, bench.vload, tb.iref_a)
    # the cascode's copy, fed the load current, its source the drain-source voltage off the input's rail
    bench.vcas_source = h.Signal()
    vds = float(tb.vds_in_v)
    bench.vvcas_source = Vdc(dc=vds if nmos_input else float(tb.vdd) - vds)(p=bench.vcas_source, n=vss)
    bench.mcas, bench.icas = _reference(
        bench, tb, csa.input_xtors, {"w": csa.cas_w, "l": csa.cas_l}, bench.vcas, tb.iref_a, source=bench.vcas_source
    )
    if csa.feedback == Feedback.KRUMMENACHER:
        # the tail carries twice the discharge current: under signal, half of it returns the input
        bench.mtail, bench.itail = _reference(
            bench, tb, other, {"w": csa.tail_w, "l": csa.tail_l}, bench.vfb, 2 * tb.ifb_a
        )
    elif csa.feedback == Feedback.CONTINUOUS:
        # the feedback device's copy, fed its current, standing on the input device's copy: the
        # input's level
        bench.vin_rest = h.Signal()
        bench.min, bench.iin = _reference(
            bench, tb, csa.input_xtors, {"w": csa.in_w, "l": csa.in_l}, bench.vin_rest, tb.iref_a
        )
        bench.mfb, bench.ifb = _reference(
            bench, tb, csa.input_xtors, {"w": csa.fb_w, "l": csa.fb_l}, bench.vfb, tb.ifb_a, source=bench.vin_rest
        )
    else:
        # the switch on until the reset time, then off
        on, off = (float(tb.vdd), 0.0) if nmos_input else (0.0, float(tb.vdd))
        bench.vvfb = Vpulse(
            v1=on,
            v2=off,
            delay=tb.reset_time_s,
            rise=tb.transition_time_s,
            fall=tb.transition_time_s,
            width=2 * float(tb.stop_time_s),
            period=4 * float(tb.stop_time_s),
        )(p=bench.vfb, n=vss)

    bench.inj = h.Signal()
    if tb.stimulus is Stimulus.CHARGE:
        bench.vinj = Vpulse(
            v1=0.0,
            v2=tb.injection_step_v,
            delay=tb.inject_time_s,
            rise=tb.transition_time_s,
            fall=tb.transition_time_s,
            width=2 * float(tb.stop_time_s),
            period=4 * float(tb.stop_time_s),
        )(p=bench.inj, n=vss)
    else:
        bench.vinj = Vdc(dc=0.0)(p=bench.inj, n=vss)
    bench.cinj = C(c=tb.cinj_f)(p=bench.inj, n=bench.inp)
    if float(tb.cdet_f):
        bench.cdet = C(c=tb.cdet_f)(p=bench.inp, n=vss)
    if float(tb.cload_f):
        bench.cload = C(c=tb.cload_f)(p=bench.out, n=vss)
    bench.dut = netlist(tb.params)(**connections)
    return bench


def simulate(tb: TbParams, run_dir: Path) -> Path:
    """Run ``testbench(tb)`` in Spectre in ``run_dir``, its raw output left on disk: after the
    operating point every run starts from (``opdc``), the charge's transient to ``tb.stop_time_s``
    (``tran``, in nutbin), written at its strobes alone, every ``tb.waveform_sample_interval_s``,
    the step bounded to it; or the output noise from ``tb.fstart_hz`` to ``tb.fstop_hz`` referred to
    the injection source (``noise``, in PSF ASCII). One Spectre thread: a campaign runs one process
    per run."""

    pdk = importlib.import_module(f"pdk.{tb.pdk}")
    install = importlib.import_module(f"pdk.{tb.pdk}.hdl21.site").install
    run_dir.mkdir(parents=True, exist_ok=True)
    h.pdk.set_default(pdk.pdk_logic)
    bench = testbench(tb)
    h.pdk.compile(bench)
    attrs = [*spectre.includes(install), *spectre.options(), hs.Save(list(SAVES))]
    if tb.stimulus is Stimulus.CHARGE:
        interval = tb.waveform_sample_interval_s
        attrs.append(
            hs.Tran(
                tstop=tb.stop_time_s,
                name="tran",
                options={"strobeperiod": interval, "maxstep": interval, "strobeoutput": "strobeonly"},
            )
        )
    else:
        # VLSIR's npts: points per decade
        sweep = hs.LogSweep(start=tb.fstart_hz, stop=tb.fstop_hz, npts=tb.points_per_decade)
        attrs.append(hs.Noise(output=bench.out, input_source=bench.vinj, sweep=sweep, name="noise"))
    spectre.run(bench, attrs, run_dir)
    return run_dir / "netlist.raw"
