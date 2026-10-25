"""The layout compiler's netlist check (``flow/web/static/compile.html``): whether a SPICE netlist is
one the ALIGN row flow lays out (``flow/layout/align/build.py``), its diagnostics by line, and its
statistics; ``normalize`` writes the netlist the flow builds from.

The subset: one ``.subckt`` with ``vdd`` and ``vss`` among its ports, of MOS lines (``M name d g s
b model w=... l=... [nf=...] [m=...]``, ``w`` the total width of the fingers or, in a PDK whose
netlists give it per finger (the manifest's ``w_per_finger``), one finger's, of the PDK's row
transistors) and
standard-cell lines (``X name nets... cell``, of the PDK's library); comments (``*`` lines, ``$`` or
``;`` after a statement), continuation lines (``+``) and ``.end``. Nothing else: no includes,
libraries, models, parameters, sources or control blocks, as nothing here is simulated and the
netlist never names a file.

    manifest = in_pdk("ihp130", "flow.layout.lint", "pdk_manifest")
    result = check(text, manifest)  # result.diagnostics, result.stats, result.normalized
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

SUPPLIES = ("vdd", "vss")
# ALIGN on its own: past this many devices its placer may search for tens of minutes
LARGE = 40
NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]*\Z")
SCALE = {"f": 1e-15, "p": 1e-12, "n": 1e-9, "u": 1e-6, "m": 1e-3, "k": 1e3, "meg": 1e6, "g": 1e9}
NUMBER = re.compile(r"([-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?)(meg|[fpnumkg])?\Z", re.IGNORECASE)
MOS_KEYS = {"w", "l", "nf", "ng", "m"}
# a MOS terminal's role, for the nets each connects
TERMINALS = ("d", "g", "s", "b")


@dataclass
class Device:
    name: str
    line: int  # 1-based, of the statement's first line
    kind: str  # "m" or "x"
    nets: list[str]
    model: str  # MOS model or library cell
    params: dict[str, float] = field(default_factory=dict)
    polarity: str | None = None  # "n" or "p" for a MOS line of the PDK's models


@dataclass
class Result:
    top: str | None
    ports: list[str]
    devices: list[Device]
    diagnostics: list[dict]
    stats: list[dict]

    @property
    def ok(self) -> bool:
        return not any(item["severity"] == "error" for item in self.diagnostics)


def pdk_manifest() -> dict:
    """What a netlist may use in the PDK this process is bound to (``flow.layout.pdkproc.in_pdk``):
    its row transistors' models by polarity, its library cells with their pins, and whether its
    netlists give a MOS's ``w`` per finger (``stems/mosline.py``)."""

    import mosline
    import tech
    from paths import STD_SPICE

    cells = {}
    for line in STD_SPICE.read_text(errors="replace").splitlines():
        words = line.split()
        if len(words) > 1 and words[0].lower() == ".subckt":
            cells.setdefault(words[1], [pin.lower() for pin in words[2:]])
    return {"models": dict(tech.MODELS), "cells": cells, "w_per_finger": mosline.w_per_finger()}


def number(text: str) -> float | None:
    """A SPICE number with an optional scale (``500n``, ``1.2u``, ``2meg``, ``3e-6``), else None."""

    match = NUMBER.match(text)
    if not match:
        return None
    return float(match[1]) * SCALE.get((match[2] or "").lower(), 1.0)


def statements(text: str) -> list[tuple[int, list[str]]]:
    """The netlist's statements, each its first line number and words: comments dropped,
    continuation lines joined."""

    out: list[tuple[int, list[str]]] = []
    for number_, raw in enumerate(text.splitlines(), 1):
        line = re.split(r"\s[$;]|^[$;]", raw, maxsplit=1)[0].strip()
        if not line or line.startswith("*"):
            continue
        if line.startswith("+"):
            if out:
                out[-1][1].extend(line[1:].split())
            else:
                out.append((number_, line[1:].split()))
            continue
        out.append((number_, line.split()))
    return out


