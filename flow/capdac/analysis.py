"""The capacitive DAC's analyses: from its testbench's measurement (``flow.pipeline.Meas``: every saved signal
on the simulator's own time axis, the run's ``TbParams``) to each stage's settling
(``analyze_settling``) and the numbers its characterization reports (``metrics``).

For each stage and direction ``analyze_settling`` measures, with ``flow.analysis.calc``, on the raw
time points (nothing is resampled):

- the differential top plate's step (``vdac_p`` less ``vdac_n``), from the window's start to its end,
  and the drawn array's gain, the steps against the design's;
- the driver's delay: from the P side's state (``dac_state_p_<stage>``) crossing mid-supply to its
  main bottom plate (``dut_p.main_<stage>``, within its side) crossing it;
- the settling time: from that input edge until the differential top plate stays within half the
  converter's LSB (2 full scale / 2^bits, the full scale the drawn array gives) of its final value.

``analyze_mismatch`` takes a Monte Carlo run's measurement (each saved plate's drawn value, one a
run) to the static linearity each run's drawn plates give (``AnalysisMismatch``), with the CDAC's
static transfer of ``flow.analysis.calc``: the DAC alone over its control words
(``calc_dac_transfer``), the converter's decision paths in the SAR loop from its A state
(``calc_decision_steps``, ``calc_paths``) graded with the design weights (``calc_paths_linearity``)
and for what no calibration recovers (``calc_paths_gap``).

On the bench a stage's switching curves are read through a converter (``AnalysisSwitching``, each
point of a curve as ``adc.analyze_switching`` gives it): its trials as the comparator's decisions
(``analyze_decisions``, which the comparator's S-curve fit takes), each curve's transition from that
fit (``analyze_transition``), and each stage's capacitance from its curves' transitions against the
comparator's own offset (``analyze_cap_mismatch``).
"""

from __future__ import annotations

import math
from collections.abc import Sequence

import numpy as np

from flow import comp
from flow.analysis import calc
from flow.analysis.calc import calc_dac_transfer, calc_decision_steps, calc_paths, calc_paths_gap, calc_paths_linearity
from flow.pipeline import Identity, Meas, analysis, check_identity, measurement_identity

from .types import AnalysisCapMismatch, AnalysisMismatch, AnalysisSettling, AnalysisSwitching, AnalysisTransition


@analysis
def analyze_settling(meas: Meas) -> AnalysisSettling:
    """Every stage's step, driver delay and settling to half an LSB, both directions. The drawn
    array's gain against its design (its top plates' load beyond the design's plates: the units'
    capacitance to their shields) is the measured rising steps fitted to the design's by least
    squares; its full scale and LSB, which the settling is measured to, are the design's at that gain."""

    tb = meas.param
    vdd, window, time_s = float(tb.vdd), float(tb.window_s), meas.time_s
    differential = meas.v["vdac_p"] - meas.v["vdac_n"]
    directions = (("rise", "rising"), ("fall", "falling"))
    # each stage's window, both ways: its step from the window's start to its end
    spans = {
        (stage, direction): (start, min(start + window, float(time_s[-1])))
        for stage in range(tb.stages)
        for direction, _ in directions
        for start in (tb.window_start_s(stage, rising=direction == "rise"),)
    }
    ends = {
        key: (calc.value(differential, time_s, start), calc.value(differential, time_s, stop))
        for key, (start, stop) in spans.items()
    }
    step = {
        direction: np.asarray([ends[stage, direction][1] - ends[stage, direction][0] for stage in range(tb.stages)])
        for direction, _ in directions
    }
    design = tb.ideal_step_v
    gain = float(np.dot(step["rise"], design) / np.dot(design, design))
    lsb = gain * tb.lsb_v
    delays: dict[str, list[float]] = {direction: [] for direction, _ in directions}
    settlings: dict[str, list[float]] = {direction: [] for direction, _ in directions}
    for stage in range(tb.stages):
        state, bottom = meas.v[f"dac_state_p_{stage}"], meas.v[f"dut_p.main_{stage}"]
        for direction, edge in directions:
            # the state's edge in this window: the stimulus switches each state once each way
            edge_s, _, delay = calc.delay(
                state, bottom, time_s, vdd / 2, vdd / 2, trigger_edge=edge, response_edge=edge
            )
            initial, final = ends[stage, direction]
            settling = math.nan
            if math.isfinite(edge_s):
                segment, segment_s = calc.clip(differential, time_s, edge_s, spans[stage, direction][1])
                settled = calc.settlingTime(
                    segment, segment_s, initial=initial, final=final, absolute_tolerance=lsb / 2
                )
                settling = settled - edge_s
            delays[direction].append(delay)
            settlings[direction].append(settling)
    return AnalysisSettling(
        group=meas.group,
        index=meas.index,
        dut=meas.dut,
        lsb_v=lsb,
        full_scale_v=gain * tb.full_scale_v,
        gain=gain,
        window_s=window,
        ideal_step_v=gain * design,
        step_rise_v=step["rise"],
        step_fall_v=step["fall"],
        delay_rise_s=np.asarray(delays["rise"]),
        delay_fall_s=np.asarray(delays["fall"]),
        settling_rise_s=np.asarray(settlings["rise"]),
        settling_fall_s=np.asarray(settlings["fall"]),
    )


