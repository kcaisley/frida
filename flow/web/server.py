"""The viewer's server: ``/`` from ``flow/web/static``, ``/data/`` from ``build/web/data``,
``/api/wave?path=<measurement>&record=<n>`` with one record of a cached measurement's waveforms
(read from its HDF5 file, under ``build/``), ``/api/figure?path=<svg>`` with an instance's
figure (an SVG under ``build/sweep/``, drawn by its analysis plots) and ``/api/gds?path=<gds>``
with a layout's GDS (under ``build/``) as a download. The layout compiler (``compile.html``) has
``/api/compile/...`` (``flow/web/jobs.py``) and its jobs' files under ``/data/compile/``.
``python -m flow web.serve`` serves it; on a remote machine, forward the port
(``ssh -L 8765:localhost:8765 host``) and open http://localhost:8765.
"""

from __future__ import annotations

import errno
import functools
import json
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from flow.web import jobs
from flow.web.export import DATA_DIR, read_wave

STATIC_DIR = Path(__file__).resolve().parent / "static"
BUILD_DIR = Path(__file__).resolve().parents[2] / "build"
FIGURES_DIR = BUILD_DIR / "sweep"
MAX_BODY = 1 << 20  # bytes of a POST body


@functools.lru_cache(maxsize=32)
def wave_body(path: str, record: int) -> bytes:
    """A waveform record as JSON, kept for the next request."""
    return json.dumps(read_wave(path, record), separators=(",", ":")).encode()


def figure_body(path: str) -> bytes:
    """An instance's SVG figure: only an ``.svg`` under ``build/sweep/``."""
    figure = (FIGURES_DIR.parent.parent / path).resolve()
    if figure.suffix != ".svg" or not figure.is_relative_to(FIGURES_DIR.resolve()):
        raise ValueError(f"not a sweep figure: {path}")
    return figure.read_bytes()


def gds_path(path: str) -> Path:
    """A layout's GDS: only a ``.gds`` under ``build/``."""
    gds = (BUILD_DIR.parent / path).resolve()
    if gds.suffix != ".gds" or not gds.is_relative_to(BUILD_DIR.resolve()) or not gds.is_file():
        raise ValueError(f"not a layout: {path}")
    return gds


class Handler(SimpleHTTPRequestHandler):
    """Static files from ``flow/web/static``, the exported data under ``/data/``, waveforms
    under ``/api/wave``, the layout compiler under ``/api/compile/``."""

    def do_GET(self) -> None:
        url = urlsplit(self.path)
        if url.path.startswith("/api/compile/"):
            self.compile_api("GET", url.path.removeprefix("/api/compile/"))
            return
        if url.path not in ("/api/wave", "/api/figure", "/api/gds"):
            super().do_GET()
            return
        query = parse_qs(url.query)
        headers = {}
        try:
            if url.path == "/api/figure":
                body, kind = figure_body(query["path"][0]), "image/svg+xml"
            elif url.path == "/api/gds":
                gds = gds_path(query["path"][0])
                body, kind = gds.read_bytes(), "application/octet-stream"
                headers["Content-Disposition"] = f'attachment; filename="{gds.name}"'
            else:
                body, kind = wave_body(query["path"][0], int(query.get("record", ["0"])[0])), "application/json"
        except (KeyError, ValueError, OSError) as error:
            self.send_error(404, str(error))
            return
        self.send_body(200, body, kind, headers)

    def do_POST(self) -> None:
        url = urlsplit(self.path)
        if not url.path.startswith("/api/compile/"):
            self.send_error(404)
            return
        self.compile_api("POST", url.path.removeprefix("/api/compile/"))

    def compile_api(self, method: str, route: str) -> None:
        """The layout compiler's routes (``flow/web/jobs.py``), JSON both ways."""
        parts = route.strip("/").split("/")
        try:
            body = {}
            if method == "POST":
                length = int(self.headers.get("Content-Length") or 0)
                if length > MAX_BODY:
                    raise ValueError("the request is too large")
                body = json.loads(self.rfile.read(length) or b"{}") if length else {}
                if not isinstance(body, dict):
                    raise ValueError("the request is a JSON object")
            if method == "GET" and parts == ["pdks"]:
                answer = jobs.pdks()
            elif method == "POST" and parts == ["check"]:
                answer = jobs.check(body)
            elif parts == ["jobs"]:
                answer = jobs.jobs() if method == "GET" else {"id": jobs.submit(body)}
            elif method == "GET" and len(parts) == 2 and parts[0] == "jobs":
                answer = jobs.status(parts[1])
            elif method == "POST" and len(parts) == 3 and parts[0] == "jobs" and parts[2] == "cancel":
                jobs.cancel(parts[1])
                answer = {"ok": True}
            else:
                self.send_json(404, {"error": f"no route {method} /api/compile/{route}"})
                return
        except KeyError as error:
            self.send_json(404, {"error": str(error.args[0] if error.args else error)})
            return
        except (TypeError, ValueError) as error:  # a JSONDecodeError is a ValueError
            diagnostics = error.args[1] if len(error.args) > 1 else []
            self.send_json(400, {"error": str(error.args[0] if error.args else error), "diagnostics": diagnostics})
            return
        self.send_json(200, answer)

    def send_json(self, code: int, value) -> None:
        self.send_body(code, json.dumps(value, separators=(",", ":")).encode(), "application/json")

    def send_body(self, code: int, body: bytes, kind: str, headers: dict[str, str] | None = None) -> None:
        self.send_response(code)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(len(body)))
        for key, value in (headers or {}).items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(body)

    def translate_path(self, path: str) -> str:
        path = path.split("?", 1)[0]
        for prefix, directory in (("/data/compile/", jobs.JOBS_DIR), ("/data/", DATA_DIR)):
            if path.startswith(prefix):
                relative = path.removeprefix(prefix)
                return SimpleHTTPRequestHandler.translate_path(self, "/" + relative).replace(
                    str(STATIC_DIR), str(directory), 1
                )
        return super().translate_path(path)

    def end_headers(self) -> None:
        self.send_header("Cache-Control", "no-cache")
        super().end_headers()

    def log_message(self, format: str, *args) -> None:
        if not str(args[1] if len(args) > 1 else "").startswith(("2", "3")):
            super().log_message(format, *args)


def serve(port: int, host: str) -> None:
    """Serve the viewer on ``host:port`` until interrupted; the sweep tables must exist
    (``python -m flow web.tables``)."""

    if not (DATA_DIR / "sweep/catalog.json").exists():
        raise SystemExit(f"no sweep tables in {DATA_DIR / 'sweep'}: run `python -m flow web.tables` first")
    try:
        server = ThreadingHTTPServer((host, port), functools.partial(Handler, directory=str(STATIC_DIR)))
    except OSError as error:
        if error.errno != errno.EADDRINUSE:
            raise
        raise SystemExit(
            f"port {port} is in use (another viewer?): stop it, or serve on another port "
            f"(flow.web.server.serve({port + 1}, {host!r}))"
        ) from None
    print(f"frida viewer on http://{host}:{port} (data {DATA_DIR})", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.server_close()
