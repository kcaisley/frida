"""Checks of the latch's testbench parameters and testbenches without a simulator, and one opt-in
Spectre run of the timing bench on an ideal stand-in for the latch."""

import importlib.util
import math
import shutil
from pathlib import Path
from typing import Any

import hdl21 as h
import hdl21.sim as hs
import numpy as np
import pytest
from hdl21.primitives import C, R, Vcvs, Vdc, Vpulse

from flow.circuit.ports import module_from_ports

from . import runs, sim
from .analysis import analyze_timing, metrics
from .params import SUPPLY_SWEEP, Bench, Params, Style, TbParams
from .subckt import Nets
from .test_analysis import approx


def test_a_run_defaults_to_the_timing_bench_of_the_c2mos_latch() -> None:
    tb = TbParams()
    assert (tb.pdk, tb.params, tb.bench) == ("tsmc65", Params(), Bench.TIMING)
    assert (tb.clock_period_s, tb.data_offset_s, tb.transition_time_s) == (2e-9, 0.5e-9, 50e-12)
    assert (tb.cload_f, tb.cycles, tb.waveform_sample_interval_s) == (2e-15, 8, 1e-12)
    # the reset and nine clock cycles; an SR latch three set and reset periods; a strike twice its time
    assert tb.stop_s == approx(0.5e-9 + 9 * 2e-9)
    assert TbParams(params=runs.sr_nand()).stop_s == approx(3 * 5.2e-9)
    assert TbParams(bench=Bench.UPSET, charge_c=5e-15).stop_s == approx(4e-9)


def test_the_timing_bench_puts_data_an_offset_before_each_capturing_edge() -> None:
    """A flip-flop captures on the rising edge, a latch on the falling one; data crosses mid-supply
    ``data_offset_s`` before it, in the first cycle after the reset."""
    period, transition = 2e-9, 50e-12
    for params, capture in ((runs.flop_rst(), period / 2 + transition / 2), (Params(), period + transition / 2)):
        bench = sim.testbench(TbParams(params=params, data_offset_s=0.2e-9))
        assert isinstance(bench, h.Module) and bench.dut.of.name.startswith("Latch")
        assert float(bench.vclk.of.params.period) == approx(period)
        assert float(bench.vclk.of.params.delay) == approx(period / 2)
        data = bench.vd.of.params
        assert float(data.period) == approx(2 * period)
        assert float(data.delay) + transition / 2 == approx(capture + period - 0.2e-9)
        assert float(bench.cloadq.of.params.c) == float(bench.cloadqb.of.params.c) == approx(2e-15)


# Spectre's pulse rises from its delay over t_r, stays at v2 for its width, and falls over t_r: its
# mid-supply crossings are delay + t_r / 2 and delay + t_r + width + t_r / 2, so it is past
# mid-supply for width + t_r. A 50 % duty cycle is width + t_r = T / 2 at every period and edge.
@pytest.mark.parametrize(("period", "transition"), ((2e-9, 50e-12), (100e-12, 12.5e-12), (30e-12, 3.75e-12)))
def test_the_clocks_are_high_half_the_period(period: float, transition: float) -> None:
    bench = sim.testbench(
        TbParams(params=runs.flop_rst(), clock_period_s=period, transition_time_s=transition, data_offset_s=period / 2)
    )
    for source in (bench.vclk, bench.vclkb):
        params = source.of.params
        assert float(params.width) + float(params.rise) == approx(period / 2)
        assert float(params.fall) == approx(transition)


def test_an_sr_latch_gets_set_and_reset_pulses_active_as_its_gates_take_them() -> None:
    nand = sim.testbench(TbParams(params=runs.sr_nand(), vdd=1.0))
    nor = sim.testbench(TbParams(params=runs.sr_nor(), vdd=1.0))
    assert (float(nand.vs.of.params.v1), float(nand.vs.of.params.v2)) == (1.0, 0.0)
    assert (float(nor.vs.of.params.v1), float(nor.vs.of.params.v2)) == (0.0, 1.0)
    assert float(nor.vs.of.params.delay) == approx(5.2e-9 / 4)
    assert float(nor.vr.of.params.delay) == approx(3 * 5.2e-9 / 4)


def test_the_upset_bench_holds_a_one_and_loads_q_and_qb_as_the_timing_bench() -> None:
    bench = sim.testbench(TbParams(params=runs.latch_dice(), bench=Bench.UPSET, charge_c=10e-15))
    assert float(bench.vd.of.params.dc) == approx(1.2) and float(bench.vrst.of.params.dc) == 0.0
    # open (clk high) for the first nanosecond, then closed
    assert (float(bench.vclk.of.params.v1), float(bench.vclk.of.params.v2)) == (1.2, 0.0)
    assert float(bench.vclk.of.params.delay) == approx(1e-9)
    # one write phase, set once: the clock closes the latch and the strike must come after it
    early = sim.testbench(TbParams(params=runs.latch_dice(), bench=Bench.UPSET, charge_c=10e-15, write_time_s=0.4e-9))
    assert float(early.vclk.of.params.delay) == approx(0.4e-9)
    # one load condition a record: q and qb carry cload_f on both benches
    assert float(bench.cloadq.of.params.c) == float(bench.cloadqb.of.params.c) == approx(2e-15)


