"""Generic standard cells: the functions and drive strengths every PDK's chosen library has, by one
name, for PDK-agnostic netlists; each PDK's compile pass swaps them for its own cells.

A generic cell is an ExternalModule of the "generic" domain named ``<function>_x<drive>``
(``nand2_x1``, ``inv_x4``) with the same ports in every PDK: inputs A, B, C, D (a mux's select S),
output Y; flip-flops D, CLK and Q, with RN an active-low reset; the latch D, EN (transparent while
high) and Q; supplies VDD and VSS. ``DRIVES`` lists the drives every library reaches, natively or
through a substitute (a flip-flop with a reset for one without, its reset held inactive).

Each PDK's hdl21 package holds its library (``cells.py``, written by ``flow.circuit.cellmap``):
every cell with its SPICE pin order and directions, and which cell implements each generic one with
which pins. ``substitute`` builds the wrapper a compile pass returns: the library cell, its pins
on the wrapper's, an output it does not use on a net of its own, an input it holds inactive on the
library's tie cell (a gate tied to a rail by metal alone breaks some PDKs' rules). A library
without tie cells would tie with an inverter whose input is on the opposite rail.

    from flow.circuit.cells import cell
    module.Xnand = cell("nand2", 1)(A=a, B=b, Y=y, VDD=vdd, VSS=vss)
"""

from __future__ import annotations

from types import ModuleType

import hdl21 as h

# function -> (inputs, outputs) in the generic port order
FUNCTIONS: dict[str, tuple[tuple[str, ...], tuple[str, ...]]] = {
    "inv": (("A",), ("Y",)),
    "buf": (("A",), ("Y",)),
    "nand2": (("A", "B"), ("Y",)),
    "nand3": (("A", "B", "C"), ("Y",)),
    "nand4": (("A", "B", "C", "D"), ("Y",)),
    "nor2": (("A", "B"), ("Y",)),
    "nor3": (("A", "B", "C"), ("Y",)),
    "nor4": (("A", "B", "C", "D"), ("Y",)),
    "and2": (("A", "B"), ("Y",)),
    "and3": (("A", "B", "C"), ("Y",)),
    "or2": (("A", "B"), ("Y",)),
    "or3": (("A", "B", "C"), ("Y",)),
    "xor2": (("A", "B"), ("Y",)),
    "xnor2": (("A", "B"), ("Y",)),
    "mux2": (("A", "B", "S"), ("Y",)),
    "aoi21": (("A", "B", "C"), ("Y",)),
    "oai21": (("A", "B", "C"), ("Y",)),
    "aoi22": (("A", "B", "C", "D"), ("Y",)),
    "ao21": (("A", "B", "C"), ("Y",)),
    "dff": (("D", "CLK"), ("Q",)),
    "dffr": (("D", "CLK", "RN"), ("Q",)),
    "latch": (("D", "EN"), ("Q",)),
    "tiehi": ((), ("Y",)),
    "tielo": ((), ("Y",)),
}
# each combinational function over its generic inputs, in Liberty's notation (cellmap compares the
# libraries' cells against it)
DEFINITIONS: dict[str, str] = {
    "inv": "!A",
    "buf": "A",
    "nand2": "!(A&B)",
    "nand3": "!(A&B&C)",
    "nand4": "!(A&B&C&D)",
    "nor2": "!(A|B)",
    "nor3": "!(A|B|C)",
    "nor4": "!(A|B|C|D)",
    "and2": "A&B",
    "and3": "A&B&C",
    "or2": "A|B",
    "or3": "A|B|C",
    "xor2": "A^B",
    "xnor2": "!(A^B)",
    "mux2": "(A&!S)|(B&S)",
    "aoi21": "!((A&B)|C)",
    "oai21": "!((A|B)&C)",
    "aoi22": "!((A&B)|(C&D))",
    "ao21": "(A&B)|C",
}
# function -> the drives every PDK's library has (checked by flow/circuit/test_cells.py)
DRIVES: dict[str, tuple[int, ...]] = {
    "inv": (1, 2, 4, 8, 16),
    "buf": (2, 4, 8, 16),  # Tower180 has no X1 buffer (its X1 is a delay cell)
    "nand2": (1, 2),
    "nand3": (1,),
    "nand4": (1,),
    "nor2": (1, 2),
    "nor3": (1, 2),
    "nor4": (2,),
    "and2": (1, 2),
    "and3": (1, 2),
    "or2": (1, 2),
    "or3": (1, 2),
    "xor2": (1,),
    "xnor2": (1,),
    "mux2": (1, 2),
    "aoi21": (2,),
    "oai21": (1,),
    "aoi22": (1,),
    "ao21": (1,),
    "dff": (1, 2),
    "dffr": (1, 2),
    "latch": (1,),
    "tiehi": (1,),
    "tielo": (1,),
}

