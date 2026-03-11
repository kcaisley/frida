#!/usr/bin/env python3
"""
sweep.py -- Run transient Allpix Squared sweep studies for thin silicon pixels.

This script keeps the actual sweep definitions in Python and applies them via
Allpix command-line overrides. The configuration files remain static and use
comments only to document the intended sweep ranges.

Shared static inputs:
    - simulation.conf  main Allpix module configuration
    - placement.conf   detector placement
    - pixel.conf       detector model defaults

Examples:
    uv run sweep.py
    uv run sweep.py --limit 4
    uv run sweep.py --list --limit 5
    uv run sweep.py --case 1
    uv run sweep.py --case electron/e_100keV/p10um_t25um_b-5V_i10ns
    uv run sweep.py --particle photon --label ph_12keV --pitch 20 \
        --thickness 50 --bias -20 --integration 25

Environment overrides:
    ALLPIX_BIN   path to the allpix executable
    ROOT_SETUP   path to ROOT's thisroot.sh
"""

from __future__ import annotations

import argparse
import os
import random
import shlex
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence


SCRIPT_DIR = Path(__file__).resolve().parent
OUTPUTS_DIR = SCRIPT_DIR / "outputs"
SIMULATION_CONFIG = SCRIPT_DIR / "simulation.conf"
PLACEMENT_CONFIG = SCRIPT_DIR / "placement.conf"
MODEL_CONFIG = SCRIPT_DIR / "pixel.conf"
DEFAULT_ALLPIX_BIN = Path(
    os.environ.get("ALLPIX_BIN", "~/libs/allpix-squared/build/src/exec/allpix")
).expanduser()
DEFAULT_ROOT_SETUP = Path(
    os.environ.get("ROOT_SETUP", "~/libs/root/bin/thisroot.sh")
).expanduser()
DEFAULT_EVENTS = 1

# Geometry sweep lists. These define the actual sweep; comments in the config
# files are documentation only.
PIXEL_PITCHES_UM = (10, 20, 30, 40, 50)
SENSOR_THICKNESSES_UM = (25, 50, 75, 100)
BIAS_VOLTAGES_V = (-5, -10, -20, -40)
INTEGRATION_TIMES_NS = (10, 25, 100, 1000)

ELECTRON_MIP_DIRECTION = "0 0 1"
ELECTRON_NUMBER_OF_STEPS = 100
PHOTON_POSITION = "0um 0um 0um"


@dataclass(frozen=True)
class SweepDefinition:
    particle: str
    label: str
    charge_override: str
    notes: str
    source_type: str = "mip"
    position_override: str | None = None
    mip_direction_override: str | None = None
    number_of_steps_override: int | None = None


@dataclass(frozen=True)
class Case:
    sweep: SweepDefinition
    pitch_um: int
    thickness_um: int
    bias_v: int
    integration_time_ns: int

    @property
    def run_name(self) -> str:
        return (
            f"p{self.pitch_um}um_t{self.thickness_um}um_"
            f"b{self.bias_v}V_i{self.integration_time_ns}ns"
        )

    @property
    def case_id(self) -> str:
        return f"{self.sweep.particle}/{self.sweep.label}/{self.run_name}"

    @property
    def output_stem(self) -> str:
        return f"{self.sweep.particle}_{self.sweep.label}_{self.run_name}"

    @property
    def output_dir(self) -> Path:
        return OUTPUTS_DIR

    @property
    def output_dir_rel(self) -> Path:
        return self.output_dir.relative_to(SCRIPT_DIR)

    @property
    def data_file_name(self) -> str:
        return f"{self.output_stem}_data.root"

    @property
    def modules_file_name(self) -> str:
        return f"{self.output_stem}_modules.root"

    @property
    def log_file_name(self) -> str:
        return f"{self.output_stem}_allpix.log"

    @property
    def data_path_rel(self) -> Path:
        return self.output_dir_rel / self.data_file_name

    @property
    def modules_path_rel(self) -> Path:
        return self.output_dir_rel / self.modules_file_name

    @property
    def log_path_rel(self) -> Path:
        return self.output_dir_rel / self.log_file_name

    def allpix_args(self, allpix_bin: Path, events: int) -> list[str]:
        args = [
            str(allpix_bin),
            "-c",
            SIMULATION_CONFIG.name,
            "-o",
            f"number_of_events={events}",
            "-o",
            f"output_directory={self.output_dir_rel.as_posix()}",
            "-o",
            f"root_file={self.modules_file_name}",
            "-o",
            f"DepositionPointCharge.number_of_charges={self.sweep.charge_override}",
            "-o",
            f"ElectricFieldReader.bias_voltage={self.bias_v}V",
            "-o",
            f"TransientPropagation.integration_time={self.integration_time_ns}ns",
            "-o",
            f"ROOTObjectWriter.file_name={self.data_file_name}",
            "-o",
            f"random_seed={random.SystemRandom().randint(1, 999_999)}",
            "-o",
            f'DepositionPointCharge.source_type="{self.sweep.source_type}"',
            "-g",
            f"dut.pixel_size={self.pitch_um}um,{self.pitch_um}um",
            "-g",
            f"dut.sensor_thickness={self.thickness_um}um",
        ]
        if self.sweep.position_override is not None:
            args.extend(
                [
                    "-o",
                    f"DepositionPointCharge.position={self.sweep.position_override}",
                ]
            )
        if self.sweep.mip_direction_override is not None:
            args.extend(
                [
                    "-o",
                    f"DepositionPointCharge.mip_direction={self.sweep.mip_direction_override}",
                ]
            )
        if self.sweep.number_of_steps_override is not None:
            args.extend(
                [
                    "-o",
                    f"DepositionPointCharge.number_of_steps={self.sweep.number_of_steps_override}",
                ]
            )
        return args


