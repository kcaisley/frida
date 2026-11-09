"""The CLI (``python -m flow``): its steps from one to another, its runs, make-style resume,
``--predict`` and its refusals, on the toy block (``flow/conftest.py``'s ``toy``); its layout steps
with the tools stood in for (``tools``)."""

from __future__ import annotations

import importlib
import json
import shutil
import sys
from pathlib import Path
from types import SimpleNamespace

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
    pexsim = [Step.NETLIST, Step.SIM, Step.LAYOUT, Step.DRC, Step.LVS, Step.PEX, Step.PEXSIM]
    assert cli.between(Step.NETLIST, Step.PEXSIM) == pexsim
    # each step's order puts it after what it needs
    assert all(need.value < step.value for step in Step for need in step.needs)
    with pytest.raises(SystemExit, match="--from layout does not lead to --to record: record needs netlist, sim"):
        cli.between(Step.LAYOUT, Step.RECORD)


def test_the_bare_command_prints_the_usage_the_steps_and_the_blocks(capsys) -> None:
    cli.main([])
    lines = capsys.readouterr().out.splitlines()
    assert lines[0].startswith("python -m flow <block> --to STEP")
    assert "  record (needs netlist, sim)" in lines and "  page (needs record, pex)" in lines
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


def test_a_reused_run_keeps_to_its_own_pdks(flow, toy, monkeypatch, capsys) -> None:
    """A later step works in the PDKs its run holds, its instances picked or not; a new run in every
    PDK the block admits."""
    monkeypatch.setattr(runner, "PDKS", ("toypdk", "otherpdk"))
    flow("--to", "record", "--predict")
    assert [line.split()[0] for line in capsys.readouterr().out.splitlines()[1:3]] == ["toypdk", "otherpdk"]
    flow("--to", "netlist", "--pdk", "toypdk", "--run", "mine")
    capsys.readouterr()
    for picked in ((), ("--instance", "one")):
        flow("--from", "sim", "--to", "record", "--predict", *picked)
        lines = capsys.readouterr().out.splitlines()
        assert lines[1].startswith("toypdk one") and lines[2].startswith("1 instance in 1 PDK")


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


def test_predict_marks_the_steps_that_would_fail_and_why(flow, toy, capsys) -> None:
    """A step whose inputs are neither complete nor made first would fail: ``--predict`` says so,
    with the command that makes them, and the steps after it not run; the totals count them."""
    flow("--to", "netlist", "--run", "mine")
    capsys.readouterr()
    flow("--from", "record", "--to", "figures", "--predict")
    lines = capsys.readouterr().out.splitlines()
    command = "python -m flow toyblock --to sim --run mine --pdk toypdk --instance one"
    assert lines[1] == (
        f"toypdk one (one): record (fails: record needs its sim step's output: {command}), "
        "figures (fails: not run, as record fails)"
    )
    assert lines[2] == "1 instance in 1 PDK: 0 steps to run, 2 would fail, 0 complete, about 0 simulator runs"


def test_a_run_from_before_run_json_keeps_its_time_when_reused(flow, toy, capsys) -> None:
    """A run without ``run.json`` (its time its name's stamp) reused by ``--run`` gains none: it does
    not become the block's latest run."""
    flow("--to", "sim", "--run", "mine")
    old = runner.RUNS_DIR / "toyblock" / "20261101_015731"
    shutil.copytree(runner.RUNS_DIR / "toyblock" / "mine", old)
    (old / "run.json").unlink()
    assert runner.newest_run("toyblock").name == "mine"
    flow("--from", "record", "--to", "record", "--run", "20261101_015731")
    assert "resumed run" in capsys.readouterr().out and (old / "toypdk/one/instance.json").exists()
    assert not (old / "run.json").exists() and runner.newest_run("toyblock").name == "mine"


