"""Operating-point checks of a bench's transistors, for any block: whether its current sources and
amplifying devices sit in saturation (``saturation``), and whether any device has a junction
forward-biased or a pair of terminals past the run's supply (``stress``).

A bench saves each transistor's V_GS, V_DS, V_BS, V_TH, V_D,sat and Spectre's region (``saves``:
Spectre's values of the device, which ``flow.pipeline.read`` keeps as ``v["<device>:vds"]``; a
run that saves them writes PSF ASCII, ``flow.circuit.spectre.raw_format``); an analysis turns its
runs' operating points (an ``OP`` or a ``DC`` ``Sweep``: ``Meas.sweeps["opdc"]``, the run's DC
solution, at each supply corner) into each device's margin V_DS - V_D,sat, and names those meant
to be saturated that are not (``Saturation.unsaturated``); and its operating points and transients
(a ``Meas``'s own signals) into each device's junction bias and terminal voltages, naming the
devices past either limit (``Stress.forward``, ``Stress.overstressed``)::

    devices = oppoint.mos_devices(bench)  # before h.pdk.compile(bench)
    h.pdk.compile(bench)
    includes = spectre.includes(install)
    attrs = [*includes, ..., hs.Save([*SAVES, *oppoint.saves(devices, bench, includes, prefix="xtop.")]), ...]
    found = oppoint.saturation([m.sweeps["opdc"] for m in measurements], {"dut.Mtail": MosType.NMOS})
    stress = oppoint.stress([*measurements, *(m.sweeps["opdc"] for m in measurements)], devices, nominal_v=vdd)

``saturation`` takes the devices meant to be saturated (a block's current sources, cascodes and
amplifying devices, not its switches, which are meant to be in triode); ``stress`` takes every
device. ``mos_devices`` lists every transistor of a module by its path below the module.

The kits differ in two ways the checks absorb. Some wrap each transistor in a subckt of their own
(a subckt in the kit's device file around one transistor instance), so Spectre has the values
at the device inside (``Mn.<instance>``): ``saves`` names that one, and the checks read a device's values
there. And a model writes a PMOS's V_GS, V_DS and V_BS either as they are (BSIM, PSP 102: negative
for a PMOS that is on) or as an NMOS's (IHP's PSP 103): its V_TH's sign says which (``_written``).
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from enum import Enum, auto
from pathlib import Path
from typing import Any

import numpy as np
from hdl21 import sim as hs
from hdl21.primitives import MosType

from flow.pipeline import Meas, Sweep, SweepKind

# not in the reference texts: the largest supply corner the flow simulates, 110 % of a kit's nominal
# supply (the blocks' supply sweeps of 90, 100 and 110 %), which no terminal pair may exceed
SUPPLY_CORNER_MAX = 1.1
# [Razavi-Analog] Sec. 15.4.2, p. 641: a junction forward-biased by 300 mV conducts negligibly
FORWARD_BIAS_V = 0.3
# what ``saves`` saves of every device: its V_D,sat by both of the names models give it (BSIM's
# ``vdsat``, PSP 102's ``vdss``; Spectre warns of the one a model lacks), its
# threshold for the sign its model writes a PMOS's voltages with, and Spectre's region
VALUES = ("vgs", "vds", "vbs", "vth", "vdsat", "vdss", "region")


class Region(Enum):
    """A transistor's operating region as Spectre estimates it (its op value ``region``), in the
    order of the number Spectre writes for it (0 to 4)."""

    # [Razavi-Analog] Example 2.2, Fig. 2.18, p. 18: the off, saturation and triode regions
    OFF = auto()
    TRIODE = auto()
    SATURATION = auto()
    # not in the reference texts: Spectre's own further regions of a BSIM device, below threshold
    # and in breakdown (``spectre -help bsim4``, its op value ``region``)
    SUBTHRESHOLD = auto()
    BREAKDOWN = auto()


class Junction(Enum):
    """A transistor's junction to its bulk (an NMOS's substrate or p-well, a PMOS's n-well)."""

    SOURCE = auto()
    DRAIN = auto()


class Terminals(Enum):
    """A pair of a transistor's terminals whose voltage ``stress`` bounds."""

    GS = auto()
    GD = auto()
    DS = auto()
    GB = auto()


def spectre_region(number: float, device: str) -> Region:
    """The region Spectre writes as ``number`` (0 to 4) for ``device``; raises naming the device
    where the number is none of them."""
    regions = list(Region)
    if not np.isfinite(number) or round(number) != number or not 0 <= number < len(regions):
        names = ", ".join(region.name for region in regions)
        raise ValueError(f"{device}'s region is {number}, none of Spectre's 0 to 4 ({names})")
    return regions[int(number)]


