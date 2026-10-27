"""The optimizer's pieces that need no simulator: a trial's design, and a record's score."""

import math

import optuna
import pytest
from hdl21.primitives import MosType

from flow import comp, pipeline
from flow.opt import runner


def _space() -> comp.Params:
    """NMOS input pairs, every latch and tail, the pair's width, the dynamic bias's capacitors with it."""
    space = pipeline.widen(comp.Params(input_pair=MosType.NMOS))
    space.latch = pipeline.every(comp.Latch)
    space.bias = pipeline.every(comp.Bias)
    space.diffpair_w = pipeline.steps(2, 8192, log=True)
    space.preamp_c_ff = pipeline.steps(10, 16000, log=True, when=comp.Bias.DYNAMIC)
    space.bias_c_ff = pipeline.steps(10, 64000, log=True, when=comp.Bias.DYNAMIC)
    return space


PROBLEM = pipeline.Problem(
    cost={"energy_0p5mv_j": 1.0, "layout_area_um2": 1.0, "noise_v": (6.0, 100e-6)},
    bound={"noise_v": 100e-6, "layout_area_um2": 400.0, "decides_in_time": True},
    space=_space(),
)


def _trial(**chosen) -> optuna.trial.FixedTrial:
    """A trial that answers every widened parameter: ``chosen``, else each range's low end or the
    first choice."""
    values = {
        name: dist.low if hasattr(dist, "low") else dist.choices[0]
        for name, dist in runner.distributions(PROBLEM).items()
    }
    return optuna.trial.FixedTrial({**values, **chosen})


def test_a_trial_proposes_a_design_of_the_problems_space() -> None:
    """Its choices, then the ranges its choices use (a switched tail asks for no capacitors), every
    other parameter at the space's base."""
    switched = runner.suggest(_trial(latch="DOUBLE_TAIL", bias="SWITCHED", diffpair_w=64), PROBLEM)
    assert switched.latch == comp.Latch.DOUBLE_TAIL and switched.diffpair_w == 64
    assert switched.input_pair == MosType.NMOS and switched.preamp_c_ff == comp.Params().preamp_c_ff
    dynamic = runner.suggest(_trial(bias="DYNAMIC", preamp_c_ff=120, bias_c_ff=400), PROBLEM)
    assert dynamic.bias == comp.Bias.DYNAMIC and (dynamic.preamp_c_ff, dynamic.bias_c_ff) == (120, 400)
    assert "input_pair" not in runner.distributions(PROBLEM)


def test_a_record_scores_by_the_problems_costs_and_bounds() -> None:
    better = runner.betters("comp")
    metrics = {"energy_0p5mv_j": 1e-13, "layout_area_um2": 300.0, "noise_v": 80e-6, "decides_in_time": True}
    value, violations = runner.score(PROBLEM, {"valid": True, "metrics": metrics}, better)
    # the product of the factors, in J um^2: 0.1 pJ x 300 um^2 x (1 + 0.8^2)^6
    assert value == pytest.approx(1e-13 * 300.0 * 1.64**6)
    assert pipeline.cost_unit(PROBLEM) == "j_um2"
    assert all(v <= 0 for v in violations.values())
    # not measured (the screen stopped first): no term, no violation; measured but not a number: violated
    _, screened = runner.score(PROBLEM, {"valid": True, "metrics": {**metrics, "noise_v": None}}, better)
    assert screened["noise_v"] == 0.0
    _, unresolved = runner.score(PROBLEM, {"valid": True, "metrics": {**metrics, "noise_v": math.nan}}, better)
    assert unresolved["noise_v"] == 1.0
    late_value, late = runner.score(PROBLEM, {"valid": True, "metrics": {**metrics, "decides_in_time": False}}, better)
    assert late["decides_in_time"] == 1.0 and late["layout_area_um2"] == pytest.approx(math.log(300 / 400))
    # a comparator that never decides (its delay, noise unmeasured, its energy tiny) never outranks
    # one that meets every bound, for a tool ranking by the objective alone
    broken = {"energy_0p5mv_j": 1e-15, "layout_area_um2": 100.0, "noise_v": None, "decides_in_time": False}
    broken_value, _ = runner.score(PROBLEM, {"valid": True, "metrics": broken}, better)
    assert broken_value == late_value == runner.INFEASIBLE and broken_value > value
    # an area without a floorplan stays unmeasurable through the record's JSON (NaN written as null)
    stored = {"valid": True, "metrics": {**metrics, "layout_area_um2": None}, "unmeasurable": ["layout_area_um2"]}
    assert runner.unmeasurable({**metrics, "layout_area_um2": math.nan}) == ["layout_area_um2"]
    assert runner.score(PROBLEM, stored, better)[1]["layout_area_um2"] == 1.0
    # an area estimated from the gates alone (a best case) breaks its bound by at least 1
    gated = {"valid": True, "metrics": {"layout_area_um2": 401.0}, "estimated": ["layout_area_um2"]}
    assert runner.score(PROBLEM, gated, better)[1]["layout_area_um2"] == pytest.approx(1 + math.log(401 / 400))
    # a design the block does not admit: every bound violated, without metrics
    assert runner.score(PROBLEM, {"valid": False, "metrics": {}}, better) == (
        runner.INFEASIBLE,
        dict.fromkeys(PROBLEM.bound, 1.0),
    )
