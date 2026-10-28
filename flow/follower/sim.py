"""Follower testbench and named Spectre simulation targets, in every PDK.

The testbench: the input a DC level carrying a 1 V AC
stimulus, current-reference biases (a diode-connected copy fed the bias current, from a supply
of its own), a capacitive load, an operating point, the AC response and the supply's transfer to
the output (Spectre's ``xf``, for the PSRR). The same bench can instead put its AC stimulus on a
test current into the output (1 V through a large resistor), whose response is the output
impedance, where a flipped follower differs from a plain one; or drive the input with a large
step up and back down, whose transient gives the slew rates
(a source follower pulls one way through its device, the other only with its bias current).
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
from hdl21.primitives import C, Idc, MosType, R, Vdc, Vpulse
from vlsirtools.spice import ResultFormat, SimError, SimOptions, SupportedSimulators

from flow.analysis.io import write_measurement
from flow.circuit.devices import mos as _mos
from flow.circuit.ports import testbench_from_ports

from .subckt import CASES, Follower, FollowerNets, FollowerParams


def follower_signal_names() -> dict[str, str]:
    """Derive simulator saves and waveform names from the block's net bundle."""
    names = {"freq": "freq"}
    for net in FollowerNets.signals.values():
        if net.vis == h.Visibility.PORT and net.usage not in (h.Usage.POWER, h.Usage.GROUND):
            names[f"xtop.{net.name}"] = net.name
        if net.usage == h.Usage.POWER:
            names[f"xtop.v{net.name}:p"] = f"i({net.name})"
    return names


@h.paramclass
class FollowerTbParams:
    """Parameters which determine the generated follower testbench."""

    pdk = h.Param(dtype=str, desc="PDK the testbench compiles to and simulates in", default="tsmc65")
    vdd = h.Param(dtype=h.Scalar, desc="Supply voltage", default=1.2)
    follower = h.Param(dtype=FollowerParams, desc="Follower parameters", default=FollowerParams())
    cload = h.Param(dtype=h.Scalar, desc="Load capacitance on vout (F)", default=100e-15)
    vin = h.Param(dtype=h.Scalar, desc="Input DC voltage", default=0.9)
    bias_current_a = h.Param(dtype=float, desc="Current the bias references set (A)", default=20e-6)
    output_test = h.Param(dtype=bool, desc="AC stimulus on a test current into vout, not on vin", default=False)
    test_resistance_ohm = h.Param(dtype=float, desc="Series resistance of the output test current", default=1e6)
    fstart_hz = h.Param(dtype=float, desc="AC sweep start", default=1e3)
    fstop_hz = h.Param(dtype=float, desc="AC sweep stop", default=1e11)
    points_per_decade = h.Param(dtype=int, desc="AC points per decade", default=20)
    step_v = h.Param(dtype=h.Scalar, desc="Input step about vin for the transient bench; 0: the AC bench", default=0.0)
    period_s = h.Param(dtype=h.Scalar, desc="Step period: up a quarter in, down three quarters in", default=20e-9)
    transition_time_s = h.Param(dtype=h.Scalar, desc="Input step rise and fall time", default=10e-12)
    waveform_sample_interval_s = h.Param(dtype=float, desc="Uniform waveform record interval", default=5e-12)


def _validate_follower_tb_params(params: FollowerTbParams) -> None:
    values = (params.vdd, params.cload, params.vin, params.bias_current_a)
    if not all(math.isfinite(float(value)) for value in values):
        raise ValueError("follower testbench values must be finite")
    if min(float(params.vdd), float(params.cload), params.bias_current_a) <= 0:
        raise ValueError("follower supply, load, and bias current must be positive")
    if not 0 <= float(params.vin) <= float(params.vdd):
        raise ValueError("follower input must lie between the rails")
    if not 0 < params.fstart_hz < params.fstop_hz or params.points_per_decade < 1:
        raise ValueError("follower frequency sweep must rise from a positive start")
    if float(params.step_v):
        if params.output_test:
            raise ValueError("the follower step bench drives the input, not the output test current")
        if (
            not 0
            <= float(params.vin) - float(params.step_v) / 2
            < float(params.vin) + float(params.step_v) / 2
            <= float(params.vdd)
        ):
            raise ValueError("the follower input step must rise and stay between the rails")
        if (
            not 0 < 4 * float(params.transition_time_s) < float(params.period_s)
            or params.waveform_sample_interval_s <= 0
        ):
            raise ValueError("the follower step needs short edges in its period and a positive record interval")


