"""Phase interpolator testbench and named TSMC65 Spectre simulation targets.

The testbench follows Usb2Phy's ``PhaseInterpTb``: two clock phases, A and B a set spacing
later, with their complements, fixed biases and a load on each output; Usb2Phy measures the
output's differential crossing (``.measure tdelay when V(dck_p)-V(dck_n)=0``). Here the cases'
weights are fixed, so the characterization sweeps the phase spacing (the interpolator's
transfer and linearity) and the clock period at quadrature spacing.
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

from .subckt import CASES, Pi, PiNets, PiParams, Style


def pi_signal_names() -> dict[str, str]:
    """Derive simulator saves and waveform names from the block's net bundle."""
    names = {"time": "time"}
    for net in PiNets.signals.values():
        if net.vis == h.Visibility.PORT and net.usage not in (h.Usage.POWER, h.Usage.GROUND):
            names[f"xtop.{net.name}"] = net.name
        if net.usage == h.Usage.POWER:
            names[f"xtop.v{net.name}:p"] = f"i({net.name})"
    return names


@h.paramclass
class PiTbParams:
    """Parameters which determine the generated phase interpolator testbench."""

    waveform_sample_interval_s = h.Param(
        dtype=float, desc="Maximum raw step and stored waveform spacing", default=0.5e-12
    )
    vdd = h.Param(dtype=h.Scalar, desc="Supply voltage", default=1.2)
    pi = h.Param(dtype=PiParams, desc="Interpolator parameters", default=PiParams())
    cload = h.Param(dtype=h.Scalar, desc="Load capacitance on each output (F)", default=2e-15)
    cml_low = h.Param(dtype=h.Scalar, desc="Low level of the CML phases", default=0.8)
    vbn = h.Param(dtype=h.Scalar, desc="CML tail bias", default=0.55)
    vbp = h.Param(dtype=h.Scalar, desc="CML load bias", default=0.55)
    period_s = h.Param(dtype=h.Scalar, desc="Phase period", default=400e-12)
    spacing_deg = h.Param(dtype=h.Scalar, desc="Phase B's lag behind phase A (degrees)", default=90.0)
    transition_time_s = h.Param(dtype=h.Scalar, desc="Rise and fall time of every source", default=100e-12)
    cycles = h.Param(dtype=int, desc="Clock periods simulated", default=10)


def _validate_pi_tb_params(params: PiTbParams) -> None:
    values = (params.vdd, params.cload, params.period_s, params.transition_time_s, params.spacing_deg)
    if not all(math.isfinite(float(value)) for value in (*values, params.waveform_sample_interval_s)):
        raise ValueError("phase interpolator testbench values must be finite")
    if min(float(params.vdd), float(params.cload), params.waveform_sample_interval_s) <= 0:
        raise ValueError("phase interpolator supply, load, and sample interval must be positive")
    if float(params.transition_time_s) <= 0 or float(params.period_s) < 4 * float(params.transition_time_s):
        raise ValueError("phase interpolator period must hold four transitions, which must be positive")
    if not 0 <= float(params.spacing_deg) < 360 or params.cycles < 4:
        raise ValueError("phase interpolator spacing must lie within a period and the run hold four of them")


@h.generator
def PiTb(params: PiTbParams) -> h.Module:
    """Generate the phase interpolator testbench (Usb2Phy ``PhaseInterpTb``): phase A and phase
    B ``spacing_deg`` later, full-swing (CMOS) or at CML levels, both complements; fixed biases,
    a load on each output."""

    _validate_pi_tb_params(params)

    PiTb, connections = testbench_from_ports(
        "PiTb", {net.name: net for net in PiNets.signals.values() if net.vis == h.Visibility.PORT}
    )
    vss = PiTb.vss
    vdd = float(params.vdd)
    low = 0.0 if params.pi.style == Style.CMOS else float(params.cml_low)
    period = float(params.period_s)
    edge = {"rise": params.transition_time_s, "fall": params.transition_time_s}
    PiTb.vvdd = Vdc(dc=vdd)(p=PiTb.vdd, n=vss)
    spacing = float(params.spacing_deg) / 360 * period
    for phase, delay in (("a", period / 4), ("b", period / 4 + spacing)):
        for side, (v1, v2) in (("p", (low, vdd)), ("n", (vdd, low))):
            net = getattr(PiTb, f"{phase}{side}")
            PiTb.add(
                Vpulse(
                    v1=v1, v2=v2, period=period, width=period / 2 - float(params.transition_time_s), delay=delay, **edge
                )(p=net, n=vss),
                name=f"vphase_{phase}{side}",
            )
    PiTb.vvbn = Vdc(dc=params.vbn)(p=PiTb.vbn, n=vss)
    PiTb.vvbp = Vdc(dc=params.vbp)(p=PiTb.vbp, n=vss)
    PiTb.cloadp = C(c=params.cload)(p=PiTb.outp, n=vss)
    PiTb.cloadn = C(c=params.cload)(p=PiTb.outn, n=vss)
    PiTb.dut = Pi(params.pi)(**connections)
    return PiTb


