"""Capacitor driver testbench and named Spectre simulation targets, in every PDK.

Each stage drives a load capacitor, the CDAC stage's bottom plate it stands for. Over two periods
the state steps up and back down with the invert input low (the state path), then the invert input
does the same with the state low (the invert path), so every edge of both XOR paths is seen once.
The characterization sweeps the load and the supply; the period grows with the load so that even
the weakest band settles within half of it.
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

from flow.analysis.io import write_measurement
from flow.circuit.ports import testbench_from_ports

from .subckt import CASES, CapDriver, CapDriverParams, driver_ports


def capdriver_signal_names() -> dict[str, str]:
    """Derive simulator saves and waveform names from a single stage's ports."""
    names = {"time": "time"}
    for name, net in driver_ports(1).items():
        if net.usage not in (h.Usage.POWER, h.Usage.GROUND):
            names[f"xtop.{name}"] = name
        if net.usage == h.Usage.POWER:
            names[f"xtop.v{name}:p"] = f"i({name})"
    return names


@h.paramclass
class CapdriverTbParams:
    """Parameters which determine the generated capacitor driver testbench."""

    pdk = h.Param(dtype=str, desc="PDK the testbench compiles to and simulates in", default="tsmc65")
    vdd = h.Param(dtype=h.Scalar, desc="Supply voltage", default=1.2)
    driver = h.Param(dtype=CapDriverParams, desc="Driver parameters", default=CASES["x1"])
    cload = h.Param(dtype=h.Scalar, desc="Load capacitance on each stage's output (F)", default=100e-15)
    period_s = h.Param(dtype=h.Scalar, desc="Each path's period: up a quarter in, down three quarters in", default=2e-9)
    transition_time_s = h.Param(dtype=h.Scalar, desc="Rise and fall time of the input steps", default=30e-12)
    waveform_sample_interval_s = h.Param(
        dtype=float, desc="Maximum raw step and stored waveform spacing", default=1e-12
    )


def _validate_capdriver_tb_params(params: CapdriverTbParams) -> None:
    values = (params.vdd, params.cload, params.period_s, params.transition_time_s)
    if not all(math.isfinite(float(value)) for value in (*values, params.waveform_sample_interval_s)):
        raise ValueError("capacitor driver testbench values must be finite")
    if min(float(params.vdd), float(params.cload), params.waveform_sample_interval_s) <= 0:
        raise ValueError("capacitor driver supply, load, and sample interval must be positive")
    if float(params.transition_time_s) <= 0 or float(params.period_s) <= 4 * float(params.transition_time_s):
        raise ValueError("capacitor driver period must hold both input steps, which must be positive")


@h.generator
def CapdriverTb(params: CapdriverTbParams) -> h.Module:
    """Generate the capacitor driver testbench: the state, then the invert input, stepping up and
    back down once each; a load capacitor on every stage."""

    _validate_capdriver_tb_params(params)

    stages = params.driver.n_stages
    CapdriverTb, connections = testbench_from_ports("CapdriverTb", driver_ports(stages))
    vss = CapdriverTb.vss
    vdd, period = float(params.vdd), float(params.period_s)
    edge = params.transition_time_s
    pulse = {"v1": 0.0, "v2": vdd, "period": 2 * period, "width": period / 2 - float(edge), "rise": edge, "fall": edge}
    CapdriverTb.vvdd = Vdc(dc=vdd)(p=CapdriverTb.vdd, n=vss)
    # the state path in the first period, the invert path in the second
    CapdriverTb.vinvert = Vpulse(delay=5 * period / 4, **pulse)(p=CapdriverTb.dac_drive_invert, n=vss)
    for stage in range(stages):
        state = Vpulse(delay=period / 4, **pulse)(p=CapdriverTb.dac_state[stage], n=vss)
        CapdriverTb.add(state, name=f"vstate_{stage}")
        CapdriverTb.add(C(c=params.cload)(p=CapdriverTb.dac_drive[stage], n=vss), name=f"cload_{stage}")
    CapdriverTb.dut = CapDriver(params.driver)(**connections)
    return CapdriverTb


def _run_capdriver_sim(run_dir: Path, params: CapdriverTbParams, *, check: bool = False) -> Path:
    """Run one capacitor driver testbench transient over both periods in its PDK and return its raw file.

    ``check`` adds Spectre's static and connectivity checks.
    """

    pdk = importlib.import_module(f"pdk.{params.pdk}")
    install = importlib.import_module(f"pdk.{params.pdk}.hdl21.site").install

    run_dir.mkdir(parents=True, exist_ok=True)
    h.pdk.set_default(pdk.pdk_logic)
    tb = CapdriverTb(params)
    h.pdk.compile(tb)
    interval = params.waveform_sample_interval_s
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
        hs.Save([raw for raw in capdriver_signal_names() if raw != "time"]),
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
            tstop=2 * float(params.period_s),
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