# a subckt of a device file and its end, in Spectre's syntax and in SPICE's (an inline one is
# Spectre's name for its device itself: no wrapper); the language a file switches to
_SUBCKT = re.compile(r"^\s*(inline\s+)?subckt\s+(\S+)")
_SPICE_SUBCKT = re.compile(r"^\s*\.subckt\s+(\S+)", re.IGNORECASE)
_ENDS = re.compile(r"^\s*\.?ends\b", re.IGNORECASE)
_LANG = re.compile(r"^\s*simulator\s+lang\s*=\s*(\w+)")
# a line of a subckt's body that is no instance: a comment, a continuation, its parameters
_NO_INSTANCE = re.compile(r"(//|\*|\+|parameters\b|\.param\b)", re.IGNORECASE)


def wrappers(includes: Iterable[Any]) -> dict[str, str]:
    """The subckts of a run's device files (its ``hs.Include``s; a model library, ``hs.Lib``, wraps
    its devices inline) that hold one instance alone, each by its name with that instance's
    (a wrapper subckt: its one transistor's name); a SPICE subckt by its name in lower case, as SPICE matches it."""
    found: dict[str, str] = {}
    for include in includes:
        if not isinstance(include, hs.Include) or not Path(include.path).is_file():
            continue
        spice, name, body = False, None, []
        for line in Path(include.path).read_text(errors="replace").splitlines():
            if lang := _LANG.match(line):
                spice = lang.group(1).lower() == "spice"
            elif name is None:
                spectre, other = _SUBCKT.match(line), _SPICE_SUBCKT.match(line)
                if spectre and not spice and not spectre.group(1):
                    name, body = spectre.group(2), []
                elif other and spice:
                    name, body = other.group(1).lower(), []
            elif _ENDS.match(line):
                if len(body) == 1:
                    found[name] = body[0]
                name = None
            elif (words := line.split()) and not _NO_INSTANCE.match(words[0]):
                body.append(words[0])
    return found


def _spectre_path(bench: Any, path: str, inner: Mapping[str, str]) -> str:
    """``path`` (a device's, below the compiled ``bench``) as Spectre has its values: the device
    inside where the kit wraps it (``inner``: ``wrappers``)."""
    module, parts = bench, path.split(".")
    for depth, part in enumerate(parts):
        instances = getattr(module, "instances", {})
        if part not in instances:
            raise ValueError(f"{'.'.join(parts[: depth + 1])} is no instance of {getattr(bench, 'name', bench)}")
        module = instances[part].of
    master = getattr(module, "module", module)
    name = getattr(master, "name", None)
    if getattr(module, "prim", None) is not None or not isinstance(name, str):
        raise ValueError(f"{path} is no kit device yet: compile the bench (h.pdk.compile) before naming its saves")
    wrapped = inner.get(name) or inner.get(name.lower())
    return f"{path}.{wrapped}" if wrapped else path


def saves(devices: Iterable[str], bench: Any, includes: Iterable[Any], *, prefix: str = "xtop.dut.") -> list[str]:
    """What a run saves of each of ``devices`` (paths below ``prefix``: ``xtop.`` the compiled
    testbench ``bench``, ``dut.`` its DUT's instance) at each operating point or time point: its
    ``VALUES``, of the device Spectre has them at (inside the kit's wrapper, where the run's
    ``includes`` wrap it: ``wrappers``)."""
    inner = wrappers(includes)
    within = prefix.removeprefix("xtop.")
    found = []
    for device in devices:
        path = _spectre_path(bench, f"{within}{device}", inner).removeprefix(within)
        found += [f"{prefix}{path}:{value}" for value in VALUES]
    return found


def mos_devices(module: Any, path: str = "") -> dict[str, MosType]:
    """Every transistor of the hdl21 ``module`` (before ``h.pdk.compile``), by its path below the
    module (``Mtail``, ``xlatch.Mn1``), with its type."""
    found: dict[str, MosType] = {}
    for name, instance in module.instances.items():
        target = instance.of
        params = getattr(target, "params", None)
        if hasattr(params, "tp") and params.tp in (MosType.NMOS, MosType.PMOS):
            found[f"{path}{name}"] = params.tp
        elif hasattr(target, "instances"):
            found |= mos_devices(target, f"{path}{name}.")
    return found


def _lookup(v: Mapping[str, Any], device: str, name: str) -> str | None:
    """The key of ``device``'s value ``name`` in a point's signals: the device's own, or that of
    the one device inside it (a kit's wrapper: ``saves``)."""
    if f"{device}:{name}" in v:
        return f"{device}:{name}"
    inside = [key for key in v if key.endswith(f":{name}") and key.rsplit(":", 1)[0].rpartition(".")[0] == device]
    return inside[0] if len(inside) == 1 else None


