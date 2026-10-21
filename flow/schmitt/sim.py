"""Schmitt trigger testbench and named Spectre simulation targets, in every PDK.

The input either ramps slowly from ground to the supply and back (a triangle: the trip points
on the way up and down, their difference the hysteresis) or steps rail to rail and back with fast edges (each edge's delay, the output's
transitions and the energy per cycle); the output drives the next gate's input.
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
from hdl21.primitives import C, Vdc, Vpulse
from vlsirtools.spice import ResultFormat, SimError, SimOptions, SupportedSimulators

from flow.analysis.io import write_measurement
from flow.circuit.ports import testbench_from_ports

from .subckt import CASES, Schmitt, SchmittNets, SchmittParams


def schmitt_signal_names() -> dict[str, str]:
    """Derive simulator saves and waveform names from the block's net bundle."""
    names = {"time": "time"}
    for net in SchmittNets.signals.values():
        if net.vis == h.Visibility.PORT and net.usage not in (h.Usage.POWER, h.Usage.GROUND):
            names[f"xtop.{net.name}"] = net.name
        if net.usage == h.Usage.POWER:
            names[f"xtop.v{net.name}:p"] = f"i({net.name})"
    return names


@h.paramclass
class SchmittTbParams:
    """Parameters which determine the generated Schmitt trigger testbench."""

    pdk = h.Param(dtype=str, desc="PDK the testbench compiles to and simulates in", default="tsmc65")
    vdd = h.Param(dtype=h.Scalar, desc="Supply voltage", default=1.2)
    schmitt = h.Param(dtype=SchmittParams, desc="Trigger parameters", default=SchmittParams())
    cload = h.Param(dtype=h.Scalar, desc="Load capacitance on the output (F)", default=5e-15)
    step = h.Param(dtype=bool, desc="The step bench (delays); else the triangle (trip points)", default=False)
    ramp_time_s = h.Param(dtype=h.Scalar, desc="Triangle's rise and fall time", default=1e-6)
    period_s = h.Param(dtype=h.Scalar, desc="Step period: up a quarter in, down three quarters in", default=4e-9)
    transition_time_s = h.Param(dtype=h.Scalar, desc="Step rise and fall time", default=50e-12)
    waveform_sample_interval_s = h.Param(dtype=float, desc="Uniform waveform record interval", default=0.5e-9)


def _ramp_settle_s(params: SchmittTbParams) -> float:
    """The triangle's rest before, between and after its two ramps."""
    return float(params.ramp_time_s) / 40


def stop_time_s(params: SchmittTbParams) -> float:
    """The transient's length: one step period, or rest, ramp up, rest, ramp down, rest."""
    if params.step:
        return float(params.period_s)
    return 2 * float(params.ramp_time_s) + 3 * _ramp_settle_s(params)


def _validate_schmitt_tb_params(params: SchmittTbParams) -> None:
    values = (params.vdd, params.cload, params.ramp_time_s, params.period_s, params.transition_time_s)
    if not all(math.isfinite(float(value)) for value in (*values, params.waveform_sample_interval_s)):
        raise ValueError("Schmitt trigger testbench values must be finite")
    if min(float(params.vdd), float(params.ramp_time_s), params.waveform_sample_interval_s) <= 0:
        raise ValueError("Schmitt trigger supply, ramp and record interval must be positive")
    if float(params.cload) < 0 or not 0 < 4 * float(params.transition_time_s) < float(params.period_s):
        raise ValueError("Schmitt trigger load must not be negative and the step needs short edges in its period")


@h.generator
def SchmittTb(params: SchmittTbParams) -> h.Module:
    """Generate the Schmitt trigger testbench: the input a slow triangle from ground to the supply
    and back, or with ``step`` a rail-to-rail step a quarter period in and back three quarters in;
    the load on the output."""

    _validate_schmitt_tb_params(params)

    SchmittTb, connections = testbench_from_ports(
        "SchmittTb", {net.name: net for net in SchmittNets.signals.values() if net.vis == h.Visibility.PORT}
    )
    vdd, vss = float(params.vdd), SchmittTb.vss
    SchmittTb.vvdd = Vdc(dc=params.vdd)(p=SchmittTb.vdd, n=vss)
    if params.step:
        edge, period = float(params.transition_time_s), float(params.period_s)
        source = Vpulse(v1=0.0, v2=vdd, delay=period / 4, width=period / 2 - edge, period=period, rise=edge, fall=edge)
    else:
        settle, ramp = _ramp_settle_s(params), float(params.ramp_time_s)
        source = Vpulse(
            v1=0.0, v2=vdd, delay=settle, rise=ramp, width=settle, fall=ramp, period=2 * stop_time_s(params)
        )
    SchmittTb.vinp = source(p=SchmittTb.inp, n=vss)
    if float(params.cload):
        SchmittTb.cload = C(c=params.cload)(p=SchmittTb.out, n=vss)
    SchmittTb.dut = Schmitt(params.schmitt)(**connections)
    return SchmittTb


