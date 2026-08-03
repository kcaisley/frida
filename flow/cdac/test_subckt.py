"""Software-only tests for the CDAC subcircuit and layout generators."""

from pathlib import Path

from klayout import db

from flow.layout.dsl import GenericLayers

from .layout import FRIDA_CAP_WEIGHTS, UNARY_WEIGHT, build_layout, partition_weights
from .subckt import Cdac, CdacParams, RedunStrat, get_cdac_weights


class _SmokeTestPdkLayout:
    """Minimal TSMC65-like layer interface for portable layout regression."""

    DBU = 0.0005

    @staticmethod
    def layer_map() -> dict[db.LayerInfo, db.LayerInfo]:
        generic = GenericLayers()
        return {
            generic.M4: db.LayerInfo(13, 0, "METAL4"),
            generic.PIN4: db.LayerInfo(13, 1, "M4.PIN"),
            generic.VIA4: db.LayerInfo(14, 0, "VIA4"),
            generic.M5: db.LayerInfo(15, 0, "METAL5"),
            generic.VIA5: db.LayerInfo(16, 0, "VIA5"),
            generic.M6: db.LayerInfo(17, 0, "METAL6"),
            generic.PIN6: db.LayerInfo(17, 1, "M6.PIN"),
        }


def _layer_index(layout: db.Layout, layer: int, datatype: int) -> int:
    """Find a layer after GDS round-tripping, which may discard layer names."""
    for index in layout.layer_indexes():
        info = layout.get_info(index)
        if (info.layer, info.datatype) == (layer, datatype):
            return index
    raise AssertionError(f"missing GDS layer {layer}/{datatype}")


def test_cdac():
    """Verify CDAC generator produces a valid module."""
    m = Cdac(CdacParams())
    assert m is not None


def test_cdac_weights():
    """Test weight calculation for different strategies."""
    assert get_cdac_weights(CdacParams()) == list(FRIDA_CAP_WEIGHTS)

    params = CdacParams(n_dac=8, n_extra=0, redun_strat=RedunStrat.RDX2)
    weights = get_cdac_weights(params)
    assert len(weights) == 8

    params = CdacParams(n_dac=8, n_extra=2, redun_strat=RedunStrat.SUBRDX2_LIM)
    weights = get_cdac_weights(params)
    assert len(weights) == 10


def test_explicit_cdac_weights_override_strategy():
    """Explicit physical weights bypass the strategy calculation."""
    explicit = (8, 5, 2, 1)
    params = CdacParams(
        n_dac=3,
        n_extra=1,
        redun_strat=RedunStrat.SUBRDX2,
        weights=explicit,
    )
    assert get_cdac_weights(params) == list(explicit)


def test_cdac_connects_msb_to_largest_weight():
    """Connect the MSB-first weight list to bus bits from MSB down to LSB."""
    params = CdacParams(
        n_dac=3,
        n_extra=1,
        weights=(8, 5, 2, 1),
    )
    module = Cdac(params)

    assert float(module.C_3.of.params.c) == 8e-15
    assert module.MP_buf_3.conns["g"].index == 3
    assert float(module.C_0.of.params.c) == 1e-15
    assert module.MP_buf_0.conns["g"].index == 0


def test_default_cdac_driver_strengths_match_frida_bands() -> None:
    """Use 4×, 2×, and 1× driver bands from MSB to LSB."""
    params = CdacParams()
    module = Cdac(params)
    strengths = (4, 4, 2, 2) + (1,) * 12

    for bit, strength in zip(reversed(range(16)), strengths, strict=True):
        assert getattr(module, f"MP_drv_{bit}").of.params.w == params.driver_p_w * strength
        assert getattr(module, f"MN_drv_{bit}").of.params.w == params.driver_n_w * strength


def test_explicit_cdac_weights_are_validated():
    """Reject the wrong count and non-positive values."""
    for weights in ((8, 4, 2), (8, 4, 0, 1)):
        params = CdacParams(n_dac=3, n_extra=1, weights=weights)
        try:
            get_cdac_weights(params)
        except ValueError:
            pass
        else:
            raise AssertionError(f"accepted invalid explicit weights {weights}")


def test_transitional_layout_preserves_frida_weights():
    partitioned = partition_weights(list(FRIDA_CAP_WEIGHTS), UNARY_WEIGHT)

    assert [sum(group) for group in partitioned] == list(FRIDA_CAP_WEIGHTS)
    assert all(0 < chunk <= UNARY_WEIGHT for group in partitioned for chunk in group)


def test_transitional_layout_gds_smoke(tmp_path: Path):
    """Generate, write, and re-read the complete FRIDA capacitor array."""
    output = tmp_path / "frida_caparray.gds"
    build_layout("frida_caparray", _SmokeTestPdkLayout).write(str(output))

    loaded = db.Layout()
    loaded.read(str(output))
    top_cells = loaded.top_cells()

    assert output.stat().st_size > 0
    assert loaded.cells() == 42
    assert [cell.name for cell in top_cells] == ["frida_caparray"]
    assert {(loaded.get_info(index).layer, loaded.get_info(index).datatype) for index in loaded.layer_indexes()} == {
        (13, 0),
        (13, 1),
        (14, 0),
        (15, 0),
        (16, 0),
        (17, 0),
        (17, 1),
    }

    top = top_cells[0]
    pin4_texts = {shape.text.string for shape in top.shapes(_layer_index(loaded, 13, 1)).each() if shape.is_text()}
    expected_bottom_pins = {
        f"cap_botplate_{side}[{bit}]" for side in ("m", "d") for bit in range(len(FRIDA_CAP_WEIGHTS))
    }
    pin6_texts = {shape.text.string for shape in top.shapes(_layer_index(loaded, 17, 1)).each() if shape.is_text()}

    assert pin4_texts == expected_bottom_pins
    assert pin6_texts == {"cap_topplate"}
    assert top.bbox().width() > 0
    assert top.bbox().height() > 0
