"""The chain's analyses, metrics and record on synthetic runs whose answer is known in closed form,
as a run's measurement (``flow.pipeline.Meas``) reads: a ring's output a sine or a trapezoid of known
frequency, amplitude and duty cycle; a delay line's output a single-pole response to the input clock
after a known transport delay; the supply current a known level plus a known charge at each edge.
Every waveform is sampled on a simulator's time axis: steps drawn between half and one and a half of
the bench's strobe, with a time point at each corner of a source or edge, as Spectre places one."""

from __future__ import annotations

import dataclasses
import math
from collections.abc import Callable, Iterable
from dataclasses import replace
from datetime import UTC, datetime

import numpy as np
import pytest

from flow import pipeline
from flow.pipeline import Meas, MeasInfo, Plot

from . import runs
from .analysis import analyze_oscillation, analyze_propagation, metrics
from .params import CONTROL_SWEEP, GAIN_POINTS, NOMINAL_CONTROL, SUPPLY_SWEEP, Oscillation, Params, TbParams
from .types import AnalysisOscillation, AnalysisPropagation, Metrics

INFO = MeasInfo(backend="spice", timestamp_utc=datetime(2026, 10, 17, tzinfo=UTC))
# the bench's strobe: the mean step of every synthetic time axis, its longest one and a half of it
STEP_S = 2e-12
STEP_MAX_S = 1.5 * STEP_S
LN2, LN9 = math.log(2.0), math.log(9.0)


def simulator_axis(stop_s: float, breakpoints: Iterable[float] = (), seed: int = 1) -> np.ndarray:
    """A simulator's time axis over [0, ``stop_s``]: steps drawn uniformly between half and one and a
    half of ``STEP_S``, and a time point at each of ``breakpoints``."""
    rng = np.random.default_rng(seed)
    time_s = np.cumsum(np.r_[0.0, rng.uniform(0.5 * STEP_S, STEP_MAX_S, int(stop_s / (0.5 * STEP_S)) + 2)])
    corners = [corner for corner in breakpoints if 0 < corner < stop_s]
    return np.unique(np.r_[time_s[time_s < stop_s], stop_s, corners])


def pulses(time_s: np.ndarray, centres_s: Iterable[float], charge_c: float, sigma_s: float = 10e-12) -> np.ndarray:
    """A Gaussian current pulse of ``charge_c`` (width ``sigma_s``) centred on each of ``centres_s``."""
    current = np.zeros_like(time_s)
    for centre in centres_s:
        near = np.abs(time_s - centre) < 10 * sigma_s
        current[near] += (
            charge_c / (sigma_s * math.sqrt(2 * math.pi)) * np.exp(-((time_s[near] - centre) ** 2) / (2 * sigma_s**2))
        )
    return current


def run(tb: TbParams, time_s: np.ndarray, outp: np.ndarray, idd_a: np.ndarray, inp: np.ndarray | None = None) -> Meas:
    """A run of ``tb``: its output ``outp`` and supply current ``idd_a`` over ``time_s``, its input
    ``inp`` (else held at zero)."""
    return Meas(
        group=None,
        index=None,
        dut=tb.params,
        info=INFO,
        param=tb,
        time_s=time_s,
        v={"outp": outp, "inp": np.zeros_like(time_s) if inp is None else inp},
        i={"vdd": idd_a},
    )


def cut(measured: Meas, stop_s: float) -> Meas:
    """The run ``measured`` as if its record had ended at ``stop_s``."""
    kept = measured.time_s <= stop_s
    return replace(
        measured,
        time_s=measured.time_s[kept],
        v={name: values[kept] for name, values in measured.v.items()},
        i={name: values[kept] for name, values in measured.i.items()},
    )


def cycles_since_enable(
    tb: TbParams, frequency_hz: float, startup: tuple[int, float] | None = None
) -> tuple[Callable[[np.ndarray], np.ndarray], Callable[[np.ndarray], np.ndarray]]:
    """A ring's phase in cycles since its enable (zero before it) and its inverse (the time at a
    phase): at ``frequency_hz`` throughout, or its first ``startup[0]`` cycles at ``startup[1]`` Hz."""
    enable = float(tb.enable_delay_s)
    cycles, slow_hz = startup if startup else (0, frequency_hz)
    slow_s = cycles / slow_hz

    def phase(time_s: np.ndarray) -> np.ndarray:
        elapsed = np.maximum(time_s - enable, 0.0)
        return np.where(elapsed < slow_s, elapsed * slow_hz, cycles + (elapsed - slow_s) * frequency_hz)

    def at(phase_cycles: np.ndarray) -> np.ndarray:
        return enable + np.where(
            phase_cycles < cycles, phase_cycles / slow_hz, slow_s + (phase_cycles - cycles) / frequency_hz
        )

    return phase, at


def ring_run(
    tb: TbParams,
    frequency_hz: float,
    *,
    amplitude_v: float | None = None,
    idd_a: float = 40e-6,
    charge_c: float = 10e-15,
    startup: tuple[int, float] | None = None,
    early_hz: float | None = None,
    seed: int = 1,
) -> Meas:
    """A ring whose output after the enable is ``vdd/2 - A cos(2 pi phase)`` (``A`` half the supply
    unless given), low at the enable; before it, still at that low level or, with ``early_hz``, a
    sine of that frequency the analysis must pass over. Its supply draws ``idd_a`` and ``charge_c`` at
    each crest and trough after the enable. Its rising mid-supply crossings are at phases k + 1/4."""
    vdd = float(tb.vdd)
    amplitude = vdd / 2 if amplitude_v is None else amplitude_v
    phase, at = cycles_since_enable(tb, frequency_hz, startup)
    time_s = simulator_axis(float(tb.stop_time_s), seed=seed)
    outp = vdd / 2 - amplitude * np.cos(2 * np.pi * phase(time_s))
    if early_hz is not None:
        before = time_s < tb.enable_delay_s
        outp[before] = vdd / 2 - amplitude * np.cos(2 * np.pi * early_hz * time_s[before])
    extremes = at(np.arange(1, 2 * float(phase(np.asarray(tb.stop_time_s)))) / 2)
    return run(tb, time_s, outp, idd_a + pulses(time_s, extremes, charge_c))


def trapezoid_run(tb: TbParams, frequency_hz: float, duty: float, edge_s: float = 40e-12) -> Meas:
    """A ring whose output is a rail-to-rail trapezoid at ``frequency_hz``, above mid-supply for
    ``duty`` of each period, its edges linear over ``edge_s`` (a time point at each corner); low until
    the enable, which falls in the middle of a low phase. Its supply draws 40 uA throughout."""
    vdd, enable = float(tb.vdd), float(tb.enable_delay_s)
    edge = edge_s * frequency_hz  # in cycles
    # the first rising mid-supply crossing half a low phase after the enable
    shift = (1 - duty) / 2
    phase, _at = cycles_since_enable(tb, frequency_hz)
    corners = [
        enable + (k + shift + offset) / frequency_hz
        for k in range(int(float(tb.stop_time_s) * frequency_hz) + 1)
        for offset in (-edge / 2, edge / 2, duty - edge / 2, duty + edge / 2)
    ]
    time_s = simulator_axis(float(tb.stop_time_s), corners)
    # the phase within a period from a rising mid-supply crossing, signed by its distance to the
    # nearer crossing: positive above mid-supply
    within = np.mod(phase(time_s) - shift, 1.0)
    signed = np.where(within < duty, np.minimum(within, duty - within), -np.minimum(within - duty, 1 - within))
    outp = vdd / 2 + vdd / 2 * np.clip(signed / (edge / 2), -1.0, 1.0)
    outp[time_s < enable] = 0.0
    return run(tb, time_s, outp, np.full(len(time_s), 40e-6))