def photon_charge_pairs(energy_keV: int) -> int:
    return round(energy_keV * 1000.0 / 3.64)


ELECTRON_SWEEPS: tuple[SweepDefinition, ...] = (
    SweepDefinition(
        "electron",
        "e_100keV",
        "40/um",
        "sub-MIP electron surrogate, high scatter",
        mip_direction_override=ELECTRON_MIP_DIRECTION,
        number_of_steps_override=ELECTRON_NUMBER_OF_STEPS,
    ),
    SweepDefinition(
        "electron",
        "e_200keV",
        "30/um",
        "near-MIP electron surrogate",
        mip_direction_override=ELECTRON_MIP_DIRECTION,
        number_of_steps_override=ELECTRON_NUMBER_OF_STEPS,
    ),
    SweepDefinition(
        "electron",
        "e_1MeV",
        "25/um",
        "MIP-minimum-like electron surrogate",
        mip_direction_override=ELECTRON_MIP_DIRECTION,
        number_of_steps_override=ELECTRON_NUMBER_OF_STEPS,
    ),
    SweepDefinition(
        "electron",
        "e_5MeV",
        "27/um",
        "MIP-like electron surrogate",
        mip_direction_override=ELECTRON_MIP_DIRECTION,
        number_of_steps_override=ELECTRON_NUMBER_OF_STEPS,
    ),
    SweepDefinition(
        "electron",
        "e_100MeV",
        "33/um",
        "relativistic-rise electron surrogate",
        mip_direction_override=ELECTRON_MIP_DIRECTION,
        number_of_steps_override=ELECTRON_NUMBER_OF_STEPS,
    ),
    SweepDefinition(
        "electron",
        "e_1GeV",
        "35/um",
        "Fermi-plateau electron surrogate",
        mip_direction_override=ELECTRON_MIP_DIRECTION,
        number_of_steps_override=ELECTRON_NUMBER_OF_STEPS,
    ),
    SweepDefinition(
        "electron",
        "mip_mpv",
        "80/um",
        "generic MIP most-probable-value bracket",
        mip_direction_override=ELECTRON_MIP_DIRECTION,
        number_of_steps_override=ELECTRON_NUMBER_OF_STEPS,
    ),
    SweepDefinition(
        "electron",
        "mip_thin_mpv",
        "65/um",
        "thin-sensor MIP MPV bracket around 50um silicon",
        mip_direction_override=ELECTRON_MIP_DIRECTION,
        number_of_steps_override=ELECTRON_NUMBER_OF_STEPS,
    ),
)

PHOTON_SWEEPS: tuple[SweepDefinition, ...] = (
    SweepDefinition(
        "photon",
        "ph_1keV",
        str(photon_charge_pairs(1)),
        "soft X-ray absorbed-photon surrogate",
        source_type="point",
        position_override=PHOTON_POSITION,
    ),
    SweepDefinition(
        "photon",
        "ph_5keV",
        str(photon_charge_pairs(5)),
        "mid-energy X-ray absorbed-photon surrogate",
        source_type="point",
        position_override=PHOTON_POSITION,
    ),
    SweepDefinition(
        "photon",
        "ph_12keV",
        str(photon_charge_pairs(12)),
        "12keV X-ray absorbed-photon surrogate",
        source_type="point",
        position_override=PHOTON_POSITION,
    ),
    SweepDefinition(
        "photon",
        "ph_20keV",
        str(photon_charge_pairs(20)),
        "harder X-ray absorbed-photon surrogate",
        source_type="point",
        position_override=PHOTON_POSITION,
    ),
)