def test_the_table_takes_each_instances_newest_record_across_the_runs(flow, tools, monkeypatch) -> None:
    """A newer run of a layout alone does not hide the records of the runs before: the table keeps
    each instance's newest characterization, the newer layout joined to it."""
    data = runner.RUNS_DIR / "web/data/sweep"
    monkeypatch.setattr(runner, "DATA_DIR", data)
    flow("--to", "record", "--run", "a")
    flow("--to", "layout", "--run", "b", "--instance", "one")
    flow("--to", "layout", "--run", "c", "--instance", "wired")
    flow("--from", "table", "--to", "table")
    table = json.loads((data / "toyblock.json").read_text())
    rows = {row["id"]: row for row in table["rows"]}
    one, wired = (runner.instance_id("toypdk", build()) for build in _named("one", "wired"))
    assert set(rows) == {one, wired} and rows[one]["metrics"]["read_full"] is True and rows[wired]["metrics"] == {}
    detail = json.loads((data / "toyblock" / f"{one}.json").read_text())
    assert detail["layout"]["gds"].endswith("b/toypdk/one/layout/toy.gds")
    assert table["run"] == "c (toypdk), a (toypdk)"


def _named(*names: str):
    sweep = importlib.import_module("flow.toyblock.sweep")
    return [getattr(sweep, name) for name in names]


def test_a_step_without_its_inputs_fails_naming_the_command_that_makes_them(flow, toy, capsys) -> None:
    flow("--to", "netlist", "--run", "mine")
    with pytest.raises(SystemExit, match="1 of 1 instances failed"):
        flow("--from", "record", "--to", "record")
    out = capsys.readouterr().out
    assert "record failed: record needs its sim step's output: " in out
    assert "python -m flow toyblock --to sim --run mine --pdk toypdk --instance one" in out
    # the circuit simulator's runs of picked instances alone
    with pytest.raises(SystemExit, match="pick the instances"):
        flow("--to", "circuit")
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


def test_the_figures_step_draws_the_records_figures(flow, toy, capsys) -> None:
    flow("--to", "figures", "--run", "mine")
    instance = _instance("mine")
    assert "figures ok" in capsys.readouterr().out
    drawn = json.loads((instance / "figures/step.json").read_text())["figures"]
    assert drawn and all(name.startswith("figures/reads.") for name in drawn)
    assert all((instance / name).is_file() for name in drawn)


# ---- the layout steps: layout, then drc, lvs and pex, each its own tool, the tools stood in for


@pytest.fixture
def tools(toy, monkeypatch):
    """The signoff tools stood in for, each call recorded (``calls``: the step, the file it took and
    the checker): DRC finds ``state["violations"]``, LVS's verdict is ``state["lvs"]``; the toy PDK's
    layers for the page's views."""
    from flow.layout import signoff, step

    calls: list[tuple] = []
    engines: list = []
    state = {"violations": 0, "lvs": True}

    def drc(pdk, gds, run_dir, checker, source=None):
        calls.append(("drc", Path(gds).name, checker))
        run_dir.mkdir(parents=True, exist_ok=True)
        report = run_dir / "drc_violations.json"
        report.write_text(json.dumps({"checker": "stand-in", "violations": {"A.1": state["violations"]}}))
        return {"violations": state["violations"], "checker": "stand-in", "report": str(report), "top": "toy"}

    def lvs(pdk, gds, source, run_dir, checker):
        calls.append(("lvs", Path(source).name, checker))
        correct = state["lvs"]
        return {"lvs_correct": correct, "lvs_report": str(run_dir / "x.lvsdb"), "lvs_checker": "stand-in"}

    def extracted(pdk, gds, name, run_dir, checker, engine):
        calls.append(("pex", Path(gds).name, checker))
        engines.append(engine)
        return {"netlist": str(run_dir / f"{name}.pex.spectre"), "extractor": "stand-in", "nets": {"a": 1e-15}}

    monkeypatch.setattr(signoff, "drc", drc)
    monkeypatch.setattr(signoff, "lvs", lvs)
    monkeypatch.setattr(step, "extracted", extracted)
    monkeypatch.setitem(sys.modules, "pdk.toypdk.layout.tech", SimpleNamespace(LAYERS={"M1": (1, 0)}))
    return SimpleNamespace(calls=calls, engines=engines, state=state)


