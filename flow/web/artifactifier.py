"""The viewer as a page without its server: one run's table and some of its instances, every file the
page asks for written beside it, to publish as a claude.ai artifact (``python -m flow web.artifactify
<block> <run> [id,id...]``), where its comments reach the session that published it.

The viewer's own files (``static/``), its data under ``data/`` (the catalog holding the block and the
run alone, the run's table, each instance's files) and the server's answers under ``api/`` (each
instance's waveform records, figures and step logs, a file each, named by its query: ``apiUrl`` in
``static/js/store.js``). The page sets ``window.FRIDA_SNAPSHOT``, which opens it on the run and
instances given; a layout's GDS is not offered (no download from an artifact).
"""

from __future__ import annotations

import json
import re
import shutil
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

from flow.web.export import DATA_DIR
from flow.web.server import BUILD_DIR, STATIC_DIR, figure_body, log_body, wave_body

OUT_DIR = BUILD_DIR / "review" / "artifact"


# each answer's file type (``API_TYPES`` in ``store.js``)
API_TYPES = {"wave": "json", "log": "txt", "figure": "svg"}


def api_name(kind: str, params: dict[str, Any]) -> str:
    """The file holding the server's answer to ``/api/<kind>?<params>`` (``apiUrl``'s name)."""
    return f"api/{kind}/{re.sub(r'[^A-Za-z0-9._-]', '_', urlencode(params))}.{API_TYPES[kind]}"


def page(block: str, run: str, ids: list[str]) -> str:
    """The page's body (an artifact wraps it in its own document): the viewer's ``index.html``, opened
    on ``run``'s table, or its instances where ``ids``."""
    view = f"block={block}&run={run}" + (f"&ids={','.join(ids)}" if ids else "")
    # its name: the block, the run's name and the instances' PDKs (``tsmc65__<digest>``)
    title = " ".join([block, run.split("/")[0], *dict.fromkeys(ident.split("__")[0] for ident in ids)])
    return f"""<title>{title}</title>
<link rel="stylesheet" href="style.css">
<script>
    document.documentElement.dataset.theme = matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
    window.FRIDA_SNAPSHOT = {{ hash: {json.dumps(view)} }};
</script>
<script src="https://cdn.jsdelivr.net/npm/plotly.js-dist-min@2.35.2/plotly.min.js"></script>
<div id="app"></div>
<div id="loading"><div class="spinner"></div><span>Loading the sweep tables…</span></div>
<script type="module" src="js/app.js"></script>
"""


def _paths(found: Any, key: str) -> list[str]:
    """Every string under ``key`` anywhere in ``found``."""
    if isinstance(found, dict):
        return [
            *([found[key]] if isinstance(found.get(key), str) else []),
            *(path for value in found.values() for path in _paths(value, key)),
        ]
    if isinstance(found, list):
        return [path for value in found for path in _paths(value, key)]
    return []


def snapshot(block: str, run: str, ids: list[str], out: Path | None = None) -> Path:
    """Write the snapshot of ``block``'s ``run`` (its label, ``frida1/20261110_165725``) and its
    instances ``ids`` (every instance of the run where none) into ``out``; its page's path."""
    catalog = json.loads((DATA_DIR / "sweep/catalog.json").read_text())
    entry = next((each for each in catalog[block].get("runs", []) if each["label"] == run), None)
    if entry is None:
        raise SystemExit(f"no run {run} of {block} in the viewer's tables: run its table step first")
    table = json.loads((DATA_DIR / f"sweep/{entry['file']}.json").read_text())
    known = [row["id"] for row in table["rows"]]
    missing = [each for each in ids if each not in known]
    if missing:
        raise SystemExit(f"not in {block}'s run {run}: {', '.join(missing)}")
    out = out or OUT_DIR / block / run.replace("/", "_") / ("_".join(ids) or "all")
    shutil.rmtree(out, ignore_errors=True)
    shutil.copytree(STATIC_DIR, out, ignore=shutil.ignore_patterns("*.html"))
    (out / "index.html").write_text(page(block, run, ids))

    def put(name: str, body: bytes | str) -> None:
        path = out / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(body.encode() if isinstance(body, str) else body)

    put(
        "data/sweep/catalog.json",
        json.dumps({block: {**catalog[block], "runs": [entry], "default": run, "searches": {}}}),
    )
    put(f"data/sweep/{entry['file']}.json", json.dumps(table))
    folder = DATA_DIR / "sweep" / entry["file"]
    for ident in ids or known:
        for source in [*folder.glob(f"{ident}.*"), *(folder / ident).glob("*")]:
            put(f"data/{source.relative_to(DATA_DIR)}", source.read_bytes())
        instance = json.loads((folder / f"{ident}.json").read_text())
        traces = [json.loads(path.read_text()) for path in (folder / ident).glob("traces*.json")]
        for wave in {each["path"]: each for each in _waves(traces)}.values():
            for record in range(int(wave.get("records") or 1)):
                put(api_name("wave", {"path": wave["path"], "record": record}), wave_body(wave["path"], record))
        for figure in _paths(instance, "figure"):
            put(api_name("figure", {"path": figure}), figure_body(figure))
        for log in _paths(instance, "log_file"):
            try:
                put(api_name("log", {"path": log}), log_body(log))
            except (OSError, ValueError):
                continue
    return out / "index.html"


def _waves(found: Any) -> list[dict[str, Any]]:
    """Every trace entry (a dict with a ``path``) in the traces' indexes."""
    if isinstance(found, dict):
        return [found] if "path" in found else [each for value in found.values() for each in _waves(value)]
    if isinstance(found, list):
        return [each for value in found for each in _waves(value)]
    return []
