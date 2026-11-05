"""A PDK's mosfet table (``characterize.py``) and its lookups: the width a drive resistance takes."""

from __future__ import annotations

import math
from dataclasses import dataclass
from functools import cache

from hdl21.primitives import MosType, MosVth

from ..device import read_table
from .geometry import MosGeometry, flavor


@dataclass(frozen=True)
class MosfetTable:
    """A PDK's transistors, per unit width at the minimum length, typical corner."""

    pdk: str
    vdd_v: float
    switching_ohm: dict[str, float]
    triode_ohm: dict[str, float]

    def width(self, tp: MosType, vth: MosVth, r_ohm: float) -> MosGeometry:
        """The narrowest device of a whole number of unit widths whose switching resistance is at
        most ``r_ohm``."""
        units = max(1, math.ceil(self.switching_ohm[flavor(tp, vth)] / r_ohm))
        return MosGeometry(tp, vth, units)

    def resistance(self, geometry: MosGeometry) -> float:
        """A device's switching resistance."""
        return self.switching_ohm[geometry.key] / geometry.units


@cache
def mosfet_table(pdk: str) -> MosfetTable:
    """``pdk``'s mosfet table."""
    data = read_table("mosfet", pdk)
    devices = data["devices"]
    return MosfetTable(
        pdk=pdk,
        vdd_v=data["vdd_v"],
        switching_ohm={key: value["switching_ohm"] for key, value in devices.items()},
        triode_ohm={key: value["triode_ohm"] for key, value in devices.items()},
    )
