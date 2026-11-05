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
"""

from __future__ import annotations

import math

import numpy as np

from flow.analysis import calc
from flow.analysis.calc import calc_dac_transfer, calc_decision_steps, calc_paths, calc_paths_gap, calc_paths_linearity
from flow.pipeline import Meas, analysis

from .types import AnalysisMismatch, AnalysisSettling


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
