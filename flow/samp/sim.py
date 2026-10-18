"""Sampler testbench and named Spectre simulation targets.

The bench drives complementary clocks (tracking while ``clk`` is high), an input level and a load
capacitor. With an input step the input toggles by that step once per period, in the middle of
each hold phase, so every track phase settles from a known step (its time constant and the
switch's resistance) and every hold phase shows the charge the switch dumps on opening (the
pedestal), the droop, and the input's feedthrough to the held output.

``frida1_transient`` stays the TSMC65 FRIDA-1 reference; ``samp_characterization`` compares the
named switches in every PDK.
"""

import argparse
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
from hdl21.prefix import f, p
from hdl21.primitives import C, Vdc, Vpulse
from vlsirtools.spice import ResultFormat, SimError, SimOptions, SupportedSimulators

from flow.analysis.io import interpolate_wave_records, write_measurement
from flow.circuit.ports import testbench_from_ports

from .subckt import CASES, Samp, SampNets, SampParams


def samp_signal_names() -> dict[str, str]:
    """Derive simulator saves and waveform names from the block's net bundle."""
    names = {"time": "time"}
    for net in SampNets.signals.values():
        if net.vis == h.Visibility.PORT and net.usage not in (h.Usage.POWER, h.Usage.GROUND):
            names[f"xtop.{net.name}"] = net.name
        elif net.props.get("save"):
            names[f"xtop.dut.{net.name}"] = net.name
        if net.usage == h.Usage.POWER:
            names[f"xtop.v{net.name}:p"] = f"i({net.name})"
    return names


@h.paramclass
class SampTbParams:
    """Parameters which determine the generated sampler testbench."""

    pdk = h.Param(dtype=str, desc="PDK the testbench compiles to and simulates in", default="tsmc65")
    waveform_sample_interval_s = h.Param(
        dtype=float, desc="Maximum raw step and stored waveform spacing", default=100e-12
    )
    vdd = h.Param(dtype=h.Scalar, desc="Supply voltage", default=1.2)
    samp = h.Param(dtype=SampParams, desc="Sampler parameters", default=SampParams())
    cload = h.Param(dtype=h.Prefixed, desc="Output load capacitance", default=1 * f)
    input_voltage = h.Param(dtype=h.Scalar, desc="Input level (the middle of a stepped input)", default=0.6)
    input_step_v = h.Param(
        dtype=h.Scalar, desc="Input step once per period in mid-hold; zero holds the input DC", default=0.0
    )
    clock_period_s = h.Param(dtype=h.Scalar, desc="Clock period", default=100e-9)
    clock_high_time_s = h.Param(dtype=h.Scalar, desc="Clock high (track) time", default=50e-9)
    clock_transition_time_s = h.Param(dtype=h.Scalar, desc="Clock rise and fall time", default=100e-12)
    clock_delay_s = h.Param(dtype=h.Scalar, desc="Clock delay", default=0.0)
    periods = h.Param(dtype=int, desc="Clock periods simulated", default=5)


def _validate_samp_tb_params(params: SampTbParams) -> None:
    if not 0.0 < float(params.clock_high_time_s) < float(params.clock_period_s):
        raise ValueError("sampler clock high time must lie inside one period")
    if float(params.clock_transition_time_s) <= 0.0 or float(params.clock_delay_s) < 0.0:
        raise ValueError("sampler clock transition must be positive and delay non-negative")

    values = (
        params.vdd,
        params.input_voltage,
        params.input_step_v,
        params.cload,
        params.clock_period_s,
        params.clock_high_time_s,
        params.clock_transition_time_s,
        params.clock_delay_s,
        params.waveform_sample_interval_s,
    )
    if not all(math.isfinite(float(value)) for value in values):
        raise ValueError("sampler testbench values must be finite")
    if float(params.vdd) <= 0 or float(params.cload) <= 0 or float(params.waveform_sample_interval_s) <= 0:
        raise ValueError("sampler supply, load and waveform spacing must be positive")
    if float(params.input_step_v) < 0 or params.periods <= 0:
        raise ValueError("sampler input step must be non-negative and the periods positive")


