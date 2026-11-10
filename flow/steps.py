"""An instance's steps (``python -m flow``, whose manual ``flow.__main__`` is): the step graph
(``Step``, ``between``), make's rule over a step's folder (``done``: its ``step.json``), each step's
body, and ``run_steps``, which runs a job's steps on its instance in a worker of its own, each with
its log (``flow.logs.step_log``: ``<step>/step.log``, the warnings and errors on the console, their
counts by tool in ``step.json``).
"""

from __future__ import annotations

import json
import logging
import re
import time
import traceback
from dataclasses import asdict, dataclass
from enum import Enum, auto
from pathlib import Path
from typing import Any


class Step(Enum):
    """One tool's step over an instance (``TABLE``: over a run), in an order that puts each after
    the steps it needs (``needs``) and those whose outputs it takes where they exist (``after``);
    its folder in an instance's directory is its name. An instance's chain is linear: netlist,
    sim, layout, drc, lvs, pex, postsim, record (the run's table after: the viewer's)."""

    NETLIST = auto()
    PRESIM = auto()
    CIRCUIT = auto()
    LAYOUT = auto()
    DRC = auto()
    LVS = auto()
    PEX = auto()
    POSTSIM = auto()
    RESULTS = auto()
    FIGURES = auto()
    TABLE = auto()

    def __str__(self) -> str:
        return self.name.lower()

    @property
    def needs(self) -> tuple[Step, ...]:
        """The steps whose outputs this one takes."""
        match self:
            case Step.NETLIST:
                return ()
            case Step.PRESIM | Step.LAYOUT:
                return (Step.NETLIST,)
            case Step.CIRCUIT:
                return (Step.PRESIM,)
            case Step.RESULTS:
                return (Step.NETLIST, Step.PRESIM)
            case Step.FIGURES | Step.TABLE:
                return (Step.RESULTS,)
            case Step.DRC:
                return (Step.LAYOUT,)
            case Step.LVS:
                return (Step.DRC,)
            case Step.PEX:
                return (Step.LVS,)
            case Step.POSTSIM:
                return (Step.PRESIM, Step.LVS, Step.PEX)

    @property
    def after(self) -> tuple[Step, ...]:
        """The steps this one runs after and takes the outputs of where they ended, but does without
        where they failed or were not run: the record takes postsim's measurements (the post-layout
        metrics), else records the pre-layout ones alone."""
        return (Step.POSTSIM,) if self is Step.RESULTS else ()

    @property
    def inputs(self) -> tuple[Step, ...]:
        """The steps whose outputs this one takes: those it needs, then those it runs after."""
        return self.needs + self.after

    @property
    def evidence(self):
        """What this step adds to what is known of a design (``flow.pipeline.Evidence``), from which
        on bounds judge it: the netlist's estimates, the pre-layout simulation, the layout, its
        extraction; the record judges every bound on its own evidence (post-layout where postsim
        simulated, else pre-layout); None for a step that adds none."""
        from flow.pipeline import Evidence

        return {
            Step.NETLIST: Evidence.NETLIST,
            Step.PRESIM: Evidence.PRELAYOUT,
            Step.LAYOUT: Evidence.LAYOUT,
            Step.PEX: Evidence.EXTRACTION,
        }.get(self)

    @property
    def ancestors(self) -> set[Step]:
        """This step and every step whose output it takes, directly or through others: the steps a
        run to it runs (``between``)."""
        return {self}.union(*(step.ancestors for step in self.inputs))

    @property
    def required(self) -> set[Step]:
        """This step and every step it needs, directly or through others: a failure of any of them
        leaves it not run."""
        return {self}.union(*(need.required for need in self.needs))


def between(start: Step, stop: Step) -> list[Step]:
    """The steps from ``start`` to ``stop``, both included, in the order they run: those that need
    ``start`` and that ``stop`` needs."""
    steps = [step for step in Step if start in step.ancestors and step in stop.ancestors]
    if not steps:
        raise SystemExit(f"--from {start} does not lead to --to {stop}: {stop} needs {_needed(stop)}")
    return steps


def _needed(step: Step) -> str:
    """The steps ``step`` needs, as a sentence's words."""
    return ", ".join(str(need) for need in sorted(step.required - {step}, key=lambda s: s.value)) or "nothing"


@dataclass(frozen=True)
class Job:
    """One instance's steps in a run: its block, PDK, name in the run (a named instance's name, a
    grid's digest), label and parameters, its directory, the steps to run, the run as ``--run``
    takes it (for the commands a failure names) and the run's bounds in its PDK (``bounds(pdk)``
    of its ``@single``, ``@grid`` or ``@optimize``: ``flow.pipeline.Bound``), which reject it."""

    block: str
    pdk: str
    name: str
    label: str
    params: Any
    out: Path
    steps: tuple[Step, ...]
    run: str
    bounds: tuple[Any, ...] = ()


