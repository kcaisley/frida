"""Static layout metadata for IHP130.

Data in this module is intentionally static and manually transcribed.
No runtime parsing of TECH LEF or LYT files is performed.
"""

from pathlib import Path

from flow.layout.layout import (
    LayerInfoData,
    LayerPairRuleSetData,
    LayerRuleSetData,
    RuleDeckData,
    TechArtifacts,
    TechnologyData,
    merge_rule_decks,
    rule_statement,
    write_tech_to_proto,
)

PDK_NAME = "ihp130"
# Manual transcription sources (not loaded/ parsed at runtime):
# - TECH LEF: /home/kcaisley/libs/IHP-Open-PDK/ihp-sg13g2/libs.ref/sg13g2_stdcell/lef/sg13g2_tech.lef
# - Layer map: /home/kcaisley/libs/IHP-Open-PDK/ihp-sg13g2/libs.tech/klayout/tech/sg13g2.lyt


def layer_infos() -> tuple[LayerInfoData, ...]:
    """Static layer-purpose map for layout generation and export."""
    return (
        LayerInfoData(name="ACTIVE", index=1, sub_index=0),
        LayerInfoData(name="POLY", index=2, sub_index=0),
        LayerInfoData(name="CONT", index=3, sub_index=0),
        LayerInfoData(name="NSD", index=4, sub_index=0),
        LayerInfoData(name="PSD", index=5, sub_index=0),
        LayerInfoData(name="NWELL", index=6, sub_index=0),
        LayerInfoData(name="METAL1", index=7, sub_index=0),
        LayerInfoData(name="M1.PIN", index=7, sub_index=1, purpose_type="PIN"),
        LayerInfoData(name="VIA1", index=8, sub_index=0),
        LayerInfoData(name="METAL2", index=9, sub_index=0),
        LayerInfoData(name="M2.PIN", index=9, sub_index=1, purpose_type="PIN"),
        LayerInfoData(name="VIA2", index=10, sub_index=0),
        LayerInfoData(name="METAL3", index=11, sub_index=0),
        LayerInfoData(name="M3.PIN", index=11, sub_index=1, purpose_type="PIN"),
        LayerInfoData(name="VIA3", index=12, sub_index=0),
        LayerInfoData(name="METAL4", index=13, sub_index=0),
        LayerInfoData(name="M4.PIN", index=13, sub_index=1, purpose_type="PIN"),
        LayerInfoData(name="VIA4", index=14, sub_index=0),
        LayerInfoData(name="METAL5", index=15, sub_index=0),
        LayerInfoData(name="M5.PIN", index=15, sub_index=1, purpose_type="PIN"),
        LayerInfoData(name="TOPVIA1", index=16, sub_index=0),
        LayerInfoData(name="TOPMETAL1", index=17, sub_index=0),
        LayerInfoData(name="TM1.PIN", index=17, sub_index=1, purpose_type="PIN"),
        LayerInfoData(name="TOPVIA2", index=18, sub_index=0),
        LayerInfoData(name="TOPMETAL2", index=19, sub_index=0),
        LayerInfoData(name="TM2.PIN", index=19, sub_index=1, purpose_type="PIN"),
        LayerInfoData(name="TEXT", index=63, sub_index=0, purpose_type="LABEL"),
        LayerInfoData(
            name="PR_BOUNDARY", index=189, sub_index=0, purpose_type="OUTLINE"
        ),
    )


