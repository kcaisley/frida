"""The CLI (``python -m flow``): its steps from one to another, its runs, make-style resume,
``--dry-run`` and its refusals, on the toy block (``flow/conftest.py``'s ``toy``); its layout steps
with the tools stood in for (``tools``)."""

from __future__ import annotations

import importlib
import json
import os
import shutil
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from flow import __main__ as cli
from flow import pipeline, steps
from flow.conftest import _NowPool
from flow.sweep import runner

Step = steps.Step


def test_the_steps_run_from_one_to_another() -> None:
    """``--from`` and ``--to`` pick the steps between them, both included, each after those whose
    outputs it takes: an instance's steps are one chain, the record after postsim (whose measurements
    it takes where they exist), the run's table after it; one that does not lead to the other
    is refused."""
    chain = [Step.NETLIST, Step.PRESIM, Step.LAYOUT, Step.DRC, Step.LVS, Step.PEX, Step.POSTSIM, Step.RESULTS]
    assert steps.between(Step.NETLIST, Step.RESULTS) == chain
    assert steps.between(Step.RESULTS, Step.RESULTS) == [Step.RESULTS]
    assert steps.between(Step.NETLIST, Step.TABLE) == [*chain, Step.TABLE]
    assert steps.between(Step.NETLIST, Step.CIRCUIT) == [Step.NETLIST, Step.PRESIM, Step.CIRCUIT]
    assert steps.between(Step.NETLIST, Step.LVS) == [Step.NETLIST, Step.LAYOUT, Step.DRC, Step.LVS]
    assert steps.between(Step.NETLIST, Step.POSTSIM) == chain[:-1]
    assert steps.between(Step.PRESIM, Step.TABLE) == [Step.PRESIM, Step.POSTSIM, Step.RESULTS, Step.TABLE]
    assert steps.between(Step.LAYOUT, Step.RESULTS) == chain[2:]
    # each step's order puts it after what it takes; the record needs the sim alone
    assert all(before.value < step.value for step in Step for before in step.inputs)
    assert Step.RESULTS.required == {Step.NETLIST, Step.PRESIM, Step.RESULTS} and Step.POSTSIM in Step.RESULTS.ancestors
    with pytest.raises(SystemExit, match="--from layout does not lead to --to presim: presim needs netlist"):
        steps.between(Step.LAYOUT, Step.PRESIM)


def test_the_bare_command_prints_the_usage_the_steps_and_each_blocks_runs(capsys) -> None:
    """The bare command, and ``-h``: a help page (usage, options, steps, each block's runs by kind,
    examples) that fits a half-screen terminal."""
    cli.main([])
    out = capsys.readouterr().out
    lines = [line.rstrip() for line in out.splitlines()]
    assert lines[0] == "Usage" and lines[1].strip() == "python -m flow --block BLOCK --run RUN"
    assert {"Usage", "Options", "Steps", "Runs", "Examples"} <= set(lines)
    assert "[--from STEP] [--to STEP] [--dry-run]" in out and out.index("--from STEP") < out.index("--to STEP")
    assert any(line.split() == ["results", "netlist,", "presim;", "after", "postsim"] for line in lines)
    comp = next(line for line in lines if line.split()[:1] == ["comp"])
    assert comp.split() == ["comp", "frida1", "topologies", "adc_10bit"]
    assert max(map(len, lines)) <= 80
    cli.main(["--help"])
    assert capsys.readouterr().out == out
    assert {"adc", "capdac", "comp", "samp"} <= set(cli.pipeline_blocks())


def test_tab_completes_the_flags_the_blocks_their_runs_and_the_steps(capsys) -> None:
    """``--completion``'s bash script: after ``--block`` the blocks, after ``--run`` that block's
    runs, after ``--from``/``--to`` the steps, else the flags; another python command its own."""
    import shutil
    import subprocess

    cli.main(["--completion"])
    script = capsys.readouterr().out
    if shutil.which("bash") is None:
        pytest.skip("no bash")
    probe = (
        script
        + """
try() { COMP_WORDS=("$@"); COMP_CWORD=$((${#COMP_WORDS[@]}-1)); COMPREPLY=();
        __flow_complete python "${COMP_WORDS[-1]}" "${COMP_WORDS[-2]}"; echo "${COMPREPLY[*]}"; }
try python -m flow --block ""
try python -m flow --block comp --run ""
try python -m flow --block comp --run frida1 --t
try python -m flow --block comp --run frida1 --to p
try python -m fl
try python script.py ""
"""
    )
    lines = subprocess.run(["bash", "-c", probe], capture_output=True, text=True, check=True).stdout.splitlines()
    assert lines[0].split() == cli.pipeline_blocks()
    assert "frida1" in lines[1].split() and "adc_12bit" in lines[1].split()
    assert lines[2:5] == ["--to", "presim pex postsim", "flow"] and lines[5] == ""


