"""Write each PDK's standard-cell library for hdl21 (``pdk/<pdk>/hdl21/cells.py``): every cell of
its chosen library, and which cell implements each generic cell (``flow.circuit.cells``).

    uv run python -m flow.circuit.cellmap [pdk ...]

From the library's Liberty (``layout/paths.py``'s ``STD_LIBERTY``): each pin's direction and
function, the flip-flops' and latches' groups, ``dont_use``, the area; from its SPICE
(``STD_SPICE``): the subcircuits' pin order, which an instance's connections follow. A
combinational cell implements a generic function when its output's truth table is the function's
under some assignment of its inputs (that assignment is the pin map); a flip-flop when it is
clocked on one pin's rising edge with one data pin, a latch when one pin enables it high; a reset
or set must be active low. A cell's drive is its name's (``layout/tech.py``'s ``STD_DRIVE``, a
regular expression whose group is the drive). Clock cells (CK, CLK in the name), delay cells (DLY,
DEL) and ``dont_use`` cells implement nothing, except tie cells (synthesis keeps those for its tie
insertion; no drive in their names: drive 1). Among the cells of a function and drive the shortest
name wins, then the smallest area. A flip-flop or latch without a reset or set stands in by one with
them, those held inactive (``substitute`` ties them); a library without tie cells would tie with an
inverter whose input is on the opposite rail.
"""

from __future__ import annotations

import gzip
import itertools
import re
import sys
from importlib import import_module
from pathlib import Path

from flow.circuit.cells import DEFINITIONS, DRIVES, FUNCTIONS, generic_name

ROOT = Path(__file__).resolve().parents[2]
PDKS = ("tsmc65", "tsmc28", "ihp130", "tower180", "lf150", "tpsc65")
# a flip-flop or latch without reset or set, and the ones that stand in for it (their extra
# pins held inactive)
STAND_INS = {"dff": ("dffr", "dffs", "dffrs"), "dffr": ("dffrs",), "latch": ("latchr", "latchs", "latchrs")}


def _text(path: Path) -> str:
    """A text file, gzipped or not."""
    with gzip.open(path, "rt", errors="replace") if path.suffix == ".gz" else path.open(errors="replace") as file:
        return file.read()


def read_liberty(path: Path) -> dict[str, dict]:
    """Every cell group of a Liberty file: pins (direction, function, pg_type), the ff or latch
    group's attributes, dont_use and area."""

    text = _text(path)
    cells = {}
    for match in re.finditer(r"\bcell\s*\(\s*\"?([\w$]+)\"?\s*\)\s*\{", text):
        depth, index = 1, match.end()
        while depth:
            opening, closing = text.find("{", index), text.find("}", index)
            if opening != -1 and opening < closing:
                depth, index = depth + 1, opening + 1
            else:
                depth, index = depth - 1, closing + 1
        body = text[match.end() : index - 1]
        pins = {}
        for pin in re.finditer(r"\b(pin|pg_pin)\s*\(\s*\"?([\w\[\]]+)\"?\s*\)\s*\{", body):
            head = body[pin.end() : pin.end() + 4000]
            head = head[: head.find("timing")] if "timing" in head else head
            direction = re.search(r"direction\s*:\s*\"?(\w+)", head)
            function = re.search(r"\bfunction\s*:\s*\"([^\"]*)\"", head)
            pg_type = re.search(r"pg_type\s*:\s*\"?(\w+)", head)
            pins[pin.group(2)] = {
                "kind": pin.group(1),
                "direction": direction.group(1) if direction else None,
                "function": function.group(1).strip() if function else None,
                "pg_type": pg_type.group(1) if pg_type else None,
            }
        sequential = re.search(r"\b(ff|latch)\s*\(\s*\"?(\w+)\"?\s*,\s*\"?(\w+)\"?\s*\)\s*\{([^}]*)\}", body)
        attributes = {}
        if sequential:
            for key in ("clocked_on", "next_state", "enable", "data_in", "clear", "preset"):
                found = re.search(key + r"\s*:\s*\"([^\"]*)\"", sequential.group(4))
                if found:
                    attributes[key] = found.group(1).strip()
        area = re.search(r"\barea\s*:\s*([\d.]+)", body)
        cells[match.group(1)] = {
            "pins": pins,
            "sequential": (sequential.group(1), sequential.group(2), sequential.group(3)) if sequential else None,
            "attributes": attributes,
            "dont_use": bool(re.search(r"dont_use\s*:\s*true", body)),
            "area": float(area.group(1)) if area else 0.0,
        }
    return cells


def read_spice_pins(path: Path) -> dict[str, list[str]]:
    """Each subcircuit's pins in order (continuation lines joined)."""

    text = _text(path)
    text = re.sub(r"\n\+", " ", text)
    return {
        m.group(1): m.group(2).split()
        for m in re.finditer(r"^\s*\.subckt\s+(\S+)([^\n]*)", text, re.MULTILINE | re.IGNORECASE)
    }


