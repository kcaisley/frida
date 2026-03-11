"""FRIDA design flow runner — thin CLI dispatcher.

Usage:
    flow primitive -c mosfet -t ihp130 -m max -v
    flow netlist -c samp -t ihp130 -m max
    flow simulate -c comp -s spectre --host jupiter
"""

import argparse
import shutil
import socket
import subprocess
from pathlib import Path

try:
    import argcomplete

    HAS_ARGCOMPLETE = True
except ImportError:
    HAS_ARGCOMPLETE = False

from .pdks import list_pdks, set_pdk

# Hosts with SPICE simulators and PDKs available
SIM_HOSTS = {"jupiter", "juno", "asiclab003"}

# Simulator binaries to probe on PATH
SIMULATOR_BINARIES = {
    "spectre": ("spectre",),
    "ngspice": ("ngspice",),
    "xyce": ("Xyce", "xyce"),
}


def main():
    parser = argparse.ArgumentParser(
        prog="flow", description="FRIDA design flow runner"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # ==== Primitive ====
    p = sub.add_parser("primitive", help="Generate layout primitives")
    p.add_argument("-c", "--cell", required=True, choices=["mosfet", "momcap"])
    p.add_argument("-t", "--tech", default="ihp130", choices=list_pdks())
    p.add_argument("-m", "--mode", default="min", choices=["min", "max"])
    p.add_argument("-v", "--visual", action="store_true")
    p.add_argument("-o", "--out", default="scratch", type=Path)

    # ==== Netlist ====
    p = sub.add_parser("netlist", help="Generate netlists")
    p.add_argument(
        "-c", "--cell", required=True, choices=["samp", "comp", "cdac", "adc"]
    )
    p.add_argument("-t", "--tech", default="ihp130", choices=list_pdks())
    p.add_argument("-m", "--mode", default="min", choices=["min", "max"])
    p.add_argument(
        "-f",
        "--fmt",
        default="spectre",
        choices=["spectre", "ngspice", "cdl", "verilog"],
    )
    p.add_argument(
        "--scope",
        default="full",
        choices=["dut", "stim", "full"],
        help="dut: subcircuits only; stim: TB wrapper + sources; full: complete sim input",
    )
    p.add_argument("--montecarlo", action="store_true")
    p.add_argument("-o", "--out", default="scratch", type=Path)

    # ==== Layout ====
    p = sub.add_parser("layout", help="Run place-and-route via OpenROAD")
    p.add_argument("-c", "--cell", required=True, choices=["comp"])
    p.add_argument("-t", "--tech", default="ihp130", choices=list_pdks())
    p.add_argument("-o", "--out", default="scratch", type=Path)

    # ==== Simulate ====
    p = sub.add_parser("simulate", help="Run simulations")
    p.add_argument(
        "-c", "--cell", required=True, choices=["samp", "comp", "cdac", "adc"]
    )
    p.add_argument("-t", "--tech", default="ihp130", choices=list_pdks())
    p.add_argument("-m", "--mode", default="min", choices=["min", "max"])
    p.add_argument(
        "-s",
        "--simulator",
        default="spectre",
        choices=["spectre", "ngspice", "xyce"],
    )
    p.add_argument("--host", default=None)
    p.add_argument("--montecarlo", action="store_true")
    p.add_argument("-o", "--out", default="scratch", type=Path)

    if HAS_ARGCOMPLETE:
        argcomplete.autocomplete(parser)  # type: ignore[possibly-undefined]

    args = parser.parse_args()
    set_pdk(args.tech)
    args.out.mkdir(parents=True, exist_ok=True)

    if args.command == "primitive":
        _run_primitive(args)
    elif args.command == "netlist":
        _run_netlist(args)
    elif args.command == "layout":
        _run_layout(args)
    elif args.command == "simulate":
        _run_simulate(args)


def _run_primitive(args):
    from importlib import import_module

    mod = import_module(f"flow.{args.cell}.primitive")
    mod.run_layout(tech=args.tech, mode=args.mode, visual=args.visual, outdir=args.out)


def _run_netlist(args):
    from importlib import import_module

    # Validate scope + format combinations
    if args.scope != "dut" and args.fmt in ("cdl", "verilog"):
        raise SystemExit(
            f"--fmt={args.fmt} only supports --scope=dut (got --scope={args.scope})"
        )
    if args.fmt == "cdl":
        raise SystemExit(
            "--fmt=cdl is not supported by the installed vlsirtools backend"
        )
    if args.montecarlo and args.scope != "full":
        raise SystemExit(
            f"--montecarlo requires --scope=full (got --scope={args.scope})"
        )

    mod = import_module(f"flow.{args.cell}.testbench")
    mod.run_netlist(
        tech=args.tech,
        mode=args.mode,
        montecarlo=args.montecarlo,
        fmt=args.fmt,
        scope=args.scope,
        outdir=args.out,
        verbose=True,
    )


def _run_simulate(args):
    _check_simulator(args.simulator, args.host)
    from importlib import import_module

    mod = import_module(f"flow.{args.cell}.testbench")
    mod.run_simulate(
        tech=args.tech,
        mode=args.mode,
        montecarlo=args.montecarlo,
        simulator=args.simulator,
        sim_options=_make_sim_options(args),
        sim_server=args.host,
        outdir=args.out,
        verbose=True,
    )


def _check_openroad():
    if not shutil.which("openroad"):
        raise SystemExit("OpenROAD binary not found on PATH")


def _run_layout(args):
    _check_openroad()
    script = Path(__file__).parent / args.cell / "layout.py"
    if not script.exists():
        raise SystemExit(f"No layout script found for cell '{args.cell}' at {script}")
    subprocess.run(
        ["openroad", "-exit", "-python", str(script), args.cell, args.tech],
        check=True,
    )


def _check_simulator(simulator, host):
    """Verify simulator is available locally (skipped when using remote host)."""
    if host:
        return
    hostname = socket.gethostname().split(".")[0].lower()
    if hostname not in SIM_HOSTS:
        hosts = ", ".join(sorted(SIM_HOSTS))
        raise SystemExit(
            f"Simulator unavailable: host '{hostname}' not in allow-list ({hosts})"
        )
    binaries = SIMULATOR_BINARIES[simulator]
    if not any(shutil.which(b) for b in binaries):
        raise SystemExit(f"Simulator binary '{simulator}' not found on PATH")


def _make_sim_options(args):
    """Build vlsirtools SimOptions for the requested simulator."""
    from vlsirtools.spice import SupportedSimulators  # type: ignore[import-untyped]

    from .circuit.sim import get_sim_options

    sim = SupportedSimulators(args.simulator)
    return get_sim_options(rundir=args.out, simulator=sim)


if __name__ == "__main__":
    main()
