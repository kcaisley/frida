"""MOS capacitor testbench and named TSMC65 Spectre simulation targets."""

import argparse
import math
from datetime import datetime
from pathlib import Path

import hdl21 as h
import hdl21.sim as hs
from hdl21.primitives import Vdc
from vlsirtools.spice import ResultFormat, SimOptions, SupportedSimulators

from flow.circuit.ports import testbench_from_ports

from .subckt import CASES, Mode, MosCap, MosCapNets, MosCapParams


def moscap_signal_names() -> dict[str, str]:
    """Derive simulator saves and waveform names from the block's net bundle: the currents of the
    sources on vdd and on top, from which the capacitance follows."""
    names = {"freq": "freq"}
    for net in MosCapNets.signals.values():
        if net.vis == h.Visibility.PORT and net.usage not in (h.Usage.POWER, h.Usage.GROUND):
            names[f"xtop.{net.name}"] = net.name
            names[f"xtop.v{net.name}:p"] = f"i({net.name})"
        if net.usage == h.Usage.POWER:
            names[f"xtop.v{net.name}:p"] = f"i({net.name})"
    return names


@h.paramclass
class MosCapTbParams:
    """Parameters which determine the generated MOS capacitor testbench."""

    vdd = h.Param(dtype=h.Scalar, desc="Supply voltage", default=1.2)
    moscap = h.Param(dtype=MosCapParams, desc="Capacitor parameters", default=MosCapParams())
    vtop = h.Param(dtype=h.Scalar, desc="Gate-plate DC voltage (two-net capacitor)", default=1.2)
    vbot = h.Param(dtype=h.Scalar, desc="Channel-plate DC voltage (two-net capacitor)", default=0.0)


def _validate_moscap_tb_params(params: MosCapTbParams) -> None:
    values = (params.vdd, params.vtop, params.vbot)
    if not all(math.isfinite(float(value)) for value in values):
        raise ValueError("MOS capacitor testbench values must be finite")
    if float(params.vdd) <= 0:
        raise ValueError("MOS capacitor supply must be positive")


@h.generator
def MosCapTb(params: MosCapTbParams) -> h.Module:
    """Generate a MOS capacitor testbench: the AC stimulus on vdd (a decap) or on top (a two-net
    capacitor) at its DC level; the stimulated source's current gives the capacitance."""

    _validate_moscap_tb_params(params)

    MosCapTb, connections = testbench_from_ports(
        "MosCapTb", {net.name: net for net in MosCapNets.signals.values() if net.vis == h.Visibility.PORT}
    )
    decap = params.moscap.mode == Mode.DECAP
    vss = MosCapTb.vss
    MosCapTb.vvdd = Vdc(dc=params.vdd, ac=1.0 if decap else 0.0)(p=MosCapTb.vdd, n=vss)
    MosCapTb.vtop = Vdc(dc=params.vtop, ac=0.0 if decap else 1.0)(p=MosCapTb.top, n=vss)
    MosCapTb.vbot = Vdc(dc=params.vbot)(p=MosCapTb.bot, n=vss)
    MosCapTb.dut = MosCap(params.moscap)(**connections)
    return MosCapTb


def _ac(run_dir: Path, params: MosCapTbParams, check: bool) -> Path:
    """Run the AC response from 1 MHz to 10 GHz in TSMC65 (``check``: a few points, with Spectre's
    static checks); the capacitance is the stimulated source's current over 2 pi f."""

    from pdk import tsmc65
    from pdk.tsmc65.hdl21 import site

    run_dir.mkdir(parents=True, exist_ok=True)
    h.pdk.set_default(tsmc65.pdk_logic)
    tb = MosCapTb(params)
    h.pdk.compile(tb)
    simulation = hs.Sim(
        tb=tb,
        attrs=[
            site.install.include(h.pdk.Corner.TYP),
            site.install.include_pre_simulation(),
            hs.Options(name="temp", value=25.0),
            hs.Options(name="save", value="selected"),
            hs.Save([raw for raw in moscap_signal_names() if raw != "freq"]),
            *([h.Literal("check_erc static_erc floatbulk=all floatgate=no_top_moscap dangle=no_top")] if check else []),
            hs.Ac(sweep=hs.LogSweep(start=1e6, stop=1e10, npts=4 if check else 40), name="ac"),
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


def cap_n_ac(run_dir: Path, *, check: bool = False) -> Path:
    """AC capacitance of the two-unit NMOS two-net capacitor, its gate plate at vdd."""

    return _ac(run_dir, MosCapTbParams(moscap=CASES["cap_n"]), check)


def decap_np_ac(run_dir: Path, *, check: bool = False) -> Path:
    """AC capacitance between the rails of the complementary decap."""

    return _ac(run_dir, MosCapTbParams(moscap=CASES["decap_np"]), check)


def main() -> None:
    """Create one output directory and run one named MOS capacitor target."""

    targets = {target.__name__: target for target in (cap_n_ac, decap_np_ac)}
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("target", nargs="?", choices=sorted(targets))
    args = parser.parse_args()
    if args.target is None:
        print("Available MOS capacitor simulation targets:")
        for name in sorted(targets):
            print(f"  {name}")
        return
    run_dir = (
        Path(__file__).resolve().parents[2]
        / "build"
        / "sim"
        / "moscap"
        / args.target
        / datetime.now().astimezone().strftime("%Y%m%d_%H%M%S")
    )
    run_dir.mkdir(parents=True, exist_ok=False)
    targets[args.target](run_dir)


if __name__ == "__main__":
    main()
