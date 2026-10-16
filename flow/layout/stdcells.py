"""Standard cells in a transistor netlist: logic is always the PDK's library cells.

``recognize`` finds groups of transistors that form one of the PDK's library cells and writes
them as an instance of that cell, so the layout tools place the library cell. A group matches a
cell when its transistors connect as the cell's do (drain and source interchangeable, parallel
fingers merged), with the same polarity and channel length, and the cell's internal nets touch
nothing else in the netlist. Of the cells that match one group (the drive strengths of a
function), the one whose transistor widths come closest. The instance is named after the
transistors' common prefix (``Mbuf1_outp_n``, ``Mbuf1_outp_p`` -> ``Xbuf1_outp``).

It works on SPICE text: the netlist (one flat subcircuit) and the library's subcircuits.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass, replace
from math import log
from pathlib import Path

UNITS = {"": 1e9, "u": 1e3, "n": 1.0, "p": 1e-3, "m": 1e6}  # to nm; a plain number is in metres
VALUE = re.compile(r"^([-+0-9.eE]+?)(u|n|p|m)?$", re.IGNORECASE)


def _nm(value: str) -> float:
    m = VALUE.match(value.strip())
    if not m:
        raise ValueError(f"not a length: {value!r}")
    return float(m.group(1)) * UNITS[(m.group(2) or "").lower()]


@dataclass(frozen=True)
class Mos:
    """A transistor: total width and length in nm, fingers, polarity from its bulk's supply."""

    name: str
    d: str
    g: str
    s: str
    b: str
    model: str
    w: float
    l: float
    nf: int
    pol: str


def _lines(spice: str) -> list[str]:
    return re.sub(r"\n\+", " ", spice).splitlines()  # continuation lines joined


def _mos(fields: list[str], supplies: tuple[str, str]) -> Mos:
    """A MOS line; ``supplies``: (VDD, VSS) net names, whose bulk tells PMOS from NMOS."""

    p = {k.lower(): v for k, v in (kv.split("=", 1) for kv in fields[6:] if "=" in kv)}
    fingers = int(float(p.get("nf", p.get("ng", 1))))
    m = int(float(p.get("m", 1)))
    d, g, s, b = fields[1:5]
    pol = "p" if b.lower() == supplies[0].lower() else "n" if b.lower() == supplies[1].lower() else "?"
    return Mos(fields[0], d, g, s, b, fields[5], _nm(p["w"]) * m, _nm(p["l"]), fingers * m, pol)


def library(spice: str, cells: Iterable[str], supplies: tuple[str, str]) -> dict[str, tuple[list[str], list[Mos]]]:
    """The cells' subcircuits from library SPICE: pins in .subckt order and transistors."""

    wanted = {c.lower(): c for c in cells}
    out: dict[str, tuple[list[str], list[Mos]]] = {}
    name = None
    for line in _lines(spice):
        f = line.split()
        if not f or f[0].startswith("*"):
            continue
        if f[0].lower() == ".subckt":
            name = wanted.get(f[1].lower())
            if name:
                out[name] = (f[2:], [])
        elif f[0].lower() == ".ends":
            name = None
        elif name and f[0][0] in "Mm":
            out[name][1].append(_mos(f, supplies))
    return out


def _merged(devs: list[Mos]) -> list[Mos]:
    """Parallel transistors (same nets, drain and source either way, same polarity and length) as one."""

    out: list[Mos] = []
    for v in devs:
        for k, u in enumerate(out):
            if u.pol == v.pol and u.g == v.g and abs(u.l - v.l) < 0.5 and {u.d, u.s} == {v.d, v.s}:
                out[k] = replace(u, w=u.w + v.w, nf=u.nf + v.nf)
                break
        else:
            out.append(v)
    return out


def _stacks_merged(devs: list[Mos], pins: list[str]) -> list[Mos]:
    """Parallel copies of a two-transistor series stack (a drive-2 NOR2's PMOS, say), each with its
    own internal net, as one stack: the library draws stronger cells that way."""

    stacks: dict[tuple, list[tuple[str, list[int]]]] = {}
    for net in sorted({n for v in devs for n in (v.d, v.s)} - set(pins)):
        on = [k for k, v in enumerate(devs) if net in (v.d, v.s)]
        if len(on) != 2 or any(devs[k].g == net for k in range(len(devs))) or devs[on[0]].pol != devs[on[1]].pol:
            continue
        ends = []
        for k in on:
            v = devs[k]
            ends.append(((v.s if v.d == net else v.d), v.g, round(v.l)))
        order = sorted(range(2), key=lambda i: ends[i])
        key = (devs[on[0]].pol, tuple(ends[i] for i in order))
        stacks.setdefault(key, []).append((net, [on[i] for i in order]))
    drop: set[int] = set()
    out = list(devs)
    for copies in stacks.values():
        _, keep = copies[0]
        for _, other in copies[1:]:
            for a, b in zip(keep, other, strict=True):
                out[a] = replace(out[a], w=out[a].w + devs[b].w, nf=out[a].nf + devs[b].nf)
                drop.add(b)
    return [v for k, v in enumerate(out) if k not in drop]


def _signal(pins: list[str], supplies: tuple[str, str]) -> bool:
    return any(p.lower() not in {s.lower() for s in supplies} for p in pins)


