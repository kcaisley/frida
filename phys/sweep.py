#!/usr/bin/env python3
import argparse
import random
import shlex
import subprocess
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
SWEEPS: list[tuple[str, str, str, str, str | None]] = [
    ("electron", "e_100keV", "40/um", "mip", None),
    ("electron", "e_200keV", "30/um", "mip", None),
    ("electron", "e_1MeV", "25/um", "mip", None),
    ("electron", "e_5MeV", "27/um", "mip", None),
    ("electron", "e_100MeV", "33/um", "mip", None),
    ("electron", "e_1GeV", "35/um", "mip", None),
    ("electron", "mip_mpv", "80/um", "mip", None),
    ("electron", "mip_thin_mpv", "65/um", "mip", None),
    ("photon", "ph_1keV", "275", "point", "0um 0um 0um"),
    ("photon", "ph_5keV", "1374", "point", "0um 0um 0um"),
    ("photon", "ph_12keV", "3297", "point", "0um 0um 0um"),
    ("photon", "ph_20keV", "5495", "point", "0um 0um 0um"),
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, help="run only the first N combinations")
    parser.add_argument(
        "--dry-run", action="store_true", help="print commands without running them"
    )
    args = parser.parse_args()
    if args.limit is not None and args.limit < 0:
        parser.error("--limit must be non-negative")
    return args


def collect_cases() -> list[tuple[tuple[str, str, str, str, str | None], int, int]]:
    return list(
        product(
            SWEEPS,
            SENSOR_THICKNESSES_UM,
            BIAS_VOLTAGES_V,
        )
    )


def run_case(
    case: tuple[tuple[str, str, str, str, str | None], int, int],
    dry_run: bool,
) -> None:
    (particle, label, charge, source, position), thickness, bias = case
    stem = f"{particle}_{label}_t{thickness}um_b{bias}V"
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
    if source == "mip":
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


def main() -> int:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    cases = collect_cases()
    args = parse_args()
    limit = args.limit
    for case in cases if limit is None else cases[:limit]:
        run_case(case, args.dry_run)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
