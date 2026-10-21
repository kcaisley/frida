"""Level shifter testbench and named Spectre simulation targets, in every PDK.

The testbench: input pulses at the low supply's
levels (and their complement, unless the shifter makes it), a reset for the first quarter
period, a load on every output, and both supplies' currents. Every case gets the same stimulus.
The characterization sweeps the input supply (the shifter's figure: how low it still switches)
and the output supply.
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

from flow.analysis.io import interpolate_wave_records, write_measurement
from flow.circuit.ports import testbench_from_ports

from .subckt import CASES, LvShift, LvShiftNets, LvShiftParams


def lvshift_signal_names() -> dict[str, str]:
    """Derive simulator saves and waveform names from the block's net bundle, and the current
    of the source on the low supply."""
    names = {"time": "time"}
    for net in LvShiftNets.signals.values():
        if net.vis == h.Visibility.PORT and net.usage not in (h.Usage.POWER, h.Usage.GROUND):
            names[f"xtop.{net.name}"] = net.name
        if net.usage == h.Usage.POWER:
            names[f"xtop.v{net.name}:p"] = f"i({net.name})"
    names["xtop.vvddl:p"] = f"i({LvShiftNets.vddl.name})"
    return names


@h.paramclass
class LvShiftTbParams:
    """Parameters which determine the generated level shifter testbench."""

    pdk = h.Param(dtype=str, desc="PDK the testbench compiles to and simulates in", default="tsmc65")
    waveform_sample_interval_s = h.Param(
        dtype=float, desc="Maximum raw step and stored waveform spacing", default=2e-12
    )
    vdd = h.Param(dtype=h.Scalar, desc="Supply voltage (the outputs')", default=1.2)
    vddl = h.Param(dtype=h.Scalar, desc="The inputs' supply", default=0.6)
    lvshift = h.Param(dtype=LvShiftParams, desc="Level shifter parameters", default=LvShiftParams())
    cload = h.Param(dtype=h.Scalar, desc="Load capacitance on each output (F)", default=2e-15)
    period_s = h.Param(dtype=h.Scalar, desc="Input period", default=4e-9)
    transition_time_s = h.Param(dtype=h.Scalar, desc="Rise and fall time of every source", default=50e-12)
    cycles = h.Param(dtype=int, desc="Input periods simulated", default=3)


def _validate_lvshift_tb_params(params: LvShiftTbParams) -> None:
    values = (params.vdd, params.cload, params.period_s, params.transition_time_s)
    if not all(math.isfinite(float(value)) for value in (*values, params.waveform_sample_interval_s)):
        raise ValueError("level shifter testbench values must be finite")
    if min(float(params.vdd), float(params.cload), params.waveform_sample_interval_s) <= 0:
        raise ValueError("level shifter supply, load, and sample interval must be positive")
    if float(params.transition_time_s) <= 0 or float(params.period_s) <= 2 * float(params.transition_time_s):
        raise ValueError("level shifter period must exceed both transitions, which must be positive")
    if not 0 < float(params.vddl) <= float(params.vdd):
        raise ValueError("level shifter input supply must lie between 0 and vdd")
    if params.cycles < 2:
        raise ValueError("level shifter run must hold two input periods")


@h.generator
def LvShiftTb(params: LvShiftTbParams) -> h.Module:
    """Generate the level shifter testbench: complementary
    input pulses at vddl levels, rst high for the first quarter period, a load on each output and
    buffered output."""

    _validate_lvshift_tb_params(params)

    LvShiftTb, connections = testbench_from_ports(
        "LvShiftTb", {net.name: net for net in LvShiftNets.signals.values() if net.vis == h.Visibility.PORT}
    )
    vss = LvShiftTb.vss
    vdd, vddl, period = float(params.vdd), float(params.vddl), float(params.period_s)
    edge = {"rise": params.transition_time_s, "fall": params.transition_time_s}
    LvShiftTb.vvdd = Vdc(dc=vdd)(p=LvShiftTb.vdd, n=vss)
    LvShiftTb.vvddl = Vdc(dc=vddl)(p=LvShiftTb.vddl, n=vss)
    LvShiftTb.vinp = Vpulse(v1=0.0, v2=vddl, period=period, width=period / 2, delay=period / 2, **edge)(
        p=LvShiftTb.inp, n=vss
    )
    if not params.lvshift.input_inverter:  # the shifter makes inn itself otherwise
        LvShiftTb.vinn = Vpulse(v1=vddl, v2=0.0, period=period, width=period / 2, delay=period / 2, **edge)(
            p=LvShiftTb.inn, n=vss
        )
    LvShiftTb.vrst = Vpulse(v1=vdd, v2=0.0, period=1.0, width=0.5, delay=period / 4, **edge)(p=LvShiftTb.rst, n=vss)
    for name in ("outp", "outn", "bufp", "bufn"):
        LvShiftTb.add(C(c=params.cload)(p=getattr(LvShiftTb, name), n=vss), name=f"c{name}")
    LvShiftTb.dut = LvShift(params.lvshift)(**connections)
    return LvShiftTb


def _run_lvshift_sim(run_dir: Path, params: LvShiftTbParams, *, check: bool = False) -> Path:
    """Run one level shifter testbench transient in its PDK and return its raw file.

    ``check`` adds Spectre's static and connectivity checks and shortens the run to a tenth.
    """

    pdk = importlib.import_module(f"pdk.{params.pdk}")
    install = importlib.import_module(f"pdk.{params.pdk}.hdl21.site").install

    run_dir.mkdir(parents=True, exist_ok=True)
    h.pdk.set_default(pdk.pdk_logic)
    tb = LvShiftTb(params)
    h.pdk.compile(tb)
    interval = params.waveform_sample_interval_s
    tstop = params.cycles * float(params.period_s)
    attrs = [
        install.include(h.pdk.Corner.TYP),
        # what else the PDK's simulations take, in this order: TSMC's pre-simulation settings,
        # the device names its netlists use (pdk/<name>/hdl21)
        *(getattr(install, name)() for name in ("include_pre_simulation", "include_devices") if hasattr(install, name)),
        hs.Options(name="temp", value=25.0),
        hs.Options(name="save", value="selected"),
        hs.Save([raw for raw in lvshift_signal_names() if raw != "time"]),
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


# The characterization, in every PDK about its own core supply: the input supply from a quarter of
# it to all of it at the core supply, and the output supply (83 to 108 % of it) at two thirds of
# it for the input (half of it is below some PDK's threshold); in TSMC65, 0.3 to 1.2 V in and 1.0
# to 1.3 V out.
VDDL_SWEEP = (6 / 24, 7 / 24, 8 / 24, 9 / 24, 10 / 24, 12 / 24, 14 / 24, 16 / 24, 20 / 24, 1.0)
VDD_SWEEP = (10 / 12, 11 / 12, 1.0, 13 / 12)
NOMINAL_VDDL = 16 / 24


def lvshift_characterization(run_dir: Path, *, check: bool = False) -> Path:
    """Run every level shifter over the input and the output supply in every PDK: 3 cases, 14 points each.

    Each point writes ``<pdk>/<case>/<sweep>/<point>/result.h5`` (a ``MeasLvShift``). ``check``
    runs the nominal point of each case with Spectre's checks instead, writing no measurement.
    """

    from flow.analysis.types import MeasInfo, Wave
    from flow.circuit.results import read_raw_transient
    from flow.comp.layout import PDKS
    from flow.lvshift.analysis import MeasLvShift

    run_dir.mkdir(parents=True, exist_ok=True)
    jobs = {}
    for pdk in PDKS:
        supply = importlib.import_module(f"pdk.{pdk}.hdl21.site").install.supply_voltage(h.pdk.Corner.TYP)
        points = {"vddl": [(supply, step * supply) for step in VDDL_SWEEP]}
        points["vdd"] = [(step * supply, NOMINAL_VDDL * supply) for step in VDD_SWEEP]
        if check:
            points = {"vddl": [(supply, NOMINAL_VDDL * supply)]}
        for case, lvshift in CASES.items():
            for sweep, values in points.items():
                for vdd, vddl in values:
                    jobs[f"{pdk}/{case}/{sweep}/vdd{round(vdd * 1e3)}_vddl{round(vddl * 1e3)}"] = (
                        LvShiftTbParams(pdk=pdk, lvshift=lvshift, vdd=round(vdd, 4), vddl=round(vddl, 4)),
                        abs(vdd - supply) < 1e-6 and abs(vddl - NOMINAL_VDDL * supply) < 1e-6,
                    )
    names = lvshift_signal_names()
    failures: dict[str, str] = {}
    # one pool per PDK: hdl21 compiles each generated module in place, for the first PDK it meets
    for pdk in PDKS:
        with ProcessPoolExecutor(max_workers=16, mp_context=get_context("spawn")) as executor:
            futures = {
                executor.submit(_run_lvshift_sim, run_dir / name, params, check=check): (name, params, nominal)
                for name, (params, nominal) in jobs.items()
                if params.pdk == pdk
            }
            for future in as_completed(futures):
                name, params, nominal = futures[future]
                try:
                    raw_path = future.result()
                    if check:
                        continue
                    # one record from time zero on the stored grid; the supply currents as positive draw
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
                    measurement = MeasLvShift(
                        group=None,
                        index=None,
                        dut=params.lvshift,
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
        raise RuntimeError(f"{len(failures)} level shifter points failed; see {failure_path}")
    return run_dir
