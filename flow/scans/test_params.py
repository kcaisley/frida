"""Software-only unit tests for ADC parameters; no hardware I/O is performed."""

import dataclasses

import hdl21 as h
import pytest
from hdl21.prefix import m

from flow.scans.params import (
    AdcTbParams,
    _build_variants,
    validate_params,
)


def test_default_params_are_valid_and_immutable() -> None:
    params = AdcTbParams()

    validate_params(params)
    assert isinstance(params.vin_p, h.Vdc.Params)
    assert params.board_id is None
    with pytest.raises(dataclasses.FrozenInstanceError):
        params.conversions = 1


def test_analog_input_preserves_hdl21_source_type() -> None:
    inputs = (
        h.Vdc.Params(dc=615 * m),
        h.Vsin.Params(voff=615 * m, vamp=100 * m, freq=1e6),
        h.Vpwl.Params(wave="0 100m 1m 1100m"),
    )

    params = [AdcTbParams(vin_p=source) for source in inputs]

    assert [type(item.vin_p) for item in params] == [type(source) for source in inputs]


def test_build_variants_covers_all_adcs_and_rates() -> None:
    variants = _build_variants()

    assert len(variants) == 16 * 10
    assert {item.observed_adc for item in variants} == set(range(16))
    assert {float(item.symbol_rate) for item in variants} == {rate * 160e6 for rate in range(1, 11)}
    assert all(item.board_id == "frida65a_001" for item in variants)
    assert all(
        item.active_adc_mask == tuple(int(index == item.observed_adc) for index in reversed(range(16)))
        for item in variants
    )


def test_validation_rejects_invalid_configuration_relationships() -> None:
    incomplete_measurement = AdcTbParams(board_id="frida65a_001")
    invalid_bus = AdcTbParams(dac_astate_p=(0,) * 15 + (2,))
    unequal_patterns = AdcTbParams(seq_logic_pattern="01")

    with pytest.raises(ValueError, match="must be set together"):
        validate_params(incomplete_measurement)
    with pytest.raises(ValueError, match="zero or one"):
        validate_params(invalid_bus)
    with pytest.raises(ValueError, match="equal length"):
        validate_params(unequal_patterns)