ALL_SWEEP_DEFINITIONS = ELECTRON_SWEEPS + PHOTON_SWEEPS


def build_cases() -> list[Case]:
    cases: list[Case] = []
    for sweep in ALL_SWEEP_DEFINITIONS:
        for pitch_um in PIXEL_PITCHES_UM:
            for thickness_um in SENSOR_THICKNESSES_UM:
                for bias_v in BIAS_VOLTAGES_V:
                    for integration_time_ns in INTEGRATION_TIMES_NS:
                        cases.append(
                            Case(
                                sweep=sweep,
                                pitch_um=pitch_um,
                                thickness_um=thickness_um,
                                bias_v=bias_v,
                                integration_time_ns=integration_time_ns,
                            )
                        )
    return cases


def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run thin-pixel Allpix sweep cases from Python.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--limit",
        type=int,
        help="Run only the first N selected cases from the sweep order.",
    )
    parser.add_argument(
        "--case",
        help=(
            "Run one case by 1-based index or case id, for example "
            "electron/e_100keV/p10um_t25um_b-5V_i10ns."
        ),
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List selected cases and exit without running Allpix.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the selected commands without executing them.",
    )
    parser.add_argument(
        "--events",
        type=int,
        default=DEFAULT_EVENTS,
        help="Override number_of_events for each run (default: %(default)s).",
    )
    parser.add_argument(
        "--particle",
        action="append",
        choices=["electron", "photon"],
        help="Filter to one particle family. Can be passed more than once.",
    )
    parser.add_argument(
        "--label",
        action="append",
        help="Filter to one or more deposition labels.",
    )
    parser.add_argument(
        "--pitch",
        action="append",
        type=int,
        help="Filter to one or more pixel pitches in um.",
    )
    parser.add_argument(
        "--thickness",
        action="append",
        type=int,
        help="Filter to one or more sensor thicknesses in um.",
    )
    parser.add_argument(
        "--bias",
        action="append",
        type=int,
        help="Filter to one or more bias voltages in V, e.g. --bias -20.",
    )
    parser.add_argument(
        "--integration",
        action="append",
        type=int,
        help="Filter to one or more integration times in ns.",
    )
    args = parser.parse_args(argv)

    if args.limit is not None and args.limit < 0:
        parser.error("--limit must be zero or a positive integer")
    if args.events < 1:
        parser.error("--events must be at least 1")

    has_explicit_filters = any(
        [
            args.particle,
            args.label,
            args.pitch,
            args.thickness,
            args.bias,
            args.integration,
        ]
    )
    if args.case and args.limit is not None:
        parser.error("--case already selects one run; do not combine it with --limit")
    if args.case and has_explicit_filters:
        parser.error("--case cannot be combined with the explicit filter flags")

    return args


def matches_filters(case: Case, args: argparse.Namespace) -> bool:
    if args.particle and case.sweep.particle not in set(args.particle):
        return False
    if args.label and case.sweep.label not in set(args.label):
        return False
    if args.pitch and case.pitch_um not in set(args.pitch):
        return False
    if args.thickness and case.thickness_um not in set(args.thickness):
        return False
    if args.bias and case.bias_v not in set(args.bias):
        return False
    if args.integration and case.integration_time_ns not in set(args.integration):
        return False
    return True


def resolve_case(cases: Sequence[Case], case_spec: str) -> Case:
    if case_spec.isdigit():
        case_index = int(case_spec)
        if case_index < 1 or case_index > len(cases):
            raise ValueError(f"Case index {case_index} is out of range 1..{len(cases)}")
        return cases[case_index - 1]

    normalized = case_spec.removeprefix("outputs/")
    matches = [
        case
        for case in cases
        if case.case_id == normalized
        or case.output_stem == case_spec
        or case.output_dir_rel.as_posix() == case_spec
    ]
    if not matches:
        raise ValueError(f"No case matches '{case_spec}'")
    if len(matches) > 1:
        raise ValueError(
            f"Case spec '{case_spec}' is ambiguous; use the full particle/label/run id"
        )
    return matches[0]


def select_cases(cases: Sequence[Case], args: argparse.Namespace) -> list[Case]:
    if args.case:
        return [resolve_case(cases, args.case)]

    selected = [case for case in cases if matches_filters(case, args)]
    if args.limit is not None:
        selected = selected[: args.limit]
    return selected