def test_the_layout_steps_lay_out_then_sign_off_each_in_its_folder(flow, tools, capsys) -> None:
    """``--to pex``: the layout (here the toy's own, with its LVS source), then DRC, LVS and the
    extraction, each by the open tools, each in its folder; the record of the layout alone joins
    them, so the viewer's table and ``laid_out`` find it. A complete step is skipped; one deleted
    is made again with those after it, the layout not."""
    from flow.layout.signoff import Checker
    from flow.sweep import lookup

    flow("--to", "pex", "--run", "mine", "--instance", "wired")
    out = capsys.readouterr().out
    assert "steps netlist, layout, drc, lvs, pex" in out
    assert "layout ok in" in out and "(2 x 1 um)" in out
    assert "drc ok in" in out and "(0 violations, stand-in)" in out
    assert "(match, stand-in)" in out and "pex ok in" in out and "(1 nets)" in out
    open_ = Checker.OPEN
    assert tools.calls == [("drc", "toy.gds", open_), ("lvs", "source.cdl", open_), ("pex", "toy.gds", open_)]
    instance = _instance("mine").with_name("wired")
    assert (instance / "layout/toy.gds").is_file() and (instance / "layout/step.log").is_file()
    assert {path.parent.name for path in instance.glob("*/step.json")} == {"netlist", "layout", "drc", "lvs", "pex"}
    record = json.loads((instance / "instance.json").read_text())
    entry = record["layout"]
    assert record["name"] == "wired" and record["metrics"] == {} and record["error"] is None
    assert entry["gds"].endswith("wired/layout/toy.gds") and entry["netlist"].endswith("layout/source.cdl")
    assert (entry["w_um"], entry["h_um"], entry["drc_violations"], entry["lvs_correct"]) == (2.0, 1.0, 0, True)
    assert entry["pex"] == {"netlist": entry["pex"]["netlist"], "extractor": "stand-in", "nets": {"a": 1e-15}}
    assert entry["pex"]["netlist"].endswith("wired/pex/toy.pex.spectre") and entry["error"] is None
    assert set(entry["steps"]) == {"layout", "drc", "lvs", "pex"} and entry["floorplan"] == "lay_out"
    assert lookup.laid_out("toyblock", "toypdk", importlib.import_module("flow.toyblock.sweep").wired()) == entry
    # complete: skipped
    tools.calls.clear()
    flow("--from", "drc", "--to", "pex")
    assert "drc done, lvs done, pex done" in capsys.readouterr().out and not tools.calls
    # DRC's output gone: DRC, then LVS and PEX after it, made again; the layout kept
    laid = (instance / "layout/step.json").read_text()
    shutil.rmtree(instance / "drc")
    flow("--from", "drc", "--to", "pex")
    assert "the latest run" in capsys.readouterr().out
    assert [call[0] for call in tools.calls] == ["drc", "lvs", "pex"]
    assert (instance / "layout/step.json").read_text() == laid
    # the layout made again: every signoff step after it is out of date
    shutil.rmtree(instance / "layout")
    flow("--from", "layout", "--to", "layout")
    assert cli.done(instance, Step.LAYOUT) and not cli.done(instance, Step.DRC) and not cli.done(instance, Step.PEX)


def test_a_kit_that_names_calibre_signs_off_by_it(flow, tools, monkeypatch) -> None:
    """The checker is the kit's configuration (its ``signoff.checker(block)``), not a flag."""
    from flow.layout import signoff
    from flow.layout.signoff import Checker

    assert signoff.checker("toypdk", "toyblock") is Checker.OPEN
    monkeypatch.setitem(sys.modules, "pdk.toypdk.signoff", SimpleNamespace(checker=lambda block: Checker.CALIBRE))
    assert signoff.checker("toypdk", "toyblock") is Checker.CALIBRE
    flow("--to", "pex", "--instance", "wired")
    assert [call[2] for call in tools.calls] == [Checker.CALIBRE] * 3