@h.generator
def SampTb(params: SampTbParams) -> h.Module:
    """Generate a complementary-clock sampler testbench."""

    _validate_samp_tb_params(params)

    SampTb, connections = testbench_from_ports(
        "SampTb", {net.name: net for net in SampNets.signals.values() if net.vis == h.Visibility.PORT}
    )

    SampTb.vvdd = Vdc(dc=params.vdd)(p=SampTb.vdd, n=SampTb.vss)
    for port in SampNets.signals.values():
        if port.usage != h.Usage.CLOCK:
            continue
        complement = port is SampNets.clk_b
        net = connections[port.name]
        SampTb.add(
            Vpulse(
                v1=params.vdd if complement else 0.0,
                v2=0.0 if complement else params.vdd,
                period=params.clock_period_s,
                width=params.clock_high_time_s,
                rise=params.clock_transition_time_s,
                fall=params.clock_transition_time_s,
                delay=params.clock_delay_s,
            )(p=net, n=SampTb.vss),
            name=f"v{net.name}",
        )
    if float(params.input_step_v) == 0.0:
        SampTb.vdin = Vdc(dc=params.input_voltage)(p=SampTb.din, n=SampTb.vss)
    else:
        # low for one period, high for the next, each change in the middle of a hold phase
        period, high = float(params.clock_period_s), float(params.clock_high_time_s)
        SampTb.vdin = Vpulse(
            v1=float(params.input_voltage) - float(params.input_step_v) / 2,
            v2=float(params.input_voltage) + float(params.input_step_v) / 2,
            period=2 * period,
            width=period,
            rise=params.clock_transition_time_s,
            fall=params.clock_transition_time_s,
            delay=float(params.clock_delay_s) + high + (period - high) / 2,
        )(p=SampTb.din, n=SampTb.vss)
    SampTb.cload = C(c=params.cload)(p=SampTb.dout, n=SampTb.vss)
    SampTb.dut = Samp(params.samp)(**connections)
    return SampTb


def _run_samp_sim(run_dir: Path, params: SampTbParams, *, check: bool = False, threads: int = 1) -> Path:
    """Run one sampler testbench transient in its PDK and return its raw file.

    ``check`` adds Spectre's static and connectivity checks and runs one period.
    """

    pdk = importlib.import_module(f"pdk.{params.pdk}")
    install = importlib.import_module(f"pdk.{params.pdk}.hdl21.site").install

    run_dir.mkdir(parents=True, exist_ok=True)
    h.pdk.set_default(pdk.pdk_logic)
    tb = SampTb(params)
    h.pdk.compile(tb)
    interval = params.waveform_sample_interval_s
    attrs = [
        install.include(h.pdk.Corner.TYP),
        # what else the PDK's simulations take, in this order: TSMC's pre-simulation settings,
        # the device names its netlists use (pdk/<name>/hdl21)
        *(getattr(install, name)() for name in ("include_pre_simulation", "include_devices") if hasattr(install, name)),
        hs.Options(name="temp", value=25.0),
        hs.Options(name="save", value="selected"),
        hs.Save([raw for raw in samp_signal_names() if raw != "time"]),
    ]
    if check:
        attrs.append(
            h.Literal(
                "check_caps static_capacitor type=distr\n"
                "check_erc static_erc floatbulk=all floatgate=no_top_moscap dangle=no_top "
                "gate2power=on gate2ground=on\n"
                "check_highz static_highz node=[*] fanout=gate_has_driver_no_moscap\n"
                "check_dcpath static_dcpath net=[xtop.vdd 0]\n"
                "check_topology static_topology node=[*] pin2gnd=on\n"
                f"check_nodecap dyn_nodecap node=[xtop.din xtop.dout] "
                f"time=[{float(params.clock_period_s) / 4:g} {3 * float(params.clock_period_s) / 4:g}]"
            )
        )
    attrs.append(
        hs.Tran(
            tstop=params.clock_period_s if check else params.periods * params.clock_period_s,
            name="tran",
            options={"strobeperiod": interval, "maxstep": interval, "strobeoutput": "strobeonly"},
        )
    )
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
                    f"+mt={threads}",
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


def frida1_transient(run_dir: Path, *, check: bool = False) -> Path:
    """Run five periods of the fabricated-size sampler transient (TSMC65)."""

    _run_samp_sim(run_dir, SampTbParams(), check=check, threads=4)
    return run_dir


