"""MOSFET testbench and named simulation targets, in Spectre and ngspice, in every PDK.

The device's source and body on ground and a source each on its drain and gate (a PMOS's at
negative voltages, so every sweep spans the same magnitudes). One simulator run per device gives:

- Id-Vgs at |Vds| of 50 mV (the linear region) and of the supply (saturation),
- Id-Vds at gate voltages from a third of the supply to all of it,
- at the bias (|Vgs| and |Vds| half the supply), the drain current's noise and its gate-referred
  voltage noise from 1 Hz to 10 GHz,
- Spectre only, at the bias: the drain current's transient noise (ngspice gives devices noise in
  its small-signal analyses alone), and over a Monte Carlo of mismatch, in a run of its own on the
  PDK's statistical sections where its kit has them.

Both simulators read the PDK's ``simulation_includes``, ngspice in HSPICE compatibility
(``ngbehavior=hsa``). A PDK whose decks ngspice cannot read runs in Spectre alone. The
testbench's ground is ``gnd``: a cell library's ``.GLOBAL VSS`` would make a ``VSS`` port a
global node of its own in ngspice.
"""

import argparse
import importlib
import io
import json
import subprocess
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import UTC, datetime
from multiprocessing import get_context
from pathlib import Path

import hdl21 as h
import hdl21.sim as hs
import numpy as np
from hdl21.primitives import MosType, Vdc
from vlsirtools.netlist.spectre import SpectreNetlister
from vlsirtools.netlist.spice import NgspiceNetlister

from flow.analysis.io import write_measurement

from .subckt import Mosfet, MosfetParams, cases

SIMULATORS = ("spectre", "ngspice")


@h.paramclass
class MosfetTbParams:
    """Parameters which determine the generated MOSFET testbench and its analyses."""

    pdk = h.Param(dtype=str, desc="PDK the testbench compiles to and simulates in", default="tsmc65")
    simulator = h.Param(dtype=str, desc='"spectre" or "ngspice"', default="spectre")
    mosfet = h.Param(dtype=MosfetParams, desc="Device parameters", default=MosfetParams())
    vdd = h.Param(dtype=float, desc="Full scale of every sweep: the PDK's core supply (V)", default=1.2)
    steps = h.Param(dtype=int, desc="Steps of each DC sweep", default=60)
    vds_lin = h.Param(dtype=float, desc="|Vds| of the linear-region Id-Vgs (V)", default=0.05)
    family = h.Param(
        dtype=tuple[float, ...],
        desc="|Vgs| of the Id-Vds curves, in fractions of vdd",
        default=(2 / 6, 0.5, 4 / 6, 5 / 6, 1.0),
    )
    bias = h.Param(
        dtype=float, desc="|Vgs| and |Vds| of the noise and mismatch bias, in a fraction of vdd", default=0.5
    )
    mc_runs = h.Param(dtype=int, desc="Monte Carlo runs of mismatch (Spectre)", default=200)
    trannoise_stop_s = h.Param(dtype=float, desc="Transient noise record (Spectre)", default=10e-6)
    trannoise_fmax_hz = h.Param(dtype=float, desc="Transient noise bandwidth (Spectre)", default=1e9)


def polarity(params: MosfetTbParams) -> float:
    """+1 for an NMOS, -1 for a PMOS: the sign of its terminal voltages and drain current."""
    return 1.0 if params.mosfet.tp == MosType.NMOS else -1.0


@h.generator
def MosfetTb(params: MosfetTbParams) -> h.Module:
    """The device between its drain and gate sources, both at the bias; source and body on ``gnd``."""

    if params.simulator not in SIMULATORS:
        raise ValueError(f"MOSFET testbench simulator must be one of {SIMULATORS}")
    if not 0 < params.bias <= 1 or params.steps < 2 or not params.family:
        raise ValueError("MOSFET testbench bias must lie in (0, 1], with two steps and one family curve at least")
    MosfetTb = h.Module(name="MosfetTb")
    MosfetTb.gnd = h.Port()
    MosfetTb.d, MosfetTb.g = h.Signal(), h.Signal()
    bias = round(polarity(params) * params.bias * params.vdd, 6)
    MosfetTb.vd = Vdc(dc=bias)(p=MosfetTb.d, n=MosfetTb.gnd)
    MosfetTb.vg = Vdc(dc=bias, ac=1.0)(p=MosfetTb.g, n=MosfetTb.gnd)
    MosfetTb.dut = Mosfet(params.mosfet)(d=MosfetTb.d, g=MosfetTb.g, s=MosfetTb.gnd, b=MosfetTb.gnd)
    return MosfetTb


