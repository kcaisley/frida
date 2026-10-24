"""The pipeline every migrated block follows (docs/pipeline.md), and the types its stages share.

A block's parameters (``Params``: the design; ``TbParams``: one testbench run of it) are built in
its ``params.py``, its circuit in ``subckt.py``, its testbench and simulator run in ``sim.py``; the
simulator's raw output becomes a ``Meas`` here (``read``: every saved signal on the simulator's own
time axis), the block's ``analysis.py`` turns measurements into ``Analysis`` results and metrics,
its ``plots.py`` into ``Plot`` specs, and its ``sweep.py`` into the ``Record`` of an instance.
Its ``sweep.py`` also gives its design space: families of instances (``@family``, each the cartesian
product of its axes) and named instances (``@named``).

``Meas`` also stays the base of the measurement types of the blocks not yet migrated (the ADC's,
the CDAC's), which add their own per-row arrays to it.
"""

from __future__ import annotations

import itertools
from abc import ABC
from collections.abc import Callable, Iterator, Mapping, Sequence
from dataclasses import dataclass, field, fields
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

import numpy as np


class Params(ABC):
    """A block's design parameters. Each block's ``Params`` (an hdl21 paramclass, which can have no
    base class) is registered as one (``Params.register``)."""


class TbParams(ABC):
    """One testbench run of a block: at least the PDK it runs in (``pdk``) and the design under test
    (``params``), and the conditions of the run."""

    pdk: str
    params: Any


# ---- the design space: families and named instances (a block's sweep.py)

type Axis = Sequence[Any] | Callable[[str], Sequence[Any]]


@dataclass(frozen=True)
class Family:
    """A family of a block's design space (``@family``): ``build(**knobs)`` makes one instance's
    ``Params``; each mapping in ``axes`` gives every knob its values, its instances the cartesian
    product of them (several mappings, the union of their products). A knob's values are the same in
    every PDK, or a function of the PDK. An instance is its parameters: a family's name and knobs
    only label it."""

    build: Callable[..., Any]
    axes: tuple[Mapping[str, Axis], ...]

    @property
    def name(self) -> str:
        return getattr(self.build, "__name__", "")

    def __call__(self, **knobs: Any) -> Any:
        return self.build(**knobs)

    def instances(self, pdk: str) -> Iterator[tuple[str, Any]]:
        """Each instance in ``pdk`` with its label, ``name(knob=value, ...)``."""
        for axes in self.axes:
            values = [axis if isinstance(axis, Sequence) else axis(pdk) for axis in axes.values()]
            for combination in itertools.product(*values):
                knobs = dict(zip(axes, combination, strict=True))
                label = ", ".join(f"{knob}={value}" for knob, value in knobs.items())
                yield f"{self.name}({label})", self.build(**knobs)


def family(**axes: Axis) -> Callable[[Callable[..., Any] | Family], Family]:
    """Make a function of a few named knobs, returning a block's ``Params``, a family swept over
    ``axes``; stacked, the families' products are joined, the first written first."""
    return lambda build: (
        Family(build.build, (axes, *build.axes)) if isinstance(build, Family) else Family(build, (axes,))
    )


@dataclass(frozen=True)
class Named:
    """One instance of a block by name (``@named``): in its design space (``swept``) or only named,
    for a layout or a comparison."""

    build: Callable[[], Any]
    swept: bool = True

    @property
    def name(self) -> str:
        return getattr(self.build, "__name__", "")

    def __call__(self) -> Any:
        return self.build()


def named(build: Callable[[], Any] | None = None, *, swept: bool = True) -> Any:
    """Make a function without arguments, returning a block's ``Params``, a named instance: ``@named``
    (swept), or ``@named(swept=False)``, named but not swept."""
    if build is None:
        return lambda function: Named(function, swept)
    return Named(build, swept)


def design(sweep: Any, pdk: str) -> Iterator[tuple[str, Any]]:
    """A block's design space in ``pdk`` before its PDK's validity (``params.valid``): each family's
    instances and each swept named instance of its sweep module, labelled, in source order."""
    for value in vars(sweep).values():
        if isinstance(value, Family):
            yield from value.instances(pdk)
        elif isinstance(value, Named) and value.swept:
            yield value.name, value()


def names(sweep: Any) -> dict[str, Named]:
    """A block's named instances, swept or not, by name."""
    return {value.name: value for value in vars(sweep).values() if isinstance(value, Named)}


