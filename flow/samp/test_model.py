"""The sampling switch's physics in the behavioral ADC (``Model.sample``, ``Model.resistance``,
``Model.conductances``), on given parameters: no characterization, no PDK."""

import numpy as np
import pytest

from .model import Model
from .params import LOAD_F, Params, SwitchType


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


def test_the_pedestal_is_a_charge_on_the_load_it_is_held_on() -> None:
    """[Razavi-Analog] Eq. (13.26), p. 550: the pedestal goes as 1 / C_H. A curve of -2 mV measured
    into 1 pF is -2 fC: -4 mV on 0.5 pF and -1 mV on 2 pF; without the load it was measured into,
    the curve as it is."""
    table = {"pedestal_table_vin_v": (0.0, 1.2), "pedestal_table_v": (-2e-3, -2e-3)}
    ideal = {"n_conductance_s_per_v": 0.0, "p_conductance_s_per_v": 0.0}
    values = {"p": np.asarray([0.6]), "n": np.asarray([0.6])}
    still = {"p": np.zeros(1), "n": np.zeros(1)}
    loads = {"p": 0.5e-12, "n": 2e-12}
    scaled = Model.sample(
        Params(),
        Model.Behavioral(**ideal, **table, pedestal_load_f=1e-12),
        values,
        still,
        load_f=loads,
        gate_v=1.2,
        rng=np.random.default_rng(0),
    )
    assert scaled["p"][0] - 0.6 == pytest.approx(-4e-3, rel=1e-9)
    assert scaled["n"][0] - 0.6 == pytest.approx(-1e-3, rel=1e-9)
    plain = Model.sample(
        Params(),
        Model.Behavioral(**ideal, **table),
        values,
        still,
        load_f=loads,
        gate_v=1.2,
        rng=np.random.default_rng(0),
    )
    assert plain["p"][0] - 0.6 == pytest.approx(-2e-3, rel=1e-9)
    assert plain["n"][0] - 0.6 == pytest.approx(-2e-3, rel=1e-9)


def test_a_characterized_model_gives_the_pedestal_its_benchs_load() -> None:
    """The record's pedestal is measured into the bench's 1 pF (``params.LOAD_F``): the model's
    parameters say so, whatever load they are asked for."""
    model = Model(
        pdk="tsmc65",
        params=Params(),
        ron_v=(0.1, 1.1),
        ron_ohm=(400.0, 400.0),
        bandwidth_hz=4e8,
        pedestal_vin_v=(0.1, 1.1),
        pedestal_v=(-2e-3, -2e-3),
    )
    assert model.behavioral(load_f=0.7e-12).pedestal_load_f == LOAD_F == 1e-12


def test_a_measured_curve_is_interpolated_in_its_conductance() -> None:
    """[Razavi-ADC] Eq. (3.24), p. 27: a triode device's conductance is linear in its input, so
    between two levels the conductance is interpolated: 100 ohm at 0.2 V and 300 ohm at 1.0 V are
    10 mS and 3.333 mS, 6.667 mS halfway: 150 ohm (not the resistances' mean, 200 ohm). Next to an
    open level the conductance falls to zero: 100 ohm at 0.2 V and open at 1.0 V are 5 mS halfway
    (200 ohm) and 2.5 mS three quarters of the way (400 ohm)."""
    closed = Model.Behavioral(ron_table_v=(0.2, 1.0), ron_table_ohm=(100.0, 300.0))
    np.testing.assert_allclose(
        Model.resistance(Params(), closed, np.asarray([0.2, 0.6, 1.0]), 1.2), [100.0, 150.0, 300.0]
    )
    opening = Model.Behavioral(ron_table_v=(0.2, 1.0), ron_table_ohm=(100.0, np.inf))
    found = Model.resistance(Params(), opening, np.asarray([0.2, 0.6, 0.8, 1.0]), 1.2)
    np.testing.assert_allclose(found[:3], [100.0, 200.0, 400.0])
    assert np.isinf(found[3])
    mirrored = Model.Behavioral(ron_table_v=(0.2, 1.0), ron_table_ohm=(np.inf, 100.0))
    np.testing.assert_allclose(
        Model.resistance(Params(), mirrored, np.asarray([0.4, 0.6, 1.0]), 1.2), [400.0, 200.0, 100.0]
    )
