"""Export the viewer's data, or serve the viewer.

    uv run python -m flow.web export [--blocks schmitt bias] [--no-figures] [--workers 16]
    uv run python -m flow.web serve [--port 8765] [--host 127.0.0.1]

``serve`` answers ``/`` from ``flow/web/static``, ``/data/`` from ``build/web/data``, and
``/api/wave?path=<measurement>&record=<n>`` with one record of a cached measurement's waveforms
(read from its HDF5 file, under ``build/``); on a remote machine, forward the port
(``ssh -L 8765:localhost:8765 host``) and open http://localhost:8765.
"""

from __future__ import annotations

import argparse
import errno
import functools
import json
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from flow.web.export import BLOCKS, DATA_DIR, export, read_wave

STATIC_DIR = Path(__file__).resolve().parent / "static"


@functools.lru_cache(maxsize=32)
def wave_body(path: str, record: int) -> bytes:
    """A waveform record as JSON, kept for the next request."""
    return json.dumps(read_wave(path, record), separators=(",", ":")).encode()


class Handler(SimpleHTTPRequestHandler):
    """Static files from ``flow/web/static``, the exported data under ``/data/``, waveforms
    under ``/api/wave``."""

    def do_GET(self) -> None:
        url = urlsplit(self.path)
        if url.path != "/api/wave":
            super().do_GET()
            return
        query = parse_qs(url.query)
        try:
            body = wave_body(query["path"][0], int(query.get("record", ["0"])[0]))
        except (KeyError, ValueError, OSError) as error:
            self.send_error(404, str(error))
            return
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
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


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m flow.web", description=__doc__.splitlines()[0])
    commands = parser.add_subparsers(dest="command", required=True)
    export_parser = commands.add_parser("export", help="export cached results, layouts and schematics")
    export_parser.add_argument("--blocks", nargs="+", choices=list(BLOCKS), default=list(BLOCKS))
    export_parser.add_argument("--no-figures", action="store_true", help="skip the studies' SVG figures")
    export_parser.add_argument("--workers", type=int, default=16)
    serve_parser = commands.add_parser("serve", help="serve the viewer")
    serve_parser.add_argument("--port", type=int, default=8765)
    serve_parser.add_argument("--host", default="127.0.0.1")
    args = parser.parse_args()
    if args.command == "export":
        print(export(args.blocks, figures=not args.no_figures, workers=args.workers))
        return
    if not (DATA_DIR / "catalog.json").exists():
        raise SystemExit(f"no exported data in {DATA_DIR}: run `python -m flow.web export` first")
    try:
        server = ThreadingHTTPServer((args.host, args.port), functools.partial(Handler, directory=str(STATIC_DIR)))
    except OSError as error:
        if error.errno != errno.EADDRINUSE:
            raise
        raise SystemExit(
            f"port {args.port} is in use (another viewer?): stop it, or serve on another port (--port {args.port + 1})"
        ) from None
    print(f"frida viewer on http://{args.host}:{args.port} (data {DATA_DIR})", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.server_close()


if __name__ == "__main__":
    main()
