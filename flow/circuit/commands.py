"""Shared argument parsing for module-level FRIDA commands."""

from __future__ import annotations

import argparse
import logging
import shutil
import socket
from collections.abc import Callable
from pathlib import Path

from vlsirtools.spice import ResultFormat, SimOptions, SupportedSimulators

from flow.pdks import list_pdks, set_pdk

SIM_HOSTS = {"jupiter", "juno", "asiclab003"}
SIMULATOR_BINARIES = {
    "spectre": ("spectre",),
    "ngspice": ("ngspice",),
    "xyce": ("Xyce", "xyce"),
}


def primitive_main(
    module_name: str,
    run_layout: Callable[[str, str, bool, Path], None],
) -> None:
    """Parse module-level primitive options and run its layout sweep."""
    parser = argparse.ArgumentParser(
        prog=f"python -m {module_name}",
        description=f"Generate {module_name.split('.')[-2]} layout primitives",
    )
    parser.add_argument("-t", "--tech", default="ihp130", choices=list_pdks(), help="Target PDK technology")
    parser.add_argument(
        "-m", "--mode", default="min", choices=["min", "max"], help="min: default only; max: full sweep"
    )
    parser.add_argument("-v", "--visual", action="store_true", help="Render the generated GDS")
    parser.add_argument("-o", "--out", default="build", type=Path, help="Output directory")
    args = parser.parse_args()

    set_pdk(args.tech)
    args.out.mkdir(parents=True, exist_ok=True)
    run_layout(args.tech, args.mode, args.visual, args.out)


def testbench_main(
    module_name: str,
    block: str,
    run_netlist: Callable[..., None],
    run_simulate: Callable[..., None],
) -> None:
    """Parse module-level netlist or simulation options for one testbench."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - [%(levelname)s] (%(threadName)s) %(message)s",
    )
    parser = argparse.ArgumentParser(
        prog=f"python -m {module_name}",
        description=f"Generate and simulate the {block} testbench",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    netlist = subparsers.add_parser("netlist", help="Generate netlists")
    _add_common_testbench_options(netlist, default_mode="max")
    netlist.add_argument(
        "-f",
        "--fmt",
        default="spectre",
        choices=["spectre", "ngspice", "verilog"],
        help="Netlist output format",
    )
    netlist.add_argument(
        "--scope",
        default="full",
        choices=["dut", "stim", "full"],
        help="dut: subcircuits only; stim: testbench and sources; full: complete simulator input",
    )

    simulate = subparsers.add_parser("simulate", help="Run SPICE simulations")
    _add_common_testbench_options(simulate, default_mode="min")
    simulate.add_argument(
        "-s",
        "--simulator",
        default="spectre",
        choices=["spectre", "ngspice", "xyce"],
        help="SPICE simulator backend",
    )
    args = parser.parse_args()
    set_pdk(args.tech)
    args.out.mkdir(parents=True, exist_ok=True)

    if args.command == "netlist":
        if args.scope != "dut" and args.fmt == "verilog":
            parser.error(f"--fmt={args.fmt} only supports --scope=dut")
        if args.montecarlo and args.scope != "full":
            parser.error("--montecarlo requires --scope=full")
        outdir = args.out / block
        outdir.mkdir(parents=True, exist_ok=True)
        run_netlist(
            tech=args.tech,
            mode=args.mode,
            montecarlo=args.montecarlo,
            fmt=args.fmt,
            scope=args.scope,
            outdir=outdir,
            verbose=True,
        )
        return

    _check_simulator(args.simulator)
    run_simulate(
        tech=args.tech,
        mode=args.mode,
        montecarlo=args.montecarlo,
        simulator=args.simulator,
        sim_options=SimOptions(
            rundir=args.out,
            fmt=ResultFormat.SIM_DATA,
            simulator=SupportedSimulators(args.simulator),
        ),
        outdir=args.out,
        verbose=True,
    )


def _add_common_testbench_options(parser: argparse.ArgumentParser, default_mode: str) -> None:
    parser.add_argument("-t", "--tech", default="ihp130", choices=list_pdks(), help="Target PDK technology")
    parser.add_argument(
        "-m",
        "--mode",
        default=default_mode,
        choices=["min", "max"],
        help="min: first 10 variants; max: all variants",
    )
    parser.add_argument("--montecarlo", action="store_true", help="Add Monte Carlo analysis")
    parser.add_argument("-o", "--out", default="build", type=Path, help="Output directory")


def _check_simulator(simulator: str) -> None:
    """Verify that a local simulator is available."""
    hostname = socket.gethostname().split(".")[0].lower()
    if hostname not in SIM_HOSTS:
        hosts = ", ".join(sorted(SIM_HOSTS))
        raise SystemExit(f"Simulator unavailable: host '{hostname}' not in allow-list ({hosts})")
    if not any(shutil.which(binary) for binary in SIMULATOR_BINARIES[simulator]):
        raise SystemExit(f"Simulator binary '{simulator}' not found on PATH")
