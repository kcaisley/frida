"""The layout compiler's routes on the viewer's server (``flow/web/server.py``, ``flow/web/jobs.py``),
on a made-up PDK: nothing is laid out."""

from __future__ import annotations

import functools
import json
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

from flow.layout import lint
from flow.web import jobs
from flow.web.server import STATIC_DIR, Handler, gds_path

MANIFEST = {"models": {"n": "nfet_row", "p": "pfet_row"}, "cells": {}}


@pytest.fixture
def server(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(jobs, "manifest", lambda pdk: MANIFEST)
    monkeypatch.setattr(jobs, "_unavailable", lambda pdk: None)
    monkeypatch.setattr(jobs, "CHECK_DIR", tmp_path / "check")
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(Handler, directory=str(STATIC_DIR)))
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}"
    httpd.shutdown()


def call(url: str, body: dict | None = None) -> tuple[int, dict]:
    data = None if body is None else json.dumps(body).encode()
    try:
        with urllib.request.urlopen(urllib.request.Request(url, data=data)) as response:
            return response.status, json.loads(response.read())
    except urllib.error.HTTPError as error:
        return error.code, json.loads(error.read())


def test_the_check_answers_diagnostics_stats_and_a_schematic(server: str, tmp_path: Path) -> None:
    code, answer = call(f"{server}/api/compile/check", {"netlist": lint.example(MANIFEST), "pdk": "ihp130"})
    assert code == 200 and answer["ok"] and answer["top"] == "ota5t" and answer["diagnostics"] == []
    assert answer["schematic"].startswith("compile/check/") and answer["schematic"].endswith(".svg")
    assert (tmp_path / "check" / Path(answer["schematic"]).name).read_text().lstrip().startswith("<")
    code, answer = call(f"{server}/api/compile/check", {"netlist": ".subckt a x\n.ends\n", "pdk": "ihp130"})
    assert code == 200 and not answer["ok"] and answer["schematic"] is None


def test_bad_requests_are_400_and_unknown_routes_and_jobs_404(server: str) -> None:
    assert call(f"{server}/api/compile/check", {"netlist": 3, "pdk": "ihp130"})[0] == 400
    assert call(f"{server}/api/compile/check", {"netlist": "", "pdk": "nopdk"})[0] == 400
    code, answer = call(f"{server}/api/compile/jobs", {"netlist": ".subckt a x\n.ends\n", "pdk": "ihp130"})
    assert code == 400 and answer["diagnostics"]  # a netlist with errors is not queued
    assert call(f"{server}/api/compile/jobs/20990101_000000_none")[0] == 404
    assert call(f"{server}/api/compile/jobs/..%2F..%2Fetc")[0] == 404
    assert call(f"{server}/api/compile/nothing")[0] == 404


def test_job_files_come_from_build_compile_and_gds_only_from_build() -> None:
    handler = Handler.__new__(Handler)
    handler.directory = str(STATIC_DIR)
    assert Path(handler.translate_path("/data/compile/x/layout.json")) == jobs.JOBS_DIR / "x/layout.json"
    assert Path(handler.translate_path("/data/compile/../../../etc/passwd")).is_relative_to(jobs.JOBS_DIR)
    for path in ("flow/web/server.py", "build/../flow/web/server.py", "/etc/passwd", "build/none.gds"):
        with pytest.raises(ValueError):
            gds_path(path)
