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
    lines = capsys.readouterr().out.splitlines()
    # the verbs over the blocks on the pipeline, then every other block's targets
    verbs = len(cli.VERBS)
    assert [line.split()[3] for line in lines[:verbs]] == list(cli.VERBS)
    assert lines[verbs] == f"(blocks on the pipeline: {', '.join(cli.pipeline_blocks())})"
    assert {"comp", "samp"} <= set(cli.pipeline_blocks())
    listed = lines[verbs + 1 :]
    assert listed == [f"{block}.{name}" for block, module in cli.BLOCKS.items() for name in cli.targets(module)]
    assert {"layout.mos_inv", "sweep.run", "web.serve"} <= set(listed) and not any(
        t.startswith("comp.") for t in listed
    )
    # an unknown block or name, an imported module, a private helper and a block on the pipeline are
    # no targets
    for argument in ("comp.unknown", "unknown.run", "comp", "samp.sim", "layout._run", "samp.new_run", "comp.sweep"):
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


def test_a_verb_runs_a_pipeline_block_and_only_one(monkeypatch) -> None:
    from flow.sweep import runner

    calls = []
    monkeypatch.setattr(
        runner, "run", lambda blocks, pdks, workers, **kw: calls.append(("run", blocks, pdks, workers, kw))
    )
    monkeypatch.setattr(runner, "layout", lambda blocks, workers, **kw: calls.append(("layout", blocks, workers, kw)))
    monkeypatch.setattr(runner, "table", lambda blocks, workers: calls.append(("table", blocks, workers)))
    for argv in (
        ["run", "comp", "--pdk", "tsmc65", "--instance", "frida1", "--workers", "4"],
        ["run", "comp", "--missing"],
        ["layout", "comp", "--pdk", "ihp130"],
        ["table", "comp"],
    ):
        monkeypatch.setattr(sys, "argv", ["flow", *argv])
        cli.main()
    assert calls == [
        ("run", ["comp"], ("tsmc65",), 4, {"failed": False, "names": ["frida1"]}),
        ("run", ["comp"], runner.PDKS, 36, {"failed": True, "names": None}),
        ("layout", ["comp"], 28, {"pdks": ("ihp130",)}),
        ("table", ["comp"], 16),
    ]
    # a block not on the pipeline keeps its targets
    monkeypatch.setattr(sys, "argv", ["flow", "run", "delay"])
    with pytest.raises(SystemExit):
        cli.main()
