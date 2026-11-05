"""Every constraint ALIGN takes (its ``align/schema/constraint.py``, ``ConstraintType``), stated on
hdl21 objects: an instance is an ``h.Instance`` (or a ``Half`` of one, or a ``Group``), a net an
``h.Signal`` of the module, a pin an instance's port as hdl21 refers to it (``m.MP.d``, an
``h.PortRef``), never a name; a
choice among ALIGN's literals an Enum. Each constraint's ``align(names)`` is ALIGN's JSON for it,
the names resolved in the module the constraint is placed on (``hdl21align.place``).

Placement: ``Order``, ``Align``, ``AlignInOrder``, ``Spread``, ``Floorplan`` (usually stated as
``rows``), ``SymmetricBlocks``, ``GroupBlocks`` (a ``Group``: a virtual hierarchy other
constraints name), ``SameTemplate``, ``PlaceCloser``, ``PlaceOnBoundary``, ``PlaceOnGrid``,
``CompactPlacement``, ``BlockDistance``, ``HorizontalDistance``, ``VerticalDistance``,
``AssignBboxVariables``, ``AspectRatio``, ``Boundary``, ``Stackup`` (frida's ALIGN: instances in
disjoint slices of the metal stack-up may overlap).

Devices and the compiler: ``Generator``, ``GroupCaps``, ``GuardRing``, ``DoNotIdentify``,
``DoNotUseLib``, ``ConfigureCompiler``.

Nets and routing: ``PowerPorts``, ``GroundPorts``, ``ClockPorts``, ``DoNotRoute``, ``Route``
(with ``CustomizeRoute``), ``NetConst``, ``NetPriority``, ``MultiConnection``, ``SymmetricNets``,
``PortLocation``, ``ChargeFlow``.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto
from typing import Any, Protocol

import hdl21 as h

# the constraints ALIGN takes within a group (its GroupBlocks' ``constraints``)
IN_GROUP = (
    "Align",
    "Order",
    "Boundary",
    "AlignInOrder",
    "Floorplan",
    "SymmetricBlocks",
    "DoNotIdentify",
    "SameTemplate",
    "ConfigureCompiler",
    "Stackup",  # ALIGN's fork: a group stacked over its own rows, its edges, its routing layers
    "PlaceOnBoundary",
    "Route",
)


class Names(Protocol):
    """How a constraint's objects become ALIGN's names, in the module it is placed on."""

    def instance(self, item: Any) -> str: ...

    def net(self, signal: h.Signal) -> str: ...

    def pin(self, pin: h.PortRef | h.Signal) -> str: ...


class Axis(Enum):
    """A direction: horizontal (ALIGN's ``horizontal``, ``H``) or vertical (``vertical``, ``V``)."""

    HORIZONTAL = auto()
    VERTICAL = auto()

    @property
    def word(self) -> str:
        return self.name.lower()

    @property
    def letter(self) -> str:
        return self.name[0]


class OrderDirection(Enum):
    """``Order``'s direction: along an axis, or one way along it."""

    HORIZONTAL = auto()
    VERTICAL = auto()
    LEFT_TO_RIGHT = auto()
    RIGHT_TO_LEFT = auto()
    BOTTOM_TO_TOP = auto()
    TOP_TO_BOTTOM = auto()


class Line(Enum):
    """``Align``'s line: horizontal (any, top, bottom, centre) or vertical (any, left, right, centre)."""

    H_ANY = auto()
    H_TOP = auto()
    H_BOTTOM = auto()
    H_CENTER = auto()
    V_ANY = auto()
    V_LEFT = auto()
    V_RIGHT = auto()
    V_CENTER = auto()


class Edge(Enum):
    """``AlignInOrder``'s line."""

    TOP = auto()
    BOTTOM = auto()
    LEFT = auto()
    RIGHT = auto()
    CENTER = auto()


class Compaction(Enum):
    """``CompactPlacement``'s style."""

    LEFT = auto()
    RIGHT = auto()
    CENTER = auto()


class Location(Enum):
    """``PortLocation``'s place: the side (top, right, bottom, left) and the spot along it."""

    TL = auto()
    TC = auto()
    TR = auto()
    RT = auto()
    RC = auto()
    RB = auto()
    BL = auto()
    BC = auto()
    BR = auto()
    LB = auto()
    LC = auto()
    LT = auto()


class Metric(Enum):
    """``ChargeFlow``'s distance."""

    EUCLIDEAN = auto()
    MANHATTAN = auto()


def _all(names: Names, items) -> list[str]:
    return [names.instance(item) for item in items]


def _nets(names: Names, signals) -> list[str]:
    return [names.net(signal) for signal in signals]


class Constraint:
    """One of ALIGN's constraints; ``align`` is its JSON."""

    def align(self, names: Names) -> dict[str, Any]:
        raise NotImplementedError


# ---- placement ----------------------------------------------------------------------------------


@dataclass(frozen=True)
class Order(Constraint):
    """Place ``instances`` in order along ``direction`` (any order along an axis where it is one),
    touching where ``abut``."""

    instances: tuple[Any, ...]
    direction: OrderDirection | None = None
    abut: bool = False

    def align(self, names: Names) -> dict[str, Any]:
        out: dict[str, Any] = {"constraint": "Order", "instances": _all(names, self.instances), "abut": self.abut}
        if self.direction is not None:
            out["direction"] = self.direction.name.lower()
        return out


@dataclass(frozen=True)
class Align(Constraint):
    """Align ``instances`` on ``line``."""

    instances: tuple[Any, ...]
    line: Line | None = None

    def align(self, names: Names) -> dict[str, Any]:
        out: dict[str, Any] = {"constraint": "Align", "instances": _all(names, self.instances)}
        if self.line is not None:
            out["line"] = self.line.name.lower()
        return out


@dataclass(frozen=True)
class AlignInOrder(Constraint):
    """Align ``instances`` on ``line`` and place them in order along ``direction``."""

    instances: tuple[Any, ...]
    line: Edge = Edge.BOTTOM
    direction: Axis | None = None
    abut: bool = False

    def align(self, names: Names) -> dict[str, Any]:
        out: dict[str, Any] = {
            "constraint": "AlignInOrder",
            "instances": _all(names, self.instances),
            "line": self.line.name.lower(),
            "abut": self.abut,
        }
        if self.direction is not None:
            out["direction"] = self.direction.word
        return out


@dataclass(frozen=True)
class Spread(Constraint):
    """Place ``instances`` ``distance_nm`` apart along ``direction``."""

    instances: tuple[Any, ...]
    direction: Axis
    distance_nm: int

    def align(self, names: Names) -> dict[str, Any]:
        return {
            "constraint": "Spread",
            "instances": _all(names, self.instances),
            "direction": self.direction.word,
            "distance": self.distance_nm,
        }


@dataclass(frozen=True)
class Floorplan(Constraint):
    """Regions of instances, top first (``order``: left to right within each; ``symmetrize``:
    each mirrored about the centre). ``hdl21align.rows`` states the same, the usual way."""

    regions: tuple[tuple[Any, ...], ...]
    order: bool = False
    symmetrize: bool = False

    def align(self, names: Names) -> dict[str, Any]:
        return {
            "constraint": "Floorplan",
            "regions": [_all(names, region) for region in self.regions],
            "order": self.order,
            "symmetrize": self.symmetrize,
        }


@dataclass(frozen=True)
class SymmetricBlocks(Constraint):
    """Mirror each pair about one axis (``direction``: the axis's orientation); a single instance
    is centred on it."""

    pairs: tuple[tuple[Any, ...], ...]
    direction: Axis

    def align(self, names: Names) -> dict[str, Any]:
        return {
            "constraint": "SymmetricBlocks",
            "pairs": [_all(names, pair) for pair in self.pairs],
            "direction": self.direction.letter,
        }


@dataclass(frozen=True)
class Group(Constraint):
    """ALIGN's ``GroupBlocks``: ``instances`` as one virtual sub-cell ``name`` (it begins with X),
    which other constraints may name as an instance; ``template`` its cell's name, ``generator``
    what draws it, ``constraints`` its own (alignment, order, boundary and the like)."""

    name: str
    instances: tuple[Any, ...]
    template: str | None = None
    generator: Generator | None = None
    constraints: tuple[Constraint, ...] = ()

    def __post_init__(self) -> None:
        if not self.name.upper().startswith("X"):
            raise ValueError(f"a group's name begins with X: {self.name}")
        refused = [type(c).__name__ for c in self.constraints if type(c).__name__ not in IN_GROUP]
        if refused:
            raise ValueError(f"ALIGN takes no {', '.join(refused)} within a group")

    def align(self, names: Names) -> dict[str, Any]:
        out: dict[str, Any] = {
            "constraint": "GroupBlocks",
            "instance_name": self.name,
            "instances": _all(names, self.instances),
        }
        if self.template is not None:
            out["template_name"] = self.template
        if self.generator is not None:
            out["generator"] = {k: v for k, v in self.generator.align(names).items() if k != "constraint"}
        if self.constraints:
            out["constraints"] = [c.align(names) for c in self.constraints]
        return out


@dataclass(frozen=True)
class Stackup(Constraint):
    """The slice of the metal stack-up ``instances`` occupy: from metal ``min_layer`` (None: from the
    devices) up to metal ``max_layer``. Instances whose slices do not intersect may be placed over
    one another, a capacitor in the upper metals over transistors routed below it; an instance in
    no slice occupies the whole stack-up and overlaps nothing."""

    instances: tuple[Any, ...]
    max_layer: int
    min_layer: int | None = None

    def __post_init__(self) -> None:
        if self.min_layer is not None and self.min_layer > self.max_layer:
            raise ValueError(f"a slice from M{self.min_layer} up to M{self.max_layer}")

    def align(self, names: Names) -> dict[str, Any]:
        out: dict[str, Any] = {
            "constraint": "Stackup",
            "instances": _all(names, self.instances),
            "max_layer": f"M{self.max_layer}",
        }
        if self.min_layer is not None:
            out["min_layer"] = f"M{self.min_layer}"
        return out


@dataclass(frozen=True)
class SameTemplate(Constraint):
    """Lay out ``instances`` (of one cell) identically."""

    instances: tuple[Any, ...]

    def align(self, names: Names) -> dict[str, Any]:
        return {"constraint": "SameTemplate", "instances": _all(names, self.instances)}


@dataclass(frozen=True)
class PlaceCloser(Constraint):
    """Place ``instances`` close together."""

    instances: tuple[Any, ...]

    def align(self, names: Names) -> dict[str, Any]:
        return {"constraint": "PlaceCloser", "instances": _all(names, self.instances)}


@dataclass(frozen=True)
class PlaceOnBoundary(Constraint):
    """Place instances on the block's sides and corners."""

    north: tuple[Any, ...] = ()
    south: tuple[Any, ...] = ()
    east: tuple[Any, ...] = ()
    west: tuple[Any, ...] = ()
    northeast: Any = None
    northwest: Any = None
    southeast: Any = None
    southwest: Any = None

    def align(self, names: Names) -> dict[str, Any]:
        out: dict[str, Any] = {"constraint": "PlaceOnBoundary"}
        for side in ("north", "south", "east", "west"):
            if getattr(self, side):
                out[side] = _all(names, getattr(self, side))
        for corner in ("northeast", "northwest", "southeast", "southwest"):
            if getattr(self, corner) is not None:
                out[corner] = names.instance(getattr(self, corner))
        return out


@dataclass(frozen=True)
class PlaceOnGrid(Constraint):
    """Place the block on a grid of ``pitch`` along ``direction``: at each ``(offsets, scalings)``
    term's offsets, mirrored where its scaling is -1."""

    direction: Axis
    pitch: int
    terms: tuple[tuple[tuple[int, ...], tuple[int, ...]], ...] = (((0,), (1,)),)

    def align(self, names: Names) -> dict[str, Any]:
        return {
            "constraint": "PlaceOnGrid",
            "direction": self.direction.letter,
            "pitch": self.pitch,
            "ored_terms": [{"offsets": list(offsets), "scalings": list(scalings)} for offsets, scalings in self.terms],
        }


@dataclass(frozen=True)
class CompactPlacement(Constraint):
    """Compact the placement toward ``style``."""

    style: Compaction = Compaction.LEFT

    def align(self, names: Names) -> dict[str, Any]:
        return {"constraint": "CompactPlacement", "style": self.style.name.lower()}


@dataclass(frozen=True)
class BlockDistance(Constraint):
    """Every block at least ``distance`` (ALIGN's grid units) from the next."""

    distance: int

    def align(self, names: Names) -> dict[str, Any]:
        return {"constraint": "BlockDistance", "abs_distance": self.distance}


@dataclass(frozen=True)
class HorizontalDistance(Constraint):
    """Blocks at least ``distance`` apart horizontally."""

    distance: int

    def align(self, names: Names) -> dict[str, Any]:
        return {"constraint": "HorizontalDistance", "abs_distance": self.distance}


@dataclass(frozen=True)
class VerticalDistance(Constraint):
    """Blocks at least ``distance`` apart vertically."""

    distance: int

    def align(self, names: Names) -> dict[str, Any]:
        return {"constraint": "VerticalDistance", "abs_distance": self.distance}


@dataclass(frozen=True)
class AssignBboxVariables(Constraint):
    """Fix ``item``'s bounding box (ALIGN's grid units)."""

    item: Any
    llx: int
    lly: int
    urx: int
    ury: int

    def align(self, names: Names) -> dict[str, Any]:
        return {
            "constraint": "AssignBboxVariables",
            "bbox_name": names.instance(self.item),
            "llx": self.llx,
            "lly": self.lly,
            "urx": self.urx,
            "ury": self.ury,
        }


@dataclass(frozen=True)
class AspectRatio(Constraint):
    """The block's width over its height, between ``low`` and ``high``."""

    low: float = 0.1
    high: float = 10.0
    weight: int = 1

    def align(self, names: Names) -> dict[str, Any]:
        return {"constraint": "AspectRatio", "ratio_low": self.low, "ratio_high": self.high, "weight": self.weight}


@dataclass(frozen=True)
class Boundary(Constraint):
    """The block's largest width and height (um), and its halo."""

    max_width_um: float = 100000.0
    max_height_um: float = 100000.0
    halo_horizontal_um: float = 0.0
    halo_vertical_um: float = 0.0

    def align(self, names: Names) -> dict[str, Any]:
        return {
            "constraint": "Boundary",
            "max_width": self.max_width_um,
            "max_height": self.max_height_um,
            "halo_horizontal": self.halo_horizontal_um,
            "halo_vertical": self.halo_vertical_um,
        }


# ---- devices and the compiler ---------------------------------------------------------------------


@dataclass(frozen=True)
class Generator(Constraint):
    """The PDK generator that draws the cell (``name``), and its ``parameters``."""

    name: str | None = None
    parameters: dict[str, Any] | None = None

    def align(self, names: Names) -> dict[str, Any]:
        out: dict[str, Any] = {"constraint": "Generator"}
        if self.name is not None:
            out["name"] = self.name
        if self.parameters is not None:
            out["parameters"] = dict(self.parameters)
        return out


@dataclass(frozen=True)
class GroupCaps(Constraint):
    """``instances`` (capacitors) as one common-centroid array ``name`` of ``unit_ff`` units,
    ``units`` of them each, with dummies where ``dummy``."""

    name: str
    instances: tuple[Any, ...]
    unit_ff: float
    units: tuple[int, ...]
    dummy: bool = False

    def align(self, names: Names) -> dict[str, Any]:
        return {
            "constraint": "GroupCaps",
            "name": self.name,
            "instances": _all(names, self.instances),
            "unit_cap": f"{self.unit_ff:g}",
            "num_units": list(self.units),
            "dummy": self.dummy,
        }


@dataclass(frozen=True)
class GuardRing(Constraint):
    """A guard ring of the PDK primitive ``primitive`` around ``block``, on ``pin``."""

    primitive: str
    pin: h.Signal
    block: str

    def align(self, names: Names) -> dict[str, Any]:
        return {
            "constraint": "GuardRing",
            "guard_ring_primitives": self.primitive,
            "global_pin": names.net(self.pin),
            "block_name": self.block,
        }


@dataclass(frozen=True)
class DoNotIdentify(Constraint):
    """Keep ``instances`` out of ALIGN's primitive recognition."""

    instances: tuple[Any, ...]

    def align(self, names: Names) -> dict[str, Any]:
        return {"constraint": "DoNotIdentify", "instances": _all(names, self.instances)}


@dataclass(frozen=True)
class DoNotUseLib(Constraint):
    """Keep ALIGN's library ``libraries`` (its primitives' names) from being used."""

    libraries: tuple[str, ...]
    propagate: bool = False

    def align(self, names: Names) -> dict[str, Any]:
        return {"constraint": "DoNotUseLib", "libraries": list(self.libraries), "propagate": self.propagate}


@dataclass(frozen=True)
class ConfigureCompiler(Constraint):
    """ALIGN's compiler switches."""

    is_digital: bool = False
    auto_constraint: bool = True
    identify_array: bool = True
    fix_source_drain: bool = True
    remove_dummy_hierarchies: bool = True
    remove_dummy_devices: bool = True
    merge_series_devices: bool = True
    merge_parallel_devices: bool = True
    same_template: bool = True
    propagate: bool = True

    def align(self, names: Names) -> dict[str, Any]:
        fields_ = (
            "is_digital",
            "auto_constraint",
            "identify_array",
            "fix_source_drain",
            "remove_dummy_hierarchies",
            "remove_dummy_devices",
            "merge_series_devices",
            "merge_parallel_devices",
            "same_template",
            "propagate",
        )
        return {"constraint": "ConfigureCompiler", **{key: getattr(self, key) for key in fields_}}


# ---- nets and routing -----------------------------------------------------------------------------


@dataclass(frozen=True)
class PowerPorts(Constraint):
    """``ports`` are supplies."""

    ports: tuple[h.Signal, ...]
    propagate: bool = True

    def align(self, names: Names) -> dict[str, Any]:
        return {"constraint": "PowerPorts", "ports": _nets(names, self.ports), "propagate": self.propagate}


@dataclass(frozen=True)
class GroundPorts(Constraint):
    """``ports`` are grounds."""

    ports: tuple[h.Signal, ...]
    propagate: bool = True

    def align(self, names: Names) -> dict[str, Any]:
        return {"constraint": "GroundPorts", "ports": _nets(names, self.ports), "propagate": self.propagate}


@dataclass(frozen=True)
class ClockPorts(Constraint):
    """``ports`` are clocks."""

    ports: tuple[h.Signal, ...]
    propagate: bool = True

    def align(self, names: Names) -> dict[str, Any]:
        return {"constraint": "ClockPorts", "ports": _nets(names, self.ports), "propagate": self.propagate}


@dataclass(frozen=True)
class DoNotRoute(Constraint):
    """Leave ``nets`` unrouted (a supply the rows' rails carry, say)."""

    nets: tuple[h.Signal, ...]

    def align(self, names: Names) -> dict[str, Any]:
        return {"constraint": "DoNotRoute", "nets": _nets(names, self.nets)}


@dataclass(frozen=True)
class CustomizeRoute:
    """``Route``'s per-net layers (metal numbers), shielding and matching."""

    nets: tuple[h.Signal, ...]
    min_layer: int | None = None
    max_layer: int | None = None
    shield: bool = False
    match: bool = False

    def align(self, names: Names) -> dict[str, Any]:
        out: dict[str, Any] = {"nets": _nets(names, self.nets), "shield": self.shield, "match": self.match}
        if self.min_layer is not None:
            out["min_layer"] = f"M{self.min_layer}"
        if self.max_layer is not None:
            out["max_layer"] = f"M{self.max_layer}"
        return out


@dataclass(frozen=True)
class Route(Constraint):
    """The routing layers (metal numbers), and nets routed otherwise (``customize``)."""

    min_layer: int | None = None
    max_layer: int | None = None
    customize: tuple[CustomizeRoute, ...] = ()

    def align(self, names: Names) -> dict[str, Any]:
        out: dict[str, Any] = {"constraint": "Route", "customize": [c.align(names) for c in self.customize]}
        if self.min_layer is not None:
            out["min_layer"] = f"M{self.min_layer}"
        if self.max_layer is not None:
            out["max_layer"] = f"M{self.max_layer}"
        return out


@dataclass(frozen=True)
class NetConst(Constraint):
    """``nets`` shielded by ``shield`` and of ``criticality``."""

    nets: tuple[h.Signal, ...]
    shield: h.Signal | None = None
    criticality: int | None = None

    def align(self, names: Names) -> dict[str, Any]:
        out: dict[str, Any] = {"constraint": "NetConst", "nets": _nets(names, self.nets)}
        if self.shield is not None:
            out["shield"] = names.net(self.shield)
        if self.criticality is not None:
            out["criticality"] = self.criticality
        return out


@dataclass(frozen=True)
class NetPriority(Constraint):
    """Route ``nets`` with ``weight``."""

    nets: tuple[h.Signal, ...]
    weight: int

    def align(self, names: Names) -> dict[str, Any]:
        return {"constraint": "NetPriority", "nets": _nets(names, self.nets), "weight": self.weight}


@dataclass(frozen=True)
class MultiConnection(Constraint):
    """Route ``nets`` with ``multiplier`` parallel wires."""

    nets: tuple[h.Signal, ...]
    multiplier: int

    def align(self, names: Names) -> dict[str, Any]:
        return {"constraint": "MultiConnection", "nets": _nets(names, self.nets), "multiplier": self.multiplier}


@dataclass(frozen=True)
class SymmetricNets(Constraint):
    """Route ``net1`` and ``net2`` mirrored about an axis of ``direction``, their pins matched in
    order (``pins1``, ``pins2``)."""

    net1: h.Signal
    net2: h.Signal
    direction: Axis
    pins1: tuple[h.PortRef | h.Signal, ...] = ()
    pins2: tuple[h.PortRef | h.Signal, ...] = ()

    def align(self, names: Names) -> dict[str, Any]:
        out: dict[str, Any] = {
            "constraint": "SymmetricNets",
            "net1": names.net(self.net1),
            "net2": names.net(self.net2),
            "direction": self.direction.letter,
        }
        if self.pins1:
            out["pins1"] = [names.pin(p) for p in self.pins1]
        if self.pins2:
            out["pins2"] = [names.pin(p) for p in self.pins2]
        return out


@dataclass(frozen=True)
class PortLocation(Constraint):
    """Place ``ports`` at ``location`` on the block's edge."""

    ports: tuple[h.Signal, ...]
    location: Location

    def align(self, names: Names) -> dict[str, Any]:
        return {"constraint": "PortLocation", "ports": _nets(names, self.ports), "location": self.location.name}


@dataclass(frozen=True)
class ChargeFlow(Constraint):
    """The current through each pin at each of ``time``'s instants, for the placer."""

    time: tuple[float, ...]
    pin_current: tuple[tuple[h.PortRef | h.Signal, tuple[float, ...]], ...]
    metric: Metric = Metric.MANHATTAN

    def align(self, names: Names) -> dict[str, Any]:
        return {
            "constraint": "ChargeFlow",
            "dist_type": self.metric.name.capitalize(),
            "time": list(self.time),
            "pin_current": {names.pin(pin): list(current) for pin, current in self.pin_current},
        }


# the classes standing for ALIGN's constraint types, by ALIGN's name (a test checks it is all of them)
ALIGN_NAMES = {
    "Order": Order,
    "Align": Align,
    "AlignInOrder": AlignInOrder,
    "Spread": Spread,
    "Floorplan": Floorplan,
    "SymmetricBlocks": SymmetricBlocks,
    "GroupBlocks": Group,
    "SameTemplate": SameTemplate,
    "Stackup": Stackup,
    "PlaceCloser": PlaceCloser,
    "PlaceOnBoundary": PlaceOnBoundary,
    "PlaceOnGrid": PlaceOnGrid,
    "CompactPlacement": CompactPlacement,
    "BlockDistance": BlockDistance,
    "HorizontalDistance": HorizontalDistance,
    "VerticalDistance": VerticalDistance,
    "AssignBboxVariables": AssignBboxVariables,
    "AspectRatio": AspectRatio,
    "Boundary": Boundary,
    "Generator": Generator,
    "GroupCaps": GroupCaps,
    "GuardRing": GuardRing,
    "DoNotIdentify": DoNotIdentify,
    "DoNotUseLib": DoNotUseLib,
    "ConfigureCompiler": ConfigureCompiler,
    "PowerPorts": PowerPorts,
    "GroundPorts": GroundPorts,
    "ClockPorts": ClockPorts,
    "DoNotRoute": DoNotRoute,
    "Route": Route,
    "NetConst": NetConst,
    "NetPriority": NetPriority,
    "MultiConnection": MultiConnection,
    "SymmetricNets": SymmetricNets,
    "PortLocation": PortLocation,
    "ChargeFlow": ChargeFlow,
}
