"""Software-only tests for the CDAC electrical and physical generators."""

from dataclasses import replace
from pathlib import Path

import hdl21 as h
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
    _ordered_groups,
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


def test_physical_order_is_small_left_large_right_without_renumbering() -> None:
    weights = [768, 512, 2, 1, 1]
    partitions = _calc_weight_partitions(weights, 64)

    ordered = _ordered_groups(weights, partitions)

    assert [stage for stage, _weight, _chunks in ordered] == [4, 3, 2, 1, 0]
    assert ordered[0][1] == 1
    assert ordered[-1][1] == 768


def test_cdac_array_has_dynamic_ports_and_ideal_values() -> None:
    cdac = CdacParams(n_dac=4, n_extra=0, weights=(129, 64, 2, 1), unit_cap=0.8 * f)
    params = CdacArrayParams(cdac=cdac)
    assert is_valid_cdac_array_params(params)
    module = CdacArray(params)
    assert len(module.ports) == 10
    assert set(module.ports) == {
        "cap_topplate",
        "cap_shieldplate",
        *(f"cap_botplate_{side}<{stage}>" for side in ("main", "diff") for stage in range(4)),
    }
    assert float(module.main_0_0_m6.of.cap.of.params.c) == pytest.approx(51.6e-15, abs=1e-18)
    assert float(module.diff_0_0_m6.of.cap.of.params.c) == pytest.approx(0.4e-15, abs=1e-18)
    assert float(module.main_3_0_m6.of.cap.of.params.c) == pytest.approx(26.4e-15, abs=1e-18)
    assert float(module.diff_3_0_m6.of.cap.of.params.c) == pytest.approx(25.6e-15, abs=1e-18)


@pytest.mark.parametrize("active_layers", [(6,), (6, 7), (5, 6, 7)])
def test_simulation_and_lvs_share_the_same_hdl21_graph(active_layers: tuple[int, ...]) -> None:
    import io

    from flow.util.netlist import subcircuit_ports
    from pdk.tsmc65.signoff import mom_lvs_device

    params = CdacArrayParams(cdac=CdacParams(unit_cap=0.8 * f), active_layers=active_layers)
    ideal = CdacArray(params)
    lvs = CdacArray(
        replace(params, unit_models=tuple(mom_lvs_device(layer, active_layers[0] - 1) for layer in active_layers))
    )
    expected_ports = (
        "cap_topplate",
        "cap_shieldplate",
        *(f"cap_botplate_{kind}<{stage}>" for kind in ("main", "diff") for stage in range(16)),
    )
    assert tuple(ideal.ports) == tuple(lvs.ports) == expected_ports
    assert len(ideal.instances) == len(lvs.instances) == 2 * 41 * len(active_layers)
    for name, instance in ideal.instances.items():
        assert {pin: net.name for pin, net in instance.conns.items()} == {
            pin: net.name for pin, net in lvs.instances[name].conns.items()
        }
        assert tuple(instance.of.ports) == ("PLUS", "MINUS", "BULK")
        assert not lvs.instances[name].of.instances
    # Layer decomposition must not silently multiply the configured ideal C.
    totals = {
        kind: sum(
            float(instance.of.cap.of.params.c) for name, instance in ideal.instances.items() if name.startswith(kind)
        )
        for kind in ("main", "diff")
    }
    assert totals["main"] == pytest.approx(1884.8e-15, rel=1e-12, abs=1e-27)
    assert totals["diff"] == pytest.approx(247.2e-15, rel=1e-12, abs=1e-27)
    assert totals["main"] - totals["diff"] == pytest.approx(2047 * 0.8e-15, rel=1e-12, abs=1e-27)
    for module in (ideal, lvs):
        module.name = "array_interface_test"
        source = io.StringIO()
        h.netlist(module, source, fmt="spice")
        assert subcircuit_ports(source.getvalue(), module.name) == expected_ports


