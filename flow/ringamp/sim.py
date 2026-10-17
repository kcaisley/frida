"""Ring amplifier testbench and named TSMC65 Spectre simulation targets.

The testbench follows BAG's ring amplifier bench (``ringamp_se``): fixed tail and dead-zone
biases, a load on the output, and the enable. Open loop, the input is a slow triangle about the
common mode (the transfer curve and its supply current); closed loop, an input capacitor and a
feedback capacitor of the same size set a gain of -1, a 1 GOhm resistor across the feedback
capacitor holds the amplifier at its trip point at DC, and a step through the input capacitor
asks it to settle (BAG's settling measurement). Both cases get the same stimulus; the
characterization sweeps the dead-zone bias, and the step.
"""

import argparse
import json
import math
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import UTC, datetime
from multiprocessing import get_context
from pathlib import Path

import hdl21 as h
import hdl21.sim as hs
import numpy as np
from hdl21.primitives import C, R, Vdc, Vpulse
from vlsirtools.spice import ResultFormat, SimOptions, SupportedSimulators

from flow.analysis.io import interpolate_wave_records, write_measurement
from flow.circuit.ports import testbench_from_ports

from .subckt import CASES, Ringamp, RingampNets, RingampParams


def ringamp_signal_names() -> dict[str, str]:
    """Derive simulator saves and waveform names from the block's net bundle."""
    names = {"time": "time"}
    for net in RingampNets.signals.values():
        if net.vis == h.Visibility.PORT and net.usage not in (h.Usage.POWER, h.Usage.GROUND):
            names[f"xtop.{net.name}"] = net.name
        if net.usage == h.Usage.POWER:
            names[f"xtop.v{net.name}:p"] = f"i({net.name})"
    return names


@h.paramclass
class RingampTbParams:
    """Parameters which determine the generated ring amplifier testbench."""

    waveform_sample_interval_s = h.Param(
        dtype=float, desc="Maximum raw step and stored waveform spacing", default=2e-12
    )
    vdd = h.Param(dtype=h.Scalar, desc="Supply voltage", default=1.2)
    ringamp = h.Param(dtype=RingampParams, desc="Ring amplifier parameters", default=RingampParams())
    cload = h.Param(dtype=h.Scalar, desc="Load capacitance on out (F)", default=50e-15)
    vcm = h.Param(dtype=h.Scalar, desc="Input common mode (open loop)", default=0.6)
    vstep = h.Param(dtype=h.Scalar, desc="Input excursion either side of vcm (open loop)", default=0.3)
    vcmfb = h.Param(dtype=h.Scalar, desc="Tail bias", default=0.6)
    biasn = h.Param(dtype=h.Scalar, desc="Dead-zone NMOS bias", default=0.5)
    biasp = h.Param(dtype=h.Scalar, desc="Dead-zone PMOS bias", default=0.7)
    period_s = h.Param(dtype=h.Scalar, desc="Input ramp time (open loop)", default=20e-9)
    transition_time_s = h.Param(dtype=h.Scalar, desc="Enable and step rise and fall time", default=50e-12)
    closed_loop = h.Param(
        dtype=bool, desc="Capacitive feedback and an input step, not the open-loop ramp", default=False
    )
    cin = h.Param(dtype=h.Scalar, desc="Input capacitor (closed loop, F)", default=100e-15)
    cfb = h.Param(dtype=h.Scalar, desc="Feedback capacitor (closed loop, F)", default=100e-15)
    step_v = h.Param(dtype=h.Scalar, desc="Step through the input capacitor (closed loop)", default=0.1)
    step_delay_s = h.Param(dtype=h.Scalar, desc="Time of the step (closed loop)", default=2e-9)
    settle_time_s = h.Param(dtype=h.Scalar, desc="Run after the step (closed loop)", default=10e-9)


def _validate_ringamp_tb_params(params: RingampTbParams) -> None:
    values = (params.vdd, params.cload, params.period_s, params.transition_time_s, params.cin, params.cfb)
    values += (params.step_v, params.step_delay_s, params.settle_time_s)
    if not all(math.isfinite(float(value)) for value in (*values, params.waveform_sample_interval_s)):
        raise ValueError("ring amplifier testbench values must be finite")
    if min(float(params.vdd), float(params.cload), float(params.cin), float(params.cfb)) <= 0:
        raise ValueError("ring amplifier supply and capacitors must be positive")
    if float(params.transition_time_s) <= 0 or float(params.period_s) <= 2 * float(params.transition_time_s):
        raise ValueError("ring amplifier period must exceed both transitions, which must be positive")
    if min(float(params.step_delay_s), float(params.settle_time_s), params.waveform_sample_interval_s) <= 0:
        raise ValueError("ring amplifier step time, settling time, and sample interval must be positive")
    if abs(float(params.step_v)) >= float(params.vdd) / 2:
        raise ValueError("ring amplifier step must stay within half the supply")