def test_an_optimization_runs_its_study_and_the_viewer_keeps_its_command(monkeypatch) -> None:
    """``--run`` an optimization runs its study in each of its PDKs, its budget and workers its own
    (runs.py); the viewer keeps ``web.serve``; the old verbs and flags are gone."""
    from flow.opt import runner as opt
    from flow.web import server

    calls = []
    monkeypatch.setattr(opt, "optimize", lambda *args: calls.append(("opt", *args)))
    monkeypatch.setattr(server, "serve", lambda port, host: calls.append(("serve", port, host)))
    cli.main(["--block", "comp", "--run", "adc_12bit"])
    cli.main(["web.serve"])
    # its 48 workers, at most this machine's processors (CI's has 4)
    workers = min(48, os.cpu_count() or 1)
    assert calls == [("opt", "comp", "tsmc65", "adc_12bit", 500, workers), ("serve", 8765, "127.0.0.1")]
    for old in (["opt", "comp", "--problem", "adc(bits=12)"], ["comp", "--to", "results"]):
        with pytest.raises(SystemExit):
            cli.main(old)
    with pytest.raises(SystemExit, match="comp has no run 'nothing'"):
        cli.main(["--block", "comp", "--run", "nothing"])


@pytest.fixture
def flow(toy, tools, monkeypatch):
    """The CLI on the toy block in ``toypdk``, its instances run in this process, the signoff tools
    stood in for (``tools``: every run to the record lays out and signs off); ``flow(*argv)`` runs
    a command (``--run`` one of its singles: ``one``, ``wired``, ``signed``)."""
    monkeypatch.setattr(runner, "PDKS", ("toypdk",))
    monkeypatch.setattr(cli, "pipeline_blocks", lambda: ["toyblock"])
    monkeypatch.setattr(cli, "_pool", lambda workers: _NowPool())
    stamps = iter(f"20261108_0000{n:02d}" for n in range(100))
    monkeypatch.setattr(cli, "_stamp", lambda: next(stamps))
    return lambda *argv: cli.main(["--block", "toyblock", *argv])


@pytest.fixture
def simulated(toy, monkeypatch) -> list[str]:
    """The names of the toy's runs as they are simulated."""
    sim = importlib.import_module("flow.toyblock.sim")
    names: list[str] = []
    simulate = sim.simulate
    monkeypatch.setattr(sim, "simulate", lambda tb, run_dir: names.append(tb.name) or simulate(tb, run_dir))
    return names


def _instance(run: str) -> Path:
    """A single's folder in its run's latest folder: ``build/toyblock/<run>/<stamp>/toypdk/<run>``."""
    dated = sorted((runner.RUNS_DIR / "toyblock" / run).glob("2*"))
    return dated[-1] / "toypdk" / run


