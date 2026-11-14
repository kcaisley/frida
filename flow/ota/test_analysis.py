"""The amplifier's analyses and metrics validated on synthetic runs whose answers are known in
closed form, as a run's measurement (``flow.pipeline.Meas``) reads: one-, two- and three-pole
responses on the simulator's logarithmic sweep, rejections from known transfer functions, white and
flicker noise densities, operating points of known saturation margins, slewing ramps, single-pole
and second-order step responses on a non-uniform time axis, and a polynomial nonlinearity's
harmonics. Each expected value is derived
in the comment above its test, never from the code under test; the record is checked last."""

from __future__ import annotations

import math
from dataclasses import replace
from datetime import UTC, datetime

import numpy as np
import pytest

from flow.pipeline import Meas, MeasInfo, Plot, Sweep, SweepKind

from . import runs as block_runs
from .analysis import analyze_ac, analyze_distortion, analyze_noise, analyze_range, analyze_slew, metrics
from .params import CM_SWEEP, SINE_STROBE_S, Bench, Params, TbParams, Topology
from .types import AnalysisAc, AnalysisDistortion, AnalysisNoise, AnalysisRange, AnalysisSlew, Metrics

INFO = MeasInfo(backend="spice", timestamp_utc=datetime(2026, 10, 17, tzinfo=UTC))


# ---- synthetic measurements


def sweep_hz(start_decade: float = 3.0) -> np.ndarray:
    """The small-signal bench's sweep as Spectre writes it: 1 kHz to 100 GHz, twenty points a decade."""
    return np.logspace(start_decade, start_decade + 8, 161)


def poles(frequency_hz: np.ndarray, gain: float, *poles_hz: float) -> np.ndarray:
    """A0 / prod(1 + j f / p_k): an amplifier of low-frequency gain ``gain`` and real poles ``poles_hz``."""
    response = np.full(frequency_hz.shape, complex(gain))
    for pole_hz in poles_hz:
        response = response / (1 + 1j * frequency_hz / pole_hz)
    return response


def small_signal(
    tb: TbParams,
    response: np.ndarray,
    *,
    frequency_hz: np.ndarray | None = None,
    gain_diff: np.ndarray | None = None,
    gain_cm: np.ndarray | None = None,
    gain_supply: np.ndarray | None = None,
    gain_reference: np.ndarray | None = None,
    noise_in_v_per_rthz: np.ndarray | None = None,
    vbp: float = 0.5,
    vout_v: tuple[float, float] = (0.6, 0.6),
    idd_a: float = 50e-6,
    iss_a: float = 40e-6,
    margins: dict[str, float] | None = None,
    devices: dict[str, tuple[float, float]] | None = None,
    gain_vcm: dict[str, np.ndarray] | None = None,
) -> Meas:
    """A small-signal run of ``tb``: the differential AC ``response`` (split between outp and outn
    for a differential amplifier), the input common mode at ``tb.vin_cm_v`` (0.6 V at the nominal
    point); at outp the differential gain ``gain_diff`` (the response unless given), the
    common-mode gain ``gain_cm``, and the gains from the amplifier's supply ``gain_supply`` and the
    bias network's ``gain_reference`` (as ``xf`` holds them: per volt on each source); an
    input-referred noise density (white 10 nV/sqrt(Hz) unless given) times the response's magnitude
    at the output, the load bias at ``vbp``, the outputs at ``vout_v``, the supply drawing
    ``idd_a`` and the tail ``iss_a``, and each device's V_DS that far above its V_D,sat of 0.15 V
    (``margins``: 0.1 V for the tail, the input pair and the load unless given), or each device's
    (V_DS, V_D,sat) as given in ``devices``, signed as a PMOS's are; and, where ``gain_vcm`` gives
    them, the gains from the supplies to the input common mode the inputs ride on (``xf_vcm``, per
    volt on each source)."""
    frequency_hz = sweep_hz() if frequency_hz is None else frequency_hz
    flat = np.ones(frequency_hz.shape, dtype=np.complex128)
    gain_diff = response if gain_diff is None else gain_diff
    gain_cm = 0.01 * flat if gain_cm is None else gain_cm
    gain_supply = 0.1 * flat if gain_supply is None else gain_supply
    gain_reference = 0.0 * flat if gain_reference is None else gain_reference
    density = np.full(frequency_hz.shape, 10e-9) if noise_in_v_per_rthz is None else noise_in_v_per_rthz
    outputs = {"outp": response} if tb.single_ended else {"outp": response / 2, "outn": -response / 2}
    operating = {"outp": np.asarray([vout_v[0]])} | ({} if tb.single_ended else {"outn": np.asarray([vout_v[1]])})
    margins = dict.fromkeys(("Mtail", "Min_p", "Min_n", "Mload"), 0.1) if margins is None else margins
    if devices is None:
        devices = {device: (0.15 + margin, 0.15) for device, margin in margins.items()}
    operating_point = {
        f"{device}:{value}": np.asarray([level])
        for device, levels in devices.items()
        for value, level in zip(("vds", "vdsat"), levels, strict=True)
    }
    tails = {f"{device}:ids": np.asarray([iss_a]) for device in devices if device.startswith("Mtail")}
    vin_cm_v = 0.6 if tb.vin_cm_v is None else tb.vin_cm_v
    return Meas(
        group=None,
        index=None,
        dut=tb.params,
        info=INFO,
        param=tb,
        sweeps={
            "ac": Sweep(kind=SweepKind.AC, x=frequency_hz, v=outputs),
            # outp = a vinp + b vinn: with vinp = vcm + vd/2 and vinn = vcm - vd/2 the differential
            # gain is (a - b)/2 and the common mode's a + b, so a = Ad + Acm/2 and b = -Ad + Acm/2
            "xf": Sweep(
                kind=SweepKind.XF,
                x=frequency_hz,
                v={
                    "inp": gain_diff + gain_cm / 2,
                    "inn": -gain_diff + gain_cm / 2,
                    "vdd": gain_supply,
                    "vddb": gain_reference,
                },
            ),
            "noise": Sweep(kind=SweepKind.NOISE, x=frequency_hz, v={"out": density * np.abs(response)}),
            **({} if gain_vcm is None else {"xf_vcm": Sweep(kind=SweepKind.XF, x=frequency_hz, v=gain_vcm)}),
            "opdc": Sweep(
                kind=SweepKind.OP,
                x=np.zeros(0),
                v={"vbp": np.asarray([vbp]), "inp": np.asarray([vin_cm_v])} | operating | operating_point | tails,
                i={"vdd": np.asarray([idd_a])},
            ),
        },
    )


def simulator_time(stop_s: float, breakpoints: tuple[float, ...], *, largest_s: float, seed: int = 0) -> np.ndarray:
    """A transient's own time axis: random steps of up to ``largest_s`` (an eighth of it at least),
    a point at each of ``breakpoints`` and at the stop."""
    rng = np.random.default_rng(seed)
    steps = rng.uniform(largest_s / 8, largest_s, size=int(4 * stop_s / largest_s) + 8)
    time_s = np.cumsum(np.r_[0.0, steps])
    return np.unique(np.r_[time_s[time_s < stop_s], breakpoints, stop_s])


def transient(
    tb: TbParams, time_s: np.ndarray, outp: np.ndarray, idd_a: np.ndarray | None = None, inp: np.ndarray | None = None
) -> Meas:
    """A unity-gain run of ``tb``: ``outp`` over ``time_s``, the input ``inp`` (the output unless
    given, as a buffer's), the supply drawing ``idd_a`` (30 uA unless given)."""
    idd_a = np.full(time_s.shape, 30e-6) if idd_a is None else idd_a
    inp = outp if inp is None else inp
    return Meas(
        group=None,
        index=None,
        dut=tb.params,
        info=INFO,
        param=tb,
        time_s=time_s,
        v={"outp": outp, "inp": inp},
        i={"vdd": idd_a},
    )


def step_tb() -> TbParams:
    """The unity-gain step bench: 20 ns period, 10 ps edges, the input up at 5 ns and down at 15 ns."""
    return TbParams(bench=Bench.STEP, vin_step_v=0.3)


def step_time(tb: TbParams, corners: tuple[float, ...] = ()) -> np.ndarray:
    """The step bench's time axis: steps of up to 8 ps, points at the input's edge corners and at
    the output's own ``corners``."""
    period, edge = tb.step_period_s, tb.transition_time_s
    edges = (period / 4, period / 4 + edge, 3 * period / 4, 3 * period / 4 + edge)
    return simulator_time(period, (*edges, *corners), largest_s=8e-12)


def exponential(time_s: np.ndarray, start_s: float, initial: float, final: float, tau_s: float) -> np.ndarray:
    """A single-pole step from ``initial`` to ``final`` beginning at ``start_s``, time constant ``tau_s``."""
    return final + (initial - final) * np.exp(-np.maximum(time_s - start_s, 0.0) / tau_s)


def ramp(time_s: np.ndarray, start_s: float, initial: float, final: float, slope_v_per_s: float) -> np.ndarray:
    """A slewing edge: from ``initial`` at ``start_s`` toward ``final`` at ``slope_v_per_s``, then flat."""
    rising = final > initial
    moved = initial + (slope_v_per_s if rising else -slope_v_per_s) * np.maximum(time_s - start_s, 0.0)
    return np.minimum(moved, final) if rising else np.maximum(moved, final)


def sine_tb() -> TbParams:
    """The unity-gain sine bench: 0.12 V at 10 MHz, ten periods, a record every 100 ps."""
    return TbParams(bench=Bench.SINE, vin_amplitude_v=0.12, waveform_sample_interval_s=SINE_STROBE_S)


def polynomial_run(tb: TbParams, alpha: tuple[float, float, float], time_s: np.ndarray) -> Meas:
    """The output of a memoryless nonlinearity y = a1 x + a2 x^2 + a3 x^3 about 0.6 V, of the input
    sine x = A sin(2 pi f t) about 0.6 V, on ``time_s``."""
    x = tb.vin_amplitude_v * np.sin(2 * np.pi * tb.vin_frequency_hz * time_s)
    return transient(tb, time_s, 0.6 + alpha[0] * x + alpha[1] * x**2 + alpha[2] * x**3, inp=0.6 + x)


def row(value: float) -> np.ndarray:
    """One point's value as a result's array."""
    return np.asarray([value], dtype=np.float64)


# ---- closed forms (each derived in its docstring, independent of flow.analysis.calc)


def two_pole_unity_gain_hz(gain: float, pole_hz: float, second_hz: float) -> float:
    """Where |A0 / ((1 + j f/p1)(1 + j f/p2))| = 1: (1 + s/p1^2)(1 + s/p2^2) = A0^2 with s = f^2 is
    the quadratic s^2/(p1 p2)^2 + s (1/p1^2 + 1/p2^2) + 1 - A0^2 = 0, of one positive root."""
    a, b, c = 1 / (pole_hz * second_hz) ** 2, 1 / pole_hz**2 + 1 / second_hz**2, 1 - gain**2
    return math.sqrt((-b + math.sqrt(b * b - 4 * a * c)) / (2 * a))


