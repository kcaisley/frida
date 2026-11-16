"""The cells post.py fills a row's empty sites with: decoupling capacitors where one fits, plain
filler (``netcells.filler``'s rails, taps and well band, no device) where none does.

A decap is the MOS capacitor of the PDK's moscap table (``flow/layout/devices/moscap``,
``pdk/<pdk>/devices/moscap.json``): a row cell (``rowcell.mos_row``) of one transistor at the
table's gate length (``cap_l`` minimum lengths), its fingers as wide as the row's band of its type
lets them (``OD_LIMIT``, at most ``W_MAX``), its source, drain and bulk on its own rail and its gate
strapped in M1 into the other (``mos_array``'s ``ties``): an NMOS to VSS with its gate on VDD, a
PMOS to VDD with its gate on VSS, each in its own half of the row as the row cells have them. It
draws on M1 alone (its rails, strips, gate pads and strap), so nothing a router drew above M1
meets it. Its capacitance is the table's, in inversion, per um^2 of gate (the low threshold
flavour, the row cells' ``MODELS``); the LVS source gets it as the PDK's deck reads a MOS
(``pdk/<pdk>/netlist/lvs.py``'s ``mos``).

Run bound to a PDK (flow/layout/pdkproc.py).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import cache
from importlib import import_module
from pathlib import Path

import rowcell
import tech as _tech
from tech import MFG_GRID, MODELS, OD_LIMIT, W_MAX, XPITCH

KIT = Path(_tech.__file__).resolve().parents[1].name  # pdk/<kit>/layout/tech.py
RAIL = {"n": "vss", "p": "vdd"}  # a decap's own rail (source, drain, bulk); its gate on the other
MOST_FINGERS = 64  # one decap's fingers at most (a wider gap takes several)


@cache
def table() -> dict:
    """The PDK's moscap table."""
    return json.loads((Path(_tech.__file__).resolve().parents[1] / "devices" / "moscap.json").read_text())


def gate_length() -> int:
    """A decap's gate length (nm): the table's, ``cap_l`` minimum lengths."""
    return round(table()["unit"]["l_m"] * 1e9) * int(table()["cap_l"])


def finger_width(pol: str) -> int:
    """A decap finger's width (nm): the row band of its type (``OD_LIMIT``), at most ``W_MAX``."""
    lo, hi = OD_LIMIT[pol]
    return min(W_MAX, hi - lo) // MFG_GRID * MFG_GRID


@cache
def decap(pol: str, nf: int) -> rowcell.Cell:
    """A decap of ``nf`` fingers, NMOS (``pol`` "n") or PMOS ("p"), as a row cell on the cell grid."""
    rail, far = RAIL[pol], RAIL["p" if pol == "n" else "n"]
    dev = rowcell.Dev("M0", gate_length(), finger_width(pol), nf, d=rail, g=far, s=rail)
    return rowcell.mos_row(f"decap_{pol}{nf}", pol, [dev], XPITCH)


def width(pol: str, nf: int) -> int:
    """A decap's cell width (nm)."""
    return decap(pol, nf).width


def fingers(pol: str, room: int) -> int:
    """The most fingers (up to ``MOST_FINGERS``) of a decap no wider than ``room`` (nm); 0 where
    not even one fits."""
    if width(pol, 1) > room:
        return 0
    lo, hi = 1, MOST_FINGERS
    while lo < hi:  # the widest that fits (a cell's width grows with its fingers)
        mid = (lo + hi + 1) // 2
        lo, hi = (mid, hi) if width(pol, mid) <= room else (lo, mid - 1)
    return lo


def pack(pol: str, room: int) -> list[int]:
    """Decaps (their fingers) side by side in ``room`` (nm): the widest that fits, again in what is
    left, until none does."""
    out = []
    while (nf := fingers(pol, room)) > 0:
        out.append(nf)
        room -= width(pol, nf)
    return out


def capacitance_ff(pol: str, nf: int) -> float:
    """A decap's capacitance (fF) in inversion, the table's per um^2 of its gate."""
    key = f"{'NMOS' if pol == 'n' else 'PMOS'}/LOW"
    devices = table()["devices"]
    per_um2 = devices.get(key, devices[key.replace("LOW", "STD")])["ff_per_um2"]
    return per_um2 * gate_um2(pol, nf)


def gate_um2(pol: str, nf: int) -> float:
    """A decap's gate area (um^2)."""
    return nf * finger_width(pol) * gate_length() * 1e-6


@dataclass(frozen=True)
class Placed:
    """A decap drawn in a layout: its type, fingers and lower-left corner (nm), and its row."""

    pol: str
    nf: int
    x: int
    y: int
    row: int


def lvs_line(name: str, pol: str, nf: int) -> str:
    """A decap as the LVS source's MOS line (drain, gate, source, bulk): the PDK's deck device
    (``pdk/<kit>/netlist/lvs.py``'s ``mos``) of its total width and length, else the row cells' own
    model (``MODELS``) with ``w`` and ``l``."""
    rail, far = RAIL[pol], RAIL["p" if pol == "n" else "n"]
    w_m, l_m = nf * finger_width(pol) * 1e-9, gate_length() * 1e-9
    rule = getattr(import_module(f"pdk.{KIT}.netlist.lvs"), "mos", None)
    found = rule(MODELS[pol], w_m, l_m) if rule else None
    model, values = found if found is not None else (MODELS[pol], {"w": w_m, "l": l_m})
    params = " ".join(f"{k}={round(v * 1e6, 6):g}u" for k, v in values.items())
    return f"{name} {rail} {far} {rail} {rail} {model} {params}"