def test_the_extraction_engine_is_the_kits_configuration_for_the_block(flow, tools, monkeypatch) -> None:
    """KLayout-PEX's engine is the kit's choice for the block (its ``signoff.engine(block)``), not a
    flag: FasterCap where the kit names none, the 2.5-D engine for the block it names it for."""
    from flow.layout import signoff
    from flow.layout.kpex import Engine

    flow("--to", "pex", "--run", "fastercap", "--instance", "wired")
    assert signoff.engine("toypdk", "toyblock") is Engine.FASTERCAP and tools.engines == [Engine.FASTERCAP]
    kit = SimpleNamespace(engine=lambda block: Engine.RCX25 if block == "toyblock" else Engine.FASTERCAP)
    monkeypatch.setitem(sys.modules, "pdk.toypdk.signoff", kit)
    assert (
        signoff.engine("toypdk", "toyblock") is Engine.RCX25 and signoff.engine("toypdk", "other") is Engine.FASTERCAP
    )
    flow("--to", "pex", "--run", "rcx25", "--instance", "wired")
    assert tools.engines == [Engine.FASTERCAP, Engine.RCX25]


def test_a_block_that_plans_its_signoff_has_the_signoff_steps_run_it_each_in_its_folder(
    flow, tools, monkeypatch, capsys
) -> None:
    """A ``lay_out`` that plans its layout's signoff (``signoff.json``, ``write_plan``: its sources,
    its LVS expectation, the kit's options): the drc, lvs and pex steps run the kit's tools on it,
    each in its own folder (``planned_drc``, ``planned_lvs``, ``planned_pex``), the expected LVS
    mismatch passing among the warnings; the open tools not run."""
    import hashlib

    ran: list[tuple[str, str]] = []

    def run_drc(*, run_dir, gds_path, layout_top, options):
        ran.append(("drc", run_dir.name))
        (run_dir / "drc_violations.json").write_text(json.dumps({"checker": "kitcheck", "violations": {}}))
        return run_dir / "drc_violations.json"

    def run_lvs(*, run_dir, gds_path, source_path, layout_top, source_top, options):
        ran.append(("lvs", run_dir.name))
        (run_dir / "lvs.report").write_text("INCORRECT\n")
        return False, run_dir / "lvs.report"

    def run_pex(*, run_dir, gds_path, source_path, layout_top, source_top, output_stem, options):
        ran.append(("pex", run_dir.name))
        (run_dir / f"{output_stem}.pex.netlist").write_text("* extracted\n")
        return run_dir / f"{output_stem}.pex.netlist"

    kit = SimpleNamespace(run_drc=run_drc, run_lvs=run_lvs, run_pex=run_pex)
    monkeypatch.setitem(sys.modules, "pdk.toypdk.signoff", kit)
    flow("--to", "pex", "--instance", "signed")
    out = capsys.readouterr().out
    assert not tools.calls and ran == [("drc", "drc"), ("lvs", "lvs"), ("pex", "pex")]
    assert "(0 violations, kitcheck)" in out and "(no match, the kit's)" in out
    instance = runner.newest_run("toyblock") / "toypdk" / "signed"
    assert {path.name for path in (instance / "layout").iterdir()} == {
        "toy.gds",
        "toy.lvs.cdl",
        "signoff.json",
        "step.json",
        "step.log",
    }
    entry = json.loads((instance / "instance.json").read_text())["layout"]
    assert entry["floorplan"] == "lay_out" and entry["signoff"] == "kitcheck" and entry["drc_violations"] == 0
    assert entry["lvs_correct"] is False and entry["netlist"].endswith("signed/layout/toy.lvs.cdl")
    assert entry["warnings"] == ["expected LVS mismatch: disconnected historical MOM layer"]
    netlist = instance / "pex/toy.pex.netlist"
    assert entry["pex"]["netlist"].endswith("signed/pex/toy.pex.netlist")
    assert entry["pex"]["sha256"] == hashlib.sha256(netlist.read_bytes()).hexdigest()