def test_a_block_runs_through_every_characterization_step(flow, simulated, capsys, monkeypatch) -> None:
    """``--to results`` makes the run, dated under its name: the netlist (the circuit and its size),
    each run simulated and its measurement kept (its raw file removed), and the record from the kept
    measurements, each step in its folder, the record beside them; the table from it."""
    flow("--run", "one", "--to", "results")
    out = capsys.readouterr().out
    assert "toyblock: new run" in out and "netlist ok" in out and "presim ok" in out and "results ok" in out
    assert simulated == ["screen", "search", "full"]
    instance = _instance("one")
    assert json.loads((instance.parents[1] / "run.json").read_text())["block"] == "toyblock"
    assert (instance / "netlist/toyblock.cdl").read_text().startswith("* toyblock in toypdk")
    assert json.loads((instance / "netlist/geometry.json").read_text()) == {"devices": 0.0}
    assert sorted(path.parent.name for path in instance.glob("presim/*/result.h5")) == ["full", "screen", "search"]
    assert not list(instance.rglob("raw.txt"))
    laid = {"layout", "drc", "lvs", "pex", "postsim"}
    assert {path.parent.name for path in instance.glob("*/step.json")} == {"netlist", "presim", "results", *laid}
    record = json.loads((instance / "instance.json").read_text())
    assert record["error"] is None, record["error"]
    # no LVS source, so nothing extracted: the pre-layout metrics alone, and the layout's outcome
    assert record["evidence"] == "prelayout" and "prelayout" not in record
    assert record["layout"]["error"] is None and record["layout"]["lvs_correct"] is None
    assert record["name"] == "one" and record["label"] == "one" and record["level"] == pipeline.Level.FULL.value
    reads = {"read_screen": True, "read_search": True, "read_full": True}
    # the layout's area joined (2 x 1 um), no device area to give a density
    assert record["metrics"] == {"devices": 0.0, **reads, "layout_area_um2": 2.0, "density": None}
    assert record["netlist"].endswith("toypdk/one/netlist/toyblock.cdl")
    # the table, from the run's records
    data = runner.RUNS_DIR / "web/data/sweep"
    monkeypatch.setattr(runner, "DATA_DIR", data)
    flow("--run", "one", "--from", "table", "--to", "table")
    table = json.loads((data / "toyblock/runs/one/20261108_000000.json").read_text())
    assert [row["id"] for row in table["rows"]] == [record["id"]] and table["run"] == "one/20261108_000000"


def test_a_design_that_misses_a_bound_is_rejected_from_its_evidence_on(flow, capsys) -> None:
    """A run's bounds (``@single(bounds=...)``, as a grid's and an optimization's) judge an instance
    after each step whose evidence they reach, on what the steps established so far: a miss rejects
    it there, the steps after it not run but the record, which keeps the rejection; a run resumed
    past the step keeps it, judged again from the kept metrics."""
    flow("--run", "unread", "--to", "results")
    out = capsys.readouterr().out
    assert "toypdk/unread/presim rejected: rejected at presim (prelayout): read_full True (must be False)" in out
    assert "toypdk/unread/layout not run: (rejected at presim)" in out and "toypdk/unread/results ok" in out
    instance = _instance("unread")
    record = json.loads((instance / "instance.json").read_text())
    assert record["rejected"] == {"step": "presim", "evidence": "prelayout", "bounds": {"read_full": [True, False]}}
    assert record["evidence"] == "prelayout" and not (instance / "layout").exists()
    # the layout's own area, not the netlist's estimate (no devices here), rejects this one
    flow("--run", "tiny", "--to", "results")
    out = capsys.readouterr().out
    assert "toypdk/tiny/layout rejected: rejected at layout (layout): layout_area_um2 2 > 1" in out
    assert "toypdk/tiny/drc not run: (rejected at layout)" in out
    assert json.loads((_instance("tiny") / "layout/step.json").read_text())["metrics"] == {"layout_area_um2": 2.0}
    flow("--run", "tiny", "--from", "drc", "--to", "results")
    out = capsys.readouterr().out
    assert "toypdk/tiny/layout rejected" in out and "toypdk/tiny/drc not run: (rejected at layout)" in out
    assert json.loads((_instance("tiny") / "instance.json").read_text())["rejected"]["step"] == "layout"
    # every run kind states its bounds alike
    toy = importlib.import_module("flow.toyblock.runs")
    assert toy.one.bounds("toypdk") == () and toy.tiny.bounds("toypdk")[0].since is pipeline.Evidence.LAYOUT


