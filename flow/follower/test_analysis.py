"""The follower's analyses and metrics on synthetic runs whose answers are known in closed form, as a
run's measurement (``flow.pipeline.Meas``) reads: frequency responses on the bench's own sweep
(1 kHz to 100 GHz, 20 points a decade), step transients on a simulator's non-uniform time axis.
Each expected value is derived from the closed form in the comment above its test, never from the
code under test; each tolerance says what in the sampling bounds it."""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import asdict, replace
from datetime import UTC, datetime

import numpy as np
import pytest

from flow.pipeline import Meas, MeasInfo, Plot, Sweep, SweepKind

from . import runs
from .analysis import analyze_characteristic, analyze_impedance, analyze_slew, analyze_transfer, metrics
from .params import NOMINAL_VIN, SUPPLY_SWEEP, VIN_STEP, VIN_SWEEP, Params, Stimulus, TbParams
from .types import AnalysisCharacteristic, Metrics

INFO = MeasInfo(backend="spice", timestamp_utc=datetime(2026, 10, 17, tzinfo=UTC))
TB = TbParams(params=runs.source(), vdd=1.2, vin_v=0.9)

Response = Callable[[np.ndarray], np.ndarray]


def frequency_axis(tb: TbParams) -> np.ndarray:
    """The bench's AC sweep as Spectre runs it: ``points_per_decade`` a decade, both ends included."""
    decades = round(math.log10(tb.fstop_hz / tb.fstart_hz))
    return np.logspace(math.log10(tb.fstart_hz), math.log10(tb.fstop_hz), decades * tb.points_per_decade + 1)


def ac_run(
    tb: TbParams,
    response: Response,
    supply: Response,
    *,
    vout_v: float,
    idd_a: float,
    reference: Response | None = None,
    zout: Response | None = None,
) -> Meas:
    """A run of ``tb`` with the AC stimulus on the input: the operating point (``vout_v``, the
    supply source's current ``idd_a``), the output per volt of input ``response(f)``, per volt
    of supply ``supply(f)``, per volt of the references' supply ``reference(f)`` (none without
    it) and per ampere of the test current into it ``zout(f)``, the output node's impedance
    (1.5 kohm without it: Spectre's ``xf`` to the output)."""
    frequency_hz = frequency_axis(tb)
    references = np.zeros(len(frequency_hz)) if reference is None else reference(frequency_hz)
    impedance = np.full(len(frequency_hz), 1500.0) if zout is None else zout(frequency_hz)
    return Meas(
        group=None,
        index=None,
        dut=tb.params,
        info=INFO,
        param=tb,
        sweeps={
            "opdc": Sweep(
                kind=SweepKind.OP,
                x=np.zeros(0),
                v={"vin": np.asarray([tb.vin_v]), "vout": np.asarray([vout_v])},
                i={"vdd": np.asarray([idd_a])},
            ),
            "ac": Sweep(kind=SweepKind.AC, x=frequency_hz, v={"vout": np.asarray(response(frequency_hz), complex)}),
            "xf": Sweep(
                kind=SweepKind.XF,
                x=frequency_hz,
                v={
                    "vdd": np.asarray(supply(frequency_hz), complex),
                    "vddb": np.asarray(references, complex),
                    "itest": np.asarray(impedance, complex),
                },
            ),
        },
    )


def impedance_run(tb: TbParams, zout: Response) -> Meas:
    """A run of ``tb`` with the AC stimulus on the input whose output node presents ``zout(f)``
    to the test current (a follower of gain 0.85 and no supply transfer otherwise)."""
    return ac_run(
        tb, lambda f: np.full(len(f), 0.85), lambda f: np.zeros(len(f)), vout_v=tb.vin_v - 0.3, idd_a=20e-6, zout=zout
    )


def single_pole(tb: TbParams, value: float, pole_hz: float) -> Meas:
    """A run of ``tb`` with the AC stimulus on the input, its response ``value`` falling at one
    pole ``pole_hz`` (the output 0.3 V below the input, the supply passing a hundredth of
    ``value``, 40 uA, the output 1.5 kohm)."""
    return ac_run(
        tb,
        lambda f: value / (1 + 1j * f / pole_hz),
        lambda f: np.full(len(f), 0.01 * value),
        vout_v=tb.vin_v - 0.3,
        idd_a=40e-6,
    )


def dc_run(tb: TbParams, vout: Response) -> Meas:
    """The nominal input's run of ``tb`` with the input's DC sweep beside its AC response (a
    single pole): the output ``vout(vin)`` at each step of a 480th of the supply from ground to
    it, 481 levels."""
    tb = replace(tb, dc_step_v=tb.vdd / 480)
    run = single_pole(tb, 0.85, 1e9)
    vin_v = np.linspace(0.0, tb.vdd, 481)
    return replace(run, sweeps={**run.sweeps, "dc": Sweep(kind=SweepKind.DC, x=vin_v, v={"vout": vout(vin_v)})})


def softplus_band(a_v: float, b_v: float, width_v: float) -> Response:
    """A follower's characteristic whose gain rises from 0 near ``a_v`` to 0.85 and falls back
    near ``b_v``: vout = 0.85 w (ln(1 + exp((v - a) / w)) - ln(1 + exp((v - b) / w))), whose
    slope is exactly 0.85 (sigma((v - a) / w) - sigma((v - b) / w)), sigma the logistic."""
    return lambda v: 0.85 * width_v * (np.logaddexp(0, (v - a_v) / width_v) - np.logaddexp(0, (v - b_v) / width_v))


def step_tb(tb: TbParams = TB) -> TbParams:
    """The step run of ``tb``: 0.3 V about 0.9 V (0.75 V to 1.05 V), 20 ns period, 10 ps edges."""
    return replace(tb, stimulus=Stimulus.STEP, vin_v=0.9, step_v=0.3)


def simulator_axis(tb: TbParams, *, seed: int = 1) -> np.ndarray:
    """A time axis as an adaptive simulator steps it: the source's corners (0, each edge's start
    and end, the period, the record's end), steps of 0.5 to 1 ps for 3 ns after each edge's
    start, of 10 to 30 ps elsewhere, each step drawn at random."""
    generator = np.random.default_rng(seed)
    period, edge, stop = tb.step_period_s, tb.transition_time_s, tb.tran_stop_s
    starts = (period / 4, 3 * period / 4)
    corners = np.asarray([0.0, starts[0], starts[0] + edge, starts[1], starts[1] + edge, period, stop])
    coarse = np.cumsum(generator.uniform(10e-12, 30e-12, round(stop / 10e-12)))
    fine = [start + np.cumsum(generator.uniform(0.5e-12, 1e-12, 6000)) for start in starts]
    fine = [points[points < start + 3e-9] for points, start in zip(fine, starts, strict=True)]
    axis = np.unique(np.concatenate([corners, coarse, *fine]))
    return axis[axis <= stop]


def step_run(
    tb: TbParams,
    rise: Response,
    fall: Response,
    *,
    time_s: np.ndarray | None = None,
    idd: Callable[[np.ndarray], np.ndarray] | None = None,
) -> Meas:
    """A step run of ``tb`` (the input ``tb.step_v`` about ``tb.vin_v``, up a quarter period in
    and down three quarters in, ``tb.transition_time_s`` edges): the output 0.3 V below the
    input, leaving each level at the middle of the input's edge as ``rise(s)`` and ``fall(s)``
    say, the share of the step done ``s`` seconds after it; the supply current ``idd(t)`` (40 uA
    without it); on ``simulator_axis`` unless given ``time_s``."""
    period, edge, step = tb.step_period_s, tb.transition_time_s, tb.step_v
    time_s = simulator_axis(tb) if time_s is None else time_s
    low = tb.vin_v - step / 2 - 0.3
    rise_mid, fall_mid = period / 4 + edge / 2, 3 * period / 4 + edge / 2
    output = np.full(len(time_s), low)
    up = (time_s >= rise_mid) & (time_s < fall_mid)
    output[up] = low + step * rise(time_s[up] - rise_mid)
    down = time_s >= fall_mid
    output[down] = low + step - step * fall(time_s[down] - fall_mid)
    corners = [0, period / 4, period / 4 + edge, 3 * period / 4, 3 * period / 4 + edge, tb.tran_stop_s]
    vin = tb.vin_v - step / 2 + step * np.interp(time_s, corners, [0, 0, 1, 1, 0, 0])
    return Meas(
        group=None,
        index=None,
        dut=tb.params,
        info=INFO,
        param=tb,
        time_s=time_s,
        v={"vin": vin, "vout": output},
        i={"vdd": np.full(len(time_s), 40e-6) if idd is None else idd(time_s)},
    )


def step_pair(
    tb: TbParams,
    rise: Response,
    fall: Response,
    *,
    half_rise: Response | None = None,
    half_fall: Response | None = None,
    time_s: np.ndarray | None = None,
    idd: Callable[[np.ndarray], np.ndarray] | None = None,
) -> list[Meas]:
    """The step run of ``tb`` and that of the same step at half its size (``runs.testbenches``'s
    ``step`` and ``step_half``), each as ``step_run`` makes it: the half step's output leaving
    each level as ``half_rise`` and ``half_fall`` say (shares of its own step), as the full
    step's where not given (a linear response, whose slope halves with the step)."""
    half = replace(tb, step_v=tb.step_v / 2)
    return [
        step_run(tb, rise, fall, time_s=time_s, idd=idd),
        step_run(half, half_rise or rise, half_fall or fall, time_s=time_s, idd=idd),
    ]


def strobed_axis(tb: TbParams) -> np.ndarray:
    """A time axis as Spectre writes a strobed transient: from 0 every
    ``tb.waveform_sample_interval_s`` to ``tb.tran_stop_s``, each time the sum of the strobes
    before it, so the last falls a few ulps short of ``tran_stop_s`` (5000 strobes of 5 ps:
    24.999999999999016 ns)."""
    count = round(tb.tran_stop_s / tb.waveform_sample_interval_s)
    return np.concatenate([[0.0], np.cumsum(np.full(count, tb.waveform_sample_interval_s))])


def exponential(tau_s: float) -> Response:
    """A single pole's step response, the share of the step done: 1 - exp(-s / tau)."""
    return lambda s: 1 - np.exp(-s / tau_s)


def ramp(slope_v_per_s: float, step_v: float) -> Response:
    """A slewing output's step: a ramp of ``slope_v_per_s`` until it has moved the step."""
    return lambda s: np.minimum(slope_v_per_s * s / step_v, 1.0)


def constant(share: float) -> Response:
    """An output that jumps to ``share`` of the step at once and stays."""
    return lambda s: np.full(len(s), share)


# --- analyze_transfer -------------------------------------------------------------------------


