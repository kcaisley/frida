"""The pipeline every migrated block follows (docs/pipeline.md), and the types its stages share.

A block's parameters (``Params``: the design; ``TbParams``: one testbench run of it) are built in
its ``params.py``, its circuit in ``subckt.py``, its testbench and simulator run in ``sim.py``; the
simulator's raw output becomes a ``Meas`` here (``read``: every saved signal on the simulator's own
time axis), the block's ``analysis.py`` turns measurements into ``Analysis`` results and metrics,
its ``plots.py`` into ``Plot`` specs, and its ``runs.py`` into the ``Results`` of an instance.
Its ``runs.py`` also gives its runs, each one run of the command line by its function's name
(``python -m flow --block comp --run frida1``): one design (``@single``), a grid of them (``@grid``:
spaces, each a design with some of its parameters widened, ``widen``), or an optimization over a
space (``@optimize``: a ``Problem``).

``Meas`` also stays the base of the measurement types of the blocks not yet migrated (the ADC's,
the CDAC's), which add their own per-row arrays to it.
"""

from __future__ import annotations

import itertools
import re
from abc import ABC
from collections.abc import Callable, Iterator, Mapping, Sequence
from dataclasses import asdict, dataclass, field, fields
from datetime import UTC, datetime
from enum import Enum, auto
from inspect import signature
from pathlib import Path
from types import UnionType
from typing import TYPE_CHECKING, Any, Literal, Union, cast, get_args, get_origin, get_type_hints

import numpy as np


class Pdk(Enum):
    """The PDKs a block is built in. A member's name in lower case is its package and folder
    (``Pdk.TSMC65``: ``pdk.tsmc65``, ``pdk/tsmc65``), the string records, paths and the command line
    keep (``pdk_of`` reads one back)."""

    TSMC65 = auto()
    TSMC28 = auto()
    IHP130 = auto()
    TOWER180 = auto()
    LF150 = auto()
    TPSC65 = auto()
    SKY130 = auto()
    GF180 = auto()


def pdk_of(pdk: str | Pdk) -> Pdk:
    """A PDK's member, from its folder's name (``"tsmc65"``) or the member itself."""
    return pdk if isinstance(pdk, Pdk) else Pdk[pdk.upper()]


class Params(ABC):
    """A block's design parameters. Each block's ``Params`` (an hdl21 paramclass, which can have no
    base class) is registered as one (``Params.register``)."""


class TbParams(ABC):
    """One testbench run of a block: at least the PDK it runs in (``pdk``) and the design under test
    (``params``), and the conditions of the run."""

    if TYPE_CHECKING:  # read-only: each block's TbParams, a frozen dataclass, declares them as fields

        @property
        def pdk(self) -> str: ...

        @property
        def params(self) -> Any: ...


# ---- a block's runs (its runs.py): one design, a grid of them, an optimization

type Axis = Sequence[Any] | Callable[[str], Sequence[Any]]

# the workers a run runs on where it names none; more than the machine's processors is refused
DEFAULT_WORKERS = 36


def _pdks(pdks: Sequence[Pdk] | None) -> tuple[Pdk, ...] | None:
    return tuple(pdks) if pdks is not None else None


def _admits(pdks: tuple[Pdk, ...] | None, pdk: str | Pdk) -> bool:
    return pdks is None or pdk_of(pdk) in pdks


@dataclass(frozen=True)
class Single:
    """One design of a block (``@single``): a function without arguments returning its ``Params``,
    run by its name (``frida1``); in the PDKs ``pdks`` names (None: every PDK whose kit is here and
    whose ``params.valid`` admits it), on a worker a design (``workers``: at most so many), rejected where it
    misses one of its ``bounds`` (``Bound``)."""

    build: Callable[[], Any]
    pdks: tuple[Pdk, ...] | None = None
    workers: int | None = None
    limits: tuple[Bound, ...] = ()

    @property
    def name(self) -> str:
        return getattr(self.build, "__name__", "")

    def bounds(self, pdk: str | Pdk) -> tuple[Bound, ...]:
        """Its bounds, in any PDK."""
        return self.limits

    def __call__(self) -> Any:
        return self.build()

    def instances(self, pdk: str | Pdk) -> Iterator[tuple[str, Any]]:
        """The design in ``pdk``, labelled by its name, where its PDKs admit it."""
        if _admits(self.pdks, pdk):
            yield self.name, self.build()