def two_pole_bandwidth_hz(pole_hz: float, second_hz: float) -> float:
    """Where the two-pole gain is 1/sqrt(2) of A0: (1 + x^2)(1 + r^2 x^2) = 2 with x = f/p1 and
    r = p1/p2 is r^2 s^2 + (1 + r^2) s - 1 = 0 in s = x^2."""
    r2 = (pole_hz / second_hz) ** 2
    return pole_hz * math.sqrt((-(1 + r2) + math.sqrt((1 + r2) ** 2 + 4 * r2)) / (2 * r2))


def phase_lost_deg(frequency_hz: float | np.ndarray, *poles_hz: float) -> np.ndarray:
    """The phase a response of real left-half-plane poles has lost at ``frequency_hz``: sum of atan(f/p)."""
    return np.degrees(sum(np.arctan(np.asarray(frequency_hz) / pole_hz) for pole_hz in poles_hz))


# ---- analyze_ac: gain, bandwidths, margins
#
# Tolerances of a crossing: the calculator interpolates the gain in dB (and the phase) linearly in
# log frequency between Spectre's points, h = 0.05 decade apart. A linear interpolant errs by at
# most |g''| h^2/8. A pole's gain -10 log10(1 + y), y = (f/p)^2, bends by |g''| = 40 ln(10) y/(1 + y)^2
# dB/decade^2, at most 23 dB/decade^2 (at y = 1); its phase atan(f/p) by ln(10)^2 x (1 - x^2)/(1 +
# x^2)^2 rad/decade^2 at x = f/p, at most ln(10)^2/4 = 1.33 rad/decade^2 (76 deg/decade^2). Divided by
# the slope at the crossing, these bound each tolerance below.


# A two-pole amplifier, A0 = 20 (26.02 dB), p1 = 13 MHz, p2 = 400 MHz, sampled as Spectre samples.
# Low-frequency gain ([Razavi-Analog] Sec. 6.7.1, p. 204): the gain at the lowest point, 1 kHz,
#   20 log10(A0) less 10 log10(1 + (1e3/13e6)^2) = 2.6e-8 dB: abs = 1e-6 dB.
# Unity-gain bandwidth ([Razavi-Analog] Eq. (6.101), p. 204, with the second pole's factor): the
#   quadratic's root (two_pole_unity_gain_hz), 226.0 MHz. The gain falls 25 dB/decade there and
#   bends 17 dB/decade^2: 5.3e-3 dB, 2.1e-4 decade, 4.9e-4 relative; rel = 1e-3.
# Phase margin ([Razavi-Analog] Sec. 10.3, p. 417): PM = 180 + angle H(fu) = 180 - atan(fu/p1) -
#   atan(fu/p2) = 180 - 86.7 - 29.5 = 63.8 deg. The phase falls 0.99 rad/decade at fu, so the
#   crossing's 2.1e-4 decade is 0.012 deg and the phase's own interpolation at most 0.024 deg,
#   0.036 deg in all: abs = 0.05 deg.
# -3 dB bandwidth ([Razavi-Analog] Fig. 6.43, p. 204): the root of two_pole_bandwidth_hz, 12.99 MHz;
#   there the gain falls 10 dB/decade and bends 23 dB/decade^2: 7.2e-3 dB, 7.2e-4 decade, 1.7e-3
#   relative; rel = 2e-3.
# Gain-bandwidth product ([Razavi-Analog] Eq. (6.98), p. 204): A0 times the -3 dB bandwidth, its
#   tolerance the bandwidth's.
# Gain and phase over frequency: 20 log10 |H| and -sum atan(f/p) at each point, exactly.
# Gain margin: two poles never turn the phase 180 degrees, so there is none (NaN).
def test_a_two_pole_amplifier_reads_its_closed_form_figures() -> None:
    frequency_hz = sweep_hz()
    result = analyze_ac([small_signal(TbParams(), poles(frequency_hz, 20.0, 13e6, 400e6))])
    assert result.gain_dc_db[0] == pytest.approx(20 * math.log10(20.0), abs=1e-6)
    unity_hz = two_pole_unity_gain_hz(20.0, 13e6, 400e6)
    assert result.unity_gain_bandwidth_hz[0] == pytest.approx(unity_hz, rel=1e-3)
    assert result.phase_margin_deg[0] == pytest.approx(180 - phase_lost_deg(unity_hz, 13e6, 400e6), abs=0.05)
    bandwidth_hz = two_pole_bandwidth_hz(13e6, 400e6)
    assert result.bandwidth_hz[0] == pytest.approx(bandwidth_hz, rel=2e-3)
    assert result.gbw_hz[0] == pytest.approx(20.0 * bandwidth_hz, rel=2e-3)
    assert np.isnan(result.gain_margin_db[0])
    expected_db = -10 * np.log10((1 + (frequency_hz / 13e6) ** 2) * (1 + (frequency_hz / 400e6) ** 2))
    np.testing.assert_allclose(result.gain_db[0], 20 * math.log10(20.0) + expected_db, atol=1e-9)
    np.testing.assert_allclose(result.phase_deg[0], -phase_lost_deg(frequency_hz, 13e6, 400e6), atol=1e-9)


# A one-pole amplifier, A0 = 1000, p = 1.3 MHz ([Razavi-Analog] Eq. (6.102), p. 204):
#   fu = sqrt(A0^2 - 1) p = 1.29999935 GHz; a pole alone sets the -3 dB bandwidth, p
#   ([Razavi-Analog] Sec. 6.7.1, p. 204), and GBW = A0 p = 1.3 GHz (Eq. (6.98)).
# Tolerances: at fu the gain falls 20 dB/decade and bends 9e-5 dB/decade^2 (fu/p = 1000), so fu is
#   good to 1e-5; rel = 1e-4. At p the gain bends 23 dB/decade^2 at its 10 dB/decade slope: 1.7e-3
#   relative; rel = 2e-3. The lowest point lies 2.6e-6 dB below A0: abs = 1e-5 dB.
def test_a_one_pole_amplifier_reads_its_closed_form_figures() -> None:
    result = analyze_ac([small_signal(TbParams(), poles(sweep_hz(), 1000.0, 1.3e6))])
    assert result.gain_dc_db[0] == pytest.approx(60.0, abs=1e-5)
    assert result.unity_gain_bandwidth_hz[0] == pytest.approx(math.sqrt(1000.0**2 - 1) * 1.3e6, rel=1e-4)
    assert result.bandwidth_hz[0] == pytest.approx(1.3e6, rel=2e-3)
    assert result.gbw_hz[0] == pytest.approx(1000.0 * 1.3e6, rel=2e-3)


# A dominant pole near the sweep's start: A0 = 1e4, p1 = 5 kHz, p2 = 100 MHz.
# Phase margin ([Razavi-Analog] Sec. 10.3, p. 417): PM = 180 + angle H(fu), the phase counted from
#   DC: fu = 45.51 MHz (two_pole_unity_gain_hz), PM = 180 - atan(fu/5e3) - atan(fu/1e8) = 65.54 deg.
#   At the lowest point (1 kHz) the response has already lost atan(1e3/5e3) = 11.3 deg, which the
#   margin keeps (a margin from the phase relative to that point would read 76.8 deg). Tolerance:
#   the gain falls 23 dB/decade at fu and bends 13 dB/decade^2 (1.8e-4 decade, 0.009 deg at 50
#   deg/decade), the phase's own interpolation 0.024 deg: abs = 0.05 deg.
def test_the_phase_margin_counts_the_phase_lost_below_the_sweep() -> None:
    result = analyze_ac([small_signal(TbParams(), poles(sweep_hz(), 1e4, 5e3, 100e6))])
    unity_hz = two_pole_unity_gain_hz(1e4, 5e3, 100e6)
    assert result.unity_gain_bandwidth_hz[0] == pytest.approx(unity_hz, rel=1e-3)
    assert result.phase_margin_deg[0] == pytest.approx(180 - phase_lost_deg(unity_hz, 5e3, 100e6), abs=0.05)


# Three equal poles p: the phase reaches -180 deg where 3 atan(f/p) = 180 deg, f180 = p tan(60 deg)
#   = sqrt(3) p, and there |H| = A0/(1 + 3)^(3/2) = A0/8. The gain margin ([Baker] Sec. 24.1, p. 810:
#   how far below unity the gain is where the phase has turned 180 deg) is -20 log10(A0/8): +6.02 dB
#   for A0 = 4 (stable), -21.94 dB for A0 = 100 (the loop gain exceeds unity there).
#   The phase margin ([Razavi-Analog] Sec. 10.3, p. 417) of A0 = 4: |H| = 1 at (1 + x^2)^3 = 16,
#   x = f/p = sqrt(16^(1/3) - 1) = 1.2328, PM = 180 - 3 atan(x) = 27.14 deg; of A0 = 100, x = 4.53
#   and PM = 180 - 3 x 77.6 = -52.7 deg.
# Tolerances, p = 13 MHz: at f180 the phase falls 171 deg/decade and bends at most 228 deg/decade^2
#   (0.071 deg, 4.2e-4 decade), the gain falls 45 dB/decade there (0.019 dB) and bends 52
#   dB/decade^2 (0.016 dB); with the 0.013 deg the poles lose below 1 kHz (0.003 dB), abs = 0.05 dB.
#   At fu the gain falls 36 dB/decade and bends 66 dB/decade^2 (0.021 dB, 5.7e-4 decade, 1.3e-3
#   relative: rel = 2e-3), the phase falls 194 deg/decade: 0.11 deg, with its own interpolation and
#   the 0.013 deg 0.19 deg; abs = 0.2 deg.
def test_three_equal_poles_read_their_gain_and_phase_margins() -> None:
    frequency_hz = sweep_hz()
    stable = analyze_ac([small_signal(TbParams(), poles(frequency_hz, 4.0, 13e6, 13e6, 13e6))])
    assert stable.gain_margin_db[0] == pytest.approx(20 * math.log10(8 / 4), abs=0.05)
    x = math.sqrt(16 ** (1 / 3) - 1)
    assert stable.unity_gain_bandwidth_hz[0] == pytest.approx(x * 13e6, rel=2e-3)
    assert stable.phase_margin_deg[0] == pytest.approx(180 - 3 * math.degrees(math.atan(x)), abs=0.2)
    unstable = analyze_ac([small_signal(TbParams(), poles(frequency_hz, 100.0, 13e6, 13e6, 13e6))])
    assert unstable.gain_margin_db[0] == pytest.approx(-20 * math.log10(100 / 8), abs=0.05)
    assert unstable.phase_margin_deg[0] < 0


# The same three poles at 5 kHz, near the sweep's start: f180 = sqrt(3) x 5 kHz = 8.66 kHz and the
#   gain margin of A0 = 4 is still +6.02 dB ([Baker] Sec. 24.1, p. 810). At 1 kHz the poles have
#   already lost 3 atan(0.2) = 33.9 deg, so a phase taken relative to that point turns 180 deg only
#   where 3 atan(f/p) = 213.9 deg, f = tan(71.3 deg) p = 2.95 p, where the gain is 4/(1 + 2.95^2)^1.5,
#   17.6 dB below unity; the margin keeps the phase turned below the sweep and reads +6.02 dB.
#   Tolerance as at 13 MHz: abs = 0.05 dB.
def test_the_gain_margin_counts_the_phase_lost_below_the_sweep() -> None:
    result = analyze_ac([small_signal(TbParams(), poles(sweep_hz(), 4.0, 5e3, 5e3, 5e3))])
    assert result.gain_margin_db[0] == pytest.approx(20 * math.log10(8 / 4), abs=0.05)


