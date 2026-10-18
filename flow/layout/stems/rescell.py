"""Unsilicided poly resistors as row cells, drawn from the PDK's ``tech`` values.

A poly resistor is a front-end device like a transistor, so it is a row cell like ``rowcell``'s:
one standard-cell row tall (``H``), both supply rails with their taps, implant bands and the
N-well band at the VDD rail (``rowcell.rails``, as an NMOS cell without its device implant and VT
layers), so it abuts transistor and standard cells along a row. In the cell frame R0 (VSS at the
bottom), the resistor runs along the row at mid height:

    x  head: poly enclosing a column of contacts, an M1 pad, a via and an M2 pin (PLUS / MINUS)
       body: length l, where the silicide block and the PDK's resistor markers cover the poly
       head: likewise, mirrored

The body's width ``w`` is across the row. The PDK's resistor is ``tech.RES``:

    model      its device (the LVS and simulation model name)
    sheet      sheet resistance of the body (ohm / square)
    dw         the model's width reduction (nm)
    end        both ends' resistance times the width (ohm um)
    width      narrowest body (nm)
    length     shortest body (nm, optional)
    markers    {layer: (along, across)}: the silicide block and markers over the body, past its
               ends along the length and past the poly across it; the silicide block is first
    implant    (layer, enclosure): the body's implant over all of the poly, joined to the rail
               band of its type
    implant_space  its space to the other type's rail band (optional)
    well_space the body's space to the N-well band (optional)
    co_space   silicide block (the body's end) to the head's contacts
    co_enc     poly past the head's contacts
    min_area   {layer: nm2}: a marker's smallest area, which lengthens a short body (optional)
    cdl        the LVS source line of one resistor, formatted with name, plus, minus, bulk, r
               (ohm), w and l (um) (optional: where LVS of it is verified), and cdl_stub, a
               subcircuit the source must define for it

``res_value`` is the resistance the model gives a drawn body.
"""

from __future__ import annotations

import rowcell
import tech
from rowcell import CO, CO_PITCH, M1_CO_END, M1_HW, M2_HW, M2_MIN_LEN, MFG_GRID, RAIL, V1_H, XPITCH, Cell, H
from tech import PITCH