def line_run(
    tb: TbParams,
    *,
    transport_s: float,
    tau_rise_s: float,
    tau_fall_s: float,
    idd_a: float = 5e-6,
    charge_c: float = 20e-15,
    edge_tau_s: dict[int, float] | None = None,
    seed: int = 2,
) -> Meas:
    """A delay line driven by the bench's input clock (``sim.testbench``: a pulse from 0 to the
    supply, its first edge a quarter period in, each edge linear over ``transition_time_s``): its
    output a single-pole response, ``transport_s`` after each mid-supply input crossing, toward the
    supply with ``tau_rise_s`` and toward ground with ``tau_fall_s``, inverted by an odd chain; its
    supply draws ``idd_a`` and ``charge_c`` 10 ps into each output edge. With ``edge_tau_s``, the
    output's k-th edge (from 0: the first answers the first input edge) takes ``edge_tau_s[k]``."""
    vdd, period, edge = float(tb.vdd), float(tb.clock_period_s), float(tb.transition_time_s)
    stop = float(tb.stop_time_s)
    starts = np.arange(period / 4, stop, period)
    corners = np.sort(np.r_[starts, starts + edge, starts + period / 2, starts + period / 2 + edge])
    levels = np.tile([0.0, vdd, vdd, 0.0], len(starts))
    inverting = tb.params.stages % 2 == 1
    # the output's edges: each mid-supply input crossing plus the transport delay, and its target
    launches = np.sort(np.r_[starts + edge / 2, starts + period / 2 + edge / 2]) + transport_s
    targets = np.tile([0.0, vdd] if inverting else [vdd, 0.0], len(starts))
    time_s = simulator_axis(stop, [*corners, *launches], seed=seed)
    source = np.interp(time_s, np.r_[0.0, corners], np.r_[0.0, levels])
    outp = np.full(len(time_s), vdd if inverting else 0.0)
    level = float(outp[0])
    for k, (launch, target) in enumerate(zip(launches, targets, strict=True)):
        until = launches[k + 1] if k + 1 < len(launches) else math.inf
        tau = tau_rise_s if target > level else tau_fall_s
        tau = (edge_tau_s or {}).get(k, tau)
        segment = (time_s >= launch) & (time_s < until)
        outp[segment] = target + (level - target) * np.exp(-(time_s[segment] - launch) / tau)
        level = target + (level - target) * math.exp(-(min(until, stop) - launch) / tau)
    return run(tb, time_s, outp, idd_a + pulses(time_s, launches + 10e-12, charge_c, 5e-12), source)


# --- analyze_oscillation -------------------------------------------------------------------------


# A ring's output vdd/2 - A cos(2 pi f t): its rising mid-supply crossings are 1/f apart, so ten
# cycles between them give f itself ([Razavi-PLL] Sec. 3.1.1, p. 64: the oscillation frequency), and
# [Razavi-PLL] Sec. 3.3.2, p. 74: f0 = 1 / (2 N T_D), so T_D = 1 / (2 N f), 1 / (10 f) for five
# stages. Its peak to peak is 2 A, and it spends half of each period above mid-supply ([Razavi-PLL]
# Sec. 11.10, p. 365: the duty cycle, the high time over the period). Tolerances: a crossing found
# by linear interpolation at the sine's inflection is off by about h^3 (2 pi f)^2 / 8, under 1e-15 s
# for h <= 3 ps, so rel 1e-6; the sampled crests miss the peak by at most A (pi f h)^2 / 2, about
# 3e-4 V at 2.5 GHz, so the swing to 5e-4 V; the duty cycle from the same interpolated crossings, a
# sine's high time half its period, to 1e-5.
def test_ring_frequency_swing_duty_and_stage_delay() -> None:
    ring = runs.ring5()
    points = ((1.08, 0.8e9, 0.5), (1.2, 2.5e9, 0.45))
    result = analyze_oscillation(
        [ring_run(TbParams(params=ring, vdd=vdd), f, amplitude_v=a, seed=k) for k, (vdd, f, a) in enumerate(points)]
    )
    assert isinstance(result, AnalysisOscillation) and result.dut == ring
    assert result.vdd_v.tolist() == [1.08, 1.2]
    assert result.vcont_v.tolist() == [0.8, 0.8]
    assert result.oscillation_frequency_hz == pytest.approx([0.8e9, 2.5e9], rel=1e-6)
    assert result.swing_v == pytest.approx([1.0, 0.9], abs=5e-4)
    assert result.duty_cycle == pytest.approx([0.5, 0.5], abs=1e-5)
    assert result.stage_delay_s == pytest.approx([125e-12, 40e-12], rel=1e-6)
    assert result.oscillation == (Oscillation.TIMED, Oscillation.TIMED)


# The supply draws I0 and a charge Q at each crest and trough: the window from one rising crossing
# to the tenth after it holds exactly ten cycles, two pulses each, every pulse a quarter cycle (25
# sigma) from its ends, so the mean current is I0 + 2 Q f = 40 uA + 2 * 10 fC * 1 GHz = 60 uA.
# [Baker] Eq. (11.15), p. 355: P_avg = V_DD I_avg = 1.2 V * 60 uA = 72 uW; a cycle's energy P_avg / f
# = 72 fJ. Tolerance rel 1e-3: the trapezoidal integral of a 10 ps pulse on 1 to 3 ps steps.
def test_ring_supply_current_power_and_energy_per_cycle() -> None:
    result = analyze_oscillation([ring_run(TbParams(params=runs.ring5()), 1e9, idd_a=40e-6, charge_c=10e-15)])
    assert result.idd_a[0] == pytest.approx(60e-6, rel=1e-3)
    assert result.average_power_w[0] == pytest.approx(72e-6, rel=1e-3)
    assert result.energy_per_cycle_j[0] == pytest.approx(72e-15, rel=1e-3)


# A trapezoid above mid-supply for D = 0.3 of each period: its duty cycle is 0.3 ([Razavi-PLL] Sec.
# 11.10, p. 365: the high time over the period). Its crossings lie on linear edges sampled at their
# corners, so the crossings, the frequency and the duty cycle are exact to rounding; its plateaus are
# the rails, so the swing is the supply. A trapezoid of D = 0.7 likewise reads 0.7.
def test_ring_duty_cycle_of_an_asymmetric_output() -> None:
    result = analyze_oscillation([trapezoid_run(TbParams(params=runs.ring5()), 1e9, 0.3)])
    assert result.oscillation_frequency_hz[0] == pytest.approx(1e9, rel=1e-9)
    assert result.duty_cycle[0] == pytest.approx(0.3, abs=1e-9)
    assert analyze_oscillation([trapezoid_run(TbParams(params=runs.ring5()), 1e9, 0.7)]).duty_cycle[0] == pytest.approx(
        0.7, abs=1e-9
    )
    assert result.swing_v[0] == pytest.approx(1.2, abs=1e-9)
    assert result.idd_a[0] == pytest.approx(40e-6, rel=1e-9)