@analysis
def analyze_mismatch(meas: Meas) -> AnalysisMismatch:
    """Each Monte Carlo run's drawn plates (a probe's fF each, ``flow.layout.devices.momcap``) and the static
    linearity they give: the DAC alone, the converter with its design weights, and what no
    calibration recovers (``AnalysisMismatch``)."""

    tb = meas.param
    runs = int(meas.info.readbacks["runs"])
    drawn = {
        f"{kind}_{side}": np.column_stack(
            [
                meas.v[f"c{kind}_{side}_{stage}.drawn"] * 1e-15 if plate > 0 else np.zeros(runs)
                for stage, plate in enumerate(plates)
            ]
        )
        for side in ("p", "n")
        for kind, plates in (("main", tb.main_f), ("diff", tb.diff_f))
    }
    weights = np.asarray(tb.weights, dtype=np.float64)
    code_max = 2**tb.params.bits - 1
    decoder = np.append(2 * weights, 1.0)
    nominal = (tb.main_f, tb.diff_f)
    values = {name: np.empty(runs) for name in ("dac_inl", "dac_dnl", "dnl", "inl", "missing", "gap")}
    curves = []
    for run in range(runs):
        sides = tuple((drawn[f"main_{side}"][run], drawn[f"diff_{side}"][run]) for side in ("p", "n"))
        # the DAC alone, each side's: its plates' shares of its top plate over every control word
        transfers = [calc_dac_transfer((main - diff) / (main.sum() + diff.sum()), weights) for main, diff in sides]
        worse = max(transfers, key=lambda transfer: float(np.nanmax(np.abs(transfer[1]))))
        curves.append((worse[1], worse[2]))
        values["dac_inl"][run] = float(np.nanmax(np.abs(worse[1])))
        values["dac_dnl"][run] = max(float(np.nanmax(np.abs(transfer[2]))) for transfer in transfers)
        # the converter: every decision path of the drawn sides, from its A state
        a, b = calc_decision_steps(sides, 0.0, code_max, nominal=nominal, astate=tb.astate)
        paths = calc_paths(a, b, decoder, code_max)
        dnl, inl, missing = calc_paths_linearity(paths, code_max)
        values["dnl"][run], values["inl"][run] = float(np.max(np.abs(dnl))), float(np.max(np.abs(inl)))
        values["missing"][run], values["gap"][run] = (
            missing,
            calc_paths_gap(paths, (code_max + 1) / (2 * weights.sum())),
        )
    shown = int(np.argmin(np.abs(values["dac_inl"] - np.percentile(values["dac_inl"], 95))))
    return AnalysisMismatch(
        group=meas.group,
        index=meas.index,
        dut=meas.dut,
        pelgrom=tb.pelgrom,
        main_p_f=drawn["main_p"],
        diff_p_f=drawn["diff_p"],
        main_n_f=drawn["main_n"],
        diff_n_f=drawn["diff_n"],
        dac_inl_lsb=values["dac_inl"],
        dac_dnl_lsb=values["dac_dnl"],
        dnl_lsb=values["dnl"],
        inl_lsb=values["inl"],
        missing_codes=values["missing"],
        gap_lsb=values["gap"],
        dac_inl_curve_lsb=curves[shown][0],
        dac_dnl_curve_lsb=curves[shown][1],
    )


