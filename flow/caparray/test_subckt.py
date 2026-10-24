"""Software-only tests for the CDAC electrical and physical generators."""

from dataclasses import asdict, replace
from itertools import pairwise
from pathlib import Path
from types import SimpleNamespace

import hdl21 as h
import pytest
from hdl21.prefix import f
from klayout import db

from flow.layout.pdkproc import in_pdk

from .layout import (
    ADC_ARRAYS,
    ADC_BITS,
    CAP_SCALES,
    FRIDA1_ADC_ARRAY,
    RADIX17,
    CapArrayLayoutParams,
    UnitLengthCapFamilyParams,
    _layout_manifest,
    _ordered_groups,
    _UnitGeometry,
    adc_arrays,
    array_name,
    caparray_spec,
    is_valid_caparray_layout_params,
)
from .subckt import (
    CapArray,
    CapArrayConfig,
    CapArrayParams,
    RedunStrat,
    _calc_weight_partitions,
    get_caparray_weights,
    is_valid_caparray_config,
    is_valid_caparray_params,
    switched_capacitance_f,
    tolerance_units,
    total_capacitance_f,
    unit_capacitance_f,
)


def _rules(*, pitch: int = 200, eol_threshold: int = 120) -> SimpleNamespace:
    """A synthetic PDK ``tech`` module: metal and via rules on M3-M7."""
    metal = {
        "width": 100,
        "space": 100,
        "pitch": pitch,
        "area": 52_000,
        "enclosed_area": 200_000,
        "max_density": 0.90,
        "parallel_space": ((120, 200, 380),),
        "end_of_line": ((120, eol_threshold, 35),),
    }
    via = {"cut": 100, "space": 100, "enclosure": (40, 0, 30)}
    rules = {**{f"M{n}": dict(metal) for n in range(3, 8)}, **{f"V{n}": dict(via) for n in range(3, 7)}}
    layers = {
        "MOM_RECOG": (250, 100),
        "MOM_RECOG_SHIELD": (250, 104),
        "MOM_RECOG_M5": (250, 105),
        "MOM_RECOG_M6": (250, 106),
        "MOM_RECOG_M7": (250, 107),
        "MOM_RECOG_INNER": (250, 120),
        "BND": (189, 0),
        **{f"M{n}": (5 + 2 * n, 0) for n in range(3, 8)},
        **{f"M{n}.PIN": (5 + 2 * n, 1) for n in range(3, 8)},
        **{f"V{n}": (6 + 2 * n, 0) for n in range(3, 7)},
    }
    return SimpleNamespace(DBU=0.001, MFG_GRID=5, RULES=rules, LAYERS=layers)


def synthetic(function: str, *args, rules: dict | None = None, **kwargs):
    """Call a stems ``capcell`` function on the synthetic PDK (in a process bound to a real one):
    ``rules`` overrides ``{"M4": {"area": ...}}`` and ``pitch`` / ``eol_threshold`` its metals."""

    import capcell

    capcell.tech = _rules(**kwargs)
    for layer, values in (rules or {}).items():
        capcell.tech.RULES[layer].update(values)
    return getattr(capcell, function)(*args)


def _geometry(params: CapArrayLayoutParams, **kwargs) -> _UnitGeometry:
    stack = (asdict(params.family), params.route_layer, params.shield_layer, params.active_layers)
    return _UnitGeometry(**in_pdk("tsmc65", __name__, "synthetic", "difference_geometry", *stack, **kwargs))


def _params(
    weights: tuple[int, ...] = (768, 512, 320, 192, 96, 64, 32, 24, 12, 10, 5, 4, 4, 2, 1, 1),
    *,
    shield_layer: int = 5,
    active_layers: tuple[int, ...] = (6,),
    top_cell: str = "frida_caparray",
) -> CapArrayLayoutParams:
    return CapArrayLayoutParams(
        cdac=CapArrayConfig(n_dac=len(weights), n_extra=0, weights=weights),
        family=UnitLengthCapFamilyParams(),
        technology="synthetic",
        route_layer=4,
        shield_layer=shield_layer,
        active_layers=active_layers,
        top_cell=top_cell,
    )