def test_an_input_the_design_does_not_use_is_held_fixed() -> None:
    """A divider's d, a TSPC circuit's clkb, rst without a reset, an SR latch's clocks and d, and a
    clocked design's s and r are DC sources; the inputs it uses are pulses."""

    def kinds(params: Params) -> dict[str, str]:
        bench = sim.testbench(TbParams(params=params))
        return {name: type(getattr(bench, name).of.params) for name in ("vclk", "vclkb", "vd", "vrst", "vs", "vr")}

    pulse, dc = type(Vpulse(v1=0.0, v2=1.0).params), type(Vdc(dc=0.0).params)
    assert kinds(runs.flop_rst()) == {"vclk": pulse, "vclkb": pulse, "vd": pulse, "vrst": pulse, "vs": dc, "vr": dc}
    assert kinds(runs.latch()) == {"vclk": pulse, "vclkb": pulse, "vd": pulse, "vrst": dc, "vs": dc, "vr": dc}
    assert kinds(runs.div2_tspc()) == {"vclk": pulse, "vclkb": dc, "vd": dc, "vrst": dc, "vs": dc, "vr": dc}
    assert kinds(runs.sr_nor()) == {"vclk": dc, "vclkb": dc, "vd": dc, "vrst": dc, "vs": pulse, "vr": pulse}


def test_a_run_saves_the_ports_the_supply_current_and_the_inputs_currents() -> None:
    ports = ("d", "s", "r", "rst", "clk", "clkb", "q", "qb")
    inputs = ("d", "s", "r", "rst", "clk", "clkb")
    assert set(sim.SAVES) == {*(f"xtop.{port}" for port in ports), "xtop.vvdd:p", *(f"xtop.v{net}:p" for net in inputs)}


