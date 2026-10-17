"""Follower testbench and named TSMC65 Spectre simulation targets.

The testbench follows Usb2Phy's ``UnityGainTb``: the input a DC level carrying a 1 V AC
stimulus, fixed biases, a capacitive load, an operating point and the AC response. The same
bench can instead put its AC stimulus on a test current into the output (1 V through a large
resistor), whose response is the output impedance, where a flipped follower differs from a plain one.
"""

import argparse
import json
import math
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import UTC, datetime
from multiprocessing import get_context
from pathlib import Path

import hdl21 as h
import hdl21.sim as hs
import numpy as np
from hdl21.primitives import C, R, Vdc
from vlsirtools.spice import ResultFormat, SimOptions, SupportedSimulators

from flow.analysis.io import write_measurement
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

    vdd = h.Param(dtype=h.Scalar, desc="Supply voltage", default=1.2)
    follower = h.Param(dtype=FollowerParams, desc="Follower parameters", default=FollowerParams())
    cload = h.Param(dtype=h.Scalar, desc="Load capacitance on vout (F)", default=100e-15)
    vin = h.Param(dtype=h.Scalar, desc="Input DC voltage", default=0.9)
    vbn = h.Param(dtype=h.Scalar, desc="NMOS current-source bias", default=0.5)
    vbp = h.Param(dtype=h.Scalar, desc="PMOS current-source bias", default=0.7)
    output_test = h.Param(dtype=bool, desc="AC stimulus on a test current into vout, not on vin", default=False)
    test_resistance_ohm = h.Param(dtype=float, desc="Series resistance of the output test current", default=1e6)
    fstart_hz = h.Param(dtype=float, desc="AC sweep start", default=1e3)
    fstop_hz = h.Param(dtype=float, desc="AC sweep stop", default=1e11)
    points_per_decade = h.Param(dtype=int, desc="AC points per decade", default=20)


def _validate_follower_tb_params(params: FollowerTbParams) -> None:
    values = (params.vdd, params.cload, params.vin, params.vbn, params.vbp)
    if not all(math.isfinite(float(value)) for value in values):
        raise ValueError("follower testbench values must be finite")
    if float(params.vdd) <= 0 or float(params.cload) <= 0:
        raise ValueError("follower supply and load must be positive")
    if not all(0 <= float(v) <= float(params.vdd) for v in values[2:]):
        raise ValueError("follower input and bias voltages must lie between the rails")
    if not 0 < params.fstart_hz < params.fstop_hz or params.points_per_decade < 1:
        raise ValueError("follower frequency sweep must rise from a positive start")


