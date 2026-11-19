"""The fixed comparator characterization's own known answers: its testbenches (each bench's input,
corner, clocks and the accuracy it runs at), the delays to the held outputs and against the input's
sign, the toggling and per-input energy, the kickback left for the next decision, the stress check,
and the behavioral model's delay table by the effective input; each answer from how the synthetic
run was made (``test_known_answers``' latch), not from the code under test."""

from __future__ import annotations

import math
from dataclasses import replace
from types import SimpleNamespace

import hdl21 as h
import numpy as np
import pytest
from hdl21.primitives import MosType
from scipy import constants

from flow.analysis import calc
from flow.circuit import oppoint, spectre
from flow.pipeline import Level, Meas, Sweep, SweepKind

from . import model, plots, runs
from .analysis import analyze_kickback, analyze_metastability, analyze_power, analyze_stress, metrics
from .model import Model
from .params import (
    ADC_FULL_SCALE,
    CM_SWEEP,
    LARGE_V,
    METASTABILITY_RUN_V,
    METASTABILITY_V,
    NOISE_STROBE_S,
    NOMINAL_CM,
    SMALL_V,
    SUPPLY_SWEEP,
    ClockDrive,
    InputOrder,
    Params,
    TbParams,
    Validity,
)
from .subckt import netlist
from .test_known_answers import INFO, chain, kick, latch_run, metric_inputs

# ---------------------------------------------------------------- the testbenches


@pytest.fixture
def benches(monkeypatch) -> dict[str, TbParams]:
    """The full characterization's runs of the default design in a kit of a 1.2 V supply."""
    install = SimpleNamespace(supply_voltage=lambda corner: 1.2)
    monkeypatch.setattr(runs.importlib, "import_module", lambda name: SimpleNamespace(install=install))
    return runs.testbenches("tsmc65", Params(), Level.FULL)


def test_the_runs_that_need_accuracy_are_marked_and_the_s_curves_take_noise_to_100_ghz(benches) -> None:
    """The delays near metastability are timing runs, the kickback a small difference, every
    S-curve an S-curve: classic Spectre (sim.simulate), its noise to 100 GHz on a 5 ps strobe; the
    rest Spectre X."""
    marked = {name: tb.accuracy for name, tb in benches.items() if tb.accuracy is not None}
    scurves = {name for name in benches if name.startswith("scurve_cm")}
    assert marked == {
        "metastability": spectre.Accuracy.TIMING,
        "metastability_check": spectre.Accuracy.TIMING,
        "outputs": spectre.Accuracy.TIMING,
        "kickback": spectre.Accuracy.SMALL_DIFFERENCE,
        **dict.fromkeys(scurves, spectre.Accuracy.S_CURVE),
    }
    assert len(scurves) == len(CM_SWEEP)
    assert all(benches[name].noise and benches[name].waveform_sample_interval_s == NOISE_STROBE_S for name in scurves)
    fmax_hz = {benches[name].noise_fmax_hz for name in scurves}
    assert len(fmax_hz) == 1 and NOISE_STROBE_S == pytest.approx(0.5 / fmax_hz.pop()) and NOISE_STROBE_S <= 5e-12


