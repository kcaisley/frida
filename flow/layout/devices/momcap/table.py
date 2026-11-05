"""A PDK's momcap table (``characterize.py``) and its lookups: the finger lengths a capacitance
takes, and the capacitances a unit's fingers give."""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import cache
from pathlib import Path
from typing import Any

from flow.layout.devices.momcap.geometry import MomStyle

from ..device import FloorError, read_table
from .geometry import MomcapGeometry


@dataclass(frozen=True)
class MomcapTable:
    """A PDK's MOM units: per style and metal count, each terminal pair's fit and the lengths a
    finger can be drawn at."""

    pdk: str
    styles: dict[str, dict[str, Any]]

    def _entry(self, style: MomStyle, layers: int) -> dict[str, Any]:
        return self.styles[style.name][str(layers)]

    def capacitances(self, geometry: MomcapGeometry) -> dict[tuple[str, str], float]:
        """Every terminal pair's capacitance (F) of a unit as drawn."""
        entry = self._entry(geometry.style, geometry.layers)
        main, diff = geometry.length_nm / 1000, geometry.diff_length_nm / 1000
        values = {}
        for pair, fit in entry["pairs"].items():
            if geometry.style is MomStyle.DIFFERENCE:
                ff = fit["main_ff_per_um"] * main + fit["diff_ff_per_um"] * diff + fit["ff"]
            else:
                ff = fit["ff_per_um"] * main + fit["ff"]
            values[tuple(pair.split("-"))] = max(0.0, ff) * 1e-15
        return values

    def _strip_at(self, layers: int, net_f: float, whole_f: float) -> tuple[int, int, int]:
        """A strip's fingers on ``layers`` metals, and the shortest a finger can be there."""
        entry = self._entry(MomStyle.DIFFERENCE, layers)
        grid, least = entry["grid_nm"], entry["min_length_nm"]
        main, diff = entry["pairs"]["MAIN-TOP"], entry["pairs"]["DIFF-TOP"]
        # net(Lm, Ld) = p Lm + q Ld + r (um, fF)
        p = main["main_ff_per_um"] - diff["main_ff_per_um"]
        q = main["diff_ff_per_um"] - diff["diff_ff_per_um"]
        r = main["ff"] - diff["ff"]
        stub = least / 1000
        whole = (whole_f * 1e15 - q * stub - r) / p
        total = round((whole + stub) * 1000 / grid) * grid / 1000
        length = (net_f * 1e15 - q * total - r) / (p - q)
        main_nm = round(length * 1000 / grid) * grid
        return main_nm, round(total * 1000) - main_nm, least

    def strip(self, layers: int, net_f: float, whole_f: float) -> tuple[MomcapGeometry, FloorError | None]:
        """The difference strip of net ``net_f`` (main less difference) in a strip as long as the
        whole one, ``whole_f`` at its longest with its difference finger a minimum-length stub: on
        ``layers`` metals, or on fewer where a finger would be shorter than the PDK draws; where
        none can, the shortest fingers on one metal, and its ``FloorError``."""
        for metals in range(layers, 0, -1):
            main_nm, diff_nm, least = self._strip_at(metals, net_f, whole_f)
            if min(main_nm, diff_nm) >= least:
                return MomcapGeometry(MomStyle.DIFFERENCE, metals, main_nm, diff_nm), None
        main_nm, diff_nm, least = self._strip_at(1, net_f, whole_f)
        floor = FloorError(
            f"{self.pdk}: no strip of {net_f * 1e15:.3f} fF in {whole_f * 1e15:.3f} fF on 1 to {layers} metals; "
            f"its fingers drawn no shorter than {least} nm"
        )
        return MomcapGeometry(MomStyle.DIFFERENCE, 1, max(least, main_nm), max(least, diff_nm)), floor

    def smallest_unit(self, layers: int) -> float:
        """The smallest ring unit on ``layers`` metals (F): its inner finger at its shortest."""
        entry = self._entry(MomStyle.RING, layers)
        fit = entry["pairs"]["INNER-TOP"]
        return (fit["ff_per_um"] * entry["min_length_nm"] / 1000 + fit["ff"]) * 1e-15

    def unit(self, layers: int, c_f: float, *, exact: bool = False) -> tuple[MomcapGeometry, FloorError | None]:
        """The ring unit of ``c_f`` between its top plate and its inner finger: on ``layers``
        metals, or on fewer where ``c_f`` is below the smallest unit they draw; below the smallest
        on one metal, that smallest unit, and its ``FloorError``. ``exact``: on ``layers`` metals
        alone (an array's units share their stack), below its smallest that smallest and its
        ``FloorError``."""
        if exact:
            entry = self._entry(MomStyle.RING, layers)
            grid, least = entry["grid_nm"], entry["min_length_nm"]
            fit = entry["pairs"]["INNER-TOP"]
            length_nm = round((c_f * 1e15 - fit["ff"]) / fit["ff_per_um"] * 1000 / grid) * grid
            if length_nm >= least:
                return MomcapGeometry(MomStyle.RING, layers, length_nm), None
            floor = FloorError(
                f"{self.pdk}: no ring unit of {c_f * 1e15:.3f} fF on {layers} metals; the smallest, "
                f"{self.smallest_unit(layers) * 1e15:.3f} fF, drawn instead"
            )
            return MomcapGeometry(MomStyle.RING, layers, least), floor
        for metals in range(layers, 0, -1):
            entry = self._entry(MomStyle.RING, metals)
            grid, least = entry["grid_nm"], entry["min_length_nm"]
            fit = entry["pairs"]["INNER-TOP"]
            length_nm = round((c_f * 1e15 - fit["ff"]) / fit["ff_per_um"] * 1000 / grid) * grid
            if length_nm >= least:
                return MomcapGeometry(MomStyle.RING, metals, length_nm), None
        floor = FloorError(
            f"{self.pdk}: no ring unit of {c_f * 1e15:.3f} fF; the smallest, "
            f"{self.smallest_unit(1) * 1e15:.3f} fF on 1 metal, drawn instead"
        )
        return MomcapGeometry(MomStyle.RING, 1, self._entry(MomStyle.RING, 1)["min_length_nm"]), floor


@cache
def momcap_table(pdk: str) -> MomcapTable:
    """``pdk``'s momcap table."""
    return MomcapTable(pdk=pdk, styles=read_table("momcap", pdk)["styles"])


def stacked_over_rows(pdk: str, layers: int = 3) -> tuple[int, int] | None:
    """The slice of the metal stack (lowest, highest metal) an ``layers``-metal unit occupies, its
    shield to its top finger metal, where it lies above the metals the rows route on (ALIGN's
    ``top_signal_routing_layer``): a unit that may sit over transistor rows (``Stackup``); None where
    its shield meets their routing, and the rows go beside it."""
    root = Path(__file__).resolve().parents[4] / "pdk" / pdk / "layout"
    metals = _mom_layers(pdk)[-layers:]
    routing = json.loads((root / "layers.json").read_text())["design_info"]["top_signal_routing_layer"]
    shield = metals[0] - 1
    return (shield, metals[-1]) if shield > int(routing.removeprefix("M")) else None


@cache
def _mom_layers(pdk: str) -> tuple[int, ...]:
    from importlib import import_module

    return tuple(import_module(f"pdk.{pdk}.layout.tech").MOM_LAYERS)
