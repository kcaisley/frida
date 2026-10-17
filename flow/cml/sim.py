"""CML testbench and named Spectre simulation targets, in every PDK.

The testbench follows Usb2Phy's CML benches (``CmlDivTb`` and its ``DiffClkGen``): differential
pulses between the CML levels on the data input and on the clock (an XOR's second input),
current-reference biases (a diode-connected copy fed the tail current, from a supply of its own)
and a load on each output. Every case gets the same stimulus: a buffer ignores the clock, a
divider the data. The characterization sweeps the clock frequency, with the data at 2.6 clock
periods, and the tail current, the knob that sets a CML gate's swing.
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
from hdl21.primitives import C, Idc, MosType, Vdc, Vpulse
from vlsirtools.spice import ResultFormat, SimError, SimOptions, SupportedSimulators

from flow.analysis.io import interpolate_wave_records, write_measurement
from flow.circuit.ports import testbench_from_ports
from flow.comp.subckt import _mos

from .subckt import CASES, Cml, CmlNets, CmlParams


def cml_signal_names() -> dict[str, str]:
    """Derive simulator saves and waveform names from the block's net bundle."""
    names = {"time": "time"}
    for net in CmlNets.signals.values():
        if net.vis == h.Visibility.PORT and net.usage not in (h.Usage.POWER, h.Usage.GROUND):
            names[f"xtop.{net.name}"] = net.name
        if net.usage == h.Usage.POWER:
            names[f"xtop.v{net.name}:p"] = f"i({net.name})"
    return names


@h.paramclass
class CmlTbParams:
    """Parameters which determine the generated CML testbench."""

    pdk = h.Param(dtype=str, desc="PDK the testbench compiles to and simulates in", default="tsmc65")
    waveform_sample_interval_s = h.Param(
        dtype=float, desc="Maximum raw step and stored waveform spacing", default=0.5e-12
    )
    vdd = h.Param(dtype=h.Scalar, desc="Supply voltage", default=1.2)
    cml = h.Param(dtype=CmlParams, desc="CML parameters", default=CmlParams())
    cload = h.Param(dtype=h.Scalar, desc="Load capacitance on each output (F)", default=2e-15)
    vhigh = h.Param(dtype=h.Scalar, desc="High level of the CML inputs", default=1.2)
    vlow = h.Param(dtype=h.Scalar, desc="Low level of the CML inputs", default=0.8)
    tail_current_a = h.Param(dtype=float, desc="Tail current the bias references set (A)", default=30e-6)
    clock_period_s = h.Param(dtype=h.Scalar, desc="Clock (or second input) period", default=200e-12)
    data_period_s = h.Param(dtype=h.Scalar, desc="Data input period", default=520e-12)
    transition_time_s = h.Param(dtype=h.Scalar, desc="Rise and fall time of every source", default=20e-12)
    tstop_s = h.Param(dtype=h.Scalar, desc="Transient length", default=4e-9)


def _validate_cml_tb_params(params: CmlTbParams) -> None:
    values = (params.vdd, params.cload, params.vhigh, params.vlow, params.tail_current_a)
    values += (params.clock_period_s, params.data_period_s, params.transition_time_s, params.tstop_s)
    if not all(math.isfinite(float(value)) for value in (*values, params.waveform_sample_interval_s)):
        raise ValueError("CML testbench values must be finite")
    if min(float(params.vdd), float(params.cload), params.waveform_sample_interval_s) <= 0:
        raise ValueError("CML supply, load, and sample interval must be positive")
    edge = 2 * float(params.transition_time_s)
    if float(params.transition_time_s) <= 0 or min(float(params.clock_period_s), float(params.data_period_s)) <= edge:
        raise ValueError("CML periods must exceed both transitions, which must be positive")
    if float(params.tstop_s) <= 4 * float(params.data_period_s):
        raise ValueError("CML transient must hold more than four data periods")


