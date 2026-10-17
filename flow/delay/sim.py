"""Delay line and ring oscillator testbench and named TSMC65 Spectre simulation targets.

The testbench follows Usb2Phy's ring-oscillator benches (``IloRingFreqTb``, ``CmlRoFreqTb``): a
supply source, the rings' enable and a kick-start (complementary steps coupled onto the outputs
just after enable), the bias sources and output loads, and for a delay line the complementary input
clock of Usb2Phy's ``DiffClkGen``. Every case gets the same stimulus; a ring ignores the input
clock and a delay line the enable. Usb2Phy's ring benches sweep
the supply (``vddsweep``) and the frequency-control code (``test_dac_code``); here the supply and
one control voltage, which sets every analog control at once: ``vbn`` and ``vctrl`` to it and
``vbp`` to the supply minus it, so a starved stage's NMOS and PMOS starve alike.
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
from hdl21.primitives import C, Vdc, Vpulse
from vlsirtools.spice import ResultFormat, SimOptions, SupportedSimulators

from flow.analysis.io import interpolate_wave_records, write_measurement
from flow.circuit.ports import testbench_from_ports

from .subckt import CASES, Delay, DelayNets, DelayParams


def delay_signal_names() -> dict[str, str]:
    """Derive simulator saves and waveform names from the block's net bundle."""
    names = {"time": "time"}
    for net in DelayNets.signals.values():
        if net.vis == h.Visibility.PORT and net.usage not in (h.Usage.POWER, h.Usage.GROUND):
            names[f"xtop.{net.name}"] = net.name
        if net.usage == h.Usage.POWER:
            names[f"xtop.v{net.name}:p"] = f"i({net.name})"
    return names


@h.paramclass
class DelayTbParams:
    """Parameters which determine the generated delay line or ring testbench."""

    waveform_sample_interval_s = h.Param(
        dtype=float, desc="Maximum raw step and stored waveform spacing", default=2e-12
    )
    vdd = h.Param(dtype=h.Scalar, desc="Supply voltage", default=1.2)
    delay = h.Param(dtype=DelayParams, desc="Delay line or ring parameters", default=DelayParams())
    control_v = h.Param(dtype=h.Scalar, desc="Control voltage: vbn and vctrl, and vdd minus vbp", default=0.8)
    cload = h.Param(dtype=h.Scalar, desc="Load capacitance on each output (F)", default=2e-15)
    ckick = h.Param(dtype=h.Scalar, desc="Kick-start coupling capacitance on each output (F)", default=1e-15)
    vinj = h.Param(dtype=h.Scalar, desc="Injection input level", default=0.0)
    period_s = h.Param(dtype=h.Scalar, desc="Input clock period (a delay line)", default=4e-9)
    transition_time_s = h.Param(dtype=h.Scalar, desc="Input and enable rise and fall time", default=50e-12)
    enable_delay_s = h.Param(dtype=h.Scalar, desc="Time before en rises (the rings' kick-start)", default=1e-9)
    tstop_s = h.Param(dtype=h.Scalar, desc="Transient length", default=40e-9)


def _validate_delay_tb_params(params: DelayTbParams) -> None:
    values = (
        params.waveform_sample_interval_s,
        params.vdd,
        params.control_v,
        params.cload,
        params.ckick,
        params.vinj,
        params.period_s,
        params.transition_time_s,
        params.enable_delay_s,
        params.tstop_s,
    )
    if not all(math.isfinite(float(value)) for value in values):
        raise ValueError("delay testbench values must be finite")
    if min(float(params.vdd), float(params.cload), float(params.ckick), float(params.waveform_sample_interval_s)) <= 0:
        raise ValueError("delay supply, loads, and sample interval must be positive")
    if not 0 <= float(params.control_v) <= float(params.vdd):
        raise ValueError("delay control voltage must lie between the rails")
    if float(params.period_s) <= 2 * float(params.transition_time_s) or float(params.transition_time_s) <= 0:
        raise ValueError("delay input period must exceed both transitions, which must be positive")
    if not 0 <= float(params.enable_delay_s) < float(params.tstop_s):
        raise ValueError("delay enable must rise within the transient")


@h.generator
def DelayTb(params: DelayTbParams) -> h.Module:
    """Generate the shared delay line and ring testbench (Usb2Phy ``IloRingFreqTb`` and ``DiffClkGen``)."""

    _validate_delay_tb_params(params)

    DelayTb, connections = testbench_from_ports(
        "DelayTb", {net.name: net for net in DelayNets.signals.values() if net.vis == h.Visibility.PORT}
    )
    vdd, vss = params.vdd, DelayTb.vss
    DelayTb.vvdd = Vdc(dc=vdd)(p=DelayTb.vdd, n=vss)
    # DiffClkGen: complementary rail-to-rail halves, the period's first quarter as delay
    edge = {"rise": params.transition_time_s, "fall": params.transition_time_s}
    width = float(params.period_s) / 2 - float(params.transition_time_s)
    clock = {"period": params.period_s, "width": width, "delay": float(params.period_s) / 4, **edge}
    DelayTb.vinp = Vpulse(v1=0.0, v2=vdd, **clock)(p=DelayTb.inp, n=vss)
    DelayTb.vinn = Vpulse(v1=vdd, v2=0.0, **clock)(p=DelayTb.inn, n=vss)
    # the kick-start: en rises once and stays high (one pulse longer than the run)
    DelayTb.ven = Vpulse(v1=0.0, v2=vdd, period=1.0, width=0.5, delay=params.enable_delay_s, **edge)(
        p=DelayTb.en, n=vss
    )
    DelayTb.vinj = Vdc(dc=params.vinj)(p=DelayTb.inj, n=vss)
    DelayTb.vvbn = Vdc(dc=params.control_v)(p=DelayTb.vbn, n=vss)
    DelayTb.vvbp = Vdc(dc=float(vdd) - float(params.control_v))(p=DelayTb.vbp, n=vss)
    DelayTb.vvctrl = Vdc(dc=params.control_v)(p=DelayTb.vctrl, n=vss)
    DelayTb.cloadp = C(c=params.cload)(p=DelayTb.outp, n=vss)
    DelayTb.cloadn = C(c=params.cload)(p=DelayTb.outn, n=vss)
    # the kick-start (Usb2Phy's injection pulse): complementary steps through small capacitors on
    # the outputs just after en rises, so a coupled ring leaves the common-mode state en holds it in
    kick = {"period": 1.0, "width": 0.5, "delay": float(params.enable_delay_s) + 2 * float(params.transition_time_s)}
    DelayTb.kickp, DelayTb.kickn = h.Signal(), h.Signal()
    DelayTb.vkickp = Vpulse(v1=0.0, v2=vdd, **kick, **edge)(p=DelayTb.kickp, n=vss)
    DelayTb.vkickn = Vpulse(v1=vdd, v2=0.0, **kick, **edge)(p=DelayTb.kickn, n=vss)
    DelayTb.ckickp = C(c=params.ckick)(p=DelayTb.kickp, n=DelayTb.outp)
    DelayTb.ckickn = C(c=params.ckick)(p=DelayTb.kickn, n=DelayTb.outn)
    DelayTb.dut = Delay(params.delay)(**connections)
    return DelayTb