def _primitive_layers() -> tuple[LayerRuleSetData, ...]:
    return (
        LayerRuleSetData(
            name="ACTIVE",
            layer_type="MASTERSLICE",
            rules=(rule_statement("WIDTH", 0.15),),
        ),
        LayerRuleSetData(
            name="POLY",
            layer_type="MASTERSLICE",
            rules=(
                rule_statement("WIDTH", 0.13),
                rule_statement("MINLENGTH", 0.13),
            ),
        ),
        LayerRuleSetData(
            name="CONT",
            layer_type="CUT",
            rules=(
                rule_statement("WIDTH", 0.16),
                rule_statement("SPACING", 0.18),
            ),
        ),
        LayerRuleSetData(
            name="METAL1",
            layer_type="ROUTING",
            rules=(
                rule_statement("WIDTH", 0.16),
                rule_statement("PITCH", 0.42),
                rule_statement("DIRECTION", "HORIZONTAL"),
            ),
        ),
        LayerRuleSetData(
            name="VIA1",
            layer_type="CUT",
            rules=(rule_statement("SPACING", 0.22),),
        ),
        LayerRuleSetData(
            name="METAL2",
            layer_type="ROUTING",
            rules=(
                rule_statement("WIDTH", 0.20),
                rule_statement("PITCH", 0.48),
                rule_statement("DIRECTION", "VERTICAL"),
            ),
        ),
        LayerRuleSetData(
            name="VIA2",
            layer_type="CUT",
            rules=(
                rule_statement("WIDTH", 0.19),
                rule_statement("SPACING", 0.22),
            ),
        ),
        LayerRuleSetData(
            name="METAL3",
            layer_type="ROUTING",
            rules=(
                rule_statement("WIDTH", 0.20),
                rule_statement("PITCH", 0.42),
                rule_statement("DIRECTION", "HORIZONTAL"),
            ),
        ),
        LayerRuleSetData(
            name="VIA3",
            layer_type="CUT",
            rules=(
                rule_statement("WIDTH", 0.19),
                rule_statement("SPACING", 0.22),
            ),
        ),
        LayerRuleSetData(
            name="METAL4",
            layer_type="ROUTING",
            rules=(
                rule_statement("WIDTH", 0.20),
                rule_statement("PITCH", 0.48),
                rule_statement("DIRECTION", "VERTICAL"),
            ),
        ),
        LayerRuleSetData(
            name="VIA4",
            layer_type="CUT",
            rules=(
                rule_statement("WIDTH", 0.19),
                rule_statement("SPACING", 0.22),
            ),
        ),
        LayerRuleSetData(
            name="METAL5",
            layer_type="ROUTING",
            rules=(
                rule_statement("WIDTH", 0.20),
                rule_statement("PITCH", 0.42),
                rule_statement("DIRECTION", "HORIZONTAL"),
            ),
        ),
        LayerRuleSetData(
            name="TOPVIA1",
            layer_type="CUT",
            rules=(
                rule_statement("WIDTH", 0.42),
                rule_statement("SPACING", 0.42),
            ),
        ),
        LayerRuleSetData(
            name="TOPMETAL1",
            layer_type="ROUTING",
            rules=(
                rule_statement("WIDTH", 1.64),
                rule_statement("SPACING", 1.64),
                rule_statement("PITCH", 2.28),
                rule_statement("DIRECTION", "VERTICAL"),
            ),
        ),
        LayerRuleSetData(
            name="TOPVIA2",
            layer_type="CUT",
            rules=(
                rule_statement("WIDTH", 0.9),
                rule_statement("SPACING", 1.06),
            ),
        ),
        LayerRuleSetData(
            name="TOPMETAL2",
            layer_type="ROUTING",
            rules=(
                rule_statement("WIDTH", 2.0),
                rule_statement("SPACING", 2.0),
                rule_statement("PITCH", 4.0),
                rule_statement("DIRECTION", "HORIZONTAL"),
            ),
        ),
    )


def _layer_pairs() -> tuple[LayerPairRuleSetData, ...]:
    return (
        LayerPairRuleSetData(
            first_layer="ACTIVE",
            second_layer="CONT",
            rules=(rule_statement("ENCLOSURE", 0.07, 0.07),),
            source="manual",
        ),
        LayerPairRuleSetData(
            first_layer="POLY",
            second_layer="CONT",
            rules=(
                rule_statement("ENCLOSURE", 0.07, 0.07),
                rule_statement("SPACING", 0.11),
            ),
            source="manual",
        ),
        LayerPairRuleSetData(
            first_layer="METAL1",
            second_layer="CONT",
            rules=(rule_statement("ENCLOSURE", 0.06, 0.06),),
            source="manual",
        ),
        LayerPairRuleSetData(
            first_layer="ACTIVE",
            second_layer="NSD",
            rules=(rule_statement("ENCLOSURE", 0.18, 0.18),),
            source="manual",
        ),
        LayerPairRuleSetData(
            first_layer="ACTIVE",
            second_layer="PSD",
            rules=(rule_statement("ENCLOSURE", 0.18, 0.18),),
            source="manual",
        ),
        LayerPairRuleSetData(
            first_layer="ACTIVE",
            second_layer="NWELL",
            rules=(rule_statement("ENCLOSURE", 0.31, 0.31),),
            source="manual",
        ),
    )


def ihp130_rule_deck() -> RuleDeckData:
    """Static IHP130 rule deck (no runtime parsing)."""
    base = RuleDeckData(
        database_microns=1000,
        manufacturing_grid_microns=0.005,
    )
    return merge_rule_decks(base, layers=_primitive_layers(), layer_pairs=_layer_pairs())


def ihp130_technology_data() -> TechnologyData:
    """Create static `TechnologyData` for IHP130 layout payloads."""
    return TechnologyData(
        name=PDK_NAME,
        layer_infos=layer_infos(),
        rule_deck=ihp130_rule_deck(),
    )


def write_ihp130_tech_proto(out_dir: Path) -> TechArtifacts:
    """Write IHP130 technology layout data to `.pb` and `.pbtxt`."""
    return write_tech_to_proto(ihp130_technology_data(), out_dir=out_dir, stem=PDK_NAME)