def _values(
    points: Sweep | Meas | Sequence[Sweep | Meas],
    devices: Iterable[str],
    names: Sequence[str],
    kinds: Sequence[SweepKind],
    what: str,
    *,
    transient: bool,
) -> tuple[list[Sweep | Meas], dict[str, dict[str, np.ndarray]]]:
    """The points as a list (each a ``Sweep`` of ``kinds``, or where ``transient`` a measurement,
    its transient's signals), and each device's ``names`` over all their points in order (a name
    ``a|b``: the first of ``a`` and ``b`` that every point has, kept as ``a``); raises where none
    is given, one is of another kind, or one lacks a device's value, naming them."""
    points = [points] if isinstance(points, (Sweep, Meas)) else list(points)
    if not points:
        raise ValueError(f"{what} need at least one operating point")
    allowed = [kind.name for kind in kinds] + (["a measurement's transient"] if transient else [])
    wrong = [
        point.kind.name if isinstance(point, Sweep) else type(point).__name__
        for point in points
        if not (isinstance(point, Sweep) and point.kind in kinds) and not (transient and isinstance(point, Meas))
    ]
    if wrong:
        raise ValueError(f"{what} come from {' or '.join(allowed)}, not {', '.join(wrong)}")
    found: dict[str, dict[str, np.ndarray]] = {}
    missing = []
    for device in devices:
        found[device] = {}
        for name in names:
            options = name.split("|")
            for option in options:
                keys = [_lookup(point.v, device, option) for point in points]
                if all(keys):
                    found[device][options[0]] = np.concatenate(
                        [np.ravel(point.v[key]) for point, key in zip(points, keys, strict=True)]
                    )
                    break
            else:
                missing.append(f"{device}:{' or '.join(options)}")
    if missing:
        raise ValueError(
            f"the operating points lack {', '.join(missing)}: the run saves them with "
            "flow.circuit.oppoint.saves(devices, bench, includes) after h.pdk.compile(bench); where it "
            "did, Spectre skipped them and its log says why (SPECTRE-8282: an instance it does not "
            "have, a kit's wrapper subckt that saves did not resolve)"
        )
    return points, found


def _written(kind: MosType, vth: np.ndarray) -> float:
    """The sign that turns a device's written V_GS, V_DS and V_BS into its own: +1 for an NMOS and
    for a PMOS whose model writes them as they are (its V_TH negative: BSIM, PSP 102), -1 for a
    PMOS whose model writes them as an NMOS's (its V_TH positive: IHP's PSP 103)."""
    # [Razavi-Analog] Sec. 2.2, p. 18: V_GS, V_DS and V_TH are negative for a PMOS that is on
    return -1.0 if kind is MosType.PMOS and float(np.median(vth)) > 0.0 else 1.0


def _polarity(kind: MosType) -> float:
    """+1 for an NMOS, -1 for a PMOS: the sign that turns a PMOS's terminal voltages into an NMOS's."""
    # [Razavi-Analog] Sec. 2.2, p. 18: V_GS, V_DS and V_TH are negative for a PMOS that is on
    return 1.0 if kind is MosType.NMOS else -1.0


@dataclass(frozen=True, slots=True, kw_only=True)
class Saturation:
    """Each device's saturation margin at each operating point: ``margin_v[device]`` one value a
    point, in the order of the sweeps given (``saturation``); ``region[device]`` Spectre's region
    at each, where the runs saved it (else empty)."""

    margin_v: dict[str, np.ndarray]
    region: dict[str, tuple[Region, ...]] = field(default_factory=dict)

    @property
    def least_v(self) -> dict[str, float]:
        """Each device's least margin over the points."""
        return {device: float(np.min(margin)) for device, margin in self.margin_v.items()}

    @property
    def unsaturated(self) -> dict[str, float]:
        """The devices out of saturation at some point, with their least margin: a margin below
        zero, or a region Spectre calls off, triode or breakdown (below threshold a device whose
        V_DS clears its V_D,sat still acts as a current source)."""
        lost = (Region.OFF, Region.TRIODE, Region.BREAKDOWN)
        return {
            device: least
            for device, least in self.least_v.items()
            if least < 0.0 or any(region in lost for region in self.region.get(device, ()))
        }