# The swing is the output's peak to peak, the overshoot past each rail included: the trapezoid above,
# D = 0.5 at 1 GHz on a 1.2 V supply, with 45 mV more than the rail for 10 ps after each high corner and
# 45 mV under ground for 10 ps after each low corner (the time points there exact, between the edges)
# reads 1.2 V + 2 * 45 mV = 1.29 V, to rounding; its crossings lie on the unchanged edges, so its
# frequency and duty cycle are the trapezoid's.
def test_a_rings_swing_counts_its_overshoot_past_the_rails() -> None:
    tb = TbParams(params=runs.ring5())
    measured = trapezoid_run(tb, 1e9, 0.5)
    time_s, outp = measured.time_s, measured.v["outp"].copy()
    enable, edge = float(tb.enable_delay_s), 40e-12
    for k in range(40):
        high = enable + (k + 0.25) * 1e-9 + edge / 2  # the first rising crossing a quarter period in
        low = high + 0.5e-9
        outp[(time_s > high) & (time_s <= high + 10e-12)] += 0.045
        outp[(time_s > low) & (time_s <= low + 10e-12)] -= 0.045
    result = analyze_oscillation([replace(measured, v={**measured.v, "outp": outp})])
    assert result.swing_v[0] == pytest.approx(1.29, abs=1e-9)
    assert result.oscillation_frequency_hz[0] == pytest.approx(1e9, rel=1e-9)
    assert result.duty_cycle[0] == pytest.approx(0.5, abs=1e-9)
    described = {field.name: field.metadata["desc"] for field in dataclasses.fields(Metrics)}
    assert "overshoot" in described["swing_v"]


# The analysis counts the rising crossings after the enable only and times the last ten whole cycles
# before the run's end. A ring oscillating at 3 GHz before its enable (three rises), its first four
# cycles after it at 0.5 GHz, then at 1 GHz: the last ten cycles are all at 1 GHz, so the frequency is
# 1 GHz (rel 1e-6 as above), and the supply current the 40 uA it draws throughout.
def test_ring_window_passes_over_the_enable_and_the_start_up() -> None:
    tb = TbParams(params=runs.ring5())
    result = analyze_oscillation([ring_run(tb, 1e9, startup=(4, 0.5e9), early_hz=3e9, charge_c=0.0)])
    assert result.oscillation_frequency_hz[0] == pytest.approx(1e9, rel=1e-6)
    assert result.idd_a[0] == pytest.approx(40e-6, rel=1e-9)
    assert result.oscillation == (Oscillation.TIMED,)


# A slow ring makes fewer than eleven rises in the run: rises at t_en + (k + 1/4) / f before 40 ns,
# k < 39 ns * f - 1/4. At 170 MHz seven rises: the window shrinks to the six whole cycles between
# them, so f exactly; at 100 MHz four rises, three cycles. At 60 MHz three rises (5.17, 21.8 and
# 38.5 ns), two whole cycles, the fewest the analysis times. At 40 MHz two rises (7.25 and 32.25 ns)
# and a fall between them (19.75 ns), one whole cycle: oscillating to the run's end (its last
# crossing 7.75 ns before it, within two of its 12.5 ns crossing gaps), but too slow to be timed:
# Oscillation.SLOW, its numbers NaN.
def test_a_slow_ring_is_timed_over_the_cycles_it_made() -> None:
    ring = runs.ring5()
    frequencies = (170e6, 100e6, 60e6, 40e6)
    result = analyze_oscillation([ring_run(TbParams(params=ring), f, charge_c=0.0) for f in frequencies])
    assert result.oscillation_frequency_hz[:3] == pytest.approx(frequencies[:3], rel=1e-6)
    assert result.stage_delay_s[:3] == pytest.approx([1 / (10 * f) for f in frequencies[:3]], rel=1e-6)
    assert result.oscillation == (Oscillation.TIMED,) * 3 + (Oscillation.SLOW,)
    assert result.oscillating.tolist() == [True] * 4
    assert math.isnan(result.oscillation_frequency_hz[3]) and math.isnan(result.idd_a[3])
    assert math.isnan(result.swing_v[3]) and math.isnan(result.duty_cycle[3])


# A ring that stops: twenty cycles at 1 GHz after the enable, then its output held at ground (the
# trough it reached at phase 20) for the run's last 19 ns, nineteen of its periods without a crossing.
# [Razavi-PLL] Sec. 1.1, Fig. 1.1, p. 1: an oscillation without a sustaining mechanism dies out; an
# output that comes to rest is no oscillation, whatever its first cycles did. Not in the reference
# texts: the analysis's rule, a ring whose last rise is more than two periods before the run's end
# has stopped; here the last rise (20.25 ns) is 19.75 ns before it, so the point is stopped and holds
# no frequency (NaN).
def test_a_ring_that_stops_is_not_oscillating() -> None:
    tb = TbParams(params=runs.ring5())
    measured = ring_run(tb, 1e9, charge_c=0.0)
    outp = np.where(measured.time_s > float(tb.enable_delay_s) + 20e-9, 0.0, measured.v["outp"])
    result = analyze_oscillation([replace(measured, v={**measured.v, "outp": outp})])
    assert result.oscillation == (Oscillation.STOPPED,) and not result.oscillating[0]
    assert math.isnan(result.oscillation_frequency_hz[0])


# A ring with a long start-up: its first eight cycles after the enable at 1.5 GHz, then 2 GHz to the
# run's end (about 67 more cycles). [Razavi-PLL] Sec. 3.1.1, p. 64: the ring's period T0 = 1 / f0,
# here the steady state's, so f0 = 2 GHz, to rel 1e-6 as above: the last ten cycles are all steady,
# where any window holding start-up cycles reads less.
def test_a_ring_is_timed_in_its_steady_state() -> None:
    tb = TbParams(params=runs.ring5())
    result = analyze_oscillation([ring_run(tb, 2e9, startup=(8, 1.5e9), charge_c=0.0)])
    assert result.oscillation_frequency_hz[0] == pytest.approx(2e9, rel=1e-6)


# A ring that never oscillates holds NaN and is not oscillating, whatever it is stuck at: either
# rail, an oscillation about a level that never reaches mid-supply (0.3 V +- 0.1 V on 1.2 V), or a
# run of one time point. A design that is no ring, or a run without a transient, is refused.
def test_a_ring_that_does_not_oscillate() -> None:
    tb = TbParams(params=runs.ring5())
    time_s = simulator_axis(float(tb.stop_time_s))
    quiet = np.full(len(time_s), 1e-6)
    small = ring_run(tb, 1e9, amplitude_v=0.1)
    stuck = [
        run(tb, time_s, np.zeros_like(time_s), quiet),
        run(tb, time_s, np.full(len(time_s), 1.2), quiet),
        replace(small, v={**small.v, "outp": small.v["outp"] - 0.3}),
        run(tb, np.zeros(1), np.zeros(1), np.zeros(1)),
    ]
    result = analyze_oscillation(stuck)
    assert result.oscillation == (Oscillation.STOPPED,) * 4 and not result.oscillating.any()
    for values in (result.oscillation_frequency_hz, result.idd_a, result.swing_v, result.duty_cycle):
        assert np.isnan(values).all()
    with pytest.raises(ValueError, match="requires a ring"):
        analyze_oscillation([replace(stuck[0], dut=runs.chain4())])
    with pytest.raises(ValueError, match="requires a transient"):
        analyze_oscillation([replace(stuck[0], time_s=np.zeros(0), v={}, i={})])


