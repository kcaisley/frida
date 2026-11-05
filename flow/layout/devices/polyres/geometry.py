"""What a poly resistor is drawn as: the kit's unsilicided poly resistor at a body width and length
(nm), a row cell one standard-cell row tall (``flow/layout/rows/rescell.py``, ALIGN's ``ResUnit``)."""

from __future__ import annotations

from dataclasses import dataclass

# the kits with a poly resistor row cell (their tech.RES)
PDKS = ("tsmc65", "tsmc28", "tpsc65", "ihp130", "tower180", "lf150")


@dataclass(frozen=True)
class PolyResGeometry:
    """A resistor body ``w_nm`` across the row and ``l_nm`` along it."""

    w_nm: int
    l_nm: int