# One pole: H(f) = A0 / (1 + j f / fp), A0 = 0.85, fp = 637 MHz (between the sweep's points).
# [Razavi-Analog] Eq. (6.101), p. 204: a one-pole response's magnitude A0 / sqrt(1 + (f / fp)^2)
# - gain_dc is |H| at the sweep's first point, 1 kHz: A0 / sqrt(1 + (1e3 / fp)^2).
# - bandwidth_hz is where |H| has fallen 3.0 dB (not 3.01 dB) from that:
#   1 + (f / fp)^2 = 10^0.3 (1 + (1e3 / fp)^2), f = 0.99763 fp
#   ([Razavi-Analog] Fig. 6.43, p. 204: the -3-dB bandwidth). The analysis interpolates the dB
#   response linearly in log frequency between points 0.05 decade apart; the closed form's
#   curvature there keeps that within 0.04 % of the crossing: rel 1e-3.
# - the supply's transfer to the output is Hs(f) = 0.02 (1 + j f / 10 MHz) (rising, as a supply's
#   feedthrough does) from the follower's supply and Hb = -0.05 j from the references' (vddb), one
#   ripple on both, so psrr_dc_db = 20 log10(|H| / |Hs + Hb|) at 1 kHz
#   ([Razavi-Analog] Sec. 9.11, p. 400: PSRR, the input's gain over the supply's).
# - gain_db is 20 log10 |H(f)| at every swept f; vout_v and idd_a are the operating point's; the
#   level shift is the input minus the output ([Razavi-Analog] Sec. 3.4, p. 68).
def test_transfer_of_one_pole_gives_gain_bandwidth_psrr_and_levels() -> None:
    a0, pole_hz, zero_hz = 0.85, 637e6, 10e6
    levels = [replace(TB, vin_v=vin) for vin in (0.6, 0.9)]
    transfer = analyze_transfer(
        [
            ac_run(
                tb,
                lambda f: a0 / (1 + 1j * f / pole_hz),
                lambda f: 0.02 * (1 + 1j * f / zero_hz),
                vout_v=tb.vin_v - 0.35,
                idd_a=25e-6 * (1 + k),
                reference=lambda f: np.full(len(f), -0.05j),
            )
            for k, tb in enumerate(levels)
        ]
    )
    f0 = TB.fstart_hz
    gain_at_f0 = a0 / math.sqrt(1 + (f0 / pole_hz) ** 2)
    assert transfer.gain_dc == pytest.approx([gain_at_f0] * 2, rel=1e-12)
    expected_bandwidth = pole_hz * math.sqrt(10**0.3 * (1 + (f0 / pole_hz) ** 2) - 1)
    assert transfer.bandwidth_hz == pytest.approx([expected_bandwidth] * 2, rel=1e-3)
    supply_at_f0 = abs(0.02 * (1 + 1j * f0 / zero_hz) - 0.05j)
    assert transfer.psrr_dc_db == pytest.approx([20 * math.log10(gain_at_f0 / supply_at_f0)] * 2, abs=1e-9)
    assert transfer.vin_v == pytest.approx([0.6, 0.9]) and transfer.vout_v == pytest.approx([0.25, 0.55])
    assert transfer.vdd_v == pytest.approx([1.2, 1.2])
    assert transfer.level_shift_v == pytest.approx([0.35, 0.35], abs=1e-12)
    assert transfer.idd_a == pytest.approx([25e-6, 50e-6])
    frequency_hz = frequency_axis(TB)
    assert transfer.frequency_hz == pytest.approx(frequency_hz, rel=1e-12)
    expected_db = 20 * np.log10(a0 / np.sqrt(1 + (frequency_hz / pole_hz) ** 2))
    assert transfer.gain_db.shape == (2, 161)
    assert transfer.gain_db[1] == pytest.approx(expected_db, abs=1e-9)


# Two equal poles: H = A0 / (1 + j f / fp)^2, so |H| = A0 / (1 + (f / fp)^2); 3 dB down where
# 1 + (f / fp)^2 = 10^(3/20), f = fp sqrt(10^0.15 - 1) = 0.6423 fp (the 1 kHz point's own droop,
# 1e-11 relative, neglected). Linear interpolation in log f over 0.05-decade steps on this
# steeper curve: within 0.2 % of the closed form, so rel 5e-3.
def test_transfer_bandwidth_of_two_equal_poles() -> None:
    pole_hz = 300e6
    run = ac_run(
        TB, lambda f: 0.9 / (1 + 1j * f / pole_hz) ** 2, lambda f: np.full(len(f), 0.01), vout_v=0.6, idd_a=1e-5
    )
    transfer = analyze_transfer([run])
    assert transfer.bandwidth_hz[0] == pytest.approx(pole_hz * math.sqrt(10**0.15 - 1), rel=5e-3)


# A peaking second-order response, H = wn^2 / (s^2 + 2 zeta wn s + wn^2)
# ([Razavi-Analog] Eq. (16.16), p. 662), zeta = 0.3, fn = 2.2 GHz: the gain rises past 1 before
# it falls, and the -3 dB bandwidth is its first fall 3 dB below the low-frequency gain. With
# u = (f / fn)^2: |H|^-2 = (1 - u)^2 + 4 zeta^2 u = 10^0.3, so
# u = (1 - 2 zeta^2) + sqrt((1 - 2 zeta^2)^2 + 10^0.3 - 1), f = fn sqrt(u) = 1.4531 fn.
# Interpolation in log f: within 0.02 %, so rel 1e-3.
def test_transfer_bandwidth_of_a_peaking_response() -> None:
    zeta, natural_hz = 0.3, 2.2e9
    run = ac_run(
        TB,
        lambda f: 1 / (1 - (f / natural_hz) ** 2 + 2j * zeta * f / natural_hz),
        lambda f: np.full(len(f), 0.01),
        vout_v=0.6,
        idd_a=1e-5,
    )
    transfer = analyze_transfer([run])
    half = 1 - 2 * zeta**2
    u = half + math.sqrt(half**2 + 10**0.3 - 1)
    assert transfer.bandwidth_hz[0] == pytest.approx(natural_hz * math.sqrt(u), rel=1e-3)


# A pole at 1 THz, past the sweep's 100 GHz end: |H(100 GHz)| / |H(1 kHz)| = 1 / sqrt(1.01),
# -0.043 dB, so the response never falls 3 dB inside the sweep: the bandwidth is NaN, the gain and
# PSRR are still read at 1 kHz (the supply passing a hundredth of the gain: 40 dB).
def test_transfer_bandwidth_beyond_the_sweep_is_nan() -> None:
    transfer = analyze_transfer([single_pole(TB, 0.85, 1e12)])
    assert math.isnan(transfer.bandwidth_hz[0])
    assert transfer.gain_dc[0] == pytest.approx(0.85, rel=1e-12)
    assert transfer.psrr_dc_db[0] == pytest.approx(40.0, abs=1e-9)


def test_transfer_refuses_other_runs_and_unequal_sweeps() -> None:
    with pytest.raises(ValueError, match="on the input"):
        analyze_transfer([step_run(step_tb(), exponential(100e-12), exponential(100e-12))])
    with pytest.raises(ValueError, match="one frequency sweep"):
        analyze_transfer([single_pole(TB, 0.85, 1e9), single_pole(replace(TB, points_per_decade=10), 0.85, 1e9)])
    # the transfer functions on other frequencies than the AC response's
    run = single_pole(TB, 0.85, 1e9)
    xf = run.sweeps["xf"]
    shifted = replace(run, sweeps={**run.sweeps, "xf": replace(xf, x=xf.x * 1.001)})
    with pytest.raises(ValueError, match="AC response's frequencies"):
        analyze_transfer([shifted])
    with pytest.raises(ValueError, match="at least one measurement"):
        analyze_transfer([])


# A sweep of one frequency (the bench's start, 1 kHz, alone): a response of one point has no
# -3 dB crossing to find and nothing to fall from; the run is refused (ValueError), not read as a
# bandwidth.
def test_transfer_of_a_single_frequency_is_refused() -> None:
    run = single_pole(TB, 0.85, 1e9)
    one = {
        name: replace(sweep, x=sweep.x[:1], v={net: values[:1] for net, values in sweep.v.items()})
        if sweep.kind in (SweepKind.AC, SweepKind.XF)
        else sweep
        for name, sweep in run.sweeps.items()
    }
    with pytest.raises(ValueError):
        analyze_transfer([replace(run, sweeps=one)])


# --- analyze_impedance ------------------------------------------------------------------------


# A source follower's output impedance ([Razavi-Analog] Eq. (6.64), p. 192):
# Z_sf = (R_S C_GS s + 1) / (g_m + C_GS s), 1/g_m at low frequency rising to R_S (inductive),
# here 1/g_m = 1.5 kohm, R_S = 20 kohm, C_GS = 10 fF, with the bench's 100 fF load across it:
# Z_node = Z_sf || 1 / (s C_L), the output per ampere of the test current into it (xf). The
# analysis takes the load's admittance s C_L away, leaving the follower's own Z_sf, as Eq. (6.64)
# has it: |Z_sf(f)| to rounding (rel 1e-9; at 100 GHz the load's admittance is 1300 times the
# follower's, three digits of the sixteen lost) at two input levels; rout_ohm is |Z_sf| at 1 kHz,
# 1/g_m within 1e-6.
def test_impedance_of_a_source_follower_with_its_load() -> None:
    gm, rs, cgs, cload = 1 / 1500.0, 20e3, 10e-15, TB.cload_f

    def follower(f: np.ndarray) -> np.ndarray:
        s = 2j * np.pi * f
        return (rs * cgs * s + 1) / (gm + cgs * s)

    def node(f: np.ndarray) -> np.ndarray:
        return 1 / (1 / follower(f) + 2j * np.pi * f * cload)

    benches = [replace(TB, vin_v=vin) for vin in (0.8, 0.9)]
    impedance = analyze_impedance([impedance_run(tb, node) for tb in benches])
    expected = np.abs(follower(frequency_axis(TB)))
    # the node's own impedance, the load across it, is far from it: 160 ohm against 13.8 kohm at 10 GHz
    assert abs(node(np.asarray([1e10]))[0]) < 0.02 * abs(follower(np.asarray([1e10]))[0])
    assert impedance.zout_ohm.shape == (2, 161)
    assert impedance.zout_ohm[0] == pytest.approx(expected, rel=1e-9)
    assert impedance.zout_ohm[1] == pytest.approx(expected, rel=1e-9)
    assert impedance.rout_ohm == pytest.approx([expected[0]] * 2, rel=1e-9)
    assert impedance.rout_ohm[0] == pytest.approx(1500.0, rel=1e-6)
    assert impedance.vin_v == pytest.approx([0.8, 0.9])
    assert impedance.frequency_hz == pytest.approx(frequency_axis(TB), rel=1e-12)
    with pytest.raises(ValueError, match="on the input"):
        analyze_impedance([step_run(step_tb(), exponential(100e-12), exponential(100e-12))])


# A purely resistive follower, Z_sf = R = 2.2 kohm at every frequency ([Razavi-Analog] Eq. (3.93),
# p. 71: a follower's output resistance), behind the bench's 100 fF load (the node presents
# R || 1 / (s C_L)): its impedance is R at every frequency, and at a sweep of one frequency
# (1 kHz alone) the output resistance is that one value, R (rel 1e-12: the load's admittance at
# 1 kHz is 1.4e-6 of 1 / R, taken away exactly). Runs on different frequencies are refused, as the transfer's are.
def test_impedance_of_one_frequency_and_unequal_sweeps() -> None:
    resistance = 2200.0

    def node(f: np.ndarray) -> np.ndarray:
        return 1 / (1 / resistance + 2j * np.pi * f * TB.cload_f)

    run = impedance_run(TB, node)
    assert analyze_impedance([run]).zout_ohm[0] == pytest.approx(np.full(161, resistance), rel=1e-12)
    xf = run.sweeps["xf"]
    one = replace(run, sweeps={**run.sweeps, "xf": replace(xf, x=xf.x[:1], v={k: v[:1] for k, v in xf.v.items()})})
    single = analyze_impedance([one])
    assert single.rout_ohm == pytest.approx([resistance], rel=1e-12)
    assert single.zout_ohm.shape == (1, 1)
    with pytest.raises(ValueError, match="one frequency sweep"):
        analyze_impedance([run, impedance_run(replace(TB, points_per_decade=10), node)])


# --- analyze_slew -----------------------------------------------------------------------------