# A two-stage amplifier's output, -H: its second stage inverts ([Razavi-Analog] Eq. (3.10), p. 48, a
#   common-source stage's -g_m R_D), so its polarity is taken off and its gain, phase and every
#   figure read as H's: the phase -sum atan(f/p) exactly, the margin counted from DC (an inverting
#   amplifier in negative feedback).
def test_a_two_stage_output_reads_as_the_same_amplifier() -> None:
    frequency_hz = sweep_hz()
    response = poles(frequency_hz, 20.0, 13e6, 400e6)
    upright = analyze_ac([small_signal(TbParams(params=Params(topology=Topology.TELESCOPIC)), response)])
    tb = TbParams(params=Params(topology=Topology.TELESCOPIC, two_stage=True))
    inverted = analyze_ac([small_signal(tb, -response)])
    np.testing.assert_allclose(inverted.phase_deg[0], -phase_lost_deg(frequency_hz, 13e6, 400e6), atol=1e-9)
    np.testing.assert_allclose(inverted.gain_db[0], upright.gain_db[0], atol=1e-12)
    assert inverted.unity_gain_bandwidth_hz[0] == pytest.approx(upright.unity_gain_bandwidth_hz[0], rel=1e-12)
    assert inverted.phase_margin_deg[0] == pytest.approx(upright.phase_margin_deg[0], abs=1e-9)


# A one-stage amplifier's polarity is its topology's, not the sign its response has at the lowest
#   frequency: A0 = 1e5 with two poles below the sweep, p1 = 100 Hz and p2 = 200 Hz, has lost
#   atan(10) + atan(5) = 163.0 deg at 1 kHz, its real part negative there, and stays the
#   non-inverting amplifier it is: phase -sum atan(f/p) at every point (a response turned over by its
#   sign at 1 kHz would read +17.0 deg there and every margin 180 deg off). Unity-gain bandwidth: the
#   quadratic's root (two_pole_unity_gain_hz), 44.72 kHz; phase margin ([Razavi-Analog] Sec. 10.3,
#   p. 417) 180 - atan(fu/p1) - atan(fu/p2) = 0.384 deg. Tolerances: at fu = 447 p1 the gain falls
#   40 dB/decade and bends 2.3e-3 dB/decade^2 (7e-7 dB, 2e-8 decade), the phase bends 0.036
#   rad/decade^2 (6.4e-4 deg): rel = 1e-5, abs = 1e-3 deg. Two poles never turn the phase 180 deg:
#   no gain margin.
def test_a_response_turned_past_90_degrees_below_the_sweep_keeps_its_polarity() -> None:
    frequency_hz = sweep_hz()
    for tb in (TbParams(), TbParams(params=Params(topology=Topology.TELESCOPIC))):
        result = analyze_ac([small_signal(tb, poles(frequency_hz, 1e5, 100.0, 200.0))])
        np.testing.assert_allclose(result.phase_deg[0], -phase_lost_deg(frequency_hz, 100.0, 200.0), atol=1e-9)
        unity_hz = two_pole_unity_gain_hz(1e5, 100.0, 200.0)
        assert result.unity_gain_bandwidth_hz[0] == pytest.approx(unity_hz, rel=1e-5)
        assert result.phase_margin_deg[0] == pytest.approx(180 - phase_lost_deg(unity_hz, 100.0, 200.0), abs=1e-3)
        assert np.isnan(result.gain_margin_db[0])


# A single-ended point's levels from its bench and operating point: the supply ([Razavi-Analog]
#   Fig. 3.4, p. 48) the run's, 1.08 V; the input common mode ([Razavi-Analog] Sec. 4.2, p. 103)
#   inp's operating point, 0.45 V; the output level ([Razavi-Analog] Fig. 3.4, p. 48) outp's, 0.71 V,
#   and no differential output common mode (NaN); power ([Baker] Sec. 24.1, p. 805) 1.08 V x 31 uA
#   = 33.48 uW. Each exactly (rel = 1e-12).
def test_a_single_ended_point_reads_its_supply_input_common_mode_and_output_level() -> None:
    tb = TbParams(vdd=1.08, vin_cm_v=0.45)
    result = analyze_ac([small_signal(tb, poles(sweep_hz(), 20.0, 13e6), vout_v=(0.71, 0.71), idd_a=31e-6)])
    assert result.vdd_v[0] == pytest.approx(1.08, rel=1e-12)
    assert result.vin_cm_v[0] == pytest.approx(0.45, rel=1e-12)
    assert result.vout_v[0] == pytest.approx(0.71, rel=1e-12) and np.isnan(result.vout_cm_v[0])
    assert result.power_w[0] == pytest.approx(1.08 * 31e-6, rel=1e-12)


# A differential amplifier (telescopic): outp = H/2 and outn = -H/2, so outp - outn = H, the gain
#   A0 = 20 (26.02 dB) of the single-ended case. Output common mode ([Razavi-Analog] Sec. 4.2,
#   p. 103): the outputs' average, (0.62 + 0.58)/2 = 0.60 V; it has no single output level (NaN).
#   Power ([Baker] Sec. 24.1, p. 805): VDD x IDD = 1.2 V x 47 uA = 56.4 uW; the tail current as the
#   operating point holds it. Its rejections ([Razavi-Analog] Eq. (4.55), p. 123: A_DM over the
#   common mode's gain to the differential output, zero without mismatch) are NaN whatever the
#   transfer functions hold, and whatever the bench's feedback gain.
def test_a_differential_output_reads_as_the_difference_of_its_outputs() -> None:
    for gain in (100.0, 1000.0):
        tb = TbParams(params=Params(topology=Topology.TELESCOPIC), cmfb_gain=gain)
        run = small_signal(tb, poles(sweep_hz(), 20.0, 13e6, 400e6), vout_v=(0.62, 0.58), idd_a=47e-6, iss_a=39e-6)
        result = analyze_ac([run])
        assert result.gain_dc_db[0] == pytest.approx(20 * math.log10(20.0), abs=1e-6)
        assert result.vout_cm_v[0] == pytest.approx(0.60, abs=1e-12) and np.isnan(result.vout_v[0])
        assert result.idd_a[0] == pytest.approx(47e-6, rel=1e-12) and result.iss_a[0] == pytest.approx(39e-6, rel=1e-12)
        assert result.power_w[0] == pytest.approx(1.2 * 47e-6, rel=1e-12)
        assert np.isnan(result.psrr_dc_db[0]) and np.isnan(result.cmrr_dc_db[0])
        assert np.all(np.isnan(result.psrr_db[0])) and np.all(np.isnan(result.cmrr_db[0]))


# Rejections at a single output from the transfer functions: the differential gain there
#   Ad = 50/(1 + j f/2 MHz), the common mode's Acm = 0.02 (1 + j f/1 MHz), the amplifier supply's
#   Avdd = 0.06 (1 + j f/10 MHz) and the bias network supply's 0.04 (1 + j f/10 MHz).
# CMRR ([Razavi-Analog] Eq. (5.42), p. 157) = |Ad/Acm| and PSRR ([Razavi-Analog] Sec. 9.11, p. 400:
#   the gain from the input over the gain from the supply, the ripple on both supplies) =
#   |Ad/(Avdd + Avddb)| = |Ad|/|0.1 (1 + j f/10 MHz)|, in dB at each point exactly; at the lowest
#   point (1 kHz) the low-frequency ones, 20 log10(2500) = 67.96 dB and 20 log10(500) = 53.98 dB, less
#   what the poles and zeros take at 1 kHz (below 1e-5 dB). With the amplifier's supply alone the
#   PSRR would read 20 log10(50/0.06) = 58.4 dB.
def test_psrr_and_cmrr_are_the_differential_gain_over_the_supply_and_common_mode_gains() -> None:
    frequency_hz = sweep_hz()
    differential = 50 / (1 + 1j * frequency_hz / 2e6)
    common = 0.02 * (1 + 1j * frequency_hz / 1e6)
    supply = 0.1 * (1 + 1j * frequency_hz / 10e6)
    run = small_signal(
        TbParams(),
        poles(frequency_hz, 100.0, 2e6),
        gain_diff=differential,
        gain_cm=common,
        gain_supply=0.6 * supply,
        gain_reference=0.4 * supply,
    )
    result = analyze_ac([run])
    np.testing.assert_allclose(result.cmrr_db[0], 20 * np.log10(np.abs(differential) / np.abs(common)), atol=1e-9)
    np.testing.assert_allclose(result.psrr_db[0], 20 * np.log10(np.abs(differential) / np.abs(supply)), atol=1e-9)
    assert result.cmrr_dc_db[0] == pytest.approx(20 * math.log10(2500), abs=1e-5)
    assert result.psrr_dc_db[0] == pytest.approx(20 * math.log10(500), abs=1e-5)


# PSRR with the inputs held ([Razavi-Analog] Sec. 9.11, p. 400): the inputs ride on the nominal
#   input common mode, which the supplies move by a = dVcm/dVdd and b = dVcm/dVddb (xf_vcm). Each
#   source's transfer to outp (xf) holds the other sources but not the common mode, so a ripple v on
#   both supplies reaches outp as (Avdd + Avddb) v, of which (a + b) Acm v came through the inputs.
#   Holding them leaves Avdd + Avddb - (a + b) Acm, and
#   PSRR = |Ad| / |Avdd + Avddb - (a + b) Acm|, in dB at each point to 1e-9 dB.
#   Here the supplies' own path is s = 0.1 (1 + j f/10 MHz), split 0.6 s on vdd and 0.4 s on vddb,
#   and the common-mode path adds a Acm and b Acm with a = 0.1 and b = 0.4/(1 + j f/50 MHz); so the
#   held gain is s and PSRR = |Ad|/|s|: at 1 kHz 20 log10(50/0.1) = 53.98 dB (to 1e-5 dB, what the
#   poles and zeros take there), where the supplies' xf alone, |0.1 + 0.5 x 0.02| = 0.11, would read
#   20 log10(50/0.11) = 53.15 dB.
def test_psrr_holds_the_inputs_the_supplies_move_through_the_common_mode() -> None:
    frequency_hz = sweep_hz()
    differential = 50 / (1 + 1j * frequency_hz / 2e6)
    common = 0.02 * (1 + 1j * frequency_hz / 1e6)
    supply = 0.1 * (1 + 1j * frequency_hz / 10e6)
    a = 0.1 * np.ones(frequency_hz.shape, dtype=np.complex128)
    b = 0.4 / (1 + 1j * frequency_hz / 50e6)
    run = small_signal(
        TbParams(),
        poles(frequency_hz, 100.0, 2e6),
        gain_diff=differential,
        gain_cm=common,
        gain_supply=0.6 * supply + a * common,
        gain_reference=0.4 * supply + b * common,
        gain_vcm={"vdd": a, "vddb": b},
    )
    result = analyze_ac([run])
    held = 0.6 * supply + a * common + 0.4 * supply + b * common - (a + b) * common
    np.testing.assert_allclose(result.psrr_db[0], 20 * np.log10(np.abs(differential) / np.abs(held)), atol=1e-9)
    np.testing.assert_allclose(result.psrr_db[0], 20 * np.log10(np.abs(differential) / np.abs(supply)), atol=1e-9)
    assert result.psrr_dc_db[0] == pytest.approx(20 * math.log10(500), abs=1e-5)
    unheld = analyze_ac([replace(run, sweeps={k: v for k, v in run.sweeps.items() if k != "xf_vcm"})])
    assert unheld.psrr_dc_db[0] == pytest.approx(20 * math.log10(50 / 0.11), abs=1e-5)