def test_a_step_resumes_where_its_output_is_complete(flow, simulated, capsys) -> None:
    """Make's rule: a run from the netlist is a new one, dated; ``--from`` a later step resumes the
    run's latest, a step whose output is complete, and not older than what it needs, skipped,
    one deleted made again, and every step after it; ``--from results`` analyses again what the sim
    step kept, without simulating."""
    flow("--run", "one", "--to", "results")
    instance = _instance("one")
    capsys.readouterr()
    simulated.clear()
    flow("--run", "one", "--from", "presim", "--to", "results")
    out = capsys.readouterr().out
    assert "the latest run" in out and all(f"one/{s} done" in out for s in ("presim", "results")) and not simulated
    shutil.rmtree(instance / "results")
    (instance / "instance.json").unlink()
    flow("--run", "one", "--from", "results", "--to", "results")
    out = capsys.readouterr().out
    assert "the latest run" in out and "results ok" in out and not simulated
    assert json.loads((instance / "instance.json").read_text())["metrics"]["read_full"] is True
    # one run's measurement gone and the presim step's record with it: only that run simulated, and
    # the record after it made again
    shutil.rmtree(instance / "presim/search")
    (instance / "presim/step.json").unlink()
    record = (instance / "results/step.json").read_text()
    flow("--run", "one", "--from", "presim", "--to", "results")
    assert simulated == ["search"] and "presim ok" in capsys.readouterr().out
    assert steps.done(instance, Step.RESULTS) and (instance / "results/step.json").read_text() != record
    # from the netlist again: a new run beside the first, which stays
    flow("--run", "one", "--to", "results")
    assert (
        _instance("one") != instance
        and steps.done(instance, Step.RESULTS)
        and steps.done(_instance("one"), Step.RESULTS)
    )
    assert simulated == ["search", "screen", "search", "full"]


def test_a_later_step_needs_its_run(flow, toy, capsys) -> None:
    """``--from`` past the netlist works in the run's latest folder, which must exist."""
    with pytest.raises(SystemExit, match="no run of toyblock's one yet: python -m flow --block toyblock --run one"):
        flow("--run", "one", "--from", "results", "--to", "results")
    flow("--run", "one", "--to", "presim")
    flow("--run", "one", "--from", "results", "--to", "results")
    assert (_instance("one") / "instance.json").exists()


def test_a_search_runs_in_its_pdks(flow, toy, monkeypatch, capsys) -> None:
    """A run runs in every PDK whose kit is here and that admits its designs, or in those it names."""
    import importlib.util

    monkeypatch.setattr(runner, "PDKS", ("toypdk", "otherpdk"))
    monkeypatch.setattr(importlib.util, "find_spec", lambda name, *rest: object())
    flow("--run", "one", "--to", "results", "--dry-run")
    assert [line.split()[0] for line in capsys.readouterr().out.splitlines()[1:3]] == ["toypdk", "otherpdk"]


def test_dry_run_prints_what_would_run_and_runs_nothing(flow, toy, capsys) -> None:
    flow("--run", "one", "--to", "results", "--dry-run")
    out = capsys.readouterr().out.splitlines()
    chain = "netlist, presim, layout, drc, lvs, pex, postsim, results"
    assert out[0].startswith("toyblock: new run") and out[0].endswith(f"steps {chain}")
    # the sim's runs and postsim's again (at most: postsim does without an extraction)
    assert out[1] == f"toypdk one (one): {chain}; 6 simulator runs"
    assert out[2] == "1 instance in 1 PDK: 8 steps to run, 0 complete, about 6 simulator runs"
    assert not (runner.RUNS_DIR / "toyblock").exists()
    flow("--run", "one", "--to", "presim")
    capsys.readouterr()
    flow("--run", "one", "--from", "results", "--to", "table", "--dry-run")
    out = capsys.readouterr().out.splitlines()
    assert out[0].startswith("toyblock: the latest run") and out[1] == "toypdk one (one): results"
    assert out[2].endswith("0 complete, about 0 simulator runs; then the table")


def test_dry_run_marks_the_steps_that_would_fail_and_why(flow, toy, capsys) -> None:
    """A step whose inputs are neither complete nor made first would fail: ``--dry-run`` says so,
    with the command that makes them, and the steps after it not run; the totals count them."""
    flow("--run", "one", "--to", "netlist")
    capsys.readouterr()
    flow("--run", "one", "--from", "results", "--to", "figures", "--dry-run")
    lines = capsys.readouterr().out.splitlines()
    command = "python -m flow --block toyblock --run one --from presim --to presim"
    assert lines[1] == (
        f"toypdk one (one): results (fails: results needs its presim step's output: {command}), "
        "figures (fails: not run, as results fails)"
    )
    assert lines[2] == "1 instance in 1 PDK: 0 steps to run, 2 would fail, 0 complete, about 0 simulator runs"


