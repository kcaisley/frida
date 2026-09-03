"""Software-only tests for the CDAC electrical and physical generators."""

from dataclasses import replace
from pathlib import Path

import pytest
from hdl21.prefix import f
from klayout import db

from flow.layout.dsl import GenericLayers
from flow.layout.tech import EndOfLineRule, NewRuleDeck, ParallelSpacingRule, ViaEnclosureRule

from .laygen import (
    CdacLayout,
    CdacLayoutParams,
    UnitLengthCapFamilyParams,
    _calc_unit_geometry,
    _layout_manifest,
    is_valid_cdac_layout_params,
)
from .subckt import (
    Cdac,
    CdacArray,
    CdacArrayParams,
    CdacParams,
    RedunStrat,
    _calc_weight_partitions,
    get_cdac_weights,
    is_valid_cdac_array_params,
)


def _rules(*, pitch: int = 200, eol_threshold: int = 120) -> NewRuleDeck:
    rules = NewRuleDeck(manufacturing_grid=5)
    for metal_number in range(3, 8):
        metal = getattr(rules, f"M{metal_number}")
        metal.width = 100
        metal.pitch = pitch
        setattr(metal.spacing, f"M{metal_number}", 100)
        metal.area = 52_000
        metal.enclosed_area = 200_000
        metal.max_density = 0.90
        metal.parallel_spacing.append(ParallelSpacingRule(spacing=120, min_width=200, min_parallel_run_length=380))
        metal.end_of_line.append(EndOfLineRule(spacing=120, max_edge_length=eol_threshold, extension=35))
    for via_number in range(3, 7):
        via = getattr(rules, f"VIA{via_number}")
        via.width = 100
        via.cut_width = 100
        via.cut_height = 100
        setattr(via.spacing, f"VIA{via_number}", 100)
        via.via_enclosure = ViaEnclosureRule(opposite=40, minimum=0, all_sides=30)
    return rules


class _SyntheticPdkLayout:
    DBU = 0.0005
    PDK_NAME = "synthetic"

    @staticmethod
    def rule_deck() -> NewRuleDeck:
        return _rules()

    @staticmethod
    def layer_map() -> dict[db.LayerInfo, db.LayerInfo]:
        generic = GenericLayers()
        mapping = {
            generic.MOM_RECOG: db.LayerInfo(155, 100, "MOM_RECOG"),
            generic.MOM_RECOG_SHIELD: db.LayerInfo(155, 104, "MOM_RECOG_SHIELD"),
            generic.MOM_RECOG_M5: db.LayerInfo(155, 105, "MOM_RECOG_M5"),
            generic.MOM_RECOG_M6: db.LayerInfo(155, 106, "MOM_RECOG_M6"),
            generic.MOM_RECOG_M7: db.LayerInfo(155, 107, "MOM_RECOG_M7"),
            generic.PR_BOUNDARY: db.LayerInfo(189, 0, "PR_BOUNDARY"),
        }
        for metal_number in range(3, 8):
            layer_number = 5 + 2 * metal_number
            mapping[getattr(generic, f"M{metal_number}")] = db.LayerInfo(layer_number, 0, f"METAL{metal_number}")
            mapping[getattr(generic, f"PIN{metal_number}")] = db.LayerInfo(layer_number, 1, f"M{metal_number}.PIN")
        for via_number in range(3, 7):
            mapping[getattr(generic, f"VIA{via_number}")] = db.LayerInfo(6 + 2 * via_number, 0, f"VIA{via_number}")
        return mapping


def _params(
    weights: tuple[int, ...] = (768, 512, 320, 192, 96, 64, 32, 24, 12, 10, 5, 4, 4, 2, 1, 1),
    *,
    shield_layer: int = 5,
    active_layers: tuple[int, ...] = (6,),
    top_cell: str = "frida_caparray",
) -> CdacLayoutParams:
    return CdacLayoutParams(
        cdac=CdacParams(n_dac=len(weights), n_extra=0, weights=weights, unit_cap=0.8 * f),
        family=UnitLengthCapFamilyParams(),
        technology="synthetic",
        route_layer=4,
        shield_layer=shield_layer,
        active_layers=active_layers,
        top_cell=top_cell,
    )


def _generate(monkeypatch: pytest.MonkeyPatch, params: CdacLayoutParams) -> db.Layout:
    monkeypatch.setattr("flow.cdac.laygen.import_module", lambda _name: _SyntheticPdkLayout)
    return CdacLayout(params)


def _layer_index(layout: db.Layout, layer: int, datatype: int) -> int:
    for index in layout.layer_indexes():
        info = layout.get_info(index)
        if (info.layer, info.datatype) == (layer, datatype):
            return index
    raise AssertionError(f"missing GDS layer {layer}/{datatype}")


def test_cdac_and_weight_strategies() -> None:
    assert Cdac(CdacParams()) is not None
    assert len(get_cdac_weights(CdacParams(n_dac=8, n_extra=0, redun_strat=RedunStrat.RDX2))) == 8
    assert len(get_cdac_weights(CdacParams(n_dac=8, n_extra=2, redun_strat=RedunStrat.SUBRDX2_LIM))) == 10


