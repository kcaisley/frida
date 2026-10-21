"""The viewer's targets (``python -m flow web.<target>``)."""

from __future__ import annotations

from flow.sweep import runner
from flow.web import server


def serve() -> None:
    """The viewer on http://127.0.0.1:8765 (forward the port from a remote machine)."""
    server.serve(8765, "127.0.0.1")


def tables() -> None:
    """Every block's newest sweep exported as the viewer's tables and instance files (16 workers)."""
    runner.table(runner.sweep_blocks(), 16)