def single(
    build: Callable[[], Any] | None = None,
    *,
    pdks: Sequence[Pdk] | None = None,
    workers: int | None = None,
    bounds: Sequence[Bound] = (),
) -> Any:
    """Make a function without arguments, returning a block's ``Params``, a run of that one
    design: ``@single``, or ``@single(pdks=(Pdk.TSMC65,), bounds=(Bound(...), ...))``."""
    if build is None:
        return lambda function: Single(function, _pdks(pdks), workers, tuple(bounds))
    return Single(build, _pdks(pdks), workers, tuple(bounds))


type Run = Single | Grid | Optimize


def runs(module: Any) -> dict[str, Run]:
    """A block's runs (its runs module's ``@single``, ``@grid`` and ``@optimize`` functions) by
    name, in source order."""
    return {value.name: value for value in vars(module).values() if isinstance(value, (Single, Grid, Optimize))}


def singles(module: Any) -> dict[str, Single]:
    """A block's single designs (its runs module's ``@single`` functions) by name."""
    return {name: found for name, found in runs(module).items() if isinstance(found, Single)}


def design(module: Any, pdk: str) -> Iterator[tuple[str, Any]]:
    """Every design a block's runs name in ``pdk`` (before its ``params.valid``, where it has
    one), labelled, in source order: each single's and each grid's (an optimization's space is not
    enumerated)."""
    for value in vars(module).values():
        if isinstance(value, (Single, Grid)):
            yield from value.instances(pdk)


def workers(run: Single | Grid | Optimize, designs: int | None = None) -> int:
    """The workers a run runs on: one a design (``designs``, a single's or a grid's), else its own
    (``run.workers``, an optimization's; ``DEFAULT_WORKERS`` where it states none), at most the
    machine's processors (CI's runner has a few) and at most the run's own where it states them."""
    import os

    processors = os.cpu_count() or 1
    count = min(designs, run.workers or designs) if designs else run.workers or DEFAULT_WORKERS
    return max(1, min(count, processors))


# ---- spaces: a design with some of its parameters widened, for a grid (a block's runs.py, @grid)
# or an optimization (a problem's space, its @optimize)


@dataclass(frozen=True)
class Steps:
    """A number's range, ``low`` to ``high``: a grid takes ``n`` points across it (evenly, or evenly in
    log where ``log``; whole numbers for a whole-number parameter, each once), a search any value in
    it (on a log scale where ``log``). ``when``: where it applies, a member of an enumeration the
    design holds (``Bias.DYNAMIC``) or a test of the design; elsewhere the parameter keeps its base
    value."""

    low: float
    high: float
    n: int = 2
    log: bool = False
    when: Any = None


@dataclass(frozen=True)
class Values:
    """These values of a parameter: a grid takes each, a search chooses among them. ``when`` as for
    ``Steps``. ``names``, where they have them (``values({"frida1": comp.FRIDA1, ...})``): a grid
    labels a point by the value's name, a search offers the names."""

    values: tuple[Any, ...]
    when: Any = None
    names: tuple[str, ...] | None = None

    def labels(self) -> tuple[Any, ...]:
        """Each value as a label or a choice gives it: its name, a member's name, or itself."""
        if self.names is not None:
            return self.names
        return tuple(value.name if isinstance(value, Enum) else value for value in self.values)


type Widened = Steps | Values


# A space's parameters are set by attribute on a space typed as its Params (``widen``), so these
# return Any: a range assigned to a parameter of whole numbers is not a type error
def steps(low: float, high: float, n: int = 2, *, log: bool = False, when: Any = None) -> Any:
    """A number's range (``Steps``)."""
    return Steps(low, high, n, log, when)


def values(*choices: Any, when: Any = None) -> Any:
    """These values (``Values``); one mapping, these values by name."""
    if len(choices) == 1 and isinstance(choices[0], Mapping):
        return Values(tuple(choices[0].values()), when, tuple(choices[0]))
    return Values(tuple(choices), when)


def every(dtype: type, *, when: Any = None) -> Any:
    """Every member of an enumeration (False and True for a flag)."""
    return Values(tuple(dtype) if issubclass(dtype, Enum) else (False, True), when)


def holds(when: Any, design: Any) -> bool:
    """Whether a widened parameter applies to ``design``: always, where the design holds the member
    ``when`` names, or where the test ``when`` passes."""
    if when is None:
        return True
    if isinstance(when, Enum):
        return any(value is when for value in design.__dict__.values())
    return bool(when(design))


