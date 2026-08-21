"""Software-only tests for circuit command entry points."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from flow.layout import commands


def test_primitive_command(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    calls: list[tuple[str, str, bool, Path]] = []
    monkeypatch.setattr(commands, "set_pdk", lambda _tech: None)
    monkeypatch.setattr(
        sys,
        "argv",
        ["python -m flow.mosfet.primitive", "-t", "ihp130", "-m", "max", "-v", "-o", str(tmp_path)],
    )

    commands.primitive_main(
        "flow.mosfet.primitive",
        lambda tech, mode, visual, outdir: calls.append((tech, mode, visual, outdir)),
    )

    assert calls == [("ihp130", "max", True, tmp_path)]
