"""Technology dimensions and layer mapping for IHP130."""

from pathlib import Path

from flow.layout.layout import (
    CornerSectionData,
    DeviceMinimumData,
    LayerPairRuleSetData,
    LayerRuleSetData,
    ModelLibraryData,
    RuleDeckData,
    TechArtifacts,
    TechnologyData,
    VoltageRailData,
    load_layer_map_from_lyt,
    merge_rule_decks,
    parse_tech_lef,
    rule_statement,
    write_tech_to_proto,
)

from .pdk_logic import Install

PDK_NAME = "ihp130"
TECH_LEF_PATH = Path(
    "/home/kcaisley/libs/IHP-Open-PDK/ihp-sg13g2/libs.ref/sg13g2_stdcell/lef/"
    "sg13g2_tech.lef"
)
LYT_PATH = Path(
    "/home/kcaisley/libs/IHP-Open-PDK/ihp-sg13g2/libs.tech/klayout/tech/sg13g2.lyt"
)


def _ihp130_primitive_layers() -> tuple[LayerRuleSetData, ...]:
    """Additional primitive-generation layer rules used by FRIDA scripts."""
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
            rules=(rule_statement("WIDTH", 0.14),),
        ),
    )


def _ihp130_layer_pairs() -> tuple[LayerPairRuleSetData, ...]:
    """Pairwise layer spacing/overlap rules in LEF-like statement format."""
    return (
        LayerPairRuleSetData(
            first_layer="ACTIVE",
            second_layer="CONT",
            rules=(rule_statement("ENCLOSURE", 0.07, 0.07),),
            source="derived",
        ),
        LayerPairRuleSetData(
            first_layer="POLY",
            second_layer="CONT",
            rules=(
                rule_statement("ENCLOSURE", 0.07, 0.07),
                rule_statement("SPACING", 0.11),
            ),
            source="derived",
        ),
        LayerPairRuleSetData(
            first_layer="METAL1",
            second_layer="CONT",
            rules=(rule_statement("ENCLOSURE", 0.06, 0.06),),
            source="derived",
        ),
        LayerPairRuleSetData(
            first_layer="ACTIVE",
            second_layer="NSD",
            rules=(rule_statement("ENCLOSURE", 0.18, 0.18),),
            source="derived",
        ),
        LayerPairRuleSetData(
            first_layer="ACTIVE",
            second_layer="PSD",
            rules=(rule_statement("ENCLOSURE", 0.18, 0.18),),
            source="derived",
        ),
        LayerPairRuleSetData(
            first_layer="ACTIVE",
            second_layer="NWELL",
            rules=(rule_statement("ENCLOSURE", 0.31, 0.31),),
            source="derived",
        ),
    )


def ihp130_rule_deck() -> RuleDeckData:
    """Build the full IHP130 rule deck from TECHLEF plus FEOL additions."""
    if not TECH_LEF_PATH.exists():
        raise FileNotFoundError(f"IHP130 TECHLEF not found: {TECH_LEF_PATH}")
    lef_deck = parse_tech_lef(TECH_LEF_PATH)
    return merge_rule_decks(
        lef_deck,
        layers=_ihp130_primitive_layers(),
        layer_pairs=_ihp130_layer_pairs(),
    )


def _ihp130_voltage_rails() -> tuple[VoltageRailData, ...]:
    """Supply-rail metadata used by FRIDA for sizing/ bias context."""
    return (
        VoltageRailData(
            name="VSS",
            role="GROUND",
            nominal_volts=0.0,
            min_volts=0.0,
            max_volts=0.0,
        ),
        VoltageRailData(
            name="VDD",
            role="POWER",
            nominal_volts=1.2,
            min_volts=1.08,
            max_volts=1.32,
            notes="IHP SG13G2 LV core domain.",
        ),
        VoltageRailData(
            name="VDDIO",
            role="POWER",
            nominal_volts=3.3,
            min_volts=3.0,
            max_volts=3.6,
            notes="IHP SG13G2 HV I/O domain.",
        ),
    )