def ensure_runtime_inputs() -> None:
    required_files = (SIMULATION_CONFIG, PLACEMENT_CONFIG, MODEL_CONFIG)
    missing = [str(path) for path in required_files if not path.exists()]
    if missing:
        raise FileNotFoundError(
            "Missing required configuration inputs:\n  - " + "\n  - ".join(missing)
        )

    if not DEFAULT_ALLPIX_BIN.exists():
        raise FileNotFoundError(
            f"Allpix executable not found at {DEFAULT_ALLPIX_BIN}. "
            "Set ALLPIX_BIN to override it."
        )
    if not DEFAULT_ROOT_SETUP.exists():
        raise FileNotFoundError(
            f"ROOT setup script not found at {DEFAULT_ROOT_SETUP}. "
            "Set ROOT_SETUP to override it."
        )


def shell_join(parts: Sequence[str]) -> str:
    return " ".join(shlex.quote(part) for part in parts)


def print_case_list(cases: Sequence[Case]) -> None:
    for index, case in enumerate(cases, start=1):
        print(
            f"{index:4d}  {case.case_id}  "
            f"[{case.output_stem}, {SIMULATION_CONFIG.name}, q={case.sweep.charge_override}, "
            f"{case.sweep.notes}]"
        )


def run_case(
    case: Case, case_index: int, total_cases: int, events: int, dry_run: bool
) -> tuple[int, float]:
    print("-" * 78)
    print(f"[{case_index}/{total_cases}] {case.case_id}")
    print(f"  config: {SIMULATION_CONFIG.name}")
    print(f"  deposition: {case.sweep.charge_override}")
    print(f"  notes: {case.sweep.notes}")
    print(f"  output dir: {case.output_dir_rel.as_posix()}")
    print(f"  data file: {case.data_path_rel.as_posix()}")
    print(f"  modules file: {case.modules_path_rel.as_posix()}")
    print(f"  log file: {case.log_path_rel.as_posix()}")

    allpix_command = case.allpix_args(DEFAULT_ALLPIX_BIN, events)
    shell_command = (
        "set -euo pipefail; "
        f"source {shlex.quote(str(DEFAULT_ROOT_SETUP))}; "
        f"{shell_join(allpix_command)} 2>&1 | tee {shlex.quote(case.log_path_rel.as_posix())}"
    )

    if dry_run:
        print(f"  shell: {shell_command}")
        return 0, 0.0

    case.output_dir.mkdir(parents=True, exist_ok=True)
    start = time.perf_counter()
    completed = subprocess.run(["bash", "-lc", shell_command], cwd=SCRIPT_DIR)
    elapsed_seconds = time.perf_counter() - start
    print(f"  elapsed: {elapsed_seconds:.2f}s")
    return completed.returncode, elapsed_seconds


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    all_cases = build_cases()

    try:
        selected_cases = select_cases(all_cases, args)
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    if not selected_cases:
        print("ERROR: no sweep cases matched the requested selection", file=sys.stderr)
        return 2

    print(
        f"Defined {len(all_cases)} total cases across "
        f"{len(ELECTRON_SWEEPS)} electron and {len(PHOTON_SWEEPS)} photon sweep points."
    )
    print(f"Selected {len(selected_cases)} case(s).")

    if args.list:
        print_case_list(selected_cases)
        return 0

    if not args.dry_run:
        try:
            ensure_runtime_inputs()
        except FileNotFoundError as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 1

    elapsed_seconds: list[float] = []
    for case_index, case in enumerate(selected_cases, start=1):
        try:
            returncode, elapsed = run_case(
                case,
                case_index=case_index,
                total_cases=len(selected_cases),
                events=args.events,
                dry_run=args.dry_run,
            )
        except KeyboardInterrupt:
            print("\nInterrupted.", file=sys.stderr)
            return 130

        if returncode != 0:
            print(f"ERROR: case failed with exit code {returncode}: {case.case_id}")
            return returncode

        if not args.dry_run:
            elapsed_seconds.append(elapsed)

    if args.dry_run:
        print("Dry run complete.")
    else:
        print("Sweep complete.")
        print(f"Outputs are under {OUTPUTS_DIR}")
        if elapsed_seconds:
            total = sum(elapsed_seconds)
            average = total / len(elapsed_seconds)
            print(
                f"Timing: total={total:.2f}s avg={average:.2f}s "
                f"min={min(elapsed_seconds):.2f}s max={max(elapsed_seconds):.2f}s"
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