def test_the_new_benches_are_the_inputs_corners_and_clocks_they_measure(benches) -> None:
    """The held outputs toggle (each of the delay curve's inputs and 0.5 mV, of either sign, after
    +100 mV and again after -100 mV); the kickback runs three decisions; the recovery bench puts
    -0.96 V (the converter's full scale) before each +0.5 mV; the slow corner is slow, 75 C, 90 % of
    the supply at its common mode; the converter's clocks; 0.5 mV at every other common mode; a
    stress run of two decisions at each supply saving the devices' values on Spectre's own steps."""
    outputs = benches["outputs"]
    assert outputs.input_order is InputOrder.AFTER_BOTH and outputs.vin_diff_values_v[:2] == (LARGE_V, -LARGE_V)
    toggled = outputs.vin_diff_values_v[2:]
    assert sorted({abs(v) for v in toggled}) == sorted({*METASTABILITY_V, SMALL_V} - {LARGE_V})
    assert sorted(toggled) == sorted(-v for v in toggled)
    schedule = [outputs.vin_diff_values_v[point] for point in outputs.trial_point]
    assert schedule[:8] == [LARGE_V, toggled[0], -LARGE_V, toggled[0], LARGE_V, toggled[1], -LARGE_V, toggled[1]]
    assert benches["kickback"].conversions == 3
    recovery = benches["recovery"]
    assert recovery.vin_diff_values_v == (-round(ADC_FULL_SCALE * 1.2, 4), SMALL_V)
    assert recovery.input_order is InputOrder.CYCLED and recovery.trial_point.tolist() == [0, 1, 0, 1, 0, 1]
    slow = benches["slow"]
    assert (slow.corner, slow.temperature_c) == (h.pdk.Corner.SLOW, 75.0)
    assert slow.vdd == pytest.approx(0.9 * 1.2) and slow.vin_cm_values_v[0] == pytest.approx(
        NOMINAL_CM * 0.9 * 1.2, abs=1e-4
    )
    assert benches["converter_clock"].clock_drive is ClockDrive.CONVERTER
    common = sorted(tb.vin_cm_values_v[0] for name, tb in benches.items() if name.startswith("small_cm"))
    assert common == pytest.approx([round(f * 1.2, 4) for f in CM_SWEEP if f != NOMINAL_CM])
    for factor in SUPPLY_SWEEP:
        stress = benches[f"stress_{round(factor * 100)}"]
        assert stress.device_values and stress.waveform_sample_interval_s is None
        assert stress.vdd == pytest.approx(factor * 1.2) and stress.vin_diff_values_v == (-SMALL_V, SMALL_V)


# ---------------------------------------------------------------- delays


def toggling_run(tb: TbParams, delays_s, output_s, *, decision=None) -> Meas:
    """``latch_run``'s, its outputs held until ``output_s`` after each clock's midpoint and then
    taking the trial's decision (the SR latch and buffers after the latch)."""
    meas = latch_run(tb, delays_s, decision=decision)
    trials = len(tb.trial_point)
    mids = tb.trial_start_s + tb.reset_time_s + tb.transition_time_s / 2
    trial = np.clip(np.searchsorted(tb.trial_start_s, meas.time_s, side="right") - 1, 0, trials - 1)
    points = np.asarray(tb.points)
    high = (
        np.asarray([points[point, 1] >= 0 for point in tb.trial_point])
        if decision is None
        else np.asarray(decision, dtype=bool)
    )
    previous = np.r_[False, high[:-1]]
    after = meas.time_s >= mids[trial] + np.asarray(output_s)[trial]
    state = np.where(after, high[trial], previous[trial])
    vdd = float(tb.vdd)
    v = {**meas.v, "outp": np.where(state, vdd, 0.0), "outn": np.where(state, 0.0, vdd)}
    return replace(meas, v=v)


def test_the_delay_to_the_held_outputs_is_their_crossing_after_the_clock_and_none_where_they_hold() -> None:
    """Inputs -1, +1, +2 mV: the outputs toggle 300 ps after the clock's midpoint in the second
    decision (low to high), not in the third (high again: held, NaN); the latch's own delays
    beside them."""
    tb = TbParams(vin_diff_values_v=(-1e-3, 1e-3, 2e-3), conversions=1)
    meas = toggling_run(tb, [100e-12, 120e-12, 90e-12], [250e-12, 300e-12, 200e-12])
    _, timing, delay = chain(meas)
    np.testing.assert_allclose(timing.clock_to_decision_s, [100e-12, 120e-12, 90e-12], atol=0.05e-12)
    assert timing.clock_to_output_s[1] == pytest.approx(300e-12, abs=1.5e-12)
    assert math.isnan(timing.clock_to_output_s[2])
    assert delay.output_delay_s is not None and delay.output_delay_s[0, 1] == pytest.approx(300e-12, abs=1.5e-12)


