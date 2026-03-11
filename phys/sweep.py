#!/usr/bin/env python3
"""
sweep.py -- Run transient Allpix Squared sweep studies for thin silicon pixels.

This replaces the old single-purpose Bash runner with a single Python entry
point that drives both the electron and photon transient studies.

The sweep axes and shared Allpix defaults now live in `simulation.conf`.

ELECTRON STUDY NOTES
------------------------------------------------------------------------------
Runs Allpix Squared simulations across a range of effective electron
deposition conditions spanning electron microscopy through accelerator
beamlines.

FLUENCE REGIMES (electrons / cm^2 / s):
------------------------------------------------------------------------------
Application            Energy        Typical Fluence (e/cm^2/s)
------------------------------------------------------------------------------
SEM imaging            1-30 keV      1e6 - 1e10
TEM imaging            80-300 keV    1e4 - 1e8
STEM probe             80-300 keV    1e8 - 1e12
Electron diffraction   100-300 keV   1e2 - 1e6
Medical LINAC          4-20 MeV      1e8 - 1e12
Physics beamline       1-10 GeV      1e4 - 1e8 (typical test beam)
------------------------------------------------------------------------------

CHARGE DEPOSITION (e-h pairs / um in Si):
------------------------------------------------------------------------------
Energy        dE/dx approx      e-h pairs/um    Notes
------------------------------------------------------------------------------
100 keV       ~0.5 MeV cm2/g    ~40/um          Sub-MIP, high scatter
200 keV       ~0.35 MeV cm2/g   ~30/um          Approaching MIP
1 MeV         ~0.27 MeV cm2/g   ~25/um          Near MIP minimum
5 MeV         ~0.30 MeV cm2/g   ~27/um          MIP-like
100 MeV       ~0.38 MeV cm2/g   ~33/um          Relativistic rise
1 GeV         ~0.40 MeV cm2/g   ~35/um          Fermi plateau
MIP (generic) ~0.39 MeV cm2/g   ~80/um (MPV)    Most-probable Landau
------------------------------------------------------------------------------

(*) Electrons below ~50 keV stop within 50um Si. DepositionPointCharge with
    source_type = mip assumes a straight-through track, so the low-energy end
    of this study remains a transport surrogate rather than a realistic
    scattering/stopping model.

NOTE: The "80/um" MIP value is the most-probable Landau value including delta
rays. The restricted dE/dx (mean without delta rays) is closer to ~30/um. For
a 50um thin sensor, the most-probable value is often closer to 60-70/um, so
the sweep keeps both values to bracket the physics.

PHOTON STUDY NOTES
------------------------------------------------------------------------------
Photon cases use the simplified absorbed-photon surrogate in
`simulation.conf`:
- point-like charge deposition
- equivalent deposited charge approximated as E / 3.64eV in silicon
- fixed center-of-pixel, mid-depth interaction point

This is useful for transport and waveform sweeps, but it is not a full photon
interaction simulation. A future upgrade path is Geant4-based transport and
deposition.

GEOMETRY SWEEP NOTES
------------------------------------------------------------------------------
The detector instance and detector model are declared in `simulation.conf`.
This script materializes the detector and model snippets into `.runtime/` and
specializes the geometry per run via detector CLI overrides instead of
generating one detector-model file per sweep point.

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
import re
import shlex
import subprocess
import sys
import time
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Sequence


SCRIPT_DIR = Path(__file__).resolve().parent
OUTPUTS_DIR = SCRIPT_DIR / "outputs"
DEFAULT_ALLPIX_BIN = Path(
    os.environ.get("ALLPIX_BIN", "~/libs/allpix-squared/build/src/exec/allpix")
).expanduser()
DEFAULT_ROOT_SETUP = Path(
    os.environ.get("ROOT_SETUP", "~/libs/root/bin/thisroot.sh")
).expanduser()
DEFAULT_EVENTS = 1
UNIFIED_CONFIG = SCRIPT_DIR / "simulation.conf"
RUNTIME_DIR = SCRIPT_DIR / ".runtime"
RUNTIME_MAIN_CONFIG = RUNTIME_DIR / "simulation_allpix.conf"
RUNTIME_MAIN_CONFIG_REL = RUNTIME_MAIN_CONFIG.relative_to(SCRIPT_DIR)
RUNTIME_DETECTOR_CONFIG = RUNTIME_DIR / "detector.conf"
RUNTIME_MODEL_DIR = RUNTIME_DIR / "models"
RUNTIME_MODEL_FILE = RUNTIME_MODEL_DIR / "thin_pixel.conf"
OMIT_FROM_RUNTIME_DEPOSITION = frozenset(
    {
        "source_type",
        "position",
        "mip_direction",
        "number_of_charges",
        "number_of_steps",
    }
)


@lru_cache(maxsize=1)
def load_unified_config_sections() -> tuple[
    tuple[str, ...], tuple[tuple[str, tuple[str, ...]], ...]
]:
    if not UNIFIED_CONFIG.exists():
        raise FileNotFoundError(
            f"Unified sweep configuration not found at {UNIFIED_CONFIG}"
        )

    header_lines: list[str] = []
    sections: list[tuple[str, tuple[str, ...]]] = []
    current_name: str | None = None
    current_body: list[str] = []

    for line in UNIFIED_CONFIG.read_text(encoding="ascii").splitlines(keepends=True):
        stripped = line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            if current_name is None:
                if current_body:
                    header_lines.extend(current_body)
            else:
                sections.append((current_name, tuple(current_body)))
            current_name = stripped[1:-1]
            current_body = []
            continue
        current_body.append(line)

    if current_name is None:
        header_lines.extend(current_body)
    else:
        sections.append((current_name, tuple(current_body)))

    return tuple(header_lines), tuple(sections)


def _parse_sweep_annotation(line: str) -> tuple[str, ...]:
    match = re.search(r"#\s*Sweeping\s*->\s*\[(.*)\]\s*$", line)
    if match is None:
        return ()
    return tuple(
        item.strip().strip('"').strip("'")
        for item in match.group(1).split(",")
        if item.strip()
    )


def unified_value(section_name: str, key: str) -> str:
    _, sections = load_unified_config_sections()
    for name, body in sections:
        if name != section_name:
            continue
        for line in body:
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in stripped:
                continue
            left, right = line.split("=", 1)
            if left.strip() == key:
                return right.split("#", 1)[0].strip()
        raise ValueError(
            f"Key '{key}' not found in section [{section_name}] of {UNIFIED_CONFIG}"
        )
    raise ValueError(f"Section [{section_name}] not found in {UNIFIED_CONFIG}")


def unified_sweep_values(section_name: str, key: str) -> tuple[str, ...]:
    _, sections = load_unified_config_sections()
    for name, body in sections:
        if name != section_name:
            continue
        for line in body:
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in stripped:
                continue
            left, _ = line.split("=", 1)
            if left.strip() != key:
                continue
            values = _parse_sweep_annotation(line)
            if not values:
                raise ValueError(
                    f"Key '{key}' in section [{section_name}] is missing a '# Sweeping -> [...]' annotation"
                )
            return values
        raise ValueError(
            f"Key '{key}' not found in section [{section_name}] of {UNIFIED_CONFIG}"
        )
    raise ValueError(f"Section [{section_name}] not found in {UNIFIED_CONFIG}")


def _parse_suffixed_int(value: str, suffix: str) -> int:
    if not value.endswith(suffix):
        raise ValueError(f"Expected value ending with '{suffix}', got '{value}'")
    return int(value[: -len(suffix)])


def _parse_pitch_entry_um(value: str) -> int:
    parts = value.split()
    if len(parts) != 2 or parts[0] != parts[1]:
        raise ValueError(
            "pixel_size sweep entries must be symmetric 'Xum Xum' pairs in simulation.conf"
        )
    return _parse_suffixed_int(parts[0], "um")


@lru_cache(maxsize=1)
def load_sweep_axes() -> tuple[
    tuple[int, ...], tuple[int, ...], tuple[int, ...], tuple[int, ...]
]:
    pitches_um = tuple(
        _parse_pitch_entry_um(value)
        for value in unified_sweep_values("Model:thin_pixel", "pixel_size")
    )
    thicknesses_um = tuple(
        _parse_suffixed_int(value, "um")
        for value in unified_sweep_values("Model:thin_pixel", "sensor_thickness")
    )
    bias_voltages_v = tuple(
        _parse_suffixed_int(value, "V")
        for value in unified_sweep_values("ElectricFieldReader", "bias_voltage")
    )
    integration_times_ns = tuple(
        _parse_suffixed_int(value, "ns")
        for value in unified_sweep_values("TransientPropagation", "integration_time")
    )
    return pitches_um, thicknesses_um, bias_voltages_v, integration_times_ns


def materialize_runtime_inputs() -> None:
    header_lines, sections = load_unified_config_sections()

    main_lines = list(header_lines)
    detector_lines: list[str] = []
    model_lines: list[str] = []

    for section_name, body in sections:
        if section_name.startswith("Detector:"):
            detector_lines.append(f"[{section_name.split(':', 1)[1]}]\n")
            detector_lines.extend(body)
            if detector_lines and detector_lines[-1].strip():
                detector_lines.append("\n")
            continue

        if section_name.startswith("Model:"):
            model_lines.extend(body)
            if model_lines and model_lines[-1].strip():
                model_lines.append("\n")
            continue

        main_lines.append(f"[{section_name}]\n")
        if section_name == "DepositionPointCharge":
            for line in body:
                stripped = line.split("#", 1)[0].strip()
                if "=" in stripped:
                    key = stripped.split("=", 1)[0].strip()
                    if key in OMIT_FROM_RUNTIME_DEPOSITION:
                        continue
                main_lines.append(line)
        else:
            main_lines.extend(body)
        if main_lines and main_lines[-1].strip():
            main_lines.append("\n")

    if not detector_lines:
        raise ValueError(f"No [Detector:...] section found in {UNIFIED_CONFIG}")
    if not model_lines:
        raise ValueError(f"No [Model:...] section found in {UNIFIED_CONFIG}")

    RUNTIME_MODEL_DIR.mkdir(parents=True, exist_ok=True)
    RUNTIME_MAIN_CONFIG.write_text("".join(main_lines), encoding="ascii")
    RUNTIME_DETECTOR_CONFIG.write_text("".join(detector_lines), encoding="ascii")
    RUNTIME_MODEL_FILE.write_text("".join(model_lines), encoding="ascii")


@dataclass(frozen=True)
class SweepDefinition:
    particle: str
    label: str
    charge_override: str
    notes: str
    position_override: str | None = None
    source_type: str = "mip"
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
            str(RUNTIME_MAIN_CONFIG_REL),
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


ELECTRON_MIP_DIRECTION = unified_value(
    "DepositionPointCharge:electron", "mip_direction"
)
ELECTRON_NUMBER_OF_STEPS = int(
    unified_value("DepositionPointCharge:electron", "number_of_steps")
)
PHOTON_POSITION = unified_value("DepositionPointCharge:photon", "position")
ELECTRON_CHARGE_SWEEPS = unified_sweep_values(
    "DepositionPointCharge:electron", "number_of_charges"
)
PHOTON_CHARGE_SWEEPS = unified_sweep_values(
    "DepositionPointCharge:photon", "number_of_charges"
)

ELECTRON_SWEEP_METADATA: tuple[tuple[str, str], ...] = (
    ("e_100keV", "sub-MIP electron surrogate, high scatter"),
    ("e_200keV", "near-MIP electron surrogate"),
    ("e_1MeV", "MIP-minimum-like electron surrogate"),
    ("e_5MeV", "MIP-like electron surrogate"),
    ("e_100MeV", "relativistic-rise electron surrogate"),
    ("e_1GeV", "Fermi-plateau electron surrogate"),
    ("mip_mpv", "generic MIP most-probable-value bracket"),
    ("mip_thin_mpv", "thin-sensor MIP MPV bracket around 50um silicon"),
)

PHOTON_SWEEP_METADATA: tuple[tuple[str, str], ...] = (
    ("ph_1keV", "soft X-ray absorbed-photon surrogate"),
    ("ph_5keV", "mid-energy X-ray absorbed-photon surrogate"),
    ("ph_12keV", "12keV X-ray absorbed-photon surrogate"),
    ("ph_20keV", "harder X-ray absorbed-photon surrogate"),
)


def _build_electron_sweeps() -> tuple[SweepDefinition, ...]:
    if len(ELECTRON_CHARGE_SWEEPS) != len(ELECTRON_SWEEP_METADATA):
        raise ValueError(
            "Electron charge sweep annotation count in simulation.conf does not match ELECTRON_SWEEP_METADATA"
        )
    return tuple(
        SweepDefinition(
            particle="electron",
            label=label,
            charge_override=charge_override,
            notes=notes,
            mip_direction_override=ELECTRON_MIP_DIRECTION,
            number_of_steps_override=ELECTRON_NUMBER_OF_STEPS,
        )
        for (label, notes), charge_override in zip(
            ELECTRON_SWEEP_METADATA, ELECTRON_CHARGE_SWEEPS, strict=True
        )
    )


def _build_photon_sweeps() -> tuple[SweepDefinition, ...]:
    if len(PHOTON_CHARGE_SWEEPS) != len(PHOTON_SWEEP_METADATA):
        raise ValueError(
            "Photon charge sweep annotation count in simulation.conf does not match PHOTON_SWEEP_METADATA"
        )
    return tuple(
        SweepDefinition(
            particle="photon",
            label=label,
            charge_override=charge_override,
            notes=notes,
            position_override=PHOTON_POSITION,
            source_type="point",
        )
        for (label, notes), charge_override in zip(
            PHOTON_SWEEP_METADATA, PHOTON_CHARGE_SWEEPS, strict=True
        )
    )


# Effective electron deposition sweep points.
# Label          e-h pairs/um  Notes
ELECTRON_SWEEPS = _build_electron_sweeps()

# Effective photon deposition sweep points.
# Label      Energy   e-h pairs  Notes
PHOTON_SWEEPS = _build_photon_sweeps()

ALL_SWEEP_DEFINITIONS = ELECTRON_SWEEPS + PHOTON_SWEEPS


def build_cases() -> list[Case]:
    pitchs_um, thicknesses_um, bias_voltages_v, integration_times_ns = load_sweep_axes()
    cases: list[Case] = []
    for sweep in ALL_SWEEP_DEFINITIONS:
        for pitch_um in pitchs_um:
            for thickness_um in thicknesses_um:
                for bias_v in bias_voltages_v:
                    for integration_time_ns in integration_times_ns:
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
    required_files = (UNIFIED_CONFIG,)
    missing = [str(path) for path in required_files if not path.exists()]
    if missing:
        raise FileNotFoundError(
            "Missing required configuration inputs:\n  - " + "\n  - ".join(missing)
        )

    materialize_runtime_inputs()

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
            f"[{case.output_stem}, {RUNTIME_MAIN_CONFIG_REL.as_posix()}, q={case.sweep.charge_override}, "
            f"{case.sweep.notes}]"
        )


def run_case(
    case: Case, case_index: int, total_cases: int, events: int, dry_run: bool
) -> tuple[int, float]:
    print("-" * 78)
    print(f"[{case_index}/{total_cases}] {case.case_id}")
    print(f"  config: {RUNTIME_MAIN_CONFIG_REL.as_posix()}")
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
