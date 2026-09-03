"""Rule-derived weighted MOM-capacitor family and layout runner.

This module is the standalone entry point for the same unit cells instantiated
by :mod:`flow.cdac.layout`.  It intentionally contains no physical distance;
all geometry comes from the selected PDK rule deck.
"""

from __future__ import annotations

from dataclasses import dataclass
from importlib import import_module
from pathlib import Path

from klayout import db

from flow.cdac.laygen import (
    CdacLayoutParams,
    UnitLengthCapFamilyParams,
    _build_unit_library,
    _calc_unit_geometry,
)
from flow.cdac.subckt import CdacParams, RedunStrat
from flow.layout.commands import primitive_main
from flow.layout.dsl import load_generic_layers
from flow.layout.image import gds_to_png_with_pdk_style
from flow.layout.serialize import export_layout
from flow.layout.tech import load_layer_map, remap_layers


@dataclass(frozen=True)
class MomcapParams:
    """Dimensionless family and stack selection for weighted MOM units."""

    max_weight: int
    tail_tracks: int = 5
    route_layer: int = 4
    shield_layer: int = 5
    active_layers: tuple[int, ...] = (6,)

    def layout_params(self, technology: str) -> CdacLayoutParams:
        """Convert to the shared unit generator's validated configuration."""

        return CdacLayoutParams(
            cdac=CdacParams(n_dac=1, n_extra=0, redun_strat=RedunStrat.RDX2),
            family=UnitLengthCapFamilyParams(coarse_weight=self.max_weight, tail_tracks=self.tail_tracks),
            technology=technology,
            route_layer=self.route_layer,
            shield_layer=self.shield_layer,
            active_layers=self.active_layers,
            top_cell="MOMCAP_FAMILY",
        )


def momcap(params: MomcapParams, tech_name: str) -> db.Layout:
    """Generate the complete ``1..max_weight`` unit library for a PDK."""

    pdk_layout = import_module(f"pdk.{tech_name}.layout")
    layout_params = params.layout_params(tech_name)
    geometry = _calc_unit_geometry(layout_params, pdk_layout.rule_deck())
    layout = db.Layout()
    layout.dbu = pdk_layout.DBU
    generic = load_generic_layers(layout)
    units = _build_unit_library(layout, generic, layout_params, geometry)
    top = layout.create_cell("MOMCAP_FAMILY")
    pitch_um = geometry.unit_pitch / 1000.0
    for index, weight in enumerate(range(1, params.max_weight + 1)):
        top.insert(db.DCellInstArray(units[weight].cell_index(), db.DTrans(index * pitch_um, 0)))
    width_um = ((params.max_weight - 1) * geometry.unit_pitch + geometry.outer_width) / 1000.0
    height_um = geometry.outer_height / 1000.0
    top.shapes(generic.PR_BOUNDARY).insert(db.DBox(0, 0, width_um, height_um))
    return layout


def run_layout(tech: str, mode: str, visual: bool, outdir: Path) -> None:
    """Emit either the minimum unit or the complete FRIDA-sized unit family."""

    max_weight = 1 if mode == "min" else UnitLengthCapFamilyParams().coarse_weight
    params = MomcapParams(max_weight=max_weight)
    layout = momcap(params, tech)
    remap_layers(layout, load_layer_map(tech))
    stem = f"momcap_family_w1_to_w{max_weight}"
    artifacts = export_layout(
        layout=layout,
        out_dir=outdir,
        stem=stem,
        domain=f"frida.layout.{tech}",
        write_debug_gds=visual,
    )
    if visual and artifacts.gds is not None:
        gds_to_png_with_pdk_style(artifacts.gds, tech=tech, out_dir=outdir)


if __name__ == "__main__":
    primitive_main("flow.momcap.primitive", run_layout, default_tech="tsmc65")