@analysis
def analyze_decisions(switching: Sequence[AnalysisSwitching]) -> comp.AnalysisDecisions:
    """One switching curve's trials as the comparator's decisions (``comp.AnalysisDecisions``), for
    the comparator's S-curve fit (``comp.analyze_offset_noise``): each trial's differential input,
    common mode and decision."""

    identity = measurement_identity(switching)
    first = switching[0]
    return comp.AnalysisDecisions(
        group=identity.group,
        index=identity.index,
        dut=identity.dut,
        info=first.info,
        param=first.param,
        trial_index=np.concatenate([np.asarray(item.trial_index) for item in switching]),
        vin_diff_v=np.concatenate([np.asarray(item.vin_diff_v, dtype=np.float64) for item in switching]),
        vin_cm_v=np.concatenate([np.asarray(item.vin_cm_v, dtype=np.float64) for item in switching]),
        decision=np.concatenate([np.asarray(item.decision) for item in switching]),
    )


@analysis
def analyze_transition(
    switching: Sequence[AnalysisSwitching],
    *,
    offset: comp.AnalysisOffsetNoise,
) -> AnalysisTransition:
    """Place one element's switching-curve fit at its CDAC side, element, direction, and mode.

    ``offset`` is the S-curve fit of exactly these points, made by ``comp.analyze_offset_noise`` (of
    ``analyze_decisions``); its 50% point is the transition. The runner chooses which sweep stage
    (for example only the fine points) forms the curve.
    """

    identity = measurement_identity(switching)
    check_identity(offset, identity, name="switching-curve fit")
    keys = set()
    for item in switching:
        if item.campaign != "cdac_ab":
            raise ValueError("A-to-B CDAC analysis requires campaign='cdac_ab'")
        keys.add((item.side, item.stage, item.direction, int(item.diffcaps)))
    if len(keys) != 1:
        raise ValueError("CDAC transition requires measurements of exactly one switching curve")
    side, element, direction, diffcaps = next(iter(keys))
    if side not in ("p", "n") or element is None or direction not in ("1to0", "0to1"):
        raise ValueError("CDAC measurement is missing a valid side, element, or direction")
    fitted_inputs = np.unique(np.round(np.concatenate([item.vin_diff_v for item in switching]), decimals=12))
    if not np.array_equal(fitted_inputs, offset.vin_diff_v):
        raise ValueError("switching-curve fit was not made from these measurements")
    valid = offset.validity != "non_monotonic" and math.isfinite(offset.offset_v)
    return AnalysisTransition(
        group=identity.group,
        index=identity.index,
        dut=identity.dut,
        side="p" if side == "p" else "n",
        element=element,
        direction="1to0" if direction == "1to0" else "0to1",
        diffcaps=diffcaps,
        vin_diff_v=offset.vin_diff_v,
        decision_probability=offset.decision_probability,
        trial_count=offset.trial_count,
        transition_v=offset.offset_v if valid else math.nan,
        valid=valid,
    )