@h.generator
def CmlTb(params: CmlTbParams) -> h.Module:
    """Generate the CML testbench (Usb2Phy ``CmlDivTb``'s ``DiffClkGen``): differential data and
    clock pulses between the CML levels, current-reference biases, a load on each output."""

    _validate_cml_tb_params(params)

    CmlTb, connections = testbench_from_ports(
        "CmlTb", {net.name: net for net in CmlNets.signals.values() if net.vis == h.Visibility.PORT}
    )
    vss = CmlTb.vss
    hi, lo = params.vhigh, params.vlow
    edge = {"rise": params.transition_time_s, "fall": params.transition_time_s}
    CmlTb.vvdd = Vdc(dc=params.vdd)(p=CmlTb.vdd, n=vss)
    for name, period in (("in", float(params.data_period_s)), ("clk", float(params.clock_period_s))):
        for side, (v1, v2) in (("p", (lo, hi)), ("n", (hi, lo))):
            net = getattr(CmlTb, f"{name}{side}")
            CmlTb.add(
                Vpulse(v1=v1, v2=v2, period=period, width=period / 2, delay=period / 4, **edge)(p=net, n=vss),
                name=f"v{name}{side}",
            )
    # the bias references, as Usb2Phy's benches bias: a diode-connected copy of the tail on the
    # input type's bias, fed the tail current, and of a load on the other, fed half of it
    cml = params.cml
    tail = (cml.tail_w, cml.tail_l, params.tail_current_a)
    load = (cml.load_w, cml.load_l, params.tail_current_a / 2)
    (n_w, n_l, n_current), (p_w, p_l, p_current) = (tail, load) if cml.input_xtors == MosType.NMOS else (load, tail)
    # the references draw from their own supply, so the gate's is its own current
    CmlTb.vddb = h.Signal()
    CmlTb.vvddb = Vdc(dc=params.vdd)(p=CmlTb.vddb, n=vss)
    CmlTb.mbn = _mos(tp=MosType.NMOS, vth=cml.vth, w=n_w, l=n_l)(d=CmlTb.vbn, g=CmlTb.vbn, s=vss, b=vss)
    CmlTb.ibn = Idc(dc=n_current)(p=CmlTb.vddb, n=CmlTb.vbn)
    CmlTb.mbp = _mos(tp=MosType.PMOS, vth=cml.vth, w=p_w, l=p_l)(d=CmlTb.vbp, g=CmlTb.vbp, s=CmlTb.vddb, b=CmlTb.vddb)
    CmlTb.ibp = Idc(dc=p_current)(p=CmlTb.vbp, n=vss)
    CmlTb.cloadp = C(c=params.cload)(p=CmlTb.outp, n=vss)
    CmlTb.cloadn = C(c=params.cload)(p=CmlTb.outn, n=vss)
    CmlTb.dut = Cml(params.cml)(**connections)
    return CmlTb


