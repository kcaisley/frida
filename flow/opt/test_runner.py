"""The optimizer's pieces that need no simulator: a trial's design, and a record's score."""

import math

import optuna
import pytest
from hdl21.primitives import MosType

from flow import comp, pipeline
from flow.opt import runner

PROBLEM = pipeline.Problem(
    cost={"energy_0p5mv_j": 1.0, "layout_area_um2": 1.0, "noise_v": (6.0, 100e-6)},
    bound={"noise_v": 100e-6, "layout_area_um2": 400.0, "decides_in_time": True},
    fixed={"input_pair": MosType.NMOS},
)


def _trial(**chosen) -> optuna.trial.FixedTrial:
    """A trial that answers every searched knob: ``chosen``, else each number's lower bound."""
    values = {
        name: dist.low if hasattr(dist, "low") else dist.choices[0]
        for name, dist in runner.distributions(comp.Params, "tsmc65", PROBLEM).items()
    }
    return optuna.trial.FixedTrial({**values, **chosen})


def test_a_trial_proposes_a_design_of_the_problem() -> None:
    """Its choices, then the numbers its choices use (a switched tail asks for no capacitors), the
    problem's fixed parameters held."""
    switched = runner.suggest(
        _trial(latch="DOUBLE_TAIL", bias="SWITCHED", diffpair_w=64), comp.Params, "tsmc65", PROBLEM
    )
    assert switched.latch == comp.Latch.DOUBLE_TAIL and switched.diffpair_w == 64
    assert switched.input_pair == MosType.NMOS and switched.preamp_c_ff == comp.Params().preamp_c_ff
    dynamic = runner.suggest(_trial(bias="DYNAMIC", preamp_c_ff=120, bias_c_ff=400), comp.Params, "tsmc65", PROBLEM)
    assert dynamic.bias == comp.Bias.DYNAMIC and (dynamic.preamp_c_ff, dynamic.bias_c_ff) == (120, 400)
    assert "input_pair" not in runner.distributions(comp.Params, "tsmc65", PROBLEM)


def test_a_record_scores_by_the_problems_costs_and_bounds() -> None:
    better = runner.betters("comp")
    metrics = {"energy_0p5mv_j": 1e-13, "layout_area_um2": 300.0, "noise_v": 80e-6, "decides_in_time": True}
    value, violations = runner.score(PROBLEM, {"valid": True, "metrics": metrics}, better)
    assert value == pytest.approx(math.log(1e-13) + math.log(300.0) + 6.0 * math.log1p(0.64))
    assert all(v <= 0 for v in violations.values())
    # not measured (the screen stopped first): no term, no violation; measured but not a number: violated
    _, screened = runner.score(PROBLEM, {"valid": True, "metrics": {**metrics, "noise_v": None}}, better)
    assert screened["noise_v"] == 0.0
    _, unresolved = runner.score(PROBLEM, {"valid": True, "metrics": {**metrics, "noise_v": math.nan}}, better)
    assert unresolved["noise_v"] == 1.0
    _, late = runner.score(PROBLEM, {"valid": True, "metrics": {**metrics, "decides_in_time": False}}, better)
    assert late["decides_in_time"] == 1.0 and late["layout_area_um2"] == pytest.approx(math.log(300 / 400))
    # an area without a floorplan stays unmeasurable through the record's JSON (NaN written as null)
    stored = {"valid": True, "metrics": {**metrics, "layout_area_um2": None}, "unmeasurable": ["layout_area_um2"]}
    assert runner.unmeasurable({**metrics, "layout_area_um2": math.nan}) == ["layout_area_um2"]
    assert runner.score(PROBLEM, stored, better)[1]["layout_area_um2"] == 1.0
    # a design the block does not admit: every bound violated, without metrics
    assert runner.score(PROBLEM, {"valid": False, "metrics": {}}, better) == (0.0, dict.fromkeys(PROBLEM.bound, 1.0))