@h.generator
def FollowerTb(params: FollowerTbParams) -> h.Module:
    """Generate the follower testbench: vin a DC level with the AC
    stimulus, current-reference biases, a capacitive load; or the AC stimulus as a test current
    into vout; or with ``step_v`` the input stepping up about vin a quarter period in and back down
    three quarters in."""

    _validate_follower_tb_params(params)

    FollowerTb, connections = testbench_from_ports(
        "FollowerTb", {net.name: net for net in FollowerNets.signals.values() if net.vis == h.Visibility.PORT}
    )
    vss = FollowerTb.vss
    FollowerTb.vvdd = Vdc(dc=params.vdd)(p=FollowerTb.vdd, n=vss)
    if float(params.step_v):
        half, edge = float(params.step_v) / 2, params.transition_time_s
        FollowerTb.vvin = Vpulse(
            v1=float(params.vin) - half,
            v2=float(params.vin) + half,
            delay=float(params.period_s) / 4,
            width=float(params.period_s) / 2 - float(edge),
            period=params.period_s,
            rise=edge,
            fall=edge,
        )(p=FollowerTb.vin, n=vss)
    else:
        FollowerTb.vvin = Vdc(dc=params.vin, ac=0.0 if params.output_test else 1.0)(p=FollowerTb.vin, n=vss)
    # the bias references: a diode-connected copy of the current-source
    # device on each bias, fed the bias current
    follower = params.follower
    size = {"vth": follower.vth, "w": follower.bias_w, "l": follower.bias_l}
    # the references draw from their own supply, so the follower's is its own current
    FollowerTb.vddb = h.Signal()
    FollowerTb.vvddb = Vdc(dc=params.vdd)(p=FollowerTb.vddb, n=vss)
    FollowerTb.mbn = _mos(tp=MosType.NMOS, **size)(d=FollowerTb.vbn, g=FollowerTb.vbn, s=vss, b=vss)
    FollowerTb.ibn = Idc(dc=params.bias_current_a)(p=FollowerTb.vddb, n=FollowerTb.vbn)
    FollowerTb.mbp = _mos(tp=MosType.PMOS, **size)(
        d=FollowerTb.vbp, g=FollowerTb.vbp, s=FollowerTb.vddb, b=FollowerTb.vddb
    )
    FollowerTb.ibp = Idc(dc=params.bias_current_a)(p=FollowerTb.vbp, n=vss)
    FollowerTb.cload = C(c=params.cload)(p=FollowerTb.vout, n=vss)
    if params.output_test:
        # the output test current: 1 V of AC through a large resistor, its DC blocked by 1 F, into
        # vout. VLSIR writes a controlled current source's gain under a name Spectre ignores.
        FollowerTb.test, FollowerTb.test_dc = h.Signal(), h.Signal()
        FollowerTb.vtest = Vdc(dc=0.0, ac=1.0)(p=FollowerTb.test, n=vss)
        FollowerTb.ctest = C(c=1.0)(p=FollowerTb.test, n=FollowerTb.test_dc)
        FollowerTb.rtest = R(r=params.test_resistance_ohm)(p=FollowerTb.test_dc, n=FollowerTb.vout)
    FollowerTb.dut = Follower(params.follower)(**connections)
    return FollowerTb


