"""Discriminator testbench and named Spectre simulation targets, in every PDK.

The testbench follows the group's pixel comparator benches (DHPT ``Comparator_normal_TB``: the
input at the output's rising crossing less the reference, the offset, and the crossing's time
after the input's, the timewalk; LF-Monopix2 ``TB_CSA_NMOS_DisV1``): the threshold a DC level on
``inn``, the tail and output current sources biased by a diode-connected copy fed the bias current
from a supply of its own (Usb2Phy's ``UnityGainTb``), the output loaded by the next gate's input.
``inp`` either ramps slowly up across the threshold and back down (a triangle, its trip points:
offset and hysteresis), or steps from well below the threshold (a front end's baseline) to an
overdrive above it and back (the delay of each edge, and over the overdrive the timewalk).
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
from hdl21.primitives import C, Idc, MosType, Vdc, Vpulse
from vlsirtools.spice import ResultFormat, SimError, SimOptions, SupportedSimulators

from flow.analysis.io import write_measurement
from flow.circuit.ports import testbench_from_ports
from flow.comp.subckt import _mos

from .subckt import CASES, Disc, DiscNets, DiscParams


def disc_signal_names() -> dict[str, str]:
    """Derive simulator saves and waveform names from the block's net bundle."""
    names = {"time": "time"}
    for net in DiscNets.signals.values():
        if net.vis == h.Visibility.PORT and net.usage not in (h.Usage.POWER, h.Usage.GROUND):
            names[f"xtop.{net.name}"] = net.name
        if net.usage == h.Usage.POWER:
            names[f"xtop.v{net.name}:p"] = f"i({net.name})"
    return names


@h.paramclass
class DiscTbParams:
    """Parameters which determine the generated discriminator testbench."""

    pdk = h.Param(dtype=str, desc="PDK the testbench compiles to and simulates in", default="tsmc65")
    vdd = h.Param(dtype=h.Scalar, desc="Supply voltage", default=1.2)
    disc = h.Param(dtype=DiscParams, desc="Discriminator parameters", default=DiscParams())
    cload = h.Param(dtype=h.Scalar, desc="Load capacitance on the output (F)", default=10e-15)
    threshold_v = h.Param(dtype=h.Scalar, desc="Threshold on inn", default=0.6)
    bias_current_a = h.Param(dtype=float, desc="Current the bias reference sets (A)", default=2e-6)
    overdrive_v = h.Param(dtype=h.Scalar, desc="Step's top above the threshold; 0: the ramp bench", default=0.0)
    baseline_v = h.Param(dtype=h.Scalar, desc="Step's bottom below the threshold", default=0.1)
    ramp_v = h.Param(dtype=h.Scalar, desc="Ramp's reach either side of the threshold", default=0.1)
    ramp_time_s = h.Param(dtype=h.Scalar, desc="Ramp's rise and fall time", default=4e-6)
    period_s = h.Param(dtype=h.Scalar, desc="Step period: up a quarter in, down three quarters in", default=400e-9)
    transition_time_s = h.Param(dtype=h.Scalar, desc="Step rise and fall time", default=100e-12)
    waveform_sample_interval_s = h.Param(dtype=float, desc="Uniform waveform record interval", default=20e-12)


def _ramp_settle_s(params: DiscTbParams) -> float:
    """The ramp bench's rest before, between and after its two ramps."""
    return float(params.ramp_time_s) / 40


def stop_time_s(params: DiscTbParams) -> float:
    """The transient's length: one step period, or rest, ramp up, rest, ramp down, rest."""
    if float(params.overdrive_v):
        return float(params.period_s)
    return 2 * float(params.ramp_time_s) + 3 * _ramp_settle_s(params)


