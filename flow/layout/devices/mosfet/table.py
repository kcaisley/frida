"""A PDK's mosfet table (``characterize.py``) and its lookups: the width a drive resistance takes."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
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
    fo4_delay_s: dict[str, float] = field(default_factory=dict)
    # an inverter's input capacitance per unit width of its gates (F), by threshold
    input_f_per_unit: dict[str, float] = field(default_factory=dict)

    def width(self, tp: MosType, vth: MosVth, r_ohm: float, *, on: bool = False) -> MosGeometry:
        """The narrowest device of a whole number of unit widths whose switching resistance (``on``:
        its on-resistance, the triode resistance) is at most ``r_ohm``."""
        per_unit = (self.triode_ohm if on else self.switching_ohm)[flavor(tp, vth)]
        return MosGeometry(tp, vth, max(1, math.ceil(per_unit / r_ohm)))

    def resistance(self, geometry: MosGeometry, *, on: bool = False) -> float:
        """A device's switching resistance (``on``: its on-resistance)."""
        return (self.triode_ohm if on else self.switching_ohm)[geometry.key] / geometry.units

    def fo4(self, vth: MosVth) -> float:
        """An inverter's delay at a fan-out of four (s) at threshold ``vth``."""
        return self.fo4_delay_s[vth.name]

    def input_f(self, vth: MosVth, units: float) -> float:
        """An inverter's input capacitance (F) at threshold ``vth``, its gates ``units`` unit widths
        wide in all (its NMOS's and its PMOS's): what it loads the node it senses with."""
        return self.input_f_per_unit[vth.name] * units


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
        fo4_delay_s=data.get("fo4_delay_s", {}),
        input_f_per_unit=data.get("input_f_per_unit", {}),
    )