@analysis
def analyze_cap_mismatch(
    switching: Sequence[AnalysisSwitching],
    *,
    transitions: Sequence[AnalysisTransition],
    comparator: comp.AnalysisOffsetNoise,
) -> AnalysisCapMismatch:
    """Decompose main/diff normalized capacitance of one ADC from its switching curves.

    ``transitions`` holds one fit per measured curve. The comparator offset is the reference point
    of every step: an element's normalized movement is ``(offset - transition) / VDD_DAC``. The
    points share one expectation of each stage's effective fraction, which the result carries.
    """

    identity = measurement_identity(switching)
    check_identity(transitions, identity, name="CDAC transition")
    first = switching[0]
    check_identity(comparator, Identity(identity.group, identity.index, first.comparator), name="comparator offset")
    if comparator.validity != "valid":
        raise ValueError("CDAC analysis requires a valid comparator offset")
    element_count = first.stages
    measured_curves = {(item.side, item.stage, item.direction, int(item.diffcaps)) for item in switching}
    by_curve = {(t.side, t.element, t.direction, t.diffcaps): t for t in transitions}
    if len(by_curve) != len(transitions) or set(by_curve) != measured_curves:
        raise ValueError("CDAC transitions must contain exactly one fit per measured switching curve")
    vdd_dac_v = {item.vdd_dac_v for item in switching}
    if len(vdd_dac_v) != 1:
        raise ValueError("CDAC measurements must share one VDD_DAC")
    reference_v = next(iter(vdd_dac_v))
    expected = first.expected_fraction
    if any(not np.array_equal(item.expected_fraction, expected, equal_nan=True) for item in switching):
        raise ValueError("CDAC measurements contain inconsistent ideal/PEX expectations")

    per_mode_direction = np.full((2, element_count, 2, 2), np.nan, dtype=np.float64)
    for (side, element, direction, diffcaps), transition in by_curve.items():
        if not 0 <= element < element_count:
            raise ValueError("CDAC measurement element is outside the configured CDAC")
        signed_step = (comparator.offset_v - transition.transition_v) / reference_v if transition.valid else math.nan
        side_sign = 1.0 if side == "p" else -1.0
        direction_sign = 1.0 if direction == "0to1" else -1.0
        per_mode_direction[0 if side == "p" else 1, element, diffcaps, 0 if direction == "1to0" else 1] = (
            side_sign * direction_sign * signed_step
        )

    main_fraction = np.full((2, element_count), np.nan, dtype=np.float64)
    diff_fraction = np.full((2, element_count), np.nan, dtype=np.float64)
    effective_fraction = np.full((2, element_count), np.nan, dtype=np.float64)
    effective_fraction_by_direction = per_mode_direction[:, :, 1, :].copy()
    direction_bias = np.full((2, element_count, 2), np.nan, dtype=np.float64)
    for side in range(2):
        for element in range(element_count):
            mode_values = []
            for diffcaps in range(2):
                directions = per_mode_direction[side, element, diffcaps]
                if np.all(np.isfinite(directions)):
                    mode_values.append(calc.average(directions))
                    direction_bias[side, element, diffcaps] = float((directions[0] - directions[1]) / 2.0)
                else:
                    mode_values.append(math.nan)
            # The fabricated cap-driver XOR is active high: dac_diffcaps=0
            # switches main and diff together, whereas dac_diffcaps=1 switches
            # them oppositely.  Normal ADC operation therefore measures
            # main-minus-diff in mode 1; mode 0 supplies main-plus-diff for the
            # component decomposition.
            w_plus, w_minus = mode_values
            if math.isfinite(w_minus):
                effective_fraction[side, element] = w_minus
            if math.isfinite(w_minus) and math.isfinite(w_plus):
                main_fraction[side, element] = (w_plus + w_minus) / 2.0
                diff_fraction[side, element] = (w_plus - w_minus) / 2.0

    return AnalysisCapMismatch(
        group=identity.group,
        index=identity.index,
        dut=identity.dut,
        main_fraction=main_fraction,
        diff_fraction=diff_fraction,
        effective_fraction=effective_fraction,
        effective_fraction_by_direction=effective_fraction_by_direction,
        direction_bias=direction_bias,
        expected_fraction=np.asarray(expected, dtype=np.float64),
    )


def metrics(*, settling: AnalysisSettling, mismatch: tuple[AnalysisMismatch, ...] = ()) -> dict[str, float]:
    """The scalar metrics of a characterization: the stages, the full scale, the drawn array's gain
    against its design and the LSB, the slowest
    and the MSB's settling, the largest delay and time constant, the window, and the steps' largest
    error against the design's weights at that gain (a unit drawn other than designed, at the PDK's
    smallest); and at each Monte Carlo condition (``mc_a<Pelgrom in 0.1 %·sqrt(fF)>``), the 95th
    percentile over its runs
    of the DAC's worst INL, the converter's worst INL with its design weights, and what no
    calibration recovers."""
    conditions = {
        f"mc_a{round(result.pelgrom * 1000)}_{name}": getattr(result, name)
        for result in mismatch
        for name in ("dac_inl_p95_lsb", "inl_p95_lsb", "gap_p95_lsb")
    }
    return conditions | {
        "stages": float(len(settling.settling_s)),
        "full_scale_v": settling.full_scale_v,
        "gain": settling.gain,
        "lsb_v": settling.lsb_v,
        "settling_max_s": float(max(settling.settling_s)),
        "settling_msb_s": float(settling.settling_s[0]),
        "delay_max_s": float(max(settling.delay_s)),
        "tau_max_s": float(max(settling.tau_s)),
        "window_s": settling.window_s,
        "step_error_lsb": settling.step_error_lsb,
    }
