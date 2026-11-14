"""The runs that characterize each design (``testbenches``), by name, in a PDK (its supply)."""

import pytest

from . import runs
from .params import DATA_OFFSET_SWEEP_S, PERIOD_SWEEP_S, SUPPLY_SWEEP, UPSET_CHARGES_C, Bench


def _kinds(benches: dict) -> dict[str, int]:
    """How many runs of each kind (its name before the first underscore)."""
    kinds: dict[str, int] = {}
    for name in benches:
        kinds[name.split("_")[0]] = kinds.get(name.split("_")[0], 0) + 1
    return kinds


def test_each_design_runs_the_sweeps_it_has() -> None:
    pytest.importorskip("pdk.tsmc65.hdl21")  # a PDK-free checkout (CI) has no supply to run at
    supply, offset, period, upset = (
        len(sweep) for sweep in (SUPPLY_SWEEP, DATA_OFFSET_SWEEP_S, PERIOD_SWEEP_S, UPSET_CHARGES_C)
    )
    expected = {
        "latch": {"supply": supply, "offset": offset, "upset": upset},
        "latch_rst": {"supply": supply, "offset": offset},
        "flop_rst": {"supply": supply, "offset": offset, "period": period},
        "div2": {"supply": supply, "period": period},
        "flop_tspc": {"supply": supply, "offset": offset, "period": period},
        "div2_tspc": {"supply": supply, "period": period},
        "latch_dice": {"supply": supply, "offset": offset, "upset": upset},
        "sr_nand": {"supply": supply},
        "sr_nor": {"supply": supply},
    }
    for name, kinds in expected.items():
        assert _kinds(runs.testbenches("tsmc65", getattr(runs, name)())) == kinds, name


def test_the_runs_stay_within_the_supply_and_scale_a_short_clock() -> None:
    pytest.importorskip("pdk.tsmc65.hdl21")
    benches = runs.testbenches("tsmc65", runs.flop_rst())
    nominal = benches["supply_100"].vdd
    assert [benches[f"supply_{percent}"].vdd for percent in (90, 110)] == pytest.approx([0.9 * nominal, 1.1 * nominal])
    assert max(tb.vdd for tb in benches.values()) <= 1.1 * nominal + 1e-9
    # the edges and the data offset scale with a short clock
    short = benches["period_100ps"]
    assert (short.transition_time_s, short.data_offset_s) == pytest.approx((12.5e-12, 25e-12))
    assert (short.reset_time_s, short.cycles) == (0.5e-9, 12)
    assert benches["offset_-200ps"].data_offset_s == pytest.approx(-200e-12)
    struck = runs.testbenches("tsmc65", runs.latch_dice())["upset_7fc"]
    assert struck.bench is Bench.UPSET and struck.charge_c == pytest.approx(7e-15)