def _marker(out: Path, step: Step) -> Path:
    """A step's record of its run on an instance: ``<step>/step.json``, written once it ends."""
    return out / str(step) / "step.json"


def _ended(out: Path, step: Step) -> dict | None:
    """The step's record on this instance where it ended without error, else None."""
    path = _marker(out, step)
    if not path.exists():
        return None
    ended = json.loads(path.read_text())
    return ended if ended.get("error") is None else None


def done(out: Path, step: Step) -> bool:
    """Whether the step's output on this instance is complete: it ended without error, after each
    step it needs ended without error, each of those complete too (make's rule: made again where
    what it was made from, or what that was made from, is newer, failed or gone)."""
    ended = _ended(out, step)
    if ended is None:
        return False
    for need in step.needs:
        made = _ended(out, need)
        if made is None or made["finished"] > ended["finished"] or not done(out, need):
            return False
    # a step it runs after that ended since (made, failed or not run again) changes what it took
    for before in step.after:
        path = _marker(out, before)
        if path.exists() and json.loads(path.read_text())["finished"] > ended["finished"]:
            return False
    return True


def _mark(out: Path, step: Step, started: float, error: str | None = None, **outputs: Any) -> None:
    """The step's record on this instance: when it finished, its seconds, its error and outputs."""
    path = _marker(out, step)
    path.parent.mkdir(parents=True, exist_ok=True)
    finished = time.time()
    entry = {"step": str(step), "finished": finished, "seconds": round(finished - started, 2), "error": error}
    path.write_text(json.dumps({**entry, **outputs}, indent=1) + "\n")


def _command(job: Job, step: Step) -> str:
    """The command that makes ``step``'s output in this run, its latest folder (its designs whose
    output is complete skipped)."""
    return f"python -m flow --block {job.block} --run {job.run} --from {step} --to {step}"


def _missing(job: Job, step: Step) -> str | None:
    """What ``step`` needs on this instance that is not complete, and the command that makes it;
    None where it has all it needs."""
    for need in step.needs:
        if not done(job.out, need):
            return f"{step} needs its {need} step's output: {_command(job, need)}"
    return None


def _outputs(out: Path, step: Step) -> dict:
    """What a step that ended made on this instance (its ``step.json``), else nothing."""
    return _ended(out, step) or {}


def _netlist(job: Job) -> dict:
    """The circuit as simulated and its size (``flow.sweep.runner.write_netlist``)."""
    from flow.sweep import runner

    runner.write_netlist(job.block, job.pdk, job.params, job.out / "netlist")
    return {}


def _presim(job: Job) -> dict:
    """Each of the instance's testbench runs simulated and its measurement kept (``presim/<run>/``),
    and each net's capacitance from its devices at the runs' operating points (``device_f``, F)."""
    from flow.circuit.spectre import OPPOINT, device_capacitance
    from flow.sweep import runner

    runs = runner.testbenches_of(job.block, job.pdk, job.params)
    runner.simulate(job.block, job.pdk, runs, job.out / "presim")
    # each net's capacitance from its devices (their models' at each run's operating point), the
    # runs' mean: what the extraction's wiring adds to it, side by side in the viewer
    points = [device_capacitance(path) for path in sorted((job.out / "presim").glob(f"*/{OPPOINT}"))]
    nets = sorted({net for point in points for net in point})
    device = {net: sum(point.get(net, 0.0) for point in points) / len(points) for net in nets} if points else {}
    return {
        "runs": list(runs),
        **({"device_f": device} if device else {}),
        "stats": _simulation_stats(job.out / "presim"),
    }


def _simulation_stats(folder: Path) -> list:
    """The runs' numbers from their logs (``flow.circuit.spectre.log_stats``): the circuit (nodes,
    each primitive's instances), Spectre's preset, the transient's accepted steps (their mean),
    the times (each run's mean, all runs' sum) and the peak memory."""
    from flow.circuit.spectre import log_stats
    from flow.layout.stats import stat

    found = [log_stats(path) for path in sorted(folder.glob("*/spectre.log"))]
    if not found:
        return []
    mean = lambda key: (
        round(sum(values) / len(values), 2) if (values := [run[key] for run in found if run[key] is not None]) else None
    )
    first = found[0]
    return [
        stat("Circuit", "Nodes", first["nodes"], "#"),
        *(stat("Circuit", name.capitalize(), count, "#") for name, count in first["primitives"].items()),
        stat("Simulation", "Runs", len(found), "#"),
        stat("Simulation", "Preset", f"Spectre X {first['preset']}" if first["preset"] else "Spectre"),
        stat("Simulation", "Accepted steps", int(mean("accepted_steps") or 0) or None, "#"),
        stat("Simulation", "Parse time", mean("parse_s"), "s"),
        stat("Simulation", "Transient time", mean("tran_s"), "s"),
        stat("Simulation", "Run time", mean("elapsed_s"), "s"),
        stat("Simulation", "All runs", round(sum(run["elapsed_s"] or 0.0 for run in found), 2), "s"),
        stat("Simulation", "Peak memory", max((run["memory_b"] or 0) for run in found) or None, "B"),
    ]


