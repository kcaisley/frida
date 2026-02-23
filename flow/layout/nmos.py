"""
Gate-array NMOS unit primitive generator.

This module is intentionally split into three components:
1) Input + derived-dimension computation from explicit params and VLSIR tech.
2) Geometry generation using reusable construction helpers.
3) Pytest entrypoint for standalone smoke execution.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import klayout.db as kdb
import pytest
import vlsir.tech_pb2 as vtech

from .layout import (
    ExportArtifacts,
    export_layout,
    insert_box_um,
    insert_text_um,
    read_technology_proto,
    resolve_layer_spec_from_technology,
    technology_pair_rule_value,
    technology_rule_spacing,
    technology_rule_value,
)


# -----------------------------------------------------------------------------
# 1) Input + Derived-Dimension Computation
# -----------------------------------------------------------------------------


@dataclass(frozen=True)
class NmosInputParams:
    """User-level inputs for NMOS unit generation."""

    cell_name: str
    fingers: int
    gate_length_um: float
    finger_width_um: float
    dummy_width_scale: float
    track_count: int
    rail_width_tracks: float
    side_margin_tracks: float
    row_margin_tracks: float
    gate_track_offset: int
    connect_main_sd_to_rails: bool
    connect_dummy_to_vdd: bool
    connect_gate_to_gate_rail: bool


@dataclass(frozen=True)
class NmosLayerSpecs:
    """Layer-number / purpose specs resolved from VLSIR technology."""

    active: tuple[int, int]
    poly: tuple[int, int]
    contact: tuple[int, int]
    metal1: tuple[int, int]
    metal1_pin: tuple[int, int]
    nsd: tuple[int, int]
    psd: tuple[int, int]
    nwell: tuple[int, int]
    text: tuple[int, int] | None
    pr_boundary: tuple[int, int] | None


@dataclass(frozen=True)
class NmosPdkSettings:
    """Technology settings required to generate NMOS geometry."""

    tech_name: str
    dbu_um: float
    manufacturing_grid_um: float
    layers: NmosLayerSpecs
    m1_width_um: float
    m1_spacing_um: float
    active_width_um: float
    active_spacing_um: float
    poly_width_um: float
    poly_spacing_um: float
    cont_size_um: float
    cont_spacing_um: float
    cont_enc_active_um: float
    cont_enc_poly_um: float
    cont_enc_metal_um: float
    cont_gate_spacing_um: float
    poly_over_active_um: float
    nsd_over_active_um: float
    psd_over_active_um: float
    nwell_over_active_um: float


@dataclass(frozen=True)
class NmosDerived:
    """Fully derived NMOS geometry values ready for layout generation."""

    params: NmosInputParams
    pdk: NmosPdkSettings
    track_pitch_um: float
    rail_width_um: float
    side_margin_um: float
    row_margin_um: float
    y_vss_um: float
    y_vdd_um: float
    y_main_bot_um: float
    y_main_top_um: float
    y_dummy_bot_um: float
    y_dummy_top_um: float
    y_sd_mid_um: float
    y_gate_rail_um: float
    y_tie_um: float
    x_min_um: float
    x_max_um: float
    x_sd0_um: float
    sd_pitch_um: float
    cont_min_active_h_um: float
    m1_contact_size_um: float
    pin_length_um: float
    pin_x0_um: float
    label_dx_um: float


def _require_positive(name: str, value: float) -> float:
    if value <= 0:
        raise ValueError(f"{name} must be > 0, got {value}.")
    return value


def _require_nonnegative(name: str, value: float) -> float:
    if value < 0:
        raise ValueError(f"{name} must be >= 0, got {value}.")
    return value


def _require_rule_value(
    tech: vtech.Technology,
    layer_aliases: tuple[str, ...],
    keyword: str,
    desc: str,
) -> float:
    value = technology_rule_value(tech, layer_aliases, keyword)
    if value is None:
        raise ValueError(f"Missing required rule: {desc} ({layer_aliases}, {keyword}).")
    return value


def _require_rule_spacing(
    tech: vtech.Technology,
    layer_aliases: tuple[str, ...],
    width: float,
    desc: str,
) -> float:
    value = technology_rule_spacing(tech, layer_aliases, width=width, prl=0.0)
    if value is None:
        raise ValueError(f"Missing required spacing rule: {desc} ({layer_aliases}).")
    return value


def _require_pair_rule_value(
    tech: vtech.Technology,
    first_layer_aliases: tuple[str, ...],
    second_layer_aliases: tuple[str, ...],
    keyword: str,
    desc: str,
) -> float:
    value = technology_pair_rule_value(
        tech,
        first_layer_aliases,
        second_layer_aliases,
        keyword,
    )
    if value is None:
        raise ValueError(
            "Missing required pair-rule: "
            f"{desc} ({first_layer_aliases}, {second_layer_aliases}, {keyword})."
        )
    return value


def _optional_pair_rule_value(
    tech: vtech.Technology,
    first_layer_aliases: tuple[str, ...],
    second_layer_aliases: tuple[str, ...],
    keyword: str,
) -> float | None:
    return technology_pair_rule_value(
        tech,
        first_layer_aliases,
        second_layer_aliases,
        keyword,
    )


def _require_layer_spec(
    tech: vtech.Technology,
    aliases: tuple[str, ...],
    logical_name: str,
) -> tuple[int, int]:
    spec = resolve_layer_spec_from_technology(tech, aliases)
    if spec is None:
        raise ValueError(
            f"Could not resolve required layer '{logical_name}' from aliases {aliases}."
        )
    return spec


def _optional_layer_spec(
    tech: vtech.Technology,
    aliases: tuple[str, ...],
) -> tuple[int, int] | None:
    return resolve_layer_spec_from_technology(tech, aliases)


def extract_nmos_pdk_settings(tech: vtech.Technology) -> NmosPdkSettings:
    """
    Extract strict NMOS-generation settings from a VLSIR technology message.

    This function does not apply process-specific numeric defaults.
    """

    db_units = int(tech.rules.lef_units.database_microns)
    if db_units <= 0:
        raise ValueError("Technology.rules.lef_units.database_microns must be > 0.")
    dbu_um = 1.0 / float(db_units)

    manufacturing_grid_um = float(tech.rules.manufacturing_grid_microns)
    if manufacturing_grid_um <= 0:
        raise ValueError("Technology.rules.manufacturing_grid_microns must be > 0.")

    active_aliases = ("ACTIVE", "ACTIV", "OD")
    poly_aliases = ("POLY", "PO", "GATPOLY")
    cont_aliases = ("CONT", "CONTACT", "CO")
    m1_aliases = ("METAL1", "M1")

    layers = NmosLayerSpecs(
        active=_require_layer_spec(tech, active_aliases, "active"),
        poly=_require_layer_spec(tech, poly_aliases, "poly"),
        contact=_require_layer_spec(tech, cont_aliases, "contact"),
        metal1=_require_layer_spec(tech, m1_aliases, "metal1"),
        metal1_pin=_require_layer_spec(tech, ("M1.PIN", "METAL1.PIN"), "metal1_pin"),
        nsd=_require_layer_spec(tech, ("NSD", "NPLUS", "NPLUSDIFF"), "nsd"),
        psd=_require_layer_spec(tech, ("PSD", "PPLUS", "PPLUSDIFF"), "psd"),
        nwell=_require_layer_spec(tech, ("NWELL", "NW"), "nwell"),
        text=_optional_layer_spec(tech, ("TEXT", "LABEL")),
        pr_boundary=_optional_layer_spec(
            tech,
            ("PR_BOUNDARY", "BOUNDARY", "OVERLAP", "OUTLINE"),
        ),
    )

    m1_width = _require_rule_value(tech, m1_aliases, "WIDTH", "Metal1 width")
    m1_spacing = _require_rule_spacing(tech, m1_aliases, m1_width, "Metal1 spacing")
    active_width = _require_rule_value(tech, active_aliases, "WIDTH", "Active width")
    active_spacing = _require_rule_spacing(
        tech, active_aliases, active_width, "Active spacing"
    )
    poly_width = _require_rule_value(tech, poly_aliases, "WIDTH", "Poly width")
    poly_spacing = _require_rule_spacing(tech, poly_aliases, poly_width, "Poly spacing")
    cont_size = _require_rule_value(tech, cont_aliases, "WIDTH", "Contact width")
    cont_spacing = _require_rule_spacing(tech, cont_aliases, cont_size, "Contact spacing")

    cont_enc_active = _require_pair_rule_value(
        tech,
        active_aliases,
        cont_aliases,
        "ENCLOSURE",
        "Active encloses contact",
    )
    cont_enc_poly = _require_pair_rule_value(
        tech,
        poly_aliases,
        cont_aliases,
        "ENCLOSURE",
        "Poly encloses contact",
    )
    cont_enc_metal = _require_pair_rule_value(
        tech,
        m1_aliases,
        cont_aliases,
        "ENCLOSURE",
        "Metal1 encloses contact",
    )

    cont_gate_spacing = _require_pair_rule_value(
        tech,
        poly_aliases,
        cont_aliases,
        "SPACING",
        "Poly-to-contact spacing",
    )

    poly_over_active = _require_pair_rule_value(
        tech,
        active_aliases,
        poly_aliases,
        "ENCLOSURE",
        "Active enclosed by poly gate extension",
    )

    nsd_over_active = _require_pair_rule_value(
        tech,
        active_aliases,
        ("NSD", "NPLUS", "NPLUSDIFF"),
        "ENCLOSURE",
        "ACTIVE-NSD enclosure",
    )
    psd_over_active = _require_pair_rule_value(
        tech,
        active_aliases,
        ("PSD", "PPLUS", "PPLUSDIFF"),
        "ENCLOSURE",
        "ACTIVE-PSD enclosure",
    )
    nwell_over_active = _require_pair_rule_value(
        tech,
        active_aliases,
        ("NWELL", "NW"),
        "ENCLOSURE",
        "ACTIVE-NWELL enclosure",
    )

    return NmosPdkSettings(
        tech_name=tech.name,
        dbu_um=dbu_um,
        manufacturing_grid_um=manufacturing_grid_um,
        layers=layers,
        m1_width_um=m1_width,
        m1_spacing_um=m1_spacing,
        active_width_um=active_width,
        active_spacing_um=active_spacing,
        poly_width_um=poly_width,
        poly_spacing_um=poly_spacing,
        cont_size_um=cont_size,
        cont_spacing_um=cont_spacing,
        cont_enc_active_um=cont_enc_active,
        cont_enc_poly_um=cont_enc_poly,
        cont_enc_metal_um=cont_enc_metal,
        cont_gate_spacing_um=cont_gate_spacing,
        poly_over_active_um=poly_over_active,
        nsd_over_active_um=nsd_over_active,
        psd_over_active_um=psd_over_active,
        nwell_over_active_um=nwell_over_active,
    )


def derive_nmos_geometry(params: NmosInputParams, pdk: NmosPdkSettings) -> NmosDerived:
    """Compute all scaled and derived NMOS geometry from input + PDK settings."""

    if params.fingers < 1:
        raise ValueError("fingers must be >= 1")
    if params.track_count < 2:
        raise ValueError("track_count must be >= 2")
    if params.gate_track_offset < 1:
        raise ValueError("gate_track_offset must be >= 1")

    _require_positive("gate_length_um", params.gate_length_um)
    _require_positive("finger_width_um", params.finger_width_um)
    _require_positive("dummy_width_scale", params.dummy_width_scale)
    _require_positive("rail_width_tracks", params.rail_width_tracks)
    _require_nonnegative("side_margin_tracks", params.side_margin_tracks)
    _require_nonnegative("row_margin_tracks", params.row_margin_tracks)

    track_pitch = pdk.m1_width_um + pdk.m1_spacing_um
    rail_w = params.rail_width_tracks * track_pitch
    side_margin = params.side_margin_tracks * track_pitch
    row_margin = params.row_margin_tracks * track_pitch

    cont_min_active_h = pdk.cont_size_um + 2.0 * pdk.cont_enc_active_um
    main_h = max(params.finger_width_um, pdk.active_width_um, cont_min_active_h)
    dummy_h = max(main_h * params.dummy_width_scale, pdk.active_width_um, cont_min_active_h)

    y_vss = 0.0
    y_vdd = params.track_count * track_pitch

    y_main_bot = y_vss + 0.5 * rail_w + row_margin
    y_main_top = y_main_bot + main_h
    y_dummy_top = y_vdd - 0.5 * rail_w - row_margin
    y_dummy_bot = y_dummy_top - dummy_h

    min_row_gap = max(pdk.active_spacing_um, pdk.poly_spacing_um, pdk.m1_spacing_um)
    if y_dummy_bot <= y_main_top + min_row_gap:
        raise ValueError(
            "Insufficient vertical room for rows with current track/dimension settings."
        )

    y_sd_mid = 0.5 * (y_main_top + y_dummy_bot)
    y_gate_candidate = y_sd_mid + params.gate_track_offset * track_pitch
    y_gate_min = y_sd_mid + max(pdk.m1_spacing_um, pdk.manufacturing_grid_um)
    y_gate_max = y_vdd - 0.5 * rail_w - row_margin
    if y_gate_max <= y_gate_min:
        raise ValueError("No valid Y-location remains for gate rail.")
    y_gate_rail = min(max(y_gate_candidate, y_gate_min), y_gate_max)

    sd_pitch = pdk.cont_size_um + 2.0 * pdk.cont_gate_spacing_um + params.gate_length_um
    x_sd0 = side_margin
    x_sd_last = x_sd0 + params.fingers * sd_pitch
    x_active_l = x_sd0 - pdk.cont_enc_active_um
    x_active_r = x_sd_last + pdk.cont_enc_active_um
    x_min = x_active_l - side_margin
    x_max = x_active_r + side_margin

    tie_h = pdk.cont_size_um + 2.0 * pdk.cont_enc_poly_um
    tie_guard = max(pdk.m1_spacing_um, pdk.manufacturing_grid_um)
    y_tie_low = y_main_top + 0.5 * tie_h + tie_guard
    y_tie_high = y_dummy_bot - 0.5 * tie_h - tie_guard
    if y_tie_high <= y_tie_low:
        raise ValueError("No valid Y-location remains for poly tie bar.")
    y_tie_center = 0.5 * (y_sd_mid + y_gate_rail)
    y_tie = min(max(y_tie_center, y_tie_low), y_tie_high)

    m1_contact_size = max(pdk.m1_width_um, pdk.cont_size_um + 2.0 * pdk.cont_enc_metal_um)

    pin_length = rail_w
    pin_x0 = x_min + max(0.5 * side_margin, pdk.manufacturing_grid_um)
    label_dx = max(pdk.manufacturing_grid_um, 0.5 * pdk.m1_spacing_um)

    return NmosDerived(
        params=params,
        pdk=pdk,
        track_pitch_um=track_pitch,
        rail_width_um=rail_w,
        side_margin_um=side_margin,
        row_margin_um=row_margin,
        y_vss_um=y_vss,
        y_vdd_um=y_vdd,
        y_main_bot_um=y_main_bot,
        y_main_top_um=y_main_top,
        y_dummy_bot_um=y_dummy_bot,
        y_dummy_top_um=y_dummy_top,
        y_sd_mid_um=y_sd_mid,
        y_gate_rail_um=y_gate_rail,
        y_tie_um=y_tie,
        x_min_um=x_min,
        x_max_um=x_max,
        x_sd0_um=x_sd0,
        sd_pitch_um=sd_pitch,
        cont_min_active_h_um=cont_min_active_h,
        m1_contact_size_um=m1_contact_size,
        pin_length_um=pin_length,
        pin_x0_um=pin_x0,
        label_dx_um=label_dx,
    )


def derive_nmos_from_tech(
    params: NmosInputParams,
    tech: vtech.Technology,
) -> NmosDerived:
    """Convenience wrapper: VLSIR tech -> PDK settings -> derived geometry."""
    pdk = extract_nmos_pdk_settings(tech)
    return derive_nmos_geometry(params, pdk)


def derive_nmos_from_tech_proto(
    params: NmosInputParams,
    tech_proto: Path,
) -> NmosDerived:
    """Convenience wrapper using serialized VLSIR technology file (.pb/.pbtxt)."""
    tech = read_technology_proto(tech_proto)
    return derive_nmos_from_tech(params, tech)


# -----------------------------------------------------------------------------
# 2) Geometry Generation + Reusable Construction Helpers
# -----------------------------------------------------------------------------


def _layer_index(layout: kdb.Layout, spec: tuple[int, int]) -> int:
    return layout.layer(spec[0], spec[1])


def draw_rect(
    cell: kdb.Cell,
    layout: kdb.Layout,
    layer_idx: int,
    x0_um: float,
    y0_um: float,
    x1_um: float,
    y1_um: float,
) -> None:
    """Generic rectangle-construction helper."""
    insert_box_um(cell, layout, layer_idx, x0_um, y0_um, x1_um, y1_um)


def draw_horizontal_rail(
    cell: kdb.Cell,
    layout: kdb.Layout,
    layer_idx: int,
    x_min_um: float,
    x_max_um: float,
    y_center_um: float,
    width_um: float,
) -> None:
    """Draw a horizontal routing rail."""
    draw_rect(
        cell,
        layout,
        layer_idx,
        x_min_um,
        y_center_um - 0.5 * width_um,
        x_max_um,
        y_center_um + 0.5 * width_um,
    )


def draw_contact_cut(
    cell: kdb.Cell,
    layout: kdb.Layout,
    layer_idx: int,
    x_center_um: float,
    y_center_um: float,
    cut_size_um: float,
) -> None:
    """Draw a contact/via cut square."""
    half = 0.5 * cut_size_um
    draw_rect(
        cell,
        layout,
        layer_idx,
        x_center_um - half,
        y_center_um - half,
        x_center_um + half,
        y_center_um + half,
    )


def draw_metal_pad(
    cell: kdb.Cell,
    layout: kdb.Layout,
    layer_idx: int,
    x_center_um: float,
    y_center_um: float,
    size_um: float,
) -> None:
    """Draw a square metal landing pad."""
    half = 0.5 * size_um
    draw_rect(
        cell,
        layout,
        layer_idx,
        x_center_um - half,
        y_center_um - half,
        x_center_um + half,
        y_center_um + half,
    )


def draw_vertical_strap(
    cell: kdb.Cell,
    layout: kdb.Layout,
    layer_idx: int,
    x_center_um: float,
    y0_um: float,
    y1_um: float,
    width_um: float,
) -> None:
    """Draw a vertical metal strap between two Y locations."""
    half = 0.5 * width_um
    yl, yh = sorted((y0_um, y1_um))
    draw_rect(cell, layout, layer_idx, x_center_um - half, yl, x_center_um + half, yh)


def draw_contact_with_optional_strap(
    cell: kdb.Cell,
    layout: kdb.Layout,
    contact_layer_idx: int,
    metal_layer_idx: int,
    x_center_um: float,
    y_center_um: float,
    contact_size_um: float,
    metal_pad_size_um: float,
    strap_width_um: float,
    y_target_um: float | None,
) -> None:
    """Draw contact cut + metal pad, and optionally strap to a rail."""
    draw_contact_cut(
        cell,
        layout,
        contact_layer_idx,
        x_center_um,
        y_center_um,
        contact_size_um,
    )
    draw_metal_pad(
        cell,
        layout,
        metal_layer_idx,
        x_center_um,
        y_center_um,
        metal_pad_size_um,
    )
    if y_target_um is not None:
        draw_vertical_strap(
            cell,
            layout,
            metal_layer_idx,
            x_center_um,
            y_center_um,
            y_target_um,
            strap_width_um,
        )


def draw_label(
    cell: kdb.Cell,
    layout: kdb.Layout,
    layer_idx: int,
    text: str,
    x_um: float,
    y_um: float,
) -> None:
    """Draw a text label."""
    insert_text_um(cell, layout, layer_idx, text, x_um, y_um)


def build_nmos_layout(derived: NmosDerived) -> tuple[kdb.Layout, kdb.Cell]:
    """Build NMOS + opposite-polarity dummy geometry from derived parameters."""

    layout = kdb.Layout()
    layout.dbu = derived.pdk.dbu_um
    top = layout.create_cell(derived.params.cell_name)

    layers = derived.pdk.layers
    l_active = _layer_index(layout, layers.active)
    l_poly = _layer_index(layout, layers.poly)
    l_cont = _layer_index(layout, layers.contact)
    l_m1 = _layer_index(layout, layers.metal1)
    l_m1_pin = _layer_index(layout, layers.metal1_pin)
    l_nsd = _layer_index(layout, layers.nsd)
    l_psd = _layer_index(layout, layers.psd)
    l_nwell = _layer_index(layout, layers.nwell)
    l_text = _layer_index(layout, layers.text) if layers.text is not None else None
    l_boundary = (
        _layer_index(layout, layers.pr_boundary)
        if layers.pr_boundary is not None
        else None
    )

    pdk = derived.pdk
    params = derived.params

    # Main NMOS active row.
    x_sd_last = derived.x_sd0_um + params.fingers * derived.sd_pitch_um
    x_active_l = derived.x_sd0_um - pdk.cont_enc_active_um
    x_active_r = x_sd_last + pdk.cont_enc_active_um

    draw_rect(
        top,
        layout,
        l_active,
        x_active_l,
        derived.y_main_bot_um,
        x_active_r,
        derived.y_main_top_um,
    )
    draw_rect(
        top,
        layout,
        l_nsd,
        x_active_l - pdk.nsd_over_active_um,
        derived.y_main_bot_um - pdk.nsd_over_active_um,
        x_active_r + pdk.nsd_over_active_um,
        derived.y_main_top_um + pdk.nsd_over_active_um,
    )

    # Dummy PMOS row.
    draw_rect(
        top,
        layout,
        l_active,
        x_active_l,
        derived.y_dummy_bot_um,
        x_active_r,
        derived.y_dummy_top_um,
    )
    draw_rect(
        top,
        layout,
        l_psd,
        x_active_l - pdk.psd_over_active_um,
        derived.y_dummy_bot_um - pdk.psd_over_active_um,
        x_active_r + pdk.psd_over_active_um,
        derived.y_dummy_top_um + pdk.psd_over_active_um,
    )
    draw_rect(
        top,
        layout,
        l_nwell,
        x_active_l - pdk.nwell_over_active_um,
        derived.y_dummy_bot_um - pdk.nwell_over_active_um,
        x_active_r + pdk.nwell_over_active_um,
        derived.y_dummy_top_um + pdk.nwell_over_active_um,
    )

    # Gate fingers.
    gate_boxes: list[tuple[float, float]] = []
    y_gate_bot = derived.y_main_bot_um - pdk.poly_over_active_um
    y_gate_top = derived.y_dummy_top_um + pdk.poly_over_active_um
    for idx in range(params.fingers):
        x_sd_center = derived.x_sd0_um + idx * derived.sd_pitch_um
        x_gate_l = x_sd_center + 0.5 * pdk.cont_size_um + pdk.cont_gate_spacing_um
        x_gate_r = x_gate_l + params.gate_length_um
        gate_boxes.append((x_gate_l, x_gate_r))
        draw_rect(top, layout, l_poly, x_gate_l, y_gate_bot, x_gate_r, y_gate_top)

    # Poly tie-bar.
    tie_h = pdk.cont_size_um + 2.0 * pdk.cont_enc_poly_um
    x_tie_l = gate_boxes[0][0]
    x_tie_r = gate_boxes[-1][1]
    draw_rect(
        top,
        layout,
        l_poly,
        x_tie_l,
        derived.y_tie_um - 0.5 * tie_h,
        x_tie_r,
        derived.y_tie_um + 0.5 * tie_h,
    )

    # M1 rails.
    draw_horizontal_rail(
        top,
        layout,
        l_m1,
        derived.x_min_um,
        derived.x_max_um,
        derived.y_vss_um,
        derived.rail_width_um,
    )
    draw_horizontal_rail(
        top,
        layout,
        l_m1,
        derived.x_min_um,
        derived.x_max_um,
        derived.y_sd_mid_um,
        derived.rail_width_um,
    )
    draw_horizontal_rail(
        top,
        layout,
        l_m1,
        derived.x_min_um,
        derived.x_max_um,
        derived.y_gate_rail_um,
        derived.rail_width_um,
    )
    draw_horizontal_rail(
        top,
        layout,
        l_m1,
        derived.x_min_um,
        derived.x_max_um,
        derived.y_vdd_um,
        derived.rail_width_um,
    )

    # Main source/drain contacts.
    y_main_cont = 0.5 * (derived.y_main_bot_um + derived.y_main_top_um)
    for idx in range(params.fingers + 1):
        x_sd_center = derived.x_sd0_um + idx * derived.sd_pitch_um
        if params.connect_main_sd_to_rails:
            y_target = derived.y_vss_um if idx % 2 == 0 else derived.y_sd_mid_um
        else:
            y_target = None
        draw_contact_with_optional_strap(
            top,
            layout,
            l_cont,
            l_m1,
            x_sd_center,
            y_main_cont,
            pdk.cont_size_um,
            derived.m1_contact_size_um,
            pdk.m1_width_um,
            y_target,
        )

    # Dummy ties.
    if params.connect_dummy_to_vdd:
        y_dummy_cont = 0.5 * (derived.y_dummy_bot_um + derived.y_dummy_top_um)
        for idx in (0, params.fingers):
            x_sd_center = derived.x_sd0_um + idx * derived.sd_pitch_um
            draw_contact_with_optional_strap(
                top,
                layout,
                l_cont,
                l_m1,
                x_sd_center,
                y_dummy_cont,
                pdk.cont_size_um,
                derived.m1_contact_size_um,
                pdk.m1_width_um,
                derived.y_vdd_um,
            )

    # Gate contact.
    x_gate_cont = x_tie_l + pdk.cont_enc_poly_um + 0.5 * pdk.cont_size_um
    draw_contact_with_optional_strap(
        top,
        layout,
        l_cont,
        l_m1,
        x_gate_cont,
        derived.y_tie_um,
        pdk.cont_size_um,
        derived.m1_contact_size_um,
        pdk.m1_width_um,
        derived.y_gate_rail_um if params.connect_gate_to_gate_rail else None,
    )

    # Pins and labels.
    for pin_name, y_pin in (
        ("S", derived.y_vss_um),
        ("D", derived.y_sd_mid_um),
        ("G", derived.y_gate_rail_um),
        ("VDD_DMY", derived.y_vdd_um),
    ):
        draw_rect(
            top,
            layout,
            l_m1_pin,
            derived.pin_x0_um,
            y_pin - 0.5 * derived.rail_width_um,
            derived.pin_x0_um + derived.pin_length_um,
            y_pin + 0.5 * derived.rail_width_um,
        )
        if l_text is not None:
            draw_label(
                top,
                layout,
                l_text,
                pin_name,
                derived.pin_x0_um + derived.pin_length_um + derived.label_dx_um,
                y_pin,
            )

    if l_boundary is not None:
        draw_rect(
            top,
            layout,
            l_boundary,
            derived.x_min_um,
            derived.y_vss_um - 0.5 * derived.rail_width_um,
            derived.x_max_um,
            derived.y_vdd_um + 0.5 * derived.rail_width_um,
        )

    return layout, top


def generate_nmos_unit(
    derived: NmosDerived,
    out_dir: Path,
    domain: str = "frida.layout",
    write_debug_gds: bool = False,
) -> ExportArtifacts:
    """Generate and export NMOS unit as VLSIR raw (+ optional debug GDS)."""

    layout, _top = build_nmos_layout(derived)
    return export_layout(
        layout=layout,
        out_dir=out_dir,
        stem=derived.params.cell_name,
        domain=domain,
        write_debug_gds=write_debug_gds,
    )


# -----------------------------------------------------------------------------
# 3) Pytest Entrypoint
# -----------------------------------------------------------------------------


def _token_from_value(value: str | int | float | bool) -> vtech.RuleToken:
    token = vtech.RuleToken()
    if isinstance(value, bool):
        token.boolean = value
    elif isinstance(value, int):
        token.integer = value
    elif isinstance(value, float):
        token.real = value
    else:
        token.text = value
    return token


def _stmt(keyword: str, *tokens: str | int | float | bool) -> vtech.RuleStatement:
    raw = f"{keyword} {' '.join(str(t) for t in tokens)}".strip()
    return vtech.RuleStatement(
        keyword=keyword,
        tokens=[_token_from_value(token) for token in tokens],
        raw=raw,
    )


def _layer_rules(name: str, width: float, spacing: float) -> vtech.LayerRuleSet:
    return vtech.LayerRuleSet(
        name=name,
        rules=[
            _stmt("WIDTH", width),
            _stmt("SPACING", spacing),
        ],
    )


def _pair_rules(
    first: str,
    second: str,
    keyword: str,
    value: float,
) -> vtech.LayerPairRuleSet:
    return vtech.LayerPairRuleSet(
        first_layer=first,
        second_layer=second,
        rules=[_stmt(keyword, value, value)],
        source="pytest",
    )


def _build_pytest_technology() -> vtech.Technology:
    """Create a compact technology message for generator smoke testing."""

    tech = vtech.Technology(name="pytest130")
    tech.rules.lef_units.database_microns = 1000
    tech.rules.manufacturing_grid_microns = 0.001

    tech.layers.extend(
        [
            vtech.LayerInfo(name="ACTIVE", index=1, sub_index=0),
            vtech.LayerInfo(name="POLY", index=5, sub_index=0),
            vtech.LayerInfo(name="CONT", index=6, sub_index=0),
            vtech.LayerInfo(name="NSD", index=7, sub_index=0),
            vtech.LayerInfo(name="METAL1", index=8, sub_index=0),
            vtech.LayerInfo(name="M1.PIN", index=8, sub_index=2),
            vtech.LayerInfo(name="PSD", index=14, sub_index=0),
            vtech.LayerInfo(name="NWELL", index=31, sub_index=0),
            vtech.LayerInfo(name="TEXT", index=63, sub_index=0),
            vtech.LayerInfo(name="PR_BOUNDARY", index=189, sub_index=0),
        ]
    )

    tech.rules.layers.extend(
        [
            _layer_rules("ACTIVE", width=0.15, spacing=0.18),
            _layer_rules("POLY", width=0.13, spacing=0.16),
            _layer_rules("CONT", width=0.16, spacing=0.18),
            _layer_rules("METAL1", width=0.14, spacing=0.14),
        ]
    )

    tech.rules.layer_pairs.extend(
        [
            _pair_rules("ACTIVE", "CONT", "ENCLOSURE", 0.07),
            _pair_rules("POLY", "CONT", "ENCLOSURE", 0.07),
            vtech.LayerPairRuleSet(
                first_layer="POLY",
                second_layer="CONT",
                rules=[_stmt("SPACING", 0.11)],
                source="pytest",
            ),
            _pair_rules("METAL1", "CONT", "ENCLOSURE", 0.06),
            _pair_rules("ACTIVE", "POLY", "ENCLOSURE", 0.18),
            _pair_rules("ACTIVE", "NSD", "ENCLOSURE", 0.18),
            _pair_rules("ACTIVE", "PSD", "ENCLOSURE", 0.18),
            _pair_rules("ACTIVE", "NWELL", "ENCLOSURE", 0.31),
        ]
    )
    return tech


def test_nmos_generator_smoke(tmp_path: Path) -> None:
    """Pytest smoke test for strict VLSIR-driven NMOS generation."""

    tech = _build_pytest_technology()
    params = NmosInputParams(
        cell_name="pytest_nmos_unit_nf8",
        fingers=8,
        gate_length_um=0.13,
        finger_width_um=0.42,
        dummy_width_scale=0.75,
        track_count=9,
        rail_width_tracks=1.0,
        side_margin_tracks=0.6,
        row_margin_tracks=0.6,
        gate_track_offset=1,
        connect_main_sd_to_rails=True,
        connect_dummy_to_vdd=True,
        connect_gate_to_gate_rail=True,
    )

    derived = derive_nmos_from_tech(params, tech)
    artifacts = generate_nmos_unit(
        derived=derived,
        out_dir=tmp_path,
        domain="frida.layout",
        write_debug_gds=True,
    )

    assert artifacts.pb.exists()
    assert artifacts.pbtxt.exists()
    assert artifacts.gds is not None and artifacts.gds.exists()


@pytest.mark.skipif(
    not (
        Path("scratch/ihp130.tech.pbtxt").exists()
        or Path("scratch/ihp130.tech.pb").exists()
    ),
    reason="Requires pre-generated scratch/ihp130 tech proto.",
)
def test_nmos_generator_with_real_tech(tmp_path: Path) -> None:
    """Optional smoke run against a real serialized technology file."""

    tech_path = Path("scratch/ihp130.tech.pbtxt")
    if not tech_path.exists():
        tech_path = Path("scratch/ihp130.tech.pb")

    params = NmosInputParams(
        cell_name="ihp130_nmos_unit_nf8",
        fingers=8,
        gate_length_um=0.13,
        finger_width_um=0.42,
        dummy_width_scale=0.75,
        track_count=9,
        rail_width_tracks=1.0,
        side_margin_tracks=0.6,
        row_margin_tracks=0.6,
        gate_track_offset=1,
        connect_main_sd_to_rails=True,
        connect_dummy_to_vdd=True,
        connect_gate_to_gate_rail=True,
    )

    try:
        derived = derive_nmos_from_tech_proto(params, tech_path)
    except ValueError as err:
        pytest.skip(f"Real tech proto is missing strict NMOS inputs: {err}")

    artifacts = generate_nmos_unit(
        derived=derived,
        out_dir=tmp_path,
        domain="frida.layout",
        write_debug_gds=True,
    )

    assert artifacts.pb.exists()
    assert artifacts.pbtxt.exists()