@h.generator
def RingampTb(params: RingampTbParams) -> h.Module:
    """Generate the ring amplifier testbench: open loop, en high after a quarter period and inp a
    triangle about vcm (one period up, one down); closed loop, en high throughout, inp between an
    input and a feedback capacitor, a 1 GOhm DC feedback, and a step through the input capacitor;
    fixed biases and a load on out either way."""

    _validate_ringamp_tb_params(params)

    RingampTb, connections = testbench_from_ports(
        "RingampTb", {net.name: net for net in RingampNets.signals.values() if net.vis == h.Visibility.PORT}
    )
    vss = RingampTb.vss
    vdd, period = float(params.vdd), float(params.period_s)
    vcm, step = float(params.vcm), float(params.vstep)
    edge = {"rise": params.transition_time_s, "fall": params.transition_time_s}
    RingampTb.vvdd = Vdc(dc=vdd)(p=RingampTb.vdd, n=vss)
    # closed loop the amplifier is on from the start, so its DC point is the trip point
    off = vdd if params.closed_loop else 0.0
    RingampTb.ven = Vpulse(v1=off, v2=vdd, period=1.0, width=0.5, delay=period / 4, **edge)(p=RingampTb.en, n=vss)
    RingampTb.venb = Vpulse(v1=vdd - off, v2=0.0, period=1.0, width=0.5, delay=period / 4, **edge)(
        p=RingampTb.enb, n=vss
    )
    if params.closed_loop:
        RingampTb.drive = h.Signal()
        RingampTb.vdrive = Vpulse(
            v1=vcm, v2=vcm + float(params.step_v), period=1.0, width=0.5, delay=params.step_delay_s, **edge
        )(p=RingampTb.drive, n=vss)
        RingampTb.cin = C(c=params.cin)(p=RingampTb.drive, n=RingampTb.inp)
        RingampTb.cfb = C(c=params.cfb)(p=RingampTb.out, n=RingampTb.inp)
        RingampTb.rfb = R(r=1e9)(p=RingampTb.out, n=RingampTb.inp)
    else:
        # a triangle: the rise and the fall each one period long
        RingampTb.vinp = Vpulse(
            v1=vcm - step, v2=vcm + step, period=3 * period, width=0.0, delay=period / 2, rise=period, fall=period
        )(p=RingampTb.inp, n=vss)
    RingampTb.vvcmfb = Vdc(dc=params.vcmfb)(p=RingampTb.vcmfb, n=vss)
    RingampTb.vbiasn = Vdc(dc=params.biasn)(p=RingampTb.biasn, n=vss)
    RingampTb.vbiasp = Vdc(dc=params.biasp)(p=RingampTb.biasp, n=vss)
    RingampTb.cload = C(c=params.cload)(p=RingampTb.out, n=vss)
    RingampTb.dut = Ringamp(params.ringamp)(**connections)
    return RingampTb