def evaluate(expression: str, values: dict[str, bool]) -> bool:
    """A Liberty boolean expression (!, ', &, *, juxtaposition, |, +, ^) at the given pin values."""

    tokens = re.findall(r"[A-Za-z_][\w\[\]]*|[!'()*&+|^]|[01]", expression)
    position = 0

    def peek():
        return tokens[position] if position < len(tokens) else None

    def take():
        nonlocal position
        position += 1
        return tokens[position - 1]

    def atom():
        token = take()
        if token == "!":
            value = not atom()
        elif token == "(":
            value = either()
            take()
        elif token in ("0", "1"):
            value = token == "1"
        else:
            value = values[token]
        while peek() == "'":
            take()
            value = not value
        return value

    def both():
        value = atom()
        while peek() is not None and (
            peek() in ("*", "&", "!", "(") or re.fullmatch(r"[A-Za-z_][\w\[\]]*|[01]", peek())
        ):
            if peek() in ("*", "&"):
                take()
            value = atom() and value
        return value

    def exclusive():
        value = both()
        while peek() == "^":
            take()
            value = value != both()
        return value

    def either():
        value = exclusive()
        while peek() in ("+", "|"):
            take()
            value = exclusive() or value
        return value

    return either()


def pin_map(function: str, cell_inputs: list[str], expression: str) -> dict[str, str] | None:
    """The assignment of the cell's inputs to the generic function's that makes the cell's output
    the function's: {cell pin: generic pin}; None where none does."""

    generic_inputs, _outputs = FUNCTIONS[function]
    if len(cell_inputs) != len(generic_inputs):
        return None
    combinations = list(itertools.product((False, True), repeat=len(generic_inputs)))
    wanted = [evaluate(DEFINITIONS[function], dict(zip(generic_inputs, bits, strict=True))) for bits in combinations]
    for order in itertools.permutations(cell_inputs):
        got = [evaluate(expression, dict(zip(order, bits, strict=True))) for bits in combinations]
        if got == wanted:
            return dict(zip(order, generic_inputs, strict=True))
    return None


def _active_low_pin(expression: str | None) -> str | None:
    """The pin of an active-low control ("!RN", "(!RN)", "RESET_B'"); None otherwise."""
    if expression is None:
        return None
    found = re.fullmatch(r"\(?\s*!\s*(\w+)\s*\)?|\(?\s*(\w+)\s*'\s*\)?", expression.strip())
    return (found.group(1) or found.group(2)) if found else None


def sequential_role(name: str, cell: dict) -> tuple[str, dict[str, str], list[str]] | None:
    """A flip-flop's or latch's kind (dff, dffr, dffs, dffrs, latch, ...), {cell pin: generic pin}
    for D, CLK or EN, Q, and its set pins (held high where it stands in for one without)."""

    kind, state, _inverted = cell["sequential"]
    attributes = cell["attributes"]
    single = re.compile(r"\s*\(?\s*(\w+)\s*\)?\s*")
    clock_key, data_key = ("clocked_on", "next_state") if kind == "ff" else ("enable", "data_in")
    clock, data = single.fullmatch(attributes.get(clock_key, "")), single.fullmatch(attributes.get(data_key, ""))
    if not clock or not data:
        return None
    reset, setp = _active_low_pin(attributes.get("clear")), _active_low_pin(attributes.get("preset"))
    if ("clear" in attributes and not reset) or ("preset" in attributes and not setp):
        return None  # an active-high reset or set
    outputs = [pin for pin, info in cell["pins"].items() if info["direction"] == "output" and info["function"] == state]
    if not outputs:
        return None
    pins = {data.group(1): "D", clock.group(1): "CLK" if kind == "ff" else "EN", outputs[0]: "Q"}
    if reset:
        pins[reset] = "RN"
    base = "dff" if kind == "ff" else "latch"
    return base + ("r" if reset else "") + ("s" if setp else ""), pins, [setp] if setp else []


def classify(cells: dict[str, dict], spice: dict[str, list[str]], drive_pattern: str) -> dict[tuple[str, int], list]:
    """(generic function, drive) -> the cells implementing it: (name, area, {cell pin: generic pin},
    cell pins to hold high, cell pins to hold low), the generic functions' own kinds and the stand-in
    kinds alike."""

    found: dict[tuple[str, int], list] = {}
    for name, cell in cells.items():
        signal = {pin: info for pin, info in cell["pins"].items() if info["kind"] == "pin"}
        constant = [info["function"] for info in signal.values() if info["direction"] == "output"]
        tie = bool(constant) and all(function in ("1", "0") for function in constant)
        # dont_use leaves a tie cell to synthesis's tie insertion, not unusable
        if (cell["dont_use"] and not tie) or name not in spice or re.search(r"CK|CLK|DLY|DEL", name.upper()):
            continue
        drive_match = re.search(drive_pattern, name)
        if drive_match and drive_match.group(1).isdigit():
            drive = int(drive_match.group(1))
        elif tie:
            drive = 1  # a tie cell: no drive in its name
        else:
            continue
        inputs = [pin for pin, info in signal.items() if info["direction"] == "input"]
        outputs = [pin for pin, info in signal.items() if info["direction"] == "output"]
        supplies = {
            pin: ("VSS" if (info["pg_type"] or "").endswith(("ground", "pwell")) else "VDD")
            for pin, info in cell["pins"].items()
            if info["kind"] == "pg_pin"
        }
        supplies |= {pin: pin for pin in spice[name] if pin in ("VDD", "VSS") and pin not in supplies}
        entries = []
        if cell["sequential"]:
            role = sequential_role(name, cell)
            if role:
                kind, pins, high = role
                entries.append((kind, pins, high, []))
        elif len(outputs) == 1 and signal[outputs[0]]["function"]:
            expression = signal[outputs[0]]["function"]
            if expression in ("1", "0") and not inputs:
                entries.append(("tiehi" if expression == "1" else "tielo", {outputs[0]: "Y"}, [], []))
            for function in DEFINITIONS:
                pins = pin_map(function, inputs, expression)
                if pins is not None:
                    entries.append((function, {**pins, outputs[0]: "Y"}, [], []))
        for kind, pins, high, low in entries:
            found.setdefault((kind, drive), []).append((name, cell["area"], {**pins, **supplies}, high, low))
    return found