def grid_values(base: Any, name: str, widened: Widened) -> tuple[Any, ...]:
    """The values a grid gives a widened parameter of ``base``."""
    if isinstance(widened, Values):
        return widened.values
    if widened.n <= 1:
        points = [widened.low]
    elif widened.log:
        points = list(np.geomspace(widened.low, widened.high, widened.n))
    else:
        points = list(np.linspace(widened.low, widened.high, widened.n))
    value = getattr(base, name)
    if isinstance(value, int) and not isinstance(value, bool):
        return tuple(dict.fromkeys(round(float(point)) for point in points))
    return tuple(float(point) for point in points)


class Space:
    """A design (``base``, a block's ``Params``) with some of its parameters widened, each set by
    attribute (``widen``): ``steps`` or ``values`` (``every``) widen it, a bare value holds it there;
    every parameter not set is held at the base's value. Each is checked as it is set, by the
    parameter class: a name it does not have, or a value it does not take (a bare one, each of
    ``values``, the ends of ``steps``), raises there."""

    __slots__ = ("base", "widened")
    base: Any
    widened: dict[str, Widened]

    def __init__(self, base: Any) -> None:
        object.__setattr__(self, "base", base)
        object.__setattr__(self, "widened", {})

    def __setattr__(self, name: str, value: Any) -> None:
        cls = type(self.base)
        if name not in cls.__params__:
            raise AttributeError(f"{cls.__name__} has no parameter {name}")
        if isinstance(value, (Steps, Values)):
            ends = (
                value.values
                if isinstance(value, Values)
                else grid_values(self.base, name, Steps(value.low, value.high))
            )
            for end in ends:
                cls(**{**self.base.__dict__, name: end})
            self.widened[name] = value
        else:
            object.__setattr__(self, "base", cls(**{**self.base.__dict__, name: value}))
            self.widened.pop(name, None)

    def __getattr__(self, name: str) -> Any:
        return getattr(self.base, name)

    def points(self) -> Iterator[tuple[dict[str, Any], Any]]:
        """The space as a grid: every combination of its widened parameters' grid values (one whose
        ``when`` fails for the rest keeps its base value), each with the values it varies (those
        widened to more than one; a named value by its name) and the design."""
        cls = type(self.base)
        plain = {name: widened for name, widened in self.widened.items() if widened.when is None}
        conditional = {name: widened for name, widened in self.widened.items() if widened.when is not None}
        varies = {name for name, widened in self.widened.items() if len(grid_values(self.base, name, widened)) > 1}

        def labelled(name: str, widened: Widened) -> list[tuple[Any, Any]]:
            # each grid value with its label: a named value's name, else the value
            points = grid_values(self.base, name, widened)
            return list(zip(points, widened.labels() if isinstance(widened, Values) else points, strict=True))

        for combination in itertools.product(*(labelled(n, w) for n, w in plain.items())):
            chosen = {name: value for name, (value, _label) in zip(plain, combination, strict=True)}
            labels = {name: label for name, (_value, label) in zip(plain, combination, strict=True)}
            design = cls(**{**self.base.__dict__, **chosen})
            active = {name: widened for name, widened in conditional.items() if holds(widened.when, design)}
            for more in itertools.product(*(labelled(n, w) for n, w in active.items())):
                extra = {name: value for name, (value, _label) in zip(active, more, strict=True)}
                labels.update({name: label for name, (_value, label) in zip(active, more, strict=True)})
                shown = {name: label for name, label in labels.items() if name in varies}
                yield shown, cls(**{**design.__dict__, **extra})


def widen[P](base: P) -> P:
    """A space of ``base`` (a block's ``Params``) to widen by attribute: ``space = widen(Params())``,
    then ``space.diffpair_w = steps(32, 512, n=3, log=True)``. Typed as the Params it widens, so that
    an editor completes the parameters' names; it is a ``Space``."""
    return cast(P, Space(base))


def shown(value: Any) -> str:
    """A value as a label gives it: a member by its name, a number briefly."""
    if isinstance(value, Enum):
        return value.name
    return f"{value:g}" if isinstance(value, float) else str(value)


