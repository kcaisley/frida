"""The CDAC model from its characterization record, and its Monte Carlo draw at a percentile."""

from typing import Any

import numpy as np

from . import model as cdac_model
from .test_subckt import PARAMS


def _record(stages: int) -> dict[str, Any]:
    return {
        "metrics": {"lsb_v": 1e-3},
        "details": [
            {"name": "settling_stage", "series": {"settling": [1e-9 * (stages - k) for k in range(stages)]}},
            {
                "name": "model_stage",
                "series": {"delay": [50e-12] * stages, "time constant": [1e-10 * (k + 1) for k in range(stages)]},
            },
        ],
    }


def test_the_model_reads_its_record_by_its_parameters(monkeypatch):
    asked = {}

    def characterized(block, pdk, params, simulate):
        asked.update(block=block, pdk=pdk, params=params, simulate=simulate)
        return _record(3)

    monkeypatch.setattr(cdac_model, "characterized", characterized)
    model = cdac_model.Model.of("tsmc65", PARAMS, simulate=False)
    assert asked == {"block": "cdac", "pdk": "tsmc65", "params": PARAMS, "simulate": False}
    assert model.tau_s == (1e-10, 2e-10, 3e-10) and model.delay_s == (50e-12,) * 3 and model.lsb_v == 1e-3
    assert model.settling_s == tuple(1e-9 * (3 - k) for k in range(3))


def test_a_converter_calibrates_on_the_monte_carlo_draw_at_its_percentile(monkeypatch):
    """``Model.drawn``: of a characterization's Monte Carlo run, the draw at a percentile of what no
    calibration recovers (the converter's INL breaking ties), both sides' plates."""
    import pytest

    from .test_analysis import BINARY, _draws

    nominal = np.asarray(BINARY.dac.main_f)
    # three runs: the MSB 0 %, 30 % and 15 % heavy, so what no calibration recovers ranks them 0, 2, 1
    main = np.vstack([nominal * np.r_[1 + heavy, 1.0, 1.0] for heavy in (0.0, 0.3, 0.15)])
    monkeypatch.setattr(cdac_model, "characterized", lambda *args, **kwargs: {"waves": {"mc_a5_g50": "mc.h5"}})
    monkeypatch.setattr(cdac_model, "read_measurement", lambda path: _draws(main, main))
    (main_p, diff_p), (main_n, _diff_n) = cdac_model.Model.drawn("tsmc65", BINARY, "mc_a5_g50", 100.0)
    assert np.allclose(main_p, main[1]) and np.allclose(main_n, main[1]) and not diff_p.any()
    (main_p, _), _ = cdac_model.Model.drawn("tsmc65", BINARY, "mc_a5_g50", 50.0)
    assert np.allclose(main_p, main[2])
    with pytest.raises(LookupError):
        cdac_model.Model.drawn("tsmc65", BINARY, "mc_a10_g100", 50.0)
