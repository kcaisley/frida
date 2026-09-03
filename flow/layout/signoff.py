"""Technology-dispatched layout DRC, LVS, and PEX orchestration."""

from __future__ import annotations

import json
from dataclasses import dataclass
from importlib import import_module
from pathlib import Path
from typing import Any, Literal


@dataclass(frozen=True)
class SignoffParams:
    """Paths, top cells, and comparison policy for one complete signoff run."""

    technology: str
    gds_path: Path
    layout_top: str
    lvs_source_path: Path
    source_top: str
    output_stem: str
    pex_source_path: Path | None = None
    lvs_expectation: Literal["correct", "incorrect"] = "correct"
    lvs_required_report_fragments: tuple[str, ...] = ()
    pdk_options: Any = None


@dataclass(frozen=True)
class SignoffResult:
    """Persistent reports and status produced by one signoff run."""

    drc_report: Path
    lvs_report: Path
    lvs_correct: bool
    pex_netlist: Path
    warnings: tuple[str, ...] = ()


def _provider(technology: str) -> Any:
    if not technology or not technology.replace("_", "").isalnum():
        raise ValueError(f"invalid technology name {technology!r}")
    provider = import_module(f"pdk.{technology}.signoff")
    for function in ("run_drc", "run_lvs", "run_pex"):
        if not callable(getattr(provider, function, None)):
            raise TypeError(f"pdk.{technology}.signoff does not implement {function}()")
    return provider


def _validate(params: SignoffParams, run_dir: Path) -> None:
    if not params.layout_top or not params.source_top or not params.output_stem:
        raise ValueError("layout top, source top, and output stem must be nonempty")
    if params.lvs_expectation not in ("correct", "incorrect"):
        raise ValueError("lvs_expectation must be 'correct' or 'incorrect'")
    for path in (params.gds_path, params.lvs_source_path, params.pex_source_path or params.lvs_source_path):
        if not path.is_file():
            raise FileNotFoundError(path)
    if run_dir.resolve() == Path(__file__).resolve().parents[2]:
        raise ValueError("signoff must run beneath a dedicated result directory")


def run_drc(params: SignoffParams, run_dir: Path) -> Path:
    """Dispatch DRC, including the provider's mandatory fast precheck."""

    _validate(params, run_dir)
    return _provider(params.technology).run_drc(
        run_dir=run_dir,
        gds_path=params.gds_path,
        layout_top=params.layout_top,
        options=params.pdk_options,
    )


def run_lvs(params: SignoffParams, run_dir: Path) -> tuple[bool, Path]:
    """Dispatch LVS and return its raw correctness status and report."""

    _validate(params, run_dir)
    return _provider(params.technology).run_lvs(
        run_dir=run_dir,
        gds_path=params.gds_path,
        source_path=params.lvs_source_path,
        layout_top=params.layout_top,
        source_top=params.source_top,
        options=params.pdk_options,
    )


def run_pex(params: SignoffParams, run_dir: Path) -> Path:
    """Dispatch PEX using its explicit conductive source view."""

    _validate(params, run_dir)
    return _provider(params.technology).run_pex(
        run_dir=run_dir,
        gds_path=params.gds_path,
        source_path=params.pex_source_path or params.lvs_source_path,
        layout_top=params.layout_top,
        source_top=params.source_top,
        output_stem=params.output_stem,
        options=params.pdk_options,
    )


def run_signoff(params: SignoffParams, run_dir: Path) -> SignoffResult:
    """Run DRC, LVS, and PEX and enforce the declared LVS expectation."""

    run_dir.mkdir(parents=True, exist_ok=True)
    drc_report = run_drc(params, run_dir)
    lvs_correct, lvs_report = run_lvs(params, run_dir)
    report_text = lvs_report.read_text(encoding="utf-8", errors="replace")
    expected_correct = params.lvs_expectation == "correct"
    if lvs_correct != expected_correct:
        raise RuntimeError(f"LVS was expected to be {params.lvs_expectation}; see {lvs_report}")
    missing = [fragment for fragment in params.lvs_required_report_fragments if fragment not in report_text]
    if missing:
        raise RuntimeError(f"expected LVS mismatch signature is missing {missing}; see {lvs_report}")
    warnings = () if lvs_correct else ("expected LVS mismatch: disconnected historical MOM layer",)
    pex_netlist = run_pex(params, run_dir)
    result = SignoffResult(
        drc_report=drc_report,
        lvs_report=lvs_report,
        lvs_correct=lvs_correct,
        pex_netlist=pex_netlist,
        warnings=warnings,
    )
    (run_dir / "signoff_summary.json").write_text(
        json.dumps(
            {
                "technology": params.technology,
                "layout_top": params.layout_top,
                "source_top": params.source_top,
                "drc_report": str(drc_report),
                "lvs_report": str(lvs_report),
                "lvs_correct": lvs_correct,
                "pex_netlist": str(pex_netlist),
                "warnings": list(warnings),
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return result