# A single-pole (linear-settling) step response ([Razavi-Analog] Eq. (9.61), p. 391), from the
# middle of each input edge: rising with tau_r = 100 ps, falling with tau_f = 400 ps, between
# 0.45 V and 0.75 V (0.3 V below the input's 0.75 V and 1.05 V), on a simulator's axis, and the
# same shape at half the step.
# - 10 % to 90 % takes tau ln 9 ([Baker] Eq. (2.26), p. 49: t_90% - t_10% = RC ln 9): the rise and
#   fall times, 219.7 ps and 878.9 ps.
# - the slope step / tau exp(-s / tau) is in proportion to the step at every s ([Razavi-Analog]
#   Eq. (9.58), p. 390): at half the step every slope halves, the edge does not slew, and neither
#   edge has a slew rate: NaN in both rows.
# - 1 % settling takes tau ln 100 ([Razavi-Analog] Eq. (9.11), p. 347): 460.5 ps, 1.842 ns.
# - an exponential never passes its final level: no overshoot, exactly 0.
# - the supply current is a 20 uA bias plus C_L dv/dt on the rising edge alone (the input device
#   charges the load from the supply; the bias current discharges it): its average over one
#   period from the rise is 20 uA + C_L step / T = 20 uA + 100 fF 0.3 V / 20 ns = 21.5 uA.
# Tolerances: the levels settle to exp(-40) before each edge: abs 1e-9 V. Crossings are linearly
# interpolated over steps of at most 1 ps, a time error below h^2 / (8 tau) = 1.3 fs: rel 1e-4.
# The current's trapezoid over the step where dv/dt jumps errs by up to h / (2 tau_r) of the
# 1.5 uA: rel 1e-3 of the average.
def test_slew_of_a_single_pole_step() -> None:
    tb = step_tb()
    tau_rise, tau_fall, cload, step = 100e-12, 400e-12, 100e-15, 0.3
    rise_mid = tb.step_period_s / 4 + tb.transition_time_s / 2

    def supply_current(time_s: np.ndarray) -> np.ndarray:
        rising = (time_s >= rise_mid) & (time_s < 3 * tb.step_period_s / 4)
        slope = step / tau_rise * np.exp(-np.clip(time_s - rise_mid, 0.0, None) / tau_rise)
        return 20e-6 + cload * np.where(rising, slope, 0.0)

    slew = analyze_slew(step_pair(tb, exponential(tau_rise), exponential(tau_fall), idd=supply_current))
    assert slew.vol_v[0] == pytest.approx(0.45, abs=1e-9)
    assert slew.voh_v[0] == pytest.approx(0.75, abs=1e-9)
    assert slew.vin_v[0] == 0.9 and slew.step_v[0] == 0.3
    assert np.isnan(slew.slew_rate_rise_v_per_s).all() and np.isnan(slew.slew_rate_fall_v_per_s).all()
    assert slew.rise_time_s[0] == pytest.approx(tau_rise * math.log(9), rel=1e-4)
    assert slew.fall_time_s[0] == pytest.approx(tau_fall * math.log(9), rel=1e-4)
    assert slew.settling_rise_s[0] == pytest.approx(tau_rise * math.log(100), rel=1e-4)
    assert slew.settling_fall_s[0] == pytest.approx(tau_fall * math.log(100), rel=1e-4)
    assert slew.overshoot_rise[0] == 0.0 and slew.overshoot_fall[0] == 0.0
    assert slew.idd_a[0] == pytest.approx(20e-6 + cload * step / tb.step_period_s, rel=1e-3)


# A slewing output ([Razavi-Analog] Sec. 9.9, p. 391: slewing, the output a ramp of constant
# slope, the slew rate, the same whatever the step, p. 392): rising at 0.7 V/ns, falling at the
# bias current over the load, 20 uA / 100 fF = 0.2 V/ns, at the step and at half of it. The slew
# rate is the ramp's slope in both rows, its 10-90 % time 0.8 step / slope (342.9 ps, 1.2 ns); it
# is within 1 % of the step at 0.99 step / slope after the edge's middle: 424.3 ps rising,
# 1.485 ns falling. A ramp is linear between samples (its corner lies samples away from either
# crossing), so interpolation is exact: rel 1e-6.
def test_slew_of_a_ramp() -> None:
    tb = step_tb()
    rising, falling, half = 0.7e9, 20e-6 / 100e-15, tb.step_v / 2
    slew = analyze_slew(
        step_pair(
            tb,
            ramp(rising, tb.step_v),
            ramp(falling, tb.step_v),
            half_rise=ramp(rising, half),
            half_fall=ramp(falling, half),
        )
    )
    assert slew.slew_rate_rise_v_per_s == pytest.approx([rising, rising], rel=1e-6)
    assert slew.slew_rate_fall_v_per_s == pytest.approx([-falling, -falling], rel=1e-6)
    assert slew.rise_time_s[0] == pytest.approx(0.8 * tb.step_v / rising, rel=1e-6)
    assert slew.fall_time_s[0] == pytest.approx(0.8 * tb.step_v / falling, rel=1e-6)
    assert slew.settling_rise_s[0] == pytest.approx(0.99 * tb.step_v / rising, rel=1e-6)
    assert slew.settling_fall_s[0] == pytest.approx(0.99 * tb.step_v / falling, rel=1e-6)
    assert slew.overshoot_rise[0] == 0.0 and slew.overshoot_fall[0] == 0.0


# A fall slower than a quarter period: a single pole of tau = 1.5 ns would settle to 1 % of its
# step in tau ln 100 = 6.908 ns ([Razavi-Analog] Eq. (9.11), p. 347), past the 5 ns a quarter
# period leaves; the fall has half a period (10 ns) to settle, as the rise has. The rise is fast
# (100 ps), so the level the fall starts from is settled. The fall's final level is its own, the
# output's average over the record's last nanosecond (s1 = 8.995 ns to s2 = 9.995 ns after the
# fall's middle): A = tau (exp(-s1 / tau) - exp(-s2 / tau)) / (s2 - s1) = 1.815e-3 of the step
# above the level before the rise. The output is A + 0.01 (1 - A) of the step from it, inside the
# 1 % band, at s = -tau ln(0.01 + 0.99 A) = 6.660 ns. Interpolation over steps of at most 30 ps on
# a 1.5 ns pole: within h^2 / (8 tau) = 75 fs, rel 1e-4.
def test_slew_of_a_fall_slower_than_a_quarter_period() -> None:
    tb = step_tb()
    tau = 1.5e-9
    slew = analyze_slew(step_pair(tb, exponential(100e-12), exponential(tau)))
    s1, s2 = 8.995e-9, 9.995e-9
    final = tau * (math.exp(-s1 / tau) - math.exp(-s2 / tau)) / (s2 - s1)
    assert slew.settling_fall_s[0] == pytest.approx(-tau * math.log(0.01 + 0.99 * final), rel=1e-4)


# The fall settles to its own level, a residue of 2 uV under the level before the rise (the
# simulator's tolerance leaves such residues), monotonically: a single pole of tau = 100 ps from
# the high level to 0.45 V - 2 uV. Measured against its own settled level (the record's last
# nanosecond, there to exp(-89) of the step) it never passes it: no overshoot, exactly 0, where
# against the level before the rise it would pass it by 2 uV, 6.7e-6 of the step. Its 10-90 %
# time is tau ln 9 and its 1 % settling tau ln 100 of its own step ([Razavi-Analog] Eq. (9.11),
# p. 347); the output low level V_OL ([Baker] Fig. 10.9, p. 333) stays the level before the rise,
# 0.45 V. Crossings interpolated over steps of at most 1 ps: rel 1e-4.
def test_the_fall_settles_to_its_own_level() -> None:
    tb = step_tb()
    tau, residue = 100e-12, 2e-6
    under = 1 + residue / tb.step_v
    slew = analyze_slew(step_pair(tb, exponential(tau), lambda s: under * (1 - np.exp(-s / tau))))
    assert slew.overshoot_fall[0] == 0.0
    assert slew.vol_v[0] == pytest.approx(0.45, abs=1e-12)
    assert slew.fall_time_s[0] == pytest.approx(tau * math.log(9), rel=1e-4)
    assert slew.settling_fall_s[0] == pytest.approx(tau * math.log(100), rel=1e-4)


# A strobed record, as Spectre writes the step run: every 5 ps from 0 to tran_stop_s = 25 ns, each
# time the sum of the strobes before it, so the record ends at 24.999999999999016 ns, 1e-21 s short
# of tran_stop_s (the bench's real step run ends there too). Those 1e-21 s change no level and no
# edge: the analysis reads the closed forms of a single pole of tau = 400 ps on both edges
# ([Razavi-Analog] Eq. (9.61), p. 391: linear settling, an exponential step response):
# - 10 % to 90 % in tau ln 9 = 878.9 ps ([Baker] Eq. (2.26), p. 49);
# - 1 % settling in tau ln 100 = 1.842 ns ([Razavi-Analog] Eq. (9.11), p. 347);
# - no slew rate: the slope scales with the step (the half step's is half), NaN;
# - no overshoot (an exponential never passes its final level); the supply's constant 40 uA;
# - the levels 0.45 V and 0.75 V, each settled to exp(-12.5) of the step before the next edge.
# Tolerances: linear interpolation over 5 ps strobes errs by at most h^2 / (8 tau) = 7.8 fs at a
# crossing, rel 1e-4; the fall's level reads exp(-25 ns / 400 ps) of the step from its final one
# at worst: overshoot abs 1e-12, levels abs 2e-6 V (exp(-12.5) of 0.3 V before the fall).
def test_slew_of_a_strobed_record_ending_short_of_the_stop_time() -> None:
    tb = step_tb()
    tau = 400e-12
    time_s = strobed_axis(tb)
    assert 0 < tb.tran_stop_s - time_s[-1] < 1e-20
    slew = analyze_slew(step_pair(tb, exponential(tau), exponential(tau), time_s=time_s))
    assert slew.vol_v[0] == pytest.approx(0.45, abs=2e-6)
    assert slew.voh_v[0] == pytest.approx(0.75, abs=2e-6)
    assert slew.rise_time_s[0] == pytest.approx(tau * math.log(9), rel=1e-4)
    assert slew.fall_time_s[0] == pytest.approx(tau * math.log(9), rel=1e-4)
    assert slew.settling_rise_s[0] == pytest.approx(tau * math.log(100), rel=1e-4)
    assert slew.settling_fall_s[0] == pytest.approx(tau * math.log(100), rel=1e-4)
    assert math.isnan(slew.slew_rate_rise_v_per_s[0]) and math.isnan(slew.slew_rate_fall_v_per_s[0])
    assert slew.overshoot_rise[0] == pytest.approx(0.0, abs=1e-12)
    assert slew.overshoot_fall[0] == pytest.approx(0.0, abs=1e-12)
    assert slew.idd_a[0] == pytest.approx(40e-6, rel=1e-12)


# A record cut short, as a simulator that stopped early leaves: one sample at 0, the step run
# ending at 12 ns (between the rise and the fall), or 100 ps (twenty strobes) before tran_stop_s.
# A record ending more than one strobe (waveform_sample_interval_s) short of tran_stop_s is cut
# short: the fall's settling, and with the single sample every level, lies outside it, and the run
# is refused, not read as a step.
@pytest.mark.parametrize(
    "stop_s", [0.0, 12e-9, 24.9e-9], ids=["one_sample", "ends_before_the_fall", "ends_100ps_short_of_the_stop"]
)
def test_slew_refuses_a_record_cut_short(stop_s: float) -> None:
    tb = step_tb()
    time_s = simulator_axis(tb)
    time_s = time_s[time_s <= stop_s]
    with pytest.raises(ValueError):
        analyze_slew(step_pair(tb, exponential(100e-12), exponential(100e-12), time_s=time_s))


# A slewing edge that ends linearly, as a follower's does once its device turns back on: a ramp of
# slope S = 0.2 V/ns to 80 % of the step, then the last 20 % as an exponential whose slope at the
# knee is S, tau = 0.2 step / S = 300 ps (at half the step the same ramp, its tail's tau 150 ps).
# The slew rate is S, the ramp's slope ([Razavi-Analog] Sec. 9.9, p. 391). The 10-90 % time is
# 0.7 step / S + tau ln 2 = (0.7 + 0.2 ln 2) step / S, so the average slope over it,
# 0.8 / (0.7 + 0.2 ln 2) S = 0.954 S, reads 4.6 % short of the slew rate. The band from 10 % to
# 90 % spans 1.258 ns, the ramp the first 1.05 ns of it: a quarter of the band (315 ps) on the
# ramp alone holds one slope, exactly S, rel 1e-6.
def test_slew_rate_is_the_ramp_slope_not_the_average() -> None:
    tb = step_tb()
    slope, step = 0.2e9, tb.step_v

    def slewing(size: float) -> Response:
        knee, tau = 0.8 * size / slope, 0.2 * size / slope
        return lambda s: np.where(s < knee, slope * s / size, 1 - 0.2 * np.exp(-(s - knee) / tau))

    full, half = slewing(step), slewing(step / 2)
    slew = analyze_slew(step_pair(tb, full, full, half_rise=half, half_fall=half))
    assert slew.slew_rate_rise_v_per_s[0] == pytest.approx(slope, rel=1e-6)
    assert slew.slew_rate_fall_v_per_s[0] == pytest.approx(-slope, rel=1e-6)
    transition = (0.7 + 0.2 * math.log(2)) * step / slope
    assert slew.rise_time_s[0] == pytest.approx(transition, rel=1e-4)
    assert 0.8 * step / slew.rise_time_s[0] == pytest.approx(0.954 * slope, rel=1e-3)