# --- analyze_propagation -------------------------------------------------------------------------

D0, TAU_R, TAU_F = 30e-12, 25e-12, 15e-12


# A single-pole output launched D0 after each mid-supply input crossing: from a settled rail (half a
# period is over 80 time constants) it crosses mid-supply tau ln 2 after its launch and passes 10 to
# 90 % in tau (ln 10 - ln(10/9)) = tau ln 9. [Baker] Fig. 10.9, p. 333: t_PLH and t_PHL between the
# 50 % points, t_LH and t_HL from 10 to 90 %; [Baker] Eq. (10.17) and (10.18), p. 333: 0.7 RC and
# 2.2 RC, ln 2 and ln 9 rounded. So t_PLH = D0 + TAU_R ln 2 = 47.33 ps, t_PHL = D0 + TAU_F ln 2 =
# 40.40 ps, t_LH = TAU_R ln 9 = 54.93 ps, t_HL = TAU_F ln 9 = 32.96 ps, the stage delay their mean
# over four stages. Tolerance 0.2 ps: linear interpolation on an exponential misplaces a crossing by
# at most h^2 / (8 tau), under 0.1 ps for h <= 3 ps and tau >= 15 ps (each launch a time point).
def test_line_delays_and_transitions_of_a_single_pole_output() -> None:
    line = runs.chain4()
    result = analyze_propagation([line_run(TbParams(params=line), transport_s=D0, tau_rise_s=TAU_R, tau_fall_s=TAU_F)])
    assert isinstance(result, AnalysisPropagation) and result.dut == line
    assert result.delay_rise_s[0] == pytest.approx(D0 + TAU_R * LN2, abs=0.2e-12)
    assert result.delay_fall_s[0] == pytest.approx(D0 + TAU_F * LN2, abs=0.2e-12)
    assert result.rise_time_s[0] == pytest.approx(TAU_R * LN9, abs=0.2e-12)
    assert result.fall_time_s[0] == pytest.approx(TAU_F * LN9, abs=0.2e-12)
    assert result.delay_s[0] == pytest.approx(D0 + (TAU_R + TAU_F) / 2 * LN2, abs=0.2e-12)
    assert result.stage_delay_s[0] == pytest.approx((D0 + (TAU_R + TAU_F) / 2 * LN2) / 4, abs=0.05e-12)
    assert result.clock_period_s[0] == 4e-9 and result.valid[0]


# An odd chain inverts: its output rises after a falling input. [Baker] Fig. 10.9, p. 333: each delay
# is named by the output's edge, t_PLH to the rising output whichever input edge caused it, so with
# unequal rise and fall time constants the delay to the rising output is still D0 + TAU_R ln 2.
def test_an_inverting_line_is_timed_to_the_edge_its_output_makes() -> None:
    result = analyze_propagation(
        [line_run(TbParams(params=Params(stages=3)), transport_s=D0, tau_rise_s=TAU_R, tau_fall_s=TAU_F)]
    )
    assert result.delay_rise_s[0] == pytest.approx(D0 + TAU_R * LN2, abs=0.2e-12)
    assert result.delay_fall_s[0] == pytest.approx(D0 + TAU_F * LN2, abs=0.2e-12)
    assert result.rise_time_s[0] == pytest.approx(TAU_R * LN9, abs=0.2e-12)
    assert result.fall_time_s[0] == pytest.approx(TAU_F * LN9, abs=0.2e-12)
    assert result.stage_delay_s[0] == pytest.approx((D0 + (TAU_R + TAU_F) / 2 * LN2) / 3, abs=0.07e-12)
    assert result.valid[0]


# The supply draws I0 and a charge Q 10 ps into each output edge: two input periods from the second
# rising input crossing hold four output edges, the first 40 ps (8 sigma) after the window's start
# and the next as far past its end, so the mean current is I0 + 4 Q / (2 T) = 5 uA + 2 * 20 fC / 4 ns
# = 15 uA. [Baker] Eq. (11.15), p. 355: P_avg = V_DD I_avg = 18 uW; an input cycle's energy P_avg T =
# 72 fJ. Tolerance rel 1e-3, the trapezoidal integral of the pulses.
def test_line_supply_current_power_and_energy_per_input_cycle() -> None:
    result = analyze_propagation(
        [line_run(TbParams(params=runs.chain4()), transport_s=D0, tau_rise_s=TAU_R, tau_fall_s=TAU_F)]
    )
    assert result.idd_a[0] == pytest.approx(15e-6, rel=1e-3)
    assert result.average_power_w[0] == pytest.approx(18e-6, rel=1e-3)
    assert result.energy_per_cycle_j[0] == pytest.approx(72e-15, rel=1e-3)


# An output too slow to settle in a half period (tau = 1.5 ns, H = T/2 = 2 ns, e^(-H/tau) = 0.2636)
# never reaches 90 % of the supply: no rise or fall time (NaN), so not valid. Its delays still exist,
# from the levels the record reached (in units of the supply): from 0, after the first rise v1 = 1 -
# e^(-H/tau), after the first fall v2 = v1 e^(-H/tau); the second rise crosses 1/2 where (1 - v2)
# e^(-s/tau) = 1/2, s = tau ln(2 (1 - v2)); it reaches v3 = 1 - (1 - v2) e^(-H/tau), and the second
# fall crosses 1/2 where v3 e^(-s/tau) = 1/2, s = tau ln(2 v3). Tolerance 0.2 ps, as above.
def test_a_line_that_never_settles_has_delays_but_no_transitions() -> None:
    tau = 1.5e-9
    decay = math.exp(-2e-9 / tau)
    v2 = (1 - decay) * decay
    v3 = 1 - (1 - v2) * decay
    result = analyze_propagation(
        [line_run(TbParams(params=runs.chain4()), transport_s=D0, tau_rise_s=tau, tau_fall_s=tau)]
    )
    assert result.delay_rise_s[0] == pytest.approx(D0 + tau * math.log(2 * (1 - v2)), abs=0.2e-12)
    assert result.delay_fall_s[0] == pytest.approx(D0 + tau * math.log(2 * v3), abs=0.2e-12)
    assert math.isnan(result.rise_time_s[0]) and math.isnan(result.fall_time_s[0])
    assert math.isfinite(result.idd_a[0]) and not result.valid[0]