@dataclass(frozen=True)
class Grid:
    """A grid of a block's design space (``@grid``): ``build`` (given the PDK, where it takes one)
    gives a space or several (``widen``; their union), or several by name (a mapping), in the PDKs
    ``pdks`` names (None: every PDK), on ``workers``, a design rejected where it misses one of its
    ``bounds`` (a tuple of ``Bound``, or a function of the PDK giving one); its instances every point of each, labelled by the values that
    vary, ``name(parameter=value, ...)``, and by the space's name where it has one,
    ``name(space, parameter=value, ...)``."""

    build: Callable[..., Any]
    pdks: tuple[Pdk, ...] | None = None
    workers: int | None = None
    limits: Callable[[Pdk], Sequence[Bound]] = lambda pdk: ()

    @property
    def name(self) -> str:
        return getattr(self.build, "__name__", "")

    def bounds(self, pdk: str | Pdk) -> tuple[Bound, ...]:
        """Its bounds in ``pdk``: those it was given, or what the function it was given gives there."""
        return tuple(self.limits(pdk_of(pdk)))

    def built(self, pdk: str | Pdk) -> Any:
        """What ``build`` gives in ``pdk``: a space, several, or several by name."""
        return self.build(pdk_of(pdk)) if "pdk" in signature(self.build).parameters else self.build()

    def spaces(self, pdk: str | Pdk) -> dict[str, Space]:
        """The grid's spaces in ``pdk`` by name: their names, where ``build`` names them, else their
        places ("0", "1", ...)."""
        built = self.built(pdk)
        if isinstance(built, Mapping):
            return dict(built)
        return {str(place): space for place, space in enumerate((built,) if isinstance(built, Space) else built)}

    def instances(self, pdk: str | Pdk) -> Iterator[tuple[str, Any]]:
        """Each instance in ``pdk`` with its label."""
        if self.pdks is not None and pdk_of(pdk) not in self.pdks:
            return
        named = isinstance(self.built(pdk), Mapping)
        for title, space in self.spaces(pdk).items():
            for varied, design in space.points():
                words = [title] if named else []
                words += [f"{name}={shown(value)}" for name, value in varied.items()]
                yield f"{self.name}({', '.join(words)})", design


def grid(
    build: Callable[..., Any] | None = None,
    *,
    pdks: Sequence[Pdk] | None = None,
    workers: int | None = None,
    bounds: Sequence[Bound] | Callable[[Pdk], Sequence[Bound]] = (),
) -> Any:
    """Make a function (of the PDK, a ``Pdk``, where it takes one) returning a space, several, or
    several by name, a run of every design they hold, by its name: ``@grid``, or
    ``@grid(pdks=(Pdk.TSMC65, ...), workers=24, bounds=_adc_bounds_12)`` in those PDKs alone, on that
    many workers, a design that misses a bound rejected."""
    entry = tuple(pdks) if pdks is not None else None
    limits: Callable[[Pdk], Sequence[Bound]]
    if isinstance(bounds, Sequence):
        fixed: tuple[Bound, ...] = tuple(cast("Sequence[Bound]", bounds))

        def limits(pdk: Pdk) -> Sequence[Bound]:
            return fixed
    else:
        limits = bounds
    if build is None:
        return lambda function: Grid(function, entry, workers, limits)
    return Grid(build, entry, workers, limits)


# ---- metrics, evaluation levels and problems (a block's types.py and runs.py)


class Metrics:
    """A block's metrics (a frozen dataclass deriving this, in its types.py): each field one number
    or flag, named with its unit, declared with ``metric`` (which way is better)."""


type Better = Literal["lower", "higher", "true", "none"]


def metric(desc: str, better: Better, default: Any = float("nan")) -> Any:
    """A field of a ``Metrics`` dataclass: what it is and which way is better ("lower", "higher",
    "true" for a flag that must hold, "none" for a number only reported, a signed offset)."""
    return field(default=default, metadata={"desc": desc, "better": better})


def betters(cls: Any) -> dict[str, Better]:
    """Each metric of a ``Metrics`` dataclass and which way is better."""
    return {f.name: f.metadata["better"] for f in fields(cls) if "better" in f.metadata}


# the metrics every sweep and optimization record carries beside the block's own (the runner's
# geometry of the compiled circuit, the layout step's area), and which way is better
GEOMETRY: dict[str, Better] = {
    "child_cells": "lower",
    "devices": "lower",
    "device_area_um2": "lower",
    "layout_area_um2": "lower",
}


class Level(Enum):
    """How much of an instance's characterization to run: a quick screen (no transient noise), the
    runs a search needs, all of them, or all of them and the circuit simulator's too (a block whose
    full characterization is behavioral, as the converter's: SPICE confirmation of picked instances;
    elsewhere the same as ``FULL``). Each level's runs include the lower levels'."""

    SCREEN = 1
    SEARCH = 2
    FULL = 3
    CIRCUIT = 4