# The input edge's own coupling (through the input device's gate-source capacitance) kicks the
# output before the current-limited ramp: s(t) = S t + K (1 - exp(-t / tau_k)), S = 0.2 V/ns,
# K = 10 % of the step, tau_k = 30 ps, its share of the step capped at 1; at half the step K halves
# (the coupling is linear) and S holds. The slope S + (K / tau_k) exp(-t / tau_k) starts at
# 1.2 V/ns, six times the ramp's, and falls to within exp(-10) K / tau_k = 4.5e-5 V/ns of S by
# 300 ps. [Razavi-Analog] Sec. 9.9, p. 391: the slew rate is the slope of the ramp, S. The band
# runs from the 10 % level (39.8 ps, past the input edge's end at 5 ps) to the 90 % level
# (1.2 ns): a quarter of it (290 ps) where the kick has decayed (past 0.6 ns, to below
# exp(-20) K / tau_k) holds one slope, S, rel 1e-6; the steepest slope in the band, 0.465 V/ns at
# its 10 % level, would read 2.3 times S.
def test_slew_rate_is_the_ramp_after_a_fast_kick() -> None:
    tb = step_tb()
    slope, tau = 0.2e9, 30e-12

    def kicked(size: float) -> Response:
        return lambda s: np.minimum((slope * s + 0.1 * size * (1 - np.exp(-s / tau))) / size, 1.0)

    full, half = kicked(tb.step_v), kicked(tb.step_v / 2)
    slew = analyze_slew(step_pair(tb, full, full, half_rise=half, half_fall=half))
    assert slew.slew_rate_rise_v_per_s == pytest.approx([slope, slope], rel=1e-6)
    assert slew.slew_rate_fall_v_per_s == pytest.approx([-slope, -slope], rel=1e-6)


# An NMOS source follower's step: its device charges the load on the rise, linearly (a single pole
# of tau = 100 ps), and only the bias current discharges it on the fall, a ramp of
# I / C_L = 20 uA / 100 fF = 0.2 V/ns ([Baker] Sec. 21.2.4, p. 703). At half the step the rise's
# slope halves ([Razavi-Analog] Eq. (9.58), p. 390), the fall's holds (Sec. 9.9, p. 392): the rise
# has no slew rate (NaN), the fall's is -0.2 V/ns, exactly (a ramp: rel 1e-6), in both rows; the
# rise is told by its 10-90 % time, tau ln 9 = 219.7 ps ([Baker] Eq. (2.26), p. 49), and its
# 1 % settling, tau ln 100 = 460.5 ps ([Razavi-Analog] Eq. (9.11), p. 347).
def test_slew_rate_only_on_the_edge_that_slews() -> None:
    tb = step_tb()
    falling = 20e-6 / 100e-15
    slew = analyze_slew(
        step_pair(
            tb,
            exponential(100e-12),
            ramp(falling, tb.step_v),
            half_fall=ramp(falling, tb.step_v / 2),
        )
    )
    assert np.isnan(slew.slew_rate_rise_v_per_s).all()
    assert slew.slew_rate_fall_v_per_s == pytest.approx([-falling, -falling], rel=1e-6)
    assert slew.rise_time_s[0] == pytest.approx(100e-12 * math.log(9), rel=1e-4)
    assert slew.settling_rise_s[0] == pytest.approx(100e-12 * math.log(100), rel=1e-4)


# A monotonic edge has no overshoot: a single pole of tau = 1 ns rises toward its final level and
# never passes it. Its settled level is the output's average over the window's last nanosecond,
# where the output is still rising (by step exp(-9) = 1e-4 of the step), so the window's maximum,
# at its very end, lies above that average; the overshoot is taken before that interval, where the
# output is below its final level throughout, and clamped at 0: exactly 0 on both edges.
def test_a_monotonic_edge_has_no_overshoot() -> None:
    tb = step_tb()
    slew = analyze_slew(step_pair(tb, exponential(1e-9), exponential(1e-9)))
    assert slew.overshoot_rise[0] == 0.0 and slew.overshoot_fall[0] == 0.0


# not in the reference texts: overshoot, a fraction of the step (the calculator's overshoot), 0
# where the output passes its final level by no more than Spectre's absolute voltage tolerance,
# 1 uV (the analysis's resolution). A single pole of tau = 100 ps on both edges whose settled
# plateau (from 2 ns after each edge's middle, where the exponential is below exp(-20) = 2e-9 of
# the step) carries 1e-15 V of alternating rounding noise: the output passes its final level by
# at most 1e-15 V, far under 1 uV: the overshoot is exactly 0.0 on both edges, a positive zero.
def test_rounding_on_a_settled_level_is_no_overshoot() -> None:
    tb = step_tb()
    time_s = np.linspace(0.0, tb.tran_stop_s, 25001)

    def noisy(s: np.ndarray) -> np.ndarray:
        settled = 1.0 + 1e-15 / tb.step_v * np.cos(np.pi * np.arange(len(s)))
        return np.where(s > 2e-9, settled, 1 - np.exp(-s / 100e-12))

    slew = analyze_slew(step_pair(tb, noisy, noisy, time_s=time_s))
    for value in (slew.overshoot_rise[0], slew.overshoot_fall[0]):
        assert value == 0.0 and math.copysign(1.0, value) == 1.0


# An output still creeping at the window's end: half the step at once (a 300 ps pole), half
# through a 4 ns pole. The final level's interval is the last nanosecond before the fall's input
# edge, s = 8.995 ns to 9.995 ns after the rising edge's middle. The 4 ns term's average over
# [a, b] is 0.5 tau (exp(-a / tau) - exp(-b / tau)) / (b - a), so twice the difference of the
# interval's halves (its drift) is 1.166 % of the step, more than the 1 % band, although the output
# stays within 0.61 % of its average there: its level there is no final value, and the rising
# settling is NaN. The fall, to the level before the rise (a DC level), a single 100 ps pole,
# settles (from the level the rise reached).
def test_slew_of_an_output_still_moving_at_the_window_end() -> None:
    tb = step_tb()

    def creeping(s: np.ndarray) -> np.ndarray:
        return 1 - 0.5 * np.exp(-s / 300e-12) - 0.5 * np.exp(-s / 4e-9)

    def tail(a: float, b: float) -> float:
        return 0.5 * 4.0 * (math.exp(-a / 4.0) - math.exp(-b / 4.0)) / (b - a)

    slew = analyze_slew(step_pair(tb, creeping, exponential(100e-12)))
    assert 2 * (tail(8.995, 9.495) - tail(9.495, 9.995)) == pytest.approx(0.011657, abs=1e-6)
    assert math.isnan(slew.settling_rise_s[0])
    assert 0 < slew.settling_fall_s[0] < 1e-9


# An underdamped second-order step ([Razavi-Analog] Eq. (16.21), p. 662), zeta = 0.5,
# fn = 5 GHz: r(t) = 1 - exp(-zeta wn t) [cos(wd t) + zeta / sqrt(1 - zeta^2) sin(wd t)],
# wd = wn sqrt(1 - zeta^2). Its derivative is wn / sqrt(1 - zeta^2) exp(-zeta wn t) sin(wd t),
# zero first at wd t = pi, where r = 1 + exp(-pi zeta / sqrt(1 - zeta^2)): the overshoot is
# exp(-pi zeta / sqrt(1 - zeta^2)) = 0.16303 of the step, on both edges alike. The 1 % settling
# time is the last time |r - 1| exceeds 0.01, found here by bisection on r itself (about 0.3 ns).
# Tolerances: the sampled peak is within |r''| h^2 / 8 = 2e-5 of the step of the true one at
# h = 1 ps: rel 1e-3; the settling crossing is interpolated within one step: abs 1 ps.
def test_slew_of_an_underdamped_step() -> None:
    tb = step_tb()
    zeta, wn = 0.5, 2 * math.pi * 5e9
    wd = wn * math.sqrt(1 - zeta**2)

    def response(s: np.ndarray) -> np.ndarray:
        return 1 - np.exp(-zeta * wn * s) * (np.cos(wd * s) + zeta / math.sqrt(1 - zeta**2) * np.sin(wd * s))

    # the last exit from the 1 % band: on a 10 fs grid, then by bisection on the closed form
    dense = np.arange(0.0, 2e-9, 1e-14)
    outside = np.flatnonzero(np.abs(response(dense) - 1) > 0.01)
    low, high = float(dense[outside[-1]]), float(dense[outside[-1] + 1])
    for _ in range(60):
        middle = (low + high) / 2
        low, high = (middle, high) if abs(float(response(np.asarray([middle]))[0]) - 1) > 0.01 else (low, middle)

    slew = analyze_slew(step_pair(tb, response, response))
    peak = math.exp(-math.pi * zeta / math.sqrt(1 - zeta**2))
    assert slew.overshoot_rise[0] == pytest.approx(peak, rel=1e-3)
    assert slew.overshoot_fall[0] == pytest.approx(peak, rel=1e-3)
    assert slew.settling_rise_s[0] == pytest.approx(high, abs=1e-12)
    assert slew.settling_fall_s[0] == pytest.approx(high, abs=1e-12)


def bisect(function: Callable[[float], float], low: float, high: float) -> float:
    """The root of ``function`` between ``low`` and ``high`` (of opposite signs there), by
    bisection to the float's resolution: how a test finds a closed form's crossing on its own."""
    below = function(low) < 0
    for _ in range(200):
        middle = (low + high) / 2
        low, high = (middle, high) if (function(middle) < 0) == below else (low, middle)
    return (low + high) / 2


# The underdamped step of test_slew_of_an_underdamped_step ([Razavi-Analog] Eq. (16.21), p. 662,
# zeta = 0.5, fn = 5 GHz) on both edges: the rise and fall times are 10 % to 90 % of the step
# ([Baker] Fig. 10.9, p. 333), its first crossings of 0.1 and 0.9, both before the first peak at
# wd t = pi (115.5 ps), after which r stays above 1 - exp(-2 pi zeta / sqrt(1 - zeta^2)) = 0.973
# and never crosses either level again. Found by bisection on r itself over [0, pi / wd]: 15.54 ps
# and 67.67 ps, 52.13 ps apart. Linear interpolation over steps of at most 1 ps errs by
# h^2 |r''| / (8 |r'|) at a crossing, at most 8 fs at the 10 % level (r''/r' near 1 / t there):
# rel 1e-3 of 52 ps. A linear response: no slew rate on either edge (NaN).
def test_transition_times_of_an_underdamped_step() -> None:
    tb = step_tb()
    zeta, wn = 0.5, 2 * math.pi * 5e9
    wd = wn * math.sqrt(1 - zeta**2)

    def closed(t: float) -> float:
        return 1 - math.exp(-zeta * wn * t) * (math.cos(wd * t) + zeta / math.sqrt(1 - zeta**2) * math.sin(wd * t))

    def response(s: np.ndarray) -> np.ndarray:
        return 1 - np.exp(-zeta * wn * s) * (np.cos(wd * s) + zeta / math.sqrt(1 - zeta**2) * np.sin(wd * s))

    t10, t90 = (bisect(lambda t, level=level: closed(t) - level, 0.0, math.pi / wd) for level in (0.1, 0.9))
    assert (t10, t90) == pytest.approx((15.54e-12, 67.67e-12), abs=0.01e-12)
    slew = analyze_slew(step_pair(tb, response, response))
    assert slew.rise_time_s[0] == pytest.approx(t90 - t10, rel=1e-3)
    assert slew.fall_time_s[0] == pytest.approx(t90 - t10, rel=1e-3)
    assert np.isnan(slew.slew_rate_rise_v_per_s).all() and np.isnan(slew.slew_rate_fall_v_per_s).all()