def _generate(tmp_path: Path, params: CapArrayLayoutParams) -> db.Layout:
    path = str(tmp_path / f"{params.top_cell}.gds")
    in_pdk("tsmc65", __name__, "synthetic", "caparray_gds", caparray_spec(params), path)
    layout = db.Layout()
    layout.read(path)
    return layout


def _layer_index(layout: db.Layout, layer: int, datatype: int) -> int:
    for index in layout.layer_indexes():
        info = layout.get_info(index)
        if (info.layer, info.datatype) == (layer, datatype):
            return index
    raise AssertionError(f"missing GDS layer {layer}/{datatype}")


def test_cdac_and_weight_strategies() -> None:
    assert CapArray(CapArrayParams()) is not None
    assert get_caparray_weights(CapArrayConfig(n_dac=8, n_extra=0, redun_strat=RedunStrat.BINARY)) == [
        128, 64, 32, 16, 8, 4, 2, 1,
    ]  # fmt: skip
    # binary has no extra cycles and every other scheme at least one
    assert not is_valid_caparray_config(CapArrayConfig(n_dac=8, n_extra=2, redun_strat=RedunStrat.BINARY))
    for scheme in (RedunStrat.MSB_SPLIT, RedunStrat.LSB_SPLIT, RedunStrat.MSB_REDIST):
        assert not is_valid_caparray_config(CapArrayConfig(n_dac=8, n_extra=0, redun_strat=scheme))
        assert len(get_caparray_weights(CapArrayConfig(n_dac=9, n_extra=6, redun_strat=scheme))) == 15
    assert not is_valid_caparray_config(CapArrayConfig(cap_scale=0))
    # the names archived measurements store, read back as the same members
    assert RedunStrat["SUBRDX2_OVLY"] is RedunStrat.MSB_REDIST and RedunStrat["RDX2"] is RedunStrat.BINARY
    assert list(RedunStrat) == [RedunStrat.BINARY, RedunStrat.MSB_SPLIT, RedunStrat.LSB_SPLIT, RedunStrat.MSB_REDIST]


# each scheme's arrays, C0 first, at 10 and 14 bits (n_dac 9 and 13) with 1, 3 and 5 extra cycles
SCHEMES = {
    (RedunStrat.MSB_SPLIT, 9, 1): (128, 128, 128, 64, 32, 16, 8, 4, 2, 1),
    (RedunStrat.MSB_SPLIT, 9, 3): (128, 128, 64, 64, 32, 32, 32, 16, 8, 4, 2, 1),
    (RedunStrat.MSB_SPLIT, 9, 5): (128, 128, 64, 64, 32, 32, 16, 16, 8, 8, 8, 4, 2, 1),
    (RedunStrat.LSB_SPLIT, 9, 1): (256, 128, 64, 32, 16, 8, 4, 1, 1, 1),
    (RedunStrat.LSB_SPLIT, 9, 3): (256, 128, 64, 32, 16, 4, 4, 2, 2, 1, 1, 1),
    (RedunStrat.LSB_SPLIT, 9, 5): (256, 128, 64, 16, 16, 8, 8, 4, 4, 2, 2, 1, 1, 1),
    (RedunStrat.MSB_REDIST, 9, 1): (224, 128, 72, 40, 20, 12, 8, 4, 2, 1),
    (RedunStrat.MSB_REDIST, 9, 3): (192, 128, 80, 48, 24, 16, 8, 6, 5, 2, 1, 1),
    (RedunStrat.MSB_REDIST, 9, 5): (128, 128, 96, 64, 32, 24, 12, 10, 5, 4, 4, 2, 1, 1),
    (RedunStrat.MSB_SPLIT, 13, 1): (2048, 2048, 2048, 1024, 512, 256, 128, 64, 32, 16, 8, 4, 2, 1),
    (RedunStrat.MSB_SPLIT, 13, 3): (2048, 2048, 1024, 1024, 512, 512, 512, 256, 128, 64, 32, 16, 8, 4, 2, 1),
    (RedunStrat.MSB_SPLIT, 13, 5): (2048, 2048, 1024, 1024, 512, 512, 256, 256, 128, 128, 128, 64, 32, 16, 8, 4, 2, 1),
    (RedunStrat.LSB_SPLIT, 13, 1): (4096, 2048, 1024, 512, 256, 128, 64, 32, 16, 8, 4, 1, 1, 1),
    (RedunStrat.LSB_SPLIT, 13, 3): (4096, 2048, 1024, 512, 256, 128, 64, 32, 16, 4, 4, 2, 2, 1, 1, 1),
    (RedunStrat.LSB_SPLIT, 13, 5): (4096, 2048, 1024, 512, 256, 128, 64, 16, 16, 8, 8, 4, 4, 2, 2, 1, 1, 1),
    (RedunStrat.MSB_REDIST, 13, 1): (3968, 2048, 1056, 544, 272, 144, 72, 40, 20, 12, 8, 4, 2, 1),
    (RedunStrat.MSB_REDIST, 13, 3): (3840, 2048, 1088, 576, 288, 160, 80, 48, 24, 16, 8, 6, 5, 2, 1, 1),
    (RedunStrat.MSB_REDIST, 13, 5): (3584, 2048, 1152, 640, 320, 192, 96, 64, 32, 24, 12, 10, 5, 4, 4, 2, 1, 1),
}  # fmt: skip