def _run_follower_sim(run_dir: Path, params: FollowerTbParams, *, check: bool = False) -> Path:
    """Run the operating point, AC response and the supply's transfer to vout of one follower in
    its PDK, or with ``step_v`` its transient over one step period, and return the raw file
    (``check``: two points a decade, with Spectre's static checks)."""

    pdk = importlib.import_module(f"pdk.{params.pdk}")
    install = importlib.import_module(f"pdk.{params.pdk}.hdl21.site").install

    run_dir.mkdir(parents=True, exist_ok=True)
    h.pdk.set_default(pdk.pdk_logic)
    tb = FollowerTb(params)
    h.pdk.compile(tb)
    attrs = [
        install.include(h.pdk.Corner.TYP),
        # what else the PDK's simulations take, in this order: TSMC's pre-simulation settings,
        # the device names its netlists use (pdk/<name>/hdl21)
        *(getattr(install, name)() for name in ("include_pre_simulation", "include_devices") if hasattr(install, name)),
        hs.Options(name="temp", value=25.0),
        hs.Options(name="save", value="selected"),
        hs.Save([raw for raw in follower_signal_names() if raw != "freq"]),
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
    if float(params.step_v):
        interval = params.waveform_sample_interval_s
        attrs.append(
            hs.Tran(
                tstop=params.period_s,
                name="tran",
                options={"strobeperiod": interval, "maxstep": interval, "strobeoutput": "strobeonly"},
            )
        )
    else:
        decade = 2 if check else params.points_per_decade
        attrs += [
            hs.Op(name="op"),
            # VLSIR's npts: points per decade
            hs.Ac(sweep=hs.LogSweep(start=params.fstart_hz, stop=params.fstop_hz, npts=decade), name="ac"),
            # every source's transfer to vout; hdl21 has no transfer-function analysis
            h.Literal(f"xf (xtop.vout 0) xf start={params.fstart_hz:g} stop={params.fstop_hz:g} dec={decade}"),
        ]
    # the simulator's error holds its simulation, which cannot cross back from a worker process:
    # raise it as text
    try:
        hs.Sim(tb=tb, attrs=attrs).run(
            SimOptions(
                simulator=SupportedSimulators.SPECTRE,
                # the campaign reads the raw file itself: an operating point and an AC analysis
                fmt=ResultFormat.NONE,
                rundir=run_dir,
                simulator_args=(
                    *(() if check else ("-format", "nutbin")),
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


# The characterization, in every PDK at its own core supply: the input level across the supply
# (25 levels), each with the AC stimulus on the input (gain, bandwidth, PSRR) and on an output test
# current (output impedance); and at each case's nominal input a step of a quarter of the supply
# up and back down (slew rates). Each case's nominal input, the static checks', sits where it
# follows in most PDKs: an NMOS source follower high, a PMOS one low, the flipped ones in their
# narrower range.
VIN_SWEEP = tuple(step / 24 for step in range(25))
NOMINAL_VIN = {"source": 18 / 24, "source_pmos": 6 / 24, "flipped": 12 / 24, "flipped_pmos": 6 / 24}
STEP = 1 / 4


def follower_characterization(run_dir: Path, *, check: bool = False) -> Path:
    """Run every follower over its input level, with the AC on the input and on the output, and
    its step at the nominal input, in every PDK: 204 runs each.

    Each AC point writes ``<pdk>/<case>/<input|output>/vin<mV>/result.h5`` (a ``MeasFollower``),
    each step ``<pdk>/<case>/step/vin<mV>/result.h5`` (a ``MeasFollowerStep``). ``check`` runs the
    nominal input of each case with Spectre's checks instead, writing no measurement.
    """

    from vlsirtools.spice.spectre import parse_nutbin

    from flow.analysis.types import MeasInfo
    from flow.circuit.results import read_transient_wave
    from flow.comp.layout import PDKS
    from flow.follower.analysis import MeasFollower, MeasFollowerStep

    run_dir.mkdir(parents=True, exist_ok=True)
    jobs = {}
    for pdk in PDKS:
        supply = importlib.import_module(f"pdk.{pdk}.hdl21.site").install.supply_voltage(h.pdk.Corner.TYP)
        for case, follower in CASES.items():
            for step in (NOMINAL_VIN[case],) if check else VIN_SWEEP:
                vin = round(step * supply, 4)
                for output_test in (False,) if check else (False, True):
                    jobs[f"{pdk}/{case}/{'output' if output_test else 'input'}/vin{round(vin * 1e3)}"] = (
                        FollowerTbParams(pdk=pdk, follower=follower, vdd=supply, vin=vin, output_test=output_test)
                    )
            if not check:
                vin = round(NOMINAL_VIN[case] * supply, 4)
                jobs[f"{pdk}/{case}/step/vin{round(vin * 1e3)}"] = FollowerTbParams(
                    pdk=pdk, follower=follower, vdd=supply, vin=vin, step_v=round(STEP * supply, 4)
                )
    # the step bench's traces: the AC bench's on a time axis
    tran_names = {"time": "time", **{raw: name for raw, name in follower_signal_names().items() if raw != "freq"}}
    failures: dict[str, str] = {}
    # one pool per PDK: hdl21 compiles each generated module in place, for the first PDK it meets
    for pdk in PDKS:
        with ProcessPoolExecutor(max_workers=16, mp_context=get_context("spawn")) as executor:
            futures = {
                executor.submit(_run_follower_sim, run_dir / name, params, check=check): (name, params)
                for name, params in jobs.items()
                if params.pdk == pdk
            }
            for future in as_completed(futures):
                name, params = futures[future]
                try:
                    raw_path = future.result()
                    if check:
                        continue
                    info = MeasInfo(
                        backend="spice",
                        timestamp_utc=datetime.fromtimestamp(raw_path.stat().st_mtime, tz=UTC),
                        instruments={"simulator": "Spectre"},
                        readbacks={
                            "pdk": name.split("/")[0],
                            "case": name.split("/")[1],
                            "stimulus": name.split("/")[2],
                            "raw_file": raw_path.name,
                            "supply_current_convention": "positive_current_draw",
                        },
                    )
                    if float(params.step_v):
                        # one record from time zero on the stored grid; the supply current as positive draw
                        wave, raw_points = read_transient_wave(
                            raw_path, tran_names, params.waveform_sample_interval_s, supply_rails=("vdd",)
                        )
                        info.readbacks.update(
                            {"waveform_sample_interval_s": params.waveform_sample_interval_s, "raw_points": raw_points}
                        )
                        measurement = MeasFollowerStep(
                            group=None,
                            index=None,
                            dut=params.follower,
                            info=info,
                            param=params,
                            trial_index=np.arange(1, dtype=np.int64),
                            wave=wave,
                        )
                        write_measurement(raw_path.parent / "result.h5", measurement)
                        continue
                    with raw_path.open("rb") as stream:
                        analyses = parse_nutbin(stream)
                    op, ac, xf = analyses["op"].data, analyses["ac"].data, analyses["xf"].data
                    # the output per volt of input; or the output impedance, from the divider of the test
                    # resistance and the impedance that the 1 V test stimulus drives
                    response = np.asarray(ac["xtop.vout"])
                    if params.output_test:
                        response = response * params.test_resistance_ohm / (1 - response)
                    info.readbacks.update(
                        {
                            "nominal": abs(float(params.vin) - NOMINAL_VIN[name.split("/")[1]] * float(params.vdd))
                            < 1e-6,
                            "op_supply_current_a": -float(np.real(op["xtop.vvdd:p"][0])),
                            "op_vout_v": float(np.real(op["xtop.vout"][0])),
                        }
                    )
                    measurement = MeasFollower(
                        group=None,
                        index=None,
                        dut=params.follower,
                        info=info,
                        param=params,
                        frequency_hz=np.real(np.asarray(ac["freq"])).astype(np.float64),
                        magnitude=np.abs(response).astype(np.float64),
                        phase_deg=np.degrees(np.unwrap(np.angle(response))).astype(np.float64),
                        supply_gain_v_per_v=np.abs(np.asarray(xf["xtop.vvdd"])).astype(np.float64),
                    )
                    write_measurement(raw_path.parent / "result.h5", measurement)
                except Exception as error:  # noqa: BLE001 - report every independent point failure
                    failures[name] = repr(error)
    if failures:
        failure_path = run_dir / "failures.json"
        failure_path.write_text(json.dumps(failures, indent=2) + "\n")
        raise RuntimeError(f"{len(failures)} follower points failed; see {failure_path}")
    return run_dir
