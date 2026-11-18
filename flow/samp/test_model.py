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


def _hold(switch: Model.Behavioral, vin: list[float], slope: float = 0.0) -> dict[str, np.ndarray]:
    values = np.asarray(vin)
    return Model.sample(
        Params(),
        switch,
        {"p": values, "n": values},
        {"p": np.full(len(values), slope), "n": np.full(len(values), slope)},
        load_f={"p": 1e-12, "n": 1e-12},
        gate_v=1.2,
        rng=np.random.default_rng(0),
    )


def test_a_short_track_window_leaves_the_previous_samples_residue() -> None:
    """[Razavi-ADC] Eq. (3.81), p. 54: 1 kohm into 1 pF tracking 2 ns leaves exp(-2) of the step
    from the previous held value: 0.2 V then 0.7 V hold 0.2 V and 0.7 - 0.5 exp(-2)."""
    switch = Model.Behavioral(ron_table_v=(0.0, 1.2), ron_table_ohm=(1e3, 1e3), track_s=2e-9)
    held = _hold(switch, [0.2, 0.7])
    np.testing.assert_allclose(held["p"], [0.2, 0.7 - 0.5 * np.exp(-2.0)], rtol=1e-12)


def test_an_open_level_holds_the_previous_sample() -> None:
    """A level the characterization never settled at (inf) conducts nothing: the sample before it
    is held through it."""
    switch = Model.Behavioral(ron_table_v=(0.0, 0.6, 1.2), ron_table_ohm=(100.0, 100.0, np.inf))
    held = _hold(switch, [0.3, 1.2, 0.3])
    np.testing.assert_allclose(held["p"], [0.3, 0.3, 0.3])


def test_an_input_outside_the_characterized_levels_is_refused() -> None:
    switch = Model.Behavioral(ron_table_v=(0.1, 1.1), ron_table_ohm=(100.0, 100.0))
    with pytest.raises(ValueError, match="outside its characterized levels"):
        Model.resistance(Params(), switch, np.asarray([1.15]), 1.2)


def test_the_pedestal_and_the_aperture_move_the_held_value() -> None:
    """A pedestal of -1 mV at 0 V and +1 mV at 1.2 V adds 0 at 0.6 V; an aperture of 10 ps plus
    20 ps/V holds a 1 V/us input 22 ps later at 0.6 V: 22 uV higher (an ideal switch, no lag)."""
    switch = Model.Behavioral(
        n_conductance_s_per_v=0.0,
        p_conductance_s_per_v=0.0,
        pedestal_table_vin_v=(0.0, 1.2),
        pedestal_table_v=(-1e-3, 1e-3),
        aperture_s=10e-12,
        aperture_s_per_v=20e-12,
    )
    held = _hold(switch, [0.6, 0.0], slope=1e6)
    np.testing.assert_allclose(held["p"], [0.6 + 22e-12 * 1e6, -1e-3 + 10e-12 * 1e6], rtol=1e-9)
