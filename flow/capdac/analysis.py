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
from scipy.constants import Boltzmann
from scipy.stats import binom

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
    squares; its full scale is half the sum of its steps (the mean of both directions), the range
    the converter's decisions span, and the settling is measured to half its LSB. Each stage's P
    top plate alone, in the direction the converter switches it (``side_settling_s``); the
    supply's energy over each window; the P side's bottom plates' farthest excursion past the rails."""

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
    # [Razavi-ADC] Eqs. (11.3)-(11.4), p. 211: a load C_L on the top plate scales every step by
    #   m C_0 / (m C_0 + C_L), a gain error; the estimator is the code's own, the least-squares fit
    #   g = s . d / d . d of the measured rising steps s_k to the design's d_k (the heavy stages set
    #   it), not Sec. 8.2.1, p. 145's slope of the line through the end points
    # Terms: s_k ``step["rise"]``; d_k ``TbParams.ideal_step_v``; C_L the drawn top plate's load
    #   beyond the design's plates (the units' capacitance to their shields, the stubs).
    # Holds for: a gain common to every stage: the heavy stages drawn as designed (no unit at the
    #   kit's smallest, which draws a stage heavier than its weight); a unit drawn other than
    #   designed is the step error.
    gain = float(np.dot(step["rise"], design) / np.dot(design, design))
    # not in the reference texts: the drawn full scale, half the sum of the two-sided steps
    #   (the steps of the design sum to 2 FS, ``TbParams``), the mean of both directions
    # Terms: FS ``full_scale``; the steps ``step["rise"]``, ``step["fall"]`` (negative).
    # Holds for: a converter that switches every stage once (the input range its decisions span).
    full_scale = float(np.sum(step["rise"]) - np.sum(step["fall"])) / 4
    # [Razavi-ADC] Sec. 12.2.1, p. 237: Delta = 1 LSB, the differential range 2 FS over 2^N
    lsb = 2 * full_scale / 2**tb.params.bits
    side = meas.v["vdac_p"]
    delays: dict[str, list[float]] = {direction: [] for direction, _ in directions}
    settlings: dict[str, list[float]] = {direction: [] for direction, _ in directions}
    side_settlings: list[float] = []
    for stage in range(tb.stages):
        state, bottom = meas.v[f"dac_state_p_{stage}"], meas.v[f"dut_p.main_{stage}"]
        for direction, edge in directions:
            # [Baker] Fig. 10.9, p. 333: the delay from the input's 50 % point to the output's
            # the state's edge in this window: the stimulus switches each state once each way
            edge_s, _, delay = calc.delay(
                state, bottom, time_s, vdd / 2, vdd / 2, trigger_edge=edge, response_edge=edge
            )
            initial, final = ends[stage, direction]
            settling = math.nan
            # [Razavi-ADC] Sec. 8.2.2, p. 150: the settling time, from the input's change until the
            #   output stays within +-0.5 LSB of its final value
            # Terms: the input the state's 50 % crossing ``edge_s``; the output the differential
            #   top plate; its final value at the window's end.
            if math.isfinite(edge_s):
                segment, segment_s = calc.clip(differential, time_s, edge_s, spans[stage, direction][1])
                settled = calc.settlingTime(
                    segment, segment_s, initial=initial, final=final, absolute_tolerance=lsb / 2
                )
                settling = settled - edge_s
            delays[direction].append(delay)
            settlings[direction].append(settling)
            # [Razavi-ADC] Sec. 16.2.1, p. 346: the converter's own condition, one side switching a
            #   decision; not in the reference texts: its direction by the A state, a stage of A 0
            #   rising and of A 1 falling (flow.adc's own, ``TbParams.astate``)
            # Terms: the top plate ``vdac_p``; the band half the drawn LSB, as the bench's.
            if (direction == "rise") == (tb.astate[stage] == 0):
                start, stop = spans[stage, direction]
                one = math.nan
                if math.isfinite(edge_s):
                    segment, segment_s = calc.clip(side, time_s, edge_s, stop)
                    one = (
                        calc.settlingTime(
                            segment,
                            segment_s,
                            initial=calc.value(side, time_s, start),
                            final=calc.value(side, time_s, stop),
                            absolute_tolerance=lsb / 2,
                        )
                        - edge_s
                    )
                side_settlings.append(one)
    energies = None
    if "vdd" in meas.i:
        # [Razavi-ADC] Fig. 16.29, p. 348: the energy a source delivers, V times its charge, here
        #   E = V_DD integral of I_DD over each window
        # Terms: V_DD ``vdd``, the bench's supply (the reference and the drivers'); I_DD ``i["vdd"]``.
        # Ours against the source: the source's capacitor alone; here both sides' plates, drivers,
        #   sense inverters and their leakage (``Model.of`` takes the plates' share off).
        # Holds for: each window, from its start to its end.
        energies = {
            direction: np.asarray(
                [
                    vdd * calc.integ(*calc.clip(meas.i["vdd"], time_s, *spans[stage, direction]))
                    for stage in range(tb.stages)
                ]
            )
            for direction, _ in directions
        }
    plates = [meas.v[name] for name in meas.v if name.startswith(("dut_p.main_", "dut_p.diff_"))]
    # [Razavi-Analog] Sec. 15.4.2, p. 641: a forward bias of 300 mV draws negligible junction current,
    #   the limit an excursion past a rail is held to here
    # not in the reference texts: the code's own derivation, from the rails a driver's drain junctions
    #   sit between: a bottom plate's farthest excursion past either rail, max(V - V_DD, -V) over the P
    #   side's main and difference plates, which forward-biases its driver's drain junction and
    #   puts V_DD plus it across its off device; the guards' terminal limit, 1.1 times the nominal
    #   supply (``flow.circuit.oppoint.stress``), is the fast corner's supply itself, so there any
    #   excursion passes it: ``excursion_v`` reports it, nothing here judges it against that limit
    # Terms: V each saved bottom plate ``dut_p.main_<k>``, ``dut_p.diff_<k>``; V_DD ``vdd``.
    # Holds for: the P side (the N side its mirror, the opposite edges).
    excursion = max((max(float(np.max(v)) - vdd, -float(np.min(v))) for v in plates), default=math.nan)
    return AnalysisSettling(
        group=meas.group,
        index=meas.index,
        dut=meas.dut,
        lsb_v=lsb,
        full_scale_v=full_scale,
        gain=gain,
        window_s=window,
        ideal_step_v=gain * design,
        step_rise_v=step["rise"],
        step_fall_v=step["fall"],
        delay_rise_s=np.asarray(delays["rise"]),
        delay_fall_s=np.asarray(delays["fall"]),
        settling_rise_s=np.asarray(settlings["rise"]),
        settling_fall_s=np.asarray(settlings["fall"]),
        side_settling_s=np.asarray(side_settlings),
        energy_rise_j=None if energies is None else energies["rise"],
        energy_fall_j=None if energies is None else energies["fall"],
        excursion_v=excursion,
        settle_s=tb.params.settle_ps * 1e-12,
        budget_s=tb.params.settle_ps * 1e-12 / tb.params.settle_margin,
        reference_v=vdd,
        load_f=tb.load_f,
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
    # not in the reference texts: the decoder's weights, twice each stage's (both sides' step in
    #   the code) and the last decision's 1, summing to 2^N - 1 (the SAR's own: flow.adc's decoding)
    decoder = np.append(2 * weights, 1.0)
    nominal = (tb.main_f, tb.diff_f)
    values = {name: np.empty(runs) for name in ("dac_inl", "dac_dnl", "dnl", "inl", "missing", "gap")}
    curves = []
    for run in range(runs):
        sides = tuple((drawn[f"main_{side}"][run], drawn[f"diff_{side}"][run]) for side in ("p", "n"))
        # [Razavi-ADC] Eq. (8.5), p. 145: DNL; Sec. 8.2, Fig. 8.11, p. 147: INL against the line
        #   through the end points; Example 8.2, p. 144: the end points' LSB (Example 8.4, p. 146: a
        #   heavy MSB); each side's DAC alone over every control word, its steps the plates' shares of
        #   its top plate ([Razavi-ADC] Eq. (11.3), p. 211) (calc_dac_transfer)
        # Terms: each stage's step (main - diff) / (sum main + sum diff), of the run's drawn plates;
        #   the codes by the design weights; the LSB the end points' over the total weight.
        # Holds for: the plates alone (no parasitic, no drivers).
        transfers = [calc_dac_transfer((main - diff) / (main.sum() + diff.sum()), weights) for main, diff in sides]
        # not in the reference texts: the reduction over the sides, the INL (and its curves) the
        #   worse side's by its worst |INL|, the DNL the worst |DNL| of either side
        worse = max(transfers, key=lambda transfer: float(np.nanmax(np.abs(transfer[1]))))
        curves.append((worse[1], worse[2]))
        values["dac_inl"][run] = float(np.nanmax(np.abs(worse[1])))
        values["dac_dnl"][run] = max(float(np.nanmax(np.abs(transfer[2]))) for transfer in transfers)
        # the converter: every decision path of the drawn sides, from its A state ([Razavi-ADC] Sec.
        #   16.2.1, p. 346: one side a decision), each decision's step the switching side's plates over
        #   its top plate with no parasitic (0.0: the plates alone), in the LSB the nominal plates give
        #   (calc_decision_steps)
        a, b = calc_decision_steps(sides, 0.0, code_max, nominal=nominal, astate=tb.astate)
        paths = calc_paths(a, b, decoder, code_max)
        # [Razavi-ADC] Eq. (12.11), p. 242: DNL_j, each code's width against the mean width (the
        #   end points' LSB); Eq. (12.12), p. 244: INL_j = V_j - j Delta against the line through the
        #   end points, the first and the last transition: the DNLs' running sum, every transition's
        # Terms: V_j each transition of the decision paths; Delta the mean code width.
        # Holds for: codes 1 to 2^N - 2 (the end codes are unbounded), the design weights decoding.
        dnl, _, missing = calc_paths_linearity(paths, code_max)
        inl = calc.inl(dnl, endpoint_correct=False)
        values["dnl"][run], values["inl"][run] = float(np.max(np.abs(dnl))), float(np.max(np.abs(inl)))
        # not in the reference texts: a paper's, Hsu's missing level: with every decision's true
        #   weight, the widest decision path over a code's width, less one; the code's width in
        #   unit steps 2^N / (2 W) (calc_paths_gap)
        # Terms: W ``weights.sum()``; the paths of the drawn sides from the A state.
        # Holds for: an ideal calibration of every decision's weight; the plates alone.
        values["missing"][run], values["gap"][run] = (
            missing,
            calc_paths_gap(paths, (code_max + 1) / (2 * weights.sum())),
        )
    # not in the reference texts: the run shown, the one nearest the 95th percentile of the DAC's INL
    # Terms: ``values["dac_inl"]`` each run's worst |INL| of the DAC in its own LSB.
    # Holds for: one coefficient's runs; the record's DAC curves (``dac_inl``, ``dac_dnl``) are its.
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

    # not in the reference texts: bookkeeping, no quantity computed: one curve's captures concatenated,
    #   each trial's differential input, common mode and decision as the comparator's S-curve fit
    #   (``comp.analyze_offset_noise``) reads them
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
    # not in the reference texts: the transition, the S-curve fit's 50 % point (the comparator's
    #   offset fit, ``comp.analyze_offset_noise``, of this curve), valid where the curve rises
    #   monotonically and the fit found a point
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
        # not in the reference texts: the bench's own, a stage's fraction of its side, the input that
        #   balances its switching against the comparator's offset over the reference,
        #   (V_OS - V_transition) / V_REF ([Razavi-ADC] Eq. (11.3), p. 211: a step k C_0 / C V_REF)
        # Terms: V_OS ``comparator.offset_v``; V_transition the curve's 50 % point; V_REF ``vdd_dac_v``.
        # Holds for: a top plate whose whole load the fraction's denominator counts.
        signed_step = (comparator.offset_v - transition.transition_v) / reference_v if transition.valid else math.nan
        # not in the reference texts: the fraction's sign, + for the P side and - for the N side (a
        #   stage moves its side's top plate, the differential the other way on N), + for 0 to 1 and
        #   - for 1 to 0 (the plate falls), so every stage's fraction is positive as designed
        # Terms: ``side`` p or n; ``direction`` 0to1 or 1to0; ``signed_step`` the curve's fraction.
        # Holds for: the bench's comparator between the two sides (an N side's step moves its input
        #   the other way).
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
                    # not in the reference texts: a mode's fraction the mean of its two directions'
                    #   (their difference, halved, the direction bias)
                    # Terms: ``directions`` the mode's 1-to-0 and 0-to-1 fractions.
                    # Holds for: a mode with both directions measured (NaN otherwise).
                    mode_values.append(calc.average(directions))
                    direction_bias[side, element, diffcaps] = float((directions[0] - directions[1]) / 2.0)
                else:
                    mode_values.append(math.nan)
            # The fabricated cap-driver XOR is active high: dac_diffcaps=0
            # switches main and diff together, whereas dac_diffcaps=1 switches
            # them oppositely.  Normal ADC operation therefore measures
            # main-minus-diff in mode 1; mode 0 supplies main-plus-diff for the
            # component decomposition.
            # not in the reference texts: mode 0 gives main + diff, mode 1 main - diff, so
            #   main = (w+ + w-) / 2 and diff = (w+ - w-) / 2; the direction bias half the 1-to-0 less
            #   the 0-to-1 fraction
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


def metrics(
    *,
    settling: AnalysisSettling,
    mismatch: tuple[AnalysisMismatch, ...] = (),
    slow: AnalysisSettling | None = None,
    fast: AnalysisSettling | None = None,
) -> dict[str, float]:
    """The scalar metrics of a characterization (``types.Metrics`` names each and which way is
    better): the stages, the drawn full scale, its share of the reference and whether it meets
    frida's 0.80, the drawn array's gain against its design and the LSB, the sampled noise against
    the quantization noise, the slowest and the MSB's settling (both sides switched), the slowest one
    side in the converter's direction, the slowest at the slow and fast corners, the slowest over the
    drivers' budget and whether every stage settles within ``settle_ps`` at every corner run, the
    largest delay and time constant, the window, the steps' largest error against the design's
    weights at that gain (a unit drawn other than designed, at the PDK's smallest), the supply's
    energy and the bottom plates' farthest excursion past the rails; and at each Monte Carlo
    condition (``mc_a<coefficient in 0.1 %·sqrt(fF)>``, a capacitor's), the 95th percentile over its
    runs of the DAC's worst INL, the converter's worst INL with its design weights, and what no
    calibration recovers, each with its 95 % upper confidence bound. A number not measured is NaN,
    and a maximum over a stage not measured is NaN too."""
    conditions = {
        f"mc_a{round(result.pelgrom * 1000)}_{name}{suffix}": value
        for result in mismatch
        for name, values in (
            ("dac_inl", result.dac_inl_lsb),
            ("inl", result.inl_lsb),
            ("gap", result.gap_lsb),
        )
        for suffix, value in (
            ("_p95_lsb", getattr(result, f"{name}_p95_lsb")),
            ("_p95_upper_lsb", _p95_upper(values)),
        )
    }
    corners = [run for run in (slow, fast) if run is not None]
    # not in the reference texts: the reductions over the stages, the slowest stage's settling (NaN
    #   where a stage's is not measured), both sides' and one side's in the converter's direction
    # Terms: ``settling_s`` each stage's slower direction, both sides switched; ``side_settling_s``
    #   the P side's alone in the converter's direction (``analyze_settling``).
    # Holds for: the typical corner's run; NaN propagates where a stage is unmeasured.
    slowest = float(np.max(settling.settling_s))
    side = float(np.max(settling.side_settling_s)) if settling.side_settling_s is not None else math.nan
    # not in the reference texts: every settling judged against settle_ps: the typical run's and
    #   each corner run's, both sides' and one side's (where a run measures it)
    # Terms: ``slowest``, ``side``; each corner run's (``slow``, ``fast``) slowest stage, both ways.
    # Holds for: the runs its level ran (the search's: the typical run alone).
    every = [
        slowest,
        side,
        *(float(np.max(run.settling_s)) for run in corners),
        *(float(np.max(run.side_settling_s)) for run in corners if run.side_settling_s is not None),
    ]
    fraction = settling.full_scale_v / settling.reference_v
    # [Razavi-ADC] Eq. (11.52), p. 230: both sides' kT/C over the drawn top plate, C_top / g, against
    #   Eq. (12.6), p. 239: the quantization noise Delta^2 / 12 of the drawn LSB
    # Terms: C_top ``load_f`` (the design's plates), g ``gain``; Delta ``lsb_v``; T 300 K (the sizing's).
    # Holds for: the typical corner's top plate; the comparator's input not on it; C_top / g the drawn
    #   top plate while the gain is common to every stage (no unit at the kit's smallest: there the
    #   drawn plates exceed the design's and C_top / g is not the drawn top plate).
    ktc = 2 * Boltzmann * 300.0 * settling.gain / settling.load_f / (settling.lsb_v**2 / 12)
    energies = [e for e in (settling.energy_rise_j, settling.energy_fall_j) if e is not None]
    return conditions | {
        "stages": float(len(settling.settling_s)),
        "full_scale_v": settling.full_scale_v,
        # not in the reference texts: the full scale over the reference, and frida's rule of at
        #   least 0.80 of it (the owner's: the converter's input range)
        "full_scale_fraction": fraction,
        "full_scale_meets_rule": bool(fraction >= 0.80),
        "gain": settling.gain,
        "lsb_v": settling.lsb_v,
        "ktc_noise_ratio": ktc,
        "settling_max_s": slowest,
        # not in the reference texts: C0's settling, the heaviest stage's (with its weight
        #   redistributed it is not the slowest)
        # Terms: ``settling_s[0]``, C0 first (``params._weights``). Holds for: the typical run.
        "settling_msb_s": float(settling.settling_s[0]),
        "settling_side_max_s": side,
        "settling_slow_max_s": float(np.max(slow.settling_s)) if slow is not None else math.nan,
        "settling_fast_max_s": float(np.max(fast.settling_s)) if fast is not None else math.nan,
        # not in the reference texts: the slowest typical settling, both sides' or one side's, over
        #   the drivers' budget (settle_ps / settle_margin, ``subckt._drive_r_ohm``; NaN where either
        #   is not measured), and whether every measured settling, at every corner run, is within
        #   settle_ps ([Razavi-ADC] Sec. 8.2.2, p. 150: t_s)
        "settling_budget_ratio": float(np.max([slowest, side])) / settling.budget_s,
        "settles_in_time": bool(all(math.isfinite(t) and t <= settling.settle_s for t in every)),
        # not in the reference texts: the largest delay and time constant over the stages (NaN
        #   where a stage's is not measured)
        # Terms: ``delay_s`` each stage's driver delay, state to main plate at 50 %; ``tau_s`` the
        #   model's time constants (``AnalysisSettling.tau_s``). Holds for: the typical run.
        "delay_max_s": float(np.max(settling.delay_s)),
        "tau_max_s": float(np.max(settling.tau_s)),
        "window_s": settling.window_s,
        "step_error_lsb": settling.step_error_lsb,
        # not in the reference texts: the supply's energy summed over every window, both directions
        # Terms: ``energy_rise_j``, ``energy_fall_j`` each window's V_DD integral of I_DD
        #   (``analyze_settling``). Holds for: the typical run, both sides on the one supply; NaN
        #   where the run saved no supply current.
        "supply_energy_j": float(sum(np.sum(e) for e in energies)) if energies else math.nan,
        # not in the reference texts: the farthest excursion of the typical run's and the corner
        #   runs' (NaN where one is unmeasured)
        # Terms: each run's ``excursion_v`` (``analyze_settling``). Holds for: the P side's plates.
        "excursion_v": float(np.max([settling.excursion_v, *(run.excursion_v for run in corners)])),
    }


def _p95_upper(values: np.ndarray) -> float:
    """The 95 % upper confidence bound of the 95th percentile of ``values`` (NaN left out): the
    least order statistic X_(r) with P(Binomial(n, 0.95) <= r - 1) >= 0.95; NaN where n is too few."""
    # not in the reference texts: a distribution-free confidence bound of a quantile from the order
    #   statistics, P(X_(r) >= x_0.95) = P(Binomial(n, 0.95) <= r - 1) (100 runs: the second largest)
    # Terms: n the runs measured; X_(r) the r-th smallest.
    # Holds for: independent runs of one condition.
    found = np.sort(np.asarray(values, dtype=np.float64)[np.isfinite(values)])
    n = len(found)
    rank = int(binom.ppf(0.95, n, 0.95)) + 1 if n else 0
    return float(found[rank - 1]) if 0 < rank <= n else math.nan