# Missing events. A record cut short at 10 ns: the delays and transitions exist (the second edges are at 5 and
# 7 ns) but the two input periods for the current (to 13 ns) do not: NaN current, not valid. One cut
# at 4.5 ns has one rising input edge: nothing is measured. An output stuck low has no edges: no delay
# or transition, the current still averaged. A run of one time point measures nothing. A ring, or a
# run without a transient, is refused.
def test_a_line_with_missing_events() -> None:
    line = runs.chain4()
    shapes = {"transport_s": D0, "tau_rise_s": TAU_R, "tau_fall_s": TAU_F}
    full = line_run(TbParams(params=line), **shapes)
    short, shorter = (cut(full, stop_s) for stop_s in (10e-9, 4.5e-9))
    stuck = replace(full, v={**full.v, "outp": np.zeros_like(full.time_s)})
    point = run(TbParams(params=line), np.zeros(1), np.zeros(1), np.zeros(1))
    result = analyze_propagation([short, shorter, stuck, point])
    assert result.delay_rise_s[0] == pytest.approx(D0 + TAU_R * LN2, abs=0.2e-12)
    assert result.fall_time_s[0] == pytest.approx(TAU_F * LN9, abs=0.2e-12)
    assert math.isnan(result.idd_a[0])
    for values in (result.delay_rise_s, result.delay_fall_s, result.rise_time_s, result.fall_time_s):
        assert np.isnan(values[1:]).all()
    assert math.isnan(result.idd_a[1]) and math.isfinite(result.idd_a[2]) and math.isnan(result.idd_a[3])
    assert not result.valid.any()
    with pytest.raises(ValueError, match="not a ring"):
        analyze_propagation([ring_run(TbParams(params=runs.ring5()), 1e9)])
    with pytest.raises(ValueError, match="requires a transient"):
        analyze_propagation([replace(full, time_s=np.zeros(0), v={}, i={})])


# A line whose first output rise and fall are faster (tau 10 ps) than every later edge (TAU_R,
# TAU_F): the delays are measured from the second input edges to the output edges they caused, and
# [Baker] Fig. 10.9, p. 333 takes t_LH and t_HL on the same output waveform as t_PLH and t_PHL, so
# the transitions are those edges' own: t_LH = TAU_R ln 9 = 54.93 ps, t_HL = TAU_F ln 9 = 32.96 ps,
# not the first edges' 10 ps ln 9 = 21.97 ps. Each edge starts from a settled rail (a half period is
# 80 time constants of the slowest), so the delays stay D0 + tau ln 2 of the later edges. Tolerance
# 0.2 ps, as above. The same for an inverting line, whose first output edge is a fall.
def test_a_lines_transitions_are_the_edges_its_delays_measured() -> None:
    for line in (runs.chain4(), Params(stages=3)):
        result = analyze_propagation(
            [
                line_run(
                    TbParams(params=line),
                    transport_s=D0,
                    tau_rise_s=TAU_R,
                    tau_fall_s=TAU_F,
                    edge_tau_s={0: 10e-12, 1: 10e-12},
                )
            ]
        )
        assert result.delay_rise_s[0] == pytest.approx(D0 + TAU_R * LN2, abs=0.2e-12)
        assert result.delay_fall_s[0] == pytest.approx(D0 + TAU_F * LN2, abs=0.2e-12)
        assert result.rise_time_s[0] == pytest.approx(TAU_R * LN9, abs=0.2e-12)
        assert result.fall_time_s[0] == pytest.approx(TAU_F * LN9, abs=0.2e-12)
        assert result.valid[0]


# The output edge a delay timed is the one whose transition is reported, even where an earlier edge
# was incomplete. A non-inverting line whose first output pulse stops at 0.7 V_DD (its 50 % crossings
# unchanged, so the edge count holds) and whose second rise takes tau = 100 ps: t_PLH = D0 + 100 ps
# ln 2 and t_LH = 100 ps ln 9 = 219.72 ps ([Baker] Sec. 10.1.3, Fig. 10.9, p. 333: t_LH and t_PLH
# of one edge), not the third rise's TAU_R ln 9 = 54.93 ps, which the second complete transition is.
# Where the timed edge itself stops at 0.7 V_DD, its rise time is NaN and the point not valid (the
# output turns back through mid-supply at the next fall before any 90 % crossing of its own).
# Tolerance 0.2 ps, as above.
def test_a_lines_transition_is_the_timed_edges_after_an_incomplete_one() -> None:
    line = runs.chain4()
    period = float(TbParams(params=line).clock_period_s)
    measured = line_run(
        TbParams(params=line), transport_s=D0, tau_rise_s=TAU_R, tau_fall_s=TAU_F, edge_tau_s={2: 100e-12}
    )
    vdd = float(TbParams(params=line).vdd)
    for pulse, expected in ((0, 100e-12 * LN9), (1, math.nan)):
        outp = measured.v["outp"].copy()
        start = period / 4 + pulse * period
        within = (measured.time_s > start) & (measured.time_s < start + period * 0.75)
        outp[within] = np.minimum(outp[within], 0.7 * vdd)
        result = analyze_propagation([replace(measured, v={**measured.v, "outp": outp})])
        if pulse == 0:
            assert result.delay_rise_s[0] == pytest.approx(D0 + 100e-12 * LN2, abs=0.2e-12)
            assert result.rise_time_s[0] == pytest.approx(expected, abs=0.2e-12)
            assert result.fall_time_s[0] == pytest.approx(TAU_F * LN9, abs=0.2e-12)
            assert result.valid[0]
        else:
            assert math.isnan(result.rise_time_s[0]) and not result.valid[0]


# A line whose falls are too slow to reach 10 % (tau = 1.5 ns over a half period H = T/2 = 2 ns: each
# fall from the supply stops at e^(-H/tau) = 0.2636 V_DD) and whose rises are fast (TAU_R, settled
# to the supply within H). No fall reaches its end level, so t_HL is NaN; no rise after the first
# starts below 10 %, so the timed rise has no start crossing after the previous fall's mid-supply
# crossing and t_LH is NaN too ([Baker] Sec. 10.1.3, Fig. 10.9, p. 333: t_LH from V_OL's 10 % point
# of the same edge), not the time from the record's first 10 % crossing, periods earlier. The delays
# stay: the timed rise crosses 1/2 from 0.2636 at s = TAU_R ln(2 (1 - e^(-H/tau))), the timed fall
# from the supply at tau ln 2. Inverting (its first output edge a fall, so the even edges slow) and
# not alike. Tolerance 0.2 ps, as above.
def test_a_lines_transitions_need_the_previous_edge_to_have_settled() -> None:
    tau = 1.5e-9
    decay = math.exp(-2e-9 / tau)
    for line, slow in ((runs.chain4(), 1), (Params(stages=3), 0)):
        result = analyze_propagation(
            [
                line_run(
                    TbParams(params=line),
                    transport_s=D0,
                    tau_rise_s=TAU_R,
                    tau_fall_s=TAU_F,
                    edge_tau_s={k: tau for k in range(slow, 40, 2)},
                )
            ]
        )
        assert result.delay_rise_s[0] == pytest.approx(D0 + TAU_R * math.log(2 * (1 - decay)), abs=0.2e-12)
        assert result.delay_fall_s[0] == pytest.approx(D0 + tau * LN2, abs=0.2e-12)
        assert math.isnan(result.rise_time_s[0]) and math.isnan(result.fall_time_s[0])
        assert not result.valid[0]


