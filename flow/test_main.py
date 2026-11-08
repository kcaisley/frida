"""The CLI (``python -m flow``): its steps from one to another, its runs, make-style resume,
``--predict`` and its refusals, on the toy block (``flow/conftest.py``'s ``toy``)."""

from __future__ import annotations

import importlib
import json
import shutil
from pathlib import Path

import pytest

from flow import __main__ as cli
from flow import pipeline
from flow.conftest import _NowPool
from flow.sweep import runner

Step = cli.Step


def test_the_steps_run_from_one_to_another() -> None:
    """``--from`` and ``--to`` pick the steps between them, both included, each after those it needs;
    one that does not lead to the other is refused."""
    assert cli.between(Step.NETLIST, Step.RECORD) == [Step.NETLIST, Step.SIM, Step.RECORD]
    assert cli.between(Step.RECORD, Step.RECORD) == [Step.RECORD]
    assert cli.between(Step.NETLIST, Step.TABLE) == [Step.NETLIST, Step.SIM, Step.RECORD, Step.TABLE]
    assert cli.between(Step.NETLIST, Step.CIRCUIT) == [Step.NETLIST, Step.SIM, Step.CIRCUIT]
    assert cli.between(Step.NETLIST, Step.LVS) == [Step.NETLIST, Step.LAYOUT, Step.DRC, Step.LVS]
    assert cli.between(Step.SIM, Step.PAGE) == [Step.SIM, Step.RECORD, Step.PAGE]
    page = [Step.NETLIST, Step.SIM, Step.RECORD, Step.LAYOUT, Step.DRC, Step.LVS, Step.PEX, Step.PAGE]
    assert cli.between(Step.NETLIST, Step.PAGE) == page
    # each step's order puts it after what it needs
    assert all(need.value < step.value for step in Step for need in step.needs)
    with pytest.raises(SystemExit, match="--from layout does not lead to --to record: record needs netlist, sim"):
        cli.between(Step.LAYOUT, Step.RECORD)


def test_the_bare_command_prints_the_usage_the_steps_and_the_blocks(capsys) -> None:
    cli.main([])
    lines = capsys.readouterr().out.splitlines()
    assert lines[0].startswith("python -m flow <block> --to STEP")
    assert "  record (needs sim)" in lines and "  page (needs record, pex)" in lines
    assert lines[-1] == f"blocks: {', '.join(cli.pipeline_blocks())}"
    assert {"adc", "capdac", "comp", "samp"} <= set(cli.pipeline_blocks())


def test_opt_and_the_viewer_keep_their_commands(monkeypatch) -> None:
    from flow.opt import runner as opt
    from flow.web import server

    calls = []
    monkeypatch.setattr(opt, "optimize", lambda *args: calls.append(("opt", *args)))
    monkeypatch.setattr(server, "serve", lambda port, host: calls.append(("serve", port, host)))
    cli.main(["opt", "comp", "--problem", "adc(bits=12)", "--budget", "3"])
    cli.main(["web.serve"])
    assert calls == [("opt", "comp", "tsmc65", "adc(bits=12)", 3, 48), ("serve", 8765, "127.0.0.1")]
    # the old verbs are gone: a block is the first word
    with pytest.raises(SystemExit):
        cli.main(["run", "comp"])


@pytest.fixture
def flow(toy, monkeypatch):
    """The CLI on the toy block in ``toypdk``, its instances run in this process, new runs named
    ``20261108_00000<n>`` in turn; ``flow(*argv)`` runs a command."""
    monkeypatch.setattr(runner, "PDKS", ("toypdk",))
    monkeypatch.setattr(cli, "pipeline_blocks", lambda: ["toyblock"])
    monkeypatch.setattr(cli, "_pool", lambda workers: _NowPool())
    stamps = iter(f"20261108_00000{n}" for n in range(10))
    monkeypatch.setattr(cli, "_stamp", lambda: next(stamps))
    return lambda *argv: cli.main(["toyblock", *argv])


@pytest.fixture
def simulated(toy, monkeypatch) -> list[str]:
    """The names of the toy's runs as they are simulated."""
    sim = importlib.import_module("flow.toyblock.sim")
    names: list[str] = []
    simulate = sim.simulate
    monkeypatch.setattr(sim, "simulate", lambda tb, run_dir: names.append(tb.name) or simulate(tb, run_dir))
    return names


def _instance(run: str) -> Path:
    return runner.RUNS_DIR / "toyblock" / run / "toypdk" / "one"