# Saturation margins ([Razavi-Analog] Example 2.2, p. 18: saturated while |V_DS| >= |V_D,sat|):
#   each device's |V_DS| - |V_D,sat| from the operating point, a PMOS's both negative. A five-
#   transistor amplifier (NMOS input): Mtail 0.25 - 0.15 = 0.10, Min_p 0.40 - 0.12 = 0.28, Min_n
#   0.35 - 0.12 = 0.23, the PMOS diode Mload_d |-0.45| - |-0.20| = 0.25, the PMOS load Mload
#   |-0.30| - |-0.22| = 0.08: the least is the load's 0.08 V, the tail's and pair's 0.10 V (the
#   signed difference would read the load's -0.30 - (-0.22) as -0.08 V). With the load in triode,
#   |-0.12| - |-0.20| = -0.08 V (where |V_DS - V_D,sat| would read +0.08 V).
#   A self-biased amplifier: its tails' gates on the pair's drain, Mtail_n 0.05 - 0.15 = -0.10 and
#   Mtail_p |-0.04| - |-0.18| = -0.14 in triode, are left out, so the least are the input pairs':
#   Min_p_n 0.30 - 0.10 = 0.20, Min_n_n 0.27 - 0.10 = 0.17, Min_p_p |-0.33| - |-0.12| = 0.21,
#   Min_n_p |-0.29| - |-0.13| = 0.16: 0.16 V overall and for the pair alike. Exact to 1e-12 V.
def test_the_saturation_margins_are_the_least_v_ds_over_v_d_sat_of_the_devices_and_the_pair() -> None:
    response = poles(sweep_hz(), 20.0, 13e6, 400e6)
    five_t = {
        "Mtail": (0.25, 0.15),
        "Min_p": (0.40, 0.12),
        "Min_n": (0.35, 0.12),
        "Mload_d": (-0.45, -0.20),
        "Mload": (-0.30, -0.22),
    }
    triode = five_t | {"Mload": (-0.12, -0.20)}
    result = analyze_ac(
        [small_signal(TbParams(vin_cm_v=cm), response, devices=d) for cm, d in ((0.5, five_t), (0.6, triode))]
    )
    np.testing.assert_allclose(result.saturation_margin_v, [0.08, -0.08], atol=1e-12)
    np.testing.assert_allclose(result.saturation_margin_pair_v, [0.10, 0.10], atol=1e-12)
    self_biased = {
        "Mtail_n": (0.05, 0.15),
        "Mtail_p": (-0.04, -0.18),
        "Min_p_n": (0.30, 0.10),
        "Min_n_n": (0.27, 0.10),
        "Min_p_p": (-0.33, -0.12),
        "Min_n_p": (-0.29, -0.13),
    }
    tb = TbParams(params=Params(topology=Topology.SELF_BIASED))
    own = analyze_ac([small_signal(tb, response, devices=self_biased)])
    assert own.saturation_margin_v[0] == pytest.approx(0.16, abs=1e-12)
    assert own.saturation_margin_pair_v[0] == pytest.approx(0.16, abs=1e-12)


# Crossings outside the sweep:
#   A0 = 0.5: the gain never reaches unity, so no unity-gain bandwidth or phase margin (NaN); its
#   -3 dB bandwidth is still its pole, 1.3 MHz (rel = 2e-3 as above).
#   A0 = 1e6, p = 1 MHz: unity gain lies at 1e12 Hz, past the sweep's 100 GHz: NaN; the noise,
#   integrated over the sweep and not to the unity-gain bandwidth, still reads: a white 10 nV/sqrt(Hz)
#   through one pole, 10 nV sqrt(p (atan(1e5) - atan(1e-3))) = 12.53 uV referred to the input
#   (rel = 4e-3, the trapezoid's as in the noise test below).
#   A pole at 1 THz, past the sweep: no -3 dB point, so no bandwidth nor gain-bandwidth product.
def test_crossings_outside_the_sweep_read_as_absent() -> None:
    frequency_hz = sweep_hz()
    below = analyze_ac([small_signal(TbParams(), poles(frequency_hz, 0.5, 1.3e6))])
    assert np.isnan(below.unity_gain_bandwidth_hz[0]) and np.isnan(below.phase_margin_deg[0])
    assert below.bandwidth_hz[0] == pytest.approx(1.3e6, rel=2e-3)
    runs = [small_signal(TbParams(), poles(frequency_hz, 1e6, 1e6))]
    above = analyze_ac(runs)
    assert np.isnan(above.unity_gain_bandwidth_hz[0]) and np.isnan(above.phase_margin_deg[0])
    assert analyze_noise(runs, ac=above).noise_in_v[0] == pytest.approx(
        10e-9 * math.sqrt(1e6 * (math.atan(1e5) - math.atan(1e-3))), rel=4e-3
    )
    wide = analyze_ac([small_signal(TbParams(), poles(frequency_hz, 10.0, 1e12))])
    assert np.isnan(wide.bandwidth_hz[0]) and np.isnan(wide.gbw_hz[0])


# The load bias a differential amplifier's ideal feedback drives, which the bench holds between
#   the rails: a point whose vbp sits on a rail (0 V, or the 1.2 V supply) has lost its output and
#   has no figure (every one NaN), nor any noise; points between them (0.1 V and 1.1 V) keep every
#   figure. A single-ended amplifier has no feedback, its vbp a bias like any other.
def test_a_load_bias_beyond_the_rails_leaves_no_figure() -> None:
    response = poles(sweep_hz(), 20.0, 13e6, 400e6)
    telescopic = Params(topology=Topology.TELESCOPIC)
    runs = [
        small_signal(TbParams(params=telescopic, vin_cm_v=cm), response, vbp=vbp)
        for cm, vbp in ((0.4, 0.0), (0.5, 0.1), (0.6, 1.1), (0.7, 1.2))
    ]
    result = analyze_ac(runs)
    lost, kept = [0, 3], [1, 2]
    single = analyze_ac([small_signal(TbParams(vin_cm_v=0.4), response, vbp=0.0)])
    assert np.isfinite(single.gain_dc_db[0])
    for name in ("gain_dc_db", "unity_gain_bandwidth_hz", "phase_margin_deg", "bandwidth_hz", "gbw_hz", "iss_a"):
        values = getattr(result, name)
        assert np.all(np.isnan(values[lost])) and np.all(np.isfinite(values[kept])), name
    assert np.all(np.isnan(result.gain_db[lost])) and np.all(np.isnan(result.psrr_db[lost]))
    assert np.all(np.isnan(result.power_w[lost])) and np.all(np.isnan(result.vout_cm_v[lost]))
    assert np.all(np.isnan(result.saturation_margin_v[lost]))
    noise = analyze_noise(runs, ac=result)
    assert np.all(np.isnan(noise.noise_in_v_per_rthz[lost])) and np.all(np.isnan(noise.noise_in_v[lost]))
    assert np.all(np.isfinite(noise.noise_in_v[kept]))


# A sweep of one frequency has no response to read a bandwidth from, and points on different sweeps
#   cannot share the result's frequency axis: both are refused.
def test_a_single_frequency_or_mixed_sweeps_are_refused() -> None:
    one = np.asarray([1e6])
    with pytest.raises(ValueError):
        analyze_ac([small_signal(TbParams(), poles(one, 20.0, 13e6), frequency_hz=one)])
    shifted = sweep_hz(3.01)
    mixed = [
        small_signal(TbParams(), poles(sweep_hz(), 20.0, 13e6)),
        small_signal(TbParams(vin_cm_v=0.5), poles(shifted, 20.0, 13e6), frequency_hz=shifted),
    ]
    with pytest.raises(ValueError, match="one frequency sweep"):
        analyze_ac(mixed)


# ---- analyze_noise


# Noise of a one-pole amplifier, A0 = 20 and p = 13 MHz, its input-referred density e_n(f) with
#   e_n^2 = e_w^2 (1 + fc/f), white e_w = 8 nV/sqrt(Hz) and a flicker corner fc = 5 MHz
#   ([Razavi-Analog] Fig. 7.27, p. 235); the output density is e_n |H|.
# Input-referred density ([Razavi-Analog] Eq. (7.45), p. 238: the output's over the gain): e_n at
#   every point (to rounding: rel = 1e-12), at 1 MHz (a sweep point) 8 nV x sqrt(6) = 19.6 nV. The
#   output density ([Razavi-Analog] Sec. 7.1.1, p. 223) is the run's own, e_n |H|.
# Total output noise ([Razavi-Analog] Eq. (7.145), p. 264: the output density integrated), over the
#   sweep f0 = 1 kHz to f1 = 100 GHz: with |H|^2 = A0^2/(1 + (f/p)^2), the white part integrates to
#   e_w^2 A0^2 p (atan(f1/p) - atan(f0/p)) and the flicker part, 1/(f (1 + f^2/p^2)) having the
#   antiderivative ln f - ln(1 + f^2/p^2)/2, to e_w^2 A0^2 fc (ln(f1/f0) - ln((1 + f1^2/p^2)/(1 +
#   f0^2/p^2))/2).
# Total input-referred noise ([Razavi-Analog] Sec. 7.9, Eq. (7.147), p. 265): the total output noise
#   over A0 (the gain at 1 kHz, 1 - 3e-9 of A0).
# Tolerance: the trapezoid over points k = 10^(1/20) apart overestimates the integral of a 1/f^2 tail
#   by (k + 1/k)/2 - 1 = 0.75 % and of 1/f by (k - 1/k)/(2 ln k) - 1 = 0.22 %, is exact on the flat
#   part, and errs by (k - 1)^2/12 = 0.12 % about the pole: at most 0.75 % of the power, 0.38 % of
#   the RMS; rel = 4e-3.
def test_noise_integrates_the_output_and_refers_it_to_the_input_by_the_low_frequency_gain() -> None:
    frequency_hz = sweep_hz()
    density = 8e-9 * np.sqrt(1 + 5e6 / frequency_hz)
    f0, f1, pole_hz, corner_hz, gain = 1e3, 1e11, 13e6, 5e6, 20.0
    white = math.atan(f1 / pole_hz) - math.atan(f0 / pole_hz)
    flicker = math.log(f1 / f0) - math.log((1 + (f1 / pole_hz) ** 2) / (1 + (f0 / pole_hz) ** 2)) / 2
    power = 8e-9**2 * gain**2 * (pole_hz * white + corner_hz * flicker)
    for tb in (TbParams(), TbParams(params=Params(topology=Topology.TELESCOPIC))):
        runs = [small_signal(tb, poles(frequency_hz, gain, pole_hz), noise_in_v_per_rthz=density)]
        noise = analyze_noise(runs, ac=analyze_ac(runs))
        response = poles(frequency_hz, gain, pole_hz)
        np.testing.assert_allclose(noise.noise_out_v_per_rthz[0], density * np.abs(response), rtol=1e-12)
        np.testing.assert_allclose(noise.noise_in_v_per_rthz[0], density, rtol=1e-12)
        assert noise.spot_frequency_hz == pytest.approx(1e6, rel=1e-12)
        assert noise.noise_in_1mhz_v_per_rthz[0] == pytest.approx(8e-9 * math.sqrt(6.0), rel=1e-12)
        assert noise.noise_out_v[0] == pytest.approx(math.sqrt(power), rel=4e-3)
        assert noise.noise_in_v[0] == pytest.approx(math.sqrt(power) / gain, rel=4e-3)