def test_the_table_has_each_run_of_the_block_its_own(flow, tools, monkeypatch) -> None:
    """The table step exports each of the block's runs as a table of its own, the run it was given
    the one the viewer opens on: a newer run of a layout alone leaves the run before as it was."""
    data = runner.RUNS_DIR / "web/data/sweep"
    monkeypatch.setattr(runner, "DATA_DIR", data)
    flow("--run", "one", "--to", "results")
    flow("--run", "wired", "--to", "layout")
    flow("--run", "wired", "--from", "table", "--to", "table")
    one, wired = (runner.instance_id("toypdk", build()) for build in _named("one", "wired"))
    tables = {
        run: {row["id"]: row for row in json.loads((data / f"toyblock/runs/{run}.json").read_text())["rows"]}
        for run in ("one/20261108_000000", "wired/20261108_000001")
    }
    assert tables["one/20261108_000000"][one]["metrics"]["read_full"] is True
    assert set(tables["wired/20261108_000001"]) == {wired} and tables["wired/20261108_000001"][wired]["metrics"] == {}
    catalog = json.loads((data / "catalog.json").read_text())["toyblock"]
    assert [entry["label"] for entry in catalog["runs"]] == ["wired/20261108_000001", "one/20261108_000000"]
    assert catalog["default"] == "wired/20261108_000001" and not (data / "toyblock.json").exists()


def _named(*names: str):
    module = importlib.import_module("flow.toyblock.runs")
    return [getattr(module, name) for name in names]


def test_a_step_without_its_inputs_fails_naming_the_command_that_makes_them(flow, toy, capsys) -> None:
    flow("--run", "one", "--to", "netlist")
    with pytest.raises(SystemExit, match="1 of 1 instances failed"):
        flow("--run", "one", "--from", "results", "--to", "results")
    out = capsys.readouterr().out
    assert "results failed: results needs its presim step's output: " in out
    assert "python -m flow --block toyblock --run one --from presim --to presim" in out
    # the table needs every instance's record
    with pytest.raises(SystemExit, match="table needs every instance's results, 1 of 1 have none"):
        flow("--run", "one", "--from", "table", "--to", "table")


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
        flow("--run", "one", "--to", "results")
    assert ": RuntimeError: no licence" in capsys.readouterr().out
    instance = _instance("one")
    record = json.loads((instance / "instance.json").read_text())
    assert record["error"].startswith("presim: ") and record["metrics"] == {}
    assert not steps.done(instance, Step.PRESIM) and (instance / "presim/screen/result.h5").exists()
    monkeypatch.setattr(sim, "simulate", simulate)
    flow("--run", "one", "--from", "presim", "--to", "results")
    out = capsys.readouterr().out
    assert "one/presim ok" in out and "one/results ok" in out
    assert json.loads((instance / "instance.json").read_text())["error"] is None


def test_the_circuit_step_adds_the_circuit_simulators_runs_and_records_again(flow, toy, capsys) -> None:
    flow("--run", "one", "--to", "results")
    flow("--run", "one", "--from", "circuit", "--to", "circuit")
    out = capsys.readouterr().out
    assert "one/circuit ok" in out
    instance = _instance("one")
    assert [path.parent.name for path in instance.glob("circuit/*/result.h5")] == ["circuit"]
    record = json.loads((instance / "instance.json").read_text())
    assert record["level"] == pipeline.Level.CIRCUIT.value and record["metrics"]["read_circuit"] is True
    assert steps.done(instance, Step.RESULTS)
    # recorded again later, the circuit runs stay in it
    shutil.rmtree(instance / "results")
    flow("--run", "one", "--from", "results", "--to", "results")
    assert json.loads((instance / "instance.json").read_text())["metrics"]["read_circuit"] is True


def test_a_block_whose_circuit_level_adds_no_runs_refuses_the_circuit_step(flow, toy) -> None:
    module = importlib.import_module("flow.toyblock.runs")
    testbenches = module.testbenches
    level = pipeline.Level
    module.testbenches = lambda pdk, params, at=level.FULL: testbenches(
        pdk, params, level.FULL if at is level.CIRCUIT else at
    )
    with pytest.raises(SystemExit, match="no circuit simulator runs beyond its full ones"):
        flow("--run", "one", "--to", "circuit")


