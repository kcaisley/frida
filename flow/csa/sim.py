"""Charge-sensitive amplifier testbench and named Spectre simulation targets, in every PDK.

The testbench: the input loaded by the detector capacitance, the charge injected through a
small capacitor by a voltage step, the output loaded by the discriminator's input. The load's and
the Krummenacher tail's biases are diode-connected copies of their devices fed the bias currents
from a supply of their own. The cascode's is a copy fed the load
current standing a little off the input device's rail, so that the input device keeps that much
of a drain-source voltage; the continuous feedback's gate a copy of the feedback device fed its
current standing on a copy of the input device, so that at rest the feedback device carries that
current from the input's level. The reset switch
is closed until well before the charge arrives. The charge has the sign that moves the output away
from the input device's rail: electrons into an NMOS input, holes into a PMOS one. A second bench,
without the charge, gives the output noise from 1 Hz to 1 GHz (an operating point and Spectre's
``noise``), which over the response to a known charge is the ENC, as ``TB_CSA_NMOS`` measures it.
"""

import importlib
import json
import math
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import UTC, datetime
from multiprocessing import get_context
from pathlib import Path

import hdl21 as h
import hdl21.sim as hs
import numpy as np
from hdl21.primitives import C, Idc, MosType, Vdc, Vpulse
from vlsirtools.spice import ResultFormat, SimError, SimOptions, SupportedSimulators

from flow.analysis.io import write_measurement
from flow.circuit.devices import mos as _mos
from flow.circuit.ports import testbench_from_ports

from .subckt import CASES, Csa, CsaNets, CsaParams, Feedback


def csa_signal_names() -> dict[str, str]:
    """Derive simulator saves and waveform names from the block's net bundle."""
    names = {"time": "time"}
    for net in CsaNets.signals.values():
        if net.vis == h.Visibility.PORT and net.usage not in (h.Usage.POWER, h.Usage.GROUND):
            names[f"xtop.{net.name}"] = net.name
        if net.usage == h.Usage.POWER:
            names[f"xtop.v{net.name}:p"] = f"i({net.name})"
    return names


@h.paramclass
class CsaTbParams:
    """Parameters which determine the generated charge-sensitive amplifier testbench."""

    pdk = h.Param(dtype=str, desc="PDK the testbench compiles to and simulates in", default="tsmc65")
    vdd = h.Param(dtype=h.Scalar, desc="Supply voltage", default=1.2)
    csa = h.Param(dtype=CsaParams, desc="Amplifier parameters", default=CsaParams())
    cdet = h.Param(dtype=h.Scalar, desc="Detector capacitance on the input (F)", default=100e-15)
    cload = h.Param(dtype=h.Scalar, desc="Load capacitance on the output (F)", default=10e-15)
    cinj = h.Param(dtype=h.Scalar, desc="Injection capacitance (F)", default=1e-15)
    charge_c = h.Param(dtype=h.Scalar, desc="Injected charge's magnitude (C); 0: the noise bench", default=0.5e-15)
    headroom_v = h.Param(
        dtype=h.Scalar, desc="Input device's drain-source voltage the cascode bias leaves", default=0.15
    )
    vref = h.Param(dtype=h.Scalar, desc="Krummenacher reference voltage", default=0.54)
    bias_current_a = h.Param(dtype=float, desc="Current the load's reference sets (A)", default=4e-6)
    feedback_current_a = h.Param(dtype=float, desc="Discharge current under signal (A)", default=10e-9)
    reset_time_s = h.Param(dtype=h.Scalar, desc="Reset switch opens", default=10e-9)
    inject_time_s = h.Param(dtype=h.Scalar, desc="Injection step starts", default=60e-9)
    stop_time_s = h.Param(dtype=h.Scalar, desc="Transient length", default=500e-9)
    transition_time_s = h.Param(dtype=h.Scalar, desc="Injection step and reset edge time", default=100e-12)
    waveform_sample_interval_s = h.Param(dtype=float, desc="Uniform waveform record interval", default=50e-12)
    fstart_hz = h.Param(dtype=float, desc="Noise sweep start", default=1.0)
    fstop_hz = h.Param(dtype=float, desc="Noise sweep stop", default=1e9)
    points_per_decade = h.Param(dtype=int, desc="Noise points per decade", default=10)


def charge_sign(csa: CsaParams) -> float:
    """The injected charge's sign: electrons into an NMOS input, holes into a PMOS one, so the
    output moves away from the input device's rail."""
    return -1.0 if csa.input_xtors == MosType.NMOS else 1.0


