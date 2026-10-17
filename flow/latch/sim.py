"""Latch, flip-flop, divider and SR latch testbench and named Spectre simulation targets, in every PDK.

The testbench follows BAG's flip-flop and latch timing benches (bag3_digital's liberty
characterization): complementary clocks, data that toggles once per cycle and arrives a set
offset before every capturing edge (the rising edge of a flip-flop, the closing falling edge of a
latch), an initial reset, and output loads. Sweeping that offset finds setup and hold; the SR
latches get set and reset pulses on the same bench, and a divider ignores the data.
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

from .subckt import CASES, Latch, LatchNets, LatchParams, Style


def latch_signal_names() -> dict[str, str]:
    """Derive simulator saves and waveform names from the block's net bundle."""
    names = {"time": "time"}
    for net in LatchNets.signals.values():
        if net.vis == h.Visibility.PORT and net.usage not in (h.Usage.POWER, h.Usage.GROUND):
            names[f"xtop.{net.name}"] = net.name
        if net.usage == h.Usage.POWER:
            names[f"xtop.v{net.name}:p"] = f"i({net.name})"
    return names


@h.paramclass
class LatchTbParams:
    """Parameters which determine the generated latch testbench."""

    pdk = h.Param(dtype=str, desc="PDK the testbench compiles to and simulates in", default="tsmc65")
    waveform_sample_interval_s = h.Param(
        dtype=float, desc="Maximum raw step and stored waveform spacing", default=1e-12
    )
    vdd = h.Param(dtype=h.Scalar, desc="Supply voltage", default=1.2)
    latch = h.Param(dtype=LatchParams, desc="Latch parameters", default=LatchParams())
    cload = h.Param(dtype=h.Scalar, desc="Load capacitance on q and qb (F)", default=2e-15)
    clock_period_s = h.Param(dtype=h.Scalar, desc="Clock period", default=2e-9)
    data_offset_s = h.Param(dtype=h.Scalar, desc="Data edge before each capturing clock edge", default=0.5e-9)
    data_period_s = h.Param(dtype=h.Scalar, desc="SR set and reset period", default=5.2e-9)
    reset_time_s = h.Param(dtype=h.Scalar, desc="Reset (rst) pulse length at the start", default=0.5e-9)
    transition_time_s = h.Param(dtype=h.Scalar, desc="Rise and fall time of every source", default=50e-12)
    cycles = h.Param(dtype=int, desc="Clock cycles after the reset", default=8)


def _validate_latch_tb_params(params: LatchTbParams) -> None:
    values = (
        params.waveform_sample_interval_s,
        params.vdd,
        params.cload,
        params.clock_period_s,
        params.data_offset_s,
        params.data_period_s,
        params.reset_time_s,
        params.transition_time_s,
    )
    if not all(math.isfinite(float(value)) for value in values):
        raise ValueError("latch testbench values must be finite")
    if min(float(params.vdd), float(params.cload), float(params.waveform_sample_interval_s)) <= 0:
        raise ValueError("latch supply, load, and sample interval must be positive")
    edge = 2 * float(params.transition_time_s)
    if float(params.transition_time_s) <= 0 or min(float(params.clock_period_s), float(params.data_period_s)) <= edge:
        raise ValueError("latch periods must exceed both transitions, which must be positive")
    if abs(float(params.data_offset_s)) >= float(params.clock_period_s) / 2 + float(params.transition_time_s):
        raise ValueError("latch data offset must lie within half a clock period of the capturing edge")
    if float(params.reset_time_s) < 0 or params.cycles < 3:
        raise ValueError("latch reset time must be non-negative and the run at least three cycles")


