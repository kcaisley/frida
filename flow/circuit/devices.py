"""What every block's generator builds from besides its devices (``flow.layout.devices``: ``mos``,
``mos_cap``): how a device is fingered to the PDK's row cells (``fingers``), the generic logic cells a PDK maps to its library
(``Inverter``, ``Nor2``, ``Nand2``). A block's netlists are hdl21's and vlsir's
(``flow.circuit.netlists``)."""

from math import ceil

import hdl21 as h
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


def core_unit(pdk) -> tuple[float, float]:
    """A PDK's unit width and minimum length (m): its core devices', the shortest default size."""

    return min(((float(w), float(l)) for w, l in pdk.default_xtor_size.values()), key=lambda size: size[1])


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