def _run_cml_sim(run_dir: Path, params: CmlTbParams, *, check: bool = False) -> Path:
    """Run one CML testbench transient in its PDK and return its raw file.

    ``check`` adds Spectre's static and connectivity checks and shortens the run to a tenth.
    """

    pdk = importlib.import_module(f"pdk.{params.pdk}")
    install = importlib.import_module(f"pdk.{params.pdk}.hdl21.site").install

    run_dir.mkdir(parents=True, exist_ok=True)
    h.pdk.set_default(pdk.pdk_logic)
    tb = CmlTb(params)
    h.pdk.compile(tb)
    interval = params.waveform_sample_interval_s
    attrs = [
        install.include(h.pdk.Corner.TYP),
        # what else the PDK's simulations take, in this order: TSMC's pre-simulation settings,
        # the device names its netlists use (pdk/<name>/hdl21)
        *(getattr(install, name)() for name in ("include_pre_simulation", "include_devices") if hasattr(install, name)),
        hs.Options(name="temp", value=25.0),
        hs.Options(name="save", value="selected"),
        hs.Save([raw for raw in cml_signal_names() if raw != "time"]),
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


# The characterization, in every PDK at its own core supply: the clock period from 1 ns down to
# 25 ps (each run about twenty clock periods, the data at 2.6 of them), and the tail current at the
# nominal 200 ps clock. The CML levels span the supply's top third (a PMOS input: its bottom third).
CLOCK_PERIOD_SWEEP_S = (1e-9, 500e-12, 300e-12, 200e-12, 150e-12, 100e-12, 70e-12, 50e-12, 35e-12, 25e-12)
TAIL_CURRENT_SWEEP_A = (5e-6, 10e-6, 15e-6, 20e-6, 30e-6, 40e-6, 60e-6, 80e-6, 100e-6)
NOMINAL_CLOCK_PERIOD_S = 200e-12
NOMINAL_TAIL_CURRENT_A = 30e-6


def cml_characterization(run_dir: Path, *, check: bool = False) -> Path:
    """Run every CML case over the clock period and the tail current in every PDK: 5 cases, 19 points each.

    Each point writes ``<pdk>/<case>/<sweep>/<point>/result.h5`` (a ``MeasCml``). ``check`` runs
    the nominal point of each case with Spectre's checks instead, writing no measurement.
    """

    from flow.analysis.types import MeasInfo, Wave
    from flow.circuit.results import read_raw_transient
    from flow.cml.analysis import MeasCml
    from flow.comp.layout import PDKS

    run_dir.mkdir(parents=True, exist_ok=True)
    jobs = {}
    for pdk in PDKS:
        supply = importlib.import_module(f"pdk.{pdk}.hdl21.site").install.supply_voltage(h.pdk.Corner.TYP)
        for case, cml in CASES.items():
            pmos = cml.input_xtors == MosType.PMOS
            levels = {"vhigh": supply / 3, "vlow": 0.0} if pmos else {"vhigh": supply, "vlow": 2 * supply / 3}
            points = {"period": [(period, NOMINAL_TAIL_CURRENT_A) for period in CLOCK_PERIOD_SWEEP_S]}
            points["tail"] = [(NOMINAL_CLOCK_PERIOD_S, current) for current in TAIL_CURRENT_SWEEP_A]
            if check:
                points = {"period": [(NOMINAL_CLOCK_PERIOD_S, NOMINAL_TAIL_CURRENT_A)]}
            for sweep, values in points.items():
                for period, current in values:
                    jobs[f"{pdk}/{case}/{sweep}/period{round(period * 1e12)}ps_tail{round(current * 1e9)}na"] = (
                        CmlTbParams(
                            pdk=pdk,
                            cml=cml,
                            vdd=supply,
                            clock_period_s=period,
                            data_period_s=2.6 * period,
                            transition_time_s=min(20e-12, period / 5),
                            tstop_s=20 * period + 0.5e-9,
                            waveform_sample_interval_s=min(0.5e-12, period / 100),
                            tail_current_a=current,
                            **{key: round(value, 4) for key, value in levels.items()},
                        )
                    )
    names = cml_signal_names()
    failures: dict[str, str] = {}
    # one pool per PDK: hdl21 compiles each generated module in place, for the first PDK it meets
    for pdk in PDKS:
        with ProcessPoolExecutor(max_workers=16, mp_context=get_context("spawn")) as executor:
            futures = {
                executor.submit(_run_cml_sim, run_dir / name, params, check=check): (name, params)
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
                    measurement = MeasCml(
                        group=None,
                        index=None,
                        dut=params.cml,
                        info=MeasInfo(
                            backend="spice",
                            timestamp_utc=datetime.fromtimestamp(raw_path.stat().st_mtime, tz=UTC),
                            instruments={"simulator": "Spectre"},
                            readbacks={
                                "pdk": name.split("/")[0],
                                "case": name.split("/")[1],
                                "sweep": name.split("/")[2],
                                "nominal": float(params.clock_period_s) == NOMINAL_CLOCK_PERIOD_S
                                and params.tail_current_a == NOMINAL_TAIL_CURRENT_A,
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
        raise RuntimeError(f"{len(failures)} CML points failed; see {failure_path}")
    return run_dir


def main() -> None:
    """Create one output directory and run one named CML target."""

    targets = {target.__name__: target for target in (cml_characterization,)}
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("target", nargs="?", choices=sorted(targets))
    args = parser.parse_args()
    if args.target is None:
        print("Available CML simulation targets:")
        for name in sorted(targets):
            print(f"  {name}")
        return
    run_dir = (
        Path(__file__).resolve().parents[2]
        / "build"
        / "sim"
        / "cml"
        / args.target
        / datetime.now().astimezone().strftime("%Y%m%d_%H%M%S")
    )
    run_dir.mkdir(parents=True, exist_ok=False)
    targets[args.target](run_dir)


if __name__ == "__main__":
    main()