_GENERIC: dict[str, h.ExternalModule] = {}


def generic_name(function: str, drive: int) -> str:
    return f"{function}_x{drive}"


def generic_module(function: str, drive: int) -> h.ExternalModule:
    """The generic cell ``<function>_x<drive>``."""

    if drive not in DRIVES.get(function, ()):
        raise ValueError(f"no generic {function} of drive {drive}: every PDK has {DRIVES.get(function)}")
    name = generic_name(function, drive)
    if name not in _GENERIC:
        inputs, outputs = FUNCTIONS[function]
        _GENERIC[name] = h.ExternalModule(
            domain="generic",
            name=name,
            port_list=[
                *(h.Input(name=pin) for pin in inputs),
                *(h.Output(name=pin) for pin in outputs),
                h.Inout(name="VDD"),
                h.Inout(name="VSS"),
            ],
            paramtype=h.HasNoParams,
            desc=f"generic {function}, drive {drive}; a PDK compile pass swaps it for its library's cell",
        )
    return _GENERIC[name]


def cell(function: str, drive: int = 1) -> h.ExternalModuleCall:
    """A generic cell to instance: ``cell("nand2", 1)(A=..., B=..., Y=..., VDD=..., VSS=...)``."""
    return generic_module(function, drive)()


def library_module(library: ModuleType, name: str) -> h.ExternalModule:
    """One cell of a PDK's library (its ``cells.py``) as an ExternalModule, ports in SPICE order."""

    cache = library.__dict__.setdefault("_MODULES", {})
    if name not in cache:
        pins, directions = library.CELLS[name]
        port = {"input": h.Input, "output": h.Output}
        cache[name] = h.ExternalModule(
            domain=library.DOMAIN,
            name=name,
            port_list=[port.get(direction, h.Inout)(name=pin) for pin, direction in zip(pins, directions, strict=True)],
            paramtype=h.HasNoParams,
        )
    return cache[name]


def substitute(call: h.ExternalModuleCall, library: ModuleType) -> h.Module | None:
    """The wrapper that implements a generic cell call with ``library``'s cell; None for any other
    call. A compile pass returns the wrapper in the call's place."""

    module = call.module
    if module.domain != "generic" or module.name not in library.GENERIC:
        return None
    cache = library.__dict__.setdefault("_WRAPPERS", {})
    if module.name in cache:
        return cache[module.name]
    function = module.name.rsplit("_x", 1)[0]
    target, pins, tie_high, tie_low = library.GENERIC[module.name]
    inputs, outputs = FUNCTIONS[function]
    wrapper = h.Module(name=f"{library.DOMAIN}_{module.name}")
    for pin in inputs:
        wrapper.add(h.Input(), name=pin)
    for pin in outputs:
        wrapper.add(h.Output(), name=pin)
    wrapper.VDD, wrapper.VSS = h.Inout(), h.Inout()
    cell_pins, _directions = library.CELLS[target]
    connections = {}
    for pin in cell_pins:
        if pin in pins:
            connections[pin] = getattr(wrapper, pins[pin])
        elif (pin in tie_high or pin in tie_low) and function in ("tiehi", "tielo"):
            connections[pin] = wrapper.VDD if pin in tie_high else wrapper.VSS  # a tie made of another cell
        elif pin in tie_high or pin in tie_low:
            connections[pin] = _tie(wrapper, library, high=pin in tie_high)
        else:  # an output the generic cell does not have
            connections[pin] = wrapper.add(h.Signal(), name=f"open_{pin}")
    wrapper.add(library_module(library, target)()(**connections), name="cell")
    cache[module.name] = wrapper
    return wrapper


def _tie(wrapper: h.Module, library: ModuleType, *, high: bool) -> h.Signal:
    """A net held at a rail for an input the generic cell does not use: the library's tie cell's
    output (one per wrapper and level), or the rail itself where the library has no tie cell."""

    function = "tiehi" if high else "tielo"
    tie = library.GENERIC.get(generic_name(function, 1))
    if tie is None:
        return wrapper.VDD if high else wrapper.VSS
    net = f"{function}_net"
    if not hasattr(wrapper, net):
        signal = wrapper.add(h.Signal(), name=net)
        target, pins, high_pins, low_pins = tie
        output = next(pin for pin, generic in pins.items() if generic == "Y")
        cell_pins, _directions = library.CELLS[target]
        rails = {pin: getattr(wrapper, pins[pin]) for pin in cell_pins if pins.get(pin) in ("VDD", "VSS")}
        # a tie made of another cell (an inverter on the opposite rail) holds its input on the rail
        held = {pin: wrapper.VDD for pin in high_pins} | {pin: wrapper.VSS for pin in low_pins}
        wrapper.add(library_module(library, target)()(**{output: signal}, **rails, **held), name=f"x{function}")
    return getattr(wrapper, net)
