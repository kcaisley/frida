"""Layout metadata for IHP130."""

from __future__ import annotations

from pathlib import Path

import klayout.db as kdb

from flow.layout.dsl import GenericLayers
from flow.layout.serialize import read_technology_proto, write_technology_proto
from flow.layout.tech import (
    LayerInfoData,
    NewRuleDeck,
)

PDK_NAME = "ihp130"
DBU = 0.001  # 1 dbu = 1 nm (1000 database units per micron)

# Instantiate GenericLayers for use in layer_map()
_GL = GenericLayers()


# ---------------------------------------------------------------------------
# New API
# ---------------------------------------------------------------------------


def layer_map() -> dict[kdb.LayerInfo, kdb.LayerInfo]:
    """Generic-to-tech layer mapping for IHP130.

    Returns a dictionary mapping canonical GenericLayers LayerInfo objects
    to the concrete PDK layer numbers used by IHP SG13G2.
    """
    return {
        _GL.OD: kdb.LayerInfo(1, 0, "ACTIVE"),
        _GL.PO: kdb.LayerInfo(2, 0, "POLY"),
        _GL.CO: kdb.LayerInfo(3, 0, "CONT"),
        _GL.NP: kdb.LayerInfo(4, 0, "NSD"),
        _GL.PP: kdb.LayerInfo(5, 0, "PSD"),
        _GL.NW: kdb.LayerInfo(6, 0, "NWELL"),
        _GL.M1: kdb.LayerInfo(7, 0, "METAL1"),
        _GL.PIN1: kdb.LayerInfo(7, 1, "M1.PIN"),
        _GL.VIA1: kdb.LayerInfo(8, 0, "VIA1"),
        _GL.M2: kdb.LayerInfo(9, 0, "METAL2"),
        _GL.PIN2: kdb.LayerInfo(9, 1, "M2.PIN"),
        _GL.VIA2: kdb.LayerInfo(10, 0, "VIA2"),
        _GL.M3: kdb.LayerInfo(11, 0, "METAL3"),
        _GL.PIN3: kdb.LayerInfo(11, 1, "M3.PIN"),
        _GL.VIA3: kdb.LayerInfo(12, 0, "VIA3"),
        _GL.M4: kdb.LayerInfo(13, 0, "METAL4"),
        _GL.PIN4: kdb.LayerInfo(13, 1, "M4.PIN"),
        _GL.VIA4: kdb.LayerInfo(14, 0, "VIA4"),
        _GL.M5: kdb.LayerInfo(15, 0, "METAL5"),
        _GL.PIN5: kdb.LayerInfo(15, 1, "M5.PIN"),
        _GL.VIA5: kdb.LayerInfo(16, 0, "VIA5"),
        _GL.M6: kdb.LayerInfo(17, 0, "METAL6"),
        _GL.PIN6: kdb.LayerInfo(17, 1, "M6.PIN"),
        _GL.VIA6: kdb.LayerInfo(18, 0, "VIA6"),
        _GL.M7: kdb.LayerInfo(19, 0, "METAL7"),
        _GL.PIN7: kdb.LayerInfo(19, 1, "M7.PIN"),
        _GL.LVTN: kdb.LayerInfo(70, 0, "LVTN"),
        _GL.LVTP: kdb.LayerInfo(70, 1, "LVTP"),
        _GL.HVTN: kdb.LayerInfo(71, 0, "HVTN"),
        _GL.HVTP: kdb.LayerInfo(71, 1, "HVTP"),
        _GL.TEXT: kdb.LayerInfo(63, 0, "TEXT"),
        _GL.PR_BOUNDARY: kdb.LayerInfo(189, 0, "PR_BOUNDARY"),
    }


def rule_deck() -> NewRuleDeck:
    """IHP130 design rules using the new hierarchical RuleDeck API.

    All values are plain integers in nanometers.
    """
    R = NewRuleDeck()

    R.OD.width = 150
    R.OD.spacing.OD = 180

    R.PO.width = 130
    R.PO.spacing.PO = 180

    R.CO.width = 160
    R.CO.spacing.CO = 180
    R.CO.spacing.PO = 110
    R.CO.enclosure.OD = 70
    R.CO.enclosure.PO = 70

    R.M1.width = 160
    R.M1.spacing.M1 = 180
    R.M1.area = 50_000
    R.M1.enclosure.CO = 60

    R.NP.enclosure.OD = 180
    R.PP.enclosure.OD = 180
    R.NW.enclosure.OD = 310

    R.VIA1.width = 220
    R.VIA1.spacing.VIA1 = 220

    R.M2.width = 200
    R.M2.spacing.M2 = 220
    R.M2.area = 60_000
    R.M2.enclosure.VIA1 = 60

    R.VIA2.width = 190
    R.VIA2.spacing.VIA2 = 220

    R.M3.width = 200
    R.M3.spacing.M3 = 220
    R.M3.area = 60_000
    R.M3.enclosure.VIA2 = 60

    R.VIA3.width = 190
    R.VIA3.spacing.VIA3 = 220

    R.M4.width = 200
    R.M4.spacing.M4 = 220
    R.M4.area = 70_000
    R.M4.enclosure.VIA3 = 60

    R.VIA4.width = 190
    R.VIA4.spacing.VIA4 = 220

    R.M5.width = 200
    R.M5.spacing.M5 = 220
    R.M5.area = 80_000
    R.M5.enclosure.VIA4 = 60

    R.VIA5.width = 420
    R.VIA5.spacing.VIA5 = 420

    R.M6.width = 1640
    R.M6.spacing.M6 = 1640
    R.M6.area = 1_000_000
    R.M6.enclosure.VIA5 = 100

    R.VIA6.width = 900
    R.VIA6.spacing.VIA6 = 1060

    R.M7.width = 2000
    R.M7.spacing.M7 = 2000
    R.M7.area = 2_000_000
    R.M7.enclosure.VIA6 = 100

    return R


