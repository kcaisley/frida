"""Minimal layout metadata for IHP130."""

from __future__ import annotations

from pathlib import Path

from hdl21.prefix import n

from flow.layout.dsl import L, LayerRef
from flow.layout.serialize import read_technology_proto, write_technology_proto
from flow.layout.tech import LayerInfoData, RuleDeck, TechLayerMap

PDK_NAME = "ihp130"


def layer_infos() -> tuple[LayerInfoData, ...]:
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


def tech_layer_map() -> TechLayerMap:
    infos = {info.name: info for info in layer_infos()}
    return {
        LayerRef(L.OD, L.Purpose.DRAW): infos["ACTIVE"],
        LayerRef(L.PO, L.Purpose.DRAW): infos["POLY"],
        LayerRef(L.CO, L.Purpose.DRAW): infos["CONT"],
        LayerRef(L.NP, L.Purpose.DRAW): infos["NSD"],
        LayerRef(L.PP, L.Purpose.DRAW): infos["PSD"],
        LayerRef(L.NWELL, L.Purpose.DRAW): infos["NWELL"],
        LayerRef(L.M1, L.Purpose.DRAW): infos["METAL1"],
        LayerRef(L.M1, L.Purpose.PIN): infos["M1.PIN"],
        LayerRef(L.VIA1, L.Purpose.DRAW): infos["VIA1"],
        LayerRef(L.M2, L.Purpose.DRAW): infos["METAL2"],
        LayerRef(L.M2, L.Purpose.PIN): infos["M2.PIN"],
        LayerRef(L.VIA2, L.Purpose.DRAW): infos["VIA2"],
        LayerRef(L.M3, L.Purpose.DRAW): infos["METAL3"],
        LayerRef(L.M3, L.Purpose.PIN): infos["M3.PIN"],
        LayerRef(L.VIA3, L.Purpose.DRAW): infos["VIA3"],
        LayerRef(L.M4, L.Purpose.DRAW): infos["METAL4"],
        LayerRef(L.M4, L.Purpose.PIN): infos["M4.PIN"],
        LayerRef(L.VIA4, L.Purpose.DRAW): infos["VIA4"],
        LayerRef(L.M5, L.Purpose.DRAW): infos["METAL5"],
        LayerRef(L.M5, L.Purpose.PIN): infos["M5.PIN"],
        LayerRef(L.VIA5, L.Purpose.DRAW): infos["VIA5"],
        LayerRef(L.M6, L.Purpose.DRAW): infos["METAL6"],
        LayerRef(L.M6, L.Purpose.PIN): infos["M6.PIN"],
        LayerRef(L.VIA6, L.Purpose.DRAW): infos["VIA6"],
        LayerRef(L.M7, L.Purpose.DRAW): infos["METAL7"],
        LayerRef(L.M7, L.Purpose.PIN): infos["M7.PIN"],
        LayerRef(L.VTH_LVT, L.Purpose.DRAW): infos["VTH_LVT"],
        LayerRef(L.VTH_HVT, L.Purpose.DRAW): infos["VTH_HVT"],
        LayerRef(L.TEXT, L.Purpose.DRAW): infos["TEXT"],
        LayerRef(L.PR_BOUNDARY, L.Purpose.DRAW): infos["PR_BOUNDARY"],
    }


def ihp130_rule_deck() -> RuleDeck:
    deck = RuleDeck(database_microns=1000, manufacturing_grid_microns=0.005)
    deck.layer(L.OD).min_width(rule=150 * n).min_spacing(rule=180 * n)
    deck.layer(L.PO).min_width(rule=130 * n).min_spacing(rule=180 * n)
    deck.layer(L.CO).min_width(rule=160 * n).min_spacing(rule=180 * n)
    deck.layer(L.M1).min_width(rule=160 * n).min_spacing(rule=180 * n).min_area(
        rule=50000 * n * n
    )
    deck.layer(L.VIA1).min_width(rule=220 * n).min_spacing(rule=220 * n)
    deck.layer(L.M2).min_width(rule=200 * n).min_spacing(rule=220 * n).min_area(
        rule=60000 * n * n
    )
    deck.layer(L.VIA2).min_width(rule=190 * n).min_spacing(rule=220 * n)
    deck.layer(L.M3).min_width(rule=200 * n).min_spacing(rule=220 * n).min_area(
        rule=60000 * n * n
    )
    deck.layer(L.VIA3).min_width(rule=190 * n).min_spacing(rule=220 * n)
    deck.layer(L.M4).min_width(rule=200 * n).min_spacing(rule=220 * n).min_area(
        rule=70000 * n * n
    )
    deck.layer(L.VIA4).min_width(rule=190 * n).min_spacing(rule=220 * n)
    deck.layer(L.M5).min_width(rule=200 * n).min_spacing(rule=220 * n).min_area(
        rule=80000 * n * n
    )
    deck.layer(L.VIA5).min_width(rule=420 * n).min_spacing(rule=420 * n)
    deck.layer(L.M6).min_width(rule=1640 * n).min_spacing(rule=1640 * n).min_area(
        rule=1_000_000 * n * n
    )
    deck.layer(L.VIA6).min_width(rule=900 * n).min_spacing(rule=1060 * n)
    deck.layer(L.M7).min_width(rule=2000 * n).min_spacing(rule=2000 * n).min_area(
        rule=2_000_000 * n * n
    )

    deck.layer(L.CO).min_enclosure(of=L.OD, rule=70 * n)
    deck.layer(L.CO).min_enclosure(of=L.PO, rule=70 * n)
    deck.layer(L.CO).min_spacing(to=L.PO, rule=110 * n)
    deck.layer(L.M1).min_enclosure(of=L.CO, rule=60 * n)
    deck.layer(L.NP).min_enclosure(of=L.OD, rule=180 * n)
    deck.layer(L.PP).min_enclosure(of=L.OD, rule=180 * n)
    deck.layer(L.NWELL).min_enclosure(of=L.OD, rule=310 * n)
    return deck


def test_ihp130_to_vlsir(tmp_path: Path) -> None:
    artifacts = write_technology_proto(
        tech_name=PDK_NAME,
        layer_infos=layer_infos(),
        rule_deck=ihp130_rule_deck(),
        out_dir=tmp_path,
    )
    tech = read_technology_proto(artifacts.pb)
    assert tech.name.lower() == PDK_NAME
    assert any(layer.name.upper() in {"METAL1", "M1.PIN"} for layer in tech.layers)
    assert len(tech.rules.layers) > 0
