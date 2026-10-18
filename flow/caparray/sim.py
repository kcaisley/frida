"""CDAC testbench and named Spectre simulation targets.

The bench drives every stage's main bottom plate with a code's bit and its diff plate with the
complement, into 100 fF on the top plate. The array's leaf is an ideal capacitor (the MOM
capacitor's ideal view, ``unit.py``), so the transient is the same in every PDK: it checks the
array's wiring and weights, not a PDK's capacitors.

``frida1_transfer_curve`` stays the TSMC65 FRIDA-1 reference; ``caparray_characterization``
compares named arrays in every PDK.
"""

import argparse
import importlib
import json
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import UTC, datetime
from multiprocessing import get_context
from pathlib import Path

import hdl21 as h
import hdl21.sim as hs
import numpy as np
from hdl21.prefix import f
from hdl21.primitives import C, Vpwl
from vlsirtools.spice import ResultFormat, SimError, SimOptions, SupportedSimulators

from flow.analysis.io import interpolate_wave_records, write_measurement
from flow.circuit.ports import testbench_from_ports

from .subckt import CapArray, CapArrayConfig, CapArrayParams, RedunStrat, get_caparray_weights


@h.paramclass
class CapArrayTbParams:
    """Parameters which determine the generated CDAC testbench."""

    pdk = h.Param(dtype=str, desc="PDK the testbench compiles to and simulates in", default="tsmc65")
    waveform_sample_interval_s = h.Param(
        dtype=float, desc="Maximum raw step and stored waveform spacing", default=100e-12
    )
    vdd = h.Param(dtype=h.Scalar, desc="Supply voltage", default=1.2)
    cdac = h.Param(dtype=CapArrayConfig, desc="CDAC parameters", default=CapArrayConfig())
    codes = h.Param(
        dtype=tuple[int, ...] | None,
        desc="Packed codes in order; None ramps every code of the DAC resolution",
        default=None,
    )
    code_dwell_s = h.Param(dtype=h.Scalar, desc="Time held at each input code", default=200e-9)
    transition_time_s = h.Param(dtype=h.Scalar, desc="Input-code transition time", default=100e-12)


@h.generator(enable_cache=False)
def CapArrayTb(params: CapArrayTbParams) -> h.Module:
    """Drive a passive main/differential array with complementary ideal waveforms."""

    if float(params.code_dwell_s) <= 0.0 or float(params.transition_time_s) <= 0.0:
        raise ValueError("CDAC dwell and transition times must be positive")
    n_stages = params.cdac.n_dac + params.cdac.n_extra

    array = CapArray(CapArrayParams(cdac=params.cdac))
    CapArrayTb, connections = testbench_from_ports(
        "CapArrayTb",
        {name: net for name, net in array.ports.items() if net is not array.cap_shieldplate},
    )
    connections[array.cap_shieldplate.name] = CapArrayTb.vss
    CapArrayTb.cload = C(c=100 * f)(p=CapArrayTb.cap_topplate, n=CapArrayTb.vss)
    CapArrayTb.dut = array(**connections)
    stage_values: list[list[h.Scalar]] = [[] for _ in range(n_stages)]
    for code in range(2**params.cdac.n_dac) if params.codes is None else params.codes:
        # Treat the integer only as a packed display stimulus: its highest
        # position is C0 and its lowest position is C15. With redundant stages,
        # this short baseline ramp therefore exercises the low-weight tail.
        for stage in range(n_stages):
            packed_bit = n_stages - stage - 1
            stage_values[stage].append(params.vdd if (code >> packed_bit) & 1 else 0.0)
    for stage, values in enumerate(stage_values):
        for kind, levels in (("main", values), ("diff", [params.vdd - value for value in values])):
            net = connections[f"cap_botplate_{kind}<{stage}>"]
            CapArrayTb.add(
                Vpwl(
                    wave=h.Pwl.steps(
                        values=levels,
                        dwell=params.code_dwell_s + params.transition_time_s,
                        transition=params.transition_time_s,
                        transition_at="end",
                    )
                )(p=net, n=CapArrayTb.vss),
                name=f"v{kind}_{stage}",
            )
    return CapArrayTb