def test_a_decision_against_its_inputs_sign_is_counted_and_timed_nowhere() -> None:
    """Three decisions at +0.5 mV, the first low (against its sign) and slowest: the delay the
    slowest of the other two, one decision against the sign; all three against it, NaN."""
    tb = TbParams(vin_diff_values_v=(SMALL_V,), conversions=3)
    _, _, delay = chain(latch_run(tb, [400e-12, 200e-12, 250e-12], decision=[0, 1, 1]))
    assert delay.slowest_s is not None and delay.against_sign is not None
    assert delay.slowest_s[0, 0] == pytest.approx(250e-12, abs=0.1e-12)
    assert delay.delay_s[0, 0] == pytest.approx(225e-12, abs=0.1e-12)
    assert delay.against_sign.tolist() == [[1]]
    _, _, wrong = chain(latch_run(tb, [400e-12, 200e-12, 250e-12], decision=[0, 0, 0]))
    assert math.isnan(wrong.delay_s[0, 0]) and wrong.against_sign is not None and wrong.against_sign.tolist() == [[3]]
    values = metrics(**metric_inputs(small=delay, large=delay, supply=[delay] * 3))
    assert values.delay_0p5mv_s == pytest.approx(250e-12, abs=0.1e-12) and values.decisions_against_sign == 5


def test_the_output_delays_metrics_are_from_the_offset_whatever_it_is(benches) -> None:
    """The outputs run of a comparator of offset -5 mV whose latch splits 60 ps before its outputs
    toggle, both as t_0 + 30 ps ln(0.1 V / |V - V_OS|): every input's toggling decision timed (one of
    its two), the delays to the held outputs at 0.5 mV and 100 mV from the offset their law's (the
    nearest input 1 mV from it: extrapolated by the fitted 30 ps), the figure over |V - V_OS|."""
    offset_v = -5e-3
    tb = replace(benches["outputs"], params=Params())
    inputs = [tb.points[point][1] for point in tb.trial_point]
    output = lambda v: 200e-12 + 30e-12 * math.log(0.1 / abs(v - offset_v))
    decision = [v > offset_v for v in inputs]
    meas = toggling_run(tb, [output(v) - 60e-12 for v in inputs], [output(v) for v in inputs], decision=decision)
    decisions, timing, delay = chain(meas)
    outputs = analyze_metastability(meas, delay=delay, decisions=decisions, timing=timing)
    assert outputs.offset_v == pytest.approx(offset_v, abs=20e-6)
    assert outputs.regeneration_tau_s == pytest.approx(30e-12, rel=0.02)
    assert outputs.effective_output_s is not None and np.all(np.isfinite(outputs.effective_output_s))
    values = metrics(**metric_inputs(), outputs=outputs)
    assert values.delay_out_0p5mv_s == pytest.approx(200e-12 + 30e-12 * math.log(0.1 / SMALL_V), abs=2e-12)
    assert values.delay_out_100mv_s == pytest.approx(200e-12 + 30e-12 * math.log(0.1 / LARGE_V), abs=2e-12)
    figure = plots.plot_output_delay(outputs)
    assert figure.x_label == "Differential input less the offset (V)" and figure.x == sorted(figure.x)
    assert figure.series["delay"][0] == pytest.approx(output(offset_v + figure.x[0]), abs=2e-12)
    against = int(np.count_nonzero([(v > 0) != high for v, high in zip(inputs[1:], decision[1:], strict=True)]))
    assert outputs.against_sign == against