# the largest share of a layout its devices' own footprints cover (flow.sweep.geometry's device area):
# at most 0.873 over the 1615 comparator layouts of the TSMC65 studies (median 0.47, 2026-10-27), so
# a design's layout is at least its device area over it (``Evidence.NETLIST``'s area estimate)
DENSITY = 0.9


class Evidence(Enum):
    """How far along the pipeline a design is, in its order: its netlist (the estimates its devices
    give: its area at most their own over a layout's densest packing), its pre-layout simulation (the
    circuit's, or a behavioral one of laid-out blocks), its layout, its extraction, its post-layout
    simulation. A bound judges a design from the evidence it names on (``Bound.since``)."""

    NETLIST = auto()
    PRELAYOUT = auto()
    LAYOUT = auto()
    EXTRACTION = auto()
    POSTLAYOUT = auto()


@dataclass(frozen=True)
class Bound:
    """A limit a design must meet: its metric's value on the side the metric's ``better`` names
    (``limit``; a flag's ``True``, it must hold), judged from ``since`` on: a metric the layout only
    makes worse (area, delay, energy) from its first estimate, one the layout can move either way
    (offset, mismatch, noise) only once it is extracted or simulated after layout. The post-layout
    record judges every bound."""

    metric: str
    limit: float | bool
    since: Evidence = Evidence.POSTLAYOUT


def judged(bounds: Sequence[Bound], evidence: Evidence) -> tuple[Bound, ...]:
    """The bounds that may judge a design at ``evidence``: those whose ``since`` it has reached."""
    return tuple(bound for bound in bounds if bound.since.value <= evidence.value)


def missed(
    bounds: Sequence[Bound], evidence: Evidence, metrics: Mapping[str, Any], better: Mapping[str, Better]
) -> dict[str, tuple[Any, float | bool]]:
    """The bounds ``evidence`` may judge (``judged``) that ``metrics`` miss, each metric's value and
    limit by its name: a design is rejected where any is (a metric not measured misses none)."""
    found = judged(bounds, evidence)
    over = violations(found, metrics, better)
    return {bound.metric: (metrics.get(bound.metric), bound.limit) for bound in found if over[bound.metric] > 0}


@dataclass(frozen=True)
class Problem:
    """What an optimization of a block minimizes and what it must meet, by metric name: ``cost``, a
    product of factors, each a weight (the factor metric^w, in the metric's unit) or a weight and a
    scale (the factor (1 + (metric / scale)^2)^w, without unit, which stays near 1 below the scale);
    ``bounds`` (``Bound``), each a limit judged from its evidence on; ``space``, the designs it
    searches (``widen``: a design, its searched parameters widened, every other held)."""

    cost: Mapping[str, float | tuple[float, float]]
    bounds: tuple[Bound, ...] = ()
    space: Any = None

    @property
    def limits(self) -> dict[str, float | bool]:
        """Each bound's limit by its metric."""
        return {bound.metric: bound.limit for bound in self.bounds}


@dataclass(frozen=True)
class Optimize:
    """An optimization of a block (``@optimize``): a function (of the PDK, a ``Pdk``, where it takes
    one) returning its ``Problem``, run by its name (``adc_12bit``): ``budget`` trials in each of the
    PDKs ``pdks`` names (None: every PDK whose kit is here), a study each, on ``workers``."""

    build: Callable[..., Any]
    budget: int
    pdks: tuple[Pdk, ...] | None = None
    workers: int | None = None

    @property
    def name(self) -> str:
        return getattr(self.build, "__name__", "")

    def problem(self, pdk: str | Pdk) -> Problem:
        """Its problem in ``pdk``."""
        return self.build(pdk_of(pdk)) if "pdk" in signature(self.build).parameters else self.build()

    def bounds(self, pdk: str | Pdk) -> tuple[Bound, ...]:
        """Its problem's bounds in ``pdk``."""
        return tuple(self.problem(pdk).bounds)


def optimize(*, budget: int, pdks: Sequence[Pdk] | None = None, workers: int | None = None) -> Callable[..., Optimize]:
    """Make a function (of the PDK where it takes one) returning a ``Problem`` a run that
    optimizes it: ``@optimize(budget=500)``, ``@optimize(budget=500, pdks=(Pdk.TSMC65,), workers=24)``."""
    return lambda build: Optimize(build, budget, _pdks(pdks), workers)


