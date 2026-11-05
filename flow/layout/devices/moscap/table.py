"""A PDK's moscap table (``characterize.py``) and its lookup: the units a capacitance takes."""

from __future__ import annotations

from dataclasses import dataclass
from functools import cache

from hdl21.primitives import MosType, MosVth

from ..device import read_table
from .geometry import CAP_L, MosCapGeometry


@dataclass(frozen=True)
class MosCapTable:
    """A PDK's MOS capacitors in inversion, per unit device at ``CAP_L``, typical corner."""

    pdk: str
    ff_per_unit: dict[str, float]
    ff_per_um2: dict[str, float]

    def per_unit_ff(self, tp: MosType, vth: MosVth = MosVth.LOW) -> float:
        """One unit device's capacitance (fF) at ``CAP_L``, in inversion, of a flavor; a flavor
        the table lacks, the standard one's."""
        return self.ff_per_unit.get(f"{tp.name}/{vth.name}", self.ff_per_unit[f"{tp.name}/STD"])

    def units(self, tp: MosType, vth: MosVth, c_ff: float) -> MosCapGeometry:
        """The nearest whole number of unit devices (at least one) to ``c_ff``."""
        return MosCapGeometry(tp, vth, max(1, round(c_ff / self.per_unit_ff(tp, vth))))


@cache
def moscap_table(pdk: str) -> MosCapTable:
    """``pdk``'s moscap table."""
    devices = read_table("moscap", pdk)["devices"]
    return MosCapTable(
        pdk=pdk,
        ff_per_unit={key: value["ff_per_unit"] for key, value in devices.items()},
        ff_per_um2={key: value["ff_per_um2"] for key, value in devices.items()},
    )


def density(pdk: str | None, vth: MosVth = MosVth.LOW) -> dict[str, float]:
    """A MOS gate's capacitance (fF) per unit width and minimum length in inversion, by type
    (``n``, ``p``), of a flavor (the low threshold the row cells draw by default): ``pdk``'s
    measured (its table, at ``CAP_L``), or 0.1 fF without a PDK (a netlist's structure alone)."""
    if pdk is None:
        return {"n": 0.1, "p": 0.1}
    table = moscap_table(pdk)
    return {
        "n": table.per_unit_ff(MosType.NMOS, vth) / CAP_L,
        "p": table.per_unit_ff(MosType.PMOS, vth) / CAP_L,
    }