# not in the reference texts: a double-exponential strike current A (e^{-t / tau2} - e^{-t / tau1})
# integrates to A (tau2 - tau1), so a charge Q takes A = Q / (tau2 - tau1): 10 fC over 45 ps is
# 0.222 mA, driven into the node by a source from it to ground (val1 negative). The transient keeps
# the strobe alone: no maxstep, which Spectre X disables.
def test_the_run_strobes_and_strikes_with_the_charge_asked(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    pytest.importorskip("pdk.tsmc65.hdl21")
    seen: list[Any] = []
    monkeypatch.setattr(sim.spectre, "run", lambda bench, attrs, run_dir: seen.extend(attrs))
    sim.simulate(TbParams(params=runs.latch(), bench=Bench.UPSET, charge_c=10e-15), tmp_path)
    tran = next(attr for attr in seen if isinstance(attr, hs.Tran))
    options = {name: getattr(value, "text", value) for name, value in tran.options.items()}
    assert options == {"strobeperiod": 1e-12, "strobeoutput": "strobeonly"}
    strike = next(attr.text for attr in seen if isinstance(attr, h.Literal) and attr.text.startswith("iupset"))
    assert "(xtop.dut.qb 0)" in strike and f"val1={-10e-15 / 45e-12:g} " in strike


@pytest.mark.parametrize(
    "change",
    (
        {"vdd": float("nan")},
        {"cload_f": 0.0},
        {"transition_time_s": 0.0},
        {"clock_period_s": 80e-12},
        {"clock_period_s": 100e-12, "data_offset_s": 25e-12},
        {"data_period_s": 350e-12},
        {"data_offset_s": 1.1e-9},
        {"reset_time_s": -1e-9},
        {"cycles": 2},
        {"charge_c": 5e-15},
        {"bench": Bench.UPSET},
        {"bench": Bench.UPSET, "charge_c": 5e-15, "upset_time_s": 1e-9},
        {"bench": Bench.UPSET, "charge_c": 5e-15, "write_time_s": 1.95e-9},
        {"bench": Bench.UPSET, "charge_c": 5e-15, "params": Params(reset=True)},
        {"bench": Bench.UPSET, "charge_c": 5e-15, "params": Params(style=Style.SR_NOR)},
    ),
)
def test_a_run_rejects_impossible_values(change: dict[str, Any]) -> None:
    with pytest.raises(ValueError):
        TbParams(**change)


# The pulse sources fit as the bench draws them: the clock's flat top T/2 - t_r is positive above
# T = 2 t_r (150 ps against 50 ps edges leaves 25 ps), and the set and reset pulses, a quarter of
# the data period plus both edges each, stay apart down to a data period of 8 t_r (400 ps).
def test_a_run_admits_the_shortest_pulses_that_fit() -> None:
    assert TbParams(params=runs.flop_rst(), clock_period_s=150e-12, data_offset_s=37.5e-12).clock_period_s == 150e-12
    assert TbParams(params=runs.sr_nor(), data_period_s=400e-12).data_period_s == 400e-12


STAND_IN_R_OHM, STAND_IN_C_F, LEAKAGE_R_OHM = 10e3, 8e-15, 1.2e6


def transparent_stand_in(_params: Params) -> h.Module:
    """An always transparent latch of ideal primitives on the latch's ports: a unity-gain
    controlled source copies d, a resistor into q's capacitance (its own and the bench's load) gives
    a single pole, a controlled source drives qb to V_DD - q, and a resistor from vdd to vss draws
    a known supply current."""
    latch = module_from_ports("Latch", Nets.signals)
    latch.copy = h.Signal()
    latch.ed = Vcvs(gain=1.0)(p=latch.copy, n=latch.vss, cp=latch.d, cn=latch.vss)
    latch.rq = R(r=STAND_IN_R_OHM)(p=latch.copy, n=latch.q)
    latch.cq = C(c=STAND_IN_C_F)(p=latch.q, n=latch.vss)
    latch.eqb = Vcvs(gain=1.0)(p=latch.qb, n=latch.vss, cp=latch.vdd, cn=latch.q)
    latch.rleak = R(r=LEAKAGE_R_OHM)(p=latch.vdd, n=latch.vss)
    return latch


# The timing bench in Spectre with the stand-in as its DUT, read and analysed as the flow does.
# d is a ramp of T_r = 50 ps into a single pole of tau = R (C + C_load) = 10 kOhm x 10 fF = 100 ps.
# A ramp's response past its end is V [1 - (tau / T_r)(e^{T_r / tau} - 1) e^{-t / tau}] (the
# step response integrated over the ramp), so it crosses V / 2 at t = tau ln(2 (tau / T_r)
# (e^{T_r / tau} - 1)) = 95.35 ps (past T_r, so the expression holds), 70.35 ps after the ramp's own
# mid-supply point; the response is linear, so rising and falling alike and the same at every
# supply.
# [Baker] Fig. 10.9, p. 333: delays between the 50 % points of input and output
# The latch's path opens at the rising clk edge, and d crosses mid-supply 0.5 ns before the closing
# edge, 0.5 ns after the opening one, so the delay runs from d. The only supply current is the
# resistor's, V_DD / R_leak (1 uA at 1.2 V), and a cycle's energy V_DD^2 T_CK / R_leak (2.4 fJ).
# [Baker] Eq. (11.15), p. 355: the average power, V_DD I_avg
# Tolerance: the bench strobes Spectre's output at 1 ps, so linear interpolation of q's crossing is
# off by at most h^2 / (8 tau) = 1.3 fs; Spectre X's own steps follow its accuracy preset; delays
# are checked to 0.05 ps, currents and energies to 1e-3. The stand-in draws no current from its
# inputs (an ideal controlled source's control is open), so the drivers' share is zero.
@pytest.mark.spectre
def test_the_timing_bench_on_an_ideal_stand_in(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    if shutil.which("spectre") is None:
        pytest.skip("Spectre binary is not on PATH; source the Cadence environment")
    if importlib.util.find_spec("pdk.tsmc65") is None:
        pytest.skip("TSMC65 PDK Python package is not installed")
    from flow import pipeline

    monkeypatch.setattr(sim, "netlist", transparent_stand_in)
    runs_ = []
    for factor in SUPPLY_SWEEP:
        tb = TbParams(params=Params(), vdd=1.2 * factor)
        runs_.append(pipeline.read(sim.simulate(tb, tmp_path / f"vdd{factor:g}"), tb))
    timing = analyze_timing(runs_)
    tau, ramp = STAND_IN_R_OHM * (STAND_IN_C_F + 2e-15), 50e-12
    delay = tau * math.log(2 * tau / ramp * (math.exp(ramp / tau) - 1)) - ramp / 2
    assert delay == approx(70.35e-12, abs=0.01e-12)
    assert timing.delay_rise_s == approx(np.full(3, delay), abs=0.05e-12)
    assert timing.delay_fall_s == approx(np.full(3, delay), abs=0.05e-12)
    assert timing.idd_drivers_a == approx(np.zeros(3), abs=1e-9)
    assert list(timing.captured_fraction) == [1.0] * 3 and list(timing.held_fraction) == [0.0] * 3
    supply_v = 1.2 * np.asarray(SUPPLY_SWEEP)
    assert timing.idd_a == approx(supply_v / LEAKAGE_R_OHM, rel=1e-3)
    found = metrics(supply=timing)
    assert (found.delay_rise_s, found.delay_fall_s, found.delay_max_supply_s) == approx(
        (delay, delay, delay), abs=0.05e-12
    )
    assert found.energy_per_cycle_j == approx(1.2**2 * 2e-9 / LEAKAGE_R_OHM, rel=1e-3)
