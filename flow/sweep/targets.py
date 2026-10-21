"""The design-space sweep over every block with a ``sweep.py`` (``python -m flow sweep.<target>``)."""

from __future__ import annotations

from pathlib import Path

from flow.sweep import runner


def run() -> dict[str, Path]:
    """Every block's instances characterized in every PDK, in a fresh run per block (36 workers)."""
    # a Spectre X run holds 3 of the server's 120 licences: 40 runs at most, and others work too
    return runner.run(runner.sweep_blocks(), runner.PDKS, 36)


def missing() -> dict[str, Path]:
    """Each block's newest run's failed or missing instances characterized again, into that run."""
    return runner.run(runner.sweep_blocks(), runner.PDKS, 36, failed=True)


def layout() -> None:
    """Every block's newest run laid out by ALIGN and signed off where not yet clean (28 workers)."""
    runner.layout(runner.sweep_blocks(), 28)


def tables() -> None:
    """Every block's newest run exported as the viewer's tables and instance files (16 workers)."""
    runner.table(runner.sweep_blocks(), 16)