def objective(problem: Problem, metrics: Mapping[str, Any]) -> float:
    """The problem's cost of an instance's metrics, in its factors' units (a comparator's J um^2):
    the product of its factors, each factor of a metric not measured (absent, None) or not a positive
    number left out (its bound, if any, says so). Summed as logs, so that no factor under- or
    overflows on its way."""
    total = 0.0
    for name, weight in problem.cost.items():
        value = metrics.get(name)
        if value is None or not np.isfinite(float(value)) or float(value) <= 0:
            continue
        if isinstance(weight, tuple):
            total += weight[0] * float(np.log1p((float(value) / weight[1]) ** 2))
        else:
            total += weight * float(np.log(float(value)))
    return float(np.exp(total))


def cost_unit(problem: Problem) -> str:
    """The unit of the problem's cost as a metric name's suffix (``j_um2``): each plain factor's metric
    unit (its name's last word), where every such factor has the weight 1; else none."""
    plain = {name: weight for name, weight in problem.cost.items() if not isinstance(weight, tuple)}
    if any(weight != 1 for weight in plain.values()):
        return ""
    return "_".join(name.rsplit("_", 1)[-1] for name in plain)


def violations(bounds: Sequence[Bound], metrics: Mapping[str, Any], better: Mapping[str, Better]) -> dict[str, float]:
    """Each bound's violation by its metric, at most 0 where it is met: log(value / limit) for a
    "lower" metric (-10, met by far, at zero), log(limit / value) for a "higher" one, 0 or 1 for a
    flag; 0 where the metric was not measured (absent), 1 where it was measured and is not a number
    (beyond what the bench resolves)."""
    result = {}
    for name, limit in ((bound.metric, bound.limit) for bound in bounds):
        value = metrics.get(name)
        if value is None:
            result[name] = 0.0
        elif better[name] == "true":
            result[name] = 0.0 if bool(value) is bool(limit) else 1.0
        elif not np.isfinite(float(value)):
            result[name] = 1.0
        elif better[name] == "lower":
            result[name] = float(np.log(float(value) / float(limit))) if float(value) > 0 else -10.0
        else:
            result[name] = float(np.log(float(limit) / float(value))) if float(value) > 0 else 1.0
    return result


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
    """A simulation's raw output (Spectre's nutbin) as a measurement of the testbench ``tb``: its
    one transient, every saved signal on the simulator's own time axis; or its Monte Carlo of
    operating points (the plots ``mc-<run>_<analysis>``), every saved signal one value a run, in
    the runs' order (``time_s`` empty; ``readbacks["runs"]`` their count). Signals are named by
    their net (``xtop.<net>`` and ``xtop.dut.<net>`` as ``<net>``; a supply source's current
    ``xtop.v<net>:p`` as ``i[<net>]``, positive for current drawn); the design ``tb.params``,
    Monte Carlo seed and iteration where ``tb`` has them."""

    from vlsirtools.spice.spectre import parse_nutbin

    raw = Path(raw)
    with raw.open("rb") as stream:
        plots = parse_nutbin(stream)
    transients = [plot for plot in plots.values() if "time" in plot.data]
    runs = sorted(
        (int(match.group(1)), plot)
        for name, plot in plots.items()
        if (match := re.match(r"mc-(\d+)_", name)) and "time" not in plot.data
    )
    if len(transients) == 1:
        data = {name: np.asarray(values, dtype=np.float64) for name, values in transients[0].data.items()}
        time_s = data.pop("time")
    elif not transients and runs:
        names = set(runs[0][1].data) - {"dummy"}
        data = {
            name: np.asarray([np.ravel(plot.data[name])[0] for _, plot in runs], dtype=np.float64) for name in names
        }
        time_s = np.zeros(0)
    else:
        raise ValueError(f"{raw} must hold exactly one transient or one Monte Carlo of operating points")
    v, i = {}, {}
    for name, values in data.items():
        if name.endswith(":p") and name.startswith("xtop.v"):
            i[name.removeprefix("xtop.v").removesuffix(":p")] = -values
        else:
            v[name.removeprefix("xtop.").removeprefix("dut.")] = values
    readbacks: dict[str, str | int | float | bool] = {"raw_file": raw.name, "raw_points": len(time_s)}
    if runs:
        readbacks["runs"] = len(runs)
    return Meas(
        group=getattr(tb, "mc_seed", None),
        index=getattr(tb, "mc_index", None),
        dut=tb.params,
        info=MeasInfo(
            backend="spice",
            timestamp_utc=datetime.fromtimestamp(raw.stat().st_mtime, tz=UTC),
            instruments={"simulator": "Spectre"},
            readbacks=readbacks,
        ),
        param=tb,
        time_s=time_s,
        v=v,
        i=i,
    )