# A delay paired by edge count is checked against the first edges' and its sign. A glitch high from
# 0.1 to 0.2 ns, before the first input edge (T/4 + 25 ps = 1.025 ns), adds an output rise and fall:
# the second output rise is then the first answer, at 1.025 ns + D0 + TAU_R ln 2, and the second
# input rise at 5.025 ns, so the count reads D0 + TAU_R ln 2 - 4 ns < 0: no delay (NaN), the point
# not valid; the fall alike. An output pulse lost after the first (the output held low from 5 to
# 7.5 ns, the second pulse's span) makes the second output rise the third input rise's answer: the
# second edges' delay is 4 ns + D0 + TAU_R ln 2, the first edges' D0 + TAU_R ln 2, apart by the
# period T = 4 ns, over T/4: NaN and not valid, the fall alike ([Baker] Sec. 10.1.3, Fig. 10.9,
# p. 333: a delay is to the output edge the input edge caused).
def test_a_line_whose_edge_count_is_off_has_no_delay() -> None:
    line = runs.chain4()
    measured = line_run(TbParams(params=line), transport_s=D0, tau_rise_s=TAU_R, tau_fall_s=TAU_F)
    time_s, vdd = measured.time_s, float(TbParams(params=line).vdd)
    glitched = measured.v["outp"].copy()
    glitched[(time_s > 0.1e-9) & (time_s < 0.2e-9)] = vdd
    lost = measured.v["outp"].copy()
    lost[(time_s > 5e-9) & (time_s < 7.5e-9)] = 0.0
    result = analyze_propagation(
        [replace(measured, v={**measured.v, "outp": outp}) for outp in (glitched, lost, measured.v["outp"])]
    )
    assert np.isnan(result.delay_rise_s[:2]).all() and np.isnan(result.delay_fall_s[:2]).all()
    assert result.valid.tolist() == [False, False, True]
    assert result.delay_rise_s[2] == pytest.approx(D0 + TAU_R * LN2, abs=0.2e-12)


# A line slower than half the input period but faster than the period: transport 3.9 ns on a 4 ns
# period. The input crosses mid-supply rising at T/4 + 25 ps + kT (1.025, 5.025, ... ns) and falling
# half a period later; the output rises 3.9 ns after each rising crossing and falls 3.9 ns after
# each falling one, so the first output rise after the second input rise (5.025 ns) is the one it
# caused, at 8.925 ns + TAU_R ln 2, and the first output fall after the second input fall (7.025 ns)
# the one it caused, at 10.925 ns + TAU_F ln 2. [Baker] Fig. 10.9, p. 333: t_PLH = 3.9 ns + TAU_R ln
# 2, t_PHL = 3.9 ns + TAU_F ln 2. Tolerance 0.2 ps, as above.
def test_a_line_slower_than_half_a_period_is_timed_to_the_edge_it_caused() -> None:
    transport = 3.9e-9
    result = analyze_propagation(
        [line_run(TbParams(params=runs.chain4()), transport_s=transport, tau_rise_s=TAU_R, tau_fall_s=TAU_F)]
    )
    assert result.delay_rise_s[0] == pytest.approx(transport + TAU_R * LN2, abs=0.2e-12)
    assert result.delay_fall_s[0] == pytest.approx(transport + TAU_F * LN2, abs=0.2e-12)
    assert result.valid[0]


# A line slower than the input period: transport 4.6 ns on a 4 ns period. Its first output rise
# (5.625 ns + TAU_R ln 2) answers the first input rise (1.025 ns), yet falls after the second input
# rise (5.025 ns): pairing each input edge with the next output edge would read 0.6 ns + TAU_R ln 2,
# a period short. Counted from the settled start, the k-th output edge of each sense answers the
# k-th input edge that causes it, so t_PLH = 4.6 ns + TAU_R ln 2 and t_PHL = 4.6 ns + TAU_F ln 2
# ([Baker] Fig. 10.9, p. 333). Tolerance 0.2 ps, as above.
# The same pairing holds a delay of one and a half periods (6 ns): the second input rise (5.025 ns)
# causes the output's second rise (11.025 ns + TAU_R ln 2), and an inverting line (three stages) is
# paired the same way by its answering edges.
def test_a_line_slower_than_its_input_period_is_not_aliased() -> None:
    for transport, line in ((4.6e-9, runs.chain4()), (6e-9, runs.chain4()), (4.6e-9, Params(stages=3))):
        result = analyze_propagation(
            [line_run(TbParams(params=line), transport_s=transport, tau_rise_s=TAU_R, tau_fall_s=TAU_F)]
        )
        assert result.delay_rise_s[0] == pytest.approx(transport + TAU_R * LN2, abs=0.2e-12)
        assert result.delay_fall_s[0] == pytest.approx(transport + TAU_F * LN2, abs=0.2e-12)
        assert result.rise_time_s[0] == pytest.approx(TAU_R * LN9, abs=0.2e-12)
        assert result.valid[0]


# --- metrics and the record ----------------------------------------------------------------------


def ring_frequency_hz(vdd: float, vcont_v: float) -> float:
    """The synthetic ring's frequency: (V_DD / 1.2 V)^2 g(V_cont), g = 1 GHz + 2 GHz/V (V_cont -
    0.8 V) + 1.5 GHz/V^2 (V_cont - 0.8 V)^2."""
    offset = vcont_v - 0.8
    return (vdd / 1.2) ** 2 * (1e9 + 2e9 * offset + 1.5e9 * offset**2)


def ring_measurements(ring: Params) -> dict[str, Meas]:
    """A controlled ring's runs, named as ``runs.testbenches`` names them at a 1.2 V supply, each at
    ``ring_frequency_hz`` with a 0.55 V amplitude, 40 uA and 10 fC at each crest and trough."""
    measurements = {}
    for factor in SUPPLY_SWEEP:
        tb = TbParams(params=ring, vdd=round(1.2 * factor, 4), vcont_v=0.8)
        measurements[f"supply_{round(factor * 100)}"] = ring_run(tb, ring_frequency_hz(tb.vdd, 0.8), amplitude_v=0.55)
    for step in CONTROL_SWEEP:
        if not math.isclose(step, NOMINAL_CONTROL):
            tb = TbParams(params=ring, vcont_v=round(1.2 * step, 4))
            measurements[f"control_{round(step * 12)}"] = ring_run(
                tb, ring_frequency_hz(1.2, tb.vcont_v), amplitude_v=0.55
            )
    return measurements