def test_the_regeneration_time_constant_and_the_offset_are_fitted_together_near_the_offset() -> None:
    """A latch of tau_reg 20 ps and offset -9 mV whose delay above 3 mV from the offset falls faster
    than the log law (a large-signal term of 1 ps per mV): the fit over the decisions within 3 mV of
    the offset reads 20 ps within 5 % and the offset within 0.1 mV; the clock check's 10 uV is the
    law's from the decision nearest the offset."""
    offset_v = -9e-3
    law = lambda v: 300e-12 + 20e-12 * math.log(0.1 / abs(v - offset_v)) - 1e-9 * max(0.0, abs(v - offset_v) - 3e-3)
    runs_ = []
    for check in (False, True):
        tb = TbParams(vin_diff_values_v=METASTABILITY_RUN_V)
        if check:
            tb = replace(tb, reset_time_s=2e-9, evaluation_time_s=8e-9)
        inputs = [tb.points[point][1] for point in tb.trial_point]
        meas = latch_run(tb, [law(v) for v in inputs], decision=[v > offset_v for v in inputs], tau_s=10e-12)
        decisions, timing, delay = chain(meas)
        runs_.append((meas, decisions, analyze_metastability(meas, delay=delay, decisions=decisions, timing=timing)))
    found = runs_[0][2]
    assert found.regeneration_tau_s == pytest.approx(20e-12, rel=0.05)
    assert found.offset_v == pytest.approx(offset_v, abs=0.1e-3)
    assert found.effective_v is not None and found.effective_v[0] == pytest.approx(1e-3, abs=0.1e-3)
    meas, decisions, metastability = zip(*runs_, strict=True)
    check = runs.analyze_clock_check(list(meas), decisions=list(decisions), metastability=list(metastability))
    assert check.resolved_10uv_s == pytest.approx(300e-12 + 20e-12 * math.log(0.1 / 10e-6), rel=0.01)


# ---------------------------------------------------------------- energy, kickback


def test_a_toggling_decision_after_its_negative_is_settled_and_each_inputs_energy_its_own() -> None:
    """-0.5, +0.5, -0.5, +0.5 mV drawing 40, 70, 60, 80 fC at 1.2 V: every decision after the first
    follows one of the same magnitude (70, 60, 80 fC: 84 fJ); +0.5 mV's own 1.2 x 75 fC = 90 fJ,
    -0.5 mV's 1.2 x 60 fC = 72 fJ."""
    tb = TbParams(vin_diff_values_v=(-SMALL_V, SMALL_V), conversions=2, input_order=InputOrder.CYCLED, vdd=1.2)
    power = analyze_power([latch_run(tb, [200e-12] * 4, charge_c=[40e-15, 70e-15, 60e-15, 80e-15])])
    assert power.energy_per_decision_j[0] == pytest.approx(1.2 * 70e-15, rel=1e-9)
    assert power.vin_diff_v is not None and power.point_energy_j is not None
    np.testing.assert_allclose(power.vin_diff_v, [-SMALL_V, SMALL_V])
    np.testing.assert_allclose(power.point_energy_j, [[1.2 * 60e-15, 1.2 * 75e-15]], rtol=1e-9)
    assert metrics(**metric_inputs(), toggle=power).energy_toggle_0p5mv_j == pytest.approx(90e-15, rel=1e-9)


def test_with_its_decisions_the_energy_is_of_those_that_changed_the_held_outputs() -> None:
    """+100, +0.5, -100, +0.5 mV (the outputs bench's order) at 1.2 V decided 1, 0, 0, 0 (an offset
    of +1 mV decides +0.5 mV low): the held outputs change at the second decision alone, high to low,
    so its 70 fC alone counts, at +0.5 mV (the inputs ascending: -100, +0.5, +100 mV)."""
    tb = TbParams(vin_diff_values_v=(LARGE_V, -LARGE_V, SMALL_V), input_order=InputOrder.AFTER_BOTH, vdd=1.2)
    meas = latch_run(tb, [200e-12] * 4, charge_c=[40e-15, 70e-15, 60e-15, 80e-15], decision=[1, 0, 0, 0])
    power = analyze_power([meas], decisions=[chain(meas)[0]])
    assert power.energy_per_decision_j[0] == pytest.approx(1.2 * 70e-15, rel=1e-9)
    assert power.point_energy_j is not None and power.vin_diff_v is not None
    np.testing.assert_allclose(power.point_energy_j[0], [math.nan, 1.2 * 70e-15, math.nan], rtol=1e-9)


def test_the_supplys_energy_figure_is_each_corners_half_millivolt_decision() -> None:
    """Supply runs of 0.5, 0.5, 100, 100 mV drawing 50, 40, 90, 60 fC: the figure 0.5 mV's 40 fC at
    each corner's supply, not the mean of both inputs."""
    corners = [TbParams(vdd=round(f * 1.2, 4), vin_diff_values_v=(SMALL_V, 0.1), conversions=2) for f in SUPPLY_SWEEP]
    runs_ = [latch_run(tb, [200e-12] * 4, charge_c=[50e-15, 40e-15, 90e-15, 60e-15]) for tb in corners]
    figure = plots.plot_energy_supply(analyze_power(runs_))
    assert figure.series["energy"] == pytest.approx([round(f * 1.2, 4) * 40e-15 for f in SUPPLY_SWEEP], rel=1e-9)