def check(text: str, manifest: dict) -> Result:
    """Check ``text`` against the PDK's ``manifest`` (``pdk_manifest``)."""

    diagnostics: list[dict] = []

    def say(severity: str, message: str, line: int | None = None, rule: str | None = None) -> None:
        item = {"severity": severity, "source": "netlist", "message": message}
        if line is not None:
            item["line"] = line
        if rule:
            item["rule"] = rule
        diagnostics.append(item)

    models = {model.lower(): polarity for polarity, model in manifest["models"].items()}
    cells = {name.lower(): (name, pins) for name, pins in manifest["cells"].items()}
    allowed = " and ".join(manifest["models"].values())
    top, ports, devices = None, [], []
    opened = closed = 0
    seen: dict[str, int] = {}
    for line, words in statements(text):
        head = words[0].lower()
        if head == ".subckt":
            opened += 1
            if opened > 1:
                say(
                    "error",
                    "one subcircuit per netlist: the top cell, of transistors and library cells",
                    line,
                    "hierarchy",
                )
                continue
            if len(words) < 2:
                say("error", ".subckt needs a name and its ports", line, "syntax")
                continue
            top = words[1]
            if not NAME.match(top):
                say("error", f"the cell name {top!r} must be letters, digits and underscores", line, "name")
            ports = [port.lower() for port in words[2:]]
            for port in sorted({port for port in ports if ports.count(port) > 1}):
                say("error", f"port {port} is listed twice", line, "ports")
            missing = [supply for supply in SUPPLIES if supply not in ports]
            if missing:
                say(
                    "error",
                    f"no {' or '.join(missing)} port: the supplies are vdd and vss (the row cells' rails)",
                    line,
                    "supplies",
                )
            continue
        if head == ".ends":
            closed += 1
            continue
        if head == ".end":
            continue
        if head.startswith("."):
            say(
                "error",
                f"{words[0]} is not supported: one .subckt of MOS and library-cell instances, nothing "
                "included or simulated",
                line,
                "statement",
            )
            continue
        if opened == 0 or closed >= opened:
            say("error", f"{words[0]} is outside the .subckt", line, "syntax")
            continue
        name = words[0]
        if name.lower() in seen:
            say("error", f"{name} is also defined on line {seen[name.lower()]}", line, "duplicate")
            continue
        seen[name.lower()] = line
        if head[0] == "m":
            device = _mos(name, line, words, models, allowed, say)
        elif head[0] == "x":
            device = _cell(name, line, words, cells, say)
        else:
            say("error", f"{name}: only M (MOS) and X (library cell) instances are laid out", line, "element")
            continue
        if device is not None:
            devices.append(device)
    if opened == 0:
        say("error", "no .subckt: the netlist is one subcircuit, its ports on the .subckt line", None, "syntax")
    elif closed < min(opened, 1):
        say("error", f".subckt {top} has no .ends", None, "syntax")
    if opened and not devices and not any(item["severity"] == "error" for item in diagnostics):
        say("error", "no devices: nothing to lay out", None, "empty")
    _connectivity(ports, devices, say)
    mos = [device for device in devices if device.kind == "m"]
    if len(devices) > LARGE:
        say(
            "warning",
            f"{len(devices)} devices: ALIGN on its own may place for tens of minutes (it stops at 30)",
            None,
            "size",
        )
    per_finger = manifest.get("w_per_finger", False)

    def copies(d: Device) -> float:  # w times this: the device's total width
        return d.params.get("m", 1) * (d.params.get("nf", 1) if per_finger else 1)

    gate_area = sum(d.params["w"] * d.params["l"] * copies(d) for d in mos if "w" in d.params and "l" in d.params)
    width = sum(d.params["w"] * copies(d) for d in mos if "w" in d.params)
    nets = {net for device in devices for net in device.nets} - set(ports)
    stats = [
        {"group": "Netlist", "label": "Cell", "value": top or "—"},
        {"group": "Netlist", "label": "Ports", "value": len(ports)},
        {"group": "Netlist", "label": "NMOS", "value": sum(d.polarity == "n" for d in mos)},
        {"group": "Netlist", "label": "PMOS", "value": sum(d.polarity == "p" for d in mos)},
        {"group": "Netlist", "label": "Library cells", "value": sum(d.kind == "x" for d in devices)},
        {"group": "Netlist", "label": "Internal nets", "value": len(nets)},
        {"group": "Netlist", "label": "Gate area", "value": round(gate_area * 1e12, 4), "unit": "µm²"},
        {"group": "Netlist", "label": "Total width", "value": round(width * 1e6, 3), "unit": "µm"},
    ]
    diagnostics.sort(key=lambda item: (item.get("line") or 0, item["severity"] != "error"))
    return Result(top, ports, devices, diagnostics, stats)


