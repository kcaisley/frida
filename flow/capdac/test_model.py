"""The capacitive DAC's model on given parameters, no characterization and no PDK: its design's stage
weights and plates (``Model.weights``, ``Model.plates``), a Pelgrom draw of them (``Model.draw``),
a side's switching in the behavioral ADC (``Model.switch``, ``Model.switch_stage``), and the DAC it
gives that ADC (``Model.behavioral``) from a record (``Model.of``, on a stand-in) or from the design
alone (``Model.design``)."""

import math

import numpy as np
import pytest
from scipy.constants import Boltzmann

from . import model as capdac_model
from .model import Model
from .params import Params, Redundancy, TbParams, WeightImpl
from .sweep import frida1


@pytest.mark.parametrize(
    ("params", "weights"),
    [
        # FRIDA-1's fabricated array (the board's radix17): its named instance, the defaults
        (frida1(), (768, 512, 320, 192, 96, 64, 32, 24, 12, 10, 5, 4, 4, 2, 1, 1)),
        (Params(bits=10, redundancy=Redundancy.BINARY, extra=0), (256, 128, 64, 32, 16, 8, 4, 2, 1)),
        # the two heaviest binary weights split in halves; the two lightest of at least 2
        (Params(bits=10, redundancy=Redundancy.MSB_SPLIT, extra=2), (128, 128, 64, 64, 64, 32, 16, 8, 4, 2, 1)),
        (Params(bits=10, redundancy=Redundancy.LSB_SPLIT, extra=2), (256, 128, 64, 32, 16, 8, 2, 2, 1, 1, 1)),
        (Params(bits=10, redundancy=Redundancy.MSB_REDIST, extra=2), (224, 128, 72, 40, 20, 12, 6, 4, 3, 1, 1)),
    ],
)
def test_the_stage_weights_are_the_known_arrays(params: Params, weights: tuple[int, ...]) -> None:
    assert Model.weights(params) == weights
    assert sum(weights) == 2 ** (params.bits - 1) - 1


def test_an_array_of_its_own_weights_keeps_them() -> None:
    """The board's radix20 flavor: FRIDA-1's array with weights of its own, more than the binary
    total."""
    radix20 = (768, 512, 320, 192, 128, 64, 64, 64, 64, 64, 32, 16, 8, 4, 2, 1)
    assert Model.weights(Params(weights=radix20)) == radix20
    assert frida1() == Params()


@pytest.mark.parametrize("weight_impl", list(WeightImpl))
@pytest.mark.parametrize(
    "params",
    [Params(), Params(bits=10, redundancy=Redundancy.BINARY, extra=0, scale=1), Params(bits=14, extra=6, scale=1)],
)
def test_the_plates_main_less_difference_are_the_weights(params: Params, weight_impl: WeightImpl) -> None:
    """Each stage's main less difference plates is its weight's share of the side's switched
    capacitance: scale times 24 kT / LSB^2 at a full scale of the reference (26 fF at 10 bits and
    1 V, one minimum). Their sum, the top plate's load that sets the full scale, is a strip's whole
    coarse weight for each of the stage's pieces, a unit capacitor's its own weight. Unit
    capacitors have no difference plates. A run's plates are these at its supply."""
    params = Params(**{**params.__dict__, "weight_impl": weight_impl})
    main_f, diff_f = Model.plates(params, 1.2)
    weights = np.asarray(Model.weights(params), dtype=np.float64)
    switched_f = params.scale * 24 * Boltzmann * 300.0 / (2 * 1.2 / 2**params.bits) ** 2
    np.testing.assert_allclose(main_f - diff_f, switched_f * weights / weights.sum(), rtol=1e-12)
    pieces = np.ceil(weights / params.coarse_weight)
    whole = pieces * params.coarse_weight if weight_impl is WeightImpl.DIFFERENCE_CAPS else weights
    np.testing.assert_allclose(main_f + diff_f, switched_f * whole / weights.sum(), rtol=1e-12)
    assert np.all(diff_f >= 0) and np.all(main_f > diff_f)
    if weight_impl is WeightImpl.UNIT_CAPS:
        assert not diff_f.any()
    tb = TbParams(params=params, vdd=1.2, window_s=4e-9, waveform_sample_interval_s=2e-12)
    np.testing.assert_array_equal(main_f, tb.main_f)
    np.testing.assert_array_equal(diff_f, tb.diff_f)
    one = Model.plates(Params(bits=10, redundancy=Redundancy.BINARY, extra=0, scale=1), 1.0)
    assert float((one[0] - one[1]).sum()) == pytest.approx(26.06e-15, rel=1e-3)