def saturation(sweeps: Sweep | Sequence[Sweep], devices: Mapping[str, MosType]) -> Saturation:
    """Each of ``devices``' saturation margin V_DS - V_D,sat at every point of ``sweeps`` (each an
    operating point or a DC sweep whose run saved the devices' values: ``saves``), oriented so that
    a saturated device's is positive whatever its type: an NMOS's V_DS less |V_D,sat|, a PMOS's
    -V_DS less |V_D,sat| (V_DS as its model writes it, turned into its own: ``_written``; models
    write a PMOS's V_D,sat with either sign). Raises where a sweep lacks a device's values, naming
    them."""
    # [Razavi-Analog] Sec. 2.2, p. 17: V_D,sat, the least V_DS at which a device stays saturated
    kinds = (SweepKind.OP, SweepKind.DC)
    names = ("vds", "vth", "vdsat|vdss")
    sweeps, values = _values(sweeps, devices, names, kinds, "saturation margins", transient=False)
    margin_v, region = {}, {}
    for device, kind in devices.items():
        vds = _written(kind, values[device]["vth"]) * values[device]["vds"]
        margin_v[device] = _polarity(kind) * vds - np.abs(values[device]["vdsat"])
        keys = [_lookup(sweep.v, device, "region") for sweep in sweeps]
        if all(keys):
            numbers = np.concatenate([np.ravel(sweep.v[key]) for sweep, key in zip(sweeps, keys, strict=True)])
            region[device] = tuple(spectre_region(float(number), device) for number in numbers)
    return Saturation(margin_v=margin_v, region=region)


@dataclass(frozen=True, slots=True, kw_only=True)
class Stress:
    """Each device's junction bias and terminal voltages at each point (``stress``), in the order of
    the sweeps given: ``junction_v[device][Junction]`` the junction's forward bias (positive:
    forward, whatever the type), ``terminal_v[device][Terminals]`` the pair's |voltage|; and the
    run's limits, ``forward_limit_v`` (``FORWARD_BIAS_V``) and ``terminal_limit_v`` (its nominal
    supply times ``SUPPLY_CORNER_MAX``)."""

    junction_v: dict[str, dict[Junction, np.ndarray]]
    terminal_v: dict[str, dict[Terminals, np.ndarray]]
    forward_limit_v: float
    terminal_limit_v: float

    @property
    def forward(self) -> dict[str, tuple[Junction, float]]:
        """The devices with a junction forward-biased past ``forward_limit_v`` at some point: the
        junction biased most and its largest forward bias."""
        return _past(self.junction_v, self.forward_limit_v)

    @property
    def overstressed(self) -> dict[str, tuple[Terminals, float]]:
        """The devices with a pair of terminals past ``terminal_limit_v`` at some point: the pair
        stressed most and its largest |voltage|."""
        return _past(self.terminal_v, self.terminal_limit_v)


def _past(found: Mapping[str, Mapping[Any, np.ndarray]], limit: float) -> dict[str, tuple[Any, float]]:
    """Each device whose largest value over its members and points exceeds ``limit``: that member
    and value."""
    worst = {
        device: max(((member, float(np.max(value))) for member, value in members.items()), key=lambda pair: pair[1])
        for device, members in found.items()
    }
    return {device: (member, value) for device, (member, value) in worst.items() if value > limit}


def stress(
    points: Sweep | Meas | Sequence[Sweep | Meas], devices: Mapping[str, MosType], *, nominal_v: float
) -> Stress:
    """Every one of ``devices``' junction bias and terminal voltages at every point of ``points``
    (operating points and DC sweeps, ``Sweep``; measurements, each its transient's every time
    point: ``Meas.v``), whose runs saved the devices' values (``saves``), V_GS, V_DS and V_BS as
    its model writes them turned into its own (``_written``):
    the forward bias of its source and drain junctions to its bulk, V_BS and V_BD for an NMOS,
    -V_BS and -V_BD for a PMOS (V_BD = V_BS - V_DS); and |V_GS|, |V_GD|, |V_DS| and |V_GB|
    (V_GD = V_GS - V_DS, V_GB = V_GS - V_BS), bounded by the run's own largest supply,
    ``nominal_v`` (the run's nominal supply, its largest where it has several) times
    ``SUPPLY_CORNER_MAX``. Raises where a sweep lacks a device's values, naming them."""
    # [Razavi-Analog] Sec. 2.1, p. 9: a device's source and drain junctions to its bulk (an NMOS's
    # substrate, a PMOS's n-well) must stay reverse-biased
    kinds = (SweepKind.OP, SweepKind.DC)
    names = ("vgs", "vds", "vbs", "vth")
    _, values = _values(points, devices, names, kinds, "junction and terminal checks", transient=True)
    junction_v, terminal_v = {}, {}
    for device, kind in devices.items():
        sign = _written(kind, values[device]["vth"])
        vgs, vds, vbs = (sign * values[device][name] for name in ("vgs", "vds", "vbs"))
        polarity = _polarity(kind)
        junction_v[device] = {Junction.SOURCE: polarity * vbs, Junction.DRAIN: polarity * (vbs - vds)}
        terminal_v[device] = {
            Terminals.GS: np.abs(vgs),
            Terminals.GD: np.abs(vgs - vds),
            Terminals.DS: np.abs(vds),
            Terminals.GB: np.abs(vgs - vbs),
        }
    return Stress(
        junction_v=junction_v,
        terminal_v=terminal_v,
        forward_limit_v=FORWARD_BIAS_V,
        terminal_limit_v=nominal_v * SUPPLY_CORNER_MAX,
    )