def _run_caparray_sim(
    run_dir: Path, params: CapArrayTbParams, *, check: bool = False, threads: int = 1, save_all: bool = False
) -> Path:
    """Run one CDAC testbench transient in its PDK and return its raw file.

    It saves the top plate (``save_all``: every net). ``check`` adds Spectre's static and
    connectivity checks and runs the first code.
    """

    pdk = importlib.import_module(f"pdk.{params.pdk}")
    install = importlib.import_module(f"pdk.{params.pdk}.hdl21.site").install

    run_dir.mkdir(parents=True, exist_ok=True)
    h.pdk.set_default(pdk.pdk_logic)
    tb = CapArrayTb(params)
    h.pdk.compile(tb)
    n_codes = 2**params.cdac.n_dac if params.codes is None else len(params.codes)
    interval = params.waveform_sample_interval_s
    attrs = [
        install.include(h.pdk.Corner.TYP),
        # what else the PDK's simulations take, in this order: TSMC's pre-simulation settings,
        # the device names its netlists use (pdk/<name>/hdl21)
        *(getattr(install, name)() for name in ("include_pre_simulation", "include_devices") if hasattr(install, name)),
        hs.Options(name="temp", value=25.0),
        hs.Options(name="save", value="selected"),
        hs.Save(hs.SaveMode.ALL if save_all else ["xtop.cap_topplate"]),
    ]
    if check:
        attrs.append(
            h.Literal(
                "check_caps static_capacitor type=distr\n"
                "check_erc static_erc floatbulk=all floatgate=no_top_moscap dangle=no_top "
                "gate2power=on gate2ground=on\n"
                "check_highz static_highz node=[*] fanout=gate_has_driver_no_moscap\n"
                "check_dcpath static_dcpath net=[0]\n"
                "check_topology static_topology node=[*] pin2gnd=on\n"
                f"check_nodecap dyn_nodecap node=[xtop.cap_topplate] "
                f"time=[{float(params.code_dwell_s) / 2:g} {float(params.code_dwell_s):g}]"
            )
        )
    attrs.append(
        hs.Tran(
            tstop=(
                params.code_dwell_s + params.transition_time_s
                if check
                else n_codes * params.code_dwell_s + (n_codes - 1) * params.transition_time_s
            ),
            name="tran",
            options={"strobeperiod": interval, "strobeoutput": "strobeonly"},
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
                    f"+mt={threads}",
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


def frida1_transfer_curve(run_dir: Path, *, check: bool = False) -> Path:
    """Run the complete fabricated-size CDAC code ramp (TSMC65)."""

    _run_caparray_sim(run_dir, CapArrayTbParams(), check=check, threads=4, save_all=True)
    return run_dir


# The characterization's arrays: FRIDA-1's (16 stages, radix about 1.7, paired overlay), FRIDA's
# radix-2 tail on six repeated coarse units (radix 2.0 at the bottom), a plain 11-bit binary array,
# and an unpaired sub-radix-2 one. In every PDK at its own core supply: each stage toggled alone
# between all-zero codes (its weight), and the packed ramp over the DAC resolution's codes.
CASES = {
    "radix17": CapArrayConfig(),
    "radix20": CapArrayConfig(weights=(768, 512, 320, 192, 128, 64, 64, 64, 64, 64, 32, 16, 8, 4, 2, 1)),
    "binary": CapArrayConfig(n_extra=0, redun_strat=RedunStrat.RDX2),
    "subradix2": CapArrayConfig(redun_strat=RedunStrat.SUBRDX2),
}


def caparray_characterization(run_dir: Path, *, check: bool = False) -> Path:
    """Run every array's stage weights and code ramp, in every PDK.

    Each point writes ``<pdk>/<case>/<sweep>/result.h5`` (a ``MeasCapArrayTran``): ``stage``
    every stage toggled alone after an all-zero code, ``ramp`` every code of the DAC resolution.
    ``check`` runs each case's first stage step with Spectre's checks instead, writing no
    measurement.
    """

    from flow.analysis.types import MeasInfo, Wave
    from flow.caparray.analysis import MeasCapArrayTran
    from flow.circuit.results import read_raw_transient
    from flow.comp.layout import PDKS

    run_dir.mkdir(parents=True, exist_ok=True)
    jobs = {}
    for pdk in PDKS:
        supply = importlib.import_module(f"pdk.{pdk}.hdl21.site").install.supply_voltage(h.pdk.Corner.TYP)
        for case, cdac in CASES.items():
            n_stages = len(get_caparray_weights(cdac))
            # stage s is the packed code's bit n_stages - 1 - s; zero before each
            stage_codes = tuple(code for stage in range(n_stages) for code in (0, 1 << (n_stages - 1 - stage)))
            timing = {"pdk": pdk, "vdd": supply, "cdac": cdac, "transition_time_s": 50e-12}
            jobs[f"{pdk}/{case}/stage"] = CapArrayTbParams(
                codes=stage_codes, code_dwell_s=2e-9, waveform_sample_interval_s=10e-12, **timing
            )
            if not check:
                jobs[f"{pdk}/{case}/ramp"] = CapArrayTbParams(
                    code_dwell_s=1e-9, waveform_sample_interval_s=50e-12, **timing
                )
    failures: dict[str, str] = {}
    # one pool per PDK: hdl21 compiles each generated module in place, for the first PDK it meets
    for pdk in PDKS:
        with ProcessPoolExecutor(max_workers=16, mp_context=get_context("spawn")) as executor:
            futures = {
                executor.submit(_run_caparray_sim, run_dir / name, params, check=check): (name, params)
                for name, params in jobs.items()
                if params.pdk == pdk
            }
            for future in as_completed(futures):
                name, params = futures[future]
                try:
                    raw_path = future.result()
                    if check:
                        continue
                    result = read_raw_transient(raw_path)
                    times_s = np.asarray(result.data["time"])
                    interval = params.waveform_sample_interval_s
                    time_s, voltages = interpolate_wave_records(
                        times_s,
                        {"cap_topplate": result.data["xtop.cap_topplate"]},
                        [(float(times_s[0]), float(times_s[-1]))],
                        interval,
                    )
                    measurement = MeasCapArrayTran(
                        group=None,
                        index=None,
                        dut=params.cdac,
                        info=MeasInfo(
                            backend="spice",
                            timestamp_utc=datetime.fromtimestamp(raw_path.stat().st_mtime, tz=UTC),
                            instruments={"simulator": "Spectre"},
                            readbacks={
                                "pdk": name.split("/")[0],
                                "case": name.split("/")[1],
                                "sweep": name.split("/")[2],
                                "stage_weights_json": json.dumps(get_caparray_weights(params.cdac)),
                                "raw_file": raw_path.name,
                                "raw_points": len(times_s),
                                "waveform_sample_interval_s": interval,
                            },
                        ),
                        param=params,
                        trial_index=np.arange(1, dtype=np.int64),
                        wave=Wave(record_index=np.arange(1, dtype=np.int64), time_s=time_s, v=voltages, i={}),
                    )
                    write_measurement(raw_path.parent / "result.h5", measurement)
                except Exception as error:  # noqa: BLE001 - report every independent point failure
                    failures[name] = repr(error)
    if failures:
        failure_path = run_dir / "failures.json"
        failure_path.write_text(json.dumps(failures, indent=2) + "\n")
        raise RuntimeError(f"{len(failures)} capacitor-array points failed; see {failure_path}")
    return run_dir


def main() -> None:
    """Create one output directory and run one named CDAC target."""

    targets = {target.__name__: target for target in (caparray_characterization, frida1_transfer_curve)}
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("target", nargs="?", choices=sorted(targets))
    args = parser.parse_args()
    if args.target is None:
        print("Available capacitor-array simulation targets:")
        for name in sorted(targets):
            print(f"  {name}")
        return
    run_dir = (
        Path(__file__).resolve().parents[2]
        / "build"
        / "sim"
        / "caparray"
        / args.target
        / datetime.now().astimezone().strftime("%Y%m%d_%H%M%S")
    )
    run_dir.mkdir(parents=True, exist_ok=False)
    targets[args.target](run_dir)


if __name__ == "__main__":
    main()
