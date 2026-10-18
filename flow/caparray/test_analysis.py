"""Capacitor-array analyses and plots on the top plate of a known 3-bit array."""

import json
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pytest

from flow.analysis.types import MeasInfo, Wave
from flow.caparray.analysis import MeasCapArrayTran, analyze_caparray_transfer, analyze_caparray_weights
from flow.caparray.plots import plot_caparray_error, plot_caparray_transfer, plot_caparray_weights
from flow.caparray.sim import CapArrayConfig, CapArrayTbParams

CDAC = CapArrayConfig(n_dac=3, n_extra=0, weights=(4, 2, 1))


def _top_plate(codes, *, levels) -> MeasCapArrayTran:
    """Hold each code's top-plate level for its 1 ns dwell, 0.1 ns transitions between."""

    params = CapArrayTbParams(cdac=CDAC, codes=None if codes is None else tuple(codes), code_dwell_s=1e-9)
    step_s = 1.1e-9
    time_s = np.arange(0.0, len(levels) * step_s, 10e-12)
    top = np.asarray(levels)[np.minimum((time_s // step_s).astype(int), len(levels) - 1)]
    return MeasCapArrayTran(
        group=None,
        index=None,
        dut=CDAC,
        info=MeasInfo(
            backend="spice",
            timestamp_utc=datetime(2026, 10, 18, tzinfo=UTC),
            readbacks={"stage_weights_json": json.dumps([4, 2, 1])},
        ),
        param=params,
        trial_index=np.arange(1),
        wave=Wave(record_index=np.arange(1), time_s=time_s, v={"cap_topplate": top[None]}, i={}),
    )


def test_stage_weights_scale_to_the_design() -> None:
    # 1.2 V into 7 unit weights plus 1 unit of load: each stage moves the top plate by w / 8 of it,
    # the C2 stage 2 % high
    steps = np.asarray([4, 2, 1.02]) / 8 * 1.2
    levels = [value for step in steps for value in (0.0, step)]
    weights = analyze_caparray_weights(_top_plate((0, 4, 0, 2, 0, 1), levels=levels))
    np.testing.assert_allclose(weights.fraction, steps / 1.2)
    assert weights.total_fraction == pytest.approx(7.02 / 8)
    np.testing.assert_allclose(weights.design_weight, [4, 2, 1])
    assert weights.weight_error[2] == pytest.approx(1.02 * 7 / 7.02 - 1)


def test_transfer_compares_the_ramp_with_the_design_weights() -> None:
    # 2 mV per unit capacitor, code 5 (stages C0 and C2, weights 4 + 1) half a unit high
    levels = np.arange(8) * 2e-3
    levels[5] += 1e-3
    transfer = analyze_caparray_transfer(_top_plate(None, levels=levels))
    np.testing.assert_array_equal(transfer.design_weight, np.arange(8))
    assert transfer.volts_per_unit == pytest.approx(2e-3, rel=0.02)
    assert transfer.error_units.argmax() == 5


def test_every_plot_renders(tmp_path: Path) -> None:
    weights = analyze_caparray_weights(_top_plate((0, 4, 0, 2, 0, 1), levels=[0, 0.6, 0, 0.3, 0, 0.15]))
    transfer = analyze_caparray_transfer(_top_plate(None, levels=np.arange(8) * 0.1))
    paths = (
        *plot_caparray_weights([weights, weights], labels=["a", "b"], output_path=tmp_path / "weights"),
        *plot_caparray_transfer([transfer], labels=["a"], output_path=tmp_path / "transfer"),
        *plot_caparray_error([transfer], labels=["a"], output_path=tmp_path / "error"),
    )
    assert paths and all(path.exists() for path in paths)
