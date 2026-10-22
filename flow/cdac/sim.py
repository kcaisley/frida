"""CDAC testbench and its Spectre run, in every PDK.

Every stage switches alone, in its turn, as the SAR loop switches it: its P side's state rises and
its N side's falls at the start of its window (the differential top plate steps up), and back at
the start of the next (it steps down), every other stage held. Each window is long enough for the
slowest stage to settle in its first half, so its end is the step's final value; the stimulus and
the analysis (``flow.cdac.analysis``) share the window's timing.

Half an LSB of a 14-bit converter is tens of microvolts on steps of up to a volt: the transient
runs at a fixed step of a 2000th of the window and a tolerance of 1e-4, and its steps agree with
the capacitances' within 0.06 LSB. Tighter tolerances (1e-5 and 1e-6, conservative) move no
settling time by more than 1 ps in a 10- and a 14-bit array, at two to three times the run time.
"""

import importlib
import math
from datetime import UTC, datetime
from pathlib import Path

import hdl21 as h
import hdl21.sim as hs
import numpy as np
from hdl21.primitives import R, Vdc, Vpulse
from vlsirtools.spice import ResultFormat, SimError, SimOptions, SupportedSimulators

from flow.circuit.ports import testbench_from_ports

from .subckt import Cdac, CdacParams, cdac_ports

# each top plate's DC path in the testbench: to mid-supply, so slow that a window loses nothing
BLEED_OHM = 1e12
SAMPLES_PER_WINDOW = 2000
TOLERANCES = {"reltol": 1e-4, "vabstol": 1e-9, "iabstol": 1e-15}
ERRPRESET = "moderate"


def cdac_signal_names(stages: int) -> dict[str, str]:
    """Simulator saves and waveform names: both top plates, the P side's states and main bottom
    plates."""
    names = {"time": "time", "xtop.vdac_p": "vdac_p", "xtop.vdac_n": "vdac_n"}
    for stage in range(stages):
        names[f"xtop.dac_state_p_{stage}"] = f"dac_state_p[{stage}]"
        names[f"xtop.dac_botplate_p_{stage}"] = f"dac_botplate_p[{stage}]"
    return names


@h.paramclass
class CdacTbParams:
    """Parameters which determine the generated CDAC testbench."""

    dac = h.Param(dtype=CdacParams, desc="The CDAC")
    adc_bits = h.Param(dtype=int, desc="The converter's resolution: settling is to half its LSB")
    window_s = h.Param(dtype=float, desc="Each edge's window: a stage switches at its start, back at the next")
    waveform_sample_interval_s = h.Param(dtype=float, desc="Maximum raw step and stored waveform spacing")
    pdk = h.Param(dtype=str, desc="PDK the testbench compiles to and simulates in", default="tsmc65")
    vdd = h.Param(dtype=float, desc="Supply voltage, the DAC's reference", default=1.2)
    transition_time_s = h.Param(dtype=float, desc="Rise and fall time of the state steps", default=30e-12)


def window_start_s(params: CdacTbParams, stage: int, rising: bool) -> float:
    """When the stage's state starts to switch: up a window in, down the window after."""
    return (2 * stage + (1 if rising else 2)) * params.window_s


@h.generator
def CdacTb(params: CdacTbParams) -> h.Module:
    """Generate the CDAC testbench: each stage up and back down in its turn, both top plates bled to
    mid-supply."""

    stages = params.dac.driver.n_stages
    if params.window_s <= 4 * params.transition_time_s or params.waveform_sample_interval_s <= 0:
        raise ValueError("the CDAC testbench's window must hold its edges, and its sample interval be positive")
    CdacTb, connections = testbench_from_ports("CdacTb", cdac_ports(stages))
    vss, vdd, edge = CdacTb.vss, params.vdd, params.transition_time_s
    CdacTb.vcm = h.Signal()
    CdacTb.vvdd_dac = Vdc(dc=vdd)(p=CdacTb.vdd_dac, n=vss)
    CdacTb.vvcm = Vdc(dc=vdd / 2)(p=CdacTb.vcm, n=vss)
    # the main plates follow the states, the difference plates their complement
    CdacTb.vinvert = Vdc(dc=0.0)(p=CdacTb.dac_invert, n=vss)
    CdacTb.vdiffcaps = Vdc(dc=vdd)(p=CdacTb.dac_diffcaps, n=vss)
    for side in ("p", "n"):
        CdacTb.add(R(r=BLEED_OHM)(p=getattr(CdacTb, f"vdac_{side}"), n=CdacTb.vcm), name=f"rbleed_{side}")
    stop = (2 * stages + 1) * params.window_s
    for stage in range(stages):
        pulse = {
            "delay": window_start_s(params, stage, rising=True),
            "rise": edge,
            "fall": edge,
            "width": params.window_s - edge,
            "period": 2 * stop,
        }
        CdacTb.add(Vpulse(v1=0.0, v2=vdd, **pulse)(p=CdacTb.dac_state_p[stage], n=vss), name=f"vstate_p_{stage}")
        CdacTb.add(Vpulse(v1=vdd, v2=0.0, **pulse)(p=CdacTb.dac_state_n[stage], n=vss), name=f"vstate_n_{stage}")
    CdacTb.dut = Cdac(params.dac)(**connections)
    return CdacTb


