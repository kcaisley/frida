"""hdl21align: a generator's layout intent, stated on its own instances, for ALIGN (after Dan
Fritchman's AlignHdl21, his thesis ch. 7.5).

A generator says where its instances go as it makes them (``place``): a ``Placement``, rows top
first, each row its instances left to right (an hdl21 ``Instance`` itself, never its name, so a
device a generator leaves out is in no row and a renamed one moves with its row); whether the
rows are mirrored about their centre (``symmetric``); the instances ALIGN may place where it
likes (``auto``); and any of ALIGN's further constraints (``constraints``: every type ALIGN has,
stated on the module's own instances and nets, ``hdl21align.constraints``). The ``PnrInput`` rides
on the module as an hdl21 Property, which no netlist or simulation carries, so the netlist is
unchanged; ALIGN places what is stated and derives only what is not.

The netlist is hierarchical: a child module is a subcircuit of its own, laid out by its own
intent (its own ``place``), and placed in its parent's rows as one instance. A ``Group`` (ALIGN's
GroupBlocks) gathers instances of one module into a sub-cell of the layout alone, for a netlist
from elsewhere that states no layout of its own.

``issues`` is the completeness check a generator's tests run on every instance of its space,
without ALIGN: every instance placed exactly once or left to ALIGN, every placed one the
module's, every instance and net a constraint names the module's. ``module_plan`` is a module's
intent named as the netlist names its objects, the form ALIGN's constraint files take
(``flow.circuit.netlists.align_design``).

Unlike AlignHdl21, nothing here replaces hdl21's elaborator (Fritchman notes custom elaborators do
not compose): the intent is read from the Property after elaboration, by a walk of the hierarchy
(``pnr_inputs``), the same way a PDK's compile passes read a module.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Any

import hdl21 as h
from hdl21.primitives import C, Mos

from .constraints import Constraint, Group

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


Entry = h.Instance | Half | Group


@dataclass(frozen=True)
class Row:
    """A row of instances (or parts of one), left to right."""

    instances: tuple[Entry, ...]


def row(*instances: Entry | None) -> Row:
    """A row of ``instances``, left to right; a ``None`` (an instance a generator leaves out) is skipped."""
    return Row(tuple(instance for instance in instances if instance is not None))


@dataclass(frozen=True)
class Placement:
    """Rows of instances, top first."""

    rows: tuple[Row, ...]


def rows(*placed: Row) -> Placement:
    """The rows top first; an empty row is dropped."""
    return Placement(tuple(r for r in placed if r.instances))


@dataclass
class PnrInput:
    """A module's layout intent: its placement, its mirroring, what ALIGN places itself, and
    ALIGN's further constraints on it."""

    module: h.Module
    placement: Placement
    symmetric: bool = True
    auto: tuple[h.Instance, ...] = ()
    constraints: tuple[Constraint, ...] = ()


def place(
    module: h.Module,
    placement: Placement,
    *,
    symmetric: bool = True,
    auto: tuple[h.Instance, ...] = (),
    constraints: tuple[Constraint, ...] = (),
) -> PnrInput:
    """State ``module``'s layout intent; it rides on the module as a Property."""
    if module.props.get(_PNR_INPUT) is not None:
        raise ValueError(f"{module.name} already states its placement")
    pnr = PnrInput(module, placement, symmetric, tuple(auto), tuple(constraints))
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
        for instance in current.instances.values():
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


class Names:
    """ALIGN's names for a module's objects as the netlist writes them (``flow.circuit.netlists``):
    an instance (``netlist_name``; a part of one, ``<name>_a``; a group, its own name), a net or port
    (lower case), an instance's pin (``m.MP.d``: ``Mp/d``). One not the module's raises ``KeyError``."""

    def __init__(self, module: h.Module) -> None:
        self.module = module
        self._instances = {id(instance): name for name, instance in module.instances.items()}
        self._nets = {id(signal): name for name, signal in (*module.ports.items(), *module.signals.items())}

    def instance(self, item: Any) -> str:
        if isinstance(item, Group):
            return item.name
        if isinstance(item, Half):
            return f"{self.instance(item.instance)}_{chr(ord('a') + item.index)}"
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


def _groups(pnr: PnrInput) -> list[Group]:
    """The module's groups: placed in a row or stated among its constraints, each once, a group
    within a group after its own."""
    found: dict[int, Group] = {}

    def add(group: Group) -> None:
        for member in group.instances:
            if isinstance(member, Group):
                add(member)
        found.setdefault(id(group), group)

    for entry in (e for r in pnr.placement.rows for e in r.instances):
        if isinstance(entry, Group):
            add(entry)
    for constraint in pnr.constraints:
        if isinstance(constraint, Group):
            add(constraint)
    return list(found.values())


def _leaves(entry: Any) -> list[h.Instance | Half]:
    """The instances (or parts) an entry places: a group's, through any group within it."""
    if isinstance(entry, Group):
        return [leaf for member in entry.instances for leaf in _leaves(member)]
    return [entry]


def issues(pnr: PnrInput) -> list[str]:
    """What keeps the intent from being complete: an instance placed twice (a split one, other than
    once in each part; a grouped one, other than through its group), one placed and left to ALIGN,
    one in no row and not left to ALIGN, a placed one not the module's, a constraint naming an
    instance or net not the module's."""
    own = {id(instance): name for name, instance in pnr.module.instances.items()}
    entries = [leaf for r in pnr.placement.rows for entry in r.instances for leaf in _leaves(entry)]
    placed = Counter(id(_instance(entry)) for entry in entries)
    parts = {id(entry.instance): entry.parts for entry in entries if isinstance(entry, Half)}
    auto = {id(instance) for instance in pnr.auto}
    found = []
    for key, count in placed.items():
        if key not in own:
            found.append("a placed instance is not the module's")
        elif count != parts.get(key, 1):
            found.append(f"{own[key]} is placed {count} times")
        elif key in auto:
            found.append(f"{own[key]} is placed and left to ALIGN")
    found += [
        f"{name} is in no row and not left to ALIGN"
        for key, name in own.items()
        if key not in placed and key not in auto
    ]
    names = Names(pnr.module)
    for constraint in pnr.constraints:
        try:
            constraint.align(names)
        except KeyError as error:
            found.append(f"{type(constraint).__name__} names {error.args[0]}")
    return found


def _instance(entry: h.Instance | Half) -> h.Instance:
    return entry.instance if isinstance(entry, Half) else entry


def module_plan(pnr: PnrInput) -> dict[str, Any]:
    """A module's layout intent named as the hierarchical netlist names its objects
    (``flow.circuit.netlists``): its rows (a child module an instance of its own, laid out by its own
    plan), whether they are mirrored, the devices split into parts, and its constraints, groups first
    (a group: instances of this module gathered, as ALIGN's GroupBlocks)."""
    found = issues(pnr)
    if found:
        raise ValueError(f"{pnr.module.name}'s placement is incomplete: {'; '.join(found)}")
    names = Names(pnr.module)
    split = {
        names.instance(e.instance): e.parts
        for r in pnr.placement.rows
        for entry in r.instances
        for e in _leaves(entry)
        if isinstance(e, Half)
    }
    groups = _groups(pnr)
    rest = [c for c in pnr.constraints if not isinstance(c, Group)]
    return {
        "rows": [[names.instance(entry) for entry in r.instances] for r in pnr.placement.rows],
        "symmetric": pnr.symmetric,
        "split": split,
        "constraints": [c.align(names) for c in (*groups, *rest)],
    }
