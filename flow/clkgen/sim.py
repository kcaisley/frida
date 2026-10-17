"""Clock conditioning testbench and named Spectre simulation targets, in every PDK.

The testbench follows Usb2Phy's ``PulseGenTb`` and BAG's clock benches: complementary clocks,
an enable that rises a quarter period into the third period (while clk is low), and a load on
each output. Every case gets the same stimulus; only the clock gate uses the enable. The
characterization sweeps the supply and the clock period.
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
from hdl21.primitives import C, Vdc, Vpulse
from vlsirtools.spice import ResultFormat, SimError, SimOptions, SupportedSimulators

from flow.analysis.io import interpolate_wave_records, write_measurement
from flow.circuit.ports import testbench_from_ports

from .subckt import CASES, Clkgen, ClkgenNets, ClkgenParams


def clkgen_signal_names() -> dict[str, str]:
    """Derive simulator saves and waveform names from the block's net bundle."""
    names = {"time": "time"}
    for net in ClkgenNets.signals.values():
        if net.vis == h.Visibility.PORT and net.usage not in (h.Usage.POWER, h.Usage.GROUND):
            names[f"xtop.{net.name}"] = net.name
        if net.usage == h.Usage.POWER:
            names[f"xtop.v{net.name}:p"] = f"i({net.name})"
    return names


@h.paramclass
class ClkgenTbParams:
    """Parameters which determine the generated clock generator testbench."""

    pdk = h.Param(dtype=str, desc="PDK the testbench compiles to and simulates in", default="tsmc65")
    waveform_sample_interval_s = h.Param(
        dtype=float, desc="Maximum raw step and stored waveform spacing", default=1e-12
    )
    vdd = h.Param(dtype=h.Scalar, desc="Supply voltage", default=1.2)
    clkgen = h.Param(dtype=ClkgenParams, desc="Clock generator parameters", default=ClkgenParams())
    cload = h.Param(dtype=h.Scalar, desc="Load capacitance on each output (F)", default=2e-15)
    period_s = h.Param(dtype=h.Scalar, desc="Clock period", default=1e-9)
    transition_time_s = h.Param(dtype=h.Scalar, desc="Rise and fall time of every source", default=30e-12)
    cycles = h.Param(dtype=int, desc="Clock periods simulated", default=10)


def _validate_clkgen_tb_params(params: ClkgenTbParams) -> None:
    values = (params.vdd, params.cload, params.period_s, params.transition_time_s)
    if not all(math.isfinite(float(value)) for value in (*values, params.waveform_sample_interval_s)):
        raise ValueError("clock generator testbench values must be finite")
    if min(float(params.vdd), float(params.cload), params.waveform_sample_interval_s) <= 0:
        raise ValueError("clock generator supply, load, and sample interval must be positive")
    if float(params.transition_time_s) <= 0 or float(params.period_s) <= 2 * float(params.transition_time_s):
        raise ValueError("clock generator period must exceed both transitions, which must be positive")
    if params.cycles < 5:
        raise ValueError("clock generator run must hold two periods after the enable")


@h.generator
def ClkgenTb(params: ClkgenTbParams) -> h.Module:
    """Generate the clock generator testbench (Usb2Phy ``PulseGenTb``): complementary clocks, en
    low for the first two periods then high, a load on each output."""

    _validate_clkgen_tb_params(params)

    ClkgenTb, connections = testbench_from_ports(
        "ClkgenTb", {net.name: net for net in ClkgenNets.signals.values() if net.vis == h.Visibility.PORT}
    )
    vss = ClkgenTb.vss
    vdd, period = float(params.vdd), float(params.period_s)
    edge = {"rise": params.transition_time_s, "fall": params.transition_time_s}
    ClkgenTb.vvdd = Vdc(dc=vdd)(p=ClkgenTb.vdd, n=vss)
    ClkgenTb.vclk = Vpulse(v1=0.0, v2=vdd, period=period, width=period / 2, delay=period / 2, **edge)(
        p=ClkgenTb.clk, n=vss
    )
    ClkgenTb.vclkb = Vpulse(v1=vdd, v2=0.0, period=period, width=period / 2, delay=period / 2, **edge)(
        p=ClkgenTb.clkb, n=vss
    )
    # en rises a quarter period into the third clock period, while clk is low
    ClkgenTb.ven = Vpulse(v1=0.0, v2=vdd, period=1.0, width=0.5, delay=2.25 * period, **edge)(p=ClkgenTb.en, n=vss)
    ClkgenTb.cloadp = C(c=params.cload)(p=ClkgenTb.outp, n=vss)
    ClkgenTb.cloadn = C(c=params.cload)(p=ClkgenTb.outn, n=vss)
    ClkgenTb.dut = Clkgen(params.clkgen)(**connections)
    return ClkgenTb