def test_every_scheme_redistributes_the_binary_weight() -> None:
    for (scheme, n_dac, extra), expected in SCHEMES.items():
        assert tuple(get_caparray_weights(CapArrayConfig(n_dac=n_dac, n_extra=extra, redun_strat=scheme))) == expected
    # FRIDA-1's array is MSB redistribution with 5 at n_dac = 11
    assert get_caparray_weights(RADIX17) == [768, 512, 320, 192, 96, 64, 32, 24, 12, 10, 5, 4, 4, 2, 1, 1]
    for n_dac in range(2, 16):
        for extra in range(1, 7):
            for scheme in (RedunStrat.MSB_SPLIT, RedunStrat.LSB_SPLIT, RedunStrat.MSB_REDIST):
                config = CapArrayConfig(n_dac=n_dac, n_extra=extra, redun_strat=scheme)
                if not is_valid_caparray_config(config):
                    continue
                weights = get_caparray_weights(config)
                # the binary total, falling, no negative tolerance: every code reached
                assert sum(weights) == 2**n_dac - 1 and len(weights) == n_dac + extra
                assert weights == sorted(weights, reverse=True) and min(tolerance_units(weights)) >= 0
    # every scheme reaches 1 to 6 extra cycles from 9 to 13 steps
    assert all(
        is_valid_caparray_config(CapArrayConfig(n_dac=n_dac, n_extra=extra, redun_strat=scheme))
        for n_dac in range(9, 14)
        for extra in range(1, 7)
        for scheme in (RedunStrat.MSB_SPLIT, RedunStrat.LSB_SPLIT, RedunStrat.MSB_REDIST)
    )
    # where the tolerance falls: the split MSBs' stages, the split LSBs' stages, the overlay's
    assert tolerance_units(SCHEMES[RedunStrat.MSB_SPLIT, 9, 1]) == [256, 128] + [0] * 8
    assert tolerance_units(SCHEMES[RedunStrat.LSB_SPLIT, 9, 1]) == [0] * 7 + [2, 1, 0]
    assert (
        tolerance_units(get_caparray_weights(CapArrayConfig(n_dac=9, n_extra=0, redun_strat=RedunStrat.BINARY)))
        == [0] * 9
    )