def test_cdac_array_rejects_incompatible_device_views() -> None:
    from pdk.tsmc65.signoff import mom_lvs_device

    params = CdacArrayParams(active_layers=(6, 7))
    assert not is_valid_cdac_array_params(replace(params, active_layers=(7, 6)))
    assert not is_valid_cdac_array_params(replace(params, active_layers=()))
    assert not is_valid_cdac_array_params(replace(params, unit_models=(mom_lvs_device(6, 5),)))
    bad = h.Module(name="missing_bulk")
    bad.PLUS, bad.MINUS = h.Inouts(2)
    assert not is_valid_cdac_array_params(replace(params, unit_models=(bad, bad)))


def test_geometry_is_derived_from_rules() -> None:
    params = _params()
    geometry = _calc_unit_geometry(params, _rules())
    assert (geometry.finger_width, geometry.gap, geometry.end_gap) == (100, 100, 120)
    assert (geometry.weight_step, geometry.tail_length, geometry.unit_pitch) == (400, 520, 400)
    assert (geometry.via_cut, geometry.via_pitch, geometry.via_landing) == (100, 200, 380)
    scaled = _calc_unit_geometry(params, _rules(pitch=240, eol_threshold=90))
    assert (scaled.end_gap, scaled.weight_step, scaled.tail_length) == (100, 480, 520)
    larger_area = _rules()
    larger_area.M4.area = 64_000
    assert _calc_unit_geometry(params, larger_area).tail_length == 640
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
    assert len(list(top.each_inst())) == 43
    assert top.dbbox().width() == pytest.approx(18.40)
    assert top.dbbox().height() == pytest.approx(53.08)
    texts = {shape.text.string for shape in top.shapes(_layer_index(loaded, 13, 1)).each() if shape.is_text()}
    assert len(texts) == 34
    assert {"cap_topplate", "cap_shieldplate", "cap_botplate_main<15>", "cap_botplate_diff<0>"} <= texts


def test_layout_width_grows_one_pitch_per_chunk(monkeypatch: pytest.MonkeyPatch) -> None:
    one = _generate(monkeypatch, _params((64,), top_cell="one"))
    three = _generate(monkeypatch, _params((129,), top_cell="three"))
    assert three.cell("three").dbbox().width() - one.cell("one").dbbox().width() == pytest.approx(0.8)
    assert len(list(one.cell("one").each_inst())) == 3
    assert len(list(three.cell("three").each_inst())) == 5


def test_shared_m4_keeps_m3_empty_and_owns_shield_tabs(monkeypatch: pytest.MonkeyPatch) -> None:
    params = _params(shield_layer=4, active_layers=(5, 6, 7))
    layout = _generate(monkeypatch, params)
    top = layout.cell(params.top_cell)
    assert db.Region(top.begin_shapes_rec(layout.layer(11, 0))).is_empty()
    assert db.Region(top.begin_shapes_rec(layout.layer(12, 0))).is_empty()
    # Four additional floating M4 landings belong to the two edge dummies.
    assert len(list(db.Region(top.begin_shapes_rec(layout.layer(13, 0))).merged().each())) == 38
    right_edge = top.bbox().right
    tabs = [
        shape.bbox().to_dtype(layout.dbu)
        for shape in top.shapes(layout.layer(13, 0)).each()
        if shape.bbox().right == right_edge
    ]
    assert len(tabs) == 16
    assert all(tab.height() == pytest.approx(0.10) and tab.width() == pytest.approx(1.10) for tab in tabs)
    assert sorted(tab.bottom for tab in tabs) == pytest.approx(
        [3.22, 6.22, 9.22, 12.22, 15.22, 18.22, 21.22, 24.22, 28.60, 31.60, 34.60, 37.60, 40.60, 43.60, 46.60, 49.60]
    )