def test_the_figures_step_draws_the_records_figures(flow, toy, capsys) -> None:
    flow("--run", "one", "--to", "figures")
    instance = _instance("one")
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

    flow("--to", "pex", "--run", "wired")
    out = capsys.readouterr().out
    assert "steps netlist, layout, drc, lvs, pex" in out
    assert "layout ok in" in out and "2 x 1 um" in out
    assert "drc ok in" in out and "0 violations (stand-in)" in out
    assert "match (stand-in)" in out and "pex ok in" in out and "1 nets" in out
    open_ = Checker.OPEN
    assert tools.calls == [("drc", "toy.gds", open_), ("lvs", "source.cdl", open_), ("pex", "toy.gds", open_)]
    instance = _instance("wired")
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
    assert lookup.laid_out("toyblock", "toypdk", importlib.import_module("flow.toyblock.runs").wired()) == entry
    # complete: skipped
    tools.calls.clear()
    flow("--run", "wired", "--from", "drc", "--to", "pex")
    out = capsys.readouterr().out
    assert all(f"/{s} done" in out for s in ("drc", "lvs", "pex")) and not tools.calls
    # DRC's output gone: DRC, then LVS and PEX after it, made again; the layout kept
    laid = (instance / "layout/step.json").read_text()
    shutil.rmtree(instance / "drc")
    flow("--run", "wired", "--from", "drc", "--to", "pex")
    assert "the latest run" in capsys.readouterr().out
    assert [call[0] for call in tools.calls] == ["drc", "lvs", "pex"]
    assert (instance / "layout/step.json").read_text() == laid
    # the layout made again: every signoff step after it is out of date
    shutil.rmtree(instance / "layout")
    flow("--run", "wired", "--from", "layout", "--to", "layout")
    assert (
        steps.done(instance, Step.LAYOUT) and not steps.done(instance, Step.DRC) and not steps.done(instance, Step.PEX)
    )


def test_a_kit_that_names_calibre_signs_off_by_it(flow, tools, monkeypatch) -> None:
    """The checker is the kit's configuration (its ``signoff.checker(block)``), not a flag."""
    from flow.layout import signoff
    from flow.layout.signoff import Checker

    assert signoff.checker("toypdk", "toyblock") is Checker.OPEN
    monkeypatch.setitem(sys.modules, "pdk.toypdk.signoff", SimpleNamespace(checker=lambda block: Checker.CALIBRE))
    assert signoff.checker("toypdk", "toyblock") is Checker.CALIBRE
    flow("--to", "pex", "--run", "wired")
    assert [call[2] for call in tools.calls] == [Checker.CALIBRE] * 3


def test_the_extraction_engine_is_the_kits_configuration_for_the_block(flow, tools, monkeypatch) -> None:
    """KLayout-PEX's engine is the kit's choice for the block (its ``signoff.engine(block)``), not a
    flag: FasterCap where the kit names none, the 2.5-D engine for the block it names it for."""
    from flow.layout import signoff
    from flow.layout.kpex import Engine

    flow("--to", "pex", "--run", "wired")
    assert signoff.engine("toypdk", "toyblock") is Engine.FASTERCAP and tools.engines == [Engine.FASTERCAP]
    kit = SimpleNamespace(engine=lambda block: Engine.RCX25 if block == "toyblock" else Engine.FASTERCAP)
    monkeypatch.setitem(sys.modules, "pdk.toypdk.signoff", kit)
    assert (
        signoff.engine("toypdk", "toyblock") is Engine.RCX25 and signoff.engine("toypdk", "other") is Engine.FASTERCAP
    )
    shutil.rmtree(_instance("wired") / "pex")  # extracted again, by the kit's engine now
    flow("--to", "pex", "--run", "wired")
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
    flow("--to", "pex", "--run", "signed")
    out = capsys.readouterr().out
    assert not tools.calls and ran == [("drc", "drc"), ("lvs", "lvs"), ("pex", "pex")]
    assert "0 violations (kitcheck)" in out and "no match (the kit's)" in out
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
    flow("--to", "pex", "--run", "wired")
    instance = _instance("wired")
    assert steps.done(instance, Step.PEX)
    shutil.rmtree(instance / "layout")
    assert not steps.done(instance, Step.DRC) and not steps.done(instance, Step.PEX)
    layout = importlib.import_module("flow.toyblock.layout")
    monkeypatch.setattr(layout, "lay_out", lambda params, pdk, run_dir: (_ for _ in ()).throw(RuntimeError("no room")))
    capsys.readouterr()
    tools.calls.clear()
    with pytest.raises(SystemExit, match="1 of 1 instances failed"):
        flow("--run", "wired", "--from", "layout", "--to", "pex")
    out = capsys.readouterr().out
    assert (
        ": RuntimeError: no room" in out
        and all(f"/{s} not run" in out for s in ("drc", "lvs", "pex"))
        and not tools.calls
    )
    assert not any(steps.done(instance, step) for step in (Step.LAYOUT, Step.DRC, Step.LVS, Step.PEX))
    entry = json.loads((instance / "instance.json").read_text())["layout"]
    assert entry["error"] and entry["drc_violations"] is None and entry["lvs_correct"] is None and entry["pex"] is None


