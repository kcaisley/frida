"""The chain's design space (``flow.delay.runs``): its named chains and each at its sizes, and the
runs that characterize one."""

import pytest

from flow import pipeline

from . import runs
from .params import Control, Params, Stage


def test_the_named_chains() -> None:
    named = {name: single() for name, single in pipeline.singles(runs).items()}
    assert list(named) == [
        "ring5",
        "ring5_starved",
        "ring4_coupled",
        "ring4_tail",
        "chain4",
        "chain2_coupled",
        "chain4_starved",
    ]
    assert named["ring5"] == Params(stages=5, ring=True)
    assert named["ring4_tail"] == Params(
        stages=4, ring=True, differential=True, stage=Stage.COUPLED, control=Control.TAIL
    )
    assert named["chain4"] == Params(stages=4)


def test_each_chain_at_every_size_it_has_devices_for() -> None:
    designs = dict(runs.sizes.instances("tsmc65"))
    # five sizes each, a sixth for a coupled stage's coupling inverters and for a control's devices
    assert len(designs) == 7 * 5 + 3 + 3
    assert {label for label in designs if "coupling" in label} == {
        f"sizes({name}_coupling)" for name in ("ring4_coupled", "ring4_tail", "chain2_coupled")
    }
    assert {label for label in designs if label.endswith("_control)")} == {
        f"sizes({name}_control)" for name in ("ring5_starved", "ring4_tail", "chain4_starved")
    }
    for name, single in pipeline.singles(runs).items():
        assert designs[f"sizes({name}_nominal)"] == single()
    half, quadruple, long = (designs[f"sizes(ring4_tail_{size})"] for size in ("half", "quadruple", "long"))
    assert (half.inv_n_w, half.inv_p_w, half.fb_n_w, half.tail_w, half.en_w) == (2, 4, 1, 8, 1)
    assert (quadruple.inv_n_w, quadruple.tail_w, quadruple.inv_l) == (16, 64, 1)
    assert (long.inv_l, long.inv_n_w) == (2, 4)
    assert designs["sizes(ring4_tail_coupling)"].fb_p_w == 8 and designs["sizes(ring4_tail_control)"].tail_w == 32


def test_the_runs_of_a_chain() -> None:
    pytest.importorskip("pdk.tsmc65.hdl21")  # the PDK's supply: a PDK-free checkout (CI) has none
    plain = runs.testbenches("tsmc65", runs.chain4())
    assert list(plain) == ["supply_90", "supply_100", "supply_110"]
    assert [tb.vdd for tb in plain.values()] == pytest.approx([1.08, 1.2, 1.32])
    # the control stays at 8/12 of the PDK's supply over the supply sweep
    assert {tb.vcont_v for tb in plain.values()} == {0.8}
    controlled = runs.testbenches("tsmc65", runs.ring5_starved())
    assert list(controlled)[3:] == [f"control_{twelfths}" for twelfths in (5, 6, 7, 9, 10, 11, 12)]
    assert [controlled[f"control_{twelfths}"].vcont_v for twelfths in (5, 12)] == pytest.approx([0.5, 1.2])
    assert all(tb.vdd == 1.2 for name, tb in controlled.items() if name.startswith("control_"))