# The spot value is at the sweep point nearest 1 MHz in log frequency: on a sweep starting at
#   10^3.01 Hz the points around 1 MHz are 10^5.96 and 10^6.01, so 10^6.01 Hz = 1.023 MHz, where a
#   white density of 10 nV/sqrt(Hz) reads 10 nV/sqrt(Hz).
def test_the_spot_noise_is_at_the_point_nearest_1_mhz() -> None:
    frequency_hz = sweep_hz(3.01)
    runs = [small_signal(TbParams(), poles(frequency_hz, 20.0, 13e6, 400e6), frequency_hz=frequency_hz)]
    noise = analyze_noise(runs, ac=analyze_ac(runs))
    assert noise.spot_frequency_hz == pytest.approx(10**6.01, rel=1e-9)
    assert noise.noise_in_1mhz_v_per_rthz[0] == pytest.approx(10e-9, rel=1e-12)


# The noise result belongs to the AC result of the same points in the same order, on its sweep.
def test_noise_of_other_points_than_the_ac_result_is_refused() -> None:
    response = poles(sweep_hz(), 20.0, 13e6, 400e6)
    ac = analyze_ac([small_signal(TbParams(), response)])
    with pytest.raises(ValueError, match="same points"):
        analyze_noise([small_signal(TbParams(vin_cm_v=0.5), response)], ac=ac)
    run = small_signal(TbParams(), response)
    shifted = Sweep(kind=SweepKind.NOISE, x=sweep_hz(3.01), v=run.sweeps["noise"].v)
    moved = Meas(group=None, index=None, dut=run.dut, info=INFO, param=run.tb, sweeps=run.sweeps | {"noise": shifted})
    with pytest.raises(ValueError, match="frequency sweep"):
        analyze_noise([moved], ac=ac)


# ---- analyze_slew
#
# The step bench: the input rises at 5 ns and falls at 15 ns with 10 ps edges; the output is
# measured from each edge's middle (5.005 ns, 15.005 ns), between the levels over the nanosecond
# before each edge (the rise settling to the one before the fall, the fall to the one before the
# rise, where the run starts), on a time axis of random steps of up to 8 ps with points at the
# input's edge corners.


# A slewing amplifier ([Razavi-Analog] Sec. 9.9, p. 391: the slope of the ramp): the output ramps
#   from 0.46 V to 0.74 V at 0.6 V/ns and back at 0.25 V/ns, each from its edge's middle. The
#   steepest slope between the 10 % and 90 % crossings of a ramp is its slope: +0.6 V/ns and
#   -0.25 V/ns. It is within 1 % of the 0.28 V step
#   ([Razavi-Analog] Eq. (9.11), p. 347) once it has moved 99 % of it: 0.99 x 0.28/0.6 = 0.462 ns and
#   0.99 x 0.28/0.25 = 1.109 ns. With points at the ramps' corners (as a simulator's step control
#   lands on them), every crossing lies on a straight part, read exactly: rel = 1e-6.
def test_a_slewing_ramp_reads_its_slope_and_settling() -> None:
    tb = step_tb()
    corners = (5.005e-9, 5.005e-9 + 0.28 / 0.6e9, 15.005e-9, 15.005e-9 + 0.28 / 0.25e9)
    time_s = step_time(tb, corners)
    rising = ramp(time_s, 5.005e-9, 0.46, 0.74, 0.6e9)
    output = np.where(time_s < 15.005e-9, rising, ramp(time_s, 15.005e-9, 0.74, 0.46, 0.25e9))
    slew = analyze_slew([transient(tb, time_s, output)])
    assert slew.vout_low_v[0] == pytest.approx(0.46, abs=1e-12)
    assert slew.vout_high_v[0] == pytest.approx(0.74, abs=1e-12)
    assert (slew.vin_low_v[0], slew.vin_high_v[0]) == pytest.approx((0.46, 0.74), abs=1e-12)
    assert (slew.vin_rise_s[0], slew.vin_fall_s[0]) == pytest.approx((5.005e-9, 15.005e-9), rel=1e-12)
    assert slew.slew_rate_rise_v_per_s[0] == pytest.approx(0.6e9, rel=1e-6)
    assert slew.slew_rate_fall_v_per_s[0] == pytest.approx(-0.25e9, rel=1e-6)
    assert slew.settling_rise_s[0] == pytest.approx(0.99 * 0.28 / 0.6e9, rel=1e-6)
    assert slew.settling_fall_s[0] == pytest.approx(0.99 * 0.28 / 0.25e9, rel=1e-6)
    assert slew.overshoot_rise[0] == 0.0 and slew.overshoot_fall[0] == 0.0
    np.testing.assert_array_equal(slew.time_s, time_s)
    np.testing.assert_array_equal(slew.vout_v[0], output)


# Linear settling ([Razavi-Analog] Eq. (9.61), p. 391): a single-pole closed loop's step response
#   V(t) = V_low + dV (1 - exp(-t/tau)), tau = 150 ps up and 400 ps down, dV = 0.28 V.
# Its slope dV/tau exp(-t/tau) ([Razavi-Analog] Eq. (9.58), p. 390) is steepest at the start of the
#   10-90 % span, where 10 % of the step has passed: 0.9 dV/tau, +1.68 V/ns and -0.630 V/ns.
# 1 % settling ([Razavi-Analog] Eq. (9.11), p. 347): t = tau ln 100, 0.691 ns and 1.842 ns.
# No overshoot: an exponential never passes its final level.
# Tolerance: the steepest secant is that of the interval holding the 10 % crossing, between the
#   slopes at its ends, within a factor exp(h/tau) of the slope there (h <= 8 ps): 5.5 % up and 2.0 %
#   down; rel = 6e-2 and 2.1e-2. A linear interpolant of the exponential errs by (h^2/8)/tau in time
#   at any level: 5e-14 s, 1e-4 of the settling time; rel = 1e-3.
def test_a_single_pole_step_reads_its_slope_and_settling() -> None:
    tb = step_tb()
    time_s = step_time(tb)
    rising = exponential(time_s, 5.005e-9, 0.46, 0.74, 150e-12)
    output = np.where(time_s < 15.005e-9, rising, exponential(time_s, 15.005e-9, 0.74, 0.46, 400e-12))
    slew = analyze_slew([transient(tb, time_s, output)])
    assert slew.slew_rate_rise_v_per_s[0] == pytest.approx(0.9 * 0.28 / 150e-12, rel=6e-2)
    assert slew.slew_rate_fall_v_per_s[0] == pytest.approx(-0.9 * 0.28 / 400e-12, rel=2.1e-2)
    assert slew.settling_rise_s[0] == pytest.approx(150e-12 * math.log(100), rel=1e-3)
    assert slew.settling_fall_s[0] == pytest.approx(400e-12 * math.log(100), rel=1e-3)
    assert slew.overshoot_rise[0] == 0.0 and slew.overshoot_fall[0] == 0.0


# A slewing edge that ends in linear settling, as a large step drives a single-pole loop
#   ([Razavi-Analog] Sec. 9.9, Fig. 9.71, p. 392): the output ramps at 0.6 V/ns until 0.1 V short of
#   0.74 V, then settles exponentially with tau = 1/6 ns, whose slope there, 0.1 V/tau, matches the
#   ramp's. The steepest slope between 10 % and 90 % is the ramp's, 0.6 V/ns (rel = 1e-6, the
#   corners on the axis); the 10-90 % average slope would read lower: 0.224 V over the ramp's
#   (0.64 - 0.488)/0.6 = 0.253 ns and the exponential's tau ln(0.1/0.028) = 0.212 ns, 0.481 V/ns.
def test_the_slew_rate_is_the_ramp_not_the_average_slope() -> None:
    tb = step_tb()
    knee_s = 5.005e-9 + 0.18 / 0.6e9
    time_s = step_time(tb, (5.005e-9, knee_s))
    tau = 0.1 / 0.6e9
    rising = np.where(
        time_s < knee_s, ramp(time_s, 5.005e-9, 0.46, 0.64, 0.6e9), exponential(time_s, knee_s, 0.64, 0.74, tau)
    )
    output = np.where(time_s < 15.005e-9, rising, exponential(time_s, 15.005e-9, 0.74, 0.46, 400e-12))
    slew = analyze_slew([transient(tb, time_s, output)])
    assert slew.slew_rate_rise_v_per_s[0] == pytest.approx(0.6e9, rel=1e-6)


# An underdamped second-order step, damping zeta = 0.5, natural frequency 1 GHz:
#   V(t) = V_low + dV (1 - exp(-zeta wn t) (cos(wd t) + zeta/sqrt(1 - zeta^2) sin(wd t))),
#   wd = wn sqrt(1 - zeta^2). Overshoot (not in the reference texts: how far a step response passes
#   its final level, a fraction of the step; for this response exp(-pi zeta/sqrt(1 - zeta^2)), the
#   standard second-order result) = exp(-pi/sqrt(3)) = 0.163, at t = pi/wd = 0.577 ns.
# Tolerance: the sampled maximum lies below the true one by at most |V''| h^2/8 <= dV wn^2 h^2/8 =
#   8.8e-5 V, 3.1e-4 of the step; abs = 1e-3.
def test_an_underdamped_step_reads_its_overshoot() -> None:
    tb = step_tb()
    time_s = step_time(tb)
    zeta, wn = 0.5, 2 * np.pi * 1e9
    wd = wn * math.sqrt(1 - zeta**2)
    t = np.maximum(time_s - 5.005e-9, 0.0)
    decay = np.exp(-zeta * wn * t) * (np.cos(wd * t) + zeta / math.sqrt(1 - zeta**2) * np.sin(wd * t))
    ringing = 0.46 + 0.28 * (1 - decay)
    output = np.where(time_s < 15.005e-9, ringing, exponential(time_s, 15.005e-9, 0.74, 0.46, 400e-12))
    slew = analyze_slew([transient(tb, time_s, output)])
    assert slew.overshoot_rise[0] == pytest.approx(math.exp(-math.pi * zeta / math.sqrt(1 - zeta**2)), abs=1e-3)
    assert slew.overshoot_fall[0] == 0.0