@dataclass(frozen=True)
class Marker:
    """A labelled line across a plot at one value of an axis, in the axis's unit: in
    ``Plot.x_markers`` at an x (the bandwidth, Nyquist, a tone), in ``Plot.y_markers`` at a y (a
    noise floor, a detection limit). Drawn dashed over the curves, its label along it at the top (an
    x's) or over it at the right (a y's)."""

    at: float
    label: str = ""  # none drawn where empty


@dataclass(frozen=True)
class Band:
    """A labelled range of x shaded behind the curves (``Plot.x_bands``: a line's bins, a decade),
    in x's unit, its label at the top."""

    low: float
    high: float
    label: str = ""


@dataclass(frozen=True)
class Heatmap:
    """A map over a plot's x and y (``Plot.heatmap``): a value in each cell of a grid (an eye's
    samples, the conversions through each code estimate at each decision, the codes at each input),
    drawn under the curves in the density colours beside its colour bar. ``x`` and ``y`` are the
    cells' edges in the axes' units, one more than the cells (as ``calc.histogram2D`` gives them);
    ``z`` a row of values for each row of cells (``z[j][i]`` the cell from ``y[j]`` to ``y[j + 1]``
    and from ``x[i]`` to ``x[i + 1]``: a 2-D histogram's counts transposed), NaN where a cell holds
    nothing (the paper shows)."""

    x: list[float]
    y: list[float]
    z: list[list[float]]
    label: str  # the colour bar's title, with its unit where it has one: "Conversions"
    log: bool = False  # the colours by decade (counts over decades): a cell at or under 0 holds nothing

    def __post_init__(self) -> None:
        columns, rows = len(self.x) - 1, len(self.y) - 1
        if columns < 1 or rows < 1 or len(self.z) != rows or any(len(row) != columns for row in self.z):
            raise ValueError(
                f"a heatmap on {len(self.x)} x and {len(self.y)} y edges holds {rows} rows of {columns} values, "
                f"not {len(self.z)} rows of {sorted({len(row) for row in self.z})}"
            )


@dataclass
class Plot:
    """One figure, backend-neutral: each series' y over the shared x, drawn by the viewer (Plotly,
    from its JSON, ``to_json``) or by ``flow.plot.render`` (matplotlib), each with what it marks,
    shades or maps alike. A record's plots are its condition sweeps."""

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
    # y is categories (a map's rows: a rate, a signal): y the indices 0, 1, 2, ..., bottom first, and
    # these their names, the ticks (a map's row j between the edges j - 0.5 and j + 0.5; y_ticks unused)
    y_labels: list[str] | None = None
    # the series are a histogram: each y the count (or share) in its bin, centred on its x and as
    # wide as x's even step (an output code; a voltage's 25 µV), drawn as a step outline without
    # markers or fill, so compared instances overlay
    histogram: bool = False
    # the legend's title, where the series are values of one quantity (the common modes)
    legend_title: str | None = None
    # labelled lines across the plot (``Marker``: at an x, a bandwidth or a tone; at a y, a floor)
    # and labelled ranges of x shaded behind the curves (``Band``: a line's bins)
    x_markers: list[Marker] = field(default_factory=list)
    y_markers: list[Marker] = field(default_factory=list)
    x_bands: list[Band] = field(default_factory=list)
    # a map over x and y (``Heatmap``: an eye, a decision-path density), x and series empty or
    # curves over it
    heatmap: Heatmap | None = None

    def to_json(self) -> dict[str, Any]:
        """The spec as a record keeps it and the viewer reads it (``dataclasses.asdict``, NaN as it
        is: the writers make it null), its y categories, markers, bands and heatmap only where it has
        any."""
        spec = asdict(self)
        for name in ("y_labels", "x_markers", "y_markers", "x_bands", "heatmap"):
            if not spec[name]:
                del spec[name]
        return spec

    @classmethod
    def from_json(cls, spec: Mapping[str, Any]) -> Plot:
        """A spec from its JSON (``to_json``: a record's detail), its markers, bands and heatmap
        their types again (a null, where a point failed or a cell is empty, stays None; a missing
        key its default)."""
        given = dict(spec)
        heatmap = given.pop("heatmap", None)
        return cls(
            **{name: value for name, value in given.items() if name not in ("x_markers", "y_markers", "x_bands")},
            x_markers=[Marker(**marker) for marker in given.get("x_markers", ())],
            y_markers=[Marker(**marker) for marker in given.get("y_markers", ())],
            x_bands=[Band(**band) for band in given.get("x_bands", ())],
            heatmap=Heatmap(**heatmap) if heatmap else None,
        )