def generic_mapping(found: dict[tuple[str, int], list]) -> tuple[dict[str, tuple], list[str]]:
    """Each generic cell (``DRIVES``) -> (cell, {cell pin: generic pin}, held high, held low), and
    the generic cells the library cannot implement."""

    mapping, missing = {}, []
    for function, drives in DRIVES.items():
        for drive in drives:
            choice = None
            for kind in (function, *STAND_INS.get(function, ())):
                candidates = sorted(found.get((kind, drive), []), key=lambda item: (len(item[0]), item[1], item[0]))
                if candidates:
                    name, _area, pins, high, low = candidates[0]
                    if kind != function:  # a stand-in: its reset (and set) held inactive
                        unused = [
                            pin
                            for pin, generic in pins.items()
                            if generic == "RN" and "RN" not in FUNCTIONS[function][0]
                        ]
                        pins = {pin: generic for pin, generic in pins.items() if pin not in unused}
                        high = [*high, *unused]
                    choice = (name, pins, high, low)
                    break
            if choice is None and function in ("tiehi", "tielo"):
                inverters = sorted(found.get(("inv", 1), []), key=lambda item: (len(item[0]), item[1], item[0]))
                if inverters:  # an inverter on the opposite rail
                    name, _area, pins, _high, _low = inverters[0]
                    held = [pin for pin, generic in pins.items() if generic == "A"]
                    pins = {pin: generic for pin, generic in pins.items() if generic != "A"}
                    choice = (name, pins, held if function == "tielo" else [], held if function == "tiehi" else [])
            if choice is None:
                missing.append(generic_name(function, drive))
            else:
                mapping[generic_name(function, drive)] = choice
    return mapping, missing


def write_library(pdk: str) -> tuple[Path, list[str]]:
    """``pdk/<pdk>/hdl21/cells.py`` for one PDK; its path and the generic cells it lacks."""

    paths = import_module(f"pdk.{pdk}.layout.paths")
    tech = import_module(f"pdk.{pdk}.layout.tech")
    cells = read_liberty(Path(paths.STD_LIBERTY))
    spice = read_spice_pins(Path(paths.STD_SPICE))
    mapping, missing = generic_mapping(classify(cells, spice, tech.STD_DRIVE))
    lines = [
        f'"""Every cell of {tech.STD_LIB} for hdl21 and the generic cells (flow.circuit.cells) it implements.',
        "",
        "Written by flow.circuit.cellmap from the library's Liberty and SPICE; do not edit:",
        f"    uv run python -m flow.circuit.cellmap {pdk}",
        '"""',
        "",
        f'DOMAIN = "{pdk}"',
        f'LIBRARY = "{tech.STD_LIB}"',
        "",
        "# cell -> (pins in SPICE order, their directions)",
        "CELLS = {",
    ]
    for name in sorted(spice):
        if name not in cells:
            continue
        pins = spice[name]
        directions = tuple(cells[name]["pins"].get(pin, {}).get("direction") or "inout" for pin in pins)
        lines.append(f"    {name!r}: ({tuple(pins)!r}, {directions!r}),")
    lines += [
        "}",
        "# generic cell -> (library cell, {cell pin: generic pin}, cell pins held high, cell pins held low)",
        "GENERIC = {",
    ]
    for generic, (name, pins, high, low) in mapping.items():
        lines.append(f"    {generic!r}: ({name!r}, {pins!r}, {tuple(high)!r}, {tuple(low)!r}),")
    lines += ["}", f"# generic cells the library cannot implement: {missing}" if missing else "", ""]
    out = ROOT / "pdk" / pdk / "hdl21" / "cells.py"
    out.write_text("\n".join(line for line in lines if line is not None).rstrip() + "\n")
    return out, missing


def main() -> None:
    for pdk in sys.argv[1:] or PDKS:
        out, missing = write_library(pdk)
        print(f"{pdk}: {out.relative_to(ROOT)}" + (f"; lacks {', '.join(missing)}" if missing else ""))


if __name__ == "__main__":
    main()
