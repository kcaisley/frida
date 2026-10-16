"""Follower testbench and named TSMC65 Spectre simulation targets."""

import argparse
import math
from datetime import datetime
from pathlib import Path

import hdl21 as h
import hdl21.sim as hs
from hdl21.prefix import f
from hdl21.primitives import C, Vdc
from vlsirtools.spice import ResultFormat, SimOptions, SupportedSimulators

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
    cload = h.Param(dtype=h.Prefixed, desc="Load capacitance on vout", default=100 * f)
    vin = h.Param(dtype=h.Scalar, desc="Input DC voltage", default=0.9)
    vbn = h.Param(dtype=h.Scalar, desc="NMOS current-source bias", default=0.5)
    vbp = h.Param(dtype=h.Scalar, desc="PMOS current-source bias", default=0.7)


def _validate_follower_tb_params(params: FollowerTbParams) -> None:
    values = (params.vdd, params.cload, params.vin, params.vbn, params.vbp)
    if not all(math.isfinite(float(value)) for value in values):
        raise ValueError("follower testbench values must be finite")
    if float(params.vdd) <= 0 or float(params.cload) <= 0:
        raise ValueError("follower supply and load must be positive")
    if not all(0 <= float(v) <= float(params.vdd) for v in values[2:]):
        raise ValueError("follower input and bias voltages must lie between the rails")


@h.generator
def FollowerTb(params: FollowerTbParams) -> h.Module:
    """Generate a follower testbench: vin carries the AC stimulus on its DC level, fixed biases,
    a capacitive load."""

    _validate_follower_tb_params(params)

    FollowerTb, connections = testbench_from_ports(
        "FollowerTb", {net.name: net for net in FollowerNets.signals.values() if net.vis == h.Visibility.PORT}
    )
    vss = FollowerTb.vss
    FollowerTb.vvdd = Vdc(dc=params.vdd)(p=FollowerTb.vdd, n=vss)
    FollowerTb.vvin = Vdc(dc=params.vin, ac=1.0)(p=FollowerTb.vin, n=vss)
    FollowerTb.vvbn = Vdc(dc=params.vbn)(p=FollowerTb.vbn, n=vss)
    FollowerTb.vvbp = Vdc(dc=params.vbp)(p=FollowerTb.vbp, n=vss)
    FollowerTb.cload = C(c=params.cload)(p=FollowerTb.vout, n=vss)
    FollowerTb.dut = Follower(params.follower)(**connections)
    return FollowerTb


def _ac(run_dir: Path, params: FollowerTbParams, check: bool) -> Path:
    """Run the operating point and the AC response from 1 kHz to 100 GHz in TSMC65
    (``check``: ten points a decade fewer, with Spectre's static checks)."""

    from pdk import tsmc65
    from pdk.tsmc65.hdl21 import site

    run_dir.mkdir(parents=True, exist_ok=True)
    h.pdk.set_default(tsmc65.pdk_logic)
    tb = FollowerTb(params)
    h.pdk.compile(tb)
    simulation = hs.Sim(
        tb=tb,
        attrs=[
            site.install.include(h.pdk.Corner.TYP),
            site.install.include_pre_simulation(),
            hs.Options(name="temp", value=25.0),
            hs.Options(name="save", value="selected"),
            hs.Save([raw for raw in follower_signal_names() if raw != "freq"]),
            *(
                [
                    h.Literal(
                        "check_erc static_erc floatbulk=all floatgate=no_top_moscap dangle=no_top "
                        "gate2power=on gate2ground=on\n"
                        "check_dcpath static_dcpath net=[xtop.vdd 0]"
                    ),
                ]
                if check
                else []
            ),
            hs.Op(name="op"),
            hs.Ac(sweep=hs.LogSweep(start=1e3, stop=1e11, npts=8 if check else 80), name="ac"),
        ],
    )
    simulation.run(
        SimOptions(
            simulator=SupportedSimulators.SPECTRE,
            fmt=ResultFormat.NONE if check else ResultFormat.SIM_DATA,
            rundir=run_dir,
            simulator_args=(
                "+preset=mx",
                "+mt=4",
                "+lqtimeout",
                "3600",
                "+escchars",
                "+log",
                "spectre.log",
                *(("-ahdllint=warn", "-ahdllint_log", "ahdllint.log") if check else ()),
            ),
        )
    )
    return run_dir


def flipped_ac(run_dir: Path, *, check: bool = False) -> Path:
    """AC response of the NMOS flipped voltage follower (vin 0.6 V: its current source needs headroom)."""

    return _ac(run_dir, FollowerTbParams(follower=CASES["flipped"], vin=0.6), check)


def source_ac(run_dir: Path, *, check: bool = False) -> Path:
    """AC response of the NMOS source follower."""

    return _ac(run_dir, FollowerTbParams(follower=CASES["source"]), check)


def main() -> None:
    """Create one output directory and run one named follower target."""

    targets = {target.__name__: target for target in (flipped_ac, source_ac)}
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