def test_a_block_runs_through_every_characterization_step(flow, simulated, capsys, monkeypatch) -> None:
    """``--to record`` makes a new run: the netlist (the circuit and its size), each run simulated and
    its measurement kept (its raw file removed), and the record from the kept measurements, each
    step in its folder, the record beside them; the table from it."""
    flow("--to", "record")
    out = capsys.readouterr().out
    assert "toyblock: new run" in out and "netlist ok" in out and "sim ok" in out and "record ok" in out
    assert simulated == ["screen", "search", "full"]
    instance = _instance("20261108_000000")
    assert json.loads((instance.parents[1] / "run.json").read_text())["block"] == "toyblock"
    assert (instance / "netlist/toyblock.cdl").read_text().startswith("* toyblock in toypdk")
    assert json.loads((instance / "netlist/geometry.json").read_text()) == {"devices": 0.0}
    assert sorted(path.parent.name for path in instance.glob("sim/*/result.h5")) == ["full", "screen", "search"]
    assert not list(instance.rglob("raw.txt"))
    assert {path.parent.name for path in instance.glob("*/step.json")} == {"netlist", "sim", "record"}
    record = json.loads((instance / "instance.json").read_text())
    assert record["error"] is None, record["error"]
    assert record["name"] == "one" and record["label"] == "one" and record["level"] == pipeline.Level.FULL.value
    assert record["metrics"] == {"devices": 0.0, "read_screen": True, "read_search": True, "read_full": True}
    assert record["netlist"].endswith("toypdk/one/netlist/toyblock.cdl")
    # the table, from the run's records
    data = runner.RUNS_DIR / "web/data/sweep"
    monkeypatch.setattr(runner, "DATA_DIR", data)
    flow("--from", "table", "--to", "table")
    table = json.loads((data / "toyblock.json").read_text())
    assert [row["id"] for row in table["rows"]] == [record["id"]] and table["run"] == "20261108_000000"


def test_a_step_resumes_where_its_output_is_complete(flow, simulated, capsys) -> None:
    """Make's rule: a step whose output is complete, and not older than what it needs, is skipped;
    one deleted is made again, and every step after it; ``--from record`` analyses again what the
    sim step kept, without simulating."""
    flow("--to", "record", "--run", "mine")
    instance = _instance("mine")
    capsys.readouterr()
    simulated.clear()
    flow("--to", "record", "--run", "mine")
    out = capsys.readouterr().out
    assert "resumed run" in out and "netlist done, sim done, record done" in out and not simulated
    shutil.rmtree(instance / "record")
    (instance / "instance.json").unlink()
    flow("--from", "record", "--to", "record")
    out = capsys.readouterr().out
    assert "the latest run" in out and "record ok" in out and not simulated
    assert json.loads((instance / "instance.json").read_text())["metrics"]["read_full"] is True
    # one run's measurement gone and the sim step's record with it: only that run simulated, and
    # the record after it made again
    shutil.rmtree(instance / "sim/search")
    (instance / "sim/step.json").unlink()
    flow("--from", "sim", "--to", "record")
    assert simulated == ["search"] and "sim ok" in capsys.readouterr().out
    assert cli.done(instance, Step.RECORD)
    # a step made again makes the steps after it out of date
    record = (instance / "record/step.json").read_text()
    shutil.rmtree(instance / "netlist")
    flow("--to", "netlist", "--run", "mine")
    assert not cli.done(instance, Step.SIM) and not cli.done(instance, Step.RECORD)
    flow("--to", "record", "--run", "mine")
    assert cli.done(instance, Step.RECORD) and (instance / "record/step.json").read_text() != record
    assert simulated == ["search", "screen", "search", "full"]


def test_a_later_step_takes_the_latest_run_or_the_one_named(flow, toy, capsys) -> None:
    """``--from`` past the netlist reuses the newest run (by when it was made, whatever its name) and
    says so, or the one ``--run`` names, by name or directory; none is refused."""
    with pytest.raises(SystemExit, match="no run of toyblock yet to start at record: python -m flow toyblock"):
        flow("--from", "record", "--to", "record")
    flow("--to", "sim", "--run", "zz_first")
    flow("--to", "sim")  # 20261108_000000, made after it
    capsys.readouterr()
    flow("--from", "record", "--to", "record")
    first = capsys.readouterr().out.splitlines()[0]
    assert first.startswith("toyblock: the latest run ") and first.split()[4].endswith("toyblock/20261108_000000;")
    assert (_instance("20261108_000000") / "instance.json").exists()
    assert not (_instance("zz_first") / "instance.json").exists()
    flow("--from", "record", "--to", "record", "--run", str(_instance("zz_first").parents[1]))
    assert (_instance("zz_first") / "instance.json").exists()
    with pytest.raises(SystemExit, match="no run nothing of toyblock"):
        flow("--from", "record", "--to", "record", "--run", "nothing")


