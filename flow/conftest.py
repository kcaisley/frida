"""Fixtures the flow's tests share across blocks."""

import importlib
from pathlib import Path

import hdl21 as h
import pytest

from flow.sweep import runner


@pytest.fixture
def tsmc65(monkeypatch: pytest.MonkeyPatch) -> None:
    """TSMC65 the active PDK for one test, as the runners bind it before they build a netlist or a
    testbench (a generated ADC's DAC takes its devices and its reference from the active PDK); the
    PDK bound before it after. A checkout without the kit (CI's) skips the test."""
    logic = pytest.importorskip("pdk.tsmc65.hdl21").pdk_logic
    manager = importlib.import_module("hdl21.pdk.pdk")._mgr
    monkeypatch.setattr(manager, "default", manager.default)
    h.pdk.set_default(logic)


# ---- a toy block on the pipeline, for the CLI's steps and the runner's own contract: its reader
# (sim.read), a run a level (its circuit level one more), a figure, a testbench whose DUT draws a
# capacitor, and a layout of its own (layout.py's lay_out: no LVS source, one, or signed off by
# itself, by its mode)

_TOY = {
    "__init__.py": '"""A toy block."""\n',
    "params.py": '''"""A toy design: how its own layout signs itself off."""

from dataclasses import dataclass

import hdl21 as h

from flow import pipeline


@h.paramclass
class Params:
    mode = h.Param(dtype=int, desc="0: no LVS source; 1: an LVS source; 2: signed off by lay_out", default=0)


@dataclass(frozen=True)
class TbParams(pipeline.TbParams):
    pdk: str
    params: Params
    name: str
''',
    "subckt.py": '''"""A capacitor drawn between its port and ground."""

import hdl21 as h
from hdl21.primitives import C

from .params import Params


@h.generator
def netlist(params: Params) -> h.Module:
    toy = h.Module()
    toy.a = h.Port()
    toy.vss = h.Port(usage=h.Usage.GROUND)
    toy.cdrawn = C(c=1e-15)(p=toy.a, n=toy.vss)
    return toy
''',
    "sim.py": '''"""A run compiles its testbench and writes its name; the block reads it back itself."""

from datetime import datetime, timezone
from pathlib import Path

import hdl21 as h

from flow import pipeline

from .params import TbParams
from .subckt import netlist


def simulate(tb: TbParams, run_dir: Path) -> Path:
    bench = h.Module(name="ToyTb")
    bench.vss = h.Port()
    bench.a = h.Signal()
    bench.dut = netlist(tb.params)(a=bench.a, vss=bench.vss)
    h.pdk.compile(bench)
    run_dir.mkdir(parents=True, exist_ok=True)
    raw = run_dir / "raw.txt"
    raw.write_text(tb.name)
    return raw


def read(raw: Path, tb: TbParams) -> pipeline.Meas:
    info = pipeline.MeasInfo(backend="behavioral", timestamp_utc=datetime.now(timezone.utc), readbacks={"text": raw.read_text()})
    return pipeline.Meas(group=None, index=None, dut=tb.params, info=info, param=tb)
''',
    "runs.py": '''"""Five single designs (one characterized, two more for their layouts, two bounded); a run a level; a figure."""

from flow.pipeline import Bound, Evidence, Level, Meas, Plot, Record, single

from .params import Params, TbParams


@single
def one() -> Params:
    return Params()


@single
def wired() -> Params:
    return Params(mode=1)


@single
def signed() -> Params:
    return Params(mode=2)


@single(bounds=(Bound("read_full", False, since=Evidence.PRELAYOUT),))
def unread() -> Params:
    return Params()


@single(bounds=(Bound("layout_area_um2", 1.0, since=Evidence.LAYOUT),))
def tiny() -> Params:
    return Params()


def testbenches(pdk: str, params: Params, level: Level = Level.FULL) -> dict[str, TbParams]:
    names = [name for name in Level if name.value <= level.value]
    return {name.name.lower(): TbParams(pdk=pdk, params=params, name=name.name.lower()) for name in names}


def record(measurements: dict[str, Meas]) -> Record:
    reads = {name: meas.info.readbacks["text"] == name for name, meas in measurements.items()}
    figure = Plot("reads", "Reads", "Run", "Read", list(range(len(reads))), {"read": [float(r) for r in reads.values()]})
    return Record(metrics={f"read_{name}": read for name, read in reads.items()}, details=[figure])
''',
    "types.py": '''"""Its metrics: which run read back its own name."""

from dataclasses import dataclass

from flow import pipeline


@dataclass(frozen=True)
class Metrics(pipeline.Metrics):
    read_screen: bool = pipeline.metric("the screen run read back its name", "true", False)
    read_search: bool = pipeline.metric("the search run read back its name", "true", False)
    read_full: bool = pipeline.metric("the full run read back its name", "true", False)
''',
    "layout.py": '''"""Its own layout: a box, and what its mode says it signs off."""

from pathlib import Path

from klayout import db

from flow.layout.signoff import SignoffParams, write_plan

from .params import Params


def lay_out(params: Params, pdk: str, run_dir: Path) -> Path:
    run_dir.mkdir(parents=True, exist_ok=True)
    layout = db.Layout()
    top = layout.create_cell("toy")
    top.shapes(layout.layer(1, 0)).insert(db.Box(0, 0, 2000, 1000))
    gds = run_dir / "toy.gds"
    layout.write(str(gds))
    if params.mode == 1:
        (run_dir / "source.cdl").write_text(".subckt toy\\n.ends\\n")
    if params.mode == 2:
        source = run_dir / "toy.lvs.cdl"
        source.write_text(".subckt toy\\n.ends\\n")
        plan = SignoffParams("toypdk", gds, "toy", source, "toy", "toy", lvs_expectation="incorrect")
        write_plan(plan, run_dir / "signoff.json")
    return gds
''',
}