# Two coincident poles, the critically damped case of the second-order response ([Razavi-Analog]
# Eq. (16.16), p. 662, zeta = 1: H(s) = wn^2 / (s + wn)^2, tau = 1 / wn): the inverse Laplace
# transform of H(s) / s is r(t) = 1 - (1 + x) exp(-x), x = t / tau, rising with tau = 100 ps and
# falling with tau = 250 ps. Solved by bisection on r itself:
# - r = 0.1 at x = 0.53181, r = 0.9 at x = 3.88972: rise and fall times 3.35791 tau ([Baker]
#   Fig. 10.9, p. 333: 10 % to 90 %), 335.8 ps and 839.5 ps;
# - |r - 1| = (1 + x) exp(-x) = 0.01 at x = 6.63835, after which it only falls: 1 % settling
#   ([Razavi-ADC] Sec. 8.2.2, p. 150) 663.8 ps and 1.660 ns from the input edge's middle;
# - r' = x exp(-x) / tau >= 0: monotonic, no overshoot, exactly 0;
# - linear: at half the step every slope halves ([Razavi-Analog] Eq. (9.58), p. 390), its ramp's
#   slope by 0.5 and its chord over a tenth to three tenths of the half step (5 % to 15 % of the
#   full step, 10 % to 30 % of the half) by (x15 - x5) / (x30 - x10) = 0.580, both under
#   sqrt(1/2): no slew rate, NaN in both rows.
# Tolerances: r''/r' = (1 - x) / (x tau) is under 1 / tau at both levels, so interpolation over
# steps of at most 1 ps errs by under h^2 / (8 tau) = 1.3 fs at a crossing: rel 1e-4.
def test_slew_of_a_critically_damped_two_pole_step() -> None:
    tb = step_tb()
    tau_rise, tau_fall = 100e-12, 250e-12

    def closed(x: float) -> float:
        return 1 - (1 + x) * math.exp(-x)

    def two_poles(tau_s: float) -> Response:
        return lambda s: 1 - (1 + s / tau_s) * np.exp(-s / tau_s)

    x10, x90 = (bisect(lambda x, level=level: closed(x) - level, 0.0, 20.0) for level in (0.1, 0.9))
    x_settled = bisect(lambda x: (1 + x) * math.exp(-x) - 0.01, 1.0, 20.0)
    assert (x10, x90, x_settled) == pytest.approx((0.53181, 3.88972, 6.63835), abs=1e-5)
    slew = analyze_slew(step_pair(tb, two_poles(tau_rise), two_poles(tau_fall)))
    assert slew.rise_time_s[0] == pytest.approx((x90 - x10) * tau_rise, rel=1e-4)
    assert slew.fall_time_s[0] == pytest.approx((x90 - x10) * tau_fall, rel=1e-4)
    assert slew.settling_rise_s[0] == pytest.approx(x_settled * tau_rise, rel=1e-4)
    assert slew.settling_fall_s[0] == pytest.approx(x_settled * tau_fall, rel=1e-4)
    assert slew.overshoot_rise[0] == 0.0 and slew.overshoot_fall[0] == 0.0
    assert np.isnan(slew.slew_rate_rise_v_per_s).all() and np.isnan(slew.slew_rate_fall_v_per_s).all()


# not in the reference texts: overshoot, how far the output passes its final level, a fraction of
# the step, resolved only beyond Spectre's absolute voltage tolerance, 1 uV (types.AnalysisSlew), a
# voltage, not a share of the step. A fast single pole (tau = 40 ps) with a Gaussian bump of d volts
# 1 ns after each edge's middle, 150 ps wide: r(s) = 1 - exp(-s / tau) + (d / step)
# exp(-((s - 1 ns) / 150 ps)^2), up on the rise and down on the fall. At the bump's peak the pole
# is exp(-25) = 1.4e-11 of the step (4e-12 V) from its final level, and by the final level's
# interval (9 ns on) the bump is below exp(-2800): the output passes its final level by d alone,
# on both edges, and the overshoot is d over the 0.3 V step.
# - d = 3 uV, past the tolerance: 1e-5 of the step. The sampled peak (steps of at most 1 ps) is
#   within h^2 / (4 w^2) = 1.1e-5 of d of the true one: rel 1e-4.
# - d = 0.5 uV, within the tolerance: 0, although it is 1.7e-6 of the step (more than a millionth
#   of it: the threshold is the voltage the simulator resolves, not a share of the step).
@pytest.mark.parametrize(("bump_v", "expected"), [(3e-6, 1e-5), (0.5e-6, 0.0)], ids=["3uV", "0.5uV"])
def test_overshoot_resolves_a_microvolt_of_the_output(bump_v: float, expected: float) -> None:
    tb = step_tb()

    def bumped(size: float) -> Response:
        return lambda s: 1 - np.exp(-s / 40e-12) + bump_v / size * np.exp(-(((s - 1e-9) / 150e-12) ** 2))

    full, half = bumped(tb.step_v), bumped(tb.step_v / 2)
    slew = analyze_slew(step_pair(tb, full, full, half_rise=half, half_fall=half))
    if expected:
        assert slew.overshoot_rise[0] == pytest.approx(expected, rel=1e-4)
        assert slew.overshoot_fall[0] == pytest.approx(expected, rel=1e-4)
    else:
        assert slew.overshoot_rise[0] == 0.0 and slew.overshoot_fall[0] == 0.0


# An output that rings on forever: the single-pole rise (tau = 100 ps) plus a 6 mV (2 % of the
# step) cosine of 100 ps period that never decays. It never stays within 1 % (3 mV) of its final
# level, and the record's rising window ends outside the band (0.02 cos(2 pi 0.05) = 1.9 % of the
# step at its end), so its rising settling is NaN; the settled level before the fall is the mean
# over a whole number of the cosine's periods (the 1 ns before the edge: ten), the final level
# itself, so the overshoot is the cosine's amplitude over the step, 0.02 (sampled every 1 ps, its
# peaks within 0.5 ps of a sample: within 1 - cos(pi / 100) = 5e-4 of it, rel 2e-3).
def test_slew_of_an_output_that_never_settles() -> None:
    tb = step_tb()
    amplitude = 0.02

    def ringing(s: np.ndarray) -> np.ndarray:
        return 1 - np.exp(-s / 100e-12) + amplitude * np.cos(2 * np.pi * s / 100e-12)

    time_s = np.linspace(0.0, tb.tran_stop_s, 25001)
    slew = analyze_slew(step_pair(tb, ringing, exponential(100e-12), time_s=time_s))
    assert math.isnan(slew.settling_rise_s[0])
    assert slew.overshoot_rise[0] == pytest.approx(amplitude, rel=2e-3)
    assert slew.voh_v[0] == pytest.approx(0.75, abs=1e-5)


# The same ringing as a sine: it never settles either (|r - 1| reaches 0.02 of the step every
# 100 ps to the end), but the record's rising window happens to end inside the 1 % band
# (0.02 sin(2 pi 99.95) = -0.62 % of the step at 9.995 ns after the edge), and only for its last
# 3.3 ps (from 9.9917 ns, where the sine passes -0.5). Its final level is known (the halves of
# the final level's interval each hold five whole periods: no drift), but it enters the band for
# good only inside that interval, the last nanosecond of the window: it has not settled in the
# window, and the settling is NaN, as for the cosine.
def test_slew_of_ringing_that_ends_inside_the_band() -> None:
    tb = step_tb()

    def ringing(s: np.ndarray) -> np.ndarray:
        return 1 - np.exp(-s / 100e-12) + 0.02 * np.sin(2 * np.pi * s / 100e-12)

    time_s = np.linspace(0.0, tb.tran_stop_s, 25001)
    slew = analyze_slew(step_pair(tb, ringing, exponential(100e-12), time_s=time_s))
    assert math.isnan(slew.settling_rise_s[0])


# A single pole (tau = 100 ps) with a lasting ripple of 0.7 % of the step (a 100 ps sine), always
# inside the 1 % band once the exponential has decayed: r(s) = 1 - exp(-s / tau) + 0.007 sin(2 pi
# s / 100 ps). [Razavi-ADC] Sec. 8.2.2, p. 150: the settling time is where the output enters the
# band about its final value and stays in it. The final level, the average over the last
# nanosecond (ten whole periods), is the exponential's asymptote itself, and the halves of that
# interval (five periods each) do not drift; the last exit from |r - 1| <= 0.01, found by
# bisection on r itself, is 0.578 ns after the edge's middle. Linear interpolation on 1 ps
# samples: within one sample, abs 1 ps.
def test_slew_of_a_ripple_inside_the_band() -> None:
    tb = step_tb()

    def ripple(s: np.ndarray) -> np.ndarray:
        return 1 - np.exp(-s / 100e-12) + 0.007 * np.sin(2 * np.pi * s / 100e-12)

    dense = np.arange(0.0, 5e-9, 1e-14)
    outside = np.flatnonzero(np.abs(ripple(dense) - 1) > 0.01)
    low, high = float(dense[outside[-1]]), float(dense[outside[-1] + 1])
    for _ in range(60):
        middle = (low + high) / 2
        low, high = (middle, high) if abs(float(ripple(np.asarray([middle]))[0]) - 1) > 0.01 else (low, middle)
    assert high == pytest.approx(0.578e-9, abs=1e-12)

    time_s = np.linspace(0.0, tb.tran_stop_s, 25001)
    slew = analyze_slew(step_pair(tb, ripple, ripple, time_s=time_s))
    assert slew.settling_rise_s[0] == pytest.approx(high, abs=1e-12)
    assert slew.settling_fall_s[0] == pytest.approx(high, abs=1e-12)


# An output that does not follow: stuck at its low level, or moving 5 % of the step (under the
# tenth the analysis asks of an edge) and back. Its levels are read, its edges are NaN: there is
# no transition to time.
def test_slew_of_an_output_that_does_not_follow() -> None:
    tb = step_tb()
    stuck = analyze_slew(step_pair(tb, constant(0.0), constant(1.0)))
    assert stuck.vol_v[0] == pytest.approx(0.45) and stuck.voh_v[0] == pytest.approx(0.45)
    partial = analyze_slew(step_pair(tb, constant(0.05), constant(1.0)))
    assert partial.voh_v[0] - partial.vol_v[0] == pytest.approx(0.05 * 0.3)
    for result in (stuck, partial):
        edges = (
            result.slew_rate_rise_v_per_s,
            result.slew_rate_fall_v_per_s,
            result.rise_time_s,
            result.fall_time_s,
            result.settling_rise_s,
            result.settling_fall_s,
            result.overshoot_rise,
            result.overshoot_fall,
        )
        assert all(math.isnan(value[0]) for value in edges)


def test_slew_refuses_runs_without_a_step_transient() -> None:
    with pytest.raises(ValueError, match="step run"):
        analyze_slew([single_pole(TB, 0.85, 1e9)])
    empty = Meas(group=None, index=None, dut=TB.params, info=INFO, param=step_tb())
    with pytest.raises(ValueError, match="step run"):
        analyze_slew([empty])
    # one step size alone tells no slewing edge from a linear one
    one = step_run(step_tb(), exponential(100e-12), exponential(100e-12))
    with pytest.raises(ValueError, match="two step sizes"):
        analyze_slew([one, one])