def _run_cdac_sim(run_dir: Path, params: CdacTbParams) -> Path:
    """Run one CDAC testbench transient in its PDK and return its raw file."""

    pdk = importlib.import_module(f"pdk.{params.pdk}")
    install = importlib.import_module(f"pdk.{params.pdk}.hdl21.site").install

    run_dir.mkdir(parents=True, exist_ok=True)
    h.pdk.set_default(pdk.pdk_logic)
    tb = CdacTb(params)
    h.pdk.compile(tb)
    interval = params.waveform_sample_interval_s
    stages = params.dac.driver.n_stages
    attrs = [
        install.include(h.pdk.Corner.TYP),
        *(
            getattr(install, name)()
            for name in ("include_pre_simulation", "include_stdcell", "include_devices")
            if hasattr(install, name)
        ),
        hs.Options(name="temp", value=25.0),
        hs.Options(name="save", value="selected"),
        *(hs.Options(name=name, value=value) for name, value in TOLERANCES.items()),
        hs.Save([raw for raw in cdac_signal_names(stages) if raw != "time"]),
        hs.Tran(
            tstop=(2 * stages + 1) * params.window_s,
            name="tran",
            options={
                "strobeperiod": interval,
                "maxstep": interval,
                "strobeoutput": "strobeonly",
                "errpreset": ERRPRESET,
            },
        ),
    ]
    try:
        hs.Sim(tb=tb, attrs=attrs).run(
            SimOptions(
                simulator=SupportedSimulators.SPECTRE,
                fmt=ResultFormat.SIM_DATA,
                rundir=run_dir,
                simulator_args=("+escchars", "+log", "spectre.log"),
            )
        )
    except SimError as error:
        raise RuntimeError(f"Spectre failed in {run_dir}: {error}") from None
    return run_dir / "netlist.raw"


def measure(run_dir: Path, params: CdacTbParams):
    """One Spectre run of the testbench, as a ``MeasCdac`` keeping the top plates alone (its raw
    file removed)."""

    from flow.analysis.types import MeasInfo
    from flow.cdac.analysis import MeasCdac
    from flow.circuit.results import read_transient_wave

    raw = _run_cdac_sim(run_dir, params)
    interval = params.waveform_sample_interval_s
    wave, points = read_transient_wave(raw, cdac_signal_names(params.dac.driver.n_stages), interval, supply_rails=())
    measurement = MeasCdac(
        group=None,
        index=None,
        dut=params.dac,
        info=MeasInfo(
            backend="spice",
            timestamp_utc=datetime.fromtimestamp(raw.stat().st_mtime, tz=UTC),
            instruments={"simulator": "Spectre"},
            readbacks={"pdk": params.pdk, "raw_points": points, "waveform_sample_interval_s": interval},
        ),
        param=params,
        trial_index=np.arange(1, dtype=np.int64),
        wave=wave,
    )
    raw.unlink()
    return measurement


def top_plates(measurement):
    """The measurement with its top plates alone: what is kept of it."""

    import dataclasses

    from flow.analysis.types import Wave

    wave = measurement.wave
    kept = Wave(record_index=wave.record_index, time_s=wave.time_s, v={k: wave.v[k] for k in ("vdac_p", "vdac_n")})
    return dataclasses.replace(measurement, wave=kept)


def settling_window_s(pdk: str, dac: CdacParams, adc_bits: int, vdd: float) -> float:
    """A window the slowest stage settles in within its first half: twice each plate's driver
    delay and its RC settling to half an LSB from its plate's step (the drivers' characterization,
    ``flow.capdriver.model``, where it exists; else 10 kOhm over the weight and 1 ns), at least 1 ns,
    rounded up to 0.1 ns."""

    from flow.capdriver.model import CapDriverModel
    from flow.capdriver.subckt import stage_strengths
    from flow.cdac.analysis import full_scale_v

    load = sum(dac.main_f) + sum(dac.diff_f) + dac.parasitic_f
    tolerance = full_scale_v(dac, vdd) / 2**adc_bits  # half an LSB
    slowest = 0.0
    for strength, main, diff in zip(stage_strengths(dac.driver), dac.main_f, dac.diff_f, strict=True):
        for plate in (main, diff):
            if plate <= 0:
                continue
            try:
                driver = CapDriverModel.of(pdk, strength, load_f=plate, simulate=False)
                resistance, delay = driver.resistance_ohm, max(driver.delay_rise_s, driver.delay_fall_s)
            except (LookupError, RuntimeError):
                resistance, delay = 10e3 / strength, 1e-9
            tau = resistance * plate * (load - plate) / load
            slowest = max(slowest, delay + tau * math.log(max(2.0, 2 * vdd * plate / load / tolerance)))
    return math.ceil(max(1e-9, 2 * slowest) / 1e-10) * 1e-10