def _validate_csa_tb_params(params: CsaTbParams) -> None:
    values = (params.vdd, params.cdet, params.cload, params.cinj, params.charge_c, params.headroom_v, params.vref)
    values += (params.reset_time_s, params.inject_time_s, params.stop_time_s, params.transition_time_s)
    if not all(math.isfinite(float(value)) for value in values):
        raise ValueError("charge-sensitive amplifier testbench values must be finite")
    if min(float(params.vdd), float(params.cinj), params.bias_current_a, params.feedback_current_a) <= 0:
        raise ValueError("amplifier supply, injection capacitance and bias currents must be positive")
    if min(float(params.cdet), float(params.cload), float(params.charge_c)) < 0:
        raise ValueError("amplifier capacitances and charge must not be negative")
    if not (0 < float(params.headroom_v) < float(params.vdd) and 0 <= float(params.vref) <= float(params.vdd)):
        raise ValueError("amplifier bias voltages must lie between the rails")
    edge = float(params.transition_time_s)
    if not 0 < edge < float(params.reset_time_s) < float(params.inject_time_s) < float(params.stop_time_s) - edge:
        raise ValueError("the reset must open and the charge arrive, in that order, within the transient")
    if params.waveform_sample_interval_s <= 0:
        raise ValueError("amplifier record interval must be positive")
    if not 0 < params.fstart_hz < params.fstop_hz or params.points_per_decade < 1:
        raise ValueError("amplifier noise sweep must rise from a positive start")
    if params.csa.feedback == Feedback.RESET and not float(params.charge_c):
        raise ValueError("a reset amplifier holds no operating point for the noise bench")


@h.generator
def CsaTb(params: CsaTbParams) -> h.Module:
    """Generate the charge-sensitive amplifier testbench: the detector and injection capacitors on
    the input, the load on the output, current-reference biases, the cascode and reference
    voltages, the feedback's bias or reset; the injection step, or with no charge a DC injection
    node for the noise bench."""

    _validate_csa_tb_params(params)

    CsaTb, connections = testbench_from_ports(
        "CsaTb", {net.name: net for net in CsaNets.signals.values() if net.vis == h.Visibility.PORT}
    )
    csa, vss = params.csa, CsaTb.vss
    nmos_input = csa.input_xtors == MosType.NMOS
    other = MosType.PMOS if nmos_input else MosType.NMOS
    CsaTb.vvdd = Vdc(dc=params.vdd)(p=CsaTb.vdd, n=vss)
    CsaTb.vvref = Vdc(dc=params.vref)(p=CsaTb.vref, n=vss)

    # the bias references draw from their own supply, so the amplifier's is its own current
    CsaTb.vddb = h.Signal()
    CsaTb.vvddb = Vdc(dc=params.vdd)(p=CsaTb.vddb, n=vss)

    def reference(tp, size, gate, current, source=None):
        """A diode-connected copy fed ``current``: from the reference supply into an NMOS, from a
        PMOS to ground; its source on its rail unless given."""
        rail = vss if tp == MosType.NMOS else CsaTb.vddb
        device = _mos(tp=tp, vth=csa.vth, **size)(d=gate, g=gate, s=rail if source is None else source, b=rail)
        feed = Idc(dc=current)(p=CsaTb.vddb, n=gate) if tp == MosType.NMOS else Idc(dc=current)(p=gate, n=vss)
        return device, feed

    CsaTb.mload, CsaTb.iload = reference(other, {"w": csa.load_w, "l": csa.load_l}, CsaTb.vload, params.bias_current_a)
    # the cascode's copy, fed the load current, its source the headroom off the input's rail
    CsaTb.vcas_source = h.Signal()
    headroom = float(params.headroom_v)
    CsaTb.vvcas_source = Vdc(dc=headroom if nmos_input else float(params.vdd) - headroom)(p=CsaTb.vcas_source, n=vss)
    CsaTb.mcas, CsaTb.icas = reference(
        csa.input_xtors,
        {"w": csa.cas_w, "l": csa.cas_l},
        CsaTb.vcas,
        params.bias_current_a,
        source=CsaTb.vcas_source,
    )
    if csa.feedback == Feedback.KRUMMENACHER:
        # the tail carries twice the discharge current: under signal, half of it returns the input
        CsaTb.mtail, CsaTb.itail = reference(
            other, {"w": csa.tail_w, "l": csa.tail_l}, CsaTb.vfb, 2 * params.feedback_current_a
        )
    elif csa.feedback == Feedback.CONTINUOUS:
        # the feedback device's copy, fed its current, standing on the input device's copy: the
        # input's level
        CsaTb.vin_rest = h.Signal()
        CsaTb.min, CsaTb.iin = reference(
            csa.input_xtors, {"w": csa.in_w, "l": csa.in_l}, CsaTb.vin_rest, params.bias_current_a
        )
        CsaTb.mfb, CsaTb.ifb = reference(
            csa.input_xtors,
            {"w": csa.fb_w, "l": csa.fb_l},
            CsaTb.vfb,
            params.feedback_current_a,
            source=CsaTb.vin_rest,
        )
    else:
        # the switch on until the reset time, then off
        on, off = (float(params.vdd), 0.0) if nmos_input else (0.0, float(params.vdd))
        CsaTb.vvfb = Vpulse(
            v1=on,
            v2=off,
            delay=params.reset_time_s,
            rise=params.transition_time_s,
            fall=params.transition_time_s,
            width=2 * float(params.stop_time_s),
            period=4 * float(params.stop_time_s),
        )(p=CsaTb.vfb, n=vss)

    CsaTb.inj = h.Signal()
    if float(params.charge_c):
        step = charge_sign(csa) * float(params.charge_c) / float(params.cinj)
        CsaTb.vinj = Vpulse(
            v1=0.0,
            v2=step,
            delay=params.inject_time_s,
            rise=params.transition_time_s,
            fall=params.transition_time_s,
            width=2 * float(params.stop_time_s),
            period=4 * float(params.stop_time_s),
        )(p=CsaTb.inj, n=vss)
    else:
        CsaTb.vinj = Vdc(dc=0.0)(p=CsaTb.inj, n=vss)
    CsaTb.cinj = C(c=params.cinj)(p=CsaTb.inj, n=CsaTb.inp)
    if float(params.cdet):
        CsaTb.cdet = C(c=params.cdet)(p=CsaTb.inp, n=vss)
    if float(params.cload):
        CsaTb.cload = C(c=params.cload)(p=CsaTb.out, n=vss)
    CsaTb.dut = Csa(csa)(**connections)
    return CsaTb