# Supply current ([Baker] Sec. 24.1, p. 805), averaged over time: 30 uA with a 20 uA pulse
#   from 5 to 7 ns (10 ps edges, trapezoidal: its area 20 uA x 2 ns) over the 20 ns period:
#   30 + 20 x 2/20 = 32 uA. The axis is four times denser inside the pulse, so a mean of the samples
#   would read about 36 uA. The pulse's corners are points of the axis, so the trapezoid integrates
#   it exactly: rel = 1e-9.
def test_the_supply_current_is_averaged_over_time() -> None:
    tb = step_tb()
    coarse = step_time(tb)
    dense = simulator_time(2e-9, (), largest_s=2e-12, seed=1) + 5e-9
    outside = coarse[(coarse < 5e-9) | (coarse > 7.01e-9)]
    time_s = np.unique(np.r_[outside, dense[dense < 7e-9], 5.01e-9, 7e-9, 7.01e-9])
    pulse = np.interp(time_s, [5e-9, 5.01e-9, 7e-9, 7.01e-9], [0.0, 20e-6, 20e-6, 0.0])
    output = exponential(time_s, 5.005e-9, 0.46, 0.74, 150e-12)
    output = np.where(time_s < 15.005e-9, output, exponential(time_s, 15.005e-9, 0.74, 0.46, 400e-12))
    slew = analyze_slew([transient(tb, time_s, output, 30e-6 + pulse)])
    assert slew.idd_a[0] == pytest.approx(32e-6, rel=1e-9)


# An output that rings on, never settling: a single-pole rise (tau = 150 ps) carrying a sustained
#   oscillation of 5 % of the step at 1 GHz, its envelope rising with the same time constant. It
#   never stays within 1 % of the step, so it has no settling time (NaN); whole periods of the
#   oscillation average out of the level measured over the nanosecond before the falling edge
#   (to 1e-5 V: the trapezoid's error on a cosine sampled every 8 ps or less). The oscillation is a
#   cosine: at the window's end (9.995 periods on) it is at its peak, outside the band.
def test_an_output_that_rings_on_does_not_settle() -> None:
    tb = step_tb()
    time_s = step_time(tb)
    t = np.maximum(time_s - 5.005e-9, 0.0)
    envelope = 1 - np.exp(-t / 150e-12)
    rising = 0.46 + 0.28 * envelope + 0.05 * 0.28 * envelope * np.cos(2 * np.pi * 1e9 * t)
    output = np.where(time_s < 15.005e-9, rising, exponential(time_s, 15.005e-9, 0.74, 0.46, 400e-12))
    slew = analyze_slew([transient(tb, time_s, output)])
    assert slew.vout_high_v[0] == pytest.approx(0.74, abs=1e-5)
    assert np.isnan(slew.settling_rise_s[0])
    assert slew.settling_fall_s[0] == pytest.approx(400e-12 * math.log(100), rel=1e-3)


# The same ringing output as a sine: at the window's end (15 ns, 9.995 periods on) its phase is
#   -0.031 rad, 0.16 % of the step off the level, inside the 1 % band for the window's last 27 ps
#   only. It never settles either (NaN): over the level's window it swings 5 % of the step about its
#   average, outside the band, so the level is no final value.
def test_an_output_that_rings_on_does_not_settle_whatever_its_phase() -> None:
    tb = step_tb()
    time_s = step_time(tb)
    t = np.maximum(time_s - 5.005e-9, 0.0)
    envelope = 1 - np.exp(-t / 150e-12)
    rising = 0.46 + 0.28 * envelope + 0.05 * 0.28 * envelope * np.sin(2 * np.pi * 1e9 * t)
    output = np.where(time_s < 15.005e-9, rising, exponential(time_s, 15.005e-9, 0.74, 0.46, 400e-12))
    slew = analyze_slew([transient(tb, time_s, output)])
    assert np.isnan(slew.settling_rise_s[0])


# A single-pole rise slower than the window ([Razavi-Analog] Eq. (9.11), p. 347: 1 % after tau ln 100).
#   tau = 1 ns settles at 4.605 ns, inside the 10 ns half period: over the level's window (9 to 10 ns
#   after the edge) it drifts 0.28 (exp(-9) - exp(-10)) = 21 uV, within a quarter of the 2.8 mV
#   band, and its average lies 0.28 exp(-9.5) = 21 uV off the final value, which moves the band's
#   crossing by tau x 21 uV/2.8 mV = 7.5 ps (rel = 3e-3). tau = 2 ns settles at 9.21 ns, and over the
#   window it still drifts 0.28 (exp(-4.5) - exp(-5)) = 1.2 mV, more than a quarter of the band: its
#   level is no final value, so no settling time (NaN); tau = 3 ns (13.8 ns, past the window) alike.
def test_a_rise_slower_than_its_window_does_not_settle() -> None:
    tb = step_tb()
    time_s = step_time(tb)
    for tau, expected in ((1e-9, 1e-9 * math.log(100)), (2e-9, math.nan), (3e-9, math.nan)):
        rising = exponential(time_s, 5.005e-9, 0.46, 0.74, tau)
        output = np.where(time_s < 15.005e-9, rising, exponential(time_s, 15.005e-9, rising[-1], 0.46, 400e-12))
        settling = analyze_slew([transient(tb, time_s, output)]).settling_rise_s[0]
        if math.isnan(expected):
            assert math.isnan(settling), tau
        else:
            assert settling == pytest.approx(expected, rel=3e-3)


# An output stuck at 0.3 V, or following less than a tenth of the 0.3 V step (0.02 V), has no
#   edges: its slopes, settling and overshoot are NaN; its levels and supply current still read.
def test_a_stuck_output_has_no_edges() -> None:
    tb = step_tb()
    time_s = step_time(tb)
    slew = analyze_slew([transient(tb, time_s, np.full(time_s.shape, 0.3))])
    names = ("slew_rate_rise_v_per_s", "slew_rate_fall_v_per_s", "settling_rise_s", "settling_fall_s")
    for name in (*names, "overshoot_rise", "overshoot_fall"):
        assert np.isnan(getattr(slew, name)[0]), name
    assert slew.vout_low_v[0] == pytest.approx(0.3) and slew.idd_a[0] == pytest.approx(30e-6)
    small = exponential(time_s, 5.005e-9, 0.46, 0.48, 150e-12)
    assert np.isnan(analyze_slew([transient(tb, time_s, small)]).slew_rate_rise_v_per_s[0])


# The slew analysis reads the step bench only.
def test_slew_of_another_bench_is_refused() -> None:
    tb = sine_tb()
    with pytest.raises(ValueError, match="step bench"):
        analyze_slew([polynomial_run(tb, (1.0, 0.0, 0.0), np.arange(10001) * 1e-10)])


# ---- analyze_distortion


# A memoryless nonlinearity y = a1 x + a2 x^2 + a3 x^3 driven by x = A sin(wt), A = 0.12 V,
#   a1 = 0.95, a2 = 0.4 /V, a3 = -2 /V^2 ([Razavi-Analog] Eq. (14.9), p. 579, for sin as for cos):
#   the fundamental's amplitude a1 A + 3 a3 A^3/4 = 0.111408 V, the second harmonic's a2 A^2/2 =
#   2.88 mV, the third's a3 A^3/4 = -0.864 mV.
# THD ([Razavi-Analog] Eq. (14.10), p. 579), a power ratio: ((2.88e-3)^2 + (0.864e-3)^2)/0.111408^2,
#   -31.376 dB. Without noise or other harmonics SNDR is its inverse, +31.376 dB.
# Gain: the fundamental over the input's amplitude, 0.111408/0.12 = 0.92840. The spectrum relative to
#   the input's amplitude: 20 log10(0.92840) at 10 MHz, 20 log10(2.88e-3/0.12) = -32.40 dB at 20 MHz,
#   20 log10(0.864e-3/0.12) = -42.85 dB at 30 MHz.
# The run is sampled on a simulator's axis, steps of 12 to 100 ps, which the analysis puts on its own
#   100 ps grid; eight whole periods of it. The linear interpolant errs by A w^2 h^2/8 < 5e-6 of the
#   fundamental (-106 dB), 66 dB below the harmonics: 5e-4 of their amplitude, 0.005 dB of THD; the
#   coherent record leaves no leakage. abs = 0.02 dB, the gain rel = 1e-4.
# Input common mode ([Razavi-Analog] Sec. 4.2, p. 103): the input's average over the record, 0.6 V;
#   the record's 8000 samples span eight periods less one 100 ps interval, which leaves at most
#   A/7999 = 1.5e-5 V of the sine in the average: abs = 2e-5 V.
def test_harmonic_distortion_of_a_cubic_nonlinearity() -> None:
    tb = sine_tb()
    time_s = simulator_time(tb.stop_s, (), largest_s=100e-12)
    distortion = analyze_distortion([polynomial_run(tb, (0.95, 0.4, -2.0), time_s)])
    amplitude = 0.12
    fundamental = 0.95 * amplitude + 3 * -2.0 * amplitude**3 / 4
    second, third = 0.4 * amplitude**2 / 2, -2.0 * amplitude**3 / 4
    thd_db = 10 * math.log10((second**2 + third**2) / fundamental**2)
    assert distortion.thd_db[0] == pytest.approx(thd_db, abs=0.02)
    assert distortion.sndr_db[0] == pytest.approx(-thd_db, abs=0.02)
    assert distortion.gain[0] == pytest.approx(fundamental / amplitude, rel=1e-4)
    assert distortion.vin_frequency_hz[0] == 10e6 and distortion.vin_amplitude_v[0] == amplitude
    assert distortion.vin_cm_v[0] == pytest.approx(0.6, abs=2e-5)
    spectrum = distortion.spectrum_db[0]
    for order, tone in ((1, fundamental), (2, second), (3, third)):
        index = int(np.argmin(np.abs(distortion.frequency_hz - order * 10e6)))
        assert spectrum[index] == pytest.approx(20 * math.log10(abs(tone) / amplitude), abs=0.02), order


# THD counts the harmonics to the seventh (SPECTRUM_HARMONICS, the analysis's stated order); a ninth
#   harmonic is noise and distortion to SNDR only. Output: 0.95 A (sin(wt) + 0.01 sin(2wt) + 0.01
#   sin(7wt) + 0.01 sin(9wt)): THD = 10 log10(0.01^2 + 0.01^2) = -36.99 dB ([Razavi-Analog] Eq.
#   (14.10), p. 579, to the seventh: a THD to the fifth would read -40 dB), SNDR = 10 log10(1/(3 x
#   0.01^2)) = 35.23 dB. Tolerance as above.
def test_thd_counts_harmonics_to_the_seventh_and_sndr_all_others() -> None:
    tb = sine_tb()
    time_s = simulator_time(tb.stop_s, (), largest_s=100e-12)
    phase = 2 * np.pi * tb.vin_frequency_hz * time_s
    tones = np.sin(phase) + 0.01 * (np.sin(2 * phase) + np.sin(7 * phase) + np.sin(9 * phase))
    distortion = analyze_distortion([transient(tb, time_s, 0.6 + 0.95 * 0.12 * tones)])
    assert distortion.thd_db[0] == pytest.approx(10 * math.log10(2e-4), abs=0.02)
    assert distortion.sndr_db[0] == pytest.approx(10 * math.log10(1 / 3e-4), abs=0.02)