# The slew rate's test of an edge ([Razavi-Analog] Eq. (9.58), p. 390: a linear step response's
# slope is in proportion to the step, so at half the step it halves; Sec. 9.9, p. 391: a slewing
# output's ramp keeps its slope whatever the step). The analysis tells them apart halfway between,
# on a log scale (types.AnalysisSlew): an edge slews where its ramp's slope at half the step is
# more than sqrt(1/2) = 0.7071 of the full step's. Both edges are ramps of 0.2 V/ns at the full
# step (0.3 V) and of r 0.2 V/ns at half of it: at r = 0.75 and 0.72 (above 0.7071) each row's
# slew rate is its own ramp's slope, 0.2 and r 0.2 V/ns (falling: negative); at r = 0.69 and 0.5
# (a linear edge) none, NaN in both rows. The 10-90 % time is 0.8 step / slope either way:
# 1.2 ns at the full step. Ramps are linear between samples: rel 1e-6.
@pytest.mark.parametrize(("ratio", "slews"), [(0.75, True), (0.72, True), (0.69, False), (0.5, False)])
def test_slew_rate_where_the_ramp_holds_at_half_the_step(ratio: float, slews: bool) -> None:
    tb = step_tb()
    slope, half = 0.2e9, tb.step_v / 2
    full_ramp, half_ramp = ramp(slope, tb.step_v), ramp(ratio * slope, half)
    slew = analyze_slew(step_pair(tb, full_ramp, full_ramp, half_rise=half_ramp, half_fall=half_ramp))
    if slews:
        assert slew.slew_rate_rise_v_per_s == pytest.approx([slope, ratio * slope], rel=1e-6)
        assert slew.slew_rate_fall_v_per_s == pytest.approx([-slope, -ratio * slope], rel=1e-6)
    else:
        assert np.isnan(slew.slew_rate_rise_v_per_s).all() and np.isnan(slew.slew_rate_fall_v_per_s).all()
    assert slew.rise_time_s == pytest.approx([0.8 * tb.step_v / slope, 0.8 * half / (ratio * slope)], rel=1e-6)


# Three step sizes (0.3, 0.15 and 0.075 V about 0.9 V) of one slewing output, a ramp of 0.2 V/ns on
# both edges whatever the step ([Razavi-Analog] Sec. 9.9, p. 391): the slew rate is 0.2 V/ns in
# every row (rel 1e-6, ramps); runs at one input level only, and of two step sizes or more.
def test_slew_of_three_step_sizes() -> None:
    benches = [replace(step_tb(), step_v=size) for size in (0.3, 0.15, 0.075)]
    slew = analyze_slew([step_run(tb, ramp(0.2e9, tb.step_v), ramp(0.2e9, tb.step_v)) for tb in benches])
    assert slew.step_v == pytest.approx([0.3, 0.15, 0.075])
    assert slew.slew_rate_rise_v_per_s == pytest.approx([0.2e9] * 3, rel=1e-6)
    assert slew.slew_rate_fall_v_per_s == pytest.approx([-0.2e9] * 3, rel=1e-6)
    other_level = replace(step_tb(), vin_v=0.8, step_v=0.15)
    with pytest.raises(ValueError, match="one input level"):
        analyze_slew(
            [
                step_run(step_tb(), exponential(100e-12), exponential(100e-12)),
                step_run(other_level, exponential(100e-12), exponential(100e-12)),
            ]
        )


def slew_limited(slew_rate_v_per_s: float, tau_s: float, step_v: float) -> Response:
    """A slew-limited single pole's step, the share of the step done: dv/dt = min(SR, (step - v) / tau),
    a ramp at SR until the output is x0 = SR tau from its final level, then x0 exp(-(s - t1) / tau)
    from t1 = (step - x0) / SR; a single pole of tau alone where x0 is the step or more."""
    x0 = slew_rate_v_per_s * tau_s
    if x0 >= step_v:
        return exponential(tau_s)
    knee = (step_v - x0) / slew_rate_v_per_s
    return lambda s: np.where(s < knee, slew_rate_v_per_s * s / step_v, 1 - x0 / step_v * np.exp(-(s - knee) / tau_s))


# A slew-limited single pole (dv/dt = min(SR, (V_f - v) / tau), SR = 0.2 V/ns: a ramp, then the
# exponential of linear settling once the output is x0 = SR tau from its final level; [Razavi-Analog]
# Fig. 9.70, p. 391) at 0.3 V and at 0.15 V, on both edges, on Spectre's strobed axis. The full step
# ramps at exactly SR from the input edge's middle until it is x0 from its final level: 0.3 - x0,
# 0.18 V (tau = 600 ps) down to 0.10 V (tau = 1 ns), a third of its height or more. Its ramp (the
# analysis's longest stretch of one slope from the input edge's end) is that ramp, whatever the
# tail after it, and its slope SR (the chord over the stretch's flattest quarter, on the ramp:
# linear between samples, rel 1e-6); it spans more than a twentieth of the step (at 1 ns, 0.10 V less
# the local slope's window, about 0.077 V). The half step slews at SR only while x0 < 0.15 V
# (600 ps); from 800 ps it is a single pole of tau, its steepest slope past the input edge's end
# (5 ps after its middle) 0.15 V / tau exp(-5 ps / tau): 0.94 SR at 800 ps, 0.75 SR at 1 ns, more
# than sqrt(1/2) SR = 0.707 SR: its slope holds, as a slewing edge's does ([Razavi-Analog] Sec. 9.9,
# p. 392). The bench step's slew rate is SR, 2e8 V/s rising and -2e8 V/s falling.
@pytest.mark.parametrize(
    "tau_s",
    [600e-12, 800e-12, 850e-12, 900e-12, 950e-12, 1000e-12],
    ids=["tau_600ps", "tau_800ps", "tau_850ps", "tau_900ps", "tau_950ps", "tau_1000ps"],
)
def test_slew_rate_of_a_slew_limited_pole_whose_half_step_barely_slews(tau_s: float) -> None:
    tb = step_tb()
    slew_rate = 0.2e9
    full, half = slew_limited(slew_rate, tau_s, tb.step_v), slew_limited(slew_rate, tau_s, tb.step_v / 2)
    slew = analyze_slew(step_pair(tb, full, full, half_rise=half, half_fall=half, time_s=strobed_axis(tb)))
    assert slew.slew_rate_rise_v_per_s[0] == pytest.approx(slew_rate, rel=1e-6)
    assert slew.slew_rate_fall_v_per_s[0] == pytest.approx(-slew_rate, rel=1e-6)


# An edge its device drives after an internal node's delay, as a flipped follower's shunt device
# does once its gate has moved: the output moves 35 mV at S0 = 0.2 V/ns whatever the step (the
# internal node), then ramps at k times the step, k = 5 /ns (the drive in proportion to the error:
# 1.5 V/ns at 0.3 V, 0.75 V/ns at 0.15 V) to its final level. Its ramp, the longest stretch of one
# slope from the input edge's end with nothing steeper after it, is the fast one (35 mV to the 90 %
# level, 0.78 of the full step: the slow start is followed by it, as no current-limited ramp is),
# and its slope halves with the step: 0.75 V/ns at half of 1.5 V/ns, not more than
# sqrt(1/2) of it ([Razavi-Analog] Eq. (9.58), p. 390: a linear edge's slope scales with the
# step), so the edge has no slew rate (NaN) in either row.
def test_an_edge_its_device_drives_after_a_delay_has_no_slew_rate() -> None:
    tb = step_tb()
    slow, delay_v, k = 0.2e9, 0.035, 5e9

    def delayed(size: float) -> Response:
        knee = delay_v / slow
        return lambda s: np.minimum(np.where(s < knee, slow * s, delay_v + k * size * (s - knee)) / size, 1.0)

    slew = analyze_slew(
        step_pair(
            tb,
            delayed(tb.step_v),
            delayed(tb.step_v),
            half_rise=delayed(tb.step_v / 2),
            half_fall=delayed(tb.step_v / 2),
            time_s=strobed_axis(tb),
        )
    )
    assert np.isnan(slew.slew_rate_rise_v_per_s).all() and np.isnan(slew.slew_rate_fall_v_per_s).all()
    # its 10-90 % time: 5 mV at S0, then 235 mV at 1.5 V/ns
    assert slew.rise_time_s[0] == pytest.approx(0.005 / slow + 0.235 / (k * tb.step_v), rel=1e-4)


# A slewing edge after a fast start, as a PMOS flipped follower's fall: its device first moves the
# output linearly, a single pole of tau = 30 ps toward 0.84 of the step (its slope in proportion
# to the step), until that slope has fallen to S = 0.2 V/ns, at 0.84 step - S tau (0.82 of the full
# 0.3 V step, 0.80 of the half); from there the bias currents ramp it at S to its final level,
# whatever the step ([Razavi-Analog] Sec. 9.9, p. 391: slewing, a ramp of constant slope). From
# the input edge's end to the 90 % level each step's longest stretch of one slope with nothing
# steeper after it is the ramp, 0.82 (0.80) to 0.9 of its step (more than a twentieth of it, less
# its local slope's window), of the same slope S at both sizes, more than sqrt(1/2) of the full
# step's: the edge slews, its slew rate S (the ramp's chord: linear between samples, rel 1e-6),
# though the ramp spans under a tenth of the bench step's height.
def test_slew_rate_of_a_short_ramp_after_a_fast_start() -> None:
    tb = step_tb()
    slope, tau = 0.2e9, 30e-12

    def started(size: float) -> Response:
        knee = tau * math.log(0.84 * size / (tau * slope))
        start = 0.84 * size - slope * tau
        return lambda s: np.minimum(
            np.where(s < knee, 0.84 * size * (1 - np.exp(-s / tau)), start + slope * (s - knee)) / size, 1.0
        )

    full, half = started(tb.step_v), started(tb.step_v / 2)
    slew = analyze_slew(step_pair(tb, full, full, half_rise=half, half_fall=half, time_s=strobed_axis(tb)))
    assert slew.slew_rate_rise_v_per_s == pytest.approx([slope, slope], rel=1e-6)
    assert slew.slew_rate_fall_v_per_s == pytest.approx([-slope, -slope], rel=1e-6)


# --- metrics ----------------------------------------------------------------------------------


def input_runs(tb: TbParams, gains: list[float]) -> list[Meas]:
    """The thirteen input-level runs of ``tb``'s supply, each different: at level k (k twelfths
    of the supply) the output 0.3 + 0.01 k below the input, the gain ``gains[k]`` falling at a
    pole of (k + 1) 100 MHz, the supply passing 0.01 (k + 1), (20 + k) uA, the follower's output
    resistive, 1000 + 100 k ohm, the load across it at the output node."""
    made = []
    for k, fraction in enumerate(VIN_SWEEP):
        level = replace(tb, vin_v=round(fraction * tb.vdd, 4))
        made.append(
            ac_run(
                level,
                lambda f, a=gains[k], p=(k + 1) * 100e6: a / (1 + 1j * f / p),
                lambda f, s=0.01 * (k + 1): np.full(len(f), s),
                vout_v=level.vin_v - 0.3 - 0.01 * k,
                idd_a=(20 + k) * 1e-6,
                zout=lambda f, r=1000.0 + 100 * k: r / (1 + 2j * np.pi * f * r * tb.cload_f),
            )
        )
    return made


def nominal_at(vin_v: float, tb: TbParams = TB) -> AnalysisCharacteristic:
    """The characteristic of a follower whose input range's middle is ``vin_v``: softplus_band
    from ``vin_v`` - 0.3 V to ``vin_v`` + 0.3 V (its gain symmetric about ``vin_v``, largest there;
    its range about 0.19 V either side), so that its nominal input is ``vin_v`` where that is a
    level the nominal input may take (2/12 to 10/12 of the 1.2 V supply)."""
    return analyze_characteristic(dc_run(replace(tb, vin_v=0.6), softplus_band(vin_v - 0.3, vin_v + 0.3, 0.05)))