def _spectre_analyses(params: MosfetTbParams, *, mismatch: bool) -> str:
    """Spectre's statements: the sweeps, noise and transient noise, or the Monte Carlo alone."""

    s, vdd, n = polarity(params), params.vdd, params.steps
    bias = round(s * params.bias * vdd, 6)
    if mismatch:
        return (
            f"mc montecarlo numruns={params.mc_runs} seed=1 variations=mismatch savefamilyplots=yes {{\n  mcop dc\n}}\n"
        )
    family = " ".join(str(round(s * f * vdd, 6)) for f in params.family)
    period = 0.5 / params.trannoise_fmax_hz
    return "\n".join(
        (
            f"set_lin alter dev=xtop.vd param=dc value={s * params.vds_lin}",
            f"idvg_lin dc dev=xtop.vg param=dc start=0 stop={s * vdd} lin={n}",
            f"set_sat alter dev=xtop.vd param=dc value={s * vdd}",
            f"idvg_sat dc dev=xtop.vg param=dc start=0 stop={s * vdd} lin={n}",
            f"idvd sweep dev=xtop.vg param=dc values=[{family}] {{",
            f"  idvd_dc dc dev=xtop.vd param=dc start=0 stop={s * vdd} lin={n}",
            "}",
            f"bias_d alter dev=xtop.vd param=dc value={bias}",
            f"bias_g alter dev=xtop.vg param=dc value={bias}",
            "noise (xtop.d 0) noise start=1 stop=1e10 dec=10 oprobe=xtop.vd iprobe=xtop.vg",
            (
                f"tnoise tran stop={params.trannoise_stop_s} noisefmax={params.trannoise_fmax_hz} "
                f"noisefmin={1 / params.trannoise_stop_s} noiseseed=1 strobeperiod={period} strobeoutput=strobeonly"
            ),
            "",
        )
    )


def _ngspice_control(params: MosfetTbParams) -> str:
    """ngspice's control block: noise first (its plots then are noise1 and noise2), then the
    sweeps, each written to a raw file of its own in the run directory."""

    s, vdd, n = polarity(params), params.vdd, params.steps
    sweep = f"0 {s * vdd} {s * vdd / n}"
    lines = [
        ".control",
        "noise v(nsense) v.xtop.vvg dec 10 1 1e10",
        "setplot noise1",
        "write noise.raw",
        f"alter v.xtop.vvd dc={s * params.vds_lin}",
        f"dc v.xtop.vvg {sweep}",
        "write idvg_lin.raw",
        f"alter v.xtop.vvd dc={s * vdd}",
        f"dc v.xtop.vvg {sweep}",
        "write idvg_sat.raw",
    ]
    for index, fraction in enumerate(params.family):
        lines += [
            f"alter v.xtop.vvg dc={round(s * fraction * vdd, 6)}",
            f"dc v.xtop.vvd {sweep}",
            f"write idvd_{index}.raw",
        ]
    return "\n".join([*lines, "quit 0", ".endc"])


def _run_mosfet_sim(run_dir: Path, params: MosfetTbParams, *, mismatch: bool = False) -> Path:
    """Netlist and run one device in its simulator (``mismatch``: the Monte Carlo alone, in
    Spectre); returns the run directory, which holds the simulator's raw output."""

    pdk = importlib.import_module(f"pdk.{params.pdk}")
    install = importlib.import_module(f"pdk.{params.pdk}.hdl21.site").install

    run_dir.mkdir(parents=True, exist_ok=True)
    h.pdk.set_default(pdk.pdk_logic)
    tb = MosfetTb(params)
    h.pdk.compile(tb)
    includes = install.simulation_includes(h.pdk.Corner.TYP, params.simulator, mismatch=mismatch)
    out = io.StringIO()
    if params.simulator == "spectre":
        attrs = [*includes, hs.Save(["xtop.vd:p"]), h.Literal(_spectre_analyses(params, mismatch=mismatch))]
        SpectreNetlister(out).write_sim_input(hs.to_proto(hs.Sim(tb=tb, attrs=attrs)))
        (run_dir / "netlist.scs").write_text(out.getvalue())
        command = ["spectre", "-64", "+escchars", "-format", "psfascii", "+log", "spectre.log", "netlist.scs"]
    else:
        # ngspice's noise output is a voltage: the drain source's current through a unit transresistance
        attrs = [*includes, h.Literal("hsense nsense 0 v.xtop.vvd 1"), h.Literal(_ngspice_control(params))]
        NgspiceNetlister(out).write_sim_input(hs.to_proto(hs.Sim(tb=tb, attrs=attrs)))
        (run_dir / "netlist.sp").write_text(out.getvalue())
        command = ["ngspice", "--no-spiceinit", "-D", "ngbehavior=hsa", "-b", "netlist.sp"]
    done = subprocess.run(command, cwd=run_dir, capture_output=True, text=True, timeout=3600, check=False)
    (run_dir / f"{params.simulator}.out").write_text(done.stdout + done.stderr)
    if done.returncode:
        tail = "\n".join((done.stdout + done.stderr).splitlines()[-12:])
        raise RuntimeError(f"{params.simulator} failed ({done.returncode}) in {run_dir}:\n{tail}")
    return run_dir