@h.generator
def LatchTb(params: LatchTbParams) -> h.Module:
    """Generate the shared latch testbench: complementary clocks, data a set offset before each
    capturing edge, an initial reset pulse, and set and reset pulses for an SR latch."""

    _validate_latch_tb_params(params)

    LatchTb, connections = testbench_from_ports(
        "LatchTb", {net.name: net for net in LatchNets.signals.values() if net.vis == h.Visibility.PORT}
    )
    vdd, vss = params.vdd, LatchTb.vss
    transition = float(params.transition_time_s)
    edge = {"rise": transition, "fall": transition}
    clock, data = float(params.clock_period_s), float(params.data_period_s)
    LatchTb.vvdd = Vdc(dc=vdd)(p=LatchTb.vdd, n=vss)
    LatchTb.vclk = Vpulse(v1=0.0, v2=vdd, period=clock, width=clock / 2, delay=clock / 2, **edge)(p=LatchTb.clk, n=vss)
    LatchTb.vclkb = Vpulse(v1=vdd, v2=0.0, period=clock, width=clock / 2, delay=clock / 2, **edge)(
        p=LatchTb.clkb, n=vss
    )
    # the capturing edge's mid-supply time: a flip-flop's rising edge, a latch's falling (closing) one
    capture = clock / 2 + transition / 2 + (0.0 if params.latch.flop else clock / 2 + transition)
    first = max(1, math.ceil((float(params.reset_time_s) + transition + float(params.data_offset_s) - capture) / clock))
    # data toggles once per cycle, each mid-supply crossing data_offset_s before a capturing edge
    LatchTb.vd = Vpulse(
        v1=0.0,
        v2=vdd,
        period=2 * clock,
        width=clock - transition,
        delay=capture + first * clock - float(params.data_offset_s) - transition / 2,
        **edge,
    )(p=LatchTb.d, n=vss)
    LatchTb.vrst = Vpulse(v1=vdd, v2=0.0, period=1.0, width=0.5, delay=params.reset_time_s, **edge)(
        p=LatchTb.rst, n=vss
    )
    # set and reset pulses, a quarter period each and half a period apart (active low for a NAND latch)
    active, idle = (0.0, vdd) if params.latch.style == Style.SR_NAND else (vdd, 0.0)
    for name, net, delay in (("vs", LatchTb.s, data / 4), ("vr", LatchTb.r, 3 * data / 4)):
        LatchTb.add(
            Vpulse(v1=idle, v2=active, period=data, width=data / 4, delay=delay, **edge)(p=net, n=vss), name=name
        )
    LatchTb.cloadq = C(c=params.cload)(p=LatchTb.q, n=vss)
    LatchTb.cloadqb = C(c=params.cload)(p=LatchTb.qb, n=vss)
    LatchTb.dut = Latch(params.latch)(**connections)
    return LatchTb


