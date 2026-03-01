"""Monolithic MOSFET layout generator and inline sweep test."""

from __future__ import annotations

from importlib import import_module
from pathlib import Path

import klayout.db as kdb
import vlsir.tech_pb2 as vtech

from .dsl import L
from .image import gds_to_png_with_pdk_style
from .serialize import export_layout, read_technology_proto, write_technology_proto
from .tech import map_generic_to_tech_layers


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
def mosfet(params: MosfetParams, tech: vtech.Technology) -> kdb.Layout:
    if params.wf_mult < 1 or params.lf_mult < 1:
        raise ValueError("wf_mult and lf_mult must be >= 1")
    if params.fing_count < 1:
        raise ValueError("fing_count must be >= 1")
    if params.track_count < 5:
        raise ValueError("track_count must be >= 5")
    if params.powerrail_mult < 1:
        raise ValueError("powerrail_mult must be >= 1")

    db_microns = (
        int(tech.rules.lef_units.database_microns)
        if tech.rules.lef_units.database_microns
        else 1000
    )
    dbu_um = 1.0 / float(db_microns)

    layer_rules = {layer.name.upper(): layer for layer in tech.rules.layers}

    m1_width_nm = 0
    for stmt in layer_rules["M1"].rules:
        if stmt.keyword.upper() == "WIDTH":
            for tok in stmt.tokens:
                field = tok.WhichOneof("value")
                if field in {"integer", "real"}:
                    m1_width_nm = int(round(float(getattr(tok, field)) * 1000.0))
                    break
        if m1_width_nm > 0:
            break
    if m1_width_nm <= 0:
        raise ValueError("Missing WIDTH rule for M1")

    m1_spacing_nm = 0
    for stmt in layer_rules["M1"].rules:
        if stmt.keyword.upper() != "SPACING":
            continue
        for tok in stmt.tokens:
            field = tok.WhichOneof("value")
            if field in {"integer", "real"}:
                m1_spacing_nm = max(
                    m1_spacing_nm, int(round(float(getattr(tok, field)) * 1000.0))
                )
                break
    if m1_spacing_nm <= 0:
        m1_spacing_nm = m1_width_nm

    od_width_nm = 0
    for stmt in layer_rules["OD"].rules:
        if stmt.keyword.upper() == "WIDTH":
            for tok in stmt.tokens:
                field = tok.WhichOneof("value")
                if field in {"integer", "real"}:
                    od_width_nm = int(round(float(getattr(tok, field)) * 1000.0))
                    break
        if od_width_nm > 0:
            break
    if od_width_nm <= 0:
        od_width_nm = m1_width_nm

    od_spacing_nm = 0
    for stmt in layer_rules["OD"].rules:
        if stmt.keyword.upper() != "SPACING":
            continue
        for tok in stmt.tokens:
            field = tok.WhichOneof("value")
            if field in {"integer", "real"}:
                od_spacing_nm = max(
                    od_spacing_nm, int(round(float(getattr(tok, field)) * 1000.0))
                )
                break
    if od_spacing_nm <= 0:
        od_spacing_nm = od_width_nm

    po_width_nm = 0
    for stmt in layer_rules["PO"].rules:
        if stmt.keyword.upper() in {"WIDTH", "MINLENGTH"}:
            for tok in stmt.tokens:
                field = tok.WhichOneof("value")
                if field in {"integer", "real"}:
                    po_width_nm = int(round(float(getattr(tok, field)) * 1000.0))
                    break
        if po_width_nm > 0:
            break
    if po_width_nm <= 0:
        po_width_nm = m1_width_nm

    po_spacing_nm = 0
    for stmt in layer_rules["PO"].rules:
        if stmt.keyword.upper() != "SPACING":
            continue
        for tok in stmt.tokens:
            field = tok.WhichOneof("value")
            if field in {"integer", "real"}:
                po_spacing_nm = max(
                    po_spacing_nm, int(round(float(getattr(tok, field)) * 1000.0))
                )
                break
    if po_spacing_nm <= 0:
        po_spacing_nm = po_width_nm

    co_width_nm = 0
    for stmt in layer_rules["CO"].rules:
        if stmt.keyword.upper() == "WIDTH":
            for tok in stmt.tokens:
                field = tok.WhichOneof("value")
                if field in {"integer", "real"}:
                    co_width_nm = int(round(float(getattr(tok, field)) * 1000.0))
                    break
        if co_width_nm > 0:
            break
    if co_width_nm <= 0:
        co_width_nm = m1_width_nm

    co_spacing_nm = 0
    for stmt in layer_rules["CO"].rules:
        if stmt.keyword.upper() != "SPACING":
            continue
        for tok in stmt.tokens:
            field = tok.WhichOneof("value")
            if field in {"integer", "real"}:
                co_spacing_nm = max(
                    co_spacing_nm, int(round(float(getattr(tok, field)) * 1000.0))
                )
                break
    if co_spacing_nm <= 0:
        co_spacing_nm = co_width_nm

    co_po_spacing_nm = po_spacing_nm
    co_od_encl_nm = max(1, co_width_nm // 4)
    co_po_encl_nm = max(1, co_width_nm // 4)
    m1_co_encl_nm = max(1, m1_width_nm // 4)
    np_od_encl_nm = od_spacing_nm
    pp_od_encl_nm = od_spacing_nm
    nwell_od_encl_nm = max(od_spacing_nm, m1_width_nm)

    for pair in tech.rules.layer_pairs:
        first = pair.first_layer.upper()
        second = pair.second_layer.upper()

        for stmt in pair.rules:
            kw = stmt.keyword.upper()
            value_nm = None
            for tok in stmt.tokens:
                field = tok.WhichOneof("value")
                if field in {"integer", "real"}:
                    value_nm = int(round(float(getattr(tok, field)) * 1000.0))
                    break
            if value_nm is None:
                continue

            names = {first, second}
            if kw == "SPACING" and names == {"CO", "PO"}:
                co_po_spacing_nm = value_nm
            if kw == "ENCLOSURE" and names == {"CO", "OD"}:
                co_od_encl_nm = value_nm
            if kw == "ENCLOSURE" and names == {"CO", "PO"}:
                co_po_encl_nm = value_nm
            if kw == "ENCLOSURE" and names == {"M1", "CO"}:
                m1_co_encl_nm = value_nm
            if kw == "ENCLOSURE" and names == {"NP", "OD"}:
                np_od_encl_nm = value_nm
            if kw == "ENCLOSURE" and names == {"PP", "OD"}:
                pp_od_encl_nm = value_nm
            if kw == "ENCLOSURE" and names == {"NWELL", "OD"}:
                nwell_od_encl_nm = value_nm

    layout = kdb.Layout()
    layout.dbu = dbu_um
    top = layout.create_cell("MOSFET")

    l_od = layout.layer(kdb.LayerInfo(L.generic_name(L.OD.draw)))
    l_po = layout.layer(kdb.LayerInfo(L.generic_name(L.PO.draw)))
    l_co = layout.layer(kdb.LayerInfo(L.generic_name(L.CO.draw)))
    l_m1 = layout.layer(kdb.LayerInfo(L.generic_name(L.M1.draw)))
    l_m1_pin = layout.layer(kdb.LayerInfo(L.generic_name(L.M1.pin)))
    l_np = layout.layer(kdb.LayerInfo(L.generic_name(L.NP.draw)))
    l_pp = layout.layer(kdb.LayerInfo(L.generic_name(L.PP.draw)))
    l_nwell = layout.layer(kdb.LayerInfo(L.generic_name(L.NWELL.draw)))

    vth_layer = L.param_to_generic(vth=params.mosfet_vth)
    l_vth = None
    if vth_layer is not None:
        l_vth = layout.layer(kdb.LayerInfo(L.generic_name(vth_layer.draw)))

    track_pitch_nm = m1_width_nm + m1_spacing_nm
    rail_w_nm = params.powerrail_mult * m1_width_nm
    row_margin_nm = max(m1_spacing_nm, od_spacing_nm)

    cell_h_nm = params.track_count * track_pitch_nm
    y_vss0 = 0
    y_vss1 = rail_w_nm
    y_vdd1 = cell_h_nm
    y_vdd0 = y_vdd1 - rail_w_nm

    main_h_nm = max(params.wf_mult * od_width_nm, co_width_nm + 2 * co_od_encl_nm)
    dummy_h_nm = main_h_nm
    y_main0 = y_vss1 + row_margin_nm
    y_main1 = y_main0 + main_h_nm
    y_dummy1 = y_vdd0 - row_margin_nm
    y_dummy0 = y_dummy1 - dummy_h_nm
    if y_dummy0 <= y_main1 + max(od_spacing_nm, po_spacing_nm):
        raise ValueError("track_count too small for requested geometry")

    poly_ext_nm = max(po_spacing_nm, co_po_encl_nm)
    y_poly0 = y_main0 - poly_ext_nm
    y_poly1 = y_dummy1 + poly_ext_nm
    y_sd_mid = (y_main0 + y_main1) // 2
    y_gate = (y_main1 + y_dummy0) // 2

    gate_len_nm = max(po_width_nm, params.lf_mult * po_width_nm)
    sd_pitch_nm = co_width_nm + 2 * co_po_spacing_nm + gate_len_nm
    x_left_margin_nm = track_pitch_nm
    x_sd0_nm = x_left_margin_nm + co_od_encl_nm + co_width_nm // 2
    x_sd_last_nm = x_sd0_nm + params.fing_count * sd_pitch_nm
    x_act0 = x_sd0_nm - co_width_nm // 2 - co_od_encl_nm
    x_act1 = x_sd_last_nm + co_width_nm // 2 + co_od_encl_nm
    x0 = max(0, x_act0 - x_left_margin_nm)
    x1 = x_act1 + x_left_margin_nm

    top.shapes(l_m1).insert(kdb.Box(x0, y_vss0, x1, y_vss1))
    top.shapes(l_m1).insert(kdb.Box(x0, y_vdd0, x1, y_vdd1))
    top.shapes(l_m1).insert(
        kdb.Box(x0, y_gate - m1_width_nm // 2, x1, y_gate + m1_width_nm // 2)
    )

    top.shapes(l_od).insert(kdb.Box(x_act0, y_main0, x_act1, y_main1))
    top.shapes(l_od).insert(kdb.Box(x_act0, y_dummy0, x_act1, y_dummy1))

    if params.mosfet_type == L.MosType.NMOS:
        top.shapes(l_np).insert(
            kdb.Box(
                x_act0 - np_od_encl_nm,
                y_main0 - np_od_encl_nm,
                x_act1 + np_od_encl_nm,
                y_main1 + np_od_encl_nm,
            )
        )
        top.shapes(l_pp).insert(
            kdb.Box(
                x_act0 - pp_od_encl_nm,
                y_dummy0 - pp_od_encl_nm,
                x_act1 + pp_od_encl_nm,
                y_dummy1 + pp_od_encl_nm,
            )
        )
        top.shapes(l_nwell).insert(
            kdb.Box(
                x_act0 - nwell_od_encl_nm,
                y_dummy0 - nwell_od_encl_nm,
                x_act1 + nwell_od_encl_nm,
                y_dummy1 + nwell_od_encl_nm,
            )
        )
    else:
        top.shapes(l_pp).insert(
            kdb.Box(
                x_act0 - pp_od_encl_nm,
                y_main0 - pp_od_encl_nm,
                x_act1 + pp_od_encl_nm,
                y_main1 + pp_od_encl_nm,
            )
        )
        top.shapes(l_nwell).insert(
            kdb.Box(
                x_act0 - nwell_od_encl_nm,
                y_main0 - nwell_od_encl_nm,
                x_act1 + nwell_od_encl_nm,
                y_main1 + nwell_od_encl_nm,
            )
        )
        top.shapes(l_np).insert(
            kdb.Box(
                x_act0 - np_od_encl_nm,
                y_dummy0 - np_od_encl_nm,
                x_act1 + np_od_encl_nm,
                y_dummy1 + np_od_encl_nm,
            )
        )

    for i in range(params.fing_count):
        xg0 = x_sd0_nm + i * sd_pitch_nm + co_width_nm // 2 + co_po_spacing_nm
        xg1 = xg0 + gate_len_nm
        top.shapes(l_po).insert(kdb.Box(xg0, y_poly0, xg1, y_poly1))

    pad_w_nm = max(m1_width_nm, co_width_nm + 2 * m1_co_encl_nm)
    for i in range(params.fing_count + 1):
        xc = x_sd0_nm + i * sd_pitch_nm
        yc_main = y_sd_mid
        yc_dummy = (y_dummy0 + y_dummy1) // 2
        c0x = xc - co_width_nm // 2
        c1x = c0x + co_width_nm
        c0y_main = yc_main - co_width_nm // 2
        c1y_main = c0y_main + co_width_nm
        c0y_dummy = yc_dummy - co_width_nm // 2
        c1y_dummy = c0y_dummy + co_width_nm
        top.shapes(l_co).insert(kdb.Box(c0x, c0y_main, c1x, c1y_main))
        top.shapes(l_co).insert(kdb.Box(c0x, c0y_dummy, c1x, c1y_dummy))

        m0x = xc - pad_w_nm // 2
        m1x = m0x + pad_w_nm
        m0y_main = yc_main - pad_w_nm // 2
        m1y_main = m0y_main + pad_w_nm
        top.shapes(l_m1).insert(kdb.Box(m0x, m0y_main, m1x, m1y_main))

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
            sw = max(m1_width_nm, co_width_nm)
            top.shapes(l_m1).insert(kdb.Box(xc - sw // 2, yl, xc + sw // 2, yh))

    if l_vth is not None:
        top.shapes(l_vth).insert(kdb.Box(x_act0, y_main0, x_act1, y_dummy1))

    pin_w = rail_w_nm
    top.shapes(l_m1_pin).insert(kdb.Box(x0, y_vss0, min(x1, x0 + pin_w), y_vss1))
    top.shapes(l_m1_pin).insert(kdb.Box(x0, y_vdd0, min(x1, x0 + pin_w), y_vdd1))
    top.shapes(l_m1_pin).insert(
        kdb.Box(
            x0,
            y_gate - m1_width_nm // 2,
            min(x1, x0 + pin_w),
            y_gate + m1_width_nm // 2,
        )
    )
    top.shapes(l_m1_pin).insert(
        kdb.Box(
            x1 - pin_w, y_sd_mid - m1_width_nm // 2, x1, y_sd_mid + m1_width_nm // 2
        )
    )

    return layout


def test_mosfet(outdir: Path, tech: str, mode: str, visual: bool) -> None:
    """Inline MOSFET sweep test controlled by --tech and --mode."""

    module = import_module(f"pdk.{tech}.layout.pdk_layout")
    rule_fn = getattr(module, f"{tech}_rule_deck")
    artifacts = write_technology_proto(
        tech_name=tech,
        layer_infos=module.layer_infos(),
        rule_deck=rule_fn(),
        out_dir=outdir,
        stem=f"{tech}_layout_mosfet_tech",
    )
    proto = read_technology_proto(artifacts.pb)
    tech_map = module.tech_layer_map()

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
        layout = mosfet(params, proto)
        map_generic_to_tech_layers(layout, tech_map)
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