def _ihp130_device_minimums() -> tuple[DeviceMinimumData, ...]:
    """Minimum transistor dimensions exported for primitive generation."""
    return (
        DeviceMinimumData(
            device_type="MOS",
            name="sg13_lv_nmos",
            variant="nmos/std/lv",
            min_width_microns=0.35,
            min_length_microns=0.13,
        ),
        DeviceMinimumData(
            device_type="MOS",
            name="sg13_lv_pmos",
            variant="pmos/std/lv",
            min_width_microns=0.35,
            min_length_microns=0.13,
        ),
        DeviceMinimumData(
            device_type="MOS",
            name="sg13_hv_nmos",
            variant="nmos/std/hv",
            min_width_microns=0.35,
            min_length_microns=0.45,
        ),
        DeviceMinimumData(
            device_type="MOS",
            name="sg13_hv_pmos",
            variant="pmos/std/hv",
            min_width_microns=0.35,
            min_length_microns=0.45,
        ),
    )


def _ihp130_model_libraries() -> tuple[ModelLibraryData, ...]:
    """Simulator model-library path metadata."""
    return (
        ModelLibraryData(
            simulator="ngspice",
            path=str(Install().model_path / "cornerMOSlv.lib"),
            corner_sections=(
                CornerSectionData(corner="TYP", section="tt"),
                CornerSectionData(corner="FAST", section="ff"),
                CornerSectionData(corner="SLOW", section="ss"),
            ),
            notes="Open-PDK LV MOS corners.",
        ),
        ModelLibraryData(
            simulator="ngspice",
            path=str(Install().model_path / "cornerMOShv.lib"),
            corner_sections=(
                CornerSectionData(corner="TYP", section="tt"),
                CornerSectionData(corner="FAST", section="ff"),
                CornerSectionData(corner="SLOW", section="ss"),
            ),
            notes="Open-PDK HV MOS corners.",
        ),
        ModelLibraryData(
            simulator="spectre",
            path=(
                "/eda/kits/IHP/IHP-SG13G2/SG13G2_618_rev1.2.10/tech/"
                "SG13_MOS/library/spectreG2/cornerMOSlv_psp.scs"
            ),
            corner_sections=(
                CornerSectionData(corner="TYP", section="tt"),
                CornerSectionData(corner="FAST", section="ff"),
                CornerSectionData(corner="SLOW", section="ss"),
            ),
            notes="Observed on jupiter under /eda/kits.",
        ),
        ModelLibraryData(
            simulator="spectre",
            path=(
                "/eda/kits/IHP/IHP-SG13G2/SG13G2_618_rev1.2.10/tech/"
                "SG13_MOS/library/spectreG2/cornerMOShv_psp.scs"
            ),
            corner_sections=(
                CornerSectionData(corner="TYP", section="tt"),
                CornerSectionData(corner="FAST", section="ff"),
                CornerSectionData(corner="SLOW", section="ss"),
            ),
            notes="Observed on jupiter under /eda/kits.",
        ),
    )


def ihp130_technology_data() -> TechnologyData:
    """Create `TechnologyData` for IHP130."""
    layer_infos = load_layer_map_from_lyt(LYT_PATH) if LYT_PATH.exists() else ()
    return TechnologyData(
        name=PDK_NAME,
        voltage_rails=_ihp130_voltage_rails(),
        device_minimums=_ihp130_device_minimums(),
        model_libraries=_ihp130_model_libraries(),
        layer_infos=layer_infos,
        rule_deck=ihp130_rule_deck(),
    )


def write_ihp130_tech_proto(out_dir: Path) -> TechArtifacts:
    """Write IHP130 technology rules to `.pb` and `.pbtxt`."""
    return write_tech_to_proto(ihp130_technology_data(), out_dir=out_dir, stem=PDK_NAME)