def _fresh(out: Path, step: Step) -> Path:
    """The step's folder, emptied where the step ended before (its output out of date, made again
    whole); a step that failed or stopped part way keeps what it made, which it then reuses (the
    presim step its kept measurements)."""
    import shutil

    if _ended(out, step) is not None:
        shutil.rmtree(out / str(step))
    return out / str(step)


def _established(job: Job, step: Step) -> dict[str, Any]:
    """The metrics ``step`` established on this instance, from its evidence: the netlist's size and
    its area estimate (its devices over the densest packing a layout reaches, ``pipeline.DENSITY``:
    no layout is smaller), the pre-layout record's metrics, the layout's area; made once, when a
    bound first asks, and kept in its ``step.json`` (``metrics``)."""
    from flow import pipeline
    from flow.sweep import runner

    path = _marker(job.out, step)
    entry = json.loads(path.read_text())
    if "metrics" in entry:
        return entry["metrics"]
    sizes = json.loads((job.out / "netlist" / "geometry.json").read_text())
    match step:
        case Step.NETLIST:
            area = sizes.get("device_area_um2")
            found = {**sizes, **({"layout_area_um2": area / pipeline.DENSITY} if area else {})}
        case Step.PRESIM:
            files = {run: job.out / "presim" / run / "result.h5" for run in entry["runs"]}
            found = runner.results(job.block, job.pdk, job.params, None, files, sizes)["metrics"]
        case Step.LAYOUT if entry.get("cell_um"):
            width, height = entry["cell_um"]
            found = {"layout_area_um2": width * height}
        case _:
            found = {}
    entry["metrics"] = runner._json(found)
    path.write_text(json.dumps(entry, indent=1) + "\n")
    return entry["metrics"]


def _rejection(job: Job, upto: Step) -> dict[str, Any] | None:
    """Whether the run's bounds reject this instance from what its steps up to ``upto`` established
    (``_established``), each step's evidence judging the bounds it reaches
    (``flow.pipeline.missed``): the first step that does, its evidence and the bounds missed (each
    metric's value and limit); None where none does, or the run has no bounds. Judged again from
    the kept metrics on every run, so changed bounds judge a resumed run anew."""
    from flow import pipeline
    from flow.sweep import runner

    if not job.bounds:
        return None
    better, known = runner.betters(job.block), {}
    for step in Step:
        if step.value > upto.value:
            break
        if step.evidence is None or _ended(job.out, step) is None:
            continue
        known |= _established(job, step)
        missed = pipeline.missed(job.bounds, step.evidence, known, better)
        if missed:
            return {"step": str(step), "evidence": step.evidence.name.lower(), "bounds": missed}
    return None


def _shown_rejection(rejected: dict[str, Any]) -> str:
    """A rejection as a line says it: ``rejected at sim (prelayout): delay_0p5mv_s 2.1e-09 > 2e-09``."""
    misses = ", ".join(
        f"{metric} {value:.3g} {'>' if value > limit else '<'} {limit:.3g}"
        if isinstance(value, (int, float)) and not isinstance(limit, bool)
        else f"{metric} {value} (must be {limit})"
        for metric, (value, limit) in rejected["bounds"].items()
    )
    return f"rejected at {rejected['step']} ({rejected['evidence']}): {misses}"