def test_a_plan_reads_back_as_written(tmp_path) -> None:
    """``write_plan`` then ``read_plan``: the same ``SignoffParams``, the kit's options as its class
    (its lists tuples again)."""
    from dataclasses import dataclass

    from flow.layout.signoff import SignoffParams, read_plan, write_plan

    @dataclass(frozen=True)
    class Options:
        waived: tuple[str, ...] = ()
        layer: int | None = None

    module = SimpleNamespace(Options=Options)
    Options.__module__, Options.__qualname__ = "toykit_options", "Options"
    sys.modules["toykit_options"] = module  # type: ignore[assignment]
    try:
        plan = SignoffParams(
            "toypdk",
            tmp_path / "a.gds",
            "top",
            tmp_path / "a.cdl",
            "top",
            "a",
            pex_source_path=tmp_path / "a.pex.cdl",
            lvs_expectation="incorrect",
            lvs_required_report_fragments=("x", "y"),
            pdk_options=Options(waived=("R.1", "R.2"), layer=5),
        )
        assert read_plan(write_plan(plan, tmp_path / "signoff.json")) == plan
    finally:
        del sys.modules["toykit_options"]


def test_a_layout_made_again_that_fails_leaves_its_signoff_steps_not_run(flow, tools, monkeypatch, capsys) -> None:
    """Make's rule through a failure: a layout deleted, or made again and failed, leaves the steps
    after it incomplete (their outputs of a GDS no longer there), not run, and none of their
    results joined to the record."""
    flow("--to", "pex", "--run", "mine", "--instance", "wired")
    instance = _instance("mine").with_name("wired")
    assert cli.done(instance, Step.PEX)
    shutil.rmtree(instance / "layout")
    assert not cli.done(instance, Step.DRC) and not cli.done(instance, Step.PEX)
    layout = importlib.import_module("flow.toyblock.layout")
    monkeypatch.setattr(layout, "lay_out", lambda params, pdk, run_dir: (_ for _ in ()).throw(RuntimeError("no room")))
    capsys.readouterr()
    tools.calls.clear()
    with pytest.raises(SystemExit, match="1 of 1 instances failed"):
        flow("--from", "layout", "--to", "pex")
    out = capsys.readouterr().out
    assert "layout failed: RuntimeError: no room, drc not run, lvs not run, pex not run" in out and not tools.calls
    assert not any(cli.done(instance, step) for step in (Step.LAYOUT, Step.DRC, Step.LVS, Step.PEX))
    entry = json.loads((instance / "instance.json").read_text())["layout"]
    assert entry["error"] and entry["drc_violations"] is None and entry["lvs_correct"] is None and entry["pex"] is None


def test_a_layout_without_an_lvs_source_is_checked_by_drc_alone(flow, tools, capsys) -> None:
    flow("--to", "pex", "--instance", "one")
    out = capsys.readouterr().out
    assert [call[0] for call in tools.calls] == ["drc"]
    assert "lvs ok" in out and "(not run: no LVS source" in out
    instance = runner.newest_run("toyblock") / "toypdk" / "one"
    entry = json.loads((instance / "instance.json").read_text())["layout"]
    assert entry["lvs_correct"] is None and entry["pex"]["skipped"].startswith("no LVS source")


def test_a_layout_other_than_its_netlist_is_not_extracted_and_its_page_still_written(flow, tools, capsys) -> None:
    """LVS that does not match refuses the extraction; the page, which takes whatever exists, is
    written all the same, with the record's metrics and the layout's steps. DRC's violations are a
    count, not a failure."""
    tools.state.update(lvs=False, violations=3)
    with pytest.raises(SystemExit, match="1 of 1 instances failed"):
        flow("--to", "page", "--run", "mine", "--instance", "wired")
    out = capsys.readouterr().out
    assert "record ok" in out and "(3 violations, stand-in)" in out and "(no match, stand-in)" in out
    assert "pex failed: RuntimeError: LVS found the layout other than its netlist" in out and "page ok" in out
    instance = _instance("mine").with_name("wired")
    steps = {entry["key"]: entry for entry in json.loads((instance / "page/steps.json").read_text())}
    assert (instance / "page/page.html").is_file()
    assert steps["record"]["state"] == "ok" and steps["gds"]["state"] == "ok"
    assert steps["drc"]["state"] == "bad" and steps["lvs"]["state"] == "bad" and steps["pex"]["state"] == "bad"
    record = json.loads((instance / "instance.json").read_text())
    assert record["metrics"]["layout_area_um2"] == 2.0 and record["layout"]["steps"]["pex"]["error"]