@dataclass(frozen=True, slots=True)
class Identity:
    """Instance and design identity shared by measurements and their results.

    ``group`` is the physical board number or a Monte Carlo seed. ``index`` is
    the observed ADC channel or a Monte Carlo iteration. Nominal simulations
    use ``None`` for both. ``dut`` holds the design parameters analyzed.
    """

    group: int | None
    index: int | None
    dut: Any


@dataclass(frozen=True, slots=True)
class Analysis:
    """Base of every typed analysis result: identity only, no behavior.

    ``dut`` is ``None`` only for instrument characterizations that involve no
    design under test, such as a raw oscilloscope capture or the diff-amp.
    """

    group: int | None
    index: int | None
    dut: Any

    @property
    def identity(self) -> Identity:
        return Identity(self.group, self.index, self.dut)


def measurement_identity(measurements: Sequence[Any]) -> Identity:
    """Return the one identity shared by every input measurement (or result), or raise."""

    if not measurements:
        raise ValueError("analysis requires at least one measurement")
    identities = [measurement.identity for measurement in measurements]
    first = identities[0]
    if any(identity != first for identity in identities[1:]):
        raise ValueError("analysis inputs must share one group, index, and DUT parameter set")
    return first


def check_identity(prior: Analysis | Sequence[Analysis], identity: Identity, *, name: str) -> None:
    """Raise unless every prior result has the consumer's group, index, and DUT params."""

    for result in (prior,) if isinstance(prior, Analysis) else prior:
        if result.identity != identity:
            raise ValueError(
                f"{name} ({type(result).__name__}) does not match the analyzed instance: "
                f"group {result.group}/{identity.group}, index {result.index}/{identity.index}, "
                f"DUT params {'equal' if result.dut == identity.dut else 'different'}"
            )


@dataclass(frozen=True, slots=True)
class MeasInfo:
    """Run information shared by every measurement."""

    backend: Literal["physical", "behavioral", "spice"]
    timestamp_utc: datetime
    instruments: dict[str, str] = field(default_factory=dict)
    readbacks: dict[str, str | int | float | bool] = field(default_factory=dict)
    source_path: Path | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class Wave:
    """Records of node voltages and supply currents, read like Cadence's ``v()`` and ``i()``.

    Keys are canonical net names from the circuit's net bundle, such as
    ``comp_out`` or ``comp.latch_p``, whether the source was a simulator or an
    oscilloscope. ``vin_diff`` is the one derived name: a differential probe
    observes no single net. Supply currents use the supply name and are
    positive for current drawn from the source. Every trace has one row per
    record, the measurement row given by ``record_index``, and one column per
    sample of ``time_s``.
    """

    record_index: np.ndarray
    time_s: np.ndarray
    v: dict[str, np.ndarray]
    i: dict[str, np.ndarray] = field(default_factory=dict)

    def __post_init__(self) -> None:
        shape = (len(self.record_index), len(self.time_s))
        if len(self.time_s) < 2 or np.any(np.diff(self.time_s) <= 0):
            raise ValueError("wave.time_s must contain at least two strictly increasing samples")
        if wrong := {name: trace.shape for name, trace in (*self.v.items(), *self.i.items()) if trace.shape != shape}:
            raise ValueError(f"wave traces must have shape {shape}: {wrong}")


@dataclass(frozen=True, slots=True, kw_only=True)
class Meas:
    """A measurement: identity, run information, the parameters that produced it, and its signals.

    ``group``, ``index``, and ``dut`` match :class:`Analysis`, so results copy them across.
    ``param`` holds the complete scan or testbench parameters. A simulation's measurement (``read``)
    holds every saved signal on the simulator's own time axis ``time_s`` (empty without signals):
    node voltages ``v`` and supply currents ``i`` (positive for current drawn), by canonical net
    name; nothing is resampled. The blocks not yet migrated add their per-row readback arrays as
    fields of a subclass (they share one row per conversion or trial, which is checked here) and
    records in ``wave``.
    """

    group: int | None
    index: int | None
    dut: Any
    info: MeasInfo
    param: Any
    wave: Wave | None = None
    time_s: np.ndarray = field(default_factory=lambda: np.zeros(0))
    v: dict[str, np.ndarray] = field(default_factory=dict)
    i: dict[str, np.ndarray] = field(default_factory=dict)

    def __post_init__(self) -> None:
        rows = {
            data_field.name: len(value)
            for data_field in fields(self)
            if data_field.name != "time_s" and isinstance(value := getattr(self, data_field.name), np.ndarray)
        }
        if len(set(rows.values())) > 1:
            raise ValueError(f"{type(self).__name__} readback arrays are not aligned: {rows}")
        if len(self.time_s) and (
            wrong := {
                name: trace.shape
                for name, trace in (*self.v.items(), *self.i.items())
                if trace.shape != self.time_s.shape
            }
        ):
            raise ValueError(f"signals must share the time axis's shape {self.time_s.shape}: {wrong}")

    @property
    def identity(self) -> Identity:
        return Identity(self.group, self.index, self.dut)

    @property
    def tb(self) -> Any:
        """Return the testbench parameters, nested inside scan parameters for a physical capture."""

        return getattr(self.param, "tb", self.param)


