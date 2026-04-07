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

import argcomplete

from .pdks import list_pdks, set_pdk

# Available cells per flow command
PRIMITIVES = ["mosfet", "momcap"]
SUBCKTS = ["samp", "comp", "cdac", "adc"]
LAYOUTS = ["comp"]
TESTBENCHES = ["samp", "comp", "cdac", "adc"]

# Hosts with SPICE simulators and PDKs available
SIM_HOSTS = {"jupiter", "juno", "asiclab003"}

# Simulator binaries to probe on PATH
SIMULATOR_BINARIES = {
    "spectre": ("spectre",),
    "ngspice": ("ngspice",),
    "xyce": ("Xyce", "xyce"),
}


def main():
    parser = argparse.ArgumentParser(prog="flow", description="FRIDA design flow runner")
    sub = parser.add_subparsers(dest="command", required=True)

    # ==== Primitive ====
    p = sub.add_parser("primitive", help="Generate layout primitives")
    p.add_argument("-c", "--cell", required=True, choices=PRIMITIVES, help="Primitive cell to generate")
    p.add_argument("-t", "--tech", default="ihp130", choices=list_pdks(), help="Target PDK technology")
    p.add_argument("-m", "--mode", default="min", choices=["min", "max"], help="min: default only; max: full sweep")
    p.add_argument("-v", "--visual", action="store_true", help="Open result in KLayout viewer")
    p.add_argument("-o", "--out", default="scratch", type=Path, help="Output directory")

    # ==== Netlist ====
    p = sub.add_parser("netlist", help="Generate netlists")
    p.add_argument("-c", "--cell", required=True, choices=SUBCKTS, help="Circuit block")
    p.add_argument("-t", "--tech", default="ihp130", choices=list_pdks(), help="Target PDK technology")
    p.add_argument("-m", "--mode", default="max", choices=["min", "max"], help="min: first 10 variants; max: all")
    p.add_argument(
        "-f",
        "--fmt",
        default="spectre",
        choices=["spectre", "ngspice", "cdl", "verilog"],
        help="Netlist output format",
    )
    p.add_argument(
        "--scope",
        default="full",
        choices=["dut", "stim", "full"],
        help="dut: subcircuits only; stim: TB wrapper + sources; full: complete sim input",
    )
    p.add_argument("--montecarlo", action="store_true", help="Add Monte Carlo analysis to sim input")
    p.add_argument("-o", "--out", default="scratch", type=Path, help="Output directory")

    # ==== Layout ====
    p = sub.add_parser("layout", help="Run place-and-route via OpenROAD")
    p.add_argument("-c", "--cell", required=True, choices=LAYOUTS, help="Circuit block")
    p.add_argument("-t", "--tech", default="ihp130", choices=list_pdks(), help="Target PDK technology")
    p.add_argument("-o", "--out", default="scratch", type=Path, help="Output directory")

    # ==== Simulate ====
    p = sub.add_parser("simulate", help="Run simulations")
    p.add_argument("-c", "--cell", required=True, choices=TESTBENCHES, help="Circuit block")
    p.add_argument("-t", "--tech", default="ihp130", choices=list_pdks(), help="Target PDK technology")
    p.add_argument("-m", "--mode", default="min", choices=["min", "max"], help="min: first 10 variants; max: all")
    p.add_argument(
        "-s",
        "--simulator",
        default="spectre",
        choices=["spectre", "ngspice", "xyce"],
        help="SPICE simulator backend",
    )
    p.add_argument("--host", default=None, help="Remote simulation host (e.g. jupiter)")
    p.add_argument("--montecarlo", action="store_true", help="Add Monte Carlo analysis")
    p.add_argument("-o", "--out", default="scratch", type=Path, help="Output directory")

    # ==== Convert ====
    p = sub.add_parser("convert", help="Convert netlists between formats (OA/CDL/SP)")
    p.add_argument("--from", dest="src_fmt", required=True, choices=["oa", "cdl", "sp"], help="Source format")
    p.add_argument("--to", dest="dst_fmt", required=True, choices=["cdl", "sp", "sp_clean"], help="Target format")
    p.add_argument("--file", type=Path, help="Input file path (required for cdl/sp sources)")
    p.add_argument("--cdslib", type=Path, help="Path to cds.lib (required for --from oa)")
    p.add_argument("--oalib", help="OA library name (required for --from oa)")
    p.add_argument("--oacell", help="OA cell name (required for --from oa)")
    p.add_argument("--outdir", required=True, type=Path, help="Output directory")
    p.add_argument("--verilog", type=Path, help="Verilog file for port reordering (sp_clean only)")
    p.add_argument("--module", help="Module name for port reordering (sp_clean only)")

    argcomplete.autocomplete(parser)

    args = parser.parse_args()

    if args.command == "convert":
        _run_convert(args)
        return

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