def _validate_disc_tb_params(params: DiscTbParams) -> None:
    values = (params.vdd, params.cload, params.threshold_v, params.overdrive_v, params.baseline_v, params.ramp_v)
    values += (params.ramp_time_s, params.period_s, params.transition_time_s)
    if not all(math.isfinite(float(value)) for value in (*values, params.bias_current_a)):
        raise ValueError("discriminator testbench values must be finite")
    if min(float(params.vdd), params.bias_current_a, float(params.ramp_time_s), float(params.period_s)) <= 0:
        raise ValueError("discriminator supply, bias current and times must be positive")
    low = float(params.threshold_v) - (float(params.baseline_v) if float(params.overdrive_v) else float(params.ramp_v))
    high = float(params.threshold_v) + (float(params.overdrive_v) or float(params.ramp_v))
    if not 0 <= low < float(params.threshold_v) < high <= float(params.vdd) or float(params.overdrive_v) < 0:
        raise ValueError("the discriminator input must cross the threshold and stay between the rails")
    if not 0 < 4 * float(params.transition_time_s) < float(params.period_s):
        raise ValueError("the discriminator step needs short edges in its period")
    if params.waveform_sample_interval_s <= 0 or float(params.cload) < 0:
        raise ValueError("discriminator record interval must be positive and load not negative")


@h.generator
def DiscTb(params: DiscTbParams) -> h.Module:
    """Generate the discriminator testbench: the threshold on inn, the bias reference, the load,
    and on inp a slow triangle across the threshold or, with ``overdrive_v``, a step from below it
    up to the overdrive a quarter period in and back down three quarters in."""

    _validate_disc_tb_params(params)

    DiscTb, connections = testbench_from_ports(
        "DiscTb", {net.name: net for net in DiscNets.signals.values() if net.vis == h.Visibility.PORT}
    )
    disc, vss = params.disc, DiscTb.vss
    DiscTb.vvdd = Vdc(dc=params.vdd)(p=DiscTb.vdd, n=vss)
    DiscTb.vinn = Vdc(dc=params.threshold_v)(p=DiscTb.inn, n=vss)
    threshold = float(params.threshold_v)
    if float(params.overdrive_v):
        edge = float(params.transition_time_s)
        DiscTb.vinp = Vpulse(
            v1=threshold - float(params.baseline_v),
            v2=threshold + float(params.overdrive_v),
            delay=float(params.period_s) / 4,
            width=float(params.period_s) / 2 - edge,
            period=params.period_s,
            rise=edge,
            fall=edge,
        )(p=DiscTb.inp, n=vss)
    else:
        settle, ramp = _ramp_settle_s(params), float(params.ramp_time_s)
        DiscTb.vinp = Vpulse(
            v1=threshold - float(params.ramp_v),
            v2=threshold + float(params.ramp_v),
            delay=settle,
            rise=ramp,
            width=settle,
            fall=ramp,
            period=2 * stop_time_s(params),
        )(p=DiscTb.inp, n=vss)
    # the bias reference: a diode-connected copy of the tail and output current source, fed the
    # bias current from its own supply, so the discriminator's supply current is its own
    DiscTb.vddb = h.Signal()
    DiscTb.vvddb = Vdc(dc=params.vdd)(p=DiscTb.vddb, n=vss)
    size = {"vth": disc.vth, "w": disc.tail_w, "l": disc.tail_l}
    if disc.input_xtors == MosType.NMOS:
        DiscTb.mbias = _mos(tp=MosType.NMOS, **size)(d=DiscTb.vbias, g=DiscTb.vbias, s=vss, b=vss)
        DiscTb.ibias = Idc(dc=params.bias_current_a)(p=DiscTb.vddb, n=DiscTb.vbias)
    else:
        DiscTb.mbias = _mos(tp=MosType.PMOS, **size)(d=DiscTb.vbias, g=DiscTb.vbias, s=DiscTb.vddb, b=DiscTb.vddb)
        DiscTb.ibias = Idc(dc=params.bias_current_a)(p=DiscTb.vbias, n=vss)
    if float(params.cload):
        DiscTb.cload = C(c=params.cload)(p=DiscTb.out, n=vss)
    DiscTb.dut = Disc(disc)(**connections)
    return DiscTb