# The record of a controlled ring whose frequency is ring_frequency_hz. At 1.2 V and 0.8 V: f =
# 1 GHz, swing 2 * 0.55 V = 1.1 V, T_D = 1 / (2 * 5 * f) = 100 ps ([Razavi-PLL] Sec. 3.3.2, p. 74),
# I_DD = 40 uA + 2 * 10 fC * f = 60 uA, P = 72 uW and 72 fJ a cycle ([Baker] Eq. (11.15), p. 355);
# the slowest stage over the supply at 1.08 V, f = 0.81 GHz, T_D = 1 / (10 * 0.81 GHz). [Razavi-PLL]
# Sec. 1.6, p. 27: K_VCO the slope of the frequency over the control, at 0.8 V dg/dV = 2 GHz/V; the
# metric's points 0.7 V and 0.9 V lie symmetric about it, where a central difference of a quadratic
# is exact. The duty cycle a sine's, 0.5 ([Razavi-PLL] Sec. 11.10, p. 365), to 1e-5 as above. A ring
# has no line's numbers (NaN). Tolerances: the frequencies' rel 1e-6, so K_VCO to rel 1e-5 (two
# frequencies near 1 GHz over 0.2 V); the current's rel 1e-3.
def test_a_controlled_rings_record() -> None:
    record = runs.results(ring_measurements(runs.ring5_starved()))
    assert set(record.metrics) == set(Metrics.__dataclass_fields__)
    values = record.metrics
    assert values["oscillation_frequency_hz"] == pytest.approx(1e9, rel=1e-6)
    assert values["swing_v"] == pytest.approx(1.1, abs=1e-4)
    assert values["duty_cycle"] == pytest.approx(0.5, abs=1e-5)
    assert values["stage_delay_s"] == pytest.approx(100e-12, rel=1e-6)
    assert values["average_power_w"] == pytest.approx(72e-6, rel=1e-3)
    assert values["energy_per_cycle_j"] == pytest.approx(72e-15, rel=1e-3)
    assert values["stage_delay_max_supply_s"] == pytest.approx(1 / (10 * 0.81e9), rel=1e-6)
    assert values["kvco_hz_per_v"] == pytest.approx(2e9, rel=1e-5)
    for name in ("delay_rise_s", "delay_fall_s", "rise_time_s", "fall_time_s", "kdl_s_per_v"):
        assert math.isnan(values[name])
    assert [plot.name for plot in record.details] == [
        "oscillation_frequency_supply",
        "stage_delay_supply",
        "energy_supply",
        "duty_cycle_supply",
        "oscillation_frequency_control",
        "kvco_control",
        "energy_control",
        "duty_cycle_control",
    ]
    assert all(isinstance(plot, Plot) for plot in record.details)
    assert record.waves == {"nominal": "supply_100"}


# The plotted K_VCO (kvco_control) at each control point against the slope of g: dg/dV = 2 GHz/V +
# 3 GHz/V^2 (V - 0.8 V), 1.1 GHz/V at 0.5 V to 3.2 GHz/V at 1.2 V. On the uniform 0.1 V sweep a
# central difference of a quadratic is exact, so the six inner points match to rel 1e-4 (frequency
# errors of rel 1e-6 over 0.2 V); at the nominal point the plot's and the metric's estimates are the
# same difference of the same two runs.
def test_the_vco_gain_curve_inside_the_sweep() -> None:
    record = runs.results(ring_measurements(runs.ring5_starved()))
    kvco = next(plot for plot in record.details if plot.name == "kvco_control")
    controls = np.asarray(kvco.x)
    assert controls == pytest.approx([0.5, 0.6, 0.7, 0.8, 0.9, 1.0, 1.1, 1.2])
    slope = 2e9 + 3e9 * (controls - 0.8)
    assert kvco.series["VCO gain"][1:-1] == pytest.approx(slope[1:-1].tolist(), rel=1e-4)
    nominal = CONTROL_SWEEP.index(NOMINAL_CONTROL)
    assert kvco.series["VCO gain"][nominal] == pytest.approx(record.metrics["kvco_hz_per_v"], rel=1e-9)


# The same curve at the sweep's ends, where the slope of g is 1.1 GHz/V (0.5 V) and 3.2 GHz/V
# (1.2 V). A second-order one-sided difference of a quadratic is exact, as the central one inside (a
# first-order one would be off by a h = 1.5 GHz/V^2 * 0.1 V = 0.15 GHz/V there, 14 % at 0.5 V).
def test_the_vco_gain_curve_at_the_sweeps_ends() -> None:
    record = runs.results(ring_measurements(runs.ring5_starved()))
    kvco = next(plot for plot in record.details if plot.name == "kvco_control")
    assert [kvco.series["VCO gain"][0], kvco.series["VCO gain"][-1]] == pytest.approx([1.1e9, 3.2e9], rel=1e-4)


def line_shapes(vdd: float, vcont_v: float) -> dict[str, float]:
    """The synthetic line's output: a transport delay (1.2 V / V_DD) (100 ps - 200 ps/V (V_cont -
    0.8 V) + 300 ps/V^2 (V_cont - 0.8 V)^2) and the time constants ``TAU_R`` and ``TAU_F``."""
    offset = vcont_v - 0.8
    return {
        "transport_s": 1.2 / vdd * (100e-12 - 200e-12 * offset + 300e-12 * offset**2),
        "tau_rise_s": TAU_R,
        "tau_fall_s": TAU_F,
    }


# The record of a controlled four-stage line whose output is line_shapes'. At 1.2 V and 0.8 V the
# transport delay is 100 ps: t_PLH = 100 ps + TAU_R ln 2, t_PHL = 100 ps + TAU_F ln 2, t_LH = TAU_R
# ln 9, t_HL = TAU_F ln 9 ([Baker] Fig. 10.9 and Eq. (10.17), (10.18), p. 333), the stage delay
# their mean over four; the slowest stage over the supply at 1.08 V, its transport 100 ps / 0.9.
# I_DD = 5 uA + 2 * 20 fC / 4 ns = 15 uA, P = 18 uW, 72 fJ an input cycle ([Baker] Eq. (11.15),
# p. 355). [Razavi-PLL] Sec. 11.1, p. 346: K_DL the delay's slope over the control (here in s/V), at
# 0.8 V -200 ps/V; the metric's points 0.7 V and 0.9 V are symmetric about it, where a central
# difference of a quadratic is exact. A line has no ring's numbers (NaN). Tolerances: each delay
# 0.2 ps, so the gain 2 * 0.2 ps / 0.2 V = 2 ps/V.
def test_a_controlled_lines_record() -> None:
    line = runs.chain4_starved()
    measurements = {
        f"supply_{round(factor * 100)}": line_run(
            TbParams(params=line, vdd=round(1.2 * factor, 4)), **line_shapes(round(1.2 * factor, 4), 0.8)
        )
        for factor in SUPPLY_SWEEP
    }
    for step in CONTROL_SWEEP:
        if not math.isclose(step, NOMINAL_CONTROL):
            tb = TbParams(params=line, vcont_v=round(1.2 * step, 4))
            measurements[f"control_{round(step * 12)}"] = line_run(tb, **line_shapes(1.2, tb.vcont_v))
    record = runs.results(measurements)
    values = record.metrics
    assert values["delay_rise_s"] == pytest.approx(100e-12 + TAU_R * LN2, abs=0.2e-12)
    assert values["delay_fall_s"] == pytest.approx(100e-12 + TAU_F * LN2, abs=0.2e-12)
    assert values["rise_time_s"] == pytest.approx(TAU_R * LN9, abs=0.2e-12)
    assert values["fall_time_s"] == pytest.approx(TAU_F * LN9, abs=0.2e-12)
    assert values["stage_delay_s"] == pytest.approx((100e-12 + (TAU_R + TAU_F) / 2 * LN2) / 4, abs=0.05e-12)
    slowest = (100e-12 / 0.9 + (TAU_R + TAU_F) / 2 * LN2) / 4
    assert values["stage_delay_max_supply_s"] == pytest.approx(slowest, abs=0.05e-12)
    assert values["average_power_w"] == pytest.approx(18e-6, rel=1e-3)
    assert values["energy_per_cycle_j"] == pytest.approx(72e-15, rel=1e-3)
    assert values["kdl_s_per_v"] == pytest.approx(-200e-12, abs=2e-12)
    for name in ("oscillation_frequency_hz", "swing_v", "duty_cycle", "kvco_hz_per_v"):
        assert math.isnan(values[name])
    assert [plot.name for plot in record.details] == [
        "delay_rise_supply",
        "delay_fall_supply",
        "stage_delay_supply",
        "energy_supply",
        "delay_rise_control",
        "delay_fall_control",
        "rise_time_control",
        "fall_time_control",
        "energy_control",
    ]