def _run_convert(args):
    from .util.netlist import cdl_to_sp, clean_cdl, oa_to_cdl

    src, dst = args.src_fmt, args.dst_fmt
    args.outdir.mkdir(parents=True, exist_ok=True)

    if src == "oa":
        if not args.cdslib or not args.oalib or not args.oacell:
            raise SystemExit("--cdslib, --oalib, and --oacell are required when --from=oa")
        if dst == "cdl":
            out = oa_to_cdl(args.oalib, args.oacell, args.outdir, cdslib=args.cdslib)
        elif dst == "sp":
            cdl = oa_to_cdl(args.oalib, args.oacell, args.outdir, cdslib=args.cdslib)
            out = cdl_to_sp(cdl, args.outdir / cdl.with_suffix(".sp").name)
        elif dst == "sp_clean":
            cdl = oa_to_cdl(args.oalib, args.oacell, args.outdir, cdslib=args.cdslib)
            out = clean_cdl(cdl, args.outdir / cdl.with_suffix(".sp").name,
                            verilog=args.verilog, module=args.module)
        else:
            raise SystemExit(f"Unsupported conversion: oa → {dst}")

    elif src == "cdl":
        if not args.file:
            raise SystemExit("--file is required when --from=cdl")
        stem = args.file.stem
        if dst == "sp":
            out = cdl_to_sp(args.file, args.outdir / f"{stem}.sp")
        elif dst == "sp_clean":
            out = clean_cdl(args.file, args.outdir / f"{stem}.sp",
                            verilog=args.verilog, module=args.module)
        else:
            raise SystemExit(f"Unsupported conversion: cdl → {dst}")

    else:
        raise SystemExit(f"Unsupported source format: {src}")

    print(f"Converted: {out}")


def _run_primitive(args):
    from importlib import import_module

    mod = import_module(f"flow.{args.cell}.primitive")
    mod.run_layout(tech=args.tech, mode=args.mode, visual=args.visual, outdir=args.out)


def _run_netlist(args):
    from importlib import import_module

    # Validate scope + format combinations
    if args.scope != "dut" and args.fmt in ("cdl", "verilog"):
        raise SystemExit(f"--fmt={args.fmt} only supports --scope=dut (got --scope={args.scope})")
    if args.fmt == "cdl":
        raise SystemExit("--fmt=cdl is not supported by the installed vlsirtools backend")
    if args.montecarlo and args.scope != "full":
        raise SystemExit(f"--montecarlo requires --scope=full (got --scope={args.scope})")

    mod = import_module(f"flow.{args.cell}.testbench")
    outdir = args.out / args.cell
    outdir.mkdir(parents=True, exist_ok=True)
    mod.run_netlist(
        tech=args.tech,
        mode=args.mode,
        montecarlo=args.montecarlo,
        fmt=args.fmt,
        scope=args.scope,
        outdir=outdir,
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
        raise SystemExit(f"Simulator unavailable: host '{hostname}' not in allow-list ({hosts})")
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