class _NowPool:
    """A process pool that runs each task at once, in this process (where the toy block imports)."""

    def __init__(self, **_kwargs) -> None:
        pass

    def __enter__(self):
        return self

    def __exit__(self, *_exc) -> None:
        return None

    def submit(self, function, *args, **kwargs):
        from concurrent.futures import Future

        future = Future()
        future.set_result(function(*args, **kwargs))
        return future


def _toy_compiled(block: str, pdk: str, params, path: Path) -> h.Module:
    """The toy's netlist step: an empty circuit, its netlist one line."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"* {block} in {pdk}\n")
    return h.Module()


@pytest.fixture
def toy(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """The toy block, ``flow.toyblock``, in a PDK of no devices (``toypdk``), its runs under
    ``tmp_path/build`` and characterized in this process."""
    import sys
    from types import SimpleNamespace

    import flow
    from flow import sweep
    from flow.layout.devices import device

    package = tmp_path / "flow" / "toyblock"
    package.mkdir(parents=True)
    for name, text in _TOY.items():
        (package / name).write_text(text)
    monkeypatch.setattr(flow, "__path__", [*flow.__path__, str(tmp_path / "flow")])
    monkeypatch.setitem(sys.modules, "pdk.toypdk", SimpleNamespace(pdk_logic=None))
    monkeypatch.setattr(h.pdk, "set_default", lambda logic: None)
    monkeypatch.setattr(h.pdk, "compile", lambda module, *args: None)
    monkeypatch.setattr(device, "resolve", lambda module, pdk: None)
    monkeypatch.setattr(sweep, "geometry", lambda module, pdk: {"devices": 0.0})
    monkeypatch.setattr(runner, "_compiled", _toy_compiled)
    monkeypatch.setattr(runner, "RUNS_DIR", tmp_path / "build")
    monkeypatch.setattr(runner, "ProcessPoolExecutor", _NowPool)
    for cached in (runner.design_space, runner.labelled_space):
        cached.cache_clear()
    yield importlib.import_module("flow.toyblock")
    for cached in (runner.design_space, runner.labelled_space):
        cached.cache_clear()
    for name in [name for name in sys.modules if name.startswith("flow.toyblock")]:
        del sys.modules[name]