def _run_schmitt_sim(run_dir: Path, params: SchmittTbParams, *, check: bool = False) -> Path:
    """Run one Schmitt trigger transient in its PDK and return its raw file (``check``: Spectre's
    static checks besides)."""

    pdk = importlib.import_module(f"pdk.{params.pdk}")
    install = importlib.import_module(f"pdk.{params.pdk}.hdl21.site").install

    run_dir.mkdir(parents=True, exist_ok=True)
    h.pdk.set_default(pdk.pdk_logic)
    tb = SchmittTb(params)
    h.pdk.compile(tb)
    interval = params.waveform_sample_interval_s
    attrs = [
        install.include(h.pdk.Corner.TYP),
        # what else the PDK's simulations take, in this order: TSMC's pre-simulation settings,
        # the device names its netlists use (pdk/<name>/hdl21)
        *(getattr(install, name)() for name in ("include_pre_simulation", "include_devices") if hasattr(install, name)),
        hs.Options(name="temp", value=25.0),
        hs.Options(name="save", value="selected"),
        hs.Save([raw for raw in schmitt_signal_names() if raw != "time"]),
        hs.Tran(
            tstop=stop_time_s(params),
            name="tran",
            options={"strobeperiod": interval, "maxstep": interval, "strobeoutput": "strobeonly"},
        ),
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


# The characterization, in every PDK about its own core supply: each trigger's triangle (1 µs a
# ramp) at 75 to 108 % of the supply, and its step (4 ns period, 50 ps edges, 1 ps record) at the
# core supply; the output drives 5 fF.
SUPPLY_SWEEP = (9 / 12, 10 / 12, 11 / 12, 1.0, 13 / 12)


def schmitt_characterization(run_dir: Path, *, check: bool = False) -> Path:
    """Run every trigger's triangle over the supply and its step in every PDK: 18 runs each.

    Each run writes ``<pdk>/<case>/<supply|step>/vdd<mV>/result.h5`` (a ``MeasSchmitt``).
    ``check`` runs each case's step with Spectre's checks instead, writing no measurement.
    """

    from flow.analysis.types import MeasInfo
    from flow.circuit.results import read_transient_wave
    from flow.comp.layout import PDKS
    from flow.schmitt.analysis import MeasSchmitt

    run_dir.mkdir(parents=True, exist_ok=True)
    jobs = {}
    for pdk in PDKS:
        supply = importlib.import_module(f"pdk.{pdk}.hdl21.site").install.supply_voltage(h.pdk.Corner.TYP)
        for case, schmitt in CASES.items():
            jobs[f"{pdk}/{case}/step/vdd{round(supply * 1e3)}"] = SchmittTbParams(
                pdk=pdk, schmitt=schmitt, vdd=supply, step=True, waveform_sample_interval_s=1e-12
            )
            for vdd in () if check else [round(step * supply, 4) for step in SUPPLY_SWEEP]:
                jobs[f"{pdk}/{case}/supply/vdd{round(vdd * 1e3)}"] = SchmittTbParams(pdk=pdk, schmitt=schmitt, vdd=vdd)
    names = schmitt_signal_names()
    failures: dict[str, str] = {}
    # one pool per PDK: hdl21 compiles each generated module in place, for the first PDK it meets
    for pdk in PDKS:
        with ProcessPoolExecutor(max_workers=16, mp_context=get_context("spawn")) as executor:
            futures = {
                executor.submit(_run_schmitt_sim, run_dir / name, params, check=check): (name, params)
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
                    wave, raw_points = read_transient_wave(
                        raw_path, names, params.waveform_sample_interval_s, supply_rails=("vdd",)
                    )
                    measurement = MeasSchmitt(
                        group=None,
                        index=None,
                        dut=params.schmitt,
                        info=MeasInfo(
                            backend="spice",
                            timestamp_utc=datetime.fromtimestamp(raw_path.stat().st_mtime, tz=UTC),
                            instruments={"simulator": "Spectre"},
                            readbacks={
                                "pdk": name.split("/")[0],
                                "case": name.split("/")[1],
                                "sweep": name.split("/")[2],
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
        raise RuntimeError(f"{len(failures)} Schmitt trigger points failed; see {failure_path}")
    return run_dir