def _mos(name: str, line: int, words: list[str], models: dict, allowed: str, say) -> Device | None:
    if len(words) < 6:
        say("error", f"{name}: a MOS line is M<name> drain gate source bulk model w=... l=...", line, "syntax")
        return None
    nets = [net.lower() for net in words[1:5]]
    model = words[5]
    polarity = models.get(model.lower())
    if polarity is None:
        say("error", f"{name}: model {model} is not one the row cells draw ({allowed})", line, "model")
    params: dict[str, float] = {}
    for word in words[6:]:
        if "=" not in word:
            say("error", f"{name}: {word!r} is not a key=value parameter", line, "syntax")
            continue
        key, value = (part.strip() for part in word.split("=", 1))
        key = key.lower()
        parsed = number(value)
        if parsed is None:
            say(
                "error",
                f"{name}: {key}={value} is not a number (expressions and parameters are not supported)",
                line,
                "value",
            )
            continue
        if key not in MOS_KEYS:
            say("warning", f"{name}: {key} is ignored (the layout takes w, l, nf and m)", line, "parameter")
            continue
        params["nf" if key == "ng" else key] = parsed
    for key in ("w", "l"):
        if key not in params:
            say("error", f"{name}: no {key}=", line, "size")
        elif params[key] <= 0:
            say("error", f"{name}: {key} must be positive", line, "size")
    for key in ("nf", "m"):
        if key in params and (params[key] < 1 or params[key] != int(params[key])):
            say("error", f"{name}: {key} must be a whole number of at least 1", line, "size")
    drain, _gate, source, bulk = nets
    if drain == source:
        say("info", f"{name}: drain and source on one net ({drain}): a MOS capacitor?", line, "shorted")
    rail = {"n": "vss", "p": "vdd"}.get(polarity or "")
    if rail and bulk != rail:
        say("warning", f"{name}: bulk on {bulk}: the row cells tie {polarity.upper()}MOS bulk to {rail}", line, "bulk")
    return Device(name, line, "m", nets, model, params, polarity)


def _cell(name: str, line: int, words: list[str], cells: dict, say) -> Device | None:
    if len(words) < 3:
        say("error", f"{name}: a library-cell line is X<name> nets... cell", line, "syntax")
        return None
    found = cells.get(words[-1].lower())
    nets = [net.lower() for net in words[1:-1]]
    if found is None:
        say("error", f"{name}: {words[-1]} is not a library cell of this PDK", line, "cell")
        return None
    cell, pins = found
    if len(nets) != len(pins):
        say("error", f"{name}: {cell} has {len(pins)} pins ({' '.join(pins)}), not {len(nets)}", line, "pins")
    return Device(name, line, "x", nets, cell)


def _connectivity(ports: list[str], devices: list[Device], say) -> None:
    """Ports nothing connects, and inner nets on one terminal or on gates alone."""

    terminals: dict[str, list[tuple[Device, str]]] = {}
    for device in devices:
        roles = TERMINALS if device.kind == "m" else ("pin",) * len(device.nets)
        for net, role in zip(device.nets, roles, strict=False):
            terminals.setdefault(net, []).append((device, role))
    for port in ports:
        if port not in terminals and port not in SUPPLIES:
            say("warning", f"port {port} connects to nothing: it is left out of the layout", None, "port")
    for net, ends in sorted(terminals.items()):
        if net in ports:
            continue
        first = min(device.line for device, _ in ends)
        if len(ends) == 1:
            device, role = ends[0]
            say("warning", f"net {net} connects only to {device.name}'s {role}", first, "floating")
        elif all(role == "g" for _, role in ends):
            say("warning", f"net {net} reaches only gates: nothing drives it", first, "undriven")


def normalize(result: Result) -> str:
    """The netlist the flow builds from: the subcircuit and its instances one line each, net names
    lower case, comments dropped."""

    lines = [f".subckt {result.top} {' '.join(result.ports)}"]
    for device in result.devices:
        if device.kind == "m":
            # lengths in nm and counts whole, as the generators write them (netcells reads both)
            sizes = " ".join(
                f"{key}={round(value * 1e9)}n" if key in ("w", "l") else f"{key}={int(value)}"
                for key, value in device.params.items()
            )
            lines.append(f"{device.name} {' '.join(device.nets)} {device.model} {sizes}")
        else:
            lines.append(f"{device.name} {' '.join(device.nets)} {device.model}")
    lines.append(f".ends {result.top}")
    return "\n".join(lines) + "\n"


def example(manifest: dict) -> str:
    """A small netlist in the PDK: a five-transistor OTA."""

    n, p = manifest["models"]["n"], manifest["models"]["p"]
    w, meaning = ("2u", "one finger's width") if manifest.get("w_per_finger") else ("4u", "the total width")
    return f"""* A five-transistor OTA: an NMOS pair on a tail current source and a PMOS mirror load.
* w is {meaning}, nf the fingers; the supplies are vdd and vss.
.subckt ota5t inp inn out vbn vdd vss
Mtail tail vbn vss vss {n} w={w} l=1u nf=2
Mpair_p mir inp tail vss {n} w={w} l=0.5u nf=2
Mpair_n out inn tail vss {n} w={w} l=0.5u nf=2
Mload_p mir mir vdd vdd {p} w={w} l=0.5u nf=2
Mload_n out mir vdd vdd {p} w={w} l=0.5u nf=2
.ends ota5t
"""
