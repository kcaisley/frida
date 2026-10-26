"""The CDAC's analyses: from its testbench's measurement (``flow.pipeline.Meas``: every saved signal
on the simulator's own time axis, the run's ``TbParams``) to each stage's settling
(``analyze_settling``) and the numbers its characterization reports (``metrics``).

For each stage and direction ``analyze_settling`` measures, with ``flow.analysis.calc``, on the raw
time points (nothing is resampled):

- the differential top plate's step (``vdac_p`` less ``vdac_n``), from the window's start to its end;
- the driver's delay: from the P side's state (``dac_state_p_<stage>``) crossing mid-supply to its
  main bottom plate (``dac_botplate_p_<stage>``) crossing it;
- the settling time: from that input edge until the differential top plate stays within half the
  converter's LSB (2 full scale / 2^adc_bits) of its final value.
"""

from __future__ import annotations

import math

import numpy as np

from flow.analysis import calc
from flow.pipeline import Meas, analysis

from .types import AnalysisSettling


@analysis
def analyze_settling(meas: Meas) -> AnalysisSettling:
    """Every stage's step, driver delay and settling to half an LSB, both directions."""

    tb = meas.param
    vdd, window, time_s = float(tb.vdd), float(tb.window_s), meas.time_s
    lsb = tb.lsb_v
    differential = meas.v["vdac_p"] - meas.v["vdac_n"]
    columns = ("step", "delay", "settling")
    rows: dict[str, dict[str, list[float]]] = {
        direction: {key: [] for key in columns} for direction in ("rise", "fall")
    }
    for stage in range(tb.stages):
        state, bottom = meas.v[f"dac_state_p_{stage}"], meas.v[f"dac_botplate_p_{stage}"]
        for direction, edge in (("rise", "rising"), ("fall", "falling")):
            start = tb.window_start_s(stage, rising=direction == "rise")
            stop = min(start + window, float(time_s[-1]))
            # the state's edge in this window: the stimulus switches each state once each way
            edge_s, _, delay = calc.delay(
                state, bottom, time_s, vdd / 2, vdd / 2, trigger_edge=edge, response_edge=edge
            )
            initial = calc.value(differential, time_s, start)
            final = calc.value(differential, time_s, stop)
            settling = math.nan
            if math.isfinite(edge_s):
                segment, segment_s = calc.clip(differential, time_s, edge_s, stop)
                settled = calc.settlingTime(
                    segment, segment_s, initial=initial, final=final, absolute_tolerance=lsb / 2
                )
                settling = settled - edge_s
            rows[direction]["step"].append(final - initial)
            rows[direction]["delay"].append(delay)
            rows[direction]["settling"].append(settling)
    array = {f"{key}_{direction}": np.asarray(rows[direction][key]) for direction in rows for key in columns}
    return AnalysisSettling(
        group=meas.group,
        index=meas.index,
        dut=meas.dut,
        lsb_v=lsb,
        full_scale_v=tb.full_scale_v,
        window_s=window,
        ideal_step_v=tb.ideal_step_v,
        step_rise_v=array["step_rise"],
        step_fall_v=array["step_fall"],
        delay_rise_s=array["delay_rise"],
        delay_fall_s=array["delay_fall"],
        settling_rise_s=array["settling_rise"],
        settling_fall_s=array["settling_fall"],
    )


def metrics(*, settling: AnalysisSettling) -> dict[str, float]:
    """The scalar metrics of a characterization: the stages, the full scale and the LSB, the slowest
    and the MSB's settling, the largest delay and time constant, the window, and the steps' largest
    error against the capacitances' (the simulator's precision)."""
    return {
        "stages": float(len(settling.settling_s)),
        "full_scale_v": settling.full_scale_v,
        "lsb_v": settling.lsb_v,
        "settling_max_s": float(max(settling.settling_s)),
        "settling_msb_s": float(settling.settling_s[0]),
        "delay_max_s": float(max(settling.delay_s)),
        "tau_max_s": float(max(settling.tau_s)),
        "window_s": settling.window_s,
        "step_error_lsb": settling.step_error_lsb,
    }