def test_the_shared_step_lays_out_by_align_and_its_other_router_where_one_fails(flow, tools, monkeypatch) -> None:
    """A block that states its layout in its generator: ALIGN alone in the layout step (its netlists,
    its design directory, ALIGN by the PDK's router, by the other where that one fails), the
    signoff the steps after it."""
    from flow.layout import step

    def inputs(block, out, pdk, design, params, seconds=None):
        (out / "netlist").mkdir(parents=True)
        (out / "netlist" / f"{design}.cdl").write_text(f".subckt {design}\n.ends\n")
        return out / "align/input" / design, [], out / "netlist" / f"{design}.cdl", True

    def align(pdk, design, cells, out, placed, seed=0, router=None):
        if router == "first":
            raise RuntimeError("the router gave up")
        from klayout import db

        layout = db.Layout()
        layout.create_cell("TOYBLOCK").shapes(layout.layer(1, 0)).insert(db.Box(0, 0, 3000, 1000))
        (out / "gds").mkdir(parents=True)
        layout.write(str(out / "gds/toyblock.gds"))
        return out / "gds/toyblock.gds"

    monkeypatch.setattr(step, "own_layout", lambda block: False)
    monkeypatch.setattr(step, "inputs", inputs)
    monkeypatch.setattr(step, "build_design", align)
    monkeypatch.setattr(step, "pdk_router", lambda pdk: "first")
    monkeypatch.setattr(step, "other_router", {"first": "second", "second": "first"}.get)
    monkeypatch.setattr(step, "route_shorts", lambda work, name: {})
    flow("--to", "pex", "--run", "mine", "--instance", "wired")
    instance = _instance("mine").with_name("wired")
    laid = json.loads((instance / "layout/step.json").read_text())
    assert laid["router"] == "second" and laid["gds"].endswith("layout/align_second/gds/toyblock.gds")
    # the design by its instance: a top cell of its own
    assert laid["cell_um"] == [3.0, 1.0] and laid["source"].endswith("layout/netlist/toyblock_wired.cdl")
    assert [call[:2] for call in tools.calls] == [
        ("drc", "toyblock.gds"),
        ("lvs", "toyblock_wired.cdl"),
        ("pex", "toyblock.gds"),
    ]
    assert json.loads((instance / "instance.json").read_text())["layout"]["floorplan"] == "generator"


def test_a_signoff_step_without_its_layout_fails_naming_the_command_that_makes_it(flow, tools, capsys) -> None:
    flow("--to", "netlist", "--run", "mine")
    capsys.readouterr()
    with pytest.raises(SystemExit, match="1 of 1 instances failed"):
        flow("--from", "drc", "--to", "pex")
    out = capsys.readouterr().out
    assert "drc failed: drc needs its layout step's output: python -m flow toyblock --to layout --run mine" in out
    assert "lvs not run, pex not run" in out and not tools.calls
    with pytest.raises(SystemExit, match="1 of 1 instances failed"):
        flow("--from", "page", "--to", "page")
    assert "page failed: page needs the record or the layout" in capsys.readouterr().out


@pytest.fixture
def extraction(tools, monkeypatch):
    """The open extractor stood in for by a toy's capacitances (its port ``a``, ground, a gate's
    poly ``$1`` LVS finds on ``a``, a cell's inner net ``$9`` it finds on none) with their probes,
    and LVS's cross-reference by a fake (``mapped``: each layout net's schematic net)."""
    from flow.layout import annotate, step

    mapped = {"a": "a", "$1": "a", "$9": None}

    def extracted(pdk, gds, name, run_dir, checker, engine):
        run_dir.mkdir(parents=True, exist_ok=True)
        netlist, probes = run_dir / f"{name}.pex.netlist", run_dir / f"{name}.probes.json"
        lines = ["c_0 ( a 0 ) capacitor c=3f", "c_1 ( $1 a ) capacitor c=0.5f", "c_2 ( $1 0 ) capacitor c=0.2f"]
        netlist.write_text("\n".join([*lines, "c_3 ( $9 a ) capacitor c=0.01f"]) + "\n")
        probes.write_text(json.dumps({net: [[17, 0, 5, 5]] for net in mapped}))
        return {"netlist": str(netlist), "probes": str(probes), "extractor": "stand-in", "nets": {"a": 3.51e-15}}

    monkeypatch.setattr(step, "extracted", extracted)
    monkeypatch.setattr(annotate, "schematic_nets", lambda lvsdb, probes: {net: mapped[net] for net in probes})
    return mapped