def test_the_switched_capacitance_puts_kt_c_at_the_quantization_noise() -> None:
    # 2 kT / C = LSB^2 / 12 with LSB = 2 V / 2^N: the 14-bit row of the table, 6.7 pF
    assert total_capacitance_f(14, 1.0) == pytest.approx(6.671e-12, rel=1e-3)
    assert total_capacitance_f(11, 1.0) == pytest.approx(4**-3 * total_capacitance_f(14, 1.0))
    # 1/cap_scale of the quantization noise, at a full scale's square
    assert total_capacitance_f(12, 0.5, 2) == pytest.approx(2 * 4 * total_capacitance_f(12, 1.0))
    for name, config in ADC_ARRAYS.items():
        # by default an ideal array at 1 V: every scheme the same capacitance at a resolution and scale
        bits = config.n_dac + 1
        assert switched_capacitance_f(config) == pytest.approx(config.cap_scale * total_capacitance_f(bits, 1.0))
        assert unit_capacitance_f(config) * (2**config.n_dac - 1) == pytest.approx(switched_capacitance_f(config)), name
        # at a full scale FS of a reference: the switched share FS / reference of the top plate
        assert switched_capacitance_f(config, 0.96, 1.2) == pytest.approx(
            total_capacitance_f(bits, 0.96, config.cap_scale) * 0.8
        )
    assert unit_capacitance_f(ADC_ARRAYS["10b_binary_x1"]) == pytest.approx(51.0e-18, rel=1e-2)
    assert unit_capacitance_f(ADC_ARRAYS["14b_msb_redist6_x2"]) == pytest.approx(1.629e-15, rel=1e-3)


def test_the_adc_arrays_are_ten_a_resolution_and_scale_and_frida1s() -> None:
    assert len(ADC_ARRAYS) == len(ADC_BITS) * len(CAP_SCALES) * 10 + 1 == 61
    # FRIDA-1's: its scheme at 12 bits, at two of the resolution's least capacitance
    assert ADC_ARRAYS["12b_msb_redist5_x2"] == FRIDA1_ADC_ARRAY == replace(RADIX17, cap_scale=2)
    assert RADIX17 == CapArrayConfig()
    assert (
        array_name(CapArrayConfig(n_dac=13, n_extra=6, redun_strat=RedunStrat.LSB_SPLIT, cap_scale=2))
        == "14b_lsb_split6_x2"
    )
    for bits in ADC_BITS:
        for scale in CAP_SCALES:
            arrays = adc_arrays(bits, scale)
            weights = {tuple(get_caparray_weights(cdac)) for cdac in arrays}
            assert len(arrays) == len(weights) == 10
            assert all(cdac.n_dac == bits - 1 and cdac.cap_scale == scale for cdac in arrays)
            assert {sum(w) for w in weights} == {2 ** (bits - 1) - 1}
    # the design space never sets FRIDA-1's fabricated fields
    assert all(cdac.weights is None and cdac.driver_strengths is None for cdac in ADC_ARRAYS.values())
    with pytest.raises(ValueError):
        array_name(CapArrayConfig(n_dac=3, n_extra=0, weights=(4, 2, 1)))


