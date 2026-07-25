"""Software-only tests for typed ADC acquisition data."""

from flow.scans.results import AdcConversion, parameter_digest, read_adc_conversions, write_adc_conversions
from flow.scans.params import AdcTbParams


def test_adc_conversion_csv_round_trip(tmp_path) -> None:
    first = [
        AdcConversion(
            conversion_index=0,
            raw_word=0xA1234567,
            identifier=0xA,
            frame=3,
            spi=0x12345,
            bout="10101010101010101",
            dout_raw=1234,
            dout=2345,
        )
    ]
    second = [
        AdcConversion(
            conversion_index=1,
            raw_word=0xA7654321,
            identifier=0xA,
            frame=4,
            spi=0x14321,
            bout="10100001101000001",
            dout_raw=1235,
            dout=2346,
        )
    ]
    path = tmp_path / "adc.csv"

    assert write_adc_conversions(path, first) == 1
    assert write_adc_conversions(path, second, append=True) == 1
    assert read_adc_conversions(path) == first + second


def test_parameter_digest_is_stable_and_sensitive() -> None:
    params = AdcTbParams()
    assert parameter_digest(params) == parameter_digest(params)
    assert parameter_digest(params) != parameter_digest(AdcTbParams(conversions=params.conversions + 1))
