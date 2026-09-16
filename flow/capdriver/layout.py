"""Extract and sign off the unmodified FRIDA-1 capacitor driver (no PEX)."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
from dataclasses import replace
from datetime import datetime
from importlib import import_module
from pathlib import Path
from typing import Any

from flow.circuit.ports import module_from_ports, port_connections, scalar_connections
from flow.layout import signoff
from flow.util.netlist import _subcircuit_span, subcircuit_ports

from .subckt import driver_ports

ROOT = Path(__file__).resolve().parents[2]
# Flatten the canonical declaration, retaining the historical supply spelling.
DRIVER_PORTS = driver_ports(16)
LAYOUT_NAMES = {DRIVER_PORTS["vdd"].name: "vdd_dac", DRIVER_PORTS["vss"].name: "vss_dac"}
LAYOUT_PORTS = {
    name: replace(net.parent if hasattr(net, "parent") else net, name=name, width=1)
    for name, net in scalar_connections(
        {LAYOUT_NAMES.get(name, name): net for name, net in DRIVER_PORTS.items()}, brackets="<>"
    ).items()
}
PORTS = tuple(LAYOUT_PORTS)


def _sha256(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def _generate_source(run_dir: Path) -> dict[str, Any]:
    """Compile a fresh generic driver; retain upstream transistor model names."""
    import hdl21 as h

    from .subckt import CapDriver, CapDriverParams

    tsmc65 = import_module("pdk.tsmc65")
    site = import_module("pdk.tsmc65.site")
    driver = CapDriver(CapDriverParams(n_stages=16))
    driver.name = "generated_driver"
    strengths = [instance.of.params.drive_band for instance in driver.instances.values()]
    generic = io.StringIO()
    h.netlist(driver, generic, fmt="spice")
    generic_path = run_dir / "generated_driver.generic.cdl"
    generic_path.write_text(generic.getvalue(), encoding="utf-8")
    tsmc65.compile(driver)

    top = module_from_ports("capdriver", LAYOUT_PORTS)
    # Concat is MSB-first: canonical C0 connects to legacy physical bit 15.
    connections = {}
    for name, port in DRIVER_PORTS.items():
        connections[name] = (
            h.Concat(*(top.ports[f"{name}<{bit}>"] for bit in range(port.width)))
            if port.width > 1
            else top.ports[LAYOUT_NAMES.get(name, name)]
        )
    top.driver = driver(**port_connections(driver.ports, top, **connections))
    compiled = io.StringIO()
    h.netlist(top, compiled, fmt="spice")
    netlist = compiled.getvalue()
    if subcircuit_ports(netlist, "capdriver") != PORTS:
        raise RuntimeError("HDL21 netlisting changed the layout's scalar port names or order")
    library_path = Path(site.install.include_stdcell().path).resolve()
    library = library_path.read_text(encoding="utf-8")
    cells = ("CKXOR2D2LVT", "CKXOR2D4LVT")
    selected = []
    for name in cells:
        start, end = _subcircuit_span(library, name)
        selected.append(library[start:end])
    local_library = run_dir / "stdcells.cdl"
    local_library.write_text("\n\n".join(selected) + "\n", encoding="utf-8")
    source = run_dir / "capdriver.lvs.cdl"
    # Embed the exact selected definitions so LVS in lvs/ needs no include search path.
    source.write_text(netlist + "\n" + local_library.read_text(encoding="utf-8"), encoding="utf-8")
    return {
        "upstream_library": {"path": str(library_path), "sha256": _sha256(library_path)},
        "library_cells": list(cells),
        "files": {path.name: _sha256(path) for path in (generic_path, local_library, source)},
        "ports": list(PORTS),
        "index_mapping": [
            {"generic_stage": stage, "legacy_index": 15 - stage, "drive_band": band}
            for stage, band in enumerate(strengths)
        ],
        "model_policy": "Unmodified upstream ordinary models; no device mapping or waivers",
    }


def frida1(run_dir: Path, *, source_gds: Path | None = None) -> Path:
    """Export capdriver and descendants, then independently attempt DRC and LVS."""
    from klayout import db

    source_gds = (source_gds if source_gds is not None else ROOT / "build/frida-1.gds").resolve()
    if not source_gds.is_file():
        raise FileNotFoundError(source_gds)
    layout = db.Layout()
    layout.read(str(source_gds))
    cell = layout.cell("capdriver")
    if cell is None:
        raise ValueError(f"source GDS has no cell 'capdriver': {source_gds}")
    run_dir = run_dir.resolve()
    run_dir.mkdir(parents=True, exist_ok=False)
    gds = run_dir / "capdriver.gds"
    save = db.SaveLayoutOptions()
    save.set_format_from_filename(str(gds))
    save.add_cell(cell.cell_index())
    layout.write(str(gds), save)

    cells = sorted((layout.cell(index) for index in {cell.cell_index(), *cell.called_cells()}), key=lambda c: c.name)
    manifest = {
        "source_gds": {"path": str(source_gds), "sha256": _sha256(source_gds)},
        "export_gds": {"path": str(gds), "sha256": _sha256(gds)},
        "layout_top": cell.name,
        "bbox_um": str(cell.dbbox()),
        "dbu_um": layout.dbu,
        "cells": [item.name for item in cells],
        "labels": [
            {
                "cell": item.name,
                "layer": str(layout.get_info(layer)),
                "text": shape.text.string,
                "transform": str(shape.text.trans),
            }
            for item in cells
            for layer in layout.layer_indexes()
            for shape in item.shapes(layer).each()
            if shape.is_text()
        ],
    }
    summary = {"status": "failed", "errors": [], "drc": {"status": "not_run"}, "lvs": {"status": "not_run"}}
    try:
        manifest["source"] = _generate_source(run_dir)
        options = import_module("pdk.tsmc65.signoff").SignoffOptions()
        params = signoff.SignoffParams(
            technology="tsmc65",
            gds_path=gds,
            layout_top="capdriver",
            lvs_source_path=run_dir / "capdriver.lvs.cdl",
            source_top="capdriver",
            output_stem="capdriver",
            pdk_options=options,
        )
        for check in ("drc", "lvs"):
            check_dir = run_dir / check
            check_dir.mkdir()
            result = {"status": "failed", "directory": str(check_dir), "report": None}
            summary[check] = result
            try:
                if check == "drc":
                    report = signoff.run_drc(params, check_dir)
                else:
                    correct, report = signoff.run_lvs(params, check_dir)
                    result["correct"] = correct
                    result["report"] = str(report)
                    if not correct:
                        raise RuntimeError(f"LVS is INCORRECT; see {report}")
                result.update(status="passed", report=str(report))
            except Exception as exc:  # noqa: BLE001 - retain diagnostics and attempt the other check.
                result["error"] = f"{type(exc).__name__}: {exc}"
                summary["errors"].append(f"{check}: {result['error']}")
            finally:
                result["artifacts"] = [str(path) for path in sorted(check_dir.rglob("*")) if path.is_file()]
        if not summary["errors"]:
            summary["status"] = "passed"
    except Exception as exc:  # noqa: BLE001 - persist setup failures, then fail the target below.
        summary["errors"].append(f"{type(exc).__name__}: {exc}")
    finally:
        (run_dir / "provenance.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        (run_dir / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    if summary["status"] != "passed":
        raise RuntimeError(f"capdriver signoff failed; see {run_dir / 'summary.json'}: " + "; ".join(summary["errors"]))
    return run_dir


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("target", choices=("frida1",))
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--source-gds", type=Path)
    args = parser.parse_args()
    run_dir = args.output_dir or (
        ROOT / "build/layout/capdriver" / args.target / datetime.now().astimezone().strftime("%Y%m%d_%H%M%S")
    )
    print(frida1(run_dir, source_gds=args.source_gds))


if __name__ == "__main__":
    main()