def test_a_unary_row_is_one_main_finger_in_the_netlist() -> None:
    weights = (129, 64, 1)
    params = CapArrayParams(
        cdac=CapArrayConfig(n_dac=3, n_extra=0, weights=weights),
        unit_cap=1 * f,
        tail_cap=0.25 * f,
        coarse_weight=64,
        unary_rows=True,
    )
    module = CapArray(params)
    names = {name.removesuffix("_m6") for name in module.instances}
    # stage 0: two unary rows and a binary one; stage 1: a unary row alone; stage 2: a binary row
    assert names == {"main_0_0", "main_0_1", "main_0_2", "diff_0_2", "main_1_0", "main_2_0", "diff_2_0"}
    values = {
        name.removesuffix("_m6"): float(inst.of.cap.of.params.c) * 1e15 for name, inst in module.instances.items()
    }
    assert values["main_0_0"] == values["main_1_0"] == pytest.approx(64)  # the coarse weight in units
    assert values["main_0_2"] - values["diff_0_2"] == pytest.approx(1)  # a binary row: the difference
    assert values["main_0_2"] + values["diff_0_2"] == pytest.approx(64 + 2 * 0.25)
    plain = CapArray(replace(params, unary_rows=False))
    assert {name.removesuffix("_m6") for name in plain.instances} >= {"diff_0_0", "diff_1_0"}


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
    radix17 = tuple(get_caparray_weights(CapArrayConfig()))
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
    cdac = CapArrayConfig(n_dac=4, n_extra=0, weights=(129, 64, 2, 1))
    params = CapArrayParams(cdac=cdac, unit_cap=0.8 * f)
    assert is_valid_caparray_params(params)
    module = CapArray(params)
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
    import re

    from flow.util.netlist import subcircuit_ports
    from pdk.tsmc65.calibre.signoff import mom_lvs_device

    params = CapArrayParams(cdac=CapArrayConfig(), unit_cap=0.8 * f, active_layers=active_layers)
    ideal = CapArray(params)
    lvs = CapArray(
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
    escaped_ports = tuple(name.replace("<", r"\<").replace(">", r"\>") for name in expected_ports)
    for module in (ideal, lvs):
        module.name = "array_interface_test"
        assert tuple((port.name, port.width) for port in module.ports.values()) == tuple(
            (name, 1) for name in expected_ports
        )
        source = io.StringIO()
        h.netlist(module, source, fmt="spectre")
        spectre = source.getvalue()
        # Normalize comments/continuations, but retain identifier escaping verbatim.
        statements = " ".join(re.sub(r"\n\s*\+", " ", re.sub(r"//[^\n]*", "", spectre)).split())
        assert f"subckt {module.name} {' '.join(escaped_ports)} " in statements
        assert re.search(r"(?<!\\)[<>]|\\\\[<>]", spectre) is None
        for name, instance in module.instances.items():
            bottom = instance.conns["MINUS"].name.replace("<", r"\<").replace(">", r"\>")
            assert f"{name} ( cap_topplate {bottom} cap_shieldplate )" in statements

        assert tuple(module.ports) == expected_ports
        assert tuple((port.name, port.width) for port in module.ports.values()) == tuple(
            (name, 1) for name in expected_ports
        )
        source = io.StringIO()
        h.netlist(module, source, fmt="spice")
        spice = source.getvalue()
        assert subcircuit_ports(spice, module.name) == expected_ports
        assert r"\<" not in spice and r"\>" not in spice
        for instance in module.instances.values():
            assert f"cap_topplate {instance.conns['MINUS'].name} cap_shieldplate" in spice


def test_cdac_array_rejects_incompatible_device_views() -> None:
    from pdk.tsmc65.calibre.signoff import mom_lvs_device

    params = CapArrayParams(active_layers=(6, 7))
    assert not is_valid_caparray_params(replace(params, active_layers=(7, 6)))
    assert not is_valid_caparray_params(replace(params, active_layers=()))
    assert not is_valid_caparray_params(replace(params, unit_models=(mom_lvs_device(6, 5),)))
    bad = h.Module(name="missing_bulk")
    bad.PLUS, bad.MINUS = h.Inouts(2)
    assert not is_valid_caparray_params(replace(params, unit_models=(bad, bad)))


def test_geometry_is_derived_from_rules() -> None:
    params = _params()
    geometry = _geometry(params)
    assert (geometry.finger_width, geometry.gap, geometry.end_gap) == (100, 100, 120)
    assert (geometry.weight_step, geometry.tail_length, geometry.unit_pitch) == (400, 520, 400)
    assert (geometry.via_cut, geometry.via_pitch, geometry.via_landing) == (100, 200, 380)
    scaled = _geometry(params, pitch=240, eol_threshold=90)
    assert (scaled.end_gap, scaled.weight_step, scaled.tail_length) == (100, 480, 520)
    assert _geometry(params, rules={"M4": {"area": 64_000}}).tail_length == 640
    assert _geometry(params, rules={"M6": {"parallel_space": ((140, 90, 380),)}}).gap == 140


def test_a_unit_below_the_tracks_is_two_strips_difference(tmp_path: Path) -> None:
    # a weight step of 45 nm: each unit of weight lengthens the main finger and shortens the
    # difference finger of the same cell by it, both near the family's nominal length
    params = replace(_params((2, 1)), family=UnitLengthCapFamilyParams(weight_step=45))
    geometry = _geometry(params)
    assert geometry.weight_step == 45 and geometry.nominal_length == geometry.tail_length + 64 * 45
    layout = _generate(tmp_path, params)
    for weight in (1, 2, 64):
        unit = layout.cell(f"frida_mom_w{weight}_m6")
        boxes = [shape.bbox() for shape in unit.shapes(layout.layer(17, 0)).each()]
        fingers = [box for box in boxes if box.left == geometry.ring_width + geometry.gap]
        main, diff = sorted(fingers, key=lambda box: box.bottom)
        assert main.height() - geometry.nominal_length == geometry.nominal_length - diff.height() == 45 * weight
    with pytest.raises(Exception, match="off the 5 nm grid"):
        _geometry(replace(params, family=UnitLengthCapFamilyParams(weight_step=47)))
    assert not is_valid_caparray_layout_params(replace(params, family=UnitLengthCapFamilyParams(weight_step=0)))


def test_unary_rows_and_tied_dummies(tmp_path: Path) -> None:
    # stage 0: chunks 64, 64 and 1; stage 1: 64; stage 2: 1
    family = UnitLengthCapFamilyParams(weight_step=45, tied_dummies=True, unary_length=5000)
    params = replace(_params((129, 64, 1)), family=family)
    assert is_valid_caparray_layout_params(params)
    assert not is_valid_caparray_layout_params(replace(params, family=replace(family, unary_length=0)))
    geometry = _geometry(params)
    layout = _generate(tmp_path, params)
    finger_x = geometry.ring_width + geometry.gap

    def fingers(name: str) -> list[db.Box]:
        boxes = [shape.bbox() for shape in layout.cell(name).shapes(layout.layer(17, 0)).each()]
        return sorted((box for box in boxes if box.left == finger_x), key=lambda box: box.bottom)

    def cuts(name: str) -> list[db.Box]:
        return [shape.bbox() for shape in layout.cell(name).shapes(layout.layer(14, 0)).each()]

    # a unary unit: one main finger of the unary length from the bottom, its access at the bottom alone
    (unary,) = fingers("frida_mom_w64u_m6")
    assert (unary.bottom, unary.height()) == (geometry.ring_width + geometry.end_gap, 5000)
    assert all(cut.top < geometry.outer_height / 2 for cut in cuts("frida_mom_w64u_m6"))
    # a binary unit keeps both fingers about the coarse weight
    main, diff = fingers("frida_mom_w1_m6")
    assert main.height() - geometry.nominal_length == geometry.nominal_length - diff.height() == 45
    # a tied dummy: both fingers joined to the ring, no access
    main, diff = fingers("frida_mom_dummy_tied_m6")
    assert (main.bottom, diff.top) == (geometry.ring_width, geometry.outer_height - geometry.ring_width)
    assert not cuts("frida_mom_dummy_tied_m6")
    # the difference buses: over the binary rows alone, none for the unary stage
    top = layout.cell(params.top_cell)
    texts = {s.text.string for s in top.shapes(_layer_index(layout, 13, 1)).each() if s.is_text()}
    assert {"cap_botplate_diff<0>", "cap_botplate_diff<2>"} <= texts and "cap_botplate_diff<1>" not in texts
    route = db.Region(top.begin_shapes_rec(layout.layer(13, 0))).merged()
    labels = {s.text.string: db.Point(s.text.x, s.text.y) for s in top.each_shape(layout.layer(13, 1)) if s.is_text()}
    bus = next(poly for poly in route.each() if poly.inside(labels["cap_botplate_diff<0>"])).bbox()
    assert bus.width() < geometry.unit_pitch  # one unit's landing


def test_a_short_familys_shield_taps_keep_clear_of_the_top_plate(tmp_path: Path) -> None:
    params = replace(
        _params((8, 4, 2, 1), shield_layer=4, active_layers=(5, 6, 7)),
        family=UnitLengthCapFamilyParams(coarse_weight=8, weight_step=145, tied_dummies=True),
    )
    layout = _generate(tmp_path, params)
    top = layout.cell(params.top_cell)
    route = db.Region(top.begin_shapes_rec(layout.layer(13, 0))).merged()
    labels = {s.text.string: db.Point(s.text.x, s.text.y) for s in top.each_shape(layout.layer(13, 1)) if s.is_text()}
    topplate = next(poly for poly in route.each() if poly.inside(labels["cap_topplate"]))
    assert not topplate.inside(labels["cap_shieldplate"])


def test_layout_validation_rejects_reserved_or_nonconsecutive_layers() -> None:
    assert is_valid_caparray_layout_params(_params())
    assert is_valid_caparray_layout_params(_params(shield_layer=4, active_layers=(5, 6, 7)))
    assert is_valid_caparray_layout_params(replace(_params(), route_layer=3))
    assert not is_valid_caparray_layout_params(replace(_params(), route_layer=0))
    assert not is_valid_caparray_layout_params(replace(_params(), route_layer=6))
    assert not is_valid_caparray_layout_params(_params(active_layers=(6, 8)))


def test_rule_derived_radix17_layout(tmp_path: Path) -> None:
    params = _params()
    layout = _generate(tmp_path, params)
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


def test_layout_width_grows_one_pitch_per_chunk(tmp_path: Path) -> None:
    one = _generate(tmp_path, _params((64,), top_cell="one"))
    three = _generate(tmp_path, _params((129,), top_cell="three"))
    assert three.cell("three").dbbox().width() - one.cell("one").dbbox().width() == pytest.approx(0.8)
    assert len(list(one.cell("one").each_inst())) == 3
    assert len(list(three.cell("three").each_inst())) == 5


def test_shared_m4_keeps_m3_empty_and_owns_shield_tabs(tmp_path: Path) -> None:
    params = _params(shield_layer=4, active_layers=(5, 6, 7))
    layout = _generate(tmp_path, params)
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
def test_every_shield_tab_reaches_the_shield(tmp_path: Path, shield_layer: int, active_layers: tuple[int, ...]) -> None:
    params = _params(shield_layer=shield_layer, active_layers=active_layers)
    layout = _generate(tmp_path, params)
    top = layout.cell(params.top_cell)
    route_index = layout.layer(13, 0)
    route = db.Region(top.begin_shapes_rec(route_index)).merged()
    shield = db.Region(top.begin_shapes_rec(layout.layer(5 + 2 * shield_layer, 0))).merged()
    shield_body = db.Region(max(shield.each(), key=lambda polygon: polygon.area()))
    shield_tag = db.Region(top.begin_shapes_rec(layout.layer(250, 104)))
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
    monkeypatch.setattr("flow.caparray.layout._calc_unit_geometry", _geometry)
    manifest = _layout_manifest(_params((129, 64, 1)))
    assert manifest["physical_chunk_count"] == 5
    assert manifest["edge_dummy_count"] == 2
    assert manifest["placed_unit_count"] == 7
    assert manifest["port_count"] == 8
    assert manifest["partitioned_weights_by_stage"] == [[64, 64, 1], [64], [1]]


def test_reviewed_landings_and_bent_topplate(tmp_path: Path) -> None:
    layout = _generate(tmp_path, _params(shield_layer=4, active_layers=(5, 6, 7)))
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


@pytest.mark.parametrize("pdk", ("tsmc28", "tower180", "ihp130", "lf150", "tpsc65"))
def test_array_sizing_reads_the_fmom_model_at_the_drawn_gap(pdk: str) -> None:
    from flow.caparray.layout import _calc_unit_geometry, mom_array_params
    from flow.layout.pdkproc import pdk_value

    mom = pdk_value(pdk, "tech", "MOM_LAYERS")
    params = CapArrayLayoutParams(
        CapArrayConfig(), UnitLengthCapFamilyParams(), pdk, mom[-2] - 1, mom[-2] - 1, tuple(mom[-2:]), "x"
    )
    rows = pdk_value(pdk, "tech", "MOM_MODEL")["difference", 2]
    # rows in rising spacing from the minimum, slopes falling with spacing
    assert [row[0] for row in rows] == sorted(row[0] for row in rows)
    assert all(a[1] > b[1] > 0 for a, b in pairwise(rows))
    space, slope, intercept = rows[0]
    geometry = _calc_unit_geometry(params)
    assert geometry.gap == space  # the generator draws the minimum spacing
    scale = pdk_value(pdk, "tech", "MOM_ARRAY_SCALE", {}).get(2, 1.0)
    assert 0.9 < scale < 1.1
    circuit = mom_array_params(params)
    unit = scale * slope * 1e-15 * 2 * geometry.weight_step / 1000
    assert float(circuit.unit_cap) == pytest.approx(unit)
    assert float(circuit.tail_cap) == pytest.approx(scale * (slope * geometry.tail_length / 1000 + intercept) * 1e-15)
