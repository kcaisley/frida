"""hdl21align: a generator's layout intent, stated on its own instances, for ALIGN (after Dan
Fritchman's AlignHdl21, his thesis ch. 7.5).

A generator says where its instances go as it makes them (``place``): a ``Placement``, rows top
first, each row its entries left to right (an hdl21 ``Instance`` itself, never its name, so a
device a generator leaves out is in no row and a renamed one moves with its row); whether the
rows are mirrored about their centre (``symmetric``); the instances ALIGN may place where it
likes (``auto``); and any of ALIGN's further constraints (``constraints``: every type ALIGN has,
stated on the module's own instances and nets, ``hdl21align.constraints``). The ``PnrInput`` rides
on the module as an hdl21 Property, which no netlist or simulation carries, so the netlist is
unchanged; ALIGN places what is stated and derives only what is not.

A placement nests, as Fritchman's does: a row's entry may be a ``Column`` (``column``: its entries
top first), a column's a ``Row``, to any depth (``rows(row(a, column(b, c), d))``). A row within a
row is the same row, a column within a column the same column; a column of more than one entry in
a row is one virtual sub-cell (ALIGN's GroupBlocks, ``Xcolumn<k>`` or the column's own name) whose
own Floorplan stacks its entries, each a region (a row within it, its region), mirrored as the
module's rows are. An entry is an instance, a part of one (``halves``), a ``Group``, an ``h.Pair``
or one of its ``sides``.

An ``h.Pair`` (two identical instances, hdl21's differential instance bundle, which elaboration
replaces by ``<pair>_p`` and ``<pair>_n``) is captured as ``place`` is called, while it is still
one. Placed whole, it is a sub-cell of its own, ``X<pair>``: its two instances side by side,
mirrored about a vertical axis (GroupBlocks, Order, SymmetricBlocks). Placed side by side
(``sides``), in one row, its sides are mirrored about a vertical axis of their own (SymmetricBlocks),
unless the generator states it already (the rows mirrored with the sides in mirrored places, or a
SymmetricBlocks or symmetrized Floorplan of its own naming both); sides in different rows are
mirrored about none.

The netlist is hierarchical: a child module is a subcircuit of its own, laid out by its own
intent (its own ``place``), and placed in its parent's rows as one instance. A ``Group`` (ALIGN's
GroupBlocks) gathers instances of one module into a sub-cell of the layout alone, for a netlist
from elsewhere that states no layout of its own.

``issues`` is the completeness check a generator's tests run on every instance of its space,
without ALIGN: every instance placed exactly once (through any nesting) or left to ALIGN, every
placed one the module's, every instance and net a constraint names the module's, every sub-cell's
name its own. ``module_plan`` is a module's intent named as the netlist names its objects, the form
ALIGN's constraint files take (``flow.circuit.netlists.align_design``).

Unlike AlignHdl21, nothing here replaces hdl21's elaborator (Fritchman notes custom elaborators do
not compose): the intent is read from the Property after elaboration, by a walk of the hierarchy
(``pnr_inputs``), the same way a PDK's compile passes read a module.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from itertools import count
from typing import Any

import hdl21 as h
from hdl21.primitives import C, Mos

from .constraints import Axis, Constraint, DoNotIdentify, Floorplan, Group, Order, OrderDirection, SymmetricBlocks

_PNR_INPUT = "frida.pnr_input"


@dataclass(frozen=True)
class Half:
    """One of the ``parts`` equal parts ALIGN's netlist splits an instance into (``halves``):
    a device too tall for one row, in two, its netlist unchanged."""

    instance: h.Instance
    index: int
    parts: int


def halves(instance: h.Instance, parts: int = 2) -> tuple[Half, ...]:
    """``instance`` as ``parts`` equal parts, each placed on its own (``make_design`` splits the
    netlist's device so: ``<name>_a``, ``<name>_b``, ...)."""
    return tuple(Half(instance, index, parts) for index in range(parts))


@dataclass(frozen=True, eq=False)
class Side:
    """One instance of an ``h.Pair``, ``signal`` its ``p`` or ``n`` (``sides``): after elaboration,
    the instance hdl21 makes of it, ``<pair>_<signal>``."""

    pair: h.Pair
    signal: str


def sides(pair: h.Pair) -> tuple[Side, ...]:
    """An ``h.Pair``'s two instances, ``p`` then ``n``, each placed on its own."""
    if not isinstance(pair, h.Pair):
        raise TypeError(f"not an h.Pair: {pair!r}")
    return tuple(Side(pair, signal) for signal in pair.bundle.signals)


@dataclass(frozen=True)
class Row:
    """A row's entries, left to right."""

    instances: tuple[Any, ...]


@dataclass(frozen=True)
class Column:
    """A column's entries, top first; ``name`` its sub-cell's (it begins with X; None:
    ``Xcolumn<k>``)."""

    instances: tuple[Any, ...]
    name: str | None = None

    def __post_init__(self) -> None:
        if self.name is not None and not self.name.upper().startswith("X"):
            raise ValueError(f"a column's name begins with X: {self.name}")


Entry = h.Instance | Half | Side | h.Pair | Group | Row | Column


def row(*instances: Entry | None) -> Row:
    """A row of ``instances``, left to right; a ``None`` (an instance a generator leaves out) is skipped."""
    return Row(tuple(instance for instance in instances if instance is not None))


def column(*instances: Entry | None, name: str | None = None) -> Column:
    """A column of ``instances``, top first; a ``None`` is skipped."""
    return Column(tuple(instance for instance in instances if instance is not None), name)


@dataclass(frozen=True)
class Placement:
    """Rows of entries, top first."""

    rows: tuple[Row, ...]


def rows(*placed: Row | Column) -> Placement:
    """The rows top first (a column's entries, each its own row); an empty row is dropped."""
    flat: list[Row] = []
    for r in placed:
        if isinstance(r, Column):
            flat += [e if isinstance(e, Row) else Row((e,)) for e in _flat(r.instances, Column)]
        else:
            flat.append(r)
    return Placement(tuple(r for r in flat if r.instances))


@dataclass
class PnrInput:
    """A module's layout intent: its placement, its mirroring, what ALIGN places itself, ALIGN's
    further constraints on it, and its ``h.Pair``s (captured before elaboration replaces them)."""

    module: h.Module
    placement: Placement
    symmetric: bool = True
    auto: tuple[h.Instance | h.Pair, ...] = ()
    constraints: tuple[Constraint, ...] = ()
    pairs: tuple[h.Pair, ...] = ()


def place(
    module: h.Module,
    placement: Placement,
    *,
    symmetric: bool = True,
    auto: tuple[h.Instance | h.Pair, ...] = (),
    constraints: tuple[Constraint, ...] = (),
) -> PnrInput:
    """State ``module``'s layout intent; it rides on the module as a Property."""
    if module.props.get(_PNR_INPUT) is not None:
        raise ValueError(f"{module.name} already states its placement")
    pairs = tuple(b for b in module.instbundles.values() if isinstance(b, h.Pair))
    taken = [f"{p.name}_{s}" for p in pairs for s in p.bundle.signals if f"{p.name}_{s}" in module.namespace]
    if taken:
        raise ValueError(f"{module.name}: a Pair's instance would be renamed, its name taken: {', '.join(taken)}")
    pnr = PnrInput(module, placement, symmetric, tuple(auto), tuple(constraints), pairs)
    module.props.set(_PNR_INPUT, pnr)
    return pnr


def pnr_input(module: object) -> PnrInput | None:
    """A module's layout intent, or None where its generator states none."""
    props = getattr(module, "props", None)
    return props.get(_PNR_INPUT) if props is not None else None


def pnr_inputs(module: h.Module) -> list[PnrInput]:
    """Every module's layout intent in ``module``'s hierarchy, ``module``'s first, each once."""
    found: list[PnrInput] = []
    seen: set[int] = set()

    def walk(current: h.Module) -> None:
        if id(current) in seen:
            return
        seen.add(id(current))
        pnr = pnr_input(current)
        if pnr is not None:
            found.append(pnr)
        for instance in (*current.instances.values(), *current.instbundles.values()):
            if isinstance(instance.of, h.Module):
                walk(instance.of)

    walk(module)
    return found


def own_name(name: str, letter: str) -> str:
    """An instance's own name in a netlist: without the element letter its name may begin with
    (``Mdiff_p`` of a MOS: ``diff_p``), lower case; the netlister writes the letter."""
    rest = name[1:] if len(name) > 1 and name[0].lower() == letter else name
    return rest.lower()


def letter(of: Any) -> str:
    """The element letter of what an hdl21 instance is of: ``m`` a MOS (hdl21's or the PDK's),
    ``c`` an ideal capacitor, ``x`` anything else (a module, a library cell, a drawn device)."""
    if isinstance(of, h.PrimitiveCall):
        return {Mos: "m", C: "c"}.get(of.prim, "x")
    if isinstance(of, h.ExternalModuleCall):
        if is_pdk_mos(of.module):
            return "m"
        spicetype = getattr(of.module, "spicetype", None)
        return {"MOS": "m", "CAPACITOR": "c", "RESISTOR": "r"}.get(getattr(spicetype, "name", ""), "x")
    return "x"


MOS_PORTS = frozenset({"d", "g", "s", "b"})  # hdl21's Mos's, which a PDK's MOS keeps


def is_pdk_mos(module: Any) -> bool:
    """Whether an external module is a PDK's MOS (hdl21's ``Mos`` compiled, its ports ``d g s b``):
    a MOS element in the layout's and LVS's netlists, though a PDK whose models are subcircuits
    (SG13G2's) calls it as one in simulation."""
    ports = getattr(module, "port_list", None) or list(getattr(module, "ports", {}).values())
    return {getattr(port, "name", "").lower() for port in ports} == MOS_PORTS


def netlist_name(name: str, of: Any) -> str:
    """An instance's name in the netlists hdl21 and vlsir write (``flow.circuit.netlists``):
    its element letter capital, its own name lower case (``Mdiff_p``, ``Xdrive_p``)."""
    return letter(of).upper() + own_name(name, letter(of))


def device_name(name: str) -> str:
    """A device's name as the netlists write it: its element letter capital, the rest lower case
    (``Xdrive_p``, ``Mn0``); a net, a port and a parameter all lower case."""
    return name[:1].upper() + name[1:].lower()


def _unelaborated(module: h.Module, pair: h.Pair) -> bool:
    """Whether ``pair`` is still one of ``module``'s instance bundles (elaboration not yet run)."""
    return any(b is pair for b in module.instbundles.values())


def side_instance(module: h.Module, side: Side) -> h.Instance | None:
    """The instance elaboration made of a pair's side, ``<pair>_<signal>``; None before elaboration
    or where ``module`` has none."""
    if _unelaborated(module, side.pair):
        return None
    return module.instances.get(f"{side.pair.name}_{side.signal}")


class Names:
    """ALIGN's names for a module's objects as the netlist writes them (``flow.circuit.netlists``):
    an instance (``netlist_name``; a part of one, ``<name>_a``; a pair's side, the instance it
    becomes; a group, its own name; a column or a placed pair, its sub-cell's), a net or port
    (lower case), an instance's pin (``m.MP.d``: ``Mp/d``). One not the module's raises ``KeyError``."""

    def __init__(self, module: h.Module) -> None:
        self.module = module
        self._instances = {id(instance): name for name, instance in module.instances.items()}
        self._nets = {id(signal): name for name, signal in (*module.ports.items(), *module.signals.items())}
        self.subcells: dict[int, str] = {}  # a column's or a placed pair's sub-cell (``_lower``)

    def instance(self, item: Any) -> str:
        if id(item) in self.subcells:
            return self.subcells[id(item)]
        if isinstance(item, Group):
            return item.name
        if isinstance(item, Half):
            return f"{self.instance(item.instance)}_{chr(ord('a') + item.index)}"
        if isinstance(item, Side):
            made = side_instance(self.module, item)
            if made is not None:
                return self.instance(made)
            if _unelaborated(self.module, item.pair):
                return netlist_name(f"{item.pair.name}_{item.signal}", item.pair.of)
            raise KeyError(f"a pair's side not {self.module.name}'s: {item.pair.name}_{item.signal}")
        if id(item) not in self._instances:
            raise KeyError(f"an instance not {self.module.name}'s")
        return netlist_name(self._instances[id(item)], item.of)

    def net(self, signal: h.Signal) -> str:
        if id(signal) not in self._nets:
            raise KeyError(f"a net not {self.module.name}'s: {getattr(signal, 'name', signal)}")
        return self._nets[id(signal)].lower()

    def pin(self, pin: h.PortRef | h.Signal) -> str:
        if isinstance(pin, h.PortRef):
            return f"{self.instance(pin.inst)}/{pin.portname.lower()}"
        return self.net(pin)


def _flat(entries: tuple[Any, ...], kind: type) -> list[Any]:
    """``entries`` with each nested container of ``kind`` opened in place (a row in a row is the
    same row, a column in a column the same column)."""
    return [leaf for e in entries for leaf in (_flat(e.instances, kind) if isinstance(e, kind) else [e])]


def _mirrored(regions: list[list[Any]]) -> list[list[Any]]:
    """The pairs a symmetrized Floorplan mirrors (ALIGN's ``Floorplan.yield_constraints``): a
    region of up to two one pair, else its ends inwards and its middle on its own."""
    found = []
    for region in regions:
        if len(region) <= 2:
            found.append(list(region))
            continue
        half = len(region) // 2
        found += [[region[i], region[-1 - i]] for i in range(half)]
        if len(region) % 2:
            found.append([region[half]])
    return found


def _is_mos(entry: Any) -> bool:
    if isinstance(entry, Half):
        return _is_mos(entry.instance)
    if isinstance(entry, Side):
        return letter(entry.pair.of) == "m"
    return isinstance(entry, h.Instance) and letter(entry.of) == "m"


@dataclass
class _Lowered:
    """A placement in ALIGN's terms (``_lower``): its rows' entries (instances, parts, sides and
    groups), the sub-cells its columns and placed pairs make (a sub-cell within one before it), the
    mirrorings a pair's sides placed apart get at the module's level, and what is amiss."""

    rows: list[list[Any]]
    made: dict[int, Group] = field(default_factory=dict)
    symmetry: list[Constraint] = field(default_factory=list)
    found: list[str] = field(default_factory=list)


def _named(names: Names, item: Any) -> str | None:
    try:
        return names.instance(item)
    except KeyError:
        return None


def _stated(names: Names, constraints: tuple[Constraint, ...]) -> set[frozenset[str]]:
    """The pairs ``constraints`` mirror (their SymmetricBlocks and symmetrized Floorplans), by name."""
    pairs: list[tuple[Any, ...]] = []
    for c in constraints:
        if isinstance(c, SymmetricBlocks):
            pairs += c.pairs
        elif isinstance(c, Floorplan) and c.symmetrize:
            pairs += [tuple(p) for p in _mirrored([list(r) for r in c.regions])]
    return {frozenset(n for n in (_named(names, x) for x in p) if n is not None) for p in pairs if len(p) == 2}


def _side_pairs(names: Names, regions: list[list[Any]], stated: set[frozenset[str]]) -> list[SymmetricBlocks]:
    """A SymmetricBlocks (an axis of its own) for each pair whose two sides stand in one of
    ``regions`` and are not mirrored already (``stated``, by name)."""
    found = []
    for region in regions:
        by_pair: dict[int, list[Side]] = {}
        for e in region:
            if isinstance(e, Side):
                by_pair.setdefault(id(e.pair), []).append(e)
        for two in by_pair.values():
            key = frozenset(n for n in (_named(names, s) for s in two) if n is not None)
            if len(two) == 2 and len(key) == 2 and key not in stated:
                found.append(SymmetricBlocks((tuple(two),), Axis.VERTICAL))
    return found


def _lower(pnr: PnrInput, names: Names) -> _Lowered:
    """``pnr``'s placement in ALIGN's terms: nested rows opened, each column of more than one entry
    and each pair placed whole a sub-cell (a group, which ``names`` then names), each pair's sides
    in one row mirrored where nothing stated mirrors them."""
    low = _Lowered(rows=[])
    columns = count()

    def pair_cell(pair: h.Pair) -> Group:
        if id(pair) not in low.made:
            p, n = sides(pair)
            name = "X" + own_name(pair.name, letter(pair.of))
            low.made[id(pair)] = Group(
                name,
                (p, n),
                constraints=(
                    Order((p, n), OrderDirection.LEFT_TO_RIGHT),
                    SymmetricBlocks(((p, n),), Axis.VERTICAL),
                ),
            )
            names.subcells[id(pair)] = name
        return low.made[id(pair)]

    def in_group(group: Group) -> None:
        for member in group.instances:
            if isinstance(member, Group):
                in_group(member)
            elif isinstance(member, h.Pair):
                pair_cell(member)
            elif isinstance(member, Column):
                cell = column_cell(member)  # a group, its sub-cell; one entry, that entry
                name = _named(names, cell[0]) if len(cell) == 1 else None
                if name is not None:
                    names.subcells[id(member)] = name

    def in_row(entries: tuple[Any, ...]) -> list[Any]:
        out: list[Any] = []
        for e in _flat(entries, Row):
            if isinstance(e, Column):
                out += column_cell(e)
            elif isinstance(e, h.Pair):
                out.append(pair_cell(e))
            else:
                if isinstance(e, Group):
                    in_group(e)
                out.append(e)
        return out

    def column_cell(col: Column) -> list[Any]:
        regions = [in_row(e.instances if isinstance(e, Row) else (e,)) for e in _flat(col.instances, Column)]
        regions = [r for r in regions if r]
        members = [e for r in regions for e in r]
        if len(members) <= 1:
            return members  # a column of one entry is that entry
        name = col.name or f"Xcolumn{next(columns)}"
        mos = tuple(e for e in members if _is_mos(e))
        floorplan = Floorplan(tuple(map(tuple, regions)), order=True, symmetrize=pnr.symmetric)
        stated = _stated(names, (floorplan,))
        group = Group(
            name,
            tuple(members),
            constraints=(
                floorplan,
                *_side_pairs(names, regions, stated),
                *((DoNotIdentify(mos),) if mos else ()),
            ),
        )
        low.made[id(col)] = group
        names.subcells[id(col)] = name
        return [group]

    low.rows = [r for r in (in_row(placed.instances) for placed in pnr.placement.rows) if r]
    for constraint in pnr.constraints:
        if isinstance(constraint, Group):
            in_group(constraint)
    stated = _stated(
        names,
        (*pnr.constraints, *((Floorplan(tuple(map(tuple, low.rows)), symmetrize=True),) if pnr.symmetric else ())),
    )
    low.symmetry = list(_side_pairs(names, low.rows, stated))

    every = Counter(g.name.upper() for g in _groups(pnr, low))
    taken = {n.upper() for n in (_named(names, i) for i in pnr.module.instances.values()) if n is not None}
    low.found += [f"two sub-cells are named {n}" for n, k in every.items() if k > 1]
    low.found += [f"a sub-cell is named as an instance: {n}" for n in every if n in taken]
    return low


def _groups(pnr: PnrInput, low: _Lowered) -> list[Group]:
    """The module's groups: placed in a row (a column's and a placed pair's among them) or stated
    among its constraints, each once, a group within a group after its own."""
    found: dict[int, Group] = {}

    def add(group: Group) -> None:
        for member in group.instances:
            if isinstance(member, Group):
                add(member)
            elif id(member) in low.made:
                add(low.made[id(member)])
        found.setdefault(id(group), group)

    for entry in (e for r in low.rows for e in r):
        if isinstance(entry, Group):
            add(entry)
    for constraint in pnr.constraints:
        if isinstance(constraint, Group):
            add(constraint)
    return list(found.values())


def _leaves(entry: Any) -> list[Any]:
    """The instances, parts and pair sides an entry places: through any row, column or group
    within it, a pair's two sides."""
    if isinstance(entry, Group | Row | Column):
        return [leaf for member in entry.instances for leaf in _leaves(member)]
    if isinstance(entry, h.Pair):
        return list(sides(entry))
    return [entry]


def issues(pnr: PnrInput) -> list[str]:
    """What keeps the intent from being complete: an instance placed twice (a split one, other than
    once in each part; a grouped one, other than through its group; a pair, other than once in each
    side), one placed and left to ALIGN, one in no row and not left to ALIGN, a placed one not the
    module's, a constraint naming an instance or net not the module's, two sub-cells of one name."""
    module = pnr.module
    own = {id(instance): name for name, instance in module.instances.items()}
    own_pairs = {id(p) for p in pnr.pairs}
    whole = {id(p): p.name for p in pnr.pairs if _unelaborated(module, p)}  # before elaboration
    own.update(whole)
    found: list[str] = []
    placed: Counter[int] = Counter()
    parts: dict[int, int] = {}
    for leaf in (leaf for r in pnr.placement.rows for entry in r.instances for leaf in _leaves(entry)):
        if isinstance(leaf, Side):
            if id(leaf.pair) not in own_pairs:
                found.append("a placed Pair is not the module's")
                continue
            if id(leaf.pair) in whole:
                placed[id(leaf.pair)] += 1
                parts[id(leaf.pair)] = 2
                continue
            made = side_instance(module, leaf)
            if made is None or f"{leaf.pair.name}_{leaf.signal}_" in module.instances:
                found.append(f"{leaf.pair.name}'s {leaf.signal} is no instance of its own")
                continue
            leaf = made
        if isinstance(leaf, Half):
            parts[id(leaf.instance)] = leaf.parts
            leaf = leaf.instance
        placed[id(leaf)] += 1
    auto: set[int] = set()
    for item in pnr.auto:
        if isinstance(item, h.Pair) and id(item) not in whole:
            auto |= {id(made) for s in sides(item) if (made := side_instance(module, s)) is not None}
        else:
            auto.add(id(item))
    for key, n in placed.items():
        if key not in own:
            found.append("a placed instance is not the module's")
        elif n != parts.get(key, 1):
            found.append(f"{own[key]} is placed {n} times")
        elif key in auto:
            found.append(f"{own[key]} is placed and left to ALIGN")
    found += [
        f"{name} is in no row and not left to ALIGN"
        for key, name in own.items()
        if key not in placed and key not in auto
    ]
    names = Names(module)
    low = _lower(pnr, names)
    found += low.found
    stated = [id(c) for c in pnr.constraints]
    for constraint in (*pnr.constraints, *(g for g in _groups(pnr, low) if id(g) not in stated)):
        try:
            constraint.align(names)
        except KeyError as error:
            found.append(f"{type(constraint).__name__} names {error.args[0]}")
    return found


def module_plan(pnr: PnrInput) -> dict[str, Any]:
    """A module's layout intent named as the hierarchical netlist names its objects
    (``flow.circuit.netlists``): its rows (a child module an instance of its own, laid out by its own
    plan; a column or a placed pair a sub-cell), whether they are mirrored, the devices split into
    parts, and its constraints: groups first (a group: instances of this module gathered, as ALIGN's
    GroupBlocks; a column's and a placed pair's among them), its own, then the mirroring of each
    pair's sides placed apart in one row."""
    found = issues(pnr)
    if found:
        raise ValueError(f"{pnr.module.name}'s placement is incomplete: {'; '.join(found)}")
    names = Names(pnr.module)
    low = _lower(pnr, names)
    split = {
        names.instance(e.instance): e.parts
        for r in pnr.placement.rows
        for entry in r.instances
        for e in _leaves(entry)
        if isinstance(e, Half)
    }
    rest = [c for c in pnr.constraints if not isinstance(c, Group)]
    return {
        "rows": [[names.instance(entry) for entry in r] for r in low.rows],
        "symmetric": pnr.symmetric,
        "split": split,
        "constraints": [c.align(names) for c in (*_groups(pnr, low), *rest, *low.symmetry)],
    }