def _run_pi_sim(run_dir: Path, params: PiTbParams, *, check: bool = False) -> Path:
    """Run one phase interpolator testbench transient in TSMC65 and return its raw file.

    ``check`` adds Spectre's static and connectivity checks and shortens the run to a tenth.
    """

    from pdk import tsmc65
    from pdk.tsmc65.hdl21 import site

    run_dir.mkdir(parents=True, exist_ok=True)
    h.pdk.set_default(tsmc65.pdk_logic)
    tb = PiTb(params)
    h.pdk.compile(tb)
    interval = params.waveform_sample_interval_s
    tstop = params.cycles * float(params.period_s)
    attrs = [
        site.install.include(h.pdk.Corner.TYP),
        site.install.include_pre_simulation(),
        hs.Options(name="temp", value=25.0),
        hs.Options(name="save", value="selected"),
        hs.Save([raw for raw in pi_signal_names() if raw != "time"]),
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


# The characterization: phase B's spacing behind A from 0 to 180 degrees at the 400 ps (2.5 GHz)
# period, and the period from 1 ns to 100 ps at quadrature spacing. The phases' edges take a
# quarter period, as an interpolator's slewed inputs do: with sharp edges the slices fight
# instead of mixing.
SPACING_SWEEP_DEG = tuple(15.0 * step for step in range(13))
PERIOD_SWEEP_S = (1e-9, 700e-12, 500e-12, 400e-12, 300e-12, 200e-12, 150e-12, 100e-12)
NOMINAL_PERIOD_S = 400e-12
NOMINAL_SPACING_DEG = 90.0


def pi_characterization(run_dir: Path, *, check: bool = False) -> Path:
    """Run every interpolator over the phase spacing and the period: 4 cases, 20 points each.

    Each point writes ``<case>/<sweep>/<point>/result.h5`` (a ``MeasPi``). ``check`` runs the
    nominal point of each case with Spectre's checks instead, writing no measurement.
    """

    from flow.analysis.types import MeasInfo, Wave
    from flow.circuit.results import read_raw_transient
    from flow.pi.analysis import MeasPi

    run_dir.mkdir(parents=True, exist_ok=True)
    points = {"spacing": [(NOMINAL_PERIOD_S, spacing) for spacing in SPACING_SWEEP_DEG]}
    points["period"] = [(period, NOMINAL_SPACING_DEG) for period in PERIOD_SWEEP_S]
    if check:
        points = {"spacing": [(NOMINAL_PERIOD_S, NOMINAL_SPACING_DEG)]}
    jobs = {
        f"{case}/{sweep}/period{round(period * 1e12)}ps_spacing{round(spacing)}deg": PiTbParams(
            pi=pi,
            period_s=period,
            spacing_deg=spacing,
            transition_time_s=period / 4,
        )
        for case, pi in CASES.items()
        for sweep, values in points.items()
        for period, spacing in values
    }
    names = pi_signal_names()
    failures: dict[str, str] = {}
    with ProcessPoolExecutor(max_workers=16, mp_context=get_context("spawn")) as executor:
        futures = {
            executor.submit(_run_pi_sim, run_dir / name, params, check=check): (name, params)
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
                measurement = MeasPi(
                    group=None,
                    index=None,
                    dut=params.pi,
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
        raise RuntimeError(f"{len(failures)} phase interpolator points failed; see {failure_path}")
    return run_dir


def main() -> None:
    """Create one output directory and run one named phase interpolator target."""

    targets = {target.__name__: target for target in (pi_characterization,)}
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("target", nargs="?", choices=sorted(targets))
    args = parser.parse_args()
    if args.target is None:
        print("Available phase interpolator simulation targets:")
        for name in sorted(targets):
            print(f"  {name}")
        return
    run_dir = (
        Path(__file__).resolve().parents[2]
        / "build"
        / "sim"
        / "pi"
        / args.target
        / datetime.now().astimezone().strftime("%Y%m%d_%H%M%S")
    )
    run_dir.mkdir(parents=True, exist_ok=False)
    targets[args.target](run_dir)


if __name__ == "__main__":
    main()