# The metrics read each input-level result at the follower's nominal input, the level of 2/12 to
# 10/12 of the supply nearest the middle of its input range: here a characteristic symmetric
# about 0.1 k V (softplus_band, its gain largest there and its 0.9 crossings either side of it at
# the same distance), so the nominal input is k/12 of the 1.2 V supply, with every level's runs
# made to differ (input_runs), so the chosen k shows in each value:
# - vin_v = 0.1 k; vout_v = vin - 0.3 - 0.01 k, level_shift_v = 0.3 + 0.01 k, idd_a = (20 + k) uA;
# - gain_dc = gains[k] (at 1 kHz: the pole's droop there is below 1e-10);
# - bandwidth_hz = fp sqrt(10^0.3 - 1), fp = (k + 1) 100 MHz (one pole, as in the transfer test:
#   rel 1e-3);
# - psrr_dc_db = 20 log10(gains[k] / (0.01 (k + 1)));
# - rout_ohm = 1000 + 100 k;
# - the step's metrics from the bench's step about 0.1 k V (0.3 V for a source follower, 0.15 V
#   for a flipped one), the larger of its two runs: a single pole of tau = 100 ps rising (no slew
#   rate: NaN; 10-90 % in tau ln 9, 1 % settling in tau ln 100) and a ramp at the bias current
#   falling, -0.2 V/ns at either step (its fall time 0.8 step / 0.2 V/ns, settling
#   0.99 step / 0.2 V/ns: the ramp test's closed forms);
# - bandwidth_min_supply_hz: the smallest of the supply runs' one-pole bandwidths (poles at 0.81,
#   1.0 and 1.21 GHz: the supply factor squared), 0.81 GHz sqrt(10^0.3 - 1).
# input_range_v is checked apart (test_input_range_of_the_dc_sweep).
@pytest.mark.parametrize(
    ("params", "nominal", "gains"),
    [
        (runs.source(), 9, [0.02, 0.1, 0.3, 0.8, 0.82, 0.83, 0.84, 0.85, 0.86, 0.85, 0.8, 0.3, 0.1]),
        (runs.source_pmos(), 3, [0.1, 0.78, 0.8, 0.82, 0.83, 0.79, 0.4, 0.2, 0.1, 0.05, 0.02, 0.02, 0.02]),
        (runs.flipped(), 6, [0.02, 0.1, 0.3, 0.6, 0.8, 0.84, 0.88, 0.84, 0.8, 0.5, 0.2, 0.1, 0.05]),
        (runs.flipped_pmos(), 4, [0.3, 0.7, 0.8, 0.87, 0.81, 0.6, 0.3, 0.1, 0.05, 0.02, 0.02, 0.02, 0.02]),
    ],
    ids=["nmos_source", "pmos_source", "nmos_flipped", "pmos_flipped"],
)
def test_the_metrics_take_the_nominal_input(params: Params, nominal: int, gains: list[float]) -> None:
    tb = replace(TB, params=params)
    vin = round(nominal / 12 * tb.vdd, 4)
    step = round(VIN_STEP[params.topology] * tb.vdd, 4)
    supply = analyze_transfer(
        [
            ac_run(
                replace(tb, vdd=round(factor * tb.vdd, 4), vin_v=vin),
                lambda f, p=factor**2 * 1e9: 0.85 / (1 + 1j * f / p),
                lambda f: np.full(len(f), 0.01),
                vout_v=0.5,
                idd_a=20e-6,
            )
            for factor in SUPPLY_SWEEP
        ]
    )
    stepped = replace(tb, stimulus=Stimulus.STEP, vin_v=vin, step_v=step)
    values = metrics(
        transfer=analyze_transfer(input_runs(tb, gains)),
        impedance=analyze_impedance(input_runs(tb, gains)),
        characteristic=nominal_at(vin, tb),
        slew=analyze_slew(
            # the half step first: the metrics take the bench's, the larger
            step_pair(stepped, exponential(100e-12), ramp(0.2e9, step), half_fall=ramp(0.2e9, step / 2))[::-1]
        ),
        supply=supply,
    )
    assert isinstance(values, Metrics)
    assert values.vin_v == vin
    assert values.vout_v == pytest.approx(vin - 0.3 - 0.01 * nominal, abs=1e-12)
    assert values.level_shift_v == pytest.approx(0.3 + 0.01 * nominal, abs=1e-12)
    assert values.idd_a == pytest.approx((20 + nominal) * 1e-6)
    assert values.gain_dc == pytest.approx(gains[nominal], rel=1e-9)
    assert values.bandwidth_hz == pytest.approx((nominal + 1) * 100e6 * math.sqrt(10**0.3 - 1), rel=1e-3)
    assert values.psrr_dc_db == pytest.approx(20 * math.log10(gains[nominal] / (0.01 * (nominal + 1))), abs=1e-6)
    assert values.rout_ohm == pytest.approx(1000.0 + 100 * nominal, rel=1e-9)
    assert values.step_margin_v > 0
    assert math.isnan(values.slew_rate_rise_v_per_s)
    assert values.slew_rate_fall_v_per_s == pytest.approx(-0.2e9, rel=1e-6)
    assert values.rise_time_s == pytest.approx(100e-12 * math.log(9), rel=1e-4)
    assert values.fall_time_s == pytest.approx(0.8 * step / 0.2e9, rel=1e-6)
    assert values.settling_rise_s == pytest.approx(100e-12 * math.log(100), rel=1e-4)
    assert values.settling_fall_s == pytest.approx(0.99 * step / 0.2e9, rel=1e-6)
    assert values.overshoot_rise == 0.0 and values.overshoot_fall == 0.0
    assert values.bandwidth_min_supply_hz == pytest.approx(0.81e9 * math.sqrt(10**0.3 - 1), rel=1e-3)


# not in the reference texts: the input range is the span of input level over which the gain
# dVout/dVin of the input's DC sweep stays within 10 % of its largest (types.Metrics), the
# devices saturated ([Razavi-Analog] Example 3.12, p. 70). The characteristic softplus_band(a, b, w),
# a = 0.4 V, b = 1.0 V, w = 50 mV, has the gain g(v) = 0.85 (sigma((v - a) / w) - sigma((v - b) / w))
# in closed form ([Razavi-Analog] Eq. (3.8), p. 48: the slope of the characteristic), symmetric
# about 0.7 V and largest there, g0 = g(0.7 V). The range's ends are where g crosses 0.9 g0 on
# either side, found here by bisection on g itself (about 0.51 V and 0.89 V), its middle 0.7 V, a
# level the nominal input may take (7/12 of 1.2 V): the nominal input. The analysis reads g as
# the output's chord over each 2.5 mV step, at the step's middle (within h^2 / 24 times g's second
# derivative there: under 1e-5 of the gain), linear between the middles (within h^2 / 8 of it:
# under 3e-5), each a crossing error of under 1e-5 V at g's slope there (over 3 /V): abs 2e-5 V on
# each end. The step 0.55 V to 0.85 V lies inside both ends, by the smaller distance, the step
# margin.
def test_input_range_of_the_dc_sweep() -> None:
    a_v, b_v, width_v, at = 0.4, 1.0, 0.05, 0.7

    def gain(v: float) -> float:
        return 0.85 * (1 / (1 + math.exp(-(v - a_v) / width_v)) - 1 / (1 + math.exp(-(v - b_v) / width_v)))

    def crossing(low: float, high: float, level: float) -> float:
        rising = gain(high) > gain(low)
        for _ in range(80):
            middle = (low + high) / 2
            low, high = (middle, high) if (gain(middle) < level) == rising else (low, middle)
        return (low + high) / 2

    g0 = gain(at)
    low, high = crossing(a_v, at, 0.9 * g0), crossing(at, b_v, 0.9 * g0)
    characteristic = analyze_characteristic(dc_run(replace(TB, vin_v=0.6), softplus_band(a_v, b_v, width_v)))
    assert characteristic.vin_nominal_v == at
    assert characteristic.vin_min_v == pytest.approx(low, abs=2e-5)
    assert characteristic.vin_max_v == pytest.approx(high, abs=2e-5)
    assert characteristic.gain == pytest.approx([gain(v) for v in characteristic.vin_v], abs=2e-5)
    transfer = analyze_transfer(input_runs(TB, [0.85] * 13))
    values = metrics(
        transfer=transfer,
        impedance=analyze_impedance(input_runs(TB, [0.85] * 13)),
        characteristic=characteristic,
        slew=analyze_slew(step_pair(replace(step_tb(), vin_v=at), exponential(100e-12), exponential(400e-12))),
        supply=transfer,
    )
    assert values.input_range_v == pytest.approx(high - low, abs=4e-5)
    assert values.step_margin_v == pytest.approx(min(0.55 - low, high - 0.85), abs=2e-5)


# A follower that does not follow at a level the nominal input might have been fixed at (as a
# share of the supply): a characteristic symmetric about 0.3 V (softplus_band from 0 V to 0.6 V),
# its range about 0.11 V to 0.49 V. At 0.6 V, half the supply, its gain is 0.425, half its largest
# ([Razavi-Analog] Example 3.12, p. 70: the devices leave saturation): the nominal input is taken
# where it follows, 0.3 V (3/12 of 1.2 V), not there. A step of 0.3 V about 0.3 V spans 0.15 V to
# 0.45 V, inside the range: its metrics stand; a step of 0.3 V about 0.3 V into a range 0.15 V
# wide (softplus_band from 0.05 V to 0.55 V with w = 75 mV: its range about 0.21 V to 0.39 V)
# leaves it on both sides: the step margin is negative and every step metric NaN, the
# small-signal ones taken at 0.3 V still.
def test_the_nominal_input_is_where_the_follower_follows() -> None:
    characteristic = nominal_at(0.3)
    assert characteristic.vin_nominal_v == 0.3
    assert characteristic.gain[np.argmin(np.abs(characteristic.vin_v - 0.6))] == pytest.approx(0.425, abs=0.01)
    transfer = analyze_transfer(input_runs(TB, [0.85] * 13))
    impedance = analyze_impedance(input_runs(TB, [0.85] * 13))
    steps = step_pair(replace(step_tb(), vin_v=0.3), exponential(100e-12), exponential(400e-12))
    values = metrics(
        transfer=transfer, impedance=impedance, characteristic=characteristic, slew=analyze_slew(steps), supply=transfer
    )
    assert values.vin_v == 0.3 and values.step_margin_v > 0
    assert values.rise_time_s == pytest.approx(100e-12 * math.log(9), rel=1e-4)
    narrow = analyze_characteristic(dc_run(replace(TB, vin_v=0.6), softplus_band(0.05, 0.55, 0.075)))
    assert narrow.vin_nominal_v == 0.3 and narrow.vin_max_v - narrow.vin_min_v < 0.3
    values = metrics(
        transfer=transfer, impedance=impedance, characteristic=narrow, slew=analyze_slew(steps), supply=transfer
    )
    assert values.step_margin_v < 0 and values.gain_dc == pytest.approx(0.85, rel=1e-6)
    for name in ("rise_time_s", "fall_time_s", "settling_rise_s", "settling_fall_s", "overshoot_rise"):
        assert math.isnan(getattr(values, name)), name


def test_input_range_ends_at_the_rails() -> None:
    top = analyze_characteristic(dc_run(replace(TB, vin_v=0.6), softplus_band(0.4, 2.4, 0.05)))
    assert top.vin_max_v == 1.2
    bottom = analyze_characteristic(dc_run(replace(TB, vin_v=0.6), softplus_band(-2.0, 0.75, 0.05)))
    assert bottom.vin_min_v == 0.0
    assert 0.6 < bottom.vin_max_v < 0.75


def test_characteristic_refuses_a_run_without_its_dc_sweep() -> None:
    with pytest.raises(ValueError, match="DC sweep"):
        analyze_characteristic(single_pole(TB, 0.85, 1e9))


