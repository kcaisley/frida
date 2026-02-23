"""Technology dimensions and layer mapping for TSMC65."""

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

PDK_NAME = "tsmc65"
TECH_LEF_PATH = Path("/home/kcaisley/asiclab/tech/tsmc65/lef/tsmc65_tech.lef")
LYT_PATH = Path("/home/kcaisley/asiclab/tech/tsmc65/tsmc65.lyt")


def _tsmc65_primitive_layers() -> tuple[LayerRuleSetData, ...]:
    """Additional primitive-generation layer rules used by FRIDA scripts."""
    return (
        LayerRuleSetData(
            name="ACTIVE",
            layer_type="MASTERSLICE",
            rules=(
                rule_statement("WIDTH", 0.12),
                rule_statement("SPACING", 0.14),
            ),
        ),
        LayerRuleSetData(
            name="POLY",
            layer_type="MASTERSLICE",
            rules=(
                rule_statement("WIDTH", 0.06),
                rule_statement("MINLENGTH", 0.06),
                rule_statement("SPACING", 0.10),
            ),
        ),
        LayerRuleSetData(
            name="CONT",
            layer_type="CUT",
            rules=(
                rule_statement("WIDTH", 0.07),
                rule_statement("SPACING", 0.10),
            ),
        ),
        LayerRuleSetData(
            name="METAL1",
            layer_type="ROUTING",
            rules=(
                rule_statement("WIDTH", 0.07),
                rule_statement("SPACING", 0.07),
            ),
        ),
    )


def _tsmc65_layer_pairs() -> tuple[LayerPairRuleSetData, ...]:
    """Pairwise layer spacing/overlap rules in LEF-like statement format."""
    return (
        LayerPairRuleSetData(
            first_layer="ACTIVE",
            second_layer="CONT",
            rules=(rule_statement("ENCLOSURE", 0.03, 0.03),),
            source="derived",
        ),
        LayerPairRuleSetData(
            first_layer="POLY",
            second_layer="CONT",
            rules=(
                rule_statement("ENCLOSURE", 0.03, 0.03),
                rule_statement("SPACING", 0.05),
            ),
            source="derived",
        ),
        LayerPairRuleSetData(
            first_layer="METAL1",
            second_layer="CONT",
            rules=(rule_statement("ENCLOSURE", 0.02, 0.02),),
            source="derived",
        ),
        LayerPairRuleSetData(
            first_layer="ACTIVE",
            second_layer="NSD",
            rules=(rule_statement("ENCLOSURE", 0.08, 0.08),),
            source="derived",
        ),
        LayerPairRuleSetData(
            first_layer="ACTIVE",
            second_layer="PSD",
            rules=(rule_statement("ENCLOSURE", 0.08, 0.08),),
            source="derived",
        ),
        LayerPairRuleSetData(
            first_layer="ACTIVE",
            second_layer="NWELL",
            rules=(rule_statement("ENCLOSURE", 0.12, 0.12),),
            source="derived",
        ),
    )


def tsmc65_rule_deck() -> RuleDeckData:
    """Build the full TSMC65 rule deck from TECHLEF plus FEOL additions."""
    if not TECH_LEF_PATH.exists():
        raise FileNotFoundError(f"TSMC65 TECHLEF not found: {TECH_LEF_PATH}")
    lef_deck = parse_tech_lef(TECH_LEF_PATH)
    return merge_rule_decks(
        lef_deck,
        layers=_tsmc65_primitive_layers(),
        layer_pairs=_tsmc65_layer_pairs(),
    )


def _tsmc65_voltage_rails() -> tuple[VoltageRailData, ...]:
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
            notes="TSMC65 LP core domain.",
        ),
    )


def _tsmc65_device_minimums() -> tuple[DeviceMinimumData, ...]:
    """Minimum transistor dimensions exported for primitive generation."""
    return (
        DeviceMinimumData(
            device_type="MOS",
            name="nch_lvt",
            variant="nmos/lvt",
            min_width_microns=0.12,
            min_length_microns=0.06,
        ),
        DeviceMinimumData(
            device_type="MOS",
            name="nch",
            variant="nmos/std",
            min_width_microns=0.12,
            min_length_microns=0.06,
        ),
        DeviceMinimumData(
            device_type="MOS",
            name="nch_hvt",
            variant="nmos/hvt",
            min_width_microns=0.12,
            min_length_microns=0.06,
        ),
        DeviceMinimumData(
            device_type="MOS",
            name="pch_lvt",
            variant="pmos/lvt",
            min_width_microns=0.12,
            min_length_microns=0.06,
        ),
        DeviceMinimumData(
            device_type="MOS",
            name="pch",
            variant="pmos/std",
            min_width_microns=0.12,
            min_length_microns=0.06,
        ),
        DeviceMinimumData(
            device_type="MOS",
            name="pch_hvt",
            variant="pmos/hvt",
            min_width_microns=0.12,
            min_length_microns=0.06,
        ),
    )


def _tsmc65_model_libraries() -> tuple[ModelLibraryData, ...]:
    """Simulator model-library path metadata."""
    toplevel = str(Install().pdk_path / "1p9m6x1z1u/models/spectre/toplevel.scs")
    return (
        ModelLibraryData(
            simulator="spectre",
            path=toplevel,
            corner_sections=(
                CornerSectionData(corner="TYP", section="tt_lib"),
                CornerSectionData(corner="FAST", section="ff_lib"),
                CornerSectionData(corner="SLOW", section="ss_lib"),
                CornerSectionData(corner="SF", section="sf_lib"),
                CornerSectionData(corner="FS", section="fs_lib"),
                CornerSectionData(corner="MC", section="mc_lib"),
            ),
            notes="Observed on jupiter under /eda/kits/TSMC/65LP.",
        ),
    )


def tsmc65_technology_data() -> TechnologyData:
    """Create `TechnologyData` for TSMC65."""
    layer_infos = load_layer_map_from_lyt(LYT_PATH) if LYT_PATH.exists() else ()
    return TechnologyData(
        name=PDK_NAME,
        voltage_rails=_tsmc65_voltage_rails(),
        device_minimums=_tsmc65_device_minimums(),
        model_libraries=_tsmc65_model_libraries(),
        layer_infos=layer_infos,
        rule_deck=tsmc65_rule_deck(),
    )


def write_tsmc65_tech_proto(out_dir: Path) -> TechArtifacts:
    """Write TSMC65 technology rules to `.pb` and `.pbtxt`."""
    return write_tech_to_proto(
        tsmc65_technology_data(),
        out_dir=out_dir,
        stem=PDK_NAME,
    )