def test_pexsim_simulates_the_runs_again_with_the_extraction_on_the_schematic(flow, extraction, capsys) -> None:
    """``--to pexsim``: the extraction's nets found on the schematic's through LVS (a gate's poly on
    its net, the capacitor between them shorted out), its capacitors in each run's DUT less the
    DUT's own drawn between the same nets, each run simulated again and recorded alike in
    ``pexsim/`` (the record's metric names, the annotation's totals beside them); the cell's inner
    net, a small share, reported."""
    flow("--to", "pexsim", "--run", "mine", "--instance", "wired")
    out = capsys.readouterr().out
    assert "steps netlist, sim, layout, drc, lvs, pex, pexsim" in out
    assert "pexsim ok in" in out and "(3 runs, 2.2 fF added, 0.3% of the extraction on no schematic net)" in out
    instance = _instance("mine").with_name("wired")
    runs = sorted(path.parent.name for path in instance.glob("sim/*/result.h5"))
    assert sorted(path.parent.name for path in instance.glob("pexsim/*/result.h5")) == runs
    added = json.loads((instance / "pexsim" / runs[0] / "annotation.json").read_text())
    assert added["instances"] == ["dut"] and added["added_f"] == pytest.approx(2.2e-15)
    assert added["drawn_f"] == pytest.approx(1e-15)
    record = json.loads((instance / "pexsim/instance.json").read_text())
    assert set(record["metrics"]) == {"devices", *(f"read_{run}" for run in runs)}
    annotation = record["annotation"]
    assert (
        annotation["extractor"] == "stand-in"
        and annotation["capacitors"] == 1
        and annotation["total_f"] == pytest.approx(3.71e-15)
    )
    assert annotation["mapped_f"] == pytest.approx(3.7e-15) and annotation["unmapped_f"] == pytest.approx(1e-17)
    assert annotation["unmapped_nets"] == {"$9": pytest.approx(1e-17)} and annotation["unannotated"] == []
    assert record["waves"] == {} and record["name"] == "wired"


def test_pexsim_refuses_an_extraction_mostly_on_no_schematic_net(flow, extraction, capsys) -> None:
    """More than a small share of the capacitance on nets LVS paired with nothing: not simulated,
    the totals and the nets in the failure."""
    extraction["a"] = None
    with pytest.raises(SystemExit, match="1 of 1 instances failed"):
        flow("--to", "pexsim", "--run", "mine", "--instance", "wired")
    out = capsys.readouterr().out
    assert "pexsim failed: ValueError: 3.51 fF of the extraction's 3.71 fF (94.6%, over 5%)" in out
    assert "a 3.51 fF, $9 0.01 fF" in out
    assert not list((_instance("mine").with_name("wired") / "pexsim").glob("*/result.h5"))


def test_pexsim_refuses_capacitance_on_nets_the_dut_lacks_or_no_dut(flow, extraction, capsys, monkeypatch) -> None:
    """A schematic net LVS compared that the simulated DUT lacks counts against the same share as an
    unmapped one; testbenches none of which instantiates the DUT annotate nothing and fail."""
    import sys

    extraction["$1"] = "nowhere"
    with pytest.raises(SystemExit, match="1 of 1 instances failed"):
        flow("--to", "pexsim", "--run", "mine", "--instance", "wired")
    out = capsys.readouterr().out
    assert "0.71 fF of the extraction's 3.71 fF (over 5%) is on no net of netlist(mode=1)" in out
    assert "unmapped or unsimulated: nowhere 0.7 fF" in out
    extraction["$1"] = "a"
    monkeypatch.setattr(sys.modules["flow.toyblock.subckt"], "netlist", lambda params: type("M", (), {"name": "Other"}))
    with pytest.raises(SystemExit, match="1 of 1 instances failed"):
        flow("--from", "pexsim", "--to", "pexsim", "--run", "mine", "--instance", "wired")
    assert "no testbench of toyblock instantiates Other directly" in capsys.readouterr().out