# The characterization, in every PDK about its own core supply: the load from 10 fF to 1 pF (a
# CDAC stage's bottom plate, from the LSBs to the MSB) at the core supply, and the supply (75 to
# 108 %) at 100 fF. Each period lasts 200 ps per fF of load (at least 2 ns), so even the weakest
# band-1 XORs (up to about 20 kΩ, behind a nanosecond of delay) settle to 1 % within half of it; the
# record holds 2000 samples a period, no closer than 1 ps (1 ps up to a 2 ns period, 100 ps at 1 pF).
LOAD_SWEEP_F = (10e-15, 30e-15, 100e-15, 300e-15, 1e-12)
SUPPLY_SWEEP = (9 / 12, 10 / 12, 11 / 12, 1.0, 13 / 12)
NOMINAL_LOAD_F = 100e-15


def _period_s(cload: float) -> float:
    return max(2e-9, 2e5 * cload)


def capdriver_characterization(run_dir: Path, *, check: bool = False) -> Path:
    """Run every drive band over the load and the supply in every PDK: 3 cases, 10 points each.

    Each point writes ``<pdk>/<case>/<sweep>/<point>/result.h5`` (a ``MeasCapdriver``). ``check``
    runs the nominal point of each case with Spectre's checks instead, writing no measurement.
    """

    from flow.analysis.types import MeasInfo
    from flow.capdriver.analysis import MeasCapdriver
    from flow.circuit.results import read_transient_wave
    from flow.comp.layout import PDKS

    run_dir.mkdir(parents=True, exist_ok=True)
    jobs = {}
    for pdk in PDKS:
        supply = importlib.import_module(f"pdk.{pdk}.hdl21.site").install.supply_voltage(h.pdk.Corner.TYP)
        points = {"load": [(supply, load) for load in LOAD_SWEEP_F]}
        points["supply"] = [(step * supply, NOMINAL_LOAD_F) for step in SUPPLY_SWEEP]
        if check:
            points = {"load": [(supply, NOMINAL_LOAD_F)]}
        for case, driver in CASES.items():
            for sweep, values in points.items():
                for vdd, load in values:
                    period = _period_s(load)
                    jobs[f"{pdk}/{case}/{sweep}/vdd{round(vdd * 1e3)}_load{round(load * 1e15)}ff"] = (
                        CapdriverTbParams(
                            pdk=pdk,
                            driver=driver,
                            vdd=round(vdd, 4),
                            cload=load,
                            period_s=period,
                            waveform_sample_interval_s=max(1e-12, period / 2000),
                        ),
                        abs(vdd - supply) < 1e-6 and load == NOMINAL_LOAD_F,
                    )
    names = capdriver_signal_names()
    failures: dict[str, str] = {}
    # one pool per PDK: hdl21 compiles each generated module in place, for the first PDK it meets
    for pdk in PDKS:
        with ProcessPoolExecutor(max_workers=16, mp_context=get_context("spawn")) as executor:
            futures = {
                executor.submit(_run_capdriver_sim, run_dir / name, params, check=check): (name, params, nominal)
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
                    wave, raw_points = read_transient_wave(
                        raw_path, names, params.waveform_sample_interval_s, supply_rails=("vdd",)
                    )
                    measurement = MeasCapdriver(
                        group=None,
                        index=None,
                        dut=params.driver,
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
                                "raw_points": raw_points,
                                "waveform_sample_interval_s": params.waveform_sample_interval_s,
                                "supply_current_convention": "positive_current_draw",
                            },
                        ),
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
        raise RuntimeError(f"{len(failures)} capacitor driver points failed; see {failure_path}")
    return run_dir


def main() -> None:
    """Create one output directory and run one named capacitor driver target."""

    targets = {target.__name__: target for target in (capdriver_characterization,)}
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("target", nargs="?", choices=sorted(targets))
    args = parser.parse_args()
    if args.target is None:
        print("Available capacitor driver simulation targets:")
        for name in sorted(targets):
            print(f"  {name}")
        return
    run_dir = (
        Path(__file__).resolve().parents[2]
        / "build"
        / "sim"
        / "capdriver"
        / args.target
        / datetime.now().astimezone().strftime("%Y%m%d_%H%M%S")
    )
    run_dir.mkdir(parents=True, exist_ok=False)
    targets[args.target](run_dir)


if __name__ == "__main__":
    main()
