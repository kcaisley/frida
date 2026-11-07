"""The ADC's behavioral model (``Model``): a converter's record as the stand-in a higher level
simulates, its ENOB and supply power over the rate (the behavioral converter it measures is
``flow.adc.sim``'s, ``flow/adc/test_sim.py``)."""

import math

import pytest

from flow import capdac
from flow.adc import model as adc_model
from flow.adc.model import Model
from flow.adc.params import Params


def test_the_model_reads_its_records_enob_and_power_over_the_rate(monkeypatch: pytest.MonkeyPatch) -> None:
    """``Model.of`` looks the converter's record up by its parameters and reads its figures
    ``enob_rate`` and ``power_rate``, a rate whose ENOB is null (the output no longer follows) left
    out; between the rates it interpolates the ENOB on a log rate, the power on log scales."""
    params = Params(adc_bits=12, cdac=capdac.Params())
    record = {
        "id": "tsmc65__0",
        "block": "adc",
        "details": [
            {"name": "enob_rate", "x": [1e6, 10e6, 100e6, 1e9], "series": {"ENOB": [11.0, 10.0, 8.0, None]}},
            {"name": "power_rate", "x": [1e6, 10e6, 100e6, 1e9], "series": {"Total": [1e-5, 1e-4, 1e-3, 1e-2]}},
        ],
    }
    asked = []

    def characterized(block, pdk, found, *, simulate=True):
        asked.append((block, pdk, found, simulate))
        return record

    monkeypatch.setattr(adc_model, "characterized", characterized)
    model = Model.of("tsmc65", params, simulate=False)
    assert asked == [("adc", "tsmc65", params, False)]
    assert model.rate_hz == (1e6, 10e6, 100e6)
    assert model.enob_bits(10e6) == 10.0
    assert model.enob_bits(math.sqrt(10e6 * 100e6)) == pytest.approx(9.0)
    assert model.power_w(math.sqrt(1e6 * 10e6)) == pytest.approx(math.sqrt(1e-5 * 1e-4))
    # the ends beyond the rates it ran
    assert model.enob_bits(1e3) == 11.0 and model.power_w(1e9) == pytest.approx(1e-3)