def _results(job: Job, circuit: dict[str, Path] | None = None) -> dict:
    """The instance's record (``instance.json``), the last of its characterization: from the
    measurements its postsim step kept where it simulated the extraction (``evidence``
    ``postlayout``), the metrics and figures of the presim step's measurements beside them
    (``prelayout``, ``prelayout_details``: the estimates every step before the layout judged); else from the presim step's alone (``evidence``
    ``prelayout``: no layout, or one not extracted, or not back-annotated). Each with the circuit
    step's measurements (``circuit``, else those of a complete circuit step)."""
    from flow import pipeline
    from flow.sweep import runner

    out = job.out

    def kept(step: Step) -> dict[str, Path]:
        return {run: out / str(step) / run / "result.h5" for run in json.loads(_marker(out, step).read_text())["runs"]}

    if circuit is None and done(out, Step.CIRCUIT):
        circuit = kept(Step.CIRCUIT)
    annotated = _outputs(out, Step.POSTSIM) if done(out, Step.POSTSIM) else {}
    steps = [step for step in Step if step.value < Step.RESULTS.value and _ended(out, step) is not None]
    ran = sum(_outputs(out, step)["seconds"] for step in steps)
    sizes = json.loads((out / "netlist" / "geometry.json").read_text())

    def recorded(files: dict[str, Path]) -> dict[str, Any]:
        return runner.results(
            job.block,
            job.pdk,
            job.params,
            None,
            {**files, **(circuit or {})},
            sizes,
            label=job.label,
            name=job.name,
            level=pipeline.Level.CIRCUIT if circuit else pipeline.Level.FULL,
            netlist=out / "netlist" / f"{job.block}.cdl",
            seconds=ran,
        )

    rejected = _rejection(job, Step.RESULTS)
    if not done(out, Step.PRESIM):  # rejected before the simulation: what the netlist established
        entry = {
            **runner._base_results(job.block, job.pdk, job.params, job.label, job.name),
            "metrics": _established(job, Step.NETLIST),
            "evidence": pipeline.Evidence.NETLIST.name.lower(),
            "rejected": rejected,
        }
        runner.write_results(out / "instance.json", entry)
        return {"evidence": entry["evidence"], "rejected": rejected}
    prelayout = recorded(kept(Step.PRESIM))
    if annotated and not annotated.get("skipped"):
        entry = {
            **recorded(kept(Step.POSTSIM)),
            "evidence": pipeline.Evidence.POSTLAYOUT.name.lower(),
            "prelayout": prelayout["metrics"],
            # the pre-layout figures beside the post-layout ones, by the same names (the viewer
            # draws each pre-layout curve dotted under its post-layout one)
            "prelayout_details": prelayout["details"],
            "annotation": {key: annotated[key] for key in annotated if key != "runs"},
        }
    else:
        entry = {**prelayout, "evidence": pipeline.Evidence.PRELAYOUT.name.lower()}
    # the final verdict: every bound its evidence reaches, on the record's own metrics (a step's
    # rejection before it stands)
    evidence = pipeline.Evidence[entry["evidence"].upper()]
    if rejected is None and job.bounds:
        # judged as the steps' kept metrics are (``runner._json``: a number not finite as not measured)
        missed = pipeline.missed(job.bounds, evidence, runner._json(entry["metrics"]), runner.betters(job.block))
        if missed:
            rejected = {"step": str(Step.RESULTS), "evidence": entry["evidence"], "bounds": missed}
    entry["rejected"] = rejected
    entry["unjudged"] = [bound.metric for bound in job.bounds if bound.since.value > evidence.value]
    runner.write_results(out / "instance.json", entry)
    return {"circuit": bool(circuit), "evidence": entry["evidence"], "rejected": rejected}


def _circuit(job: Job) -> dict:
    """The circuit simulator's runs of the instance (``flow.sweep.runner.circuit_testbenches``) simulated
    and kept (``circuit/<run>/``), then its record made again with them."""
    from flow.sweep import runner

    runs = runner.circuit_testbenches(job.block, job.pdk, job.params)
    files = runner.simulate(job.block, job.pdk, runs, job.out / "circuit")
    started = time.time()
    _mark(job.out, Step.RESULTS, started, **_results(job, files))
    _join_layout(job)
    return {"runs": list(runs)}


def _figures(job: Job) -> dict:
    """Each of the record's figures (its details, ``flow.pipeline.Plot`` specs) drawn by matplotlib
    into ``figures/`` (``flow.plot.render``)."""
    from flow.pipeline import Plot
    from flow.plot import render

    record = json.loads((job.out / "instance.json").read_text())
    paths = [
        path
        for detail in record["details"]
        for path in render(Plot.from_json(detail), job.out / "figures" / detail["name"])
    ]
    return {"figures": [str(path.relative_to(job.out)) for path in paths]}


def _layout(job: Job) -> dict:
    """The instance laid out into ``layout/``: by its block's own ``lay_out`` where it has a
    ``layout.py`` (``flow.layout.step.lay_out_own``: the ADC's block assembly, or a FRIDA-1
    flavor's tape-out layout with its signoff plan, which the drc, lvs and pex steps run), else by
    ALIGN through the shared layout step (``flow.layout.step.lay_out_align``)."""
    from flow.layout import step

    if step.own_layout(job.block):
        return step.lay_out_own(job.block, job.pdk, job.params, job.out / "layout")
    # the design by its instance (a top cell of its own: COMP_FRIDA1_0), as the GDS of several
    # instances open or merge in one layout
    return step.lay_out_align(job.block, job.pdk, job.params, job.out / "layout", f"{job.block}_{job.name}")


def _plan(job: Job):
    """The signoff the block's own ``lay_out`` planned (``flow.layout.signoff.write_plan``), else
    None."""
    from flow.layout.signoff import read_plan

    path = _outputs(job.out, Step.LAYOUT).get("plan")
    return read_plan(Path(path)) if path else None