@h.generator
def FollowerTb(params: FollowerTbParams) -> h.Module:
    """Generate the follower testbench (Usb2Phy ``UnityGainTb``): vin a DC level with the AC
    stimulus, fixed biases, a capacitive load; or the AC stimulus as a test current into vout."""

    _validate_follower_tb_params(params)

    FollowerTb, connections = testbench_from_ports(
        "FollowerTb", {net.name: net for net in FollowerNets.signals.values() if net.vis == h.Visibility.PORT}
    )
    vss = FollowerTb.vss
    FollowerTb.vvdd = Vdc(dc=params.vdd)(p=FollowerTb.vdd, n=vss)
    FollowerTb.vvin = Vdc(dc=params.vin, ac=0.0 if params.output_test else 1.0)(p=FollowerTb.vin, n=vss)
    FollowerTb.vvbn = Vdc(dc=params.vbn)(p=FollowerTb.vbn, n=vss)
    FollowerTb.vvbp = Vdc(dc=params.vbp)(p=FollowerTb.vbp, n=vss)
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
    """Run the operating point and AC response of one follower in TSMC65 and return the raw file
    (``check``: two points a decade, with Spectre's static checks)."""

    from pdk import tsmc65
    from pdk.tsmc65.hdl21 import site

    run_dir.mkdir(parents=True, exist_ok=True)
    h.pdk.set_default(tsmc65.pdk_logic)
    tb = FollowerTb(params)
    h.pdk.compile(tb)
    decades = math.log10(params.fstop_hz / params.fstart_hz)
    attrs = [
        site.install.include(h.pdk.Corner.TYP),
        site.install.include_pre_simulation(),
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
    attrs += [
        hs.Op(name="op"),
        hs.Ac(
            sweep=hs.LogSweep(
                start=params.fstart_hz,
                stop=params.fstop_hz,
                npts=round(decades * (2 if check else params.points_per_decade)) + 1,
            ),
            name="ac",
        ),
    ]
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
    return run_dir / "netlist.raw"


# The characterization: the input level across TSMC65's 1.2 V supply, each point with the AC
# stimulus on the input (gain, bandwidth) and on an output test current (output impedance).
VIN_SWEEP_V = tuple(round(0.05 * step, 3) for step in range(25))
NOMINAL_VIN_V = {"source": 0.9, "source_pmos": 0.3, "flipped": 0.6, "flipped_pmos": 0.3}


def follower_characterization(run_dir: Path, *, check: bool = False) -> Path:
    """Run every follower over its input level, with the AC on the input and on the output: 200 runs.

    Each point writes ``<case>/<input|output>/vin<mV>/result.h5`` (a ``MeasFollower``). ``check``
    runs the nominal input of each case with Spectre's checks instead, writing no measurement.
    """

    from vlsirtools.spice.spectre import parse_nutbin

    from flow.analysis.types import MeasInfo
    from flow.follower.analysis import MeasFollower

    run_dir.mkdir(parents=True, exist_ok=True)
    jobs = {
        f"{case}/{'output' if output_test else 'input'}/vin{round(vin * 1e3)}": FollowerTbParams(
            follower=follower, vin=vin, output_test=output_test
        )
        for case, follower in CASES.items()
        for vin in ((NOMINAL_VIN_V[case],) if check else VIN_SWEEP_V)
        for output_test in ((False,) if check else (False, True))
    }
    failures: dict[str, str] = {}
    with ProcessPoolExecutor(max_workers=16, mp_context=get_context("spawn")) as executor:
        futures = {
            executor.submit(_run_follower_sim, run_dir / name, params, check=check): (name, params)
            for name, params in jobs.items()
        }
        for future in as_completed(futures):
            name, params = futures[future]
            try:
                raw_path = future.result()
                if check:
                    continue
                with raw_path.open("rb") as stream:
                    analyses = parse_nutbin(stream)
                op, ac = analyses["op"].data, analyses["ac"].data
                # the output per volt of input; or the output impedance, from the divider of the test
                # resistance and the impedance that the 1 V test stimulus drives
                response = np.asarray(ac["xtop.vout"])
                if params.output_test:
                    response = response * params.test_resistance_ohm / (1 - response)
                measurement = MeasFollower(
                    group=None,
                    index=None,
                    dut=params.follower,
                    info=MeasInfo(
                        backend="spice",
                        timestamp_utc=datetime.fromtimestamp(raw_path.stat().st_mtime, tz=UTC),
                        instruments={"simulator": "Spectre"},
                        readbacks={
                            "case": name.split("/")[0],
                            "stimulus": name.split("/")[1],
                            "raw_file": raw_path.name,
                            "supply_current_convention": "positive_current_draw",
                            "op_supply_current_a": -float(np.real(op["xtop.vvdd:p"][0])),
                            "op_vout_v": float(np.real(op["xtop.vout"][0])),
                        },
                    ),
                    param=params,
                    frequency_hz=np.real(np.asarray(ac["freq"])).astype(np.float64),
                    magnitude=np.abs(response).astype(np.float64),
                    phase_deg=np.degrees(np.unwrap(np.angle(response))).astype(np.float64),
                )
                write_measurement(raw_path.parent / "result.h5", measurement)
            except Exception as error:  # noqa: BLE001 - report every independent point failure
                failures[name] = repr(error)
    if failures:
        failure_path = run_dir / "failures.json"
        failure_path.write_text(json.dumps(failures, indent=2) + "\n")
        raise RuntimeError(f"{len(failures)} follower points failed; see {failure_path}")
    return run_dir


def main() -> None:
    """Create one output directory and run one named follower target."""

    targets = {target.__name__: target for target in (follower_characterization,)}
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("target", nargs="?", choices=sorted(targets))
    args = parser.parse_args()
    if args.target is None:
        print("Available follower simulation targets:")
        for name in sorted(targets):
            print(f"  {name}")
        return
    run_dir = (
        Path(__file__).resolve().parents[2]
        / "build"
        / "sim"
        / "follower"
        / args.target
        / datetime.now().astimezone().strftime("%Y%m%d_%H%M%S")
    )
    run_dir.mkdir(parents=True, exist_ok=False)
    targets[args.target](run_dir)


if __name__ == "__main__":
    main()
