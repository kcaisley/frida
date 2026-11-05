"""A PDK's polyres table (``characterize.py``) and its lookups: the length a resistance takes at the
narrowest width the kit draws, and the resistance a body gives."""

from __future__ import annotations

from dataclasses import dataclass
from functools import cache

from ..device import read_table
from .geometry import PolyResGeometry


@dataclass(frozen=True)
class PolyResTable:
    """A kit's poly resistor: R = (sheet L + end) / (W - dW), on its grid, at least its width."""

    pdk: str
    sheet_ohm: float
    end_ohm_um: float
    dw_nm: float
    width_nm: int
    grid_nm: int

    def resistance(self, geometry: PolyResGeometry) -> float:
        """A body's resistance (ohm)."""
        effective_um = (geometry.w_nm - self.dw_nm) / 1000
        return (self.sheet_ohm * geometry.l_nm / 1000 + self.end_ohm_um) / effective_um

    def length(self, r_ohm: float, w_nm: int | None = None) -> PolyResGeometry:
        """The body of ``r_ohm`` at width ``w_nm`` (the narrowest the kit draws by default): its
        length on the grid, at least one grid step."""
        w_nm = w_nm or self.width_nm
        effective_um = (w_nm - self.dw_nm) / 1000
        l_um = (r_ohm * effective_um - self.end_ohm_um) / self.sheet_ohm
        return PolyResGeometry(w_nm, max(self.grid_nm, round(l_um * 1000 / self.grid_nm) * self.grid_nm))


@cache
def polyres_table(pdk: str) -> PolyResTable:
    """``pdk``'s polyres table."""
    data = read_table("polyres", pdk)
    return PolyResTable(
        pdk=pdk,
        sheet_ohm=data["sheet_ohm"],
        end_ohm_um=data["end_ohm_um"],
        dw_nm=data["dw_nm"],
        width_nm=data["width_nm"],
        grid_nm=data["grid_nm"],
    )