def read(raw: Path, tb: TbParams) -> Meas:
    """A simulation's raw transient (Spectre's nutbin) as a measurement of the testbench ``tb``:
    every saved signal on the simulator's own time axis, named by its net (``xtop.<net>`` and
    ``xtop.dut.<net>`` as ``<net>``; a supply source's current ``xtop.v<net>:p`` as ``i[<net>]``,
    positive for current drawn), the design ``tb.params``, Monte Carlo seed and iteration where
    ``tb`` has them."""

    from vlsirtools.spice.spectre import parse_nutbin

    raw = Path(raw)
    with raw.open("rb") as stream:
        plots = [plot for plot in parse_nutbin(stream).values() if "time" in plot.data]
    if len(plots) != 1:
        raise ValueError(f"{raw} must hold exactly one transient")
    data = plots[0].data
    time_s = np.asarray(data["time"], dtype=np.float64)
    v, i = {}, {}
    for name, values in data.items():
        if name == "time":
            continue
        values = np.asarray(values, dtype=np.float64)
        if name.endswith(":p") and name.startswith("xtop.v"):
            i[name.removeprefix("xtop.v").removesuffix(":p")] = -values
        else:
            v[name.removeprefix("xtop.").removeprefix("dut.")] = values
    return Meas(
        group=getattr(tb, "mc_seed", None),
        index=getattr(tb, "mc_index", None),
        dut=tb.params,
        info=MeasInfo(
            backend="spice",
            timestamp_utc=datetime.fromtimestamp(raw.stat().st_mtime, tz=UTC),
            instruments={"simulator": "Spectre"},
            readbacks={"raw_file": raw.name, "raw_points": len(time_s)},
        ),
        param=tb,
        time_s=time_s,
        v=v,
        i=i,
    )


@dataclass
class Plot:
    """One figure, backend-neutral: each series' y over the shared x, drawn by the viewer (Plotly,
    from its JSON) or by ``flow.plot.render`` (matplotlib). A record's plots are its condition
    sweeps."""

    name: str  # stable key, the same for every instance of a block
    title: str
    x_label: str  # with its unit: "Common mode (V)"
    y_label: str
    x: list[float]
    series: dict[str, list[float]]  # label -> y at each x (NaN where the point failed)
    x_log: bool = False
    y_log: bool = False
    figure: str | None = None  # an SVG under build/ the viewer shows in place of the plot (x, series empty)
    # step lines over x, each {"y": [...], "count": n}: how many records took it (the ADC's decision
    # paths), drawn weighted by their counts beside or instead of the series
    paths: list[dict[str, Any]] = field(default_factory=list)
    # each axis's ticks where its values alone do not say (the viewer's paperLayout infers them
    # otherwise: whole numbers tick at whole numbers, log axes at decades or 1, 2 and 5):
    # "integer" (whole-number ticks, never an exponent), "code" (an output code or a code estimate:
    # as "integer", whatever the values), "step" (a decision or stage index: 0 and at least every
    # even step labelled, every step ticked) or "real" (continuous, though the values are whole)
    x_ticks: str | None = None
    y_ticks: str | None = None
    # x is categories, not a quantity: x the indices 0, 1, 2, ... and these their names, the ticks
    # (the viewer ticks each category by its name, angled where they would collide; x_ticks unused)
    x_labels: list[str] | None = None
    # the series are a histogram: each y the count in the bin one unit wide centred on its x (an
    # output code), drawn as a step outline without markers or fill, so compared instances overlay
    histogram: bool = False
    # the legend's title, where the series are values of one quantity (the common modes)
    legend_title: str | None = None


@dataclass
class Record:
    """What one instance's characterization gives."""

    metrics: dict[str, float]
    details: list[Plot] = field(default_factory=list)
    # label -> the run whose measurement the viewer shows (the runner writes it, then its path)
    waves: dict[str, str] = field(default_factory=dict)