def _drc(job: Job) -> dict:
    """DRC of the layout's GDS into ``drc/``: as its ``lay_out`` planned it (``planned_drc``), else
    by the checker its kit names (``flow.layout.signoff.checker``: the open tools by default); its
    violations a count, not a failure."""
    from flow.layout import signoff

    laid, plan = _outputs(job.out, Step.LAYOUT), _plan(job)
    if plan is not None:
        return signoff.planned_drc(plan, job.out / "drc")
    source = Path(laid["source"]) if laid.get("source") else None
    checker = signoff.checker(job.pdk, job.block)
    return signoff.drc(job.pdk, Path(laid["gds"]), job.out / "drc", checker, source=source)


def _lvs(job: Job) -> dict:
    """LVS of the layout's GDS against its LVS source into ``lvs/``: as its ``lay_out`` planned it
    (``planned_lvs``: an expected mismatch among its warnings), else by its kit's checker; not run
    where the layout has no source (blocks side by side, unconnected)."""
    from flow.layout import signoff

    laid, plan = _outputs(job.out, Step.LAYOUT), _plan(job)
    if plan is not None:
        return signoff.planned_lvs(plan, job.out / "lvs")
    if not laid.get("source"):
        return {"lvs_correct": None, "skipped": "no LVS source: its blocks side by side, unconnected"}
    checker = signoff.checker(job.pdk, job.block)
    return signoff.lvs(job.pdk, Path(laid["gds"]), Path(laid["source"]), job.out / "lvs", checker)


def _pex(job: Job) -> dict:
    """The layout's extraction into ``pex/``: as its ``lay_out`` planned it (``planned_pex``, against
    its PEX source), else ``flow.layout.step.extracted`` (KLayout-PEX by the engine its kit names for
    the block, FasterCap by default, ``flow.layout.signoff.engine``; or the kit's extractor where its
    kit names Calibre), its engine among its outputs; not run where LVS was not (no source),
    refused where LVS found the layout other than its netlist (a planned signoff's LVS step holds
    it to its expectation)."""
    from flow.layout import signoff, step

    laid, checked, plan = _outputs(job.out, Step.LAYOUT), _outputs(job.out, Step.LVS), _plan(job)
    if plan is not None:
        return signoff.planned_pex(plan, job.out / "pex")
    if checked.get("skipped"):
        return {"skipped": checked["skipped"]}
    if checked.get("lvs_correct") is False:
        raise RuntimeError(f"LVS found the layout other than its netlist ({checked['lvs_report']}): not extracted")
    gds, engine = Path(laid["gds"]), signoff.engine(job.pdk, job.block)
    found = step.extracted(job.pdk, gds, gds.stem, job.out / "pex", signoff.checker(job.pdk, job.block), engine=engine)
    return {**found, **_extraction_stats(found, checked, gds, job.out / "pex")}


def _extraction_stats(found: dict, checked: dict, gds: Path, out: Path) -> dict:
    """What an extraction adds for the viewer: its nets' wiring capacitance on the schematic's nets
    (``schematic_nets``: a gate's poly, ``$6``, on its schematic net through LVS, ``flow.layout.annotate``;
    a floating net apart), and its numbers (``stats``: its nets, capacitors and conductors, FasterCap's
    solve)."""
    from flow.layout import annotate
    from flow.layout.stats import fastercap_stats, stat

    added: dict = {}
    if found.get("nets") and found.get("probes") and checked.get("lvs_report"):
        names = annotate.schematic_nets(Path(checked["lvs_report"]), json.loads(Path(found["probes"]).read_text()), gds)
        merged: dict[str, float] = {}
        for net, farad in found["nets"].items():
            name = names.get(net) or net
            name = "(floating)" if name == annotate.FLOATING else name
            merged[name] = merged.get(name, 0.0) + farad
        added["schematic_nets"] = dict(sorted(merged.items(), key=lambda item: -item[1]))
    log = out / "step.log"
    conductors = log.read_text(errors="replace").count(" : Conductor ") if log.exists() else None
    tolerance = re.search(r"(\d+(?:\.\d+)?)%", str(found.get("extractor") or ""))
    added["stats"] = [
        stat("Extraction", "Layout nets", len(found.get("nets") or {}) or None, "#"),
        stat("Extraction", "Schematic nets", len(added.get("schematic_nets") or {}) or None, "#"),
        stat("Extraction", "Conductors", conductors, "#"),
        stat("Extraction", "Capacitors", found.get("capacitors"), "#"),
        *fastercap_stats(out / "kpex" / "FasterCap_Output.txt", float(tolerance[1]) / 100 if tolerance else None),
    ]
    return added


