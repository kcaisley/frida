"""Monolithic MOMCAP layout generator and inline sweep test."""

from __future__ import annotations

from importlib import import_module
from pathlib import Path

import klayout.db as kdb

from .dsl import (
    L,
    load_generic_layers,
)
from .image import gds_to_png_with_pdk_style
from .serialize import export_layout
from .tech import (
    load_dbu,
    load_rules_deck,
    remap_layers,
)


@L.paramclass
class MomcapParams:
    bottom_layer = L.Param(dtype=int, default=4)  # metal number: 4, 5, or 6
    top_layer = L.Param(dtype=int, default=6)  # metal number: 5, 6, or 7
    inner_width_mult = L.Param(dtype=int, default=1)
    inner_width_height = L.Param(dtype=int, default=1)
    spacing_multi = L.Param(dtype=int, default=1)
    outer_width_mult = L.Param(dtype=int, default=1)


@L.generator
def momcap(params: MomcapParams, tech_name: str) -> kdb.Layout:
    if params.inner_width_mult < 1:
        raise ValueError("inner_width_mult must be >= 1")
    if params.inner_width_height < 1:
        raise ValueError("inner_width_height must be >= 1")
    if params.spacing_multi < 1:
        raise ValueError("spacing_multi must be >= 1")
    if params.outer_width_mult < 1:
        raise ValueError("outer_width_mult must be >= 1")

    # ── Valid (bottom_layer, top_layer) combinations ──────────────
    #
    #   bottom │ top │ metals used        │ vias used
    #   ───────┼─────┼────────────────────┼───────────
    #   M4     │ M5  │ M4, M5             │ VIA4
    #   M4     │ M6  │ M4, M5, M6         │ VIA4, VIA5
    #   M5     │ M7  │ M5, M6, M7         │ VIA5, VIA6
    #   M6     │ M7  │ M6, M7             │ VIA6
    #
    valid_stacks = {(4, 5), (4, 6), (5, 7), (6, 7)}
    bot = params.bottom_layer
    top = params.top_layer
    if (bot, top) not in valid_stacks:
        raise ValueError(
            f"Invalid (bottom_layer={bot}, top_layer={top}). "
            f"Valid combinations: {sorted(valid_stacks)}"
        )

    # ── Load PDK data ──────────────────────────────────────────────
    R = load_rules_deck(tech_name)

    layout = kdb.Layout()
    layout.dbu = load_dbu(tech_name)
    G = load_generic_layers(layout)

    # ── Sizing rules from the top metal ───────────────────────────
    # The top metal is the most constrained (coarsest pitch), so we
    # use its rules for all dimensions.  The structure is vertically
    # symmetric across every layer in the stack.
    top_name = f"M{top}"
    top_R = getattr(R, top_name)

    if top_R.width is None:
        raise ValueError(f"Missing width rule on {top_name}")

    metal_w = top_R.width
    metal_sp = getattr(top_R.spacing, top_name, None)
    if metal_sp is None:
        metal_sp = metal_w
    metal_area = top_R.area if top_R.area is not None else metal_w * metal_w

    # ── Via rules (use the via just below the top metal) ──────────
    top_via_name = f"VIA{top - 1}"
    top_via_R = getattr(R, top_via_name)
    if top_via_R.width is None:
        raise ValueError(f"Missing width rule on {top_via_name}")
    via_w = top_via_R.width
    via_sp = getattr(top_via_R.spacing, top_via_name, None)
    if via_sp is None:
        via_sp = via_w

    # ── Derived geometry ──────────────────────────────────────────
    base_inner_h = max(1, (metal_area + metal_w - 1) // metal_w)
    inner_w = params.inner_width_mult * metal_w
    inner_h = params.inner_width_height * base_inner_h
    gap = params.spacing_multi * metal_sp
    ring_w = params.outer_width_mult * metal_w

    # Inner plate coordinates
    ix0, iy0 = 0, 0
    ix1, iy1 = inner_w, inner_h

    # Outer ring coordinates (outside edge / inside edge)
    rx0, ry0 = ix0 - gap - ring_w, iy0 - gap - ring_w
    rx1, ry1 = ix1 + gap + ring_w, iy1 + gap + ring_w
    rix0, riy0 = ix0 - gap, iy0 - gap
    rix1, riy1 = ix1 + gap, iy1 + gap

    # Pre-compute the boxes so they can be inserted on each layer
    inner_plate = kdb.Box(ix0, iy0, ix1, iy1)
    ring_bot = kdb.Box(rx0, ry0, rx1, riy0)
    ring_top = kdb.Box(rx0, riy1, rx1, ry1)
    ring_left = kdb.Box(rx0, riy0, rix0, riy1)
    ring_right = kdb.Box(rix1, riy0, rx1, riy1)

    cell = layout.create_cell("MOMCAP")

    # ── Helper: paint the inner plate + outer ring on a layer ─────
    def paint_plate_and_ring(layer: kdb.LayerInfo) -> None:
        cell.shapes(layer).insert(inner_plate)
        cell.shapes(layer).insert(ring_bot)
        cell.shapes(layer).insert(ring_top)
        cell.shapes(layer).insert(ring_left)
        cell.shapes(layer).insert(ring_right)

    # ── Helper: fill a via array on inner-plate edges ─────────────
    def fill_inner_vias(via_layer: kdb.LayerInfo, vw: int, vs: int) -> None:
        step = vw + vs
        for x in range(ix0, ix1 - vw + 1, step):
            cell.shapes(via_layer).insert(kdb.Box(x, iy0, x + vw, iy0 + vw))
            cell.shapes(via_layer).insert(kdb.Box(x, iy1 - vw, x + vw, iy1))
        for y in range(iy0, iy1 - vw + 1, step):
            cell.shapes(via_layer).insert(kdb.Box(ix0, y, ix0 + vw, y + vw))
            cell.shapes(via_layer).insert(kdb.Box(ix1 - vw, y, ix1, y + vw))

    # ── Helper: fill a via array on ring edges ────────────────────
    def fill_ring_vias(via_layer: kdb.LayerInfo, vw: int, vs: int) -> None:
        step = vw + vs
        for x in range(rx0, rx1 - vw + 1, step):
            cell.shapes(via_layer).insert(kdb.Box(x, ry0, x + vw, ry0 + vw))
            cell.shapes(via_layer).insert(kdb.Box(x, ry1 - vw, x + vw, ry1))
        for y in range(ry0, ry1 - vw + 1, step):
            cell.shapes(via_layer).insert(kdb.Box(rx0, y, rx0 + vw, y + vw))
            cell.shapes(via_layer).insert(kdb.Box(rx1 - vw, y, rx1, y + vw))

    # ── Paint metal layers ────────────────────────────────────────
    # Every metal in the stack gets the identical plate + ring pattern.
    if (bot, top) == (4, 5):
        paint_plate_and_ring(G.M4)
        paint_plate_and_ring(G.M5)
        fill_inner_vias(G.VIA4, via_w, via_sp)
        fill_ring_vias(G.VIA4, via_w, via_sp)

    elif (bot, top) == (4, 6):
        paint_plate_and_ring(G.M4)
        paint_plate_and_ring(G.M5)
        paint_plate_and_ring(G.M6)
        # VIA4: connects M4 ↔ M5
        v4_R = getattr(R, "VIA4")
        v4_w = v4_R.width
        v4_sp = getattr(v4_R.spacing, "VIA4", v4_w)
        fill_inner_vias(G.VIA4, v4_w, v4_sp)
        fill_ring_vias(G.VIA4, v4_w, v4_sp)
        # VIA5: connects M5 ↔ M6
        fill_inner_vias(G.VIA5, via_w, via_sp)
        fill_ring_vias(G.VIA5, via_w, via_sp)

    elif (bot, top) == (5, 7):
        paint_plate_and_ring(G.M5)
        paint_plate_and_ring(G.M6)
        paint_plate_and_ring(G.M7)
        # VIA5: connects M5 ↔ M6
        v5_R = getattr(R, "VIA5")
        v5_w = v5_R.width
        v5_sp = getattr(v5_R.spacing, "VIA5", v5_w)
        fill_inner_vias(G.VIA5, v5_w, v5_sp)
        fill_ring_vias(G.VIA5, v5_w, v5_sp)
        # VIA6: connects M6 ↔ M7
        fill_inner_vias(G.VIA6, via_w, via_sp)
        fill_ring_vias(G.VIA6, via_w, via_sp)

    elif (bot, top) == (6, 7):
        paint_plate_and_ring(G.M6)
        paint_plate_and_ring(G.M7)
        fill_inner_vias(G.VIA6, via_w, via_sp)
        fill_ring_vias(G.VIA6, via_w, via_sp)

    # ── Pin labels ────────────────────────────────────────────────
    # Pin on the bottom metal's pin layer: inner plate = bottom terminal.
    # Pin on the top metal's pin layer: outer ring = top terminal.
    pin_w = metal_w
    bot_pin_layer = {4: G.PIN4, 5: G.PIN5, 6: G.PIN6}[bot]
    top_pin_layer = {5: G.PIN5, 6: G.PIN6, 7: G.PIN7}[top]

    # Inner plate pin (bottom terminal) on the bottom metal's pin layer
    cell.shapes(bot_pin_layer).insert(
        kdb.Box(ix0, iy0, min(ix1, ix0 + pin_w), iy0 + pin_w)
    )
    # Outer ring pin (top terminal) on the top metal's pin layer
    cell.shapes(top_pin_layer).insert(
        kdb.Box(rx0, ry0, min(rx1, rx0 + pin_w), ry0 + pin_w)
    )

    return layout


def test_momcap(outdir: Path, tech: str, mode: str, visual: bool) -> None:
    """Inline MOMCAP sweep test using the new API."""

    pdk_module = import_module(f"pdk.{tech}.layout")
    tech_map = pdk_module.layer_map()

    if mode == "min":
        variants = [MomcapParams()]
    else:
        variants = [
            MomcapParams(
                bottom_layer=bl,
                top_layer=tl,
                inner_width_mult=iw,
                inner_width_height=ih,
                spacing_multi=sp,
                outer_width_mult=ow,
            )
            for (bl, tl) in [(4, 5), (4, 6), (5, 7), (6, 7)]
            for iw in (1, 2, 3)
            for ih in (1, 2, 4)
            for sp in (1, 2, 3)
            for ow in (1, 2)
        ]

    for params in variants:
        layout = momcap(params, tech)
        remap_layers(layout, tech_map)
        stem = (
            f"momcap_m{params.bottom_layer}_m{params.top_layer}_"
            f"iw{params.inner_width_mult}_ih{params.inner_width_height}_"
            f"sp{params.spacing_multi}_ow{params.outer_width_mult}"
        )
        artifacts = export_layout(
            layout=layout,
            out_dir=outdir,
            stem=stem,
            domain=f"frida.layout.{tech}",
            write_debug_gds=visual,
        )
        assert artifacts.pb.exists()
        assert artifacts.pbtxt.exists()
        if visual:
            assert artifacts.gds is not None and artifacts.gds.exists()
            png = gds_to_png_with_pdk_style(artifacts.gds, tech=tech, out_dir=outdir)
            assert png.exists()
