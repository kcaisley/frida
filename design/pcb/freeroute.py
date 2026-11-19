"""Autoroute a KiCad board with FreeRouting, on this machine.

    uv run --no-project --python 3.12 python design/pcb/freeroute.py BOARD.kicad_pcb [-o ROUTED.kicad_pcb]
        [--passes N] [--threads N] [--minutes N]

KiCad writes the board as a Specctra design (.dsn), FreeRouting routes it without its window and
writes a session (.ses), and KiCad reads the session back into the board: the tracks and vias it
had stay, the routed ones are added. Without ``-o`` the board itself is updated.

The three tools are the pinned ones (``[tool.kicad.install]``, ``[tool.freerouting.install]`` and
``[tool.temurin.install]`` in pyproject.toml), fetched by tools/check.py on first use. FreeRouting
runs with its usage reporting off, and keeps its settings and log in the run's own folder (the
main checkout's build/freeroute/<board>) instead of the shared temporary directory.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
import check

# run by KiCad's own Python, which has its pcbnew module; each prints the board's copper as JSON
COUNT = """
def count(board):
    board.BuildConnectivity()
    tracks = list(board.GetTracks())
    vias = sum(1 for track in tracks if track.Type() == pcbnew.PCB_VIA_T)
    opens = board.GetConnectivity().GetUnconnectedCount(False)
    print(json.dumps({"segments": len(tracks) - vias, "vias": vias, "open": opens}))
"""
EXPORT = (
    "import json, sys, pcbnew"
    + COUNT
    + """
board = pcbnew.LoadBoard(sys.argv[1])
if not pcbnew.ExportSpecctraDSN(board, sys.argv[2]):
    sys.exit(1)
count(board)
"""
)
IMPORT = (
    "import json, sys, pcbnew"
    + COUNT
    + """
board = pcbnew.LoadBoard(sys.argv[1])
if not pcbnew.ImportSpecctraSES(board, sys.argv[2]):
    sys.exit(1)
pcbnew.SaveBoard(sys.argv[3], board)
count(board)
"""
)


def kicad() -> Path:
    """The pinned KiCad's unpacked AppImage (unpacked on first use, so it runs without FUSE)."""

    root = check.install("kicad")
    if not (root / "AppDir").exists():
        image = next(root.glob("kicad-*.AppImage"))
        subprocess.run([str(image), "--appimage-extract"], cwd=root, check=True, capture_output=True)
    return root / "AppDir"


def copper(python: str, script: str, *arguments: Path) -> dict[str, int]:
    """Run one of the scripts above under KiCad's Python; its last line is the board's copper:
    track segments, vias and connections still open."""

    done = subprocess.run([python, "-c", script, *map(str, arguments)], check=True, capture_output=True, text=True)
    return json.loads(done.stdout.strip().splitlines()[-1])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("board", type=Path)
    parser.add_argument("-o", "--output", type=Path, help="the routed board (default: the board itself)")
    parser.add_argument("--passes", type=int, default=20, help="the most routing passes (default 20)")
    parser.add_argument("--threads", type=int, default=8, help="threads for the optimization (default 8)")
    parser.add_argument(
        "--minutes", type=int, default=30, help="stop routing after this long and keep the best (default 30)"
    )
    options = parser.parse_args()

    board = options.board.resolve()
    output = (options.output or options.board).resolve()
    work = Path(check.TOOLS).parent / "freeroute" / board.stem
    work.mkdir(parents=True, exist_ok=True)
    design, session = work / f"{board.stem}.dsn", work / f"{board.stem}.ses"
    session.unlink(missing_ok=True)

    appdir = kicad()
    python = str(appdir / "bin" / "python3.11")
    java = check.install("temurin") / "bin" / "java"
    jar = next(check.install("freerouting").glob("freerouting-*.jar"))

    before = copper(python, EXPORT, board, design)

    command = [
        str(java),
        f"-Djava.io.tmpdir={work}",
        "-jar",
        str(jar),
        "-de",
        str(design),
        "-do",
        str(session),
        "-mp",
        str(options.passes),
        "-mt",
        str(options.threads),
        "--gui.enabled=false",
        "--usage_and_diagnostic_data.disable_analytics=true",
        "--profile.allow_telemetry=false",
        f"--router.job_timeout={options.minutes // 60:02d}:{options.minutes % 60:02d}:00",
    ]
    version = jar.stem.split("-")[1]
    print(
        f"FreeRouting {version}: up to {options.passes} passes or {options.minutes} minutes, log {work / 'route.log'}",
        flush=True,
    )
    started = time.monotonic()
    with (work / "route.log").open("w") as log:
        try:
            # FreeRouting stops itself at its job timeout; the margin is for writing the session
            subprocess.run(
                command, stdout=log, stderr=subprocess.STDOUT, timeout=(options.minutes + 10) * 60, check=True
            )
        except subprocess.TimeoutExpired:
            print(f"FreeRouting did not stop {options.minutes + 10} minutes in; see {work / 'route.log'}")
            return 1
    if not session.is_file():
        print(f"FreeRouting wrote no session; see {work / 'route.log'}")
        return 1

    after = copper(python, IMPORT, board, session, output)
    minutes = (time.monotonic() - started) / 60
    print(
        f"{output.name}: {after['segments']} track segments (was {before['segments']}), "
        f"{after['vias']} vias (was {before['vias']}), "
        f"{after['open']} connections open (was {before['open']}), {minutes:.1f} minutes"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