def _run_clkgen_sim(run_dir: Path, params: ClkgenTbParams, *, check: bool = False) -> Path:
    """Run one clock generator testbench transient in its PDK and return its raw file.

    ``check`` adds Spectre's static and connectivity checks and shortens the run to a tenth.
    """

    pdk = importlib.import_module(f"pdk.{params.pdk}")
    install = importlib.import_module(f"pdk.{params.pdk}.hdl21.site").install

    run_dir.mkdir(parents=True, exist_ok=True)
    h.pdk.set_default(pdk.pdk_logic)
    tb = ClkgenTb(params)
    h.pdk.compile(tb)
    interval = params.waveform_sample_interval_s
    tstop = params.cycles * float(params.period_s)
    attrs = [
        install.include(h.pdk.Corner.TYP),
        # what else the PDK's simulations take, in this order: TSMC's pre-simulation settings,
        # the standard cells, the device names its netlists use (pdk/<name>/hdl21)
        *(
            getattr(install, name)()
            for name in ("include_pre_simulation", "include_stdcell", "include_devices")
            if hasattr(install, name)
        ),
        hs.Options(name="temp", value=25.0),
        hs.Options(name="save", value="selected"),
        hs.Save([raw for raw in clkgen_signal_names() if raw != "time"]),
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


# The characterization, in every PDK about its own core supply: the supply (two thirds of it to
# 108 %; 0.8 to 1.3 V in TSMC65) at the 1 ns clock, and the clock period from 2 ns to 100 ps at the
# core supply.
SUPPLY_SWEEP = (8 / 12, 9 / 12, 10 / 12, 11 / 12, 1.0, 13 / 12)
PERIOD_SWEEP_S = (2e-9, 1e-9, 700e-12, 500e-12, 300e-12, 200e-12, 150e-12, 100e-12)
NOMINAL_PERIOD_S = 1e-9


def clkgen_characterization(run_dir: Path, *, check: bool = False) -> Path:
    """Run every clock function over the supply and the period in every PDK: 3 cases, 14 points each.

    Each point writes ``<pdk>/<case>/<sweep>/<point>/result.h5`` (a ``MeasClkgen``). ``check``
    runs the nominal point of each case with Spectre's checks instead, writing no measurement.
    """

    from flow.analysis.types import MeasInfo, Wave
    from flow.circuit.results import read_raw_transient
    from flow.clkgen.analysis import MeasClkgen
    from flow.comp.layout import PDKS

    run_dir.mkdir(parents=True, exist_ok=True)
    jobs = {}
    for pdk in PDKS:
        supply = importlib.import_module(f"pdk.{pdk}.hdl21.site").install.supply_voltage(h.pdk.Corner.TYP)
        points = {"supply": [(step * supply, NOMINAL_PERIOD_S) for step in SUPPLY_SWEEP]}
        points["period"] = [(supply, period) for period in PERIOD_SWEEP_S]
        if check:
            points = {"supply": [(supply, NOMINAL_PERIOD_S)]}
        for case, clkgen in CASES.items():
            for sweep, values in points.items():
                for vdd, period in values:
                    jobs[f"{pdk}/{case}/{sweep}/vdd{round(vdd * 1e3)}_period{round(period * 1e12)}ps"] = (
                        ClkgenTbParams(
                            pdk=pdk,
                            clkgen=clkgen,
                            vdd=round(vdd, 4),
                            period_s=period,
                            transition_time_s=min(30e-12, period / 8),
                        ),
                        abs(vdd - supply) < 1e-6 and period == NOMINAL_PERIOD_S,
                    )
    names = clkgen_signal_names()
    failures: dict[str, str] = {}
    # one pool per PDK: hdl21 compiles each generated module in place, for the first PDK it meets
    for pdk in PDKS:
        with ProcessPoolExecutor(max_workers=16, mp_context=get_context("spawn")) as executor:
            futures = {
                executor.submit(_run_clkgen_sim, run_dir / name, params, check=check): (name, params, nominal)
                for name, (params, nominal) in jobs.items()
                if params.pdk == pdk
            }
            for future in as_completed(futures):
                name, params, nominal = futures[future]
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
                    measurement = MeasClkgen(
                        group=None,
                        index=None,
                        dut=params.clkgen,
                        info=MeasInfo(
                            backend="spice",
                            timestamp_utc=datetime.fromtimestamp(raw_path.stat().st_mtime, tz=UTC),
                            instruments={"simulator": "Spectre"},
                            readbacks={
                                "pdk": name.split("/")[0],
                                "case": name.split("/")[1],
                                "sweep": name.split("/")[2],
                                "nominal": nominal,
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
        raise RuntimeError(f"{len(failures)} clock generator points failed; see {failure_path}")
    return run_dir


def main() -> None:
    """Create one output directory and run one named clock generator target."""

    targets = {target.__name__: target for target in (clkgen_characterization,)}
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("target", nargs="?", choices=sorted(targets))
    args = parser.parse_args()
    if args.target is None:
        print("Available clock generator simulation targets:")
        for name in sorted(targets):
            print(f"  {name}")
        return
    run_dir = (
        Path(__file__).resolve().parents[2]
        / "build"
        / "sim"
        / "clkgen"
        / args.target
        / datetime.now().astimezone().strftime("%Y%m%d_%H%M%S")
    )
    run_dir.mkdir(parents=True, exist_ok=False)
    targets[args.target](run_dir)


if __name__ == "__main__":
    main()
