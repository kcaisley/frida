"""
MOM capacitor primitive generator (single ring + internal cap section).

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
    technology_rule_spacing,
    technology_rule_value,
)


# -----------------------------------------------------------------------------
# 1) Input + Derived-Dimension Computation
# -----------------------------------------------------------------------------


@dataclass(frozen=True)
class MomcapInputParams:
    """User-level inputs for MOM-cap unit generation."""

    cell_name: str
    top_layer_name: str
    bottom_layer_name: str
    top_pin_layer_name: str
    bottom_pin_layer_name: str
    cap_width_um: float
    cap_height_um: float
    fingers: int
    ring_width_tracks: float
    ring_margin_tracks: float
    finger_width_tracks: float
    finger_spacing_tracks: float
    connect_top_bus_to_ring: bool
    add_boundary: bool


@dataclass(frozen=True)
class MomcapLayerSpecs:
    """Resolved layer-number / purpose specs from VLSIR technology."""

    top: tuple[int, int]
    bottom: tuple[int, int]
    top_pin: tuple[int, int]
    bottom_pin: tuple[int, int]
    text: tuple[int, int] | None
    boundary: tuple[int, int] | None


@dataclass(frozen=True)
class MomcapPdkSettings:
    """Technology settings required for MOM-cap generation."""

    tech_name: str
    dbu_um: float
    manufacturing_grid_um: float
    layers: MomcapLayerSpecs
    top_width_um: float
    top_spacing_um: float
    bottom_width_um: float
    bottom_spacing_um: float


@dataclass(frozen=True)
class MomcapDerived:
    """Fully derived geometry for one MOM-cap unit."""

    params: MomcapInputParams
    pdk: MomcapPdkSettings
    top_pitch_um: float
    bottom_pitch_um: float
    ring_width_um: float
    ring_margin_um: float
    finger_width_um: float
    finger_spacing_um: float
    bus_clear_um: float
    bus_top_width_um: float
    bus_bottom_width_um: float
    pitch_um: float
    needed_inner_width_um: float
    outer_width_um: float
    outer_height_um: float
    inner_x0_um: float
    inner_y0_um: float
    inner_x1_um: float
    inner_y1_um: float
    top_bus_y0_um: float
    top_bus_y1_um: float
    bottom_bus_y0_um: float
    bottom_bus_y1_um: float
    tie_width_um: float
    tie_x0_um: float
    tie_x1_um: float
    pin_width_um: float
    pin_inset_um: float
    label_dy_um: float


def _require_positive(name: str, value: float) -> float:
    if value <= 0:
        raise ValueError(f"{name} must be > 0, got {value}.")
    return value


def _require_nonnegative(name: str, value: float) -> float:
    if value < 0:
        raise ValueError(f"{name} must be >= 0, got {value}.")
    return value


def _require_layer_spec_by_name(
    tech: vtech.Technology,
    layer_name: str,
    logical_name: str,
) -> tuple[int, int]:
    target = layer_name.upper()
    for info in tech.layers:
        if info.name.upper() == target:
            return int(info.index), int(info.sub_index)
    raise ValueError(
        f"Could not resolve required layer '{logical_name}' with name '{layer_name}'."
    )


def _require_layer_width_spacing(tech: vtech.Technology, layer_name: str) -> tuple[float, float]:
    width = technology_rule_value(tech, (layer_name,), "WIDTH")
    if width is None:
        width = technology_rule_value(tech, (layer_name,), "MINWIDTH")
    if width is None:
        raise ValueError(f"Missing WIDTH/MINWIDTH rule for layer '{layer_name}'.")

    spacing = technology_rule_spacing(tech, (layer_name,), width=width, prl=0.0)
    if spacing is None:
        raise ValueError(f"Missing SPACING rule for layer '{layer_name}'.")
    return width, spacing


def extract_momcap_pdk_settings(
    tech: vtech.Technology,
    params: MomcapInputParams,
) -> MomcapPdkSettings:
    """
    Extract strict MOM-cap technology settings from VLSIR technology.

    This function does not apply process-specific numeric defaults.
    """

    db_units = int(tech.rules.lef_units.database_microns)
    if db_units <= 0:
        raise ValueError("Technology.rules.lef_units.database_microns must be > 0.")
    dbu_um = 1.0 / float(db_units)

    manufacturing_grid_um = float(tech.rules.manufacturing_grid_microns)
    if manufacturing_grid_um <= 0:
        raise ValueError("Technology.rules.manufacturing_grid_microns must be > 0.")

    layers = MomcapLayerSpecs(
        top=_require_layer_spec_by_name(tech, params.top_layer_name, "top_layer"),
        bottom=_require_layer_spec_by_name(
            tech,
            params.bottom_layer_name,
            "bottom_layer",
        ),
        top_pin=_require_layer_spec_by_name(
            tech,
            params.top_pin_layer_name,
            "top_pin_layer",
        ),
        bottom_pin=_require_layer_spec_by_name(
            tech,
            params.bottom_pin_layer_name,
            "bottom_pin_layer",
        ),
        text=next(
            (
                (int(info.index), int(info.sub_index))
                for info in tech.layers
                if info.name.upper() in {"TEXT", "LABEL"}
            ),
            None,
        ),
        boundary=next(
            (
                (int(info.index), int(info.sub_index))
                for info in tech.layers
                if info.name.upper() in {"PR_BOUNDARY", "BOUNDARY", "OVERLAP", "OUTLINE"}
            ),
            None,
        ),
    )

    top_width_um, top_spacing_um = _require_layer_width_spacing(tech, params.top_layer_name)
    bottom_width_um, bottom_spacing_um = _require_layer_width_spacing(
        tech,
        params.bottom_layer_name,
    )

    return MomcapPdkSettings(
        tech_name=tech.name,
        dbu_um=dbu_um,
        manufacturing_grid_um=manufacturing_grid_um,
        layers=layers,
        top_width_um=top_width_um,
        top_spacing_um=top_spacing_um,
        bottom_width_um=bottom_width_um,
        bottom_spacing_um=bottom_spacing_um,
    )


def derive_momcap_geometry(params: MomcapInputParams, pdk: MomcapPdkSettings) -> MomcapDerived:
    """Compute all scaled and derived MOM-cap geometry from input + PDK settings."""

    if params.fingers < 2:
        raise ValueError("fingers must be >= 2")

    _require_positive("cap_width_um", params.cap_width_um)
    _require_positive("cap_height_um", params.cap_height_um)
    _require_positive("ring_width_tracks", params.ring_width_tracks)
    _require_nonnegative("ring_margin_tracks", params.ring_margin_tracks)
    _require_positive("finger_width_tracks", params.finger_width_tracks)
    _require_positive("finger_spacing_tracks", params.finger_spacing_tracks)

    top_pitch = pdk.top_width_um + pdk.top_spacing_um
    bottom_pitch = pdk.bottom_width_um + pdk.bottom_spacing_um
    ref_pitch = max(top_pitch, bottom_pitch)

    ring_width = params.ring_width_tracks * top_pitch
    ring_margin = params.ring_margin_tracks * ref_pitch
    finger_width = params.finger_width_tracks * ref_pitch
    finger_spacing = params.finger_spacing_tracks * ref_pitch

    if ring_width < pdk.top_width_um:
        raise ValueError("ring_width_tracks yields width below top-layer minimum width.")
    if finger_width < max(pdk.top_width_um, pdk.bottom_width_um):
        raise ValueError("finger_width_tracks yields width below metal minimum width.")
    if finger_spacing < max(pdk.top_spacing_um, pdk.bottom_spacing_um):
        raise ValueError("finger_spacing_tracks yields spacing below metal spacing minimum.")

    bus_clear = max(pdk.top_spacing_um, pdk.bottom_spacing_um)
    bus_top_width = max(finger_width, pdk.top_width_um)
    bus_bottom_width = max(finger_width, pdk.bottom_width_um)

    min_margin = max(
        bus_clear + bus_top_width,
        bus_clear + bus_bottom_width,
        pdk.manufacturing_grid_um,
    )
    if ring_margin < min_margin:
        raise ValueError(
            "ring_margin_tracks yields insufficient space for inner buses and spacing rules."
        )

    pitch = finger_width + finger_spacing
    needed_inner_width = params.fingers * finger_width + (params.fingers - 1) * finger_spacing
    if needed_inner_width > params.cap_width_um:
        raise ValueError(
            "cap_width_um is too small for requested finger count and dimensions. "
            f"needed={needed_inner_width:.3f}um"
        )

    outer_width = params.cap_width_um + 2.0 * (ring_width + ring_margin)
    outer_height = params.cap_height_um + 2.0 * (ring_width + ring_margin)

    inner_x0 = ring_width + ring_margin
    inner_y0 = ring_width + ring_margin
    inner_x1 = inner_x0 + params.cap_width_um
    inner_y1 = inner_y0 + params.cap_height_um

    top_bus_y0 = inner_y1 + bus_clear
    top_bus_y1 = top_bus_y0 + bus_top_width
    bottom_bus_y1 = inner_y0 - bus_clear
    bottom_bus_y0 = bottom_bus_y1 - bus_bottom_width

    if top_bus_y1 > outer_height - ring_width:
        raise ValueError("Top bus overflows available ring-margin area.")
    if bottom_bus_y0 < ring_width:
        raise ValueError("Bottom bus overflows available ring-margin area.")

    tie_width = max(bus_top_width, pdk.top_width_um)
    tie_x0 = inner_x0 + bus_clear
    tie_x1 = tie_x0 + tie_width
    if tie_x1 > inner_x1:
        raise ValueError("Top-ring tie geometry does not fit inner width.")

    pin_width = max(pdk.top_width_um, pdk.bottom_width_um)
    pin_inset = pdk.manufacturing_grid_um
    label_dy = max(pdk.manufacturing_grid_um, 0.5 * max(pdk.top_spacing_um, pdk.bottom_spacing_um))

    return MomcapDerived(
        params=params,
        pdk=pdk,
        top_pitch_um=top_pitch,
        bottom_pitch_um=bottom_pitch,
        ring_width_um=ring_width,
        ring_margin_um=ring_margin,
        finger_width_um=finger_width,
        finger_spacing_um=finger_spacing,
        bus_clear_um=bus_clear,
        bus_top_width_um=bus_top_width,
        bus_bottom_width_um=bus_bottom_width,
        pitch_um=pitch,
        needed_inner_width_um=needed_inner_width,
        outer_width_um=outer_width,
        outer_height_um=outer_height,
        inner_x0_um=inner_x0,
        inner_y0_um=inner_y0,
        inner_x1_um=inner_x1,
        inner_y1_um=inner_y1,
        top_bus_y0_um=top_bus_y0,
        top_bus_y1_um=top_bus_y1,
        bottom_bus_y0_um=bottom_bus_y0,
        bottom_bus_y1_um=bottom_bus_y1,
        tie_width_um=tie_width,
        tie_x0_um=tie_x0,
        tie_x1_um=tie_x1,
        pin_width_um=pin_width,
        pin_inset_um=pin_inset,
        label_dy_um=label_dy,
    )


def derive_momcap_from_tech(
    params: MomcapInputParams,
    tech: vtech.Technology,
) -> MomcapDerived:
    """Convenience wrapper: VLSIR tech -> PDK settings -> derived geometry."""
    pdk = extract_momcap_pdk_settings(tech, params)
    return derive_momcap_geometry(params, pdk)


def derive_momcap_from_tech_proto(
    params: MomcapInputParams,
    tech_proto: Path,
) -> MomcapDerived:
    """Convenience wrapper using serialized VLSIR technology file (.pb/.pbtxt)."""
    tech = read_technology_proto(tech_proto)
    return derive_momcap_from_tech(params, tech)


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


def draw_ring(
    cell: kdb.Cell,
    layout: kdb.Layout,
    layer_idx: int,
    x0_um: float,
    y0_um: float,
    x1_um: float,
    y1_um: float,
    width_um: float,
) -> None:
    """Draw rectangular ring as four rectangles."""
    draw_rect(cell, layout, layer_idx, x0_um, y0_um, x1_um, y0_um + width_um)
    draw_rect(cell, layout, layer_idx, x0_um, y1_um - width_um, x1_um, y1_um)
    draw_rect(cell, layout, layer_idx, x0_um, y0_um + width_um, x0_um + width_um, y1_um - width_um)
    draw_rect(cell, layout, layer_idx, x1_um - width_um, y0_um + width_um, x1_um, y1_um - width_um)


def draw_label(
    cell: kdb.Cell,
    layout: kdb.Layout,
    layer_idx: int,
    text: str,
    x_um: float,
    y_um: float,
) -> None:
    """Draw text label."""
    insert_text_um(cell, layout, layer_idx, text, x_um, y_um)


def build_momcap_layout(derived: MomcapDerived) -> tuple[kdb.Layout, kdb.Cell]:
    """Build MOM-cap geometry from derived dimensions."""

    layout = kdb.Layout()
    layout.dbu = derived.pdk.dbu_um
    top = layout.create_cell(derived.params.cell_name)

    layers = derived.pdk.layers
    l_top = _layer_index(layout, layers.top)
    l_bottom = _layer_index(layout, layers.bottom)
    l_top_pin = _layer_index(layout, layers.top_pin)
    l_bottom_pin = _layer_index(layout, layers.bottom_pin)
    l_text = _layer_index(layout, layers.text) if layers.text is not None else None
    l_boundary = _layer_index(layout, layers.boundary) if layers.boundary is not None else None

    # Top-plate ring.
    draw_ring(
        top,
        layout,
        l_top,
        0.0,
        0.0,
        derived.outer_width_um,
        derived.outer_height_um,
        derived.ring_width_um,
    )

    # Inner buses.
    draw_rect(
        top,
        layout,
        l_top,
        derived.inner_x0_um,
        derived.top_bus_y0_um,
        derived.inner_x1_um,
        derived.top_bus_y1_um,
    )
    draw_rect(
        top,
        layout,
        l_bottom,
        derived.inner_x0_um,
        derived.bottom_bus_y0_um,
        derived.inner_x1_um,
        derived.bottom_bus_y1_um,
    )

    # Interdigitated fingers.
    x_finger0 = derived.inner_x0_um + 0.5 * (
        derived.params.cap_width_um - derived.needed_inner_width_um
    )
    for idx in range(derived.params.fingers):
        x0 = x_finger0 + idx * derived.pitch_um
        x1 = x0 + derived.finger_width_um
        if idx % 2 == 0:
            draw_rect(
                top,
                layout,
                l_top,
                x0,
                derived.inner_y0_um,
                x1,
                derived.inner_y1_um,
            )
            draw_rect(
                top,
                layout,
                l_top,
                x0,
                derived.inner_y1_um,
                x1,
                derived.top_bus_y0_um,
            )
        else:
            draw_rect(
                top,
                layout,
                l_bottom,
                x0,
                derived.inner_y0_um,
                x1,
                derived.inner_y1_um,
            )
            draw_rect(
                top,
                layout,
                l_bottom,
                x0,
                derived.bottom_bus_y1_um,
                x1,
                derived.inner_y0_um,
            )

    # Optional top bus tie to ring.
    if derived.params.connect_top_bus_to_ring:
        draw_rect(
            top,
            layout,
            l_top,
            derived.tie_x0_um,
            derived.top_bus_y1_um,
            derived.tie_x1_um,
            derived.outer_height_um - derived.ring_width_um,
        )

    # Pins.
    top_pin_y = derived.outer_height_um - 0.5 * derived.ring_width_um
    draw_rect(
        top,
        layout,
        l_top_pin,
        derived.outer_width_um - derived.ring_width_um + derived.pin_inset_um,
        top_pin_y - 0.5 * derived.pin_width_um,
        derived.outer_width_um - derived.pin_inset_um,
        top_pin_y + 0.5 * derived.pin_width_um,
    )

    bot_pin_y = 0.5 * (derived.bottom_bus_y0_um + derived.bottom_bus_y1_um)
    draw_rect(
        top,
        layout,
        l_bottom_pin,
        derived.inner_x1_um - derived.ring_width_um,
        bot_pin_y - 0.5 * derived.pin_width_um,
        derived.inner_x1_um - derived.pin_inset_um,
        bot_pin_y + 0.5 * derived.pin_width_um,
    )

    if l_text is not None:
        draw_label(
            top,
            layout,
            l_text,
            "TOP",
            derived.outer_width_um - derived.ring_width_um,
            top_pin_y + derived.label_dy_um,
        )
        draw_label(
            top,
            layout,
            l_text,
            "BOT",
            derived.inner_x1_um - derived.ring_width_um,
            bot_pin_y + derived.label_dy_um,
        )

    if derived.params.add_boundary and l_boundary is not None:
        draw_rect(
            top,
            layout,
            l_boundary,
            0.0,
            0.0,
            derived.outer_width_um,
            derived.outer_height_um,
        )

    return layout, top


def generate_momcap_unit(
    derived: MomcapDerived,
    out_dir: Path,
    domain: str = "frida.layout",
    write_debug_gds: bool = False,
) -> ExportArtifacts:
    """Generate and export MOM-cap unit as VLSIR raw (+ optional debug GDS)."""

    layout, _top = build_momcap_layout(derived)
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


def _build_pytest_technology() -> vtech.Technology:
    """Create a compact technology message for MOM-cap smoke testing."""

    tech = vtech.Technology(name="pytest130")
    tech.rules.lef_units.database_microns = 1000
    tech.rules.manufacturing_grid_microns = 0.001

    tech.layers.extend(
        [
            vtech.LayerInfo(name="M5", index=67, sub_index=0),
            vtech.LayerInfo(name="M6", index=68, sub_index=0),
            vtech.LayerInfo(name="M5.PIN", index=67, sub_index=2),
            vtech.LayerInfo(name="M6.PIN", index=68, sub_index=2),
            vtech.LayerInfo(name="TEXT", index=63, sub_index=0),
            vtech.LayerInfo(name="PR_BOUNDARY", index=189, sub_index=0),
        ]
    )

    tech.rules.layers.extend(
        [
            _layer_rules("M5", width=0.20, spacing=0.20),
            _layer_rules("M6", width=0.28, spacing=0.28),
        ]
    )
    return tech


def test_momcap_generator_smoke(tmp_path: Path) -> None:
    """Pytest smoke test for strict VLSIR-driven MOM-cap generation."""

    tech = _build_pytest_technology()
    params = MomcapInputParams(
        cell_name="pytest_momcap_ring_f8",
        top_layer_name="M6",
        bottom_layer_name="M5",
        top_pin_layer_name="M6.PIN",
        bottom_pin_layer_name="M5.PIN",
        cap_width_um=8.0,
        cap_height_um=5.0,
        fingers=8,
        ring_width_tracks=1.0,
        ring_margin_tracks=2.0,
        finger_width_tracks=0.8,
        finger_spacing_tracks=0.8,
        connect_top_bus_to_ring=True,
        add_boundary=True,
    )

    derived = derive_momcap_from_tech(params, tech)
    artifacts = generate_momcap_unit(
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
def test_momcap_generator_with_real_tech(tmp_path: Path) -> None:
    """Optional smoke run against a real serialized technology file."""

    tech_path = Path("scratch/ihp130.tech.pbtxt")
    if not tech_path.exists():
        tech_path = Path("scratch/ihp130.tech.pb")

    params = MomcapInputParams(
        cell_name="ihp130_momcap_ring_unit_f8",
        top_layer_name="Metal5",
        bottom_layer_name="Metal4",
        top_pin_layer_name="Metal5",
        bottom_pin_layer_name="Metal4",
        cap_width_um=8.0,
        cap_height_um=5.0,
        fingers=8,
        ring_width_tracks=1.0,
        ring_margin_tracks=2.0,
        finger_width_tracks=1.0,
        finger_spacing_tracks=1.0,
        connect_top_bus_to_ring=True,
        add_boundary=True,
    )

    try:
        derived = derive_momcap_from_tech_proto(params, tech_path)
    except ValueError as err:
        pytest.skip(f"Real tech proto is missing strict MOM-cap inputs: {err}")

    artifacts = generate_momcap_unit(
        derived=derived,
        out_dir=tmp_path,
        domain="frida.layout",
        write_debug_gds=True,
    )

    assert artifacts.pb.exists()
    assert artifacts.pbtxt.exists()
