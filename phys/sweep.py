#!/usr/bin/env python3
import argparse
import random
import shlex
import shutil
import subprocess
from enum import Enum, StrEnum
from itertools import product
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
ALLPIX_BIN = Path("~/libs/allpix-squared/build/src/exec/allpix").expanduser()
WORKSPACE_SH = SCRIPT_DIR / "workspace.sh"
SIMULATION_CONF = "simulation.conf"
RESULTS_DIR = SCRIPT_DIR / "results"
EVENTS = 1

SENSOR_THICKNESSES_UM: list[int] = [25, 50, 75, 100]
BIAS_VOLTAGES_V: list[int] = [-5, -10, -20, -40]


class Source(StrEnum):
    MIP = "mip"
    POINT = "point"


def electron_stopping_power_mev_cm2_per_g(energy_ev: int) -> float:
    return {
        100_000: 0.50,
        200_000: 0.35,
        1_000_000: 0.27,
        5_000_000: 0.30,
        100_000_000: 0.38,
        1_000_000_000: 0.40,
    }[energy_ev]


def electron_charge_pairs_per_um(energy_ev: int) -> str:
    return f"{round(electron_stopping_power_mev_cm2_per_g(energy_ev) * 2.33 * 100 / 3.64)}/um"


class Sweep(Enum):
    E100KEV = (
        "electron",
        "e_100keV",
        electron_charge_pairs_per_um(100_000),
        Source.MIP,
        None,
    )
    E200KEV = (
        "electron",
        "e_200keV",
        electron_charge_pairs_per_um(200_000),
        Source.MIP,
        None,
    )
    E1MEV = (
        "electron",
        "e_1MeV",
        electron_charge_pairs_per_um(1_000_000),
        Source.MIP,
        None,
    )
    E5MEV = (
        "electron",
        "e_5MeV",
        electron_charge_pairs_per_um(5_000_000),
        Source.MIP,
        None,
    )
    E100MEV = (
        "electron",
        "e_100MeV",
        electron_charge_pairs_per_um(100_000_000),
        Source.MIP,
        None,
    )
    E1GEV = (
        "electron",
        "e_1GeV",
        electron_charge_pairs_per_um(1_000_000_000),
        Source.MIP,
        None,
    )
    PH1KEV = ("photon", "ph_1keV", "275", Source.POINT, "0um 0um 0um")
    PH5KEV = ("photon", "ph_5keV", "1374", Source.POINT, "0um 0um 0um")
    PH12KEV = ("photon", "ph_12keV", "3297", Source.POINT, "0um 0um 0um")
    PH20KEV = ("photon", "ph_20keV", "5495", Source.POINT, "0um 0um 0um")


SWEEPS = list(Sweep)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, help="run only the first N combinations")
    parser.add_argument(
        "--fmt",
        choices=("spectre", "spice"),
        default="spectre",
        help="netlist output format (default: %(default)s)",
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="print commands without running them"
    )
    args = parser.parse_args()
    if args.limit is not None and args.limit < 0:
        parser.error("--limit must be non-negative")
    return args


def collect_cases() -> list[tuple[Sweep, int, int]]:
    return list(
        product(
            SWEEPS,
            SENSOR_THICKNESSES_UM,
            BIAS_VOLTAGES_V,
        )
    )


def finalize_netlist(stem: str, fmt: str) -> None:
    ext = "scs" if fmt == "spectre" else "sp"
    generated = list(RESULTS_DIR.glob(f"{stem}_pwl_event*.{ext}"))
    if len(generated) != 1:
        raise FileNotFoundError(
            f"Expected one generated netlist for {stem}, found {len(generated)}"
        )
    generated[0].rename(RESULTS_DIR / f"{stem}_pwl.{ext}")


def run_case(
    case: tuple[Sweep, int, int],
    fmt: str,
    dry_run: bool,
) -> None:
    (particle, label, charge, source, position), thickness, bias = (
        case[0].value,
        case[1],
        case[2],
    )
    stem = f"{particle}_{label}_t{thickness}um_b{bias}V"
    target = "SPECTRE" if fmt == "spectre" else "SPICE"
    template = f"template.{'scs' if fmt == 'spectre' else 'sp'}"
    netlist_prefix = RESULTS_DIR / f"{stem}_pwl"
    cmd = [
        str(ALLPIX_BIN),
        "-c",
        SIMULATION_CONF,
        "-o",
        f"number_of_events={EVENTS}",
        "-o",
        f"output_directory={RESULTS_DIR.name}",
        "-o",
        f"root_file={stem}_modules.root",
        "-o",
        f"ROOTObjectWriter.file_name={stem}_data.root",
        "-o",
        f"NetlistWriter.target={target}",
        "-o",
        f"NetlistWriter.netlist_template={template}",
        "-o",
        f"NetlistWriter.file_name={netlist_prefix}",
        "-o",
        f"DepositionPointCharge.number_of_charges={charge}",
        "-o",
        f'DepositionPointCharge.source_type="{source}"',
        "-o",
        f"ElectricFieldReader.bias_voltage={bias}V",
        "-o",
        f"random_seed={random.randint(1, 999999)}",
        "-g",
        f"dut.sensor_thickness={thickness}um",
    ]
    if source is Source.MIP:
        cmd += [
            "-o",
            "DepositionPointCharge.mip_direction=0 0 1",
            "-o",
            "DepositionPointCharge.number_of_steps=100",
        ]
    if position is not None:
        cmd += ["-o", f"DepositionPointCharge.position={position}"]
    shell = f"set -euo pipefail; source {shlex.quote(str(WORKSPACE_SH))}; {' '.join(shlex.quote(part) for part in cmd)}"
    print(stem)
    if dry_run:
        print(shell)
        return
    subprocess.run(["bash", "-lc", shell], cwd=SCRIPT_DIR, check=True)
    finalize_netlist(stem, fmt)


def main() -> int:
    args = parse_args()
    if not args.dry_run and RESULTS_DIR.exists():
        shutil.rmtree(RESULTS_DIR)
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    cases = collect_cases()
    limit = args.limit
    for case in cases if limit is None else cases[:limit]:
        run_case(case, args.fmt, args.dry_run)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
