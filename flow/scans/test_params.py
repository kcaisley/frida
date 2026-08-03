"""Software-only unit tests for ADC parameters; no hardware I/O is performed."""

import dataclasses

import hdl21 as h
import pytest
from hdl21.prefix import m

from flow.scans.params import (
    AdcTbParams,
    build_variants,
    convert_sample_rate_to_baud,
    validate_params,
)


def test_default_params_are_valid_and_immutable() -> None:
    params = AdcTbParams()

    validate_params(params)
    assert isinstance(params.vin_diff, h.Vdc.Params)
    assert float(params.vin_diff.dc) == 0.0
    assert params.board_id is None
    with pytest.raises(dataclasses.FrozenInstanceError):
        params.conversions = 1


def test_analog_input_preserves_hdl21_source_type() -> None:
    inputs = (
        h.Vdc.Params(dc=100 * m),
        h.Vsin.Params(voff=0.0, vamp=100 * m, freq=1e6),
        h.Vpwl.Params(wave="0 -100m 1m 100m"),
    )

    params = [AdcTbParams(vin_diff=source) for source in inputs]

    assert [type(item.vin_diff) for item in params] == [type(source) for source in inputs]


def test_build_variants_covers_adc00_seven_offset_noise_rates() -> None:
    variants = build_variants()

    assert len(variants) == 7 * 39
    assert {item.observed_adc for item in variants} == {0}
    assert {float(item.symbol_rate) for item in variants} == {rate * 40e6 for rate in range(2, 41)}
    assert all(item.board_id == "00" for item in variants)
    assert {item.active_adc_mask for item in variants} == {
        (0,) * 15 + (1,),
    }
    assert all(item.dut.adc_bits == 12 for item in variants)
    assert all(item.dut.cdac.weights is not None for item in variants)
    assert all(item.conversions == 1_000 for item in variants)
    assert all(isinstance(item.vin_diff, h.Vdc.Params) for item in variants)
    assert {float(item.symbol_rate) / 160 for item in variants} == {rate * 0.25e6 for rate in range(2, 41)}
    assert {float(item.vin_diff.dc) for item in variants} == {0.05}
    assert {float(item.vin_cm.dc) for item in variants} == {0.8}
    assert {float(item.seq_logic_phase_delay_symbols) for item in variants} == set(range(-3, 4))


def test_convert_sample_rate_to_baud_uses_active_pattern_span() -> None:
    params = AdcTbParams()
    assert convert_sample_rate_to_baud(params, 1e6) == 160e6

    inactive = "0" * len(params.seq_init_pattern)
    with pytest.raises(ValueError, match="no active symbols"):
        convert_sample_rate_to_baud(
            AdcTbParams(
                seq_init_pattern=inactive,
                seq_samp_pattern=inactive,
                seq_comp_pattern=inactive,
                seq_logic_pattern=inactive,
            ),
            1e6,
        )
    with pytest.raises(ValueError, match="finite and positive"):
        convert_sample_rate_to_baud(params, 0.0)


def test_validation_rejects_invalid_configuration_relationships() -> None:
    incomplete_measurement = AdcTbParams(board_id="00")
    invalid_bus = AdcTbParams(dac_astate_p=(0,) * 15 + (2,))
    unequal_patterns = AdcTbParams(seq_logic_pattern="01")

    with pytest.raises(ValueError, match="must be set together"):
        validate_params(incomplete_measurement)
    with pytest.raises(ValueError, match="zero or one"):
        validate_params(invalid_bus)
    with pytest.raises(ValueError, match="equal length"):
        validate_params(unequal_patterns)