def test_pexsim_leaves_an_extraction_with_devices_or_none_alone(toy, tmp_path) -> None:
    """An extraction with devices and RC (a kit's, a planned signoff's) is not back-annotated, nor a
    layout not extracted; one made before its nets' probes is refused with what makes it again."""
    job = cli.Job("toyblock", "toypdk", "one", "one", None, tmp_path / "one", (Step.PEXSIM,), "mine")
    cli._mark(job.out, Step.PEX, 0.0, netlist="toy.pex.netlist", sha256="0", extractor="the kit's (against its source)")
    assert cli._pexsim(job) == {
        "skipped": "the kit's (against its source) extraction has devices and RC, not capacitances to back-annotate"
    }
    cli._mark(job.out, Step.PEX, 0.0, skipped="no LVS source")
    assert cli._pexsim(job) == {"skipped": "no extraction (no LVS source)"}
    cli._mark(job.out, Step.PEX, 0.0, netlist="toy.pex.netlist", extractor="KLayout-PEX", nets={"a": 1e-15})
    with pytest.raises(RuntimeError, match="no net probes .* then python -m flow toyblock --to pex --run mine"):
        cli._pexsim(job)


def test_the_dut_takes_a_flat_copy_with_the_capacitors_on_its_bits_and_its_cells_nets() -> None:
    """The DUT's flat copy names a cell's net by its path (``drive_n0``: no ``:``, which Spectre's
    names refuse) and keeps its ports and their usage; the capacitors join a bus's bit, a cell's net
    (KLayout's ``drive.n0``) and ground (its ground port: a net's to ``0`` and to it one capacitor),
    less its own drawn between the same nets, taken off once; a net it lacks is left out and
    counted."""
    import io

    import hdl21 as h
    from hdl21.primitives import C, R

    from flow.layout.annotate import Annotation

    cell = h.Module(name="Cell")
    cell.a, cell.y = h.Port(), h.Port()
    cell.n0 = h.Signal()
    cell.r0, cell.r1 = R(r=1)(p=cell.a, n=cell.n0), R(r=1)(p=cell.n0, n=cell.y)
    top = h.Module(name="Top")
    top.bits, top.out, top.vss = h.Port(width=2), h.Port(), h.Port(usage=h.Usage.GROUND)
    top.drive = cell(a=top.bits[1], y=top.out)
    top.cdrawn = C(c=2e-15)(p=top.out, n=top.vss)
    flat = runner._flattened(top)
    assert set(flat.signals) == {"drive_n0"} and set(flat.instances) == {"drive_r0", "drive_r1", "cdrawn"}
    assert flat.ports["vss"].usage == h.Usage.GROUND and flat.ports["bits"].width == 2
    found = Annotation(
        capacitors=(
            ("0", "out", 3e-15),
            ("bits_1", "drive.n0", 1e-16),
            ("out", "vss", 1e-15),
            ("nowhere", "out", 2e-16),
        ),
        total_f=0,
        mapped_f=0,
        unmapped={},
    )
    added = runner._add_capacitors(flat, found)
    assert added == {
        "added_f": pytest.approx(2.1e-15),
        "drawn_f": pytest.approx(2e-15),
        "unsimulated": {"nowhere": pytest.approx(2e-16)},
    }
    out = io.StringIO()
    h.netlist(flat, out, fmt="spectre")
    lines = [line for line in out.getvalue().splitlines() if "//" not in line]
    assert sum("( bits_1 drive_n0 )" in line for line in lines) == 2 and not any(":" in line for line in lines)
    assert sum("( out vss )" in line for line in lines) == 2  # the drawn one and the extraction's 2 fF more