def test_predict_prints_what_would_run_and_runs_nothing(flow, toy, capsys) -> None:
    flow("--to", "record", "--predict")
    out = capsys.readouterr().out.splitlines()
    assert out[0].startswith("toyblock: new run") and out[0].endswith("steps netlist, sim, record")
    assert out[1] == "toypdk one (one): netlist, sim, record; 3 simulator runs"
    assert out[2] == "1 instance in 1 PDK: 3 steps to run, 0 complete, about 3 simulator runs"
    assert not (runner.RUNS_DIR / "toyblock").exists()
    flow("--to", "sim", "--run", "mine")
    capsys.readouterr()
    flow("--to", "table", "--run", "mine", "--predict")
    out = capsys.readouterr().out.splitlines()
    assert out[1] == "toypdk one (one): record" and out[2].endswith(
        "2 complete, about 0 simulator runs; then the table"
    )


def test_a_step_without_its_inputs_fails_naming_the_command_that_makes_them(flow, toy, capsys) -> None:
    flow("--to", "netlist", "--run", "mine")
    with pytest.raises(SystemExit, match="1 of 1 instances failed"):
        flow("--from", "record", "--to", "record")
    out = capsys.readouterr().out
    assert "record failed: record needs its sim step's output: " in out
    assert "python -m flow toyblock --to sim --run mine --pdk toypdk --instance one" in out
    # the circuit simulator's runs of picked instances alone; the steps the CLI does not run yet
    with pytest.raises(SystemExit, match="pick the instances"):
        flow("--to", "circuit")
    with pytest.raises(SystemExit, match="runs no layout, drc step yet"):
        flow("--to", "drc")
    with pytest.raises(SystemExit, match="no instance 'two' of toyblock in toypdk"):
        flow("--to", "record", "--instance", "two")
    # the table needs every instance's record
    with pytest.raises(SystemExit, match="table needs every instance's record, 1 of 1 have none"):
        flow("--from", "table", "--to", "table")


def test_a_failed_step_is_recorded_and_made_again_next_time(flow, toy, capsys, monkeypatch) -> None:
    """A step that fails records its error (a characterization's as the instance's record, for the
    viewer's table) and is not complete: the next command makes it again, the runs it kept kept."""
    sim = importlib.import_module("flow.toyblock.sim")
    simulate = sim.simulate

    def broken(tb, run_dir):
        if tb.name == "search":
            raise RuntimeError("no licence")
        return simulate(tb, run_dir)

    monkeypatch.setattr(sim, "simulate", broken)
    with pytest.raises(SystemExit, match="1 of 1 instances failed"):
        flow("--to", "record", "--run", "mine")
    assert "sim failed: RuntimeError: no licence" in capsys.readouterr().out
    instance = _instance("mine")
    record = json.loads((instance / "instance.json").read_text())
    assert record["error"].startswith("sim: ") and record["metrics"] == {}
    assert not cli.done(instance, Step.SIM) and (instance / "sim/screen/result.h5").exists()
    monkeypatch.setattr(sim, "simulate", simulate)
    flow("--to", "record", "--run", "mine")
    assert "netlist done, sim ok" in capsys.readouterr().out
    assert json.loads((instance / "instance.json").read_text())["error"] is None


def test_the_circuit_step_adds_the_circuit_simulators_runs_and_records_again(flow, toy, capsys) -> None:
    flow("--to", "record", "--run", "mine")
    flow("--to", "circuit", "--run", "mine", "--instance", "one")
    out = capsys.readouterr().out
    assert "netlist done, sim done, circuit ok" in out
    instance = _instance("mine")
    assert [path.parent.name for path in instance.glob("circuit/*/result.h5")] == ["circuit"]
    record = json.loads((instance / "instance.json").read_text())
    assert record["level"] == pipeline.Level.CIRCUIT.value and record["metrics"]["read_circuit"] is True
    assert cli.done(instance, Step.RECORD)
    # recorded again later, the circuit runs stay in it
    shutil.rmtree(instance / "record")
    flow("--from", "record", "--to", "record")
    assert json.loads((instance / "instance.json").read_text())["metrics"]["read_circuit"] is True


def test_a_block_whose_circuit_level_adds_no_runs_refuses_the_circuit_step(flow, toy) -> None:
    sweep = importlib.import_module("flow.toyblock.sweep")
    runs = sweep.runs
    level = pipeline.Level
    sweep.runs = lambda pdk, params, at=level.FULL: runs(pdk, params, level.FULL if at is level.CIRCUIT else at)
    with pytest.raises(SystemExit, match="no circuit simulator runs beyond its full ones"):
        flow("--to", "circuit", "--instance", "one")