# The characterization, in every PDK at its own core supply: every switch into 1 pF (about the
# CDAC it samples onto) at a 10 ns clock (5 ns tracking), its input stepping by a twelfth of the
# supply each period; over input levels from 1/12 to 11/12 of the supply, and over the supply (75
# to 108 % of it) at mid-supply input.
VIN_SWEEP = tuple(step / 12 for step in range(1, 12))
SUPPLY_SWEEP = (9 / 12, 10 / 12, 11 / 12, 1.0, 13 / 12)
NOMINAL_VIN = 0.5


def samp_characterization(run_dir: Path, *, check: bool = False) -> Path:
    """Run every switch over its input level and over the supply, in every PDK.

    Each point writes ``<pdk>/<case>/<sweep>/<point>/result.h5`` (a ``MeasSamp``). ``check`` runs
    each case's nominal point for one period with Spectre's checks instead, writing no measurement.
    """

    from flow.analysis.types import MeasInfo, Wave
    from flow.circuit.results import read_raw_transient
    from flow.comp.layout import PDKS
    from flow.samp.analysis import MeasSamp

    run_dir.mkdir(parents=True, exist_ok=True)
    jobs = {}
    for pdk in PDKS:
        supply = importlib.import_module(f"pdk.{pdk}.hdl21.site").install.supply_voltage(h.pdk.Corner.TYP)
        points = {"vin": [(supply, step * supply) for step in VIN_SWEEP]}
        points["supply"] = [(step * supply, NOMINAL_VIN * step * supply) for step in SUPPLY_SWEEP]
        if check:
            points = {"check": [(supply, NOMINAL_VIN * supply)]}
        for case, samp in CASES.items():
            for sweep, values in points.items():
                for vdd, vin in values:
                    jobs[f"{pdk}/{case}/{sweep}/vdd{round(vdd * 1e3)}_vin{round(vin * 1e3)}"] = SampTbParams(
                        pdk=pdk,
                        samp=samp,
                        vdd=round(vdd, 4),
                        input_voltage=round(vin, 4),
                        input_step_v=round(vdd / 12, 4),
                        cload=1 * p,
                        clock_period_s=10e-9,
                        clock_high_time_s=5e-9,
                        clock_transition_time_s=50e-12,
                        waveform_sample_interval_s=5e-12,
                        periods=6,
                    )
    names = samp_signal_names()
    failures: dict[str, str] = {}
    # one pool per PDK: hdl21 compiles each generated module in place, for the first PDK it meets
    for pdk in PDKS:
        with ProcessPoolExecutor(max_workers=16, mp_context=get_context("spawn")) as executor:
            futures = {
                executor.submit(_run_samp_sim, run_dir / name, params, check=check): (name, params)
                for name, params in jobs.items()
                if params.pdk == pdk
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
                    measurement = MeasSamp(
                        group=None,
                        index=None,
                        dut=params.samp,
                        info=MeasInfo(
                            backend="spice",
                            timestamp_utc=datetime.fromtimestamp(raw_path.stat().st_mtime, tz=UTC),
                            instruments={"simulator": "Spectre"},
                            readbacks={
                                "pdk": name.split("/")[0],
                                "case": name.split("/")[1],
                                "sweep": name.split("/")[2],
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
        raise RuntimeError(f"{len(failures)} sampler points failed; see {failure_path}")
    return run_dir


def main() -> None:
    """Create one output directory and run one named sampler target."""

    targets = {target.__name__: target for target in (frida1_transient, samp_characterization)}
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("target", nargs="?", choices=sorted(targets))
    args = parser.parse_args()
    if args.target is None:
        print("Available sampler simulation targets:")
        for name in sorted(targets):
            print(f"  {name}")
        return
    run_dir = (
        Path(__file__).resolve().parents[2]
        / "build"
        / "sim"
        / "samp"
        / args.target
        / datetime.now().astimezone().strftime("%Y%m%d_%H%M%S")
    )
    run_dir.mkdir(parents=True, exist_ok=False)
    targets[args.target](run_dir)


if __name__ == "__main__":
    main()