def test_frida1s_design_switches_78_percent_of_its_top_plate() -> None:
    """FRIDA-1's array as designed at 1.2 V: its switched plates, main less difference, 78.0 % of
    every plate on the top plate (its full scale over the reference), 742 fF a side."""
    main_f, diff_f = Model.plates(frida1(), 1.2)
    assert float((main_f - diff_f).sum() / (main_f + diff_f).sum()) == pytest.approx(0.78011, abs=1e-5)
    assert float((main_f + diff_f).sum()) == pytest.approx(742.3e-15, rel=1e-4)


def test_a_draw_follows_pelgroms_area_scaling() -> None:
    draws = Model.draw(np.tile([100e-15, 1e-15, 0.0], (20000, 1)), pelgrom=0.01, rng=np.random.default_rng(0))
    # sigma_C = 1 % * sqrt(C * 1 fF): 0.1 fF for 100 fF and 0.01 fF for 1 fF, about the plate; a
    # capacitor of none stays none
    np.testing.assert_allclose(np.std(draws[:, :2] / 1e-15, axis=0), [0.1, 0.01], rtol=0.03)
    np.testing.assert_allclose(np.mean(draws[:, :2], axis=0), [100e-15, 1e-15], rtol=1e-3)
    assert not draws[:, 2].any()


def test_a_side_switching_steps_its_top_plate_and_draws_its_charge() -> None:
    """Two stages, 4 and 2 fF main plates, 1 fF difference plates each, and 2 fF of parasitic: 10
    fF at the top plate, its bottom plates switched to a 1 V reference. C0 rises, holds, then falls;
    C1 stays low. Each plate at the reference after a switch draws C (dV_bottom - dV_top)."""
    main_f, diff_f = np.asarray([4e-15, 2e-15]), np.asarray([1e-15, 1e-15])
    before, after = np.asarray([[0, 0], [1, 0], [1, 0]]), np.asarray([[1, 0], [1, 0], [0, 0]])
    # difference plates the complement (diffcaps 1, capdac's arrays): C0's main plate rises 1 V and
    # its difference plate falls 1 V, (4 - 1) fF V over 10 fF; C0's main plate draws 4 fF (1 - 0.3)
    # V, C1's difference plate, held at the reference, 1 fF (0 - 0.3) V. Falling, C0's difference
    # plate draws 1 fF (1 + 0.3) V and C1's 1 fF (0 + 0.3) V.
    top, charge, transitions = Model.switch(main_f, diff_f, 2e-15, 1.0, 1, before, after)
    np.testing.assert_allclose(top, [0.3, 0.0, -0.3], atol=1e-15)
    np.testing.assert_allclose(charge, [2.5e-15, 0.0, 1.6e-15], atol=1e-30)
    assert transitions.tolist() == [2, 0, 2]
    # difference plates with the main ones (diffcaps 0): (4 + 1) fF V over 10 fF; rising, C0's two
    # plates draw 4 fF (1 - 0.5) V and 1 fF (1 - 0.5) V; falling, no plate is at the reference
    top, charge, transitions = Model.switch(main_f, diff_f, 2e-15, 1.0, 0, before, after)
    np.testing.assert_allclose(top, [0.5, 0.0, -0.5], atol=1e-15)
    np.testing.assert_allclose(charge, [2.5e-15, 0.0, 0.0], atol=1e-30)
    assert transitions.tolist() == [2, 0, 2]


@pytest.mark.parametrize("diffcaps", [0, 1])
def test_one_stage_switching_alone_is_the_sides_switch(diffcaps: int) -> None:
    """``switch_stage``, one column's work, gives what ``switch`` does where only that stage
    changes."""
    rng = np.random.default_rng(1)
    main_f, diff_f = Model.plates(Params(), 1.2)
    stage = 5
    before = rng.integers(0, 2, (64, len(main_f)))
    after = before.copy()
    after[:, stage] = rng.integers(0, 2, 64)
    whole = Model.switch(main_f, diff_f, 0.5e-12, 1.2, diffcaps, before, after)
    at_vref_f = after @ main_f + (after ^ diffcaps) @ diff_f
    alone = Model.switch_stage(
        main_f, diff_f, 0.5e-12, 1.2, diffcaps, stage, before[:, stage], after[:, stage], at_vref_f
    )
    for one, other in zip(alone, whole, strict=True):
        np.testing.assert_allclose(one, other, rtol=1e-10, atol=1e-28)
    assert np.any(alone[0] != 0)


def test_the_behavioral_defaults_are_ideal() -> None:
    """No plates of its own (the design's), no parasitic, every step whole at once, drivers that
    draw nothing, an ideal reference."""
    dac = Model.Behavioral()
    assert (dac.main_p_f, dac.diff_p_f, dac.main_n_f, dac.diff_n_f) == (None,) * 4
    assert dac.stage_tau_s is None and dac.stage_delay_s is None
    assert (dac.parasitic_f, dac.settling_tau_s, dac.driver_energy_j, dac.driver_static_w) == (0.0,) * 4
    assert (dac.reference_r_ohm, dac.reference_c_f, dac.reference_noise_v) == (0.0,) * 3


