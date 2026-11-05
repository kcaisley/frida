"""The sampling switch's physics in the behavioral ADC (``Model.sample``, ``Model.resistance``,
``Model.conductances``), on given parameters: no characterization, no PDK."""

import numpy as np
import pytest

from .model import Model
from .params import Params, SwitchType


def test_sampler_resistance_peaks_at_mid_supply_and_delays_the_track() -> None:
    switch = Model.Behavioral(n_conductance_s_per_v=10e-3, p_conductance_s_per_v=10e-3)
    resistance = Model.resistance(Params(), switch, np.asarray([0.1, 0.6, 1.1]), 1.2)
    assert resistance[1] > resistance[0] and resistance[1] > resistance[2]
    held = Model.sample(
        Params(),
        switch,
        {"p": np.asarray([0.6]), "n": np.asarray([0.6])},
        {"p": np.asarray([1e6]), "n": np.asarray([0.0])},
        load_f={"p": 1e-12, "n": 1e-12},
        gate_v=1.2,
        rng=np.random.default_rng(0),
    )
    # A 1 V/us slope lags by R * C = resistance[1] * 1 pF.
    assert held["p"][0] == pytest.approx(0.6 - 1e6 * resistance[1] * 1e-12)
    assert held["n"][0] == pytest.approx(0.6)


def test_sampler_jitter_shifts_both_sides_by_one_common_time() -> None:
    held = Model.sample(
        Params(),
        Model.Behavioral(n_conductance_s_per_v=0.0, p_conductance_s_per_v=0.0, jitter_s=1e-9),
        {"p": np.full(20000, 0.6), "n": np.full(20000, 0.6)},
        {"p": np.full(20000, 1e6), "n": np.full(20000, -1e6)},
        load_f={"p": 1e-12, "n": 1e-12},
        gate_v=1.2,
        rng=np.random.default_rng(0),
    )
    # 1 V/us times 1 ns RMS: 1 mV per side, perfectly anticorrelated across sides.
    assert np.std(held["p"]) == pytest.approx(1e-3, rel=0.03)
    np.testing.assert_allclose(held["p"] - 0.6, -(held["n"] - 0.6))


def test_sampler_conductances_follow_the_hdl21_switch_sizing() -> None:
    switch = Model.Behavioral()
    # 32 unit widths over one minimum length: W/L of 64 (a unit width is twice the minimum length)
    assert Model.conductances(Params(), switch) == pytest.approx((300e-6 * 64, 100e-6 * 64))
    assert Model.conductances(Params(switch_type=SwitchType.NMOS, mos_l=2), switch) == pytest.approx((300e-6 * 32, 0.0))