def _postsim(job: Job) -> dict:
    """The instance's runs simulated again with its extraction back-annotated (``postsim/<run>/``),
    which the results step records (the post-layout metrics, the annotation's totals beside them):
    the extraction's capacitors, each net found on the
    schematic's through LVS (``flow.layout.annotate``), in each testbench's DUT
    (``flow.sweep.runner.simulate``). Not run where the layout was not extracted, nor for an
    extraction with devices and RC (a kit's: a block's own simulation of it, the ADC's circuit
    step's); refused where more than a small share of the capacitance has no schematic net. The
    record's annotation names the extractor (its engine). Not run either where LVS had no deck (no
    database to find the extraction's nets on)."""
    from flow.layout import annotate
    from flow.sweep import runner

    extracted, checked = _outputs(job.out, Step.PEX), _outputs(job.out, Step.LVS)
    if extracted.get("skipped"):
        return {"skipped": f"no extraction ({extracted['skipped']})"}
    if "nets" not in extracted:
        return {"skipped": f"{extracted['extractor']} extraction has devices and RC, not capacitances to back-annotate"}
    if not checked.get("lvs_report"):  # LVS ran without a deck: no database pairs layout nets with schematic ones
        return {"skipped": "no LVS database to find the extraction's nets on (LVS: no deck)"}
    if "probes" not in extracted:
        made = f"delete {runner._shown(job.out / 'pex')}, then {_command(job, Step.PEX)}"
        raise RuntimeError(f"its extraction has no net probes (made before them): make it again, {made}")
    laid = _outputs(job.out, Step.LAYOUT)
    gds = Path(laid["gds"]) if laid.get("gds") else None
    lvsdb = Path(checked["lvs_report"])
    found = annotate.annotation(Path(extracted["netlist"]), Path(extracted["probes"]), lvsdb, gds=gds)
    runs = runner.testbenches_of(job.block, job.pdk, job.params)
    for kept in (job.out / "postsim").glob("*/annotation.json"):  # a failed postsim's, kept to resume
        if kept.stat().st_mtime < _marker(job.out, Step.PEX).stat().st_mtime:  # of an extraction since redone
            (kept.parent / "result.h5").unlink(missing_ok=True)
    began = time.monotonic()
    runner.simulate(job.block, job.pdk, runs, job.out / "postsim", annotation=found)
    ran = time.monotonic() - began
    added = {run: job.out / "postsim" / run / "annotation.json" for run in runs}
    added = {run: json.loads(path.read_text()) for run, path in added.items() if path.exists()}
    if not any(entry["instances"] for entry in added.values()):
        dut = next((entry["dut"] for entry in added.values()), job.block)
        raise RuntimeError(f"no testbench of {job.block} instantiates {dut} directly: nothing was back-annotated")
    summary = {
        "extractor": extracted["extractor"],
        **found.summary(),
        **next((entry for entry in added.values() if entry["instances"]), {}),
        "unannotated": [run for run in runs if not added.get(run, {}).get("instances")],
    }
    return {"runs": list(runs), "seconds_simulated": round(ran, 2), **summary}


def _body(step: Step):
    """The function that runs ``step`` on one instance, None for one that runs over a run
    (``TABLE``)."""
    return {
        Step.NETLIST: _netlist,
        Step.PRESIM: _presim,
        Step.CIRCUIT: _circuit,
        Step.RESULTS: _results,
        Step.FIGURES: _figures,
        Step.LAYOUT: _layout,
        Step.DRC: _drc,
        Step.LVS: _lvs,
        Step.PEX: _pex,
        Step.POSTSIM: _postsim,
    }.get(step)


def _made(ended: dict) -> dict:
    """A step's outputs, from its ``step.json``: its record of the run (``_mark``'s, its log's
    counts too) and what only the viewer shows (its tool, its numbers, an extraction's nets by
    schematic net) left out."""
    kept = ("step", "finished", "seconds", "error", "log", "tool", "stats", "schematic_nets")
    return {key: value for key, value in ended.items() if key not in kept}


def _join_layout(job: Job) -> None:
    """The layout steps' outcome joined to the instance's record (``instance.json``, a record of
    the layout alone where it is not characterized, so the viewer's table and
    ``flow.sweep.lookup.laid_out`` find it): its GDS, LVS source, size, router, signoff, extraction,
    the layout step's error and each step's seconds; a characterized record also its layout area
    and density. Nothing where it is not laid out."""
    from flow.sweep import runner

    marked = {step: _marker(job.out, step) for step in (Step.LAYOUT, Step.DRC, Step.LVS, Step.PEX)}
    if not marked[Step.LAYOUT].exists():
        return
    made = {step: json.loads(path.read_text()) for step, path in marked.items() if path.exists()}
    ended = {step: made[step] for step in made if done(job.out, step)}
    laid, drc, lvs, pex = (ended.get(step, {}) for step in marked)
    path = job.out / "instance.json"
    record = (
        json.loads(path.read_text())
        if path.exists()
        else runner._base_results(job.block, job.pdk, job.params, job.label, job.name)
    )
    width, height = laid.get("cell_um") or (None, None)
    record["layout"] = {
        "gds": runner._shown(laid["gds"]) if laid.get("gds") else None,
        "netlist": runner._shown(laid["source"]) if laid.get("source") else None,
        "w_um": width,
        "h_um": height,
        "floorplan": None if not laid else "lay_out" if "plan" in laid else "generator" if laid["placed"] else None,
        "router": laid.get("router"),
        "route_shorts": laid.get("route_shorts"),
        "signoff": drc.get("checker"),
        "drc_violations": drc.get("violations"),
        "lvs_correct": lvs.get("lvs_correct"),
        "warnings": lvs.get("warnings"),
        "pex": runner._shown_pex(_made(pex)) if pex else None,
        "error": made[Step.LAYOUT].get("error"),
        "seconds": round(sum(entry["seconds"] for entry in made.values()), 2),
        "steps": {str(step): {"seconds": entry["seconds"], "error": entry["error"]} for step, entry in made.items()},
    }
    if record["metrics"] and width:
        gate = record["metrics"].get("device_area_um2")
        record["metrics"].update(layout_area_um2=width * height, density=gate / (width * height) if gate else None)
    runner.write_results(path, record)