def test_a_record_gives_the_drawn_gain_area_and_settling(monkeypatch: pytest.MonkeyPatch) -> None:
    """``Model.of`` on a stand-in record in a PDK of a 0.9 V supply: its plates are the design's at
    that supply, at which the netlist draws them and the characterization runs; the gain is those
    plates over the drawn top plate's whole load, so the rest of it is the parasitic; a Monte Carlo
    draw's plates replace the design's, the parasitic stays."""
    params = Params(bits=10, redundancy=Redundancy.BINARY, extra=0)
    stages = len(Model.weights(params))
    record = {
        "block": "capdac",
        "metrics": {"lsb_v": 1.5e-3, "gain": 0.8, "layout_area_um2": 1234.0},
        "details": [
            {"name": "settling_stage", "series": {"settling": [300e-12] * stages}},
            {"name": "model_stage", "series": {"delay": [50e-12] * stages, "time constant": [40e-12] * stages}},
        ],
    }
    monkeypatch.setattr(capdac_model, "characterized", lambda block, pdk, params, simulate=True: record)
    monkeypatch.setattr(capdac_model, "_supply_v", lambda pdk: 0.9)
    model = Model.of("tsmc65", params)
    assert (model.gain, model.area_um2, model.lsb_v, model.reference_v) == (0.8, 1234.0, 1.5e-3, 0.9)
    dac = model.behavioral()
    main_f, diff_f = Model.plates(params, 0.9)
    plates_f = float(main_f.sum() + diff_f.sum())
    assert plates_f / (plates_f + dac.parasitic_f) == pytest.approx(0.8, rel=1e-12)
    assert dac.main_p_f == dac.main_n_f == tuple(main_f) and dac.diff_n_f == tuple(diff_f)
    assert dac.stage_delay_s == (50e-12,) * stages and dac.stage_tau_s == (40e-12,) * stages
    assert dac.settling_tau_s == 40e-12 and dac.driver_energy_j == 0.0
    # a draw of the drawn plates keeps the drawn gain
    drawn = model.behavioral(((1.01 * main_f, diff_f), (main_f, 0.99 * diff_f)))
    assert drawn.main_p_f == tuple(1.01 * main_f) and drawn.diff_n_f == tuple(0.99 * diff_f)
    assert drawn.parasitic_f == dac.parasitic_f
    # a record the layout step has not reached has no area
    del record["metrics"]["layout_area_um2"]
    assert math.isnan(Model.of("tsmc65", params).area_um2)


def test_a_design_without_a_record_settles_as_its_drivers_are_sized() -> None:
    """``Model.design``: no parasitic, no layout, no driver delay, and each stage within half an LSB
    in settle_ps over settle_margin (400 ps): ln(2^11 w / 511) time constants at 10 bits, about 6.9
    for the MSB; its LSB the design's at the reference (2 V / 1024 of unit capacitors, which have no
    difference plates)."""
    params = Params(bits=10, redundancy=Redundancy.BINARY, extra=0, settle_ps=800.0)
    model = Model.design("tsmc65", params, reference_v=1.0)
    weights = np.asarray(Model.weights(params), dtype=np.float64)
    assert model.gain == 1.0 and math.isnan(model.area_um2) and model.delay_s == (0.0,) * len(weights)
    assert model.reference_v == 1.0
    np.testing.assert_allclose(model.settling_s, 400e-12, rtol=1e-12)
    np.testing.assert_allclose(np.asarray(model.tau_s) * np.log(2**11 * weights / 511), 400e-12, rtol=1e-12)
    assert model.tau_s[0] == pytest.approx(400e-12 / math.log(2**11 * 256 / 511))
    main_f, diff_f = Model.plates(params, 1.0)
    assert model.lsb_v == pytest.approx(2 * float((main_f - diff_f).sum() / (main_f + diff_f).sum()) / 2**10)
    unit = Params(bits=10, redundancy=Redundancy.BINARY, extra=0, weight_impl=WeightImpl.UNIT_CAPS)
    assert Model.design("tsmc65", unit, reference_v=1.0).lsb_v == pytest.approx(2 / 1024)
    # its plates designed at its own reference
    dac = model.behavioral()
    assert dac.parasitic_f == 0.0 and dac.main_p_f == dac.main_n_f == tuple(main_f)
    assert dac.stage_tau_s == model.tau_s and dac.settling_tau_s == model.tau_s[-1]
    assert dac.stage_delay_s == (0.0,) * len(weights)