# A characteristic of known slope everywhere: vout = c (vin - v0)^2, c = 0.5 /V, v0 = 0.1 V, swept
# from 0 to 1.2 V in steps of h = 2.5 mV. [Razavi-Analog] Eq. (3.8), p. 48: the gain is its slope,
# 2 c (vin - v0), rising with the input. Over each step the chord of a quadratic is its slope at
# the step's middle m exactly, so gain = 2 c (m - v0), and the output at m (linear between the
# swept points) is the two ends' average, c ((m - v0)^2 + (h / 2)^2). Its largest gain is at the
# last middle, 1.19875 V: g = 1.09875; it falls to 0.9 of that at v0 + 0.9 (1.19875 - v0) =
# 1.088875 V, and the range runs to the sweep's end, 1.2 V: 0.111125 V wide (the gain is linear,
# so linear interpolation between the middles is exact). Its middle, 1.144 V, lies above every
# level the nominal input may take (up to 10/12 of 1.2 V, 1.0 V), none inside the range: no
# nominal input (NaN), and every nominal-point metric NaN, the input range alone reported. All
# exact to rounding: abs 1e-12.
def test_characteristic_of_a_quadratic_output() -> None:
    c, v0, h = 0.5, 0.1, 1.2 / 480
    characteristic = analyze_characteristic(dc_run(replace(TB, vin_v=0.6), lambda v: c * (v - v0) ** 2))
    middles = (np.arange(480) + 0.5) * h
    assert characteristic.vin_v == pytest.approx(middles, abs=1e-12)
    assert characteristic.gain == pytest.approx(2 * c * (middles - v0), abs=1e-12)
    assert characteristic.vout_v == pytest.approx(c * ((middles - v0) ** 2 + (h / 2) ** 2), abs=1e-12)
    assert characteristic.vin_min_v == pytest.approx(v0 + 0.9 * (1.2 - h / 2 - v0), abs=1e-12)
    assert characteristic.vin_max_v == 1.2
    assert math.isnan(characteristic.vin_nominal_v)
    transfer = analyze_transfer(input_runs(TB, [0.85] * 13))
    values = metrics(
        transfer=transfer,
        impedance=analyze_impedance(input_runs(TB, [0.85] * 13)),
        characteristic=characteristic,
        slew=analyze_slew(step_pair(step_tb(), exponential(100e-12), exponential(400e-12))),
        supply=transfer,
    )
    assert values.input_range_v == pytest.approx(0.111125, abs=1e-12)
    assert all(math.isnan(value) for name, value in asdict(values).items() if name != "input_range_v")


# An output that does not follow: a constant 0.3 V (gain 0) or an inverting line,
# vout = 1.2 - 0.8 vin (gain -0.8). The input range is where the gain holds within 10 % of its
# largest, a follower's positive gain; with none there, neither end exists: NaN, and
# the metrics' input range and step margin are NaN. A DC sweep of one point has no step to take a
# slope over: refused (ValueError).
@pytest.mark.parametrize(
    "vout", [lambda v: np.full(len(v), 0.3), lambda v: 1.2 - 0.8 * v], ids=["constant", "inverting"]
)
def test_characteristic_of_an_output_that_does_not_follow(vout: Response) -> None:
    characteristic = analyze_characteristic(dc_run(replace(TB, vin_v=0.9), vout))
    assert math.isnan(characteristic.vin_min_v) and math.isnan(characteristic.vin_max_v)
    transfer = analyze_transfer(input_runs(TB, [0.85] * 13))
    values = metrics(
        transfer=transfer,
        impedance=analyze_impedance(input_runs(TB, [0.85] * 13)),
        characteristic=characteristic,
        slew=analyze_slew(step_pair(step_tb(), exponential(100e-12), exponential(400e-12))),
        supply=transfer,
    )
    assert math.isnan(values.input_range_v) and math.isnan(values.step_margin_v)
    run = dc_run(replace(TB, vin_v=0.6), lambda v: 0.85 * v)
    point = replace(
        run, sweeps={**run.sweeps, "dc": Sweep(kind=SweepKind.DC, x=np.asarray([0.6]), v={"vout": np.asarray([0.51])})}
    )
    with pytest.raises(ValueError):
        analyze_characteristic(point)


# The smallest bandwidth over the supply, where one corner's lies past the sweep: one-pole
# responses at 90, 100 and 110 % of the supply with poles at 1 GHz, 2 GHz and 1 THz. The 1 THz
# corner never falls 3 dB inside the sweep (it falls 0.043 dB by 100 GHz): its bandwidth is NaN,
# that is, above 100 GHz (types.AnalysisTransfer: NaN beyond the sweep), where it follows: its gain
# within 10 % of the nominal corner's, its response at 100 GHz within 3 dB of 1 kHz's. The smallest of the
# three is then the 1 GHz corner's, 1 GHz sqrt(10^0.3 (1 + (1 kHz / 1 GHz)^2) - 1) = 0.9976 GHz
# ([Razavi-Analog] Eq. (6.101), p. 204, the one-pole magnitude, 3.0 dB below its 1 kHz value;
# rel 1e-3 as in the transfer test), not NaN: a corner above the sweep cannot be the smallest.
def test_bandwidth_min_supply_with_a_corner_beyond_the_sweep() -> None:
    supply = analyze_transfer(
        [
            single_pole(replace(TB, vdd=round(factor * 1.2, 4), vin_v=0.9), 0.85, pole_hz)
            for factor, pole_hz in zip(SUPPLY_SWEEP, (1e9, 2e9, 1e12), strict=True)
        ]
    )
    assert math.isnan(supply.bandwidth_hz[2])
    transfer = analyze_transfer(input_runs(TB, [0.85] * 13))
    values = metrics(
        transfer=transfer,
        impedance=analyze_impedance(input_runs(TB, [0.85] * 13)),
        characteristic=nominal_at(0.9),
        slew=analyze_slew(step_pair(step_tb(), exponential(100e-12), exponential(400e-12))),
        supply=supply,
    )
    expected = 1e9 * math.sqrt(10**0.3 * (1 + (1e3 / 1e9) ** 2) - 1)
    assert values.bandwidth_min_supply_hz == pytest.approx(expected, rel=1e-3)


# Every supply corner's bandwidth beyond the sweep: one-pole responses at 1 THz at 90, 100 and 110 %
# of the supply each fall 0.043 dB by 100 GHz, never 3 dB inside the sweep (NaN: above 100 GHz).
# Their smallest is then above 100 GHz too, a value the sweep does not give: NaN.
def test_bandwidth_min_supply_with_every_corner_beyond_the_sweep() -> None:
    supply = analyze_transfer(
        [single_pole(replace(TB, vdd=round(factor * 1.2, 4), vin_v=0.9), 0.85, 1e12) for factor in SUPPLY_SWEEP]
    )
    assert np.isnan(supply.bandwidth_hz).all()
    values = metrics(
        transfer=analyze_transfer(input_runs(TB, [0.85] * 13)),
        impedance=analyze_impedance(input_runs(TB, [0.85] * 13)),
        characteristic=nominal_at(0.9),
        slew=analyze_slew(step_pair(step_tb(), exponential(100e-12), exponential(400e-12))),
        supply=supply,
    )
    assert math.isnan(values.bandwidth_min_supply_hz)


# A supply corner where the follower does not follow: its gain 3e-5 at 1 kHz, the input device's
# gate-source capacitance feeding the input through, H(f) = 3e-5 + 0.02 j f / (1 GHz + j f), rising
# to 0.02 by 100 GHz: it never falls 3 dB, so its bandwidth is NaN, but not because it lies beyond
# the sweep (its gain is not within 10 % of the nominal corner's 0.85). The smallest bandwidth over
# the supply is then not known: NaN ([Razavi-Analog] Fig. 6.43, p. 204: the -3-dB bandwidth of a
# working amplifier), not the other corners' smallest (np.fmin would give the 1 GHz corner's
# 0.9976 GHz).
def test_bandwidth_min_supply_with_a_corner_that_does_not_follow() -> None:
    corners = [replace(TB, vdd=round(factor * 1.2, 4), vin_v=0.9) for factor in SUPPLY_SWEEP]
    supply = analyze_transfer(
        [
            ac_run(
                corners[0],
                lambda f: 3e-5 + 0.02j * f / (1e9 + 1j * f),
                lambda f: np.full(len(f), 1e-3),
                vout_v=0.0,
                idd_a=0.0,
            ),
            single_pole(corners[1], 0.85, 1e9),
            single_pole(corners[2], 0.85, 2e9),
        ]
    )
    assert math.isnan(supply.bandwidth_hz[0])
    values = metrics(
        transfer=analyze_transfer(input_runs(TB, [0.85] * 13)),
        impedance=analyze_impedance(input_runs(TB, [0.85] * 13)),
        characteristic=nominal_at(0.9),
        slew=analyze_slew(step_pair(step_tb(), exponential(100e-12), exponential(400e-12))),
        supply=supply,
    )
    assert math.isnan(values.bandwidth_min_supply_hz)


# --- the record -------------------------------------------------------------------------------


def instance_runs(tb: TbParams) -> dict[str, Meas]:
    """Every run of one instance (``runs.testbenches``'s names) about ``tb``'s supply: a gain of
    0.85 at each input level from 2/12 to 10/12 of the supply and 0.1 outside, a 1 GHz pole, a
    1.5 kohm output impedance, a characteristic symmetric about 0.9 V (the nominal input 9/12 of
    1.2 V) in the middle level's run; at each level the nominal input may take, the bandwidth in
    proportion to the supply, a single-pole step and its half."""
    dut, supply = tb.params, tb.vdd
    made = {}
    for k, fraction in enumerate(VIN_SWEEP):
        level = replace(tb, vin_v=round(fraction * supply, 4))
        made[f"input_vin_{k}"] = single_pole(level, 0.85 if 2 <= k <= 10 else 0.1, 1e9)
    made["input_vin_6"] = dc_run(made["input_vin_6"].tb, softplus_band(0.6, 1.2, 0.05))
    step_v = round(VIN_STEP[dut.topology] * supply, 4)
    for fraction in NOMINAL_VIN:
        k, vin_v = round(fraction * 12), round(fraction * supply, 4)
        for factor in SUPPLY_SWEEP:
            if factor != 1.0:
                corner = replace(tb, vdd=round(factor * supply, 4), vin_v=vin_v)
                made[f"supply_{round(factor * 100)}_vin_{k}"] = single_pole(corner, 0.85, factor * 1e9)
        step = replace(tb, stimulus=Stimulus.STEP, vin_v=vin_v, step_v=step_v)
        made[f"step_vin_{k}"], made[f"step_half_vin_{k}"] = step_pair(step, exponential(100e-12), exponential(400e-12))
    return made


def test_the_record_reads_every_run_and_names_its_wave() -> None:
    """``results`` from every run ``testbenches`` names: the metrics at the nominal input, the
    plots, the model's curve among them (``vout_vin``), the step the viewer shows."""
    result = runs.results(instance_runs(TB))
    assert list(result.metrics) == [
        "vin_v",
        "vout_v",
        "level_shift_v",
        "gain_dc",
        "bandwidth_hz",
        "psrr_dc_db",
        "idd_a",
        "rout_ohm",
        "input_range_v",
        "step_margin_v",
        "slew_rate_rise_v_per_s",
        "slew_rate_fall_v_per_s",
        "rise_time_s",
        "fall_time_s",
        "settling_rise_s",
        "settling_fall_s",
        "overshoot_rise",
        "overshoot_fall",
        "bandwidth_min_supply_hz",
    ]
    assert result.metrics["gain_dc"] == pytest.approx(0.85) and result.metrics["vin_v"] == 0.9
    assert [plot.name for plot in result.details] == [
        "vout_vin",
        "gain_vin",
        "bandwidth_vin",
        "rout_vin",
        "psrr_vin",
        "gain_frequency",
        "zout_frequency",
        "gain_supply",
        "bandwidth_supply",
        "psrr_supply",
    ]
    assert all(isinstance(plot, Plot) for plot in result.details)
    vout = result.details[0]
    # the characteristic over the DC sweep's steps' middles, 2.5 mV apart from ground to the supply
    assert vout.x == pytest.approx((np.arange(480) + 0.5) * 1.2 / 480, abs=1e-12) and list(vout.series) == ["output"]
    # the response over frequency is the nominal input's: 20 log10 0.85 = -1.41 dB at 1 kHz
    response = result.details[5]
    assert len(response.x) == 161 and response.x_log and response.series["gain"][0] == pytest.approx(-1.41, abs=0.01)
    # the supply plots' x: each supply run's own supply
    assert result.details[7].x == pytest.approx([factor * 1.2 for factor in SUPPLY_SWEEP], abs=1e-4)
    assert result.waves == {"step at the nominal input": "step_vin_9"}


def test_the_record_takes_the_runs_the_testbenches_name() -> None:
    pytest.importorskip("pdk.tsmc65.hdl21")  # the supply is the kit's
    assert set(instance_runs(TB)) == set(runs.testbenches("tsmc65", TB.params))
