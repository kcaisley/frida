"""Close the implants and wells around taps at the outer edge of a block of rows.

Inside a block, rows meet rail to rail and their tap implant and well bands continue
into the neighbouring row. At the block's outer edge nothing continues them: the
P+ taps need PP beyond them, the N+ taps NP and NWELL (the implant and well extensions). This
adds those extensions outside the block outline only, so nothing inside changes. Layers and
overhangs are the PDK's (``tech``); a PDK without a drawn N+ implant (NP None) gets only the well.

    seal(layout, top_cell, kdb)   # flat top cell
"""

from __future__ import annotations

from tech import IMP_OH, LAYERS, NW_OH

OD, PP, NP, NW = (LAYERS[k] for k in ("OD", "PP", "NP", "NW"))


def seal(layout, top, kdb, imp: int = IMP_OH, well: int = NW_OH, sides: str = "lrbt") -> None:
    """Full-length strips along the block's outline wherever taps reach it (no corner jogs)."""
    region = lambda ld: kdb.Region(top.begin_shapes_rec(layout.layer(*ld))).merged() if ld else kdb.Region()
    od, pp, np_, nw = region(OD), region(PP), region(NP), region(NW)
    ntap = (od & nw) - pp if NP is None else od & np_ & nw
    b = od.bbox()  # the rows' extent (metal pads may stick out of it)
    probes = {
        "l": kdb.Box(b.left - 1, b.bottom, b.left + 1, b.top),
        "r": kdb.Box(b.right - 1, b.bottom, b.right + 1, b.top),
        "b": kdb.Box(b.left, b.bottom - 1, b.right, b.bottom + 1),
        "t": kdb.Box(b.left, b.top - 1, b.right, b.top + 1),
    }

    def strip_box(side, d):  # the band just inside the side
        return {
            "l": kdb.Box(b.left, b.bottom, b.left + d, b.top),
            "r": kdb.Box(b.right - d, b.bottom, b.right, b.top),
            "b": kdb.Box(b.left - 200, b.bottom - 200, b.right + 200, b.bottom + d),
            "t": kdb.Box(b.left - 200, b.top - d, b.right + 200, b.top + 200),
        }[side]

    def strip(side, d, layer_region):
        # as long as the layer already is along that side (standard cells overhang the row ends),
        # so the edge stays straight (G.4)
        near = kdb.Region(strip_box(side, 400)) & layer_region  # the layer along this side only
        e = (near.bbox() if not near.is_empty() else b) + b if side in "bt" else b
        return {
            "l": kdb.Box(b.left - d, e.bottom, b.left, e.top),
            "r": kdb.Box(b.right, e.bottom, b.right + d, e.top),
            "b": kdb.Box(e.left, b.bottom - d, e.right, b.bottom),
            "t": kdb.Box(e.left, b.top, e.right, b.top + d),
        }[side]

    for side, probe in probes.items():
        if side not in sides:
            continue

        def touch(r, probe=probe):
            return not (r & kdb.Region(probe)).is_empty()

        if touch(od & pp):
            top.shapes(layout.layer(*PP)).insert(strip(side, imp, pp))
        if touch(ntap):
            if NP is not None:
                top.shapes(layout.layer(*NP)).insert(strip(side, imp, np_))
            top.shapes(layout.layer(*NW)).insert(strip(side, well, nw))