def test_weight_partitions_accept_arbitrary_lengths_and_large_weights() -> None:
    weights = [1, 63, 64, 65, 129, 1025]
    partitions = _calc_weight_partitions(weights, 64)
    assert [sum(group) for group in partitions] == weights
    assert all(1 <= chunk <= 64 for group in partitions for chunk in group)
    assert partitions[3] == [64, 1]
    assert partitions[4] == [64, 64, 1]
    assert len(partitions[-1]) == 17
    with pytest.raises(ValueError):
        _calc_weight_partitions([0], 64)
    with pytest.raises(ValueError):
        _calc_weight_partitions([-1], 64)
    with pytest.raises(ValueError):
        _calc_weight_partitions([True], 64)  # type: ignore[list-item]
    with pytest.raises(ValueError):
        _calc_weight_partitions([1], 0)


def test_radix17_and_radix20_are_data_not_generator_assumptions() -> None:
    radix17 = tuple(get_cdac_weights(CdacParams()))
    radix20 = (768, 512, 320, 192, 128, 64, 64, 64, 64, 64, 32, 16, 8, 4, 2, 1)
    assert (len(radix17), sum(radix17), sum(map(len, _calc_weight_partitions(list(radix17), 64)))) == (16, 2047, 41)
    assert (len(radix20), sum(radix20), sum(map(len, _calc_weight_partitions(list(radix20), 64)))) == (16, 2303, 41)


def test_cdac_array_has_dynamic_ports_and_ideal_values() -> None:
    cdac = CdacParams(n_dac=4, n_extra=0, weights=(129, 64, 2, 1), unit_cap=0.8 * f)
    params = CdacArrayParams(cdac=cdac)
    assert is_valid_cdac_array_params(params)
    module = CdacArray(params)
    assert len(module.ports) == 10
    assert set(module.ports) == {
        "cap_topplate",
        "cap_shieldplate",
        *(f"cap_botplate_{side}<{bit}>" for side in ("main", "diff") for bit in range(4)),
    }
    assert float(module.Cmain_3_0.of.params.c) == pytest.approx(51.6e-15)
    assert float(module.Cdiff_3_0.of.params.c) == pytest.approx(0.4e-15)


def test_geometry_is_derived_from_rules() -> None:
    params = _params()
    geometry = _calc_unit_geometry(params, _rules())
    assert (geometry.finger_width, geometry.gap, geometry.end_gap) == (100, 100, 120)
    assert (geometry.weight_step, geometry.tail_length, geometry.unit_pitch) == (400, 1_000, 400)
    scaled = _calc_unit_geometry(params, _rules(pitch=240, eol_threshold=90))
    assert (scaled.end_gap, scaled.weight_step, scaled.tail_length) == (100, 480, 1_200)
    conditional = _rules()
    conditional.M6.parallel_spacing[0] = ParallelSpacingRule(spacing=140, min_width=90, min_parallel_run_length=380)
    assert _calc_unit_geometry(params, conditional).gap == 140


def test_layout_validation_rejects_reserved_or_nonconsecutive_layers() -> None:
    assert is_valid_cdac_layout_params(_params())
    assert is_valid_cdac_layout_params(_params(shield_layer=4, active_layers=(5, 6, 7)))
    assert not is_valid_cdac_layout_params(replace(_params(), route_layer=3))
    assert not is_valid_cdac_layout_params(_params(active_layers=(6, 8)))


def test_rule_derived_radix17_layout(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    params = _params()
    layout = _generate(monkeypatch, params)
    output = tmp_path / "frida_caparray.gds"
    save = db.SaveLayoutOptions()
    save.set_format_from_filename(str(output))
    save.add_cell(layout.cell(params.top_cell).cell_index())
    layout.write(str(output), save)
    loaded = db.Layout()
    loaded.read(str(output))
    top = loaded.cell(params.top_cell)
    assert top is not None
    assert len(list(top.each_inst())) == 41
    assert top.dbbox().width() == pytest.approx(16.74)
    assert top.dbbox().height() == pytest.approx(53.76)
    texts = {shape.text.string for shape in top.shapes(_layer_index(loaded, 13, 1)).each() if shape.is_text()}
    assert len(texts) == 34
    assert {"cap_topplate", "cap_shieldplate", "cap_botplate_main<15>", "cap_botplate_diff<0>"} <= texts


def test_layout_width_grows_one_pitch_per_chunk(monkeypatch: pytest.MonkeyPatch) -> None:
    one = _generate(monkeypatch, _params((64,), top_cell="one"))
    three = _generate(monkeypatch, _params((129,), top_cell="three"))
    assert three.cell("three").dbbox().width() - one.cell("one").dbbox().width() == pytest.approx(0.8)
    assert len(list(one.cell("one").each_inst())) == 1
    assert len(list(three.cell("three").each_inst())) == 3


def test_shared_m4_keeps_m3_empty_and_owns_shield_tabs(monkeypatch: pytest.MonkeyPatch) -> None:
    params = _params(shield_layer=4, active_layers=(5, 6, 7))
    layout = _generate(monkeypatch, params)
    top = layout.cell(params.top_cell)
    assert db.Region(top.begin_shapes_rec(layout.layer(11, 0))).is_empty()
    assert db.Region(top.begin_shapes_rec(layout.layer(12, 0))).is_empty()
    assert len(list(db.Region(top.begin_shapes_rec(layout.layer(13, 0))).merged().each())) == 34
    right_edge = top.bbox().right
    assert len([shape for shape in top.shapes(layout.layer(13, 0)).each() if shape.bbox().right == right_edge]) == 9


def test_manifest_tracks_dynamic_array(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("flow.cdac.laygen.import_module", lambda _name: _SyntheticPdkLayout)
    manifest = _layout_manifest(_params((129, 64, 1)))
    assert manifest["physical_chunk_count"] == 5
    assert manifest["port_count"] == 8
    assert manifest["partitioned_weights_msb_first"] == [[64, 64, 1], [64], [1]]