def test_the_kickback_left_for_the_next_decisions_is_read_at_their_clock_rise() -> None:
    """Three decisions at 0.5 mV, each kicking inp up 2 mV in its evaluation, the second leaving
    0.3 mV on it by the third's clock rise: the residual is 0.3 mV."""
    tb = TbParams(vin_diff_values_v=(SMALL_V,), conversions=3, source_capacitance_f=1e-12)
    third_rise = 2 * tb.cycle_s + tb.reset_time_s

    def kicks(t):
        bumps = sum(kick(k * tb.cycle_s + tb.reset_time_s + 200e-12, 2e-3)(t) for k in range(3))
        return bumps + 0.3e-3 * np.exp(-(((t - third_rise) / 0.5e-9) ** 2))

    found = analyze_kickback(latch_run(tb, [200e-12] * 3, kick_p=kicks))
    assert found.residual_diff_v == pytest.approx(0.3e-3, rel=1e-2)
    alone = analyze_kickback(latch_run(replace(tb, conversions=1), [200e-12]))
    assert math.isnan(alone.residual_diff_v)


# ---------------------------------------------------------------- stress


def stress_run(vdd: float, device: str, gd_v: float) -> Meas:
    """A run of two points at ``vdd`` whose every device of the default comparator sits at
    V_GS = V_DS = 0.5 V, V_BS = 0 (V_TH 0.3 V, V_D,sat 0.1 V; a PMOS's negative), ``device``'s
    V_GS and V_GD at ``gd_v`` (V_DS 0) at the second point; its operating point the first."""
    devices = oppoint.mos_devices(netlist(Params()))
    values = {}
    for name, kind in devices.items():
        sign = 1.0 if kind is MosType.NMOS else -1.0
        vgs, vds = np.full(2, 0.5 * sign), np.full(2, 0.5 * sign)
        if name == device:
            vgs[1], vds[1] = gd_v * sign, 0.0
        values.update(
            {
                f"{name}:vgs": vgs,
                f"{name}:vds": vds,
                f"{name}:vbs": np.zeros(2),
                f"{name}:vth": np.full(2, 0.3 * sign),
                f"{name}:vdsat": np.full(2, 0.1 * sign),
                f"{name}:region": np.full(2, 2.0),
            }
        )
    tb = TbParams(vdd=vdd)
    opdc = Sweep(kind=SweepKind.OP, x=np.zeros(0), v={key: value[:1] for key, value in values.items()}, i={})
    return Meas(
        group=None,
        index=None,
        dut=tb.params,
        info=INFO,
        param=tb,
        time_s=np.asarray([0.0, 1e-9]),
        v=values,
        sweeps={"opdc": opdc},
    )


def test_the_stress_check_finds_a_device_past_the_nominal_supply_times_1_1() -> None:
    """Three corners of 1.08, 1.2 and 1.32 V, Mcross_on_p's V_GD 1.4 V at the 110 % one: the largest
    terminal pair is one of its at 1.4 V, past 1.32 V; no junction forward-biased."""
    found = analyze_stress(
        [stress_run(1.08, "Mtail", 0.6), stress_run(1.2, "Mtail", 0.6), stress_run(1.32, "Mcross_on_p", 1.4)]
    )
    assert found.limit_v == pytest.approx(1.32)
    assert (found.terminal_v, found.terminal_device) == (pytest.approx(1.4), "Mcross_on_p")
    assert found.terminal_pair in ("gs", "gd")
    assert found.overstressed == ("Mcross_on_p",) and found.forward == ()
    assert found.forward_v <= oppoint.FORWARD_BIAS_V
    values = metrics(**metric_inputs(), stress=found)
    assert values.terminal_max_v == pytest.approx(1.4) and values.forward_bias_max_v == found.forward_v


# ---------------------------------------------------------------- the S-curve, the model, the rules