@dataclass
class Results:
    """What one instance's characterization gives."""

    metrics: dict[str, Any]  # numbers, flags, None where a level did not measure one
    details: list[Plot] = field(default_factory=list)
    # label -> the run whose measurement the viewer shows (the runner writes it, then its path)
    waves: dict[str, str] = field(default_factory=dict)


# The stages' functions declare what they are: ``@analysis`` and ``@plot`` check a function's
# signature when its module is imported (a block that breaks the contract does not import), and
# their types let a type checker see that an analysis returns an ``Analysis`` and a plot a ``Plot``.
# ``STAGE_FUNCTIONS`` holds each decorated function's stage, for the contract's test.
STAGE_FUNCTIONS: dict[Callable[..., Any], str] = {}


def annotation_is(annotation: Any, base: type, *, optional: bool = False) -> bool:
    """``annotation`` names ``base`` (a subclass, a union of them) or a sequence of them; with
    ``optional``, or None as well (``X | None``: None beside at least one of them)."""
    if get_origin(annotation) in (Sequence, list, tuple):
        return all(annotation_is(arg, base) for arg in get_args(annotation) if arg is not Ellipsis)
    if isinstance(annotation, UnionType) or get_origin(annotation) is Union:
        members = [arg for arg in get_args(annotation) if not (optional and arg is type(None))]
        return bool(members) and all(annotation_is(arg, base) for arg in members)
    return isinstance(annotation, type) and issubclass(annotation, base)


def _admits_none(annotation: Any) -> bool:
    """``annotation`` is None, or a union with None among its members (``X | None``)."""
    union = isinstance(annotation, UnionType) or get_origin(annotation) is Union
    return annotation is type(None) or union and type(None) in get_args(annotation)


def _stage(function: Callable[..., Any], kind: Literal["analysis", "plot"]) -> None:
    """Check ``function`` as a stage of ``kind``, or raise TypeError: an analysis takes one
    measurement or result (or a sequence) and earlier results by keyword (one it does without where
    that was not measured optional, ``X | None = None``) and returns an ``Analysis``; a plot takes
    results and returns a ``Plot``."""
    hints = get_type_hints(function)
    result = hints.pop("return", None)
    parameters = list(signature(function).parameters.values())
    where = f"{function.__module__}.{getattr(function, '__qualname__', function)}"
    if kind == "analysis":
        if not (isinstance(result, type) and issubclass(result, Analysis)):
            raise TypeError(f"{where}: an analysis returns an Analysis, not {result}")
        positional = [p for p in parameters if p.kind is p.POSITIONAL_OR_KEYWORD]
        if len(positional) != 1 or not (
            annotation_is(hints.get(positional[0].name), Meas) or annotation_is(hints.get(positional[0].name), Analysis)
        ):
            raise TypeError(f"{where}: an analysis takes one measurement or result (or a sequence) positionally")
        priors = parameters[1:]
    else:
        if result is not Plot:
            raise TypeError(f"{where}: a plot returns a Plot, not {result}")
        priors = parameters
    for parameter in priors:
        keyword = parameter.kind is parameter.KEYWORD_ONLY or kind == "plot"
        hint = hints.get(parameter.name)
        # an analysis's optional prior: a result or None, None unless given (X | None = None)
        optional = kind == "analysis" and parameter.default is None
        if kind == "analysis" and optional != _admits_none(hint):
            raise TypeError(f"{where}: {parameter.name} is an optional prior only as X | None = None")
        if not keyword or not annotation_is(hint, Analysis, optional=optional):
            raise TypeError(
                f"{where}: {parameter.name} is not an Analysis result{' by keyword' * (kind == 'analysis')}"
            )
    STAGE_FUNCTIONS[function] = kind


def analysis[F: Callable[..., Analysis]](function: F) -> F:
    """An analysis of a block's ``analysis.py``: measurement (or results) in, one ``Analysis`` out;
    a prior result it does without where that was not measured is optional, ``X | None = None``."""
    _stage(function, "analysis")
    return function


def plot[F: Callable[..., Plot]](function: F) -> F:
    """A figure of a block's ``plots.py``: ``Analysis`` results in, one ``Plot`` spec out."""
    _stage(function, "plot")
    return function
