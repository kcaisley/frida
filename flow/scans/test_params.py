"""Software-only unit tests for ADC parameters; no hardware I/O is performed."""

import dataclasses

import hdl21 as h
import pytest
from hdl21.prefix import m

from flow import adc
from flow.adc import Recipe
from flow.scans.params import (
    AdcScanParams,
    build_adc_variants,
    convert_conversion_rate_to_baud,
    validate_params,
)

timing_sequences = tuple(recipe for recipe in Recipe if recipe.name.startswith("SYMBOL256_INIT8_SAMP16_COMP11110000_"))


def test_default_params_are_valid_and_immutable() -> None:
    params = AdcScanParams(tb=adc.TbParams(pdk="tsmc65", params=adc.Fabricated.FRIDA1_1LAYER_RADIX17.params))

    validate_params(params)
    assert isinstance(params.tb.vin_diff, h.Vdc.Params)
    assert float(params.tb.vin_diff.dc) == 0.0
    assert float(params.tb.vin_cm.dc) == pytest.approx(0.7)
    assert params.board_id is None
    with pytest.raises(dataclasses.FrozenInstanceError):
        params.tb.conversions = 1


def test_analog_input_preserves_hdl21_source_type() -> None:
    inputs = (
        h.Vdc.Params(dc=100 * m),
        h.Vsin.Params(voff=0.0, vamp=100 * m, freq=1e6),
        h.Vpwl.Params(wave="0 -100m 1m 100m"),
    )

    params = [
        adc.TbParams(pdk="tsmc65", params=adc.Fabricated.FRIDA1_1LAYER_RADIX17.params, vin_diff=source)
        for source in inputs
    ]

    assert [type(item.vin_diff) for item in params] == [type(source) for source in inputs]


def test_build_variants_covers_adc00_seven_offset_noise_rates() -> None:
    variants = build_adc_variants(
        board_id=0,
        adc_indices=(0,),
        active_conversion_rates_hz=tuple(rate * 0.25e6 for rate in range(2, 41)),
        sequences=timing_sequences,
        conversions=1_000,
        vin_cm_v=0.8,
        vin_diff=h.Vdc.Params(dc=0.05),
    )

    assert len(variants) == 7 * 39
    assert {item.observed_adc for item in variants} == {0}
    assert {float(item.tb.symbol_rate) for item in variants} == {rate * 40e6 for rate in range(2, 41)}
    assert all(item.board_id == 0 for item in variants)
    assert {item.active_adc_mask for item in variants} == {
        (0,) * 15 + (1,),
    }
    assert all(item.tb.params.adc_bits == 12 for item in variants)
    # FRIDA-1's converter on each channel, its flavor's weights (radix 17: capdac's own)
    assert all(item.tb.params.fabricated is not None for item in variants)
    assert all(item.tb.conversions == 1_000 for item in variants)
    assert all(isinstance(item.tb.vin_diff, h.Vdc.Params) for item in variants)
    assert {float(item.tb.symbol_rate) / 160 for item in variants} == {rate * 0.25e6 for rate in range(2, 41)}
    assert {float(item.tb.vin_diff.dc) for item in variants} == {0.05}
    assert {float(item.tb.vin_cm.dc) for item in variants} == {0.8}
    assert {item.tb.seq_logic.data for item in variants} == {row.rows[3] for row in timing_sequences}


def test_build_adc_variants_covers_adc00_through_adc03_ramp() -> None:
    """Describe one repeated full-scale ramp capture for each selected ADC."""

    variants = build_adc_variants(
        board_id=0,
        adc_indices=(0, 1, 2, 3),
        active_conversion_rates_hz=(1.0e6,),
        sequences=(Recipe.SYMBOL256_INIT8_SAMP16_COMP11110000_LOGIC00001111,),
        conversions=4_000_000,
        vin_cm_v=0.6,
        vin_diff=h.Vpwl.Params(wave="0 -1 0.1 1"),
        campaign="adc_ramp",
    )

    assert len(variants) == 4
    assert {item.observed_adc for item in variants} == set(range(4))
    assert all(item.board_id == 0 for item in variants)
    assert all(item.campaign == "adc_ramp" for item in variants)
    assert all(item.tb.conversions == 4_000_000 for item in variants)
    assert all(float(item.tb.symbol_rate) == 160e6 for item in variants)
    assert all(float(item.tb.vin_cm.dc) == 0.6 for item in variants)
    assert all(isinstance(item.tb.vin_diff, h.Vpwl.Params) for item in variants)
    assert {item.tb.vin_diff.wave for item in variants} == {"0 -1 0.1 1"}
    assert {item.active_adc_mask for item in variants} == {
        (0,) * (15 - adc_index) + (1,) + (0,) * adc_index for adc_index in range(4)
    }


def test_convert_conversion_rate_to_baud_uses_conversion_duration() -> None:
    params = adc.TbParams(pdk="tsmc65", params=adc.Fabricated.FRIDA1_1LAYER_RADIX17.params)
    assert convert_conversion_rate_to_baud(params, 1e6) == 160e6

    inactive = "0" * len(params.seq_init.data)
    with pytest.raises(ValueError, match="one INIT rising edge"):
        convert_conversion_rate_to_baud(
            adc.TbParams(pdk="tsmc65", params=adc.Fabricated.FRIDA1_1LAYER_RADIX17.params).sequenced(
                (inactive, inactive, inactive, inactive)
            ),
            1e6,
        )
    with pytest.raises(ValueError, match="finite and positive"):
        convert_conversion_rate_to_baud(params, 0.0)


def test_validation_rejects_invalid_configuration_relationships() -> None:
    incomplete_measurement = AdcScanParams(
        tb=adc.TbParams(pdk="tsmc65", params=adc.Fabricated.FRIDA1_1LAYER_RADIX17.params), board_id=0
    )
    with pytest.raises(ValueError, match="must be set together"):
        validate_params(incomplete_measurement)
    # a testbench refuses its own invalid values when it is built
    with pytest.raises(ValueError, match="holds a bit"):
        adc.TbParams(pdk="tsmc65", params=adc.Fabricated.FRIDA1_1LAYER_RADIX17.params, dac_astate_p=(0,) * 15 + (2,))
    tb = adc.TbParams(pdk="tsmc65", params=adc.Fabricated.FRIDA1_1LAYER_RADIX17.params)
    with pytest.raises(ValueError, match="equal lengths"):
        tb.sequenced((*tb.rows[:3], "01"))
    # a physical scan takes one of FRIDA-1's fabricated converters
    with pytest.raises(ValueError, match="fabricated converters"):
        validate_params(AdcScanParams(tb=adc.TbParams(pdk="tsmc65", params=adc.Params())))


def test_variants_use_selected_sequence_to_set_conversion_rate():
    variants = build_adc_variants(
        board_id=0,
        adc_indices=(0,),
        active_conversion_rates_hz=(10e6,),
        sequences=(
            Recipe.SYMBOL256_INIT8_SAMP16_COMP11110000_LOGIC11000011,
            Recipe.SYMBOL256_INIT8_SAMP16_COMP11111100_LOGIC00000010,
        ),
        conversions=4,
        vin_cm_v=0.6,
        vin_diff=h.Vdc.Params(dc=0.05),
    )
    assert [float(item.tb.symbol_rate) for item in variants] == [1.6e9, 1.68e9]