def _spectre_results(run_dir: Path, params: MosfetTbParams, *, mismatch: bool) -> dict:
    """The run's sweeps, noise and transient noise, or its Monte Carlo runs, as magnitudes."""

    from vlsirtools.spice.spectre import parse_psfascii

    s = polarity(params)
    analyses = {name: result.data for name, result in parse_psfascii(run_dir / "netlist.raw").items()}
    current = "xtop.vd:p"
    if mismatch:
        runs = sorted(name for name in analyses if name.startswith("mc-") and name.endswith("_mcop"))
        return {"mc_id_a": np.array([-s * float(np.real(analyses[name][current][0])) for name in runs])}
    family = sorted(name for name in analyses if name.startswith("idvd-") and name.endswith("_idvd_dc"))
    tran = analyses["tnoise"]
    return {
        "vgs_v": s * np.real(np.asarray(analyses["idvg_lin"]["dc"])),
        "id_lin_a": -s * np.real(np.asarray(analyses["idvg_lin"][current])),
        "id_sat_a": -s * np.real(np.asarray(analyses["idvg_sat"][current])),
        "vds_v": s * np.real(np.asarray(analyses[family[0]]["dc"])),
        "id_family_a": np.stack([-s * np.real(np.asarray(analyses[name][current])) for name in family], axis=1),
        "frequency_hz": np.real(np.asarray(analyses["noise"]["freq"])),
        "drain_noise_a_rthz": np.abs(np.asarray(analyses["noise"]["out"])),
        "gate_noise_v_rthz": np.abs(np.asarray(analyses["noise"]["in"])),
        "time_s": np.real(np.asarray(tran["time"])),
        "tran_id_a": -s * np.real(np.asarray(tran[current])),
    }


def _ngspice_results(run_dir: Path, params: MosfetTbParams) -> dict:
    """The run's sweeps and noise, as magnitudes (ngspice has no device transient noise)."""

    from vlsirtools.spice.ngspice import parse_nutbin

    s = polarity(params)

    def plot(name: str) -> dict:
        with (run_dir / f"{name}.raw").open("rb") as stream:
            return next(iter(parse_nutbin(stream).values())).data

    current = "i(v.xtop.vvd)"
    lin, sat, noise = plot("idvg_lin"), plot("idvg_sat"), plot("noise")
    family = [plot(f"idvd_{index}") for index in range(len(params.family))]
    return {
        "vgs_v": s * np.real(np.asarray(lin["v(v-sweep)"])),
        "id_lin_a": -s * np.real(np.asarray(lin[current])),
        "id_sat_a": -s * np.real(np.asarray(sat[current])),
        "vds_v": s * np.real(np.asarray(family[0]["v(v-sweep)"])),
        "id_family_a": np.stack([-s * np.real(np.asarray(curve[current])) for curve in family], axis=1),
        "frequency_hz": np.real(np.asarray(noise["frequency"])),
        "drain_noise_a_rthz": np.abs(np.asarray(noise["onoise_spectrum"])),
        "gate_noise_v_rthz": np.abs(np.asarray(noise["inoise_spectrum"])),
    }


def _write_measurements(run_dir: Path, params: MosfetTbParams, results: dict, readbacks: dict) -> None:
    """One file per kind of measurement in the run directory (``flow.mosfet.analysis``)."""

    from flow.analysis.types import MeasInfo
    from flow.mosfet.analysis import (
        MeasMosfetMismatch,
        MeasMosfetNoise,
        MeasMosfetOutput,
        MeasMosfetTranNoise,
        MeasMosfetTransfer,
    )

    info = MeasInfo(
        backend="spice",
        timestamp_utc=datetime.now(tz=UTC),
        instruments={"simulator": "Spectre" if params.simulator == "spectre" else "ngspice"},
        readbacks=readbacks,
    )
    common = {"group": None, "index": None, "dut": params.mosfet, "info": info, "param": params}
    kinds = {
        "transfer": (MeasMosfetTransfer, ("vgs_v", "id_lin_a", "id_sat_a")),
        "output": (MeasMosfetOutput, ("vds_v", "id_family_a")),
        "noise": (MeasMosfetNoise, ("frequency_hz", "drain_noise_a_rthz", "gate_noise_v_rthz")),
        "trannoise": (MeasMosfetTranNoise, ("time_s", "tran_id_a")),
        "mismatch": (MeasMosfetMismatch, ("mc_id_a",)),
    }
    for kind, (meas_type, keys) in kinds.items():
        if all(key in results for key in keys):
            fields = {key.removeprefix("tran_").removeprefix("mc_"): results[key] for key in keys}
            write_measurement(run_dir / f"{kind}.h5", meas_type(**common, **fields))