# A plain line has no control: its record holds no gain and no control plot.
def test_a_plain_lines_record_has_no_gain() -> None:
    line = runs.chain4()
    record = runs.results(
        {
            f"supply_{round(factor * 100)}": line_run(
                TbParams(params=line, vdd=round(1.2 * factor, 4)), **line_shapes(round(1.2 * factor, 4), 0.8)
            )
            for factor in SUPPLY_SWEEP
        }
    )
    assert math.isnan(record.metrics["kdl_s_per_v"]) and math.isnan(record.metrics["kvco_hz_per_v"])
    assert [plot.name for plot in record.details] == [
        "delay_rise_supply",
        "delay_fall_supply",
        "stage_delay_supply",
        "energy_supply",
    ]


# metrics() takes the control's gain from the two runs at GAIN_POINTS, either side of the nominal: a
# line whose mean delay is linear in the control, -100 ps/V, reads that slope whatever the other
# points hold (here the sweep's ends far off the line), to 2 ps/V as above.
def test_the_gain_reads_only_the_points_either_side_of_the_nominal() -> None:
    line = runs.chain4_starved()
    by_supply = [line_run(TbParams(params=line, vdd=round(1.2 * f, 4)), **line_shapes(1.2, 0.8)) for f in SUPPLY_SWEEP]
    by_control = []
    for step in CONTROL_SWEEP:
        vcont = round(1.2 * step, 4)
        near = any(math.isclose(step, p) for p in (*GAIN_POINTS, NOMINAL_CONTROL))
        transport = 100e-12 - 100e-12 * (vcont - 0.8) if near else 400e-12
        by_control.append(
            line_run(TbParams(params=line, vcont_v=vcont), transport_s=transport, tau_rise_s=TAU_R, tau_fall_s=TAU_F)
        )
    values = metrics(supply=analyze_propagation(by_supply), control=analyze_propagation(by_control))
    assert values.kdl_s_per_v == pytest.approx(-100e-12, abs=2e-12)
    assert math.isnan(values.kvco_hz_per_v)


# A ring that stops at the lowest supply (its output flat) has no stage delay there, unbounded: the
# slowest over the supply is not the slower of the two that ran. The metric must not be finite (NaN,
# no such number), or a search minimizing it would prefer a ring that fails at 90 % of the supply.
def test_the_slowest_stage_over_the_supply_counts_a_point_that_failed() -> None:
    ring = runs.ring5()
    supply = []
    for factor in SUPPLY_SWEEP:
        tb = TbParams(params=ring, vdd=round(1.2 * factor, 4))
        measured = ring_run(tb, ring_frequency_hz(tb.vdd, 0.8))
        if factor < 1:
            measured = replace(measured, v={**measured.v, "outp": np.zeros_like(measured.time_s)})
        supply.append(measured)
    values = metrics(supply=analyze_oscillation(supply))
    assert values.stage_delay_s == pytest.approx(100e-12, rel=1e-6)
    assert not math.isfinite(values.stage_delay_max_supply_s)


# A line's supply point that is not valid has no finite worst case either: the 90 % run's output is
# too slow to settle (tau = 1.5 ns on a 2 ns half period, as in the line that never settles), so its
# delays exist but its transitions do not, and it is not valid. The slowest stage delay over the
# supply is NaN, not the largest of the finite ones (that very point's, the longest).
def test_the_slowest_stage_over_the_supply_counts_a_line_point_not_valid() -> None:
    line = runs.chain4()
    supply = [
        line_run(
            TbParams(params=line, vdd=round(1.2 * factor, 4)),
            transport_s=D0,
            tau_rise_s=1.5e-9 if factor < 1 else TAU_R,
            tau_fall_s=1.5e-9 if factor < 1 else TAU_F,
        )
        for factor in SUPPLY_SWEEP
    ]
    analysed = analyze_propagation(supply)
    assert analysed.valid.tolist() == [False, True, True] and np.isfinite(analysed.stage_delay_s).all()
    assert math.isnan(metrics(supply=analysed).stage_delay_max_supply_s)


# K_VCO over the timed points alone ([Razavi-PLL] Fig. 3.27, p. 84: the tuning curve's local slope).
# A linear curve f = 1 GHz + 2 GHz/V (V_cont - 0.8 V) has slope 2 GHz/V at every point, so any
# difference over timed points gives it exactly: a ring stopped at 0.5 V reads NaN there alone, its
# neighbour 0.6 V the one-sided 2 GHz/V; stopped at 0.8 V, NaN there alone, 0.7 and 0.9 V one-sided;
# stopped at 0.6 and 0.8 V, the timed 0.5 and 0.7 V beside them have no timed neighbour, NaN.
# Tolerance rel 1e-9.
def test_the_vco_gain_skips_the_points_not_timed() -> None:
    controls = np.asarray(CONTROL_SWEEP) * 1.2
    for stopped, expected_nan in (((0,), [0]), ((3,), [3]), ((1, 3), [0, 1, 2, 3])):
        frequency = 1e9 + 2e9 * (controls - 0.8)
        frequency[list(stopped)] = np.nan
        result = AnalysisOscillation(
            group=None,
            index=None,
            dut=runs.ring5_starved(),
            vdd_v=np.full(len(controls), 1.2),
            vcont_v=controls,
            oscillation_frequency_hz=frequency,
            idd_a=np.full(len(controls), 50e-6),
            swing_v=np.full(len(controls), 1.2),
            duty_cycle=np.full(len(controls), 0.5),
            oscillation=tuple(Oscillation.STOPPED if k in stopped else Oscillation.TIMED for k in range(len(controls))),
        )
        gain = result.kvco_hz_per_v
        assert np.flatnonzero(np.isnan(gain)).tolist() == expected_nan
        assert np.delete(gain, expected_nan) == pytest.approx(2e9, rel=1e-9)


# A line's stage delay is its delays over 2N ([Baker] Eq. (11.22), p. 360), so it carries their
# direction ("none": a line's delay is a target, not a figure to push); the power and energy say whose
# supply and, for a line, that the bench's input clock sets them ([Baker] Eq. (11.15), p. 355).
def test_a_lines_stage_delay_carries_its_delays_direction() -> None:
    better = pipeline.betters(Metrics)
    assert better["stage_delay_s"] == better["stage_delay_max_supply_s"] == better["delay_rise_s"] == "none"
    described = {field.name: field.metadata["desc"] for field in dataclasses.fields(Metrics)}
    assert "input clock" in described["average_power_w"] and "input clock" in described["energy_per_cycle_j"]
    assert "chain's supply" in described["average_power_w"]