def _matches(cell: list[Mos], pins: list[str], devs: list[Mos], ports: set[str], lib_supplies, supplies):
    """Every embedding of the cell's transistors in ``devs``: (devices, cell net -> netlist net)."""

    fixed = {lib_supplies[0]: supplies[0], lib_supplies[1]: supplies[1]}
    internal = {n for v in cell for n in (v.d, v.g, v.s)} - set(pins)
    touching: dict[str, set[int]] = {}
    for k, v in enumerate(devs):
        for n in (v.d, v.g, v.s, v.b):
            touching.setdefault(n, set()).add(k)

    def bind(net_map, a, b):
        if a in net_map:
            return net_map[a] == b
        if a in fixed:
            return fixed[a] == b
        return b not in net_map.values() and b not in supplies

    def search(i, used, net_map):
        if i == len(cell):
            chosen = set(used)
            for a in internal:  # internal nets stay inside the group and are no ports
                n = net_map[a]
                if n in ports or not touching.get(n, set()) <= chosen:
                    return
            yield list(used), dict(net_map)
            return
        c = cell[i]
        for k, v in enumerate(devs):
            if k in used or v.pol != c.pol or abs(v.l - c.l) > 0.5 or v.b != fixed.get(c.b):
                continue
            for d, s in ((v.d, v.s), (v.s, v.d)):
                trial = dict(net_map)
                if all(bind(trial, a, b) and trial.setdefault(a, b) == b for a, b in ((c.d, d), (c.g, v.g), (c.s, s))):
                    yield from search(i + 1, [*used, k], trial)

    yield from search(0, [], {})


def _instance_name(names: list[str], taken: set[str], cell: str) -> str:
    prefix = names[0]
    for n in names[1:]:
        while not n.startswith(prefix):
            prefix = prefix[:-1]
    base = prefix.rstrip("_")[1:] if len(prefix) > 2 else ""
    name = f"X{base}" if base else f"X{cell}"
    k = 0
    while name in taken:
        k += 1
        name = f"X{base or cell}_{k}"
    return name


def recognize(
    netlist: str,
    lib: dict[str, tuple[list[str], list[Mos]]],
    *,
    supplies: tuple[str, str] = ("vdd", "vss"),
    lib_supplies: tuple[str, str] = ("VDD", "VSS"),
) -> tuple[str, dict[str, str]]:
    """``netlist`` with every group of transistors that forms a library cell written as an instance
    of it; also returns instance -> cell. Larger cells first, then the closest drive."""

    lines = _lines(netlist)
    sub = next(k for k, line in enumerate(lines) if line.split()[:1] and line.split()[0].lower() == ".subckt")
    ports = set(lines[sub].split()[2:])
    rows = {
        k: _mos(line.split(), supplies)
        for k, line in enumerate(lines)
        if line.split()[:1] and line.split()[0][0] in "Mm"
    }
    keys = list(rows)
    devs = [rows[k] for k in keys]
    cells = {
        c: (pins, _stacks_merged(_merged(ds), pins))
        for c, (pins, ds) in lib.items()
        if ds and _signal(pins, lib_supplies)
    }

    found = []  # (devices, cost, cell, net map)
    for cell, (pins, cdevs) in cells.items():
        seen = set()
        for used, net_map in _matches(cdevs, pins, devs, ports, lib_supplies, supplies):
            group = frozenset(used)
            if group in seen:  # the same group by a symmetry of the cell
                continue
            seen.add(group)
            # widths: each cell transistor against its netlist transistor
            cost = sum(abs(log(devs[k].w / c.w)) for k, c in zip(used, cdevs, strict=True))
            found.append((group, cost, cell, net_map))
    taken_devs: set[int] = set()
    names = {v.name for v in devs}
    out: dict[int, str] = {}
    cells_of: dict[str, str] = {}
    for group, _, cell, net_map in sorted(found, key=lambda f: (-len(f[0]), f[1], f[2])):
        if group & taken_devs:
            continue
        taken_devs |= group
        pins = lib[cell][0]
        fixed = dict(zip(lib_supplies, supplies, strict=True))
        inst = _instance_name(sorted(devs[k].name for k in group), names | set(cells_of), cell)
        cells_of[inst] = cell
        out[keys[min(group)]] = f"{inst} {' '.join(net_map.get(p, fixed.get(p, p)) for p in pins)} {cell}"
    gone = {keys[k] for k in taken_devs}
    result = [out.get(k, line) for k, line in enumerate(lines) if k in out or k not in gone]
    return "\n".join(result) + "\n", cells_of


def _pdk_library() -> tuple[dict[str, tuple[list[str], list[Mos]]], tuple[str, str]]:
    """The library cells of the PDK this process is bound to (flow/layout/pdkproc.py)."""

    import paths  # the bound PDK's
    import tech

    supplies = tuple(tech.STD_SUPPLY)
    return library(paths.STD_SPICE.read_text(errors="replace"), tech.STD_CELLS, supplies), supplies


def _named(text: str, name: str) -> str:
    return re.sub(r"(?im)^(\.subckt|\.ends)\s+\S+", rf"\1 {name}", text)


def recognize_file(src: Path, dst: Path) -> Path:
    """Run bound to a PDK: ``src`` with its library cells recognized, written to ``dst`` (its
    subcircuit named after it)."""

    lib, supplies = _pdk_library()
    text, cells = recognize(src.read_text(), lib, lib_supplies=supplies)
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(_named(text, dst.stem))
    print(f"{dst.name}: {len(cells)} library cells recognized")
    return dst