def _up(value: int, grid: int) -> int:
    return -(-value // grid) * grid


def res_value(w: int, l: int) -> float:
    """The model's resistance (ohm) of a body ``w`` wide and ``l`` long (nm)."""

    res = tech.RES
    width_um = (w - res["dw"]) / 1000
    return res["sheet"] * l / (w - res["dw"]) + res["end"] / width_um


def res_length(w: int, l: int) -> int:
    """The body length drawn for a requested one: on grid, and long enough that every marker
    meets its smallest area."""

    res = tech.RES
    l = _up(max(l, res.get("length", 0)), MFG_GRID)
    for layer, area in res.get("min_area", {}).items():
        along, across = res["markers"][layer]
        l = max(l, _up(-(-area // (w + 2 * across)) - 2 * along, MFG_GRID))
    return l


def res(w: int, l: int, plus: str = "PLUS", minus: str = "MINUS", vss: str = "vss", vdd: str = "vdd") -> Cell:
    """One resistor row cell: a body ``w`` wide (across the row) and ``l`` long (nm, lengthened to
    its markers' area), PLUS on the left head, MINUS on the right one, both M2 pins on the track
    nearest the row's middle."""

    spec = tech.RES
    if w < spec["width"]:
        raise ValueError(f"a poly resistor is at least {spec['width']} nm wide")
    w = _up(w, 2 * MFG_GRID)
    l = res_length(w, l)
    co_enc, co_space = spec["co_enc"], spec["co_space"]
    implant, imp_enc = spec["implant"]
    # the heads: a contact column wide enough for the body, or a dog bone for a narrow one
    head = max(w, CO + 2 * co_enc)
    contacts = max(1, (head - 2 * co_enc - CO) // CO_PITCH + 1)
    # the implant joins the rail band of its own type and keeps implant_space from the other's,
    # the body keeps well_space from the N-well band; the body sits nearest the row's middle that
    # allows that, both pins on the M2 track nearest it
    vss_band, vdd_band = rowcell.RAIL_IMPLANTS
    reach = head // 2 + imp_enc
    space = spec.get("implant_space", 0)
    low = -(10**9) if implant == vss_band else rowcell.PP_TAP + space + reach
    high = 10**9 if implant == vdd_band else rowcell.NP_TAP - space - reach
    if "well_space" in spec:
        high = min(high, rowcell.NW_N - spec["well_space"] - w // 2)
    if low > high:
        raise ValueError(f"a {w} nm resistor does not fit between the rail implants and the well")
    yc = min(max(H // 2 // MFG_GRID * MFG_GRID, _up(low, MFG_GRID)), high // MFG_GRID * MFG_GRID)
    track = round(yc / PITCH) * PITCH
    imp_y0 = -rowcell.PP_TAP if implant == vss_band else yc - reach
    imp_y1 = rowcell.NP_TAP if implant == vdd_band else yc + reach
    # along the row: the cell edge, half a poly space, the head, the body, the head
    edge = _up(max(imp_enc, tech.RULES.get("PO", {}).get("space", 0) // 2), MFG_GRID)
    head_len = co_enc + CO + co_space
    width = _up(2 * edge + 2 * head_len + l, XPITCH)
    x0 = (width - (2 * head_len + l)) // 2  # the poly's left end, the resistor centred in the cell
    xb0, xb1 = x0 + head_len, x0 + head_len + l
    x1 = xb1 + head_len
    cell = Cell(f"res_w{w}_l{l}", width)
    rowcell.rails(cell, width, "n", vss, vdd)
    # a resistor has no device implant or VT layers: drop those rails() draws over the device band
    band = rowcell.DEV_IMP["n"]
    cell.rects = [
        r for r in cell.rects if r.layer not in rowcell.VT["n"] and not (r.layer == "NP" and (r.y0, r.y1) == band)
    ]
    # the poly: body and heads
    cell.add("PO", xb0, yc - w // 2, xb1, yc + w // 2)
    for hx0, hx1 in ((x0, xb0), (xb1, x1)):
        cell.add("PO", hx0, yc - head // 2, hx1, yc + head // 2)
    cell.add(implant, x0 - imp_enc, imp_y0, x1 + imp_enc, imp_y1)
    for layer, (along, across) in spec["markers"].items():
        cell.add(layer, xb0 - along, yc - w // 2 - across, xb1 + along, yc + w // 2 + across)
    # the heads' contacts, M1 pads, vias and M2 pins
    span = (contacts - 1) * CO_PITCH
    for net, cx in ((plus, x0 + co_enc + CO // 2), (minus, x1 - co_enc - CO // 2)):
        for k in range(contacts):
            cy = yc - span // 2 + k * CO_PITCH
            cell.add("CO", cx - CO // 2, cy - CO // 2, cx + CO // 2, cy + CO // 2, net)
        # the M1 pad: over the contacts and the via on the pins' track, at least its minimum length
        pad0 = min(yc - span // 2 - CO // 2, track - V1_H) - M1_CO_END
        pad1 = max(yc + span // 2 + CO // 2, track + V1_H) + M1_CO_END
        short = rowcell.M1_MIN_LEN - (pad1 - pad0)
        if short > 0:
            pad0, pad1 = pad0 - short // 2, pad1 + short - short // 2
        pad0, pad1 = pad0 // MFG_GRID * MFG_GRID, _up(pad1, MFG_GRID)
        if pad1 > H - RAIL - rowcell.M1_SPACE or pad0 < RAIL + rowcell.M1_SPACE:
            raise ValueError(f"a {w} nm resistor's contact pads do not fit between the rails")
        cell.add("M1", cx - M1_HW, pad0, cx + M1_HW, pad1, net)
        cell.add("V1", cx - V1_H, track - V1_H, cx + V1_H, track + V1_H, net)
        cell.add("M2", cx - M2_MIN_LEN // 2, track - M2_HW, cx + M2_MIN_LEN // 2, track + M2_HW, net, "pin")
    return cell


def res_gds(path: str, w: int, l: int) -> dict:
    """Write one resistor row cell to a GDS file, its pins labelled as the row cells' (``PIN_TEXT``); returns
    its name, drawn length and modelled resistance."""

    from klayout import db as kdb

    cell = res(w, l)
    layout = kdb.Layout()
    layout.dbu = tech.DBU
    kc = rowcell.to_klayout(cell, layout, kdb)
    for net, rects in cell.pins.items():
        for r in rects:
            layer = tech.PIN_TEXT.get(r.layer) or tech.LAYERS.get(f"{r.layer}.PIN") or tech.LAYERS[r.layer]
            kc.shapes(layout.layer(*layer)).insert(kdb.Text(net, kdb.Trans((r.x0 + r.x1) // 2, (r.y0 + r.y1) // 2)))
    layout.write(path)
    drawn_w, drawn_l = (int(part[1:]) for part in cell.name.split("_")[1:])
    return {"top": cell.name, "w": drawn_w, "l": drawn_l, "r": res_value(drawn_w, drawn_l)}