def _run_latch_sim(run_dir: Path, params: LatchTbParams, *, check: bool = False) -> Path:
    """Run one latch testbench transient in its PDK and return its raw file: the reset, then
    ``cycles`` clock cycles (an SR latch: three set and reset periods).

    ``check`` adds Spectre's static and connectivity checks and shortens the run to a tenth.
    """

    pdk = importlib.import_module(f"pdk.{params.pdk}")
    install = importlib.import_module(f"pdk.{params.pdk}.hdl21.site").install

    run_dir.mkdir(parents=True, exist_ok=True)
    h.pdk.set_default(pdk.pdk_logic)
    tb = LatchTb(params)
    h.pdk.compile(tb)
    interval = params.waveform_sample_interval_s
    tstop = (
        3 * float(params.data_period_s)
        if params.latch.style != Style.CLOCKED
        else float(params.reset_time_s) + (params.cycles + 1) * float(params.clock_period_s)
    )
    attrs = [
        install.include(h.pdk.Corner.TYP),
        # what else the PDK's simulations take, in this order: TSMC's pre-simulation settings,
        # the device names its netlists use (pdk/<name>/hdl21)
        *(getattr(install, name)() for name in ("include_pre_simulation", "include_devices") if hasattr(install, name)),
        hs.Options(name="temp", value=25.0),
        hs.Options(name="save", value="selected"),
        hs.Save([raw for raw in latch_signal_names() if raw != "time"]),
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


# The characterization, in every PDK about its own core supply: every case over the supply (75 to
# 108 % of it); at the core supply the clocked latches and the flip-flop over the data offset
# (setup and hold), the flip-flop and divider over the clock period.
SUPPLY_SWEEP = (9 / 12, 10 / 12, 11 / 12, 1.0, 13 / 12)
DATA_OFFSET_SWEEP_S = tuple(round(offset * 1e-12, 15) for offset in range(-200, 301, 10))
CLOCK_PERIOD_SWEEP_S = (
    2e-9,
    1e-9,
    500e-12,
    300e-12,
    200e-12,
    150e-12,
    120e-12,
    100e-12,
    80e-12,
    60e-12,
    40e-12,
    30e-12,
)
NOMINAL_CLOCK_PERIOD_S = 2e-9
NOMINAL_DATA_OFFSET_S = 0.5e-9


def latch_characterization(run_dir: Path, *, check: bool = False) -> Path:
    """Run the supply, data offset and clock period sweeps in every PDK (about 200 transients each).

    Each point writes ``<pdk>/<case>/<sweep>/<point>/result.h5`` (a ``MeasLatch``). ``check`` runs
    the nominal point of each case with Spectre's checks instead, writing no measurement.
    """

    from flow.analysis.types import MeasInfo, Wave
    from flow.circuit.results import read_raw_transient
    from flow.comp.layout import PDKS
    from flow.latch.analysis import MeasLatch

    run_dir.mkdir(parents=True, exist_ok=True)
    jobs = {}
    for pdk in PDKS:
        supply = importlib.import_module(f"pdk.{pdk}.hdl21.site").install.supply_voltage(h.pdk.Corner.TYP)
        for case, latch in CASES.items():
            for vdd in (supply,) if check else [round(step * supply, 4) for step in SUPPLY_SWEEP]:
                jobs[f"{pdk}/{case}/supply/vdd{round(vdd * 1e3)}"] = LatchTbParams(pdk=pdk, latch=latch, vdd=vdd)
            if check or latch.style != Style.CLOCKED:
                continue
            if not latch.divider:
                for offset in DATA_OFFSET_SWEEP_S:
                    jobs[f"{pdk}/{case}/offset/offset{round(offset * 1e12)}ps"] = LatchTbParams(
                        pdk=pdk, latch=latch, vdd=supply, data_offset_s=offset
                    )
            if latch.flop:
                for period in CLOCK_PERIOD_SWEEP_S:
                    # the edges and the data offset scale with a short clock
                    jobs[f"{pdk}/{case}/period/period{round(period * 1e12)}ps"] = LatchTbParams(
                        pdk=pdk,
                        latch=latch,
                        vdd=supply,
                        clock_period_s=period,
                        transition_time_s=min(50e-12, period / 8),
                        data_offset_s=period / 4,
                        reset_time_s=max(0.5e-9, 2 * period),
                        cycles=12,
                    )
    names = latch_signal_names()
    failures: dict[str, str] = {}
    # one pool per PDK: hdl21 compiles each generated module in place, for the first PDK it meets
    for pdk in PDKS:
        with ProcessPoolExecutor(max_workers=16, mp_context=get_context("spawn")) as executor:
            futures = {
                executor.submit(_run_latch_sim, run_dir / name, params, check=check): (name, params)
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
                    measurement = MeasLatch(
                        group=None,
                        index=None,
                        dut=params.latch,
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
        raise RuntimeError(f"{len(failures)} latch points failed; see {failure_path}")
    return run_dir


def main() -> None:
    """Create one output directory and run one named latch target."""

    targets = {target.__name__: target for target in (latch_characterization,)}
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("target", nargs="?", choices=sorted(targets))
    args = parser.parse_args()
    if args.target is None:
        print("Available latch simulation targets:")
        for name in sorted(targets):
            print(f"  {name}")
        return
    run_dir = (
        Path(__file__).resolve().parents[2]
        / "build"
        / "sim"
        / "latch"
        / args.target
        / datetime.now().astimezone().strftime("%Y%m%d_%H%M%S")
    )
    run_dir.mkdir(parents=True, exist_ok=False)
    targets[args.target](run_dir)


if __name__ == "__main__":
    main()