def _run_ringamp_sim(run_dir: Path, params: RingampTbParams, *, check: bool = False) -> Path:
    """Run one ring amplifier testbench transient in TSMC65 and return its raw file: the open-loop
    triangle (2.5 periods), or the closed-loop step and its settling.

    ``check`` adds Spectre's static and connectivity checks and shortens the run to a tenth.
    """

    from pdk import tsmc65
    from pdk.tsmc65.hdl21 import site

    run_dir.mkdir(parents=True, exist_ok=True)
    h.pdk.set_default(tsmc65.pdk_logic)
    tb = RingampTb(params)
    h.pdk.compile(tb)
    interval = params.waveform_sample_interval_s
    tstop = (
        float(params.step_delay_s) + float(params.settle_time_s) if params.closed_loop else 2.5 * float(params.period_s)
    )
    attrs = [
        site.install.include(h.pdk.Corner.TYP),
        site.install.include_pre_simulation(),
        hs.Options(name="temp", value=25.0),
        hs.Options(name="save", value="selected"),
        hs.Save([raw for raw in ringamp_signal_names() if raw != "time"]),
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
    attrs.append(
        hs.Tran(
            tstop=tstop / 10 if check else tstop,
            name="tran",
            options={"strobeperiod": interval, "maxstep": interval, "strobeoutput": "strobeonly"},
        )
    )
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
    return run_dir / "netlist.raw"


# The characterization: the dead-zone bias (biasn its drive above vss, biasp the same below vdd)
# open loop and with a 100 mV closed-loop step, and the step from -200 to 200 mV at the nominal bias.
DEAD_ZONE_SWEEP_V = (0.3, 0.4, 0.5, 0.6, 0.7)
STEP_SWEEP_V = (-0.2, -0.1, -0.025, 0.025, 0.1, 0.2)
NOMINAL_DEAD_ZONE_V = 0.5
NOMINAL_STEP_V = 0.1
NOMINAL_SUPPLY_V = 1.2


def ringamp_characterization(run_dir: Path, *, check: bool = False) -> Path:
    """Run both ring amplifiers open loop and closed loop over the dead-zone bias and the step: 32 runs.

    Each point writes ``<case>/<sweep>/<point>/result.h5`` (a ``MeasRingamp``). ``check`` runs the
    nominal open-loop and closed-loop points of each case with Spectre's checks instead.
    """

    from flow.analysis.types import MeasInfo, Wave
    from flow.circuit.results import read_raw_transient
    from flow.ringamp.analysis import MeasRingamp

    run_dir.mkdir(parents=True, exist_ok=True)
    points = {
        "open": [(drive, NOMINAL_STEP_V, False) for drive in DEAD_ZONE_SWEEP_V],
        "deadzone": [(drive, NOMINAL_STEP_V, True) for drive in DEAD_ZONE_SWEEP_V],
        "step": [(NOMINAL_DEAD_ZONE_V, step, True) for step in STEP_SWEEP_V],
    }
    if check:
        points = {"check": [(NOMINAL_DEAD_ZONE_V, NOMINAL_STEP_V, closed) for closed in (False, True)]}
    jobs = {
        f"{case}/{sweep}/{'closed' if closed else 'open'}_drive{round(drive * 1e3)}mv_step{round(step * 1e3)}mv": (
            RingampTbParams(
                ringamp=ringamp,
                biasn=drive,
                biasp=NOMINAL_SUPPLY_V - drive,
                closed_loop=closed,
                step_v=step,
            )
        )
        for case, ringamp in CASES.items()
        for sweep, values in points.items()
        for drive, step, closed in values
    }
    names = ringamp_signal_names()
    failures: dict[str, str] = {}
    with ProcessPoolExecutor(max_workers=16, mp_context=get_context("spawn")) as executor:
        futures = {
            executor.submit(_run_ringamp_sim, run_dir / name, params, check=check): (name, params)
            for name, params in jobs.items()
        }
        for future in as_completed(futures):
            name, params = futures[future]
            try:
                raw_path = future.result()
                if check:
                    continue
                # one record from time zero on the stored grid; the supply current as positive draw
                result = read_raw_transient(raw_path)
                times_s = np.asarray(result.data["time"])
                interval = params.waveform_sample_interval_s
                window = [(float(times_s[0]), float(times_s[-1]))]
                time_s, voltages = interpolate_wave_records(
                    times_s,
                    {
                        names[key]: value
                        for key, value in result.data.items()
                        if not names[key].startswith(("i(", "time"))
                    },
                    window,
                    interval,
                )
                _, currents = interpolate_wave_records(
                    times_s,
                    {
                        names[key][2:-1]: -np.asarray(value)
                        for key, value in result.data.items()
                        if names[key].startswith("i(")
                    },
                    window,
                    interval,
                )
                measurement = MeasRingamp(
                    group=None,
                    index=None,
                    dut=params.ringamp,
                    info=MeasInfo(
                        backend="spice",
                        timestamp_utc=datetime.fromtimestamp(raw_path.stat().st_mtime, tz=UTC),
                        instruments={"simulator": "Spectre"},
                        readbacks={
                            "case": name.split("/")[0],
                            "sweep": name.split("/")[1],
                            "signal_map_json": json.dumps(names, sort_keys=True),
                            "raw_file": raw_path.name,
                            "raw_points": len(times_s),
                            "waveform_sample_interval_s": interval,
                            "supply_current_convention": "positive_current_draw",
                        },
                    ),
                    param=params,
                    trial_index=np.arange(1, dtype=np.int64),
                    wave=Wave(record_index=np.arange(1, dtype=np.int64), time_s=time_s, v=voltages, i=currents),
                )
                write_measurement(raw_path.parent / "result.h5", measurement)
            except Exception as error:  # noqa: BLE001 - report every independent point failure
                failures[name] = repr(error)
    if failures:
        failure_path = run_dir / "failures.json"
        failure_path.write_text(json.dumps(failures, indent=2) + "\n")
        raise RuntimeError(f"{len(failures)} ring amplifier points failed; see {failure_path}")
    return run_dir


def main() -> None:
    """Create one output directory and run one named ring amplifier target."""

    targets = {target.__name__: target for target in (ringamp_characterization,)}
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("target", nargs="?", choices=sorted(targets))
    args = parser.parse_args()
    if args.target is None:
        print("Available ring amplifier simulation targets:")
        for name in sorted(targets):
            print(f"  {name}")
        return
    run_dir = (
        Path(__file__).resolve().parents[2]
        / "build"
        / "sim"
        / "ringamp"
        / args.target
        / datetime.now().astimezone().strftime("%Y%m%d_%H%M%S")
    )
    run_dir.mkdir(parents=True, exist_ok=False)
    targets[args.target](run_dir)


if __name__ == "__main__":
    main()