@pytest.mark.parametrize("shield_layer,active_layers", [(5, (6, 7)), (4, (5, 6, 7))])
def test_every_shield_tab_reaches_the_shield(
    monkeypatch: pytest.MonkeyPatch, shield_layer: int, active_layers: tuple[int, ...]
) -> None:
    params = _params(shield_layer=shield_layer, active_layers=active_layers)
    layout = _generate(monkeypatch, params)
    top = layout.cell(params.top_cell)
    route_index = layout.layer(13, 0)
    route = db.Region(top.begin_shapes_rec(route_index)).merged()
    shield = db.Region(top.begin_shapes_rec(layout.layer(5 + 2 * shield_layer, 0))).merged()
    shield_body = db.Region(max(shield.each(), key=lambda polygon: polygon.area()))
    shield_tag = db.Region(top.begin_shapes_rec(layout.layer(155, 104)))
    assert not shield_tag.is_empty()
    assert ((shield_tag & shield) - shield_body).is_empty(), "LVS shield tag touches a signal landing"
    topplate_point = next(
        db.Point(shape.text.x, shape.text.y)
        for shape in top.shapes(layout.layer(13, 1)).each()
        if shape.is_text() and shape.text.string == "cap_topplate"
    )
    tabs = [
        shape.bbox()
        for shape in top.shapes(route_index).each()
        if shape.is_box() and shape.bbox().right == top.bbox().right and not shape.bbox().contains(topplate_point)
    ]
    # A missing last tab must fail as well as a strap ending before its vias.
    assert len(tabs) == 16
    via4 = db.Region(top.begin_shapes_rec(layout.layer(14, 0)))
    for tab in tabs:
        connection = route.interacting(db.Region(tab))
        assert connection.count() == 1
        assert all(not polygon.inside(topplate_point) for polygon in connection.each())
        if shield_layer == params.route_layer:
            assert (db.Region(tab) - shield_body).is_empty()
        else:
            cuts = via4.interacting(connection)
            assert not cuts.is_empty()
            assert (cuts - connection).is_empty(), "M4 strap does not cover its shield vias"
            assert (cuts - shield_body).is_empty(), "shield vias do not reach the shield body"


def test_manifest_tracks_dynamic_array(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("flow.cdac.laygen.import_module", lambda _name: _SyntheticPdkLayout)
    manifest = _layout_manifest(_params((129, 64, 1)))
    assert manifest["physical_chunk_count"] == 5
    assert manifest["edge_dummy_count"] == 2
    assert manifest["placed_unit_count"] == 7
    assert manifest["port_count"] == 8
    assert manifest["partitioned_weights_by_stage"] == [[64, 64, 1], [64], [1]]


def test_reviewed_landings_and_bent_topplate(monkeypatch: pytest.MonkeyPatch) -> None:
    layout = _generate(monkeypatch, _params(shield_layer=4, active_layers=(5, 6, 7)))
    top = layout.cell("frida_caparray")
    route = db.Region(top.begin_shapes_rec(layout.layer(13, 0))).merged()
    labels = {s.text.string: db.Point(s.text.x, s.text.y) for s in top.each_shape(layout.layer(13, 1)) if s.is_text()}
    for name, expected in (
        ("cap_botplate_main<15>", (0.60, 0.22, 0.70, 0.74)),
        ("cap_botplate_main<0>", (12.20, 0.22, 16.70, 0.74)),
        ("cap_botplate_diff<0>", (12.20, 52.06, 16.70, 52.58)),
        ("cap_topplate", (17.60, 51.64, 17.98, 52.02)),
    ):
        polygon = next(poly for poly in route.each() if poly.inside(labels[name]))
        bbox = polygon.bbox().to_dtype(layout.dbu)
        assert (bbox.left, bbox.bottom, bbox.right, bbox.top) == pytest.approx(expected)
    m6 = db.Region(top.begin_shapes_rec(layout.layer(17, 0)))
    for box in (db.DBox(0, 52.70, 17.60, 53.08), db.DBox(17.60, 51.64, 17.98, 53.08)):
        assert (db.Region(box.to_itype(layout.dbu)) - m6).is_empty()
    unit = layout.cell("frida_mom_w64_m5_m6_m7")
    for via_number in (4, 5, 6):
        cuts = db.Region(unit.begin_shapes_rec(layout.layer(6 + 2 * via_number, 0)))
        assert len(list(cuts.each())) == 4  # Two cuts for each main/diff finger in this unit cell.
        assert sorted(poly.bbox().center().y * layout.dbu for poly in cuts.each()) == pytest.approx(
            [0.31, 0.51, 52.29, 52.49]
        )