def _run_disc_sim(run_dir: Path, params: DiscTbParams, *, check: bool = False) -> Path:
    """Run one discriminator transient in its PDK and return its raw file (``check``: Spectre's
    static checks besides)."""

    pdk = importlib.import_module(f"pdk.{params.pdk}")
    install = importlib.import_module(f"pdk.{params.pdk}.hdl21.site").install

    run_dir.mkdir(parents=True, exist_ok=True)
    h.pdk.set_default(pdk.pdk_logic)
    tb = DiscTb(params)
    h.pdk.compile(tb)
    interval = params.waveform_sample_interval_s
    attrs = [
        install.include(h.pdk.Corner.TYP),
        # what else the PDK's simulations take, in this order: TSMC's pre-simulation settings,
        # the device names its netlists use (pdk/<name>/hdl21)
        *(getattr(install, name)() for name in ("include_pre_simulation", "include_devices") if hasattr(install, name)),
        hs.Options(name="temp", value=25.0),
        hs.Options(name="save", value="selected"),
        hs.Save([raw for raw in disc_signal_names() if raw != "time"]),
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


# The characterization, in every PDK at its own core supply with the threshold at mid-supply: the
# slow triangle (100 mV either side of the threshold over 4 µs, 50 mV/µs: a 20 ns delay shifts a
# trip point by 1 mV) and steps from 100 mV below the threshold to 2–100 mV above it. The bias
# reference sets 2 µA; the output drives 10 fF.
OVERDRIVES_V = (2e-3, 5e-3, 10e-3, 20e-3, 50e-3, 100e-3)
THRESHOLD = 0.5


def disc_characterization(run_dir: Path, *, check: bool = False) -> Path:
    """Run every discriminator's triangle and steps in every PDK: 28 runs each.

    Each run writes ``<pdk>/<case>/<ramp|od<mV>>/result.h5`` (a ``MeasDisc``). ``check`` runs each
    case's 10 mV step with Spectre's checks instead, writing no measurement.
    """

    from flow.analysis.types import MeasInfo
    from flow.circuit.results import read_transient_wave
    from flow.comp.layout import PDKS
    from flow.disc.analysis import MeasDisc

    run_dir.mkdir(parents=True, exist_ok=True)
    jobs = {}
    for pdk in PDKS:
        supply = importlib.import_module(f"pdk.{pdk}.hdl21.site").install.supply_voltage(h.pdk.Corner.TYP)
        for case, disc in CASES.items():
            common = {"pdk": pdk, "disc": disc, "vdd": supply, "threshold_v": round(THRESHOLD * supply, 4)}
            for overdrive in (10e-3,) if check else OVERDRIVES_V:
                jobs[f"{pdk}/{case}/od{round(overdrive * 1e3)}"] = DiscTbParams(**common, overdrive_v=overdrive)
            if not check:
                jobs[f"{pdk}/{case}/ramp"] = DiscTbParams(**common, waveform_sample_interval_s=1e-9)
    names = disc_signal_names()
    failures: dict[str, str] = {}
    # one pool per PDK: hdl21 compiles each generated module in place, for the first PDK it meets
    for pdk in PDKS:
        with ProcessPoolExecutor(max_workers=16, mp_context=get_context("spawn")) as executor:
            futures = {
                executor.submit(_run_disc_sim, run_dir / name, params, check=check): (name, params)
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
                    measurement = MeasDisc(
                        group=None,
                        index=None,
                        dut=params.disc,
                        info=MeasInfo(
                            backend="spice",
                            timestamp_utc=datetime.fromtimestamp(raw_path.stat().st_mtime, tz=UTC),
                            instruments={"simulator": "Spectre"},
                            readbacks={
                                "pdk": name.split("/")[0],
                                "case": name.split("/")[1],
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
        raise RuntimeError(f"{len(failures)} discriminator points failed; see {failure_path}")
    return run_dir