def readbacks(params: MosfetTbParams, case: str) -> dict:
    """What a run records besides its measurements: its PDK, simulator and case, and the device's
    drawn width and length (its unit widths and minimum lengths made physical)."""

    sizes = importlib.import_module(f"pdk.{params.pdk}.hdl21.primitives.prim_dicts").default_xtor_size
    device = case.rsplit("_l", 1)[0]
    w0, l0 = (float(size) for size in sizes[device])
    return {
        "pdk": params.pdk,
        "simulator": params.simulator,
        "case": case,
        "device": device,
        "w_m": params.mosfet.w * w0,
        "l_m": params.mosfet.l * l0,
    }


def _characterize(run_dir: Path, params: MosfetTbParams, readbacks: dict) -> Path:
    """Run one device in its simulator (and, in Spectre, its Monte Carlo where the PDK has mismatch
    statistics) and write its measurements."""

    install = importlib.import_module(f"pdk.{params.pdk}.hdl21.site").install
    _run_mosfet_sim(run_dir, params)
    if params.simulator == "spectre":
        results = _spectre_results(run_dir, params, mismatch=False)
        try:
            install.simulation_includes(h.pdk.Corner.TYP, "spectre", mismatch=True)
        except NotImplementedError as reason:
            readbacks = {**readbacks, "mismatch": f"none: {reason}"}
        else:
            _run_mosfet_sim(run_dir / "mismatch", params, mismatch=True)
            results |= _spectre_results(run_dir / "mismatch", params, mismatch=True)
    else:
        results = _ngspice_results(run_dir, params)
    _write_measurements(run_dir, params, results, readbacks)
    return run_dir


def mosfet_characterization(run_dir: Path) -> Path:
    """Run every core device of every PDK at each length, in Spectre and, where the PDK's decks
    allow, ngspice: ``<pdk>/<simulator>/<case>/{transfer,output,noise,trannoise,mismatch}.h5``."""

    from flow.comp.layout import PDKS

    run_dir.mkdir(parents=True, exist_ok=True)
    jobs = {}
    for pdk in PDKS:
        install = importlib.import_module(f"pdk.{pdk}.hdl21.site").install
        vdd = install.supply_voltage(h.pdk.Corner.TYP)
        for simulator in SIMULATORS:
            try:
                install.simulation_includes(h.pdk.Corner.TYP, simulator)
            except NotImplementedError:
                continue
            for case, mosfet in cases(pdk).items():
                params = MosfetTbParams(pdk=pdk, simulator=simulator, mosfet=mosfet, vdd=vdd)
                jobs[f"{pdk}/{simulator}/{case}"] = params
    failures: dict[str, str] = {}
    # one pool per PDK: hdl21 compiles each generated module in place, for the first PDK it meets
    for pdk in PDKS:
        with ProcessPoolExecutor(max_workers=24, mp_context=get_context("spawn")) as executor:
            futures = {
                executor.submit(_characterize, run_dir / name, params, readbacks(params, name.split("/")[2])): name
                for name, params in jobs.items()
                if params.pdk == pdk
            }
            for future in as_completed(futures):
                try:
                    future.result()
                except Exception as error:  # noqa: BLE001 - report every independent device failure
                    failures[futures[future]] = repr(error)
    if failures:
        failure_path = run_dir / "failures.json"
        failure_path.write_text(json.dumps(failures, indent=2) + "\n")
        raise RuntimeError(f"{len(failures)} MOSFET runs failed; see {failure_path}")
    return run_dir


def main() -> None:
    """Create one output directory and run one named MOSFET target (Spectre from the Cadence
    environment, ngspice from the PATH)."""

    targets = {target.__name__: target for target in (mosfet_characterization,)}
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("target", nargs="?", choices=sorted(targets))
    args = parser.parse_args()
    if args.target is None:
        print("Available MOSFET simulation targets:")
        for name in sorted(targets):
            print(f"  {name}")
        return
    run_dir = (
        Path(__file__).resolve().parents[2]
        / "build"
        / "sim"
        / "mosfet"
        / args.target
        / datetime.now().astimezone().strftime("%Y%m%d_%H%M%S")
    )
    run_dir.mkdir(parents=True, exist_ok=False)
    targets[args.target](run_dir)


if __name__ == "__main__":
    main()