def _run_delay_sim(run_dir: Path, params: DelayTbParams, *, check: bool = False) -> Path:
    """Run one delay testbench transient in TSMC65 and return its raw file.

    ``check`` adds Spectre's static and connectivity checks and shortens the run to a tenth.
    """

    from pdk import tsmc65
    from pdk.tsmc65.hdl21 import site

    run_dir.mkdir(parents=True, exist_ok=True)
    h.pdk.set_default(tsmc65.pdk_logic)
    tb = DelayTb(params)
    h.pdk.compile(tb)
    interval = params.waveform_sample_interval_s
    attrs = [
        site.install.include(h.pdk.Corner.TYP),
        site.install.include_pre_simulation(),
        hs.Options(name="temp", value=25.0),
        hs.Options(name="save", value="selected"),
        hs.Save([raw for raw in delay_signal_names() if raw != "time"]),
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
            tstop=float(params.tstop_s) / 10 if check else params.tstop_s,
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


# The characterization: Usb2Phy's supply sweep around TSMC65's 1.2 V core supply at the nominal
# control, and a control sweep at the nominal supply (the shared point once).
SUPPLY_SWEEP_V = (0.9, 1.0, 1.1, 1.2, 1.3)
CONTROL_SWEEP_V = (0.5, 0.6, 0.7, 0.8, 0.9, 1.0, 1.1, 1.2)
NOMINAL_SUPPLY_V = 1.2
NOMINAL_CONTROL_V = 0.8


def delay_characterization(run_dir: Path, *, check: bool = False) -> Path:
    """Run every delay case at every supply and control point: 7 cases, 12 points each (84 runs).

    Each point writes ``<case>/vdd<mV>_ctrl<mV>/result.h5`` (a ``MeasDelay``). ``check`` runs
    the nominal point of each case with Spectre's checks instead, writing no measurement.
    """

    from flow.analysis.types import MeasInfo, Wave
    from flow.circuit.results import read_raw_transient
    from flow.delay.analysis import MeasDelay

    run_dir.mkdir(parents=True, exist_ok=True)
    points = list(
        dict.fromkeys(
            [(vdd, NOMINAL_CONTROL_V) for vdd in SUPPLY_SWEEP_V]
            + [(NOMINAL_SUPPLY_V, control) for control in CONTROL_SWEEP_V]
        )
    )
    if check:
        points = [(NOMINAL_SUPPLY_V, NOMINAL_CONTROL_V)]
    jobs = {
        f"{case}/vdd{round(vdd * 1e3)}_ctrl{round(control * 1e3)}": DelayTbParams(
            delay=delay, vdd=vdd, control_v=control
        )
        for case, delay in CASES.items()
        for vdd, control in points
    }
    names = delay_signal_names()
    failures: dict[str, str] = {}
    with ProcessPoolExecutor(max_workers=16, mp_context=get_context("spawn")) as executor:
        futures = {
            executor.submit(_run_delay_sim, run_dir / name, params, check=check): (name, params)
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
                measurement = MeasDelay(
                    group=None,
                    index=None,
                    dut=params.delay,
                    info=MeasInfo(
                        backend="spice",
                        timestamp_utc=datetime.fromtimestamp(raw_path.stat().st_mtime, tz=UTC),
                        instruments={"simulator": "Spectre"},
                        readbacks={
                            "case": name.split("/")[0],
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
        raise RuntimeError(f"{len(failures)} delay points failed; see {failure_path}")
    return run_dir


def main() -> None:
    """Create one output directory and run one named delay line or ring target."""

    targets = {target.__name__: target for target in (delay_characterization,)}
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("target", nargs="?", choices=sorted(targets))
    args = parser.parse_args()
    if args.target is None:
        print("Available delay line and ring simulation targets:")
        for name in sorted(targets):
            print(f"  {name}")
        return
    run_dir = (
        Path(__file__).resolve().parents[2]
        / "build"
        / "sim"
        / "delay"
        / args.target
        / datetime.now().astimezone().strftime("%Y%m%d_%H%M%S")
    )
    run_dir.mkdir(parents=True, exist_ok=False)
    targets[args.target](run_dir)


if __name__ == "__main__":
    main()