def test_a_layout_without_an_lvs_source_is_checked_by_drc_alone(flow, tools, capsys) -> None:
    flow("--to", "pex", "--run", "one")
    out = capsys.readouterr().out
    assert [call[0] for call in tools.calls] == ["drc"]
    assert "lvs ok" in out and "not run: no LVS source" in out
    instance = runner.newest_run("toyblock") / "toypdk" / "one"
    entry = json.loads((instance / "instance.json").read_text())["layout"]
    assert entry["lvs_correct"] is None and entry["pex"]["skipped"].startswith("no LVS source")


def test_a_layout_other_than_its_netlist_is_not_extracted_and_its_record_still_written(flow, tools, capsys) -> None:
    """LVS that does not match refuses the extraction; the record, which needs only the netlist and
    the sim, is written all the same, with the layout's steps joined. DRC's violations are a count,
    not a failure."""
    tools.state.update(lvs=False, violations=3)
    with pytest.raises(SystemExit, match="1 of 1 instances failed"):
        flow("--to", "results", "--run", "wired")
    out = capsys.readouterr().out
    assert "results ok" in out and "3 violations (stand-in)" in out and "no match (stand-in)" in out
    assert "pex failed in" in out and "RuntimeError: LVS found the layout other than its netlist" in out
    assert "postsim not run: (after pex failed)" in out
    record = json.loads((_instance("wired") / "instance.json").read_text())
    assert record["evidence"] == "prelayout" and record["layout"]["drc_violations"] == 3
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
    flow("--to", "pex", "--run", "wired")
    instance = _instance("wired")
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
    flow("--run", "one", "--to", "netlist")
    capsys.readouterr()
    with pytest.raises(SystemExit, match="1 of 1 instances failed"):
        flow("--run", "one", "--from", "drc", "--to", "pex")
    out = capsys.readouterr().out
    assert (
        "drc failed: drc needs its layout step's output: python -m flow --block toyblock --run one --from layout --to layout"
        in out
    )
    assert "/lvs not run" in out and "/pex not run" in out and not tools.calls


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
    monkeypatch.setattr(
        annotate, "schematic_nets", lambda lvsdb, probes, gds=None: {net: mapped[net] for net in probes}
    )
    return mapped


def test_postsim_simulates_the_runs_again_with_the_extraction_on_the_schematic(flow, extraction, capsys) -> None:
    """``--to results``: the extraction's nets found on the schematic's through LVS (a gate's poly on
    its net, the capacitor between them shorted out), its capacitors in each run's DUT less the
    DUT's own drawn between the same nets, each run simulated again in ``postsim/``, and the record
    from those (``evidence`` ``postlayout``: the same metric names, the pre-layout ones beside them,
    the annotation's totals); the cell's inner net, a small share, reported."""
    flow("--to", "results", "--run", "wired")
    out = capsys.readouterr().out
    assert "steps netlist, presim, layout, drc, lvs, pex, postsim, results" in out
    assert "postsim ok in" in out and "3 runs, 2.2 fF added, 0.3% unmapped" in out
    instance = _instance("wired")
    runs = sorted(path.parent.name for path in instance.glob("presim/*/result.h5"))
    assert sorted(path.parent.name for path in instance.glob("postsim/*/result.h5")) == runs
    added = json.loads((instance / "postsim" / runs[0] / "annotation.json").read_text())
    assert added["instances"] == ["dut"] and added["added_f"] == pytest.approx(2.2e-15)
    assert added["drawn_f"] == pytest.approx(1e-15)
    record = json.loads((instance / "instance.json").read_text())
    assert record["evidence"] == "postlayout"
    assert set(record["metrics"]) - {"layout_area_um2", "density"} == {"devices", *(f"read_{run}" for run in runs)}
    assert record["prelayout"] == {"devices": 0.0, **{f"read_{run}": True for run in runs}}
    assert [detail["name"] for detail in record["prelayout_details"]] == [
        detail["name"] for detail in record["details"]
    ]
    annotation = record["annotation"]
    assert (
        annotation["extractor"] == "stand-in"
        and annotation["capacitors"] == 1
        and annotation["total_f"] == pytest.approx(3.71e-15)
    )
    assert annotation["mapped_f"] == pytest.approx(3.7e-15) and annotation["unmapped_f"] == pytest.approx(1e-17)
    assert annotation["unmapped_nets"] == {"$9": pytest.approx(1e-17)} and annotation["unannotated"] == []
    assert record["waves"] == {} and record["name"] == "wired"