def _brief(step: Step, outputs: dict) -> str:
    """What a step found, for its outcome: a simulation's runs, a layout's size, DRC's violations,
    LVS's verdict, an extraction's nets, a back-annotation's capacitance."""
    if outputs.get("skipped"):
        return f"not run: {outputs['skipped']}"
    match step:
        case Step.PRESIM | Step.CIRCUIT:
            return _count(len(outputs["runs"]), "run")
        case Step.LAYOUT:
            return f"{' x '.join(f'{v:g}' for v in outputs['cell_um'])} um"
        case Step.DRC:
            return f"{_count(outputs['violations'], 'violation')} ({outputs['checker']})"
        case Step.LVS:
            correct = outputs["lvs_correct"]
            verdict = "no deck" if correct is None else "match" if correct else "no match"
            return f"{verdict} ({outputs['lvs_checker'] or '-'})"
        case Step.PEX:
            return f"{len(outputs['nets'])} nets" if "nets" in outputs else outputs["extractor"]
        case Step.RESULTS:
            verdict = _shown_rejection(outputs["rejected"]) if outputs.get("rejected") else "met its bounds"
            return f"{outputs.get('evidence', '')}, {verdict}"
        case Step.RESULTS:
            verdict = _shown_rejection(outputs["rejected"]) if outputs.get("rejected") else "met its bounds"
            return f"{outputs.get('evidence', '')}, {verdict}"
        case Step.POSTSIM:
            return (
                f"{_count(len(outputs['runs']), 'run')}, {outputs.get('added_f', 0.0) * 1e15:.4g} fF added, "
                f"{outputs['unmapped_share']:.1%} unmapped"
                + (f", {outputs['floating_f'] * 1e15:.3g} fF floating" if outputs.get("floating_f") else "")
            )
    return ""


def logged(counts: dict[str, dict[str, int]]) -> str:
    """A step's warnings and errors by tool (``flow.logs.step_log``'s counts), for its outcome:
    ``align 4 errors, 10 warnings; spectre 26 warnings, 14 known`` (``flow.logs.WAIVERS``); nothing
    where there were none."""
    nouns = {"CRITICAL": "critical error", "ERROR": "error", "WARNING": "warning"}  # the worst first

    def said(levels: dict[str, int]) -> str:
        found = [_count(levels[level], noun) for level, noun in nouns.items() if level in levels]
        return ", ".join(found + ([f"{levels['WAIVED']} waived"] if "WAIVED" in levels else []))

    tools = [f"{tool} {said(levels)}" for tool, levels in counts.items()]
    return "; ".join(tools)