# White Gaussian noise of sigma = 1 mV on a 0.114 V sine, recorded on the strobe's 100 ps grid as
#   Spectre writes it: SNDR ([Razavi-ADC] Eq. (12.16), p. 246) = 10 log10((0.114^2/2)/sigma^2) = 38.13
#   dB. Tolerance: the tones' 62 window bins of 4000 hold 1.6 % of the noise (+0.07 dB), and the
#   noise power of about 2000 independent bins scatters by 2.2 % (0.1 dB); abs = 0.3 dB. The six
#   harmonics' 53 bins hold 1.3 % of the noise: THD reads -38.1 + 10 log10(0.013) = -57 dB, below -50 dB.
def test_sndr_of_a_sine_in_white_noise() -> None:
    tb = sine_tb()
    time_s = np.arange(10001) * tb.waveform_sample_interval_s
    rng = np.random.default_rng(7)
    output = 0.6 + 0.114 * np.sin(2 * np.pi * tb.vin_frequency_hz * time_s) + rng.normal(0.0, 1e-3, time_s.shape)
    distortion = analyze_distortion([transient(tb, time_s, output)])
    assert distortion.sndr_db[0] == pytest.approx(10 * math.log10(0.114**2 / 2 / 1e-6), abs=0.3)
    assert distortion.thd_db[0] < -50


# The distortion analysis reads the sine bench only.
def test_distortion_of_another_bench_is_refused() -> None:
    tb = step_tb()
    time_s = step_time(tb)
    with pytest.raises(ValueError, match="sine bench"):
        analyze_distortion([transient(tb, time_s, np.full(time_s.shape, 0.6))])


# Points of different record lengths (a sine of 10 and of 12 periods) have no common spectrum axis:
#   refused.
def test_distortion_of_differing_records_is_refused() -> None:
    ten, twelve = sine_tb(), replace(sine_tb(), sine_periods=12)
    runs = [
        polynomial_run(tb, (1.0, 0.0, 0.0), np.arange(round(tb.stop_s / 100e-12) + 1) * 100e-12) for tb in (ten, twelve)
    ]
    with pytest.raises(ValueError, match="record length"):
        analyze_distortion(runs)


# ---- the input common-mode range, on AC results built directly: each point's margin known


def ac_result(
    gain_dc_db: list[float],
    *,
    vdd_v: float = 1.2,
    vin_cm_v: list[float] | None = None,
    margins: list[float] | None = None,
    params: Params | None = None,
) -> AnalysisAc:
    """An AC result over ``len(gain_dc_db)`` points whose every figure differs by point: point k has
    unity-gain bandwidth (k + 1) 100 MHz, phase margin 60 + k deg, gain margin 10 + k dB, bandwidth
    (k + 1) MHz, PSRR 40 + k dB, CMRR 50 + k dB, supply current (k + 1) 10 uA, tail current (k + 1)
    5 uA, output 0.5 + k/100 V, saturation margin (k + 1) 10 mV for every device; and its input
    common mode and the tail's and input pair's margin as given (CM_SWEEP's points, 0.1 V)."""
    k = np.arange(len(gain_dc_db), dtype=np.float64)
    frequency_hz = sweep_hz()
    rows = np.zeros((len(k), len(frequency_hz)))
    vin_cm = np.asarray(CM_SWEEP[: len(k)]) * vdd_v if vin_cm_v is None else np.asarray(vin_cm_v)
    return AnalysisAc(
        group=None,
        index=None,
        dut=Params() if params is None else params,
        vdd_v=np.full(len(k), vdd_v),
        vin_cm_v=vin_cm,
        frequency_hz=frequency_hz,
        gain_db=rows,
        phase_deg=rows,
        gain_dc_db=np.asarray(gain_dc_db, dtype=np.float64),
        unity_gain_bandwidth_hz=(k + 1) * 100e6,
        phase_margin_deg=60 + k,
        bandwidth_hz=(k + 1) * 1e6,
        gbw_hz=(k + 1) * 1e6 * 10 ** (np.asarray(gain_dc_db) / 20),
        gain_margin_db=10 + k,
        psrr_db=rows,
        cmrr_db=rows,
        psrr_dc_db=40 + k,
        cmrr_dc_db=50 + k,
        idd_a=(k + 1) * 10e-6,
        iss_a=(k + 1) * 5e-6,
        vout_v=0.5 + k / 100,
        vout_cm_v=0.5 + k / 100,
        saturation_margin_v=(k + 1) * 10e-3,
        saturation_margin_pair_v=np.full(len(k), 0.1) if margins is None else np.asarray(margins, dtype=np.float64),
    )


def margin_tent(vin_cm_v: np.ndarray) -> np.ndarray:
    """A tail and input pair saturated between 0.55 V and 0.85 V: margin 0.3 - 2 |V_in,CM - 0.7 V|."""
    return 0.3 - 2 * np.abs(np.asarray(vin_cm_v) - 0.7)


# The input common-mode range ([Razavi-Analog] Eq. (4.1), p. 105: the tail and the input pair
#   saturated), over CM_SWEEP's thirteen points at 1.2 V (0 to 1.2 V by 0.1 V) and the nominal point
#   at 0.73 V. The margin 0.3 - 2 |V - 0.7| is linear between the sweep's points about each zero
#   (0.55 V and 0.85 V lie between 0.5 and 0.6, 0.8 and 0.9), so the interpolated ends are exact
#   (abs = 1e-12): 0.55 V to 0.85 V, 0.3 V. Margins positive everywhere reach both rails, 0 to 1.2 V.
#   A lost (NaN) neighbour (0.8 V) ends the range at the last saturated point (the nominal 0.73 V); a
#   nominal point out of
#   saturation has none (NaN).
def test_the_input_common_mode_range_is_where_the_tail_and_pair_stay_saturated() -> None:
    sweep = np.asarray(CM_SWEEP) * 1.2
    nominal = ac_result([40.0], vin_cm_v=[0.73], margins=list(margin_tent([0.73])))
    span = analyze_range(ac_result([40.0] * 13, margins=list(margin_tent(sweep))), nominal=nominal)
    assert isinstance(span, AnalysisRange)
    assert (span.vin_cm_min_v, span.vin_cm_max_v) == pytest.approx((0.55, 0.85), abs=1e-12)
    assert span.vin_cm_range_v == pytest.approx(0.3, abs=1e-12) and span.vin_cm_v == 0.73
    wide = analyze_range(ac_result([40.0] * 13, margins=[0.1] * 13), nominal=ac_result([40.0], vin_cm_v=[0.73]))
    assert (wide.vin_cm_min_v, wide.vin_cm_max_v, wide.vin_cm_range_v) == pytest.approx((0.0, 1.2, 1.2), abs=1e-12)
    lost = list(margin_tent(sweep))
    lost[8] = math.nan
    cut = analyze_range(ac_result([40.0] * 13, margins=lost), nominal=nominal)
    assert (cut.vin_cm_min_v, cut.vin_cm_max_v) == pytest.approx((0.55, 0.73), abs=1e-12)
    off = ac_result([40.0], vin_cm_v=[0.73], margins=[-0.01])
    assert math.isnan(
        analyze_range(ac_result([40.0] * 13, margins=list(margin_tent(sweep))), nominal=off).vin_cm_range_v
    )


# A sweep at another supply than the nominal point, or out of order, is refused.
def test_a_range_of_mismatched_points_is_refused() -> None:
    nominal = ac_result([40.0], vin_cm_v=[0.73])
    with pytest.raises(ValueError, match="rising sweep"):
        analyze_range(ac_result([40.0] * 13, vdd_v=1.1), nominal=nominal)
    with pytest.raises(ValueError, match="rising sweep"):
        analyze_range(ac_result([40.0] * 3, vin_cm_v=[0.6, 0.5, 0.7]), nominal=nominal)


# ---- metrics, on results built directly: each field's row known


def noise_result(ac: AnalysisAc) -> AnalysisNoise:
    """A noise result of ``ac``'s points: point k at (k + 1) nV/sqrt(Hz) at 1 MHz, (k + 1) 100 uV RMS
    referred to the input."""
    k = np.arange(len(ac.vdd_v), dtype=np.float64)
    zeros = np.zeros((len(k), len(ac.frequency_hz)))
    return AnalysisNoise(
        group=None,
        index=None,
        dut=ac.dut,
        vdd_v=ac.vdd_v,
        vin_cm_v=ac.vin_cm_v,
        frequency_hz=ac.frequency_hz,
        noise_out_v_per_rthz=zeros,
        noise_in_v_per_rthz=zeros,
        spot_frequency_hz=1e6,
        noise_in_1mhz_v_per_rthz=(k + 1) * 1e-9,
        noise_out_v=(k + 1) * 100e-6 * 10 ** (ac.gain_dc_db / 20),
        noise_in_v=(k + 1) * 100e-6,
    )


def span_result(low: float = 0.4, high: float = 1.0) -> AnalysisRange:
    """An input common-mode range from ``low`` to ``high`` at 1.2 V."""
    return AnalysisRange(
        group=None,
        index=None,
        dut=Params(),
        vdd_v=1.2,
        vin_cm_v=0.7,
        vin_cm_min_v=low,
        vin_cm_max_v=high,
        vin_cm_range_v=high - low,
    )


def slew_result(
    settling_rise_s: float, settling_fall_s: float, vin_v: tuple[float, float] = (0.6, 0.8)
) -> AnalysisSlew:
    """A step result: the input from ``vin_v``'s first to its second, +0.6 V/ns up, -0.25 V/ns down,
    the given settling times."""
    return AnalysisSlew(
        group=None,
        index=None,
        dut=Params(),
        vin_low_v=row(vin_v[0]),
        vin_high_v=row(vin_v[1]),
        vin_rise_s=row(5.005e-9),
        vin_fall_s=row(15.005e-9),
        vout_low_v=row(0.46),
        vout_high_v=row(0.74),
        slew_rate_rise_v_per_s=row(0.6e9),
        slew_rate_fall_v_per_s=row(-0.25e9),
        settling_rise_s=row(settling_rise_s),
        settling_fall_s=row(settling_fall_s),
        overshoot_rise=row(0.0),
        overshoot_fall=row(0.0),
        idd_a=row(30e-6),
        time_s=np.linspace(0.0, 20e-9, 5),
        vout_v=np.zeros((1, 5)),
    )


def distortion_result(thd_db: float, vin_cm_v: float = 0.7) -> AnalysisDistortion:
    """A sine result of the given THD, 0.06 V about ``vin_cm_v``."""
    return AnalysisDistortion(
        group=None,
        index=None,
        dut=Params(),
        vin_cm_v=row(vin_cm_v),
        vin_amplitude_v=row(0.06),
        vin_frequency_hz=row(10e6),
        thd_db=row(thd_db),
        sndr_db=row(-thd_db),
        gain=row(0.93),
        frequency_hz=np.linspace(0.0, 5e9, 6),
        spectrum_db=np.zeros((1, 6)),
    )