def test_postsim_refuses_an_extraction_mostly_on_no_schematic_net(flow, extraction, capsys) -> None:
    """More than a small share of the capacitance on nets LVS paired with nothing: not simulated,
    the totals and the nets in the failure."""
    extraction["a"] = None
    with pytest.raises(SystemExit, match="1 of 1 instances failed"):
        flow("--to", "postsim", "--run", "wired")
    out = capsys.readouterr().out
    assert "ValueError: 3.51 fF of the extraction's 3.71 fF (94.6%, over 5%)" in out
    assert "a 3.51 fF, $9 0.01 fF" in out
    assert not list((_instance("wired") / "postsim").glob("*/result.h5"))


def test_postsim_refuses_capacitance_on_nets_the_dut_lacks_or_no_dut(flow, extraction, capsys, monkeypatch) -> None:
    """A schematic net LVS compared that the simulated DUT lacks counts against the same share as an
    unmapped one; testbenches none of which instantiates the DUT annotate nothing and fail."""
    import sys

    extraction["$1"] = "nowhere"
    with pytest.raises(SystemExit, match="1 of 1 instances failed"):
        flow("--to", "postsim", "--run", "wired")
    out = capsys.readouterr().out
    assert "0.71 fF of the extraction's 3.71 fF (over 5%) is on no net of netlist(mode=1)" in out
    assert "unmapped or unsimulated: nowhere 0.7 fF" in out
    extraction["$1"] = "a"
    monkeypatch.setattr(sys.modules["flow.toyblock.subckt"], "netlist", lambda params: type("M", (), {"name": "Other"}))
    with pytest.raises(SystemExit, match="1 of 1 instances failed"):
        flow("--from", "postsim", "--to", "postsim", "--run", "wired")
    assert "no testbench of toyblock instantiates Other directly" in capsys.readouterr().out


def test_postsim_leaves_an_extraction_with_devices_or_none_alone(toy, tmp_path) -> None:
    """An extraction with devices and RC (a kit's, a planned signoff's) is not back-annotated, nor a
    layout not extracted; one made before its nets' probes is refused with what makes it again."""
    job = steps.Job("toyblock", "toypdk", "one", "one", None, tmp_path / "one", (Step.POSTSIM,), "mine")
    steps._mark(
        job.out, Step.PEX, 0.0, netlist="toy.pex.netlist", sha256="0", extractor="the kit's (against its source)"
    )
    assert steps._postsim(job) == {
        "skipped": "the kit's (against its source) extraction has devices and RC, not capacitances to back-annotate"
    }
    steps._mark(job.out, Step.PEX, 0.0, skipped="no LVS source")
    assert steps._postsim(job) == {"skipped": "no extraction (no LVS source)"}
    # LVS without a deck: no database pairs the layout's nets with the schematic's
    steps._mark(job.out, Step.PEX, 0.0, extractor="stand-in", nets={"a": 1e-15})
    steps._mark(job.out, Step.LVS, 0.0, lvs_correct=None, lvs_report=None, lvs_checker=None)
    assert steps._postsim(job) == {"skipped": "no LVS database to find the extraction's nets on (LVS: no deck)"}
    steps._mark(job.out, Step.LVS, 0.0, lvs_correct=True, lvs_report="toy.lvsdb", lvs_checker="stand-in")
    steps._mark(job.out, Step.PEX, 0.0, netlist="toy.pex.netlist", extractor="KLayout-PEX", nets={"a": 1e-15})
    with pytest.raises(
        RuntimeError, match="no net probes .* then python -m flow --block toyblock --run mine --from pex --to pex"
    ):
        steps._postsim(job)


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
