"""Monolithic MOSFET layout generator and inline sweep test."""

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
class MosfetParams:
    wf_mult = L.Param(dtype=int, default=1)
    lf_mult = L.Param(dtype=int, default=1)
    fing_count = L.Param(dtype=int, default=4)
    mosfet_vth = L.Param(dtype=L.MosVth, default=L.MosVth.LOW)
    track_count = L.Param(dtype=int, default=9)
    mosfet_type = L.Param(dtype=L.MosType, default=L.MosType.NMOS)
    source_tie = L.Param(dtype=L.SourceTie, default=L.SourceTie.OFF)
    powerrail_mult = L.Param(dtype=int, default=2)


@L.generator
def mosfet(params: MosfetParams, tech_name: str) -> kdb.Layout:
    if params.wf_mult < 1 or params.lf_mult < 1:
        raise ValueError("wf_mult and lf_mult must be >= 1")
    if params.fing_count < 1:
        raise ValueError("fing_count must be >= 1")
    if params.track_count < 5:
        raise ValueError("track_count must be >= 5")
    if params.powerrail_mult < 1:
        raise ValueError("powerrail_mult must be >= 1")

    # ── Load PDK data ──────────────────────────────────────────────
    R = load_rules_deck(tech_name)

    layout = kdb.Layout()
    layout.dbu = load_dbu(tech_name)
    top = layout.create_cell("MOSFET")
    G = load_generic_layers(layout)

    # ── Derived geometry ──────────────────────────────────────────
    track_pitch = R.M1.width + R.M1.spacing.M1
    rail_w = params.powerrail_mult * R.M1.width
    row_margin = max(R.M1.spacing.M1, R.OD.spacing.OD)

    cell_h = params.track_count * track_pitch
    y_vss0 = 0
    y_vss1 = rail_w
    y_vdd1 = cell_h
    y_vdd0 = y_vdd1 - rail_w

    main_h = max(params.wf_mult * R.OD.width, R.CO.width + 2 * R.CO.enclosure.OD)
    dummy_h = main_h
    y_main0 = y_vss1 + row_margin
    y_main1 = y_main0 + main_h
    y_dummy1 = y_vdd0 - row_margin
    y_dummy0 = y_dummy1 - dummy_h
    if y_dummy0 <= y_main1 + max(R.OD.spacing.OD, R.PO.spacing.PO):
        raise ValueError("track_count too small for requested geometry")

    poly_ext = max(R.PO.spacing.PO, R.CO.enclosure.PO)
    y_poly0 = y_main0 - poly_ext
    y_poly1 = y_dummy1 + poly_ext
    y_sd_mid = (y_main0 + y_main1) // 2
    y_gate = (y_main1 + y_dummy0) // 2

    gate_len = max(R.PO.width, params.lf_mult * R.PO.width)
    sd_pitch = R.CO.width + 2 * R.CO.spacing.PO + gate_len
    x_left_margin = track_pitch
    x_sd0 = x_left_margin + R.CO.enclosure.OD + R.CO.width // 2
    x_sd_last = x_sd0 + params.fing_count * sd_pitch
    x_act0 = x_sd0 - R.CO.width // 2 - R.CO.enclosure.OD
    x_act1 = x_sd_last + R.CO.width // 2 + R.CO.enclosure.OD
    x0 = max(0, x_act0 - x_left_margin)
    x1 = x_act1 + x_left_margin

    # ── Power rails ───────────────────────────────────────────────
    top.shapes(G.M1).insert(kdb.Box(x0, y_vss0, x1, y_vss1))
    top.shapes(G.M1).insert(kdb.Box(x0, y_vdd0, x1, y_vdd1))
    top.shapes(G.M1).insert(
        kdb.Box(x0, y_gate - R.M1.width // 2, x1, y_gate + R.M1.width // 2)
    )

    # ── Active areas ──────────────────────────────────────────────
    top.shapes(G.OD).insert(kdb.Box(x_act0, y_main0, x_act1, y_main1))
    top.shapes(G.OD).insert(kdb.Box(x_act0, y_dummy0, x_act1, y_dummy1))

    # ── Implant layers (NP / PP) ─────────────────────────────────
    # The main device gets the matching implant; the dummy transistor
    # (opposite type) gets the complementary implant + n-well.
    #
    #   MosType  │ main implant │ dummy implant │ NW on dummy?
    #   ─────────┼──────────────┼───────────────┼─────────────
    #   NMOS     │ NP           │ PP            │ yes
    #   PMOS     │ PP (+NW)     │ NP            │ no
    #
    main_box = kdb.Box(
        x_act0 - R.NP.enclosure.OD,
        y_main0 - R.NP.enclosure.OD,
        x_act1 + R.NP.enclosure.OD,
        y_main1 + R.NP.enclosure.OD,
    )
    dummy_box = kdb.Box(
        x_act0 - R.PP.enclosure.OD,
        y_dummy0 - R.PP.enclosure.OD,
        x_act1 + R.PP.enclosure.OD,
        y_dummy1 + R.PP.enclosure.OD,
    )
    nw_box = kdb.Box(
        x_act0 - R.NW.enclosure.OD,
        y_dummy0 - R.NW.enclosure.OD,
        x_act1 + R.NW.enclosure.OD,
        y_dummy1 + R.NW.enclosure.OD,
    )

    if params.mosfet_type == L.MosType.NMOS:
        top.shapes(G.NP).insert(main_box)
        top.shapes(G.PP).insert(dummy_box)
        top.shapes(G.NW).insert(nw_box)
    else:
        top.shapes(G.PP).insert(main_box)
        top.shapes(G.NW).insert(
            kdb.Box(
                x_act0 - R.NW.enclosure.OD,
                y_main0 - R.NW.enclosure.OD,
                x_act1 + R.NW.enclosure.OD,
                y_main1 + R.NW.enclosure.OD,
            )
        )
        top.shapes(G.NP).insert(dummy_box)

    # ── Additional Vth implant layer ──────────────────────────────
    # Threshold-voltage adjust implants are selected by the
    # combination of MosVth and MosType:
    #
    #   MosVth   │ NMOS  │ PMOS
    #   ─────────┼───────┼──────
    #   LOW      │ LVTN  │ LVTP
    #   REGULAR  │  —    │  —
    #   HIGH     │ HVTN  │ HVTP
    #
    vth_box = kdb.Box(x_act0, y_main0, x_act1, y_dummy1)

    if params.mosfet_vth == L.MosVth.LOW:
        if params.mosfet_type == L.MosType.NMOS:
            top.shapes(G.LVTN).insert(vth_box)
        else:
            top.shapes(G.LVTP).insert(vth_box)
    elif params.mosfet_vth == L.MosVth.HIGH:
        if params.mosfet_type == L.MosType.NMOS:
            top.shapes(G.HVTN).insert(vth_box)
        else:
            top.shapes(G.HVTP).insert(vth_box)
    # MosVth.REGULAR requires no additional implant layer.

    # ── Gate poly ─────────────────────────────────────────────────
    for i in range(params.fing_count):
        xg0 = x_sd0 + i * sd_pitch + R.CO.width // 2 + R.CO.spacing.PO
        xg1 = xg0 + gate_len
        top.shapes(G.PO).insert(kdb.Box(xg0, y_poly0, xg1, y_poly1))

    # ── Contacts & M1 pads ────────────────────────────────────────
    pad_w = max(R.M1.width, R.CO.width + 2 * R.M1.enclosure.CO)
    for i in range(params.fing_count + 1):
        xc = x_sd0 + i * sd_pitch
        yc_main = y_sd_mid
        yc_dummy = (y_dummy0 + y_dummy1) // 2
        c0x = xc - R.CO.width // 2
        c1x = c0x + R.CO.width
        c0y_main = yc_main - R.CO.width // 2
        c1y_main = c0y_main + R.CO.width
        c0y_dummy = yc_dummy - R.CO.width // 2
        c1y_dummy = c0y_dummy + R.CO.width
        top.shapes(G.CO).insert(kdb.Box(c0x, c0y_main, c1x, c1y_main))
        top.shapes(G.CO).insert(kdb.Box(c0x, c0y_dummy, c1x, c1y_dummy))

        m0x = xc - pad_w // 2
        m1x = m0x + pad_w
        m0y_main = yc_main - pad_w // 2
        m1y_main = m0y_main + pad_w
        top.shapes(G.M1).insert(kdb.Box(m0x, m0y_main, m1x, m1y_main))

        strap_to = None
        if params.source_tie == L.SourceTie.ON and i % 2 == 0:
            strap_to = (
                (y_vss0 + y_vss1) // 2
                if params.mosfet_type == L.MosType.NMOS
                else (y_vdd0 + y_vdd1) // 2
            )

        if strap_to is not None:
            yl = min(yc_main, strap_to)
            yh = max(yc_main, strap_to)
            sw = max(R.M1.width, R.CO.width)
            top.shapes(G.M1).insert(kdb.Box(xc - sw // 2, yl, xc + sw // 2, yh))

    # ── Pin labels ────────────────────────────────────────────────
    pin_w = rail_w
    top.shapes(G.PIN1).insert(kdb.Box(x0, y_vss0, min(x1, x0 + pin_w), y_vss1))
    top.shapes(G.PIN1).insert(kdb.Box(x0, y_vdd0, min(x1, x0 + pin_w), y_vdd1))
    top.shapes(G.PIN1).insert(
        kdb.Box(
            x0,
            y_gate - R.M1.width // 2,
            min(x1, x0 + pin_w),
            y_gate + R.M1.width // 2,
        )
    )
    top.shapes(G.PIN1).insert(
        kdb.Box(x1 - pin_w, y_sd_mid - R.M1.width // 2, x1, y_sd_mid + R.M1.width // 2)
    )

    return layout


def test_mosfet(outdir: Path, tech: str, mode: str, visual: bool) -> None:
    """Inline MOSFET sweep test using the new API."""

    pdk_module = import_module(f"pdk.{tech}.layout")
    tech_map = pdk_module.layer_map()

    if mode == "min":
        variants = [MosfetParams()]
    else:
        variants = [
            MosfetParams(
                mosfet_type=tp,
                mosfet_vth=vth,
                track_count=tracks,
                fing_count=fingers,
                wf_mult=wf,
                lf_mult=lf,
                source_tie=tie,
                powerrail_mult=pr,
            )
            for tp in (L.MosType.NMOS, L.MosType.PMOS)
            for vth in (L.MosVth.LOW, L.MosVth.REGULAR, L.MosVth.HIGH)
            for tracks in (9, 12)
            for fingers in (2, 4, 8)
            for wf in (1, 2, 3)
            for lf in (1, 2)
            for tie in (L.SourceTie.OFF, L.SourceTie.ON)
            for pr in (2, 3)
        ]

    for params in variants:
        layout = mosfet(params, tech)
        remap_layers(layout, tech_map)
        stem = (
            f"mos_t{params.mosfet_type.name.lower()}_"
            f"v{params.mosfet_vth.name.lower()}_"
            f"nf{params.fing_count}_w{params.wf_mult}_l{params.lf_mult}_"
            f"s{params.source_tie.name.lower()}_pr{params.powerrail_mult}"
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