def run_steps(job: Job, events: Any = None) -> list[Outcome]:
    """The job's steps on its instance, in order, in this (fresh) process: each skipped where its
    output is complete (``done``), failed where what it needs is missing (``_missing``), else run
    in its folder (emptied where it ended before: ``_fresh``) with its log (``flow.logs.step_log``:
    every line, the flow's and its tools', in ``<step>/step.log``, each tool's whole output in its
    own log beside its results; the warnings and errors counted by tool in ``step.json``'s
    ``log``). A failure leaves
    the steps that need it not run (the record, which does without the layout's steps, runs); a
    characterization
    step's failure (netlist, sim, record) is also the instance's record
    (``flow.sweep.runner.failed_results``), and a layout step's joins it (``_join_layout``), so the
    viewer's table shows it. Each step's start and outcome an event onto ``events`` (a queue the
    run's dashboard takes them from, ``flow.dashboard``: ``key``, ``step``, ``state``, ``seconds``,
    ``found``, ``counts``), else its outcome on the console as it ends (``_report``); and the
    outcomes (``Outcome``: picklable, ``flow.__main__``)."""
    from flow.logs import step_log
    from flow.sweep import runner

    outcomes: list[Outcome] = []

    def report(step: Step, state: str, detail: str = "", seconds=None, found: str = "", counts=None) -> None:
        outcome = Outcome(str(step), state, seconds, found or detail, counts or {})
        outcomes.append(outcome)
        if events is None:
            _report(job, outcome)
        else:
            events.put({"key": key(job), **asdict(outcome)})

    failed: set[Step] = set()
    rejected: dict[str, Any] | None = None

    def judge(step: Step) -> None:
        """The run's bounds judged on what this step established, the instance rejected where it
        misses one (``_rejection``), said as its own line."""
        nonlocal rejected
        if rejected is None and step.evidence is not None and job.bounds:
            rejected = _rejection(job, step)
            if rejected is not None:
                report(step, "rejected", _shown_rejection(rejected))

    # a run resumed past a step that rejected the instance: the rejection stands (judged again
    # from what the steps before kept)
    earlier = [step for step in Step if job.steps and step.value < job.steps[0].value]
    if earlier and job.bounds:
        rejected = _rejection(job, earlier[-1])
        if rejected is not None:
            report(Step[rejected["step"].upper()], "rejected", _shown_rejection(rejected))
    for step in job.steps:
        if failed & step.required:
            failed.add(step)
            report(step, "not run", f"(after {next(s for s in job.steps if s in failed)} failed)")
            continue
        if rejected is not None and step is not Step.RESULTS:
            report(step, "not run", f"(rejected at {rejected['step']})")
            continue
        if done(job.out, step):  # its result, seconds and counts as it made them before
            before = _outputs(job.out, step)
            try:
                found = _brief(step, _made(before))
            except (KeyError, TypeError):  # a step.json from before a key it now states
                found = ""
            report(step, "done", seconds=before.get("seconds"), found=found, counts=before.get("log"))
            judge(step)
            continue
        missing = None if rejected is not None and step is Step.RESULTS else _missing(job, step)
        if missing:
            failed.add(step)
            report(step, "failed", missing)
            continue
        started = time.time()
        if events is not None:
            events.put({"key": key(job), "step": str(step), "state": "running"})
        folder = _fresh(job.out, step)
        laid = step in (Step.LAYOUT, Step.DRC, Step.LVS, Step.PEX, Step.RESULTS)  # joined to the record
        error = None
        with step_log(folder / "step.log") as counts:
            try:
                outputs = _body(step)(job)
            except Exception:  # noqa: BLE001 - every instance reports its own failure
                error = traceback.format_exc(limit=6)[-4000:]
                logging.getLogger("flow.steps").error(error.rstrip(), extra={"counted": False})
        if error is not None:
            _mark(job.out, step, started, error=error, log=counts)
            if step in (Step.NETLIST, Step.PRESIM, Step.RESULTS):
                runner.failed_results(
                    job.block, job.pdk, job.params, job.out, f"{step}: {error}", label=job.label, name=job.name
                )
            if laid:
                _join_layout(job)
            failed.add(step)
            last = error.strip().splitlines()[-1]
            report(step, "failed", seconds=time.time() - started, found=last, counts=counts)
            continue
        from flow import tools

        used = tools.of(str(step), outputs, job.out)
        _mark(job.out, step, started, log=counts, **outputs, **({"tool": used} if used else {}))
        if laid:
            _join_layout(job)
        report(step, "ok", seconds=time.time() - started, found=_brief(step, outputs), counts=counts)
        judge(step)
    return outcomes


@dataclass(frozen=True)
class Outcome:
    """How a step ended on an instance: its state (ok, failed, done: its output kept from before,
    then its seconds, result and counts as it made them; not run), its seconds (where it ran), what
    it found or why it failed, and its log's warnings and errors by tool (``flow.logs.step_log``'s
    counts)."""

    step: str
    state: str
    seconds: float | None
    found: str
    counts: dict[str, dict[str, int]]


def key(job: Job) -> str:
    """The instance's name in its run's dashboard and lines: ``<pdk>/<name>``."""
    return f"{job.pdk}/{job.name}"


def _report(job: Job, outcome: Outcome) -> None:
    """A step's outcome on the console, a line as it ends: its folder in the run (``<pdk>/<name>/
    <step>``, where its results and its ``step.log`` are), its state, seconds, what it found and
    its warnings and errors by tool (``logged``): ``tsmc65/frida1/layout ok in 5.0 s: 3.28 x 3.93
    um; align 4 errors, 10 warnings``."""
    head = f"{job.pdk}/{job.name}/{outcome.step} {outcome.state}"
    if outcome.seconds is not None:
        head += f" in {outcome.seconds:.1f} s"
    print(
        ": ".join([head, "; ".join(part for part in (outcome.found, logged(outcome.counts)) if part)]).rstrip(": "),
        flush=True,
    )


def _count(number: int, noun: str) -> str:
    """``number`` of ``noun``, plural where it is not one."""
    return f"{number} {noun}{'' if number == 1 else 's'}"
