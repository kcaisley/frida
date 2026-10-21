"""The viewer's server: ``/`` from ``flow/web/static``, ``/data/`` from ``build/web/data``,
``/api/wave?path=<measurement>&record=<n>`` with one record of a cached measurement's waveforms
(read from its HDF5 file, under ``build/``), and ``/api/figure?path=<svg>`` with an instance's
figure (an SVG under ``build/sweep/``, drawn by its analysis plots). ``python -m flow web.serve``
serves it; on a remote machine, forward the port (``ssh -L 8765:localhost:8765 host``) and open
http://localhost:8765.
"""

from __future__ import annotations

import errno
import functools
import json
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from flow.web.export import DATA_DIR, read_wave

STATIC_DIR = Path(__file__).resolve().parent / "static"
FIGURES_DIR = Path(__file__).resolve().parents[2] / "build" / "sweep"


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


class Handler(SimpleHTTPRequestHandler):
    """Static files from ``flow/web/static``, the exported data under ``/data/``, waveforms
    under ``/api/wave``."""

    def do_GET(self) -> None:
        url = urlsplit(self.path)
        if url.path not in ("/api/wave", "/api/figure"):
            super().do_GET()
            return
        query = parse_qs(url.query)
        try:
            if url.path == "/api/figure":
                body, kind = figure_body(query["path"][0]), "image/svg+xml"
            else:
                body, kind = wave_body(query["path"][0], int(query.get("record", ["0"])[0])), "application/json"
        except (KeyError, ValueError, OSError) as error:
            self.send_error(404, str(error))
            return
        self.send_response(200)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def translate_path(self, path: str) -> str:
        if path.split("?", 1)[0].startswith("/data/"):
            relative = path.split("?", 1)[0].removeprefix("/data/")
            return SimpleHTTPRequestHandler.translate_path(self, "/" + relative).replace(
                str(STATIC_DIR), str(DATA_DIR), 1
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