def _run_csa_sim(run_dir: Path, params: CsaTbParams, *, check: bool = False) -> Path:
    """Run one amplifier's transient in its PDK, or with no charge its operating point and output
    noise, and return the raw file (the noise bench's in PSF ASCII: VLSIR writes a noise
    analysis's results so) (``check``: Spectre's static checks besides)."""

    pdk = importlib.import_module(f"pdk.{params.pdk}")
    install = importlib.import_module(f"pdk.{params.pdk}.hdl21.site").install

    run_dir.mkdir(parents=True, exist_ok=True)
    h.pdk.set_default(pdk.pdk_logic)
    tb = CsaTb(params)
    h.pdk.compile(tb)
    attrs = [
        install.include(h.pdk.Corner.TYP),
        # what else the PDK's simulations take, in this order: TSMC's pre-simulation settings,
        # the device names its netlists use (pdk/<name>/hdl21)
        *(getattr(install, name)() for name in ("include_pre_simulation", "include_devices") if hasattr(install, name)),
        hs.Options(name="temp", value=25.0),
        hs.Options(name="save", value="selected"),
        hs.Save([raw for raw in csa_signal_names() if raw != "time"]),
    ]
    if check:
        attrs.append(
            h.Literal(
                "check_caps static_capacitor type=distr\n"
                "check_erc static_erc floatbulk=all floatgate=no_top_moscap dangle=no_top "
                "gate2power=on gate2ground=on\n"
                "check_highz static_highz node=[*] fanout=gate_has_driver_no_moscap\n"
                "check_dcpath static_dcpath net=[xtop.vdd 0]\n"
                "check_topology static_topology node=[*] pin2gnd=on"
            )
        )
    if float(params.charge_c):
        interval = params.waveform_sample_interval_s
        attrs.append(
            hs.Tran(
                tstop=params.stop_time_s,
                name="tran",
                options={"strobeperiod": interval, "maxstep": interval, "strobeoutput": "strobeonly"},
            )
        )
    else:
        # VLSIR's npts: points per decade
        sweep = hs.LogSweep(start=params.fstart_hz, stop=params.fstop_hz, npts=params.points_per_decade)
        attrs += [hs.Op(name="op"), hs.Noise(output=tb.out, input_source=tb.vinj, sweep=sweep, name="noise")]
    # the simulator's error holds its simulation, which cannot cross back from a worker process:
    # raise it as text
    try:
        hs.Sim(tb=tb, attrs=attrs).run(
            SimOptions(
                simulator=SupportedSimulators.SPECTRE,
                fmt=ResultFormat.NONE if check else ResultFormat.SIM_DATA,
                rundir=run_dir,
                simulator_args=(
                    "+preset=mx",
                    "+mt=1",
                    "+lqtimeout",
                    "3600",
                    "+escchars",
                    "+log",
                    "spectre.log",
                    *(("-ahdllint=warn", "-ahdllint_log", "ahdllint.log") if check else ()),
                ),
            )
        )
    except SimError as error:
        raise RuntimeError(f"Spectre failed in {run_dir}: {error}") from None
    return run_dir / "netlist.raw"


