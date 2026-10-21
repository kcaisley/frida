"""Every target of ``python -m flow``: a documented function without arguments, its name unique."""

from __future__ import annotations

import inspect
import sys
from types import SimpleNamespace

import pytest

from flow import __main__ as cli
from flow.web import targets as web


def test_every_target_is_a_documented_function_without_arguments() -> None:
    names = []
    for block, module in cli.BLOCKS.items():
        assert module.__name__ == f"flow.{block}.targets"
        found = cli.targets(module)
        assert found, block
        for name, function in found.items():
            assert not inspect.signature(function).parameters, f"{block}.{name}"
            assert (function.__doc__ or "").strip(), f"{block}.{name}"
            names.append(f"{block}.{name}")
    assert len(names) == len(set(names))


def test_the_listing_names_every_target_and_nothing_else_runs(monkeypatch, capsys) -> None:
    monkeypatch.setattr(sys, "argv", ["flow"])
    cli.main()
    listed = capsys.readouterr().out.split()
    assert listed == [f"{block}.{name}" for block, module in cli.BLOCKS.items() for name in cli.targets(module)]
    assert {"comp.characterization", "sweep.run", "web.serve"} <= set(listed)
    # an unknown block or name, an imported module and a private helper are no targets
    for argument in ("comp.unknown", "unknown.run", "comp", "comp.sim", "comp._mos_inv", "comp.new_run"):
        monkeypatch.setattr(sys, "argv", ["flow", argument])
        with pytest.raises(SystemExit, match="no target"):
            cli.main()


def test_a_named_target_runs_without_arguments(monkeypatch) -> None:
    calls = []
    runner = SimpleNamespace(
        sweep_blocks=lambda: ["comp"], table=lambda blocks, workers: calls.append((blocks, workers))
    )
    monkeypatch.setattr(web, "runner", runner)
    monkeypatch.setattr(sys, "argv", ["flow", "web.tables"])
    cli.main()
    assert calls == [(["comp"], 16)]
