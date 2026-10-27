"""Technology-dispatched layout DRC, LVS, and PEX orchestration.

Each PDK provides ``pdk/<pdk>/signoff.py`` with keyword functions ``run_drc`` (gdscheck where
installed, then the PDK's DRC; writes ``<run_dir>/drc_violations.json`` and raises unless clean),
``run_lvs`` (whether LVS is correct, and its report) and, where the PDK has extraction,
``run_pex`` (against a schematic) and ``run_layout_pex`` (a layout by its own net names with the
kit's extractor, ``calibre_pex.py``). The provider picks the checker it has (Calibre, Assura or
KLayout). ``run_layout_pex`` here extracts by FasterCap through KLayout-PEX (``flow.layout.kpex``)
unless asked for the kit's (``Extractor.CALIBRE``, its manual check). ``row_signoff`` checks a
standard-cell row layout (flow/layout) with DRC and LVS.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, is_dataclass
from importlib import import_module
from pathlib import Path
from typing import Any, Literal

from klayout import db

from flow.layout import kpex
from flow.layout.kpex import Extractor
from flow.layout.pdkproc import in_pdk, pdk_value


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
    for function in ("run_drc", "run_lvs"):
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
    provider = _provider(params.technology)
    if not callable(getattr(provider, "run_pex", None)):
        raise TypeError(f"pdk.{params.technology}.signoff has no extraction (run_pex)")
    return provider.run_pex(
        run_dir=run_dir,
        gds_path=params.gds_path,
        source_path=params.pex_source_path or params.lvs_source_path,
        layout_top=params.layout_top,
        source_top=params.source_top,
        output_stem=params.output_stem,
        options=params.pdk_options,
    )


def run_layout_pex(
    technology: str,
    gds_path: Path,
    layout_top: str,
    output_stem: str,
    run_dir: Path,
    extractor: Extractor = Extractor.KLAYOUT,
) -> Path:
    """A layout-only extraction (3D, by the layout's own net names, nothing compared): FasterCap
    through KLayout-PEX (``flow.layout.kpex``), or the kit's extractor (``Extractor.CALIBRE``).

    For primitives' test structures and arrays: plain metal with labelled terminals has no device to
    recognize and no schematic. Returns the extracted Spectre netlist.
    """

    if not gds_path.is_file():
        raise FileNotFoundError(gds_path)
    if extractor is Extractor.KLAYOUT:
        return kpex.run_layout_pex(technology, gds_path, layout_top, output_stem, run_dir)
    provider = _provider(technology)
    if not callable(getattr(provider, "run_layout_pex", None)):
        raise TypeError(f"pdk.{technology}.signoff has no layout-only extraction (run_layout_pex)")
    return provider.run_layout_pex(run_dir=run_dir, gds_path=gds_path, layout_top=layout_top, output_stem=output_stem)


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
                "pex_sha256": hashlib.sha256(pex_netlist.read_bytes()).hexdigest(),
                "pdk_options": asdict(params.pdk_options) if is_dataclass(params.pdk_options) else None,
                "lvs_source_sha256": hashlib.sha256(params.lvs_source_path.read_bytes()).hexdigest(),
                "gds_sha256": hashlib.sha256(params.gds_path.read_bytes()).hexdigest(),
                "warnings": list(warnings),
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return result


@dataclass(frozen=True)
class RowSignoff:
    """DRC and LVS of a row layout: the rule counts (``drc_violations.json``) and the LVS report."""

    drc_report: Path
    drc_violations: int
    lvs_report: Path
    lvs_correct: bool


def add_post_devices(pdk: str, source: Path, extra: Path, top: str) -> None:
    """Merge what a post step added to a layout (``<gds>.extra.sp``, written by align/post.py:
    devices, ``*.PORTS``, ``*.DNW``) into the LVS ``source`` in place: the devices go into the
    subcircuit ``top``, the ports onto its .subckt line, and with ``*.DNW`` (a deep N-well under
    the block) every NMOS model becomes the variant the PDK's LVS deck extracts over a deep N-well
    (``tech.DNW_MODELS``)."""

    text = extra.read_text().splitlines()
    add = [line for line in text if line.strip() and not line.startswith("*")]
    ports = [port for line in text if line.upper().startswith("*.PORTS") for port in line.split()[1:]]
    dnw = any(line.upper().startswith("*.DNW") for line in text)
    out, inside = [], False
    for line in source.read_text().splitlines():
        f = line.split()
        if f and f[0].lower() == ".subckt" and f[1].lower() == top.lower():
            inside = True
            line = " ".join([line, *ports])
        elif inside and f and f[0].lower() == ".ends":
            out += add
            inside = False
        out.append(line)
    if dnw:
        models = {k.lower(): v for k, v in pdk_value(pdk, "tech", "DNW_MODELS", {}).items()}
        out = [
            " ".join(
                models.get(t.lower(), t) if i > 0 and line.split()[0][0] in "Mm" else t
                for i, t in enumerate(line.split())
            )
            if line.split()
            else line
            for line in out
        ]
    source.write_text("\n".join(out) + "\n")


def row_signoff(pdk: str, gds: Path, netlist: Path, floorplan: Path | None, run_dir: Path) -> RowSignoff:
    """DRC and LVS (no PEX) of a row layout, both run whatever the other finds.

    The LVS source is the netlist the build used (``netlist`` with the floorplan's ``split``; as it
    is without a floorplan, ALIGN on its own), with
    the library cells' subcircuits (``pdk/<pdk>/netlist/lvs_source.py``) and the devices a post step
    added (``<gds>.extra.sp``). Source top: the netlist's last subcircuit; layout top: the GDS's
    largest top cell. Writes ``row_signoff.json``; raises only when a checker fails to run.
    """

    run_dir.mkdir(parents=True, exist_ok=True)
    if floorplan is None:
        name, used = Path(gds).stem, Path(netlist).read_text()
    else:
        name, used = in_pdk(pdk, "netcells", "floorplan_netlist", floorplan, pdk, netlist)
    built = run_dir / f"{name}.sp"
    built.write_text(used)
    source = run_dir / "source.cdl"
    in_pdk(pdk, f"pdk.{pdk}.netlist.lvs_source", "lvs_source", built, source)
    source_top = [f[1] for f in map(str.split, used.splitlines()) if f and f[0].lower() == ".subckt"][-1]
    extra = Path(f"{gds}.extra.sp")
    if extra.exists():
        add_post_devices(pdk, source, extra, source_top)
    layout = db.Layout()
    layout.read(str(gds))
    layout_top = max(layout.top_cells(), key=lambda cell: cell.bbox().area()).name
    params = SignoffParams(
        technology=pdk,
        gds_path=gds,
        layout_top=layout_top,
        lvs_source_path=source,
        source_top=source_top,
        output_stem=name,
        pdk_options=getattr(_provider(pdk), "BLOCK_OPTIONS", None),
    )
    drc_report = run_dir / "drc_violations.json"
    try:
        run_drc(params, run_dir)
    except RuntimeError:
        if not drc_report.exists():  # the checker did not run to the end
            raise
    lvs_correct, lvs_report = run_lvs(params, run_dir)
    result = RowSignoff(
        drc_report, sum(json.loads(drc_report.read_text())["violations"].values()), lvs_report, lvs_correct
    )
    (run_dir / "row_signoff.json").write_text(
        json.dumps(
            {"gds": str(gds), "layout_top": layout_top, "source_top": source_top, **asdict(result)},
            indent=2,
            default=str,
        )
        + "\n"
    )
    return result
