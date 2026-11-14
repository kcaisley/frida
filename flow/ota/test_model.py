"""The amplifier's behavioral model (``Model``) on a given record: no characterization, no PDK."""

import pytest

from . import model
from .model import Model
from .params import Params


def test_the_model_reads_a_record_and_interpolates_its_gain(monkeypatch: pytest.MonkeyPatch) -> None:
    record = {
        "block": "ota",
        "metrics": {
            "gain_dc_db": 40.0,
            "unity_gain_bandwidth_hz": 1e8,
            "phase_margin_deg": 85.0,
            "noise_in_v": 1e-4,
            "power_w": 5e-5,
        },
        "details": [{"name": "gain", "x": [1e3, 1e6, 1e8], "series": {"gain": [40.0, 40.0, 0.0]}}],
    }
    monkeypatch.setattr(model, "characterized", lambda block, pdk, params, simulate=True: record)
    found = Model.of("tsmc65", Params())
    assert (found.gain_dc_db, found.unity_gain_bandwidth_hz, found.power_w) == (40.0, 1e8, 5e-5)
    # 20 dB a decade between the last two points; held flat past the ends
    assert found.gain(1e7) == pytest.approx(10.0) and found.gain(1.0) == pytest.approx(100.0)
    assert found.gain(1e10) == pytest.approx(1.0)