# ---------------------------------------------------------------------------
# Layer info (still used by write_technology_proto for vlsir.tech export)
# ---------------------------------------------------------------------------


def layer_infos() -> tuple[LayerInfoData, ...]:
    """Tech layer descriptors for vlsir.tech layer-info export."""
    return (
        LayerInfoData(name="ACTIVE", index=1),
        LayerInfoData(name="POLY", index=2),
        LayerInfoData(name="CONT", index=3),
        LayerInfoData(name="NSD", index=4),
        LayerInfoData(name="PSD", index=5),
        LayerInfoData(name="NWELL", index=6),
        LayerInfoData(name="METAL1", index=7),
        LayerInfoData(name="M1.PIN", index=7, sub_index=1, purpose_type="PIN"),
        LayerInfoData(name="VIA1", index=8),
        LayerInfoData(name="METAL2", index=9),
        LayerInfoData(name="M2.PIN", index=9, sub_index=1, purpose_type="PIN"),
        LayerInfoData(name="VIA2", index=10),
        LayerInfoData(name="METAL3", index=11),
        LayerInfoData(name="M3.PIN", index=11, sub_index=1, purpose_type="PIN"),
        LayerInfoData(name="VIA3", index=12),
        LayerInfoData(name="METAL4", index=13),
        LayerInfoData(name="M4.PIN", index=13, sub_index=1, purpose_type="PIN"),
        LayerInfoData(name="VIA4", index=14),
        LayerInfoData(name="METAL5", index=15),
        LayerInfoData(name="M5.PIN", index=15, sub_index=1, purpose_type="PIN"),
        LayerInfoData(name="VIA5", index=16),
        LayerInfoData(name="METAL6", index=17),
        LayerInfoData(name="M6.PIN", index=17, sub_index=1, purpose_type="PIN"),
        LayerInfoData(name="VIA6", index=18),
        LayerInfoData(name="METAL7", index=19),
        LayerInfoData(name="M7.PIN", index=19, sub_index=1, purpose_type="PIN"),
        LayerInfoData(name="VTH_LVT", index=70),
        LayerInfoData(name="VTH_HVT", index=71),
        LayerInfoData(name="TEXT", index=63, purpose_type="LABEL"),
        LayerInfoData(name="PR_BOUNDARY", index=189, purpose_type="OUTLINE"),
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_ihp130_to_vlsir(tmp_path: Path) -> None:
    """Test: write/read vlsir.tech proto round-trip (layer-info only)."""
    artifacts = write_technology_proto(
        tech_name=PDK_NAME,
        layer_infos=layer_infos(),
        out_dir=tmp_path,
    )
    tech = read_technology_proto(artifacts.pb)
    assert tech.name.lower() == PDK_NAME
    assert any(layer.name.upper() in {"METAL1", "M1.PIN"} for layer in tech.layers)


def test_ihp130_new_rule_deck() -> None:
    """Verify the new hierarchical rule deck returns correct values."""
    R = rule_deck()
    assert R.M1.width == 160
    assert R.M1.spacing.M1 == 180
    assert R.M1.area == 50_000
    assert R.M1.enclosure.CO == 60
    assert R.CO.width == 160
    assert R.CO.enclosure.OD == 70
    assert R.CO.enclosure.PO == 70
    assert R.CO.spacing.PO == 110
    assert R.NW.enclosure.OD == 310
    assert R.VIA1.width == 220
    assert R.M7.width == 2000
    assert R.M7.area == 2_000_000


def test_ihp130_layer_map() -> None:
    """Verify layer_map returns a populated dict with expected entries."""
    lm = layer_map()
    assert len(lm) > 0
    # Check a few known mappings
    assert lm[_GL.M1] == kdb.LayerInfo(7, 0, "METAL1")
    assert lm[_GL.PIN1] == kdb.LayerInfo(7, 1, "M1.PIN")
    assert lm[_GL.OD] == kdb.LayerInfo(1, 0, "ACTIVE")


def test_ihp130_dbu() -> None:
    """Verify DBU is set correctly."""
    assert DBU == 0.001