def test_a_curve_with_one_point_inside_its_transition_is_undersampled_its_offset_kept() -> None:
    """0, 1/2 and 1 at -1, 0 and +1 mV: the transition's width unknown (noise NaN), its offset 0."""
    from .analysis import analyze_offset_noise
    from .test_known_answers import decisions_of

    fit = analyze_offset_noise([decisions_of(np.repeat([-1e-3, 0.0, 1e-3], 10), [0] * 10 + [0, 1] * 5 + [1] * 10)])
    assert fit.validity is Validity.UNDERSAMPLED and math.isnan(fit.noise_sigma_v)
    assert fit.offset_v == pytest.approx(0.0, abs=1e-9)


def test_the_model_reads_its_delay_table_by_the_effective_input(monkeypatch) -> None:
    """A record whose outputs' delays d(x) = 300 ps + 20 ps ln(1 mV / x) are given over the input
    less the offset its run fitted, x (one NaN: no decision there toggled them), and over 3 mV
    falling faster: the model's table is those x, its tau 20 ps from the ones up to 3 mV, and an
    effective 0.5 mV's delay d(0.5 mV)."""
    inputs = [0.1e-3, 0.3e-3, 0.5e-3, 1e-3, 3e-3, 10e-3, 30e-3]
    law = lambda x: 300e-12 + 20e-12 * math.log(1e-3 / x) - (5e-9 * (x - 3e-3) if x > 3e-3 else 0.0)
    record = {
        "metrics": {"noise_v": 0.4e-3, "offset_v": -2e-3, "energy_0p5mv_j": 1e-13},
        "details": [
            {
                "name": "output_delay",
                "x": inputs,
                "series": {"delay": [None if x == 0.3e-3 else law(x) for x in inputs]},
            },
            {"name": "noise_cm", "x": [0.6], "series": {"noise": [0.4e-3]}},
            {"name": "offset_cm", "x": [0.6], "series": {"offset": [-2e-3]}},
        ],
    }
    monkeypatch.setattr(model, "characterized", lambda *args, **kwargs: record)
    found = Model.of("tsmc65", Params(), simulate=False)
    np.testing.assert_allclose(found.delay_table_v, [x for x in inputs if x != 0.3e-3], rtol=1e-12)
    assert found.regeneration_tau_s == pytest.approx(20e-12, rel=1e-9)
    assert found.delay_s == pytest.approx(law(SMALL_V), rel=1e-9)


def test_the_strongarms_noise_estimate_is_razavis_input_pair_and_precharge_terms() -> None:
    """[Razavi-ADC] Eq. (6.59), p. 116: sigma^2 = r (2 kT gamma / C + r kT / (2 C)), r = V_ov / V_TH:
    halving the input pair's term from 4 kT gamma leaves the precharge's."""
    params = Params()
    c_pq = calc.ymax(
        np.asarray(
            [
                0.8e-15 * (params.diffpair_w + params.latch_on_w + params.rst_w) * 0.12
                + 2 / 3 * params.latch_on_w * 0.12 * params.latch_on_l * 0.06 * 14e-15
            ]
        )
    )
    kt, ratio = constants.k * 300.0, (0.7 - 0.3) / 0.3
    expected = math.sqrt(ratio * (2 * kt / c_pq + ratio * kt / (2 * c_pq)))
    assert Model.strongarm_noise(params, 0.7) == pytest.approx(expected, rel=1e-12)


def test_the_s_curve_fit_lives_with_the_comparator_not_in_the_calculator() -> None:
    assert not hasattr(calc, "probit_fit")
    assert Validity.STUCK_HIGH == "stuck-high" and InputOrder.SHUFFLED == "shuffled"
    with pytest.raises(ValueError, match="input order"):
        TbParams(input_order="sorted")


def test_the_figures_label_their_quantities_in_words_in_si_units() -> None:
    """The offset-noise title in volts, the latch's magnitude in words, the common modes' rows by
    their value under an axis in volts."""
    from .test_known_answers import offset_noise_of

    figure = plots.plot_offset_noise(offset_noise_of("valid"))
    assert "mV" not in figure.title and "0.0001 V" in figure.title
