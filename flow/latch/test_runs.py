"""The runs that characterize each design (``testbenches``), by name, in a PDK (its supply)."""

import pytest

from . import runs
from .params import DATA_OFFSET_SWEEP_S, PERIOD_SWEEP_S, SUPPLY_SWEEP, UPSET_CHARGES_C, Bench
from .test_analysis import approx


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
        "flop_rst": {"supply": supply, "offset": offset, "period": period, "slow": 1},
        "div2": {"supply": supply, "period": period, "slow": 1},
        "flop_tspc": {"supply": supply, "offset": offset, "period": period, "slow": 1},
        "div2_tspc": {"supply": supply, "period": period, "slow": 1},
        "latch_dice": {"supply": supply, "offset": offset, "upset": upset},
        "sr_nand": {"supply": supply},
        "sr_nor": {"supply": supply},
    }
    for name, kinds in expected.items():
        assert _kinds(runs.testbenches("tsmc65", getattr(runs, name)())) == kinds, name


def test_the_runs_stay_within_the_supply_and_change_only_the_period_along_it() -> None:
    pytest.importorskip("pdk.tsmc65.hdl21")
    benches = runs.testbenches("tsmc65", runs.flop_rst())
    nominal = benches["supply_100"].vdd
    assert [benches[f"supply_{percent}"].vdd for percent in (90, 110)] == approx([0.9 * nominal, 1.1 * nominal])
    assert max(tb.vdd for tb in benches.values()) <= 1.1 * nominal + 1e-9
    # along the period sweep one edge for every period, an eighth of the shortest, and the data half
    # a period ahead of each capturing edge
    for period in PERIOD_SWEEP_S:
        run = benches[f"period_{round(period * 1e12)}ps"]
        assert (run.transition_time_s, run.data_offset_s) == approx((min(PERIOD_SWEEP_S) / 8, period / 2))
    # rst falls with a falling clock edge: a whole number of periods, at least two and 0.5 ns
    for period in PERIOD_SWEEP_S:
        run = benches[f"period_{round(period * 1e12)}ps"]
        cycles = run.reset_time_s / period
        assert cycles == approx(round(cycles)) and round(cycles) >= 2 and run.reset_time_s >= 0.5e-9 - 1e-18
        assert run.cycles == 12
    slow = benches["slow_1mhz"]
    assert (slow.clock_period_s, slow.data_offset_s, slow.waveform_sample_interval_s) == (1e-6, 0.5e-6, 100e-12)
    assert benches["offset_-100ps"].data_offset_s == approx(-100e-12)
    struck = runs.testbenches("tsmc65", runs.latch_dice())["upset_7p4fc"]
    assert struck.bench is Bench.UPSET and struck.charge_c == approx(7.4e-15)
