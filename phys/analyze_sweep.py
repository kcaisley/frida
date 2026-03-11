#!/usr/bin/env python3
"""
analyze_sweep.py -- Analyze transient-oriented Allpix Squared sweep results

This script targets the transient `phys/outputs/` layouts where each run is
stored either as:

    phys/outputs/<run_name>/data.root
    phys/outputs/<run_name>/modules.root
    phys/outputs/<run_name>/allpix.log

or as flat files in one shared output directory:

    phys/outputs/<run_name>_data.root
    phys/outputs/<run_name>_modules.root
    phys/outputs/<run_name>_allpix.log

The script is intentionally conservative:
1. It works even if some expected ROOT trees are missing.
2. It reports what it can find instead of assuming a rigid schema.
3. It derives study-level occupancy estimates from fluence and frame time.

Usage:
    env ROOTSYS="$HOME/libs/root" bash -lc '. "$HOME/libs/root/bin/thisroot.sh"; python3 analyze_sweep.py'

Optional environment variables:
    FRAME_TIME_S=1e-3
    FLUENCE_CM2_S=1e8
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import asdict, dataclass, field
from typing import Optional

try:
    import ROOT

    ROOT.gROOT.SetBatch(True)
except ImportError:
    print("ERROR: PyROOT not found. Initialize the ROOT environment first:")
    print(
        '  env ROOTSYS="$HOME/libs/root" bash -lc \'. "$HOME/libs/root/bin/thisroot.sh"; python3 phys/analyze_sweep.py\''
    )
    sys.exit(1)

_ALLPIX_LIB = os.path.expanduser(
    "~/libs/allpix-squared/build/src/objects/libAllpixObjects.so"
)
if os.path.exists(_ALLPIX_LIB):
    ROOT.gSystem.Load(_ALLPIX_LIB)
else:
    print(f"WARNING: allpix dictionary not found at {_ALLPIX_LIB}")
    print("         Object deserialization may fail for some trees/branches.")


# =============================================================================
# Configuration
# =============================================================================
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUTS_DIR = os.path.join(SCRIPT_DIR, "outputs")
PLOTS_DIR = os.path.join(SCRIPT_DIR, "plots")
REPORTS_DIR = os.path.join(SCRIPT_DIR, "reports")
SUMMARY_JSON = os.path.join(REPORTS_DIR, "summary.json")

DEFAULT_PIXEL_PITCH_UM = 50.0
DEFAULT_NPIX_X = 16
DEFAULT_NPIX_Y = 16
SI_CHARGE_CREATION_EV = 3.64

FRAME_TIME_S = float(os.environ.get("FRAME_TIME_S", "1e-3"))
FLUENCE_CM2_S = float(os.environ.get("FLUENCE_CM2_S", "1e8"))


@dataclass
class RunSummary:
    run_path: str
    run_name: str
    data_root_exists: bool
    modules_root_exists: bool
    allpix_log_exists: bool
    n_events_event_tree: int = 0
    n_entries_pixelcharge: int = 0
    n_entries_pixelhit: int = 0
    n_entries_propagatedcharge: int = 0
    n_entries_depositedcharge: int = 0
    total_pixelcharge_objects: int = 0
    total_pixelhit_objects: int = 0
    mean_pixel_signal_e: Optional[float] = None
    max_pixel_signal_e: Optional[float] = None
    pulse_graph_count: int = 0
    pulse_graph_names: list[str] = field(default_factory=list)
    inferred_pixel_pitch_um: float = DEFAULT_PIXEL_PITCH_UM
    inferred_npix_x: int = DEFAULT_NPIX_X
    inferred_npix_y: int = DEFAULT_NPIX_Y
    hits_per_pixel_per_frame: Optional[float] = None
    notes: list[str] = field(default_factory=list)


@dataclass
class RunArtifacts:
    run_path: str
    run_name: str
    data_root: str
    modules_root: str
    allpix_log: str


# =============================================================================
# Utility helpers
# =============================================================================
def ensure_dirs() -> None:
    os.makedirs(PLOTS_DIR, exist_ok=True)
    os.makedirs(REPORTS_DIR, exist_ok=True)


def iter_run_artifacts(base_dir: str) -> list[RunArtifacts]:
    """
    Collect runs from either hierarchical output directories or flattened file
    sets living directly in the outputs directory.
    """
    runs: list[RunArtifacts] = []
    flat_groups: dict[str, dict[str, str]] = {}

    if not os.path.isdir(base_dir):
        return runs

    for root, _, files in os.walk(base_dir):
        if {"data.root", "modules.root", "allpix.log"} & set(files):
            rel_path = os.path.relpath(root, SCRIPT_DIR)
            run_name = os.path.relpath(root, OUTPUTS_DIR).replace(os.sep, "/")
            runs.append(
                RunArtifacts(
                    run_path=rel_path,
                    run_name=run_name,
                    data_root=os.path.join(root, "data.root"),
                    modules_root=os.path.join(root, "modules.root"),
                    allpix_log=os.path.join(root, "allpix.log"),
                )
            )

        for file_name in files:
            matched_kind = None
            stem = None
            if file_name.endswith("_data.root"):
                matched_kind = "data_root"
                stem = file_name.removesuffix("_data.root")
            elif file_name.endswith("_modules.root"):
                matched_kind = "modules_root"
                stem = file_name.removesuffix("_modules.root")
            elif file_name.endswith("_allpix.log"):
                matched_kind = "allpix_log"
                stem = file_name.removesuffix("_allpix.log")

            if matched_kind is None or stem is None:
                continue

            group_key = os.path.join(root, stem)
            group = flat_groups.setdefault(group_key, {})
            group[matched_kind] = os.path.join(root, file_name)

    for group_key, group in flat_groups.items():
        rel_group = os.path.relpath(group_key, OUTPUTS_DIR).replace(os.sep, "/")
        runs.append(
            RunArtifacts(
                run_path=os.path.relpath(group_key, SCRIPT_DIR),
                run_name=rel_group,
                data_root=group.get("data_root", ""),
                modules_root=group.get("modules_root", ""),
                allpix_log=group.get("allpix_log", ""),
            )
        )

    return sorted(runs, key=lambda run: run.run_name)


def safe_get_tree(root_file, tree_name: str):
    obj = root_file.Get(tree_name)
    if not obj:
        return None
    if not hasattr(obj, "GetEntries"):
        return None
    return obj


def list_keys(root_dir) -> list[str]:
    return [key.GetName() for key in root_dir.GetListOfKeys()]


def collect_tgraph_names_recursive(root_dir, prefix: str = "") -> list[str]:
    out: list[str] = []
    for key in root_dir.GetListOfKeys():
        name = key.GetName()
        obj = key.ReadObj()
        full_name = f"{prefix}/{name}" if prefix else name

        inherits_tgraph = hasattr(obj, "InheritsFrom") and (
            obj.InheritsFrom("TGraph")
            or obj.InheritsFrom("TGraphErrors")
            or obj.InheritsFrom("TGraphAsymmErrors")
        )
        if inherits_tgraph:
            out.append(full_name)

        if hasattr(obj, "GetListOfKeys"):
            out.extend(collect_tgraph_names_recursive(obj, full_name))
    return out


def _parse_numeric_tokens(text: str) -> list[float]:
    values: list[float] = []
    for token in text.replace(",", " ").split():
        cleaned = (
            token.replace("um", "")
            .replace("mm", "")
            .replace("cm", "")
            .replace("V", "")
            .strip()
        )
        try:
            values.append(float(cleaned))
        except ValueError:
            continue
    return values


def try_extract_detector_metadata(data_file, summary: RunSummary) -> None:
    """
    Try to infer detector metadata from ROOTObjectWriter detector/config metadata.
    Fall back gracefully if unavailable.
    """
    try:
        det_dir = data_file.GetDirectory("detectors/dut")
        if not det_dir:
            summary.notes.append(
                "No detectors/dut metadata directory found in data.root"
            )
            return

        summary.notes.append(f"detectors/dut keys: {', '.join(list_keys(det_dir))}")

        model_dir = data_file.GetDirectory("detectors/dut/model")
        if not model_dir:
            summary.notes.append("No detectors/dut/model metadata directory found")
            return

        model_keys = list_keys(model_dir)

        if "pixel_size" in model_keys:
            try:
                obj = model_dir.Get("pixel_size")
                nums = _parse_numeric_tokens(str(obj))
                if nums:
                    summary.inferred_pixel_pitch_um = nums[0]
            except Exception as exc:
                summary.notes.append(f"Could not parse pixel_size metadata: {exc}")

        if "number_of_pixels" in model_keys:
            try:
                obj = model_dir.Get("number_of_pixels")
                vals = [int(v) for v in _parse_numeric_tokens(str(obj))]
                if len(vals) >= 2:
                    summary.inferred_npix_x = vals[0]
                    summary.inferred_npix_y = vals[1]
            except Exception as exc:
                summary.notes.append(
                    f"Could not parse number_of_pixels metadata: {exc}"
                )

    except Exception as exc:
        summary.notes.append(f"Detector metadata extraction failed: {exc}")


def try_analyze_pixelhit_tree(data_file, summary: RunSummary) -> None:
    tree = safe_get_tree(data_file, "PixelHit")
    if tree is None:
        summary.notes.append("No PixelHit tree found")
        return

    summary.n_entries_pixelhit = int(tree.GetEntries())
    total_hits = 0
    signals: list[float] = []

    branch_names = [br.GetName() for br in tree.GetListOfBranches()]
    detector_branch = (
        "dut" if "dut" in branch_names else (branch_names[0] if branch_names else None)
    )

    if detector_branch is None:
        summary.notes.append("PixelHit tree has no readable branches")
        return

    for i in range(summary.n_entries_pixelhit):
        tree.GetEntry(i)
        hits = getattr(tree, detector_branch, None)
        if hits is None:
            continue
        try:
            size = hits.size()
        except Exception:
            continue

        total_hits += size
        for j in range(size):
            try:
                hit = hits[j]
                if hasattr(hit, "getSignal"):
                    signals.append(float(hit.getSignal()))
            except Exception:
                continue

    summary.total_pixelhit_objects = total_hits
    if signals:
        summary.mean_pixel_signal_e = sum(signals) / len(signals)
        summary.max_pixel_signal_e = max(signals)


def try_analyze_pixelcharge_tree(data_file, summary: RunSummary) -> None:
    tree = safe_get_tree(data_file, "PixelCharge")
    if tree is None:
        summary.notes.append("No PixelCharge tree found")
        return

    summary.n_entries_pixelcharge = int(tree.GetEntries())
    total_objs = 0
    charges: list[float] = []

    branch_names = [br.GetName() for br in tree.GetListOfBranches()]
    detector_branch = (
        "dut" if "dut" in branch_names else (branch_names[0] if branch_names else None)
    )

    if detector_branch is None:
        summary.notes.append("PixelCharge tree has no readable branches")
        return

    for i in range(summary.n_entries_pixelcharge):
        tree.GetEntry(i)
        objs = getattr(tree, detector_branch, None)
        if objs is None:
            continue
        try:
            size = objs.size()
        except Exception:
            continue

        total_objs += size
        for j in range(size):
            try:
                obj = objs[j]
                if hasattr(obj, "getCharge"):
                    charges.append(float(obj.getCharge()))
                elif hasattr(obj, "getSignal"):
                    charges.append(float(obj.getSignal()))
            except Exception:
                continue

    summary.total_pixelcharge_objects = total_objs
    if charges:
        if summary.mean_pixel_signal_e is None:
            summary.mean_pixel_signal_e = sum(charges) / len(charges)
        if summary.max_pixel_signal_e is None:
            summary.max_pixel_signal_e = max(charges)


def try_count_other_trees(data_file, summary: RunSummary) -> None:
    for name, attr in [
        ("Event", "n_events_event_tree"),
        ("PropagatedCharge", "n_entries_propagatedcharge"),
        ("DepositedCharge", "n_entries_depositedcharge"),
    ]:
        tree = safe_get_tree(data_file, name)
        if tree is not None:
            setattr(summary, attr, int(tree.GetEntries()))


def compute_study_level_metrics(summary: RunSummary) -> None:
    pixel_area_cm2 = (summary.inferred_pixel_pitch_um * 1e-4) ** 2
    summary.hits_per_pixel_per_frame = FLUENCE_CM2_S * pixel_area_cm2 * FRAME_TIME_S


def analyze_one_run(run: RunArtifacts) -> RunSummary:
    summary = RunSummary(
        run_path=run.run_path,
        run_name=run.run_name,
        data_root_exists=os.path.exists(run.data_root),
        modules_root_exists=os.path.exists(run.modules_root),
        allpix_log_exists=os.path.exists(run.allpix_log),
    )

    if summary.data_root_exists:
        f = ROOT.TFile.Open(run.data_root, "READ")
        if f and not f.IsZombie():
            try_extract_detector_metadata(f, summary)
            try_count_other_trees(f, summary)
            try_analyze_pixelcharge_tree(f, summary)
            try_analyze_pixelhit_tree(f, summary)
            f.Close()
        else:
            summary.notes.append("Could not open data.root")

    if summary.modules_root_exists:
        f = ROOT.TFile.Open(run.modules_root, "READ")
        if f and not f.IsZombie():
            try:
                graphs = collect_tgraph_names_recursive(f)
                summary.pulse_graph_names = graphs
                summary.pulse_graph_count = len(graphs)
            except Exception as exc:
                summary.notes.append(
                    f"Could not scan modules.root for pulse graphs: {exc}"
                )
            f.Close()
        else:
            summary.notes.append("Could not open modules.root")

    compute_study_level_metrics(summary)
    return summary


# =============================================================================
# Reporting
# =============================================================================
def print_summary_table(results: list[RunSummary]) -> None:
    print("\n" + "=" * 140)
    print("TRANSIENT SWEEP SUMMARY")
    print("=" * 140)
    print(f"Outputs directory: {OUTPUTS_DIR}")
    print(f"Assumed fluence    : {FLUENCE_CM2_S:.3e} /cm^2/s")
    print(f"Assumed frame time : {FRAME_TIME_S:.3e} s")
    print("-" * 140)
    print(
        f"{'Run':<54} {'data.root':>10} {'modules.root':>12} {'Events':>8} "
        f"{'PixCharge':>10} {'PixHit':>8} {'MeanSig[e]':>12} "
        f"{'PulseGraphs':>12} {'Hits/px/frame':>14}"
    )
    print("-" * 140)

    for r in results:
        mean_sig = (
            f"{r.mean_pixel_signal_e:.1f}"
            if r.mean_pixel_signal_e is not None
            else "n/a"
        )
        hppf = (
            f"{r.hits_per_pixel_per_frame:.4f}"
            if r.hits_per_pixel_per_frame is not None
            else "n/a"
        )
        print(
            f"{r.run_name:<54} "
            f"{str(r.data_root_exists):>10} "
            f"{str(r.modules_root_exists):>12} "
            f"{r.n_events_event_tree:>8d} "
            f"{r.total_pixelcharge_objects:>10d} "
            f"{r.total_pixelhit_objects:>8d} "
            f"{mean_sig:>12} "
            f"{r.pulse_graph_count:>12d} "
            f"{hppf:>14}"
        )

    print("=" * 140)


def print_run_details(results: list[RunSummary]) -> None:
    print("\nDETAILED RUN NOTES")
    print("=" * 140)
    for r in results:
        print(f"\n[{r.run_name}]")
        print(f"  path                  : {r.run_path}")
        print(f"  inferred pixel pitch  : {r.inferred_pixel_pitch_um:.1f} um")
        print(f"  inferred matrix       : {r.inferred_npix_x} x {r.inferred_npix_y}")
        print(f"  pixelcharge tree ent. : {r.n_entries_pixelcharge}")
        print(f"  pixelhit tree ent.    : {r.n_entries_pixelhit}")
        print(f"  propagatedcharge ent. : {r.n_entries_propagatedcharge}")
        print(f"  depositedcharge ent.  : {r.n_entries_depositedcharge}")
        print(f"  pulse graph count     : {r.pulse_graph_count}")
        if r.pulse_graph_names:
            preview = r.pulse_graph_names[:10]
            print("  pulse graph examples  :")
            for name in preview:
                print(f"    - {name}")
            if len(r.pulse_graph_names) > len(preview):
                print(f"    ... ({len(r.pulse_graph_names) - len(preview)} more)")
        if r.notes:
            print("  notes:")
            for note in r.notes:
                print(f"    - {note}")


def write_json_summary(results: list[RunSummary]) -> None:
    with open(SUMMARY_JSON, "w", encoding="utf-8") as f:
        json.dump([asdict(r) for r in results], f, indent=2)
    print(f"\nWrote summary JSON: {SUMMARY_JSON}")


# =============================================================================
# Main
# =============================================================================
def main() -> int:
    ensure_dirs()

    runs = iter_run_artifacts(OUTPUTS_DIR)
    if not runs:
        print(f"ERROR: no run directories found in {OUTPUTS_DIR}")
        print("Expected one of these layouts:")
        print("  phys/outputs/<particle>/<label>/<sweep_point>/data.root")
        print("  phys/outputs/<particle>/<label>/<sweep_point>/modules.root")
        print("  phys/outputs/<particle>/<label>/<sweep_point>/allpix.log")
        print("  phys/outputs/<run_name>_data.root")
        print("  phys/outputs/<run_name>_modules.root")
        print("  phys/outputs/<run_name>_allpix.log")
        return 1

    results = [analyze_one_run(run) for run in runs]

    print_summary_table(results)
    print_run_details(results)
    write_json_summary(results)

    print("\nDone.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