# The characterization, in every PDK at its own core supply: each amplifier's response to a
# quarter, a half, one and two femtocoulombs (1.6 to 12.5 thousand electrons) on 100 fF of
# detector, and its output noise without charge (but the reset amplifier's, open at rest). The
# Krummenacher reference sits 45 % of the supply above ground, the input device's drain 150 mV off
# its rail (the continuous and reset amplifiers' outputs rest at the input's level, one
# gate-source voltage off it). The load carries 4 µA; the feedback discharges at 10 nA.
CHARGES_C = (0.25e-15, 0.5e-15, 1e-15, 2e-15)
VREF = 0.45


def csa_characterization(run_dir: Path, *, check: bool = False) -> Path:
    """Run every amplifier's charge response and output noise in every PDK: 19 runs each.

    Each response writes ``<pdk>/<case>/q<aC>/result.h5`` (a ``MeasCsa``), each noise bench
    ``<pdk>/<case>/noise/result.h5`` (a ``MeasCsaNoise``). ``check`` runs each case's half
    femtocoulomb with Spectre's checks instead, writing no measurement.
    """

    from vlsirtools.spice.spectre import parse_psfascii

    from flow.analysis.types import MeasInfo
    from flow.circuit.results import read_transient_wave
    from flow.comp.layout import PDKS
    from flow.csa.analysis import MeasCsa, MeasCsaNoise

    run_dir.mkdir(parents=True, exist_ok=True)
    jobs = {}
    for pdk in PDKS:
        supply = importlib.import_module(f"pdk.{pdk}.hdl21.site").install.supply_voltage(h.pdk.Corner.TYP)
        for case, csa in CASES.items():
            biases = {"pdk": pdk, "csa": csa, "vdd": supply, "vref": round(VREF * supply, 4)}
            charges = (0.5e-15,) if check else CHARGES_C
            for charge in charges:
                jobs[f"{pdk}/{case}/q{round(charge * 1e18)}"] = CsaTbParams(**biases, charge_c=charge)
            if not check and csa.feedback != Feedback.RESET:
                jobs[f"{pdk}/{case}/noise"] = CsaTbParams(**biases, charge_c=0.0)
    names = csa_signal_names()
    failures: dict[str, str] = {}
    # one pool per PDK: hdl21 compiles each generated module in place, for the first PDK it meets
    for pdk in PDKS:
        with ProcessPoolExecutor(max_workers=16, mp_context=get_context("spawn")) as executor:
            futures = {
                executor.submit(_run_csa_sim, run_dir / name, params, check=check): (name, params)
                for name, params in jobs.items()
                if params.pdk == pdk
            }
            for future in as_completed(futures):
                name, params = futures[future]
                try:
                    raw_path = future.result()
                    if check:
                        continue
                    info = MeasInfo(
                        backend="spice",
                        timestamp_utc=datetime.fromtimestamp(raw_path.stat().st_mtime, tz=UTC),
                        instruments={"simulator": "Spectre"},
                        readbacks={
                            "pdk": name.split("/")[0],
                            "case": name.split("/")[1],
                            "raw_file": raw_path.name,
                            "supply_current_convention": "positive_current_draw",
                        },
                    )
                    if not float(params.charge_c):
                        analyses = parse_psfascii(raw_path)
                        op, noise = analyses["op"].data, analyses["noise"].data
                        info.readbacks.update(
                            {
                                "op_supply_current_a": -float(np.real(op["xtop.vvdd:p"][0])),
                                "op_out_v": float(np.real(op["xtop.out"][0])),
                                "op_inp_v": float(np.real(op["xtop.inp"][0])),
                            }
                        )
                        measurement = MeasCsaNoise(
                            group=None,
                            index=None,
                            dut=params.csa,
                            info=info,
                            param=params,
                            frequency_hz=np.real(np.asarray(noise["freq"])).astype(np.float64),
                            output_noise_v_rthz=np.asarray(noise["out"], dtype=np.float64),
                        )
                        write_measurement(raw_path.parent / "result.h5", measurement)
                        continue
                    # one record from time zero on the stored grid; the supply current as positive draw
                    wave, raw_points = read_transient_wave(
                        raw_path, names, params.waveform_sample_interval_s, supply_rails=("vdd",)
                    )
                    info.readbacks.update(
                        {"waveform_sample_interval_s": params.waveform_sample_interval_s, "raw_points": raw_points}
                    )
                    measurement = MeasCsa(
                        group=None,
                        index=None,
                        dut=params.csa,
                        info=info,
                        param=params,
                        trial_index=np.arange(1, dtype=np.int64),
                        wave=wave,
                    )
                    write_measurement(raw_path.parent / "result.h5", measurement)
                except Exception as error:  # noqa: BLE001 - report every independent point failure
                    failures[name] = repr(error)
    if failures:
        failure_path = run_dir / "failures.json"
        failure_path.write_text(json.dumps(failures, indent=2) + "\n")
        raise RuntimeError(f"{len(failures)} amplifier points failed; see {failure_path}")
    return run_dir
