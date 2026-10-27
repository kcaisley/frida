"""The devices every block's generator builds from: analog MOS devices fingered to the PDK's row
cells (``mos``), MOS capacitors (``mos_cap``), the generic logic cells a PDK maps to its library
(``Inverter``, ``Nor2``, ``Nand2``), and a block's circuit written as one flat SPICE subcircuit
after the PDK's compile (``write_netlist``)."""

from importlib import import_module
from math import ceil
from pathlib import Path

import hdl21 as h
from hdl21.primitives import C, MosType
from pydantic import StrictInt


def fingers(units: int, kind: str, nf: int | None = None) -> tuple[int, int | None]:
    """Total width and finger count for a device of ``units`` unit widths.

    The active PDK (``hdl21.pdk.default()``) may give ``MOS_FINGER_UNITS``, the widest finger
    its row cells fit per kind ("analog", "logic_n", "logic_p"), in its own unit widths. Then
    the device takes the fewest fingers that fit unless ``nf`` is given (analog devices: an
    even count, so both ends of the diffusion are one terminal, raised by up to three steps
    where that rounds closer), and every finger is the nearest whole number of units. Without those limits the device stays one finger at full size.
    ``MOS_FINGER_MIN_UNITS`` (optional) is the narrowest analog finger the PDK can contact: an even
    count that would go below it gives way to fewer fingers, and a narrower device is widened to it.
    """

    pdk = h.pdk.default()
    limits = getattr(pdk, "MOS_FINGER_UNITS", None)
    if not limits:
        return units, nf
    if kind == "analog":  # an analog device narrower than one contacted finger takes that finger
        units = max(units, getattr(pdk, "MOS_FINGER_MIN_UNITS", 1))
    rounded = lambda count: max(1, int(units / count + 0.5)) * count
    if nf is None:
        nf = ceil(units / limits[kind])
        if kind == "analog":
            # the fewest even finger counts that fit, the one closest to the requested width
            low = getattr(pdk, "MOS_FINGER_MIN_UNITS", 1)
            nf += nf % 2
            counts = [c for c in range(nf, nf + 8, 2) if rounded(c) // c >= low] or [max(1, units // low)]
            nf = min(counts, key=lambda count: (abs(rounded(count) - units), count))
    return rounded(nf), nf


# The PDK whose unit sizes analog devices keep physically in another PDK (write_netlist's
# ``constant_from``); None keeps them relative, in the active PDK's own units.
CONSTANT_FROM = None


def core_unit(pdk) -> tuple[float, float]:
    """A PDK's unit width and minimum length (m): its core devices', the shortest default size."""

    return min(((float(w), float(l)) for w, l in pdk.default_xtor_size.values()), key=lambda size: size[1])


def mos(*, tp, vth, w, l):
    """An analog MOS, fingered to the active PDK's row cells.

    With ``CONSTANT_FROM`` set, ``w`` and ``l`` are that PDK's units made physical: the width
    to the nearest whole unit of the active PDK, the length kept as drawn, except at one or two
    minimum lengths, which stay that multiple of the active PDK's minimum.
    """

    if CONSTANT_FROM is not None:
        (w_ref, l_ref), (w_unit, _) = core_unit(CONSTANT_FROM), core_unit(h.pdk.default())
        w = max(1, round(w * w_ref / w_unit))
        if l > 2:
            l = h.Prefixed.new(round(l * l_ref * 1e9), h.Prefix.NANO)
    w, nf = fingers(w, "analog")
    return h.Mos(tp=tp, vth=vth, w=w, l=l, nf=nf)


# A MOS capacitor's length in minimum lengths: long enough that its gate area, not its overlap and
# fringe, holds the charge, short enough for every PDK's models
CAP_L = 8


def mos_cap(c_ff: float, *, tp, vth):
    """A MOS capacitor of about ``c_ff`` fF: the gate is the capacitor's node and source, drain and
    bulk go to the rail it is measured against, so it must sit in strong inversion over the node's
    swing (the node starting a supply away from that rail). Its width from the active PDK's gate
    capacitance per unit device (``MOS_CAP_FF``; without one, as if a unit held 0.1 fF), at
    ``CAP_L``, fingered as any analog device."""

    density = getattr(h.pdk.default(), "MOS_CAP_FF", None) or {"n": 0.1, "p": 0.1}
    units = max(1, round(c_ff / (density["n" if tp == MosType.NMOS else "p"] * CAP_L)))
    return mos(tp=tp, vth=vth, w=units, l=CAP_L)


def logic_pair(n_units: int, p_units: int) -> tuple[tuple[int, int | None], tuple[int, int | None]]:
    """NMOS and PMOS sharing a gate in a logic cell: one finger count that fits both."""

    limits = getattr(h.pdk.default(), "MOS_FINGER_UNITS", None)
    nf = max(ceil(n_units / limits["logic_n"]), ceil(p_units / limits["logic_p"])) if limits else None
    return fingers(n_units, "logic_n", nf), fingers(p_units, "logic_p", nf)


@h.paramclass
class LogicCellParams:
    drive = h.Param(dtype=StrictInt, desc="Standard-cell drive strength", default=1)


@h.bundle
class InverterPorts:
    A = h.Input()
    Y = h.Output()
    VDD = h.Power(direction=h.PortDir.INOUT)
    VSS = h.Ground(direction=h.PortDir.INOUT)


@h.bundle
class Gate2Ports:
    A, B = h.Input(), h.Input()
    Y = h.Output()
    VDD = h.Power(direction=h.PortDir.INOUT)
    VSS = h.Ground(direction=h.PortDir.INOUT)


# PDK compile passes replace these with library cells (pdk/<tech>/stdcells.py).
Inverter, Nor2, Nand2 = (
    h.ExternalModule(
        domain="generic",
        name=name,
        paramtype=LogicCellParams,
        port_list=list(ports.signals.values()),
        desc=f"{name} standard cell; requires PDK compile substitution",
    )
    for name, ports in (("inverter", InverterPorts), ("nor2", Gate2Ports), ("nand2", Gate2Ports))
)


def instance_lines(module: h.Module) -> list[str]:
    """A compiled module's instances as the flat SPICE lines ``write_netlist`` writes: a capacitor's
    value, a MOS's total width and finger count, a logic cell's wrapper as its library cell; a custom
    child cell (a module of its own devices) as its own lines, each name followed by the child's
    (``Mdiff_p@Xcomp``: unique, and still a MOS line by its first letter)."""

    nm = lambda value: round(float(value) * 1e9)
    lines = []
    for name, inst in module.instances.items():
        conns = {port: sig.name for port, sig in inst.conns.items()}
        call = inst.of
        if isinstance(call, h.PrimitiveCall) and call.prim is C:
            lines.append(f"{name} {conns['p']} {conns['n']} {float(call.params.c) * 1e15:g}f")
        elif isinstance(call, h.ExternalModuleCall):
            q = call.params
            # the PDK's name for the finger count; none where m carries the fingers (LF150, w per finger)
            fingers = next((f" {k}={int(getattr(q, k))}" for k in ("nf", "ng") if hasattr(q, k)), "")
            lines.append(
                f"{name} {conns['d']} {conns['g']} {conns['s']} {conns['b']} {call.module.name} "
                f"w={nm(q.w)}n l={nm(q.l)}n{fingers} m={int(q.m)}"
            )
        elif isinstance(call, h.PrimitiveCall):
            continue  # an ideal source or element of a testbench: no device of a layout
        elif len(call.instances) == 1 and isinstance(next(iter(call.instances.values())).of, h.ExternalModuleCall):
            # a logic cell's wrapper around one library cell
            (cell,) = call.instances.values()
            outer = {port.name: conns[port.name] for port in call.ports.values()}
            pins = [outer[sig.name] for sig in (cell.conns[p.name] for p in cell.of.module.port_list)]
            lines.append(f"{name} {' '.join(pins)} {cell.of.module.name}")
        else:  # a custom child cell
            for line in instance_lines(call):
                first, rest = line.split(" ", 1)
                lines.append(f"{first}@{name} {rest}")
    return lines


def write_netlist(params, path: Path, pdk, constant_from=None, *, generator, nets) -> Path:
    """The block of ``generator`` (``params``, its port bundle ``nets``) after ``pdk``'s compile,
    as one flat SPICE subcircuit named after ``path``.

    Elaborated with ``pdk`` active, so every device is fingered to its row cells and sized in
    whole unit widths; simulation compiles the same way. MOS lines give the total width and
    the finger count (``w`` is the total, as in the foundry models); logic cells are written as
    their library cells. ``constant_from`` (a PDK) keeps the analog devices at that PDK's
    physical widths and lengths (``mos``) instead of the same unit counts.
    """

    global CONSTANT_FROM
    path = Path(path)
    manager = import_module("hdl21.pdk.pdk")._mgr  # hdl21 offers no public way back to "no default set"
    previous = manager.default
    h.pdk.set_default(pdk)
    CONSTANT_FROM = constant_from
    try:
        generator.Cache.reset()
        module = generator(params)
        h.pdk.compile(module, pdk)
    finally:
        generator.Cache.reset()
        manager.default = previous
        CONSTANT_FROM = None
    ports = [name for name, net in nets.signals.items() if net.vis == h.Visibility.PORT]
    lines = [f".subckt {path.stem} {' '.join(ports)}", *instance_lines(module), f".ends {path.stem}"]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n")
    return path
