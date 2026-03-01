"""Monolithic MOMCAP layout generator and inline sweep test."""

from __future__ import annotations

from importlib import import_module
from pathlib import Path

import klayout.db as kdb
import vlsir.tech_pb2 as vtech

from .dsl import L, Layer
from .image import gds_to_png_with_pdk_style
from .serialize import export_layout, read_technology_proto, write_technology_proto
from .tech import map_generic_to_tech_layers


@L.paramclass
class MomcapParams:
    top_layer = L.Param(dtype=L.MetalDraw, default=L.MetalDraw.M6)
    bottom_layer = L.Param(dtype=L.MetalDraw, default=L.MetalDraw.M5)
    inner_width_mult = L.Param(dtype=int, default=1)
    inner_width_height = L.Param(dtype=int, default=1)
    spacing_multi = L.Param(dtype=int, default=1)
    outer_width_mult = L.Param(dtype=int, default=1)


@L.generator
def momcap(params: MomcapParams, tech: vtech.Technology) -> kdb.Layout:
    if params.inner_width_mult < 1:
        raise ValueError("inner_width_mult must be >= 1")
    if params.inner_width_height < 1:
        raise ValueError("inner_width_height must be >= 1")
    if params.spacing_multi < 1:
        raise ValueError("spacing_multi must be >= 1")
    if params.outer_width_mult < 1:
        raise ValueError("outer_width_mult must be >= 1")

    top_generic = L.param_to_generic(metal=params.top_layer)
    bot_generic = L.param_to_generic(metal=params.bottom_layer)
    if top_generic is None or bot_generic is None:
        raise ValueError("MetalDraw selector must map to a generic layer")

    db_microns = (
        int(tech.rules.lef_units.database_microns)
        if tech.rules.lef_units.database_microns
        else 1000
    )
    dbu_um = 1.0 / float(db_microns)

    layer_rules = {layer.name.upper(): layer for layer in tech.rules.layers}

    def first_numeric_token_um(
        rule_set: vtech.LayerRuleSet, keyword: str
    ) -> float | None:
        for stmt in rule_set.rules:
            if stmt.keyword.upper() != keyword:
                continue
            for tok in stmt.tokens:
                field = tok.WhichOneof("value")
                if field in {"integer", "real"}:
                    return float(getattr(tok, field))
        return None

    top_name = top_generic.name
    bot_name = bot_generic.name
    if top_name not in layer_rules or bot_name not in layer_rules:
        raise ValueError("Technology is missing requested top or bottom metal rule-set")

    top_width_um = first_numeric_token_um(layer_rules[top_name], "WIDTH")
    top_area_um2 = first_numeric_token_um(layer_rules[top_name], "AREA")
    top_spacing_um = first_numeric_token_um(layer_rules[top_name], "SPACING")
    bot_width_um = first_numeric_token_um(layer_rules[bot_name], "WIDTH")
    if top_width_um is None or bot_width_um is None:
        raise ValueError("Missing WIDTH rule on selected top or bottom metal")
    if top_spacing_um is None:
        top_spacing_um = top_width_um
    if top_area_um2 is None:
        top_area_um2 = top_width_um * top_width_um

    top_num = int(params.top_layer)
    bot_num = int(params.bottom_layer)
    if abs(top_num - bot_num) != 1:
        raise ValueError("top_layer and bottom_layer must be adjacent")
    via_num = min(top_num, bot_num)
    via_name = f"VIA{via_num}"
    if via_name not in layer_rules:
        raise ValueError(f"Technology is missing {via_name} rule-set")

    via_width_um = first_numeric_token_um(layer_rules[via_name], "WIDTH")
    via_spacing_um = first_numeric_token_um(layer_rules[via_name], "SPACING")
    if via_width_um is None:
        raise ValueError(f"Missing WIDTH rule on {via_name}")
    if via_spacing_um is None:
        via_spacing_um = via_width_um

    top_width_nm = max(1, int(round(top_width_um * 1000.0)))
    bot_width_nm = max(1, int(round(bot_width_um * 1000.0)))
    top_area_nm2 = max(1, int(round(top_area_um2 * 1_000_000.0)))
    top_spacing_nm = max(1, int(round(top_spacing_um * 1000.0)))
    via_width_nm = max(1, int(round(via_width_um * 1000.0)))
    via_spacing_nm = max(1, int(round(via_spacing_um * 1000.0)))

    base_inner_h = max(1, (top_area_nm2 + top_width_nm - 1) // top_width_nm)
    inner_w = params.inner_width_mult * top_width_nm
    inner_h = params.inner_width_height * base_inner_h
    gap = params.spacing_multi * top_spacing_nm
    ring_w = params.outer_width_mult * top_width_nm
    via_step = via_width_nm + via_spacing_nm

    ix0, iy0 = 0, 0
    ix1, iy1 = inner_w, inner_h
    rx0, ry0 = ix0 - gap - ring_w, iy0 - gap - ring_w
    rx1, ry1 = ix1 + gap + ring_w, iy1 + gap + ring_w
    rix0, riy0 = ix0 - gap, iy0 - gap
    rix1, riy1 = ix1 + gap, iy1 + gap

    layout = kdb.Layout()
    layout.dbu = dbu_um
    top = layout.create_cell("MOMCAP")

    l_top_draw = layout.layer(kdb.LayerInfo(L.generic_name(top_generic.draw)))
    l_top_pin = layout.layer(kdb.LayerInfo(L.generic_name(top_generic.pin)))
    l_bot_draw = layout.layer(kdb.LayerInfo(L.generic_name(bot_generic.draw)))
    l_bot_pin = layout.layer(kdb.LayerInfo(L.generic_name(bot_generic.pin)))
    l_via_draw = layout.layer(
        kdb.LayerInfo(L.generic_name(getattr(Layer, via_name).draw))
    )

    top.shapes(l_top_draw).insert(kdb.Box(ix0, iy0, ix1, iy1))
    top.shapes(l_top_draw).insert(kdb.Box(rx0, ry0, rx1, riy0))
    top.shapes(l_top_draw).insert(kdb.Box(rx0, riy1, rx1, ry1))
    top.shapes(l_top_draw).insert(kdb.Box(rx0, riy0, rix0, riy1))
    top.shapes(l_top_draw).insert(kdb.Box(rix1, riy0, rx1, riy1))

    bot_grow = max(0, (bot_width_nm - top_width_nm) // 2)
    bix0, biy0 = ix0 - bot_grow, iy0 - bot_grow
    bix1, biy1 = ix1 + bot_grow, iy1 + bot_grow
    brx0, bry0 = rx0 - bot_grow, ry0 - bot_grow
    brx1, bry1 = rx1 + bot_grow, ry1 + bot_grow
    brix0, briy0 = rix0 + bot_grow, riy0 + bot_grow
    brix1, briy1 = rix1 - bot_grow, riy1 - bot_grow

    top.shapes(l_bot_draw).insert(kdb.Box(bix0, biy0, bix1, biy1))
    top.shapes(l_bot_draw).insert(kdb.Box(brx0, bry0, brx1, briy0))
    top.shapes(l_bot_draw).insert(kdb.Box(brx0, briy1, brx1, bry1))
    top.shapes(l_bot_draw).insert(kdb.Box(brx0, briy0, brix0, briy1))
    top.shapes(l_bot_draw).insert(kdb.Box(brix1, briy0, brx1, briy1))

    for x in range(ix0, ix1 - via_width_nm + 1, via_step):
        top.shapes(l_via_draw).insert(
            kdb.Box(x, iy0, x + via_width_nm, iy0 + via_width_nm)
        )
        top.shapes(l_via_draw).insert(
            kdb.Box(x, iy1 - via_width_nm, x + via_width_nm, iy1)
        )
    for y in range(iy0, iy1 - via_width_nm + 1, via_step):
        top.shapes(l_via_draw).insert(
            kdb.Box(ix0, y, ix0 + via_width_nm, y + via_width_nm)
        )
        top.shapes(l_via_draw).insert(
            kdb.Box(ix1 - via_width_nm, y, ix1, y + via_width_nm)
        )

    for x in range(rx0, rx1 - via_width_nm + 1, via_step):
        top.shapes(l_via_draw).insert(
            kdb.Box(x, ry0, x + via_width_nm, ry0 + via_width_nm)
        )
        top.shapes(l_via_draw).insert(
            kdb.Box(x, ry1 - via_width_nm, x + via_width_nm, ry1)
        )
    for y in range(ry0, ry1 - via_width_nm + 1, via_step):
        top.shapes(l_via_draw).insert(
            kdb.Box(rx0, y, rx0 + via_width_nm, y + via_width_nm)
        )
        top.shapes(l_via_draw).insert(
            kdb.Box(rx1 - via_width_nm, y, rx1, y + via_width_nm)
        )

    pin_w = max(top_width_nm, bot_width_nm)
    top.shapes(l_top_pin).insert(kdb.Box(ix0, iy0, min(ix1, ix0 + pin_w), iy0 + pin_w))
    top.shapes(l_bot_pin).insert(kdb.Box(rx0, ry0, min(rx1, rx0 + pin_w), ry0 + pin_w))
    return layout


def test_momcap(outdir: Path, tech: str, mode: str, visual: bool) -> None:
    """Inline MOMCAP sweep test controlled by --tech and --mode."""

    module = import_module(f"pdk.{tech}.layout.pdk_layout")
    rule_fn = getattr(module, f"{tech}_rule_deck")
    artifacts = write_technology_proto(
        tech_name=tech,
        layer_infos=module.layer_infos(),
        rule_deck=rule_fn(),
        out_dir=outdir,
        stem=f"{tech}_layout_momcap_tech",
    )
    proto = read_technology_proto(artifacts.pb)
    tech_map = module.tech_layer_map()

    if mode == "min":
        variants = [MomcapParams()]
    else:
        variants = [
            MomcapParams(
                top_layer=L.MetalDraw.M6,
                bottom_layer=L.MetalDraw.M5,
                inner_width_mult=iw,
                inner_width_height=ih,
                spacing_multi=sp,
                outer_width_mult=ow,
            )
            for iw in (1, 2, 3)
            for ih in (1, 2, 4)
            for sp in (1, 2, 3)
            for ow in (1, 2)
        ]

    for params in variants:
        layout = momcap(params, proto)
        map_generic_to_tech_layers(layout, tech_map)
        stem = (
            f"momcap_t{params.top_layer.name.lower()}_"
            f"b{params.bottom_layer.name.lower()}_"
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