def supply_result(gain_dc_db: list[float]) -> AnalysisAc:
    """An AC result over SUPPLY_SWEEP's supplies of 1.2 V, at 0.7 V each."""
    result = ac_result(gain_dc_db, vin_cm_v=[0.7] * 3)
    return replace(result, vdd_v=np.asarray([1.08, 1.2, 1.32]))


# Every small-signal metric is the nominal point's: gain 40 dB, unity-gain bandwidth 100 MHz, phase
#   margin 60 deg, gain margin 10 dB, bandwidth 1 MHz, PSRR 40 dB, CMRR 50 dB, power 1.2 V x 10 uA
#   ([Baker] Sec. 24.1, p. 805), tail current 5 uA, output 0.5 V, noise 1 nV/sqrt(Hz) and 100 uV. The
#   range is the range result's. The lowest gain and saturation margin over the supply are the
#   supply result's minimum, 31 dB and 10 mV. The step's slopes, the fall's reported positive
#   (0.25 V/ns); the settling time of the slower edge, max(0.462, 1.109) ns; the THD as read.
def test_the_metrics_are_the_nominal_point_and_the_slower_edge() -> None:
    ac = ac_result([40.0], vin_cm_v=[0.7])
    found = metrics(
        ac=ac,
        noise=noise_result(ac),
        span=span_result(),
        supply=supply_result([31.0, 40.0, 42.0]),
        slew=slew_result(0.462e-9, 1.109e-9),
        distortion=distortion_result(-31.4),
    )
    assert isinstance(found, Metrics)
    expected = {
        "gain_dc_db": 40.0,
        "unity_gain_bandwidth_hz": 100e6,
        "phase_margin_deg": 60.0,
        "gain_margin_db": 10.0,
        "bandwidth_hz": 1e6,
        "psrr_dc_db": 40.0,
        "cmrr_dc_db": 50.0,
        "power_w": 12e-6,
        "iss_a": 5e-6,
        "vout_v": 0.5,
        "noise_in_1mhz_v_per_rthz": 1e-9,
        "noise_in_v": 100e-6,
        "vin_cm_min_v": 0.4,
        "vin_cm_max_v": 1.0,
        "vin_cm_range_v": 0.6,
        "gain_dc_min_supply_db": 31.0,
        "saturation_margin_min_supply_v": 10e-3,
        "slew_rate_rise_v_per_s": 0.6e9,
        "slew_rate_fall_v_per_s": 0.25e9,
        "settling_s": 1.109e-9,
        "thd_db": -31.4,
    }
    for name, value in expected.items():
        assert getattr(found, name) == pytest.approx(value, rel=1e-12), name
    # a differential amplifier has no unity-gain runs (those four None), no single output level and,
    # without mismatch, no rejections to report (None)
    telescopic = ac_result([40.0], vin_cm_v=[0.7], params=Params(topology=Topology.TELESCOPIC))
    bare = metrics(
        ac=telescopic, noise=noise_result(telescopic), span=span_result(), supply=supply_result([31.0, 40.0, 42.0])
    )
    assert (bare.slew_rate_rise_v_per_s, bare.slew_rate_fall_v_per_s, bare.settling_s, bare.thd_db) == (None,) * 4
    assert (bare.psrr_dc_db, bare.cmrr_dc_db, bare.vout_v) == (None,) * 3


# A response whose phase never reaches -180 deg on the sweep has no gain margin there ([Baker]
#   Sec. 24.1, p. 810: it lies beyond the sweep): None, which no bound counts as missed; a point that
#   lost its output (no gain either) keeps NaN.
def test_a_gain_margin_beyond_the_sweep_is_none() -> None:
    beyond = replace(ac_result([40.0], vin_cm_v=[0.7]), gain_margin_db=row(math.nan))
    found = metrics(ac=beyond, noise=noise_result(beyond), span=span_result(), supply=supply_result([31.0, 40.0, 42.0]))
    assert found.gain_margin_db is None
    lost = replace(beyond, gain_dc_db=row(math.nan))
    assert math.isnan(
        metrics(
            ac=lost, noise=noise_result(lost), span=span_result(), supply=supply_result([31.0, 40.0, 42.0])
        ).gain_margin_db
    )


# A stimulus leaving the input common-mode range (0.4 V to 1.0 V) measures no slew, settling or
#   distortion (NaN): a step from 0.3 V, or a sine of 0.06 V about 0.97 V (to 1.03 V); one within it
#   reads as measured.
def test_a_stimulus_outside_the_input_range_measures_nothing() -> None:
    ac = ac_result([40.0], vin_cm_v=[0.7])
    supply = supply_result([31.0, 40.0, 42.0])
    outside = metrics(
        ac=ac,
        noise=noise_result(ac),
        span=span_result(),
        supply=supply,
        slew=slew_result(0.462e-9, 1.109e-9, vin_v=(0.3, 0.5)),
        distortion=distortion_result(-31.4, vin_cm_v=0.97),
    )
    for name in ("slew_rate_rise_v_per_s", "slew_rate_fall_v_per_s", "settling_s", "thd_db"):
        assert math.isnan(getattr(outside, name)), name
    inside = metrics(
        ac=ac, noise=noise_result(ac), span=span_result(), supply=supply, distortion=distortion_result(-31.4, 0.93)
    )
    assert inside.thd_db == pytest.approx(-31.4)


# The lowest gain over the supply is NaN where a supply point lost its output; the settling time is
#   NaN where either edge never settles (the slower edge then has none). Supply points that are not
#   SUPPLY_SWEEP's about the nominal one are refused.
def test_a_lost_supply_point_or_an_unsettled_edge_reads_nan() -> None:
    ac = ac_result([40.0], vin_cm_v=[0.7])
    found = metrics(
        ac=ac,
        noise=noise_result(ac),
        span=span_result(),
        supply=supply_result([math.nan, 40.0, 42.0]),
        slew=slew_result(math.nan, 1.109e-9),
    )
    assert math.isnan(found.gain_dc_min_supply_db) and math.isnan(found.settling_s)
    with pytest.raises(ValueError, match="supply"):
        metrics(
            ac=ac,
            noise=noise_result(ac),
            span=span_result(),
            supply=replace(supply_result([1.0] * 3), vdd_v=np.full(3, 1.2)),
        )


# ---- the record, on every run of an amplifier in TSMC65


def characterization(params: Params) -> dict[str, Meas]:
    """Every run of ``params`` in TSMC65 (``runs.testbenches``), synthetic: a one-pole amplifier
    (1 MHz) of gain 100 times the supply over 1.2 V, at the nominal input common mode 0.7 V; over
    the common mode its tail and input pair's margin 0.3 - 2 |V_in,CM - 0.7 V| (saturated from 0.55
    to 0.85 V); a single-pole step of 0.24 V (150 ps up, 400 ps down) from 0.58 V to 0.82 V and the
    cubic nonlinearity's sine about 0.7 V."""
    pytest.importorskip("pdk.tsmc65.hdl21")
    found = {}
    for name, tb in block_runs.testbenches("tsmc65", params).items():
        if tb.bench is Bench.STEP:
            time_s = step_time(tb)
            low, high = 0.58, 0.82
            rise_s = tb.step_period_s / 4 + tb.transition_time_s / 2
            fall_s = 3 * tb.step_period_s / 4 + tb.transition_time_s / 2
            rising = exponential(time_s, rise_s, low, high, 150e-12)
            found[name] = transient(
                tb, time_s, np.where(time_s < fall_s, rising, exponential(time_s, fall_s, high, low, 400e-12))
            )
        elif tb.bench is Bench.SINE:
            sine = replace(tb, vin_amplitude_v=0.12)
            run = polynomial_run(sine, (0.95, 0.4, -2.0), np.arange(10001) * tb.waveform_sample_interval_s)
            found[name] = replace(run, param=tb, v={key: value + 0.1 for key, value in run.v.items()})
        else:
            vin_cm_v = 0.7 if tb.vin_cm_v is None else tb.vin_cm_v
            margin = float(margin_tent([vin_cm_v])[0])
            margins = {"Mtail": margin, "Min_p": margin, "Min_n": margin, "Mload": 0.2}
            run = small_signal(tb, poles(sweep_hz(), 100.0 * tb.vdd / 1.2, 1e6), margins=margins)
            run.sweeps["opdc"].v["inp"][0] = vin_cm_v
            found[name] = run
    return found


# The record's metrics through runs.results: 40 dB at the nominal point (TSMC65's 1.2 V, the lowest
#   point 4.3e-6 dB below A0); the range 0.55 V to 0.85 V; the lowest supply's gain 90 % of nominal
#   (40 + 20 log10(0.9) dB); power 1.2 V x 50 uA; the step's 0.9 x 0.24/150 ps (rel 6e-2, as above)
#   and the slower edge's 400 ps ln 100, its input from 0.58 V to 0.82 V inside the range; the
#   cubic's THD at 0.12 V (-31.376 dB, on the strobe's own grid) about 0.7 V, from 0.58 V to 0.82 V,
#   inside it too.
def test_metrics_of_a_characterization_over_the_common_mode_and_the_supply() -> None:
    record = block_runs.results(characterization(Params()))
    assert record.metrics["gain_dc_db"] == pytest.approx(40.0, abs=1e-4)
    assert (record.metrics["vin_cm_min_v"], record.metrics["vin_cm_max_v"]) == pytest.approx((0.55, 0.85), abs=1e-9)
    assert record.metrics["gain_dc_min_supply_db"] == pytest.approx(40.0 + 20 * math.log10(0.9), abs=1e-4)
    assert record.metrics["power_w"] == pytest.approx(1.2 * 50e-6, rel=1e-3)
    assert record.metrics["slew_rate_rise_v_per_s"] == pytest.approx(0.9 * 0.24 / 150e-12, rel=6e-2)
    assert record.metrics["settling_s"] == pytest.approx(400e-12 * math.log(100), rel=1e-3)
    assert record.metrics["thd_db"] == pytest.approx(-31.376, abs=0.02)


def test_the_record_of_a_single_ended_and_of_a_differential_amplifier() -> None:
    single = block_runs.results(characterization(Params()))
    assert set(single.metrics) == {field for field in Metrics.__dataclass_fields__}
    assert all(isinstance(detail, Plot) for detail in single.details)
    names = [detail.name for detail in single.details]
    assert names[-2:] == ["step_response", "spectrum"] and len(set(names)) == len(names) == 15
    assert single.waves == {"unity-gain step": "step", "unity-gain sine": "sine"}
    differential = block_runs.results(characterization(Params(topology=Topology.TELESCOPIC)))
    assert [detail.name for detail in differential.details] == [
        name for name in names[:-2] if name not in ("psrr", "cmrr")
    ] and differential.waves == {}
    assert differential.metrics["thd_db"] is None and differential.metrics["settling_s"] is None
    assert differential.metrics["gain_dc_db"] == pytest.approx(40.0, abs=1e-4)
