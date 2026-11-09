"""The comparator's runs (docs/pipeline.md), each by its name: its grids (``@grid``: a design
with some of its parameters widened, ``widen``, every point of it; the ADC's comparators, each
PDK's, by name), its single designs (``@single``) and its optimizations (``@optimize``: the least
energy, area and noise of a comparator for a converter of each resolution, within its bounds,
``params.ADC_FULL_SCALE`` and the constants after it, over its space; the first search NMOS input
pairs alone: the placements that give the layout area in a minute, the generator's,
``subckt._place``, are NMOS ones, and a design without one cannot meet the area bound); the
testbench runs that characterize one design (``runs``) and the record they make (``record``);
readme.md says why the space is what it is."""

from __future__ import annotations

import dataclasses
import importlib
import math
from dataclasses import replace

import hdl21 as h
from hdl21.primitives import MosType

from flow.pipeline import (
    Bound,
    Evidence,
    Level,
    Meas,
    Pdk,
    Problem,
    Record,
    every,
    grid,
    optimize,
    single,
    steps,
    widen,
)

from .analysis import (
    analyze_clock_check,
    analyze_common_mode,
    analyze_decisions,
    analyze_delay,
    analyze_kickback,
    analyze_metastability,
    analyze_offset_noise,
    analyze_power,
    analyze_scurve,
    analyze_timing,
    metrics,
)
from .params import (
    ADC_FULL_SCALE,
    AREA_SIDE_UM,
    AREA_WEIGHT,
    CHECK_CLOCK_S,
    CM_SWEEP,
    DECISION_S,
    FRIDA1,
    KICKBACK_SOURCE,
    LARGE_V,
    METASTABILITY_RUN_V,
    NOISE_STROBE_S,
    NOISE_WEIGHT,
    NOMINAL_CM,
    SCURVE_DECISIONS,
    SCURVE_V,
    SMALL_V,
    SUPPLY_SWEEP,
    Bias,
    Latch,
    Params,
    TbParams,
)
from .plots import (
    plot_delay_supply_large,
    plot_delay_supply_small,
    plot_energy_supply,
    plot_metastability,
    plot_noise_cm,
    plot_offset_cm,
    plot_scurve,
    plot_scurve_unresolved,
)


@grid
def topologies() -> Params:
    """Every latch with either tail at the characterization's sizes, the input pair 32 to 512 units
    wide, and with a dynamic bias C_P 30 or 120 fF: how the topologies compare as they widen."""
    space = widen(Params())
    space.latch = every(Latch)
    space.bias = every(Bias)
    space.diffpair_w = steps(32, 512, n=3, log=True)
    space.preamp_c_ff = steps(30, 120, n=2, log=True, when=Bias.DYNAMIC)
    return space


@grid
def base_strongarm(pdk: Pdk) -> dict[str, Params]:
    """The ADC's comparators (flow.adc.runs: TSMC65's comparator grid, elsewhere the PDK's StrongARM
    ladder at its longest tail), where the base StrongARM is the more frugal topology: each PDK's
    tails (its delays: 0.5, 1, 1.5 and 2 ns at 0.5 mV) and widths (its noise levels: 200, 150, 100,
    70 and 50 uV, where its noise floor reaches them), each point by its tail's length in minimum
    lengths and its width factor (``tail_l=14, k=3``); TSMC28 at TSMC65's physical sizes (three of
    its 40 nm units to one of 120 nm, the tail 840 nm long)."""
    ladders = {
        Pdk.TSMC65: {14: (3, 6, 12, 32, 64)},
        Pdk.TSMC28: {28: (18, 36, 72, 192)},
        Pdk.TPSC65: {6: (2, 4, 8, 16, 32), 16: (2,), 26: (2,), 36: (2, 4, 8, 16, 40)},
        Pdk.IHP130: {
            4: (2.5, 4, 10, 20, 40),
            11: (1.5, 3, 6, 12, 24),
            20: (1.5, 2.5, 6, 12, 24),
            28: (1.25, 2, 5, 10, 20),
        },
        Pdk.LF150: {4: (1, 2, 5, 24), 13: (1, 2), 23: (1, 2, 5, 16), 34: (1, 1.5, 5, 10)},
        Pdk.TOWER180: {
            3: (2.5, 4, 10, 20, 40),
            9: (1.5, 3, 6, 12, 24),
            15: (1.5, 2.5, 6, 12, 24),
            21: (1.25, 2.5, 5, 10, 20),
        },
    }
    return {
        f"tail_l={tail_l}, k={k}": widen(_base_strongarm(tail_l, k))
        for tail_l, factors in ladders[pdk].items()
        for k in factors
    }


def _base_strongarm(tail_l: int, k: float) -> Params:
    """The StrongARM at the short-channel sizes with every width times ``k`` but its tail, 4 k units
    wide and ``tail_l`` minimum lengths long: the tail's length sets the delay, ``k`` the noise."""
    base = Params()
    widths = ("diffpair_w", "rst_w", "latch_on_w", "latch_init_w", "srlatch_n_w", "srlatch_p_w")
    sizes = {name: round(k * getattr(base, name)) for name in widths}
    return Params(latch=Latch.STRONGARM, **sizes, tail_w=round(4 * k), tail_l=tail_l)


@grid
def dynamic_bias(pdk: Pdk) -> dict[str, Params]:
    """Each PDK's C_TAIL/C_P (its delays) and widths (its noise levels), where the dynamic bias is the
    more frugal topology, each point by its ratio and width factor (``ratio=3.5, k=2``)."""
    ladders = {
        Pdk.TSMC65: {3.5: (0.75, 1.5, 3, 6, 12), 2.75: (0.75, 1.5, 3, 6, 12), 2.25: (0.75, 1.5, 3, 6, 12)},
        Pdk.TPSC65: {3.5: (1, 2, 4, 8), 2.75: (0.75, 2, 4, 8)},
        Pdk.LF150: {6: (0.75, 2.5)},
    }
    return {
        f"ratio={ratio}, k={k}": widen(_dynamic_bias(ratio, k))
        for ratio, factors in ladders.get(pdk, {}).items()
        for k in factors
    }


def _dynamic_bias(ratio: float, k: float) -> Params:
    """The dynamic-bias double tail (the modified double tail's latch, the input pair's tail a
    minimum-length switch onto C_TAIL): a unit per 60 fF of C_P (input pair 64, tail switch 4, latch
    16, reset 4, no device under 4) times ``k``, C_TAIL ``ratio`` times C_P, every device at the
    minimum length: the ratio sets the delay, ``k`` the noise."""
    unit = {
        "diffpair_w": 64,
        "tail_w": 4,
        "rst_w": 4,
        "latch_on_w": 16,
        "latch_init_w": 16,
        "srlatch_n_w": 4,
        "srlatch_p_w": 8,
    }
    sizes = {name: max(4, round(k * units)) for name, units in unit.items()}
    c_p = round(60 * k)
    return Params(
        latch=Latch.DOUBLE_TAIL_MODIFIED,
        bias=Bias.DYNAMIC,
        **sizes,
        diffpair_l=1,
        tail_l=1,
        preamp_c_ff=c_p,
        bias_c_ff=round(ratio * c_p),
    )


@single
def frida1() -> Params:
    """FRIDA-1's fabricated comparator."""
    return FRIDA1


@single
def strongarm() -> Params:
    """The StrongARM at the characterization's sizes."""
    return Params(latch=Latch.STRONGARM)


@single
def double_tail() -> Params:
    """The double tail at the characterization's sizes."""
    return Params(latch=Latch.DOUBLE_TAIL)


@single
def triple_tail() -> Params:
    """The triple tail at the characterization's sizes."""
    return Params(latch=Latch.TRIPLE_TAIL)


@single
def double_tail_self_timed() -> Params:
    """The self-timed double tail at the characterization's sizes."""
    return Params(latch=Latch.DOUBLE_TAIL_SELF_TIMED)


@single
def double_tail_modified() -> Params:
    """The modified double tail at the characterization's sizes."""
    return Params(latch=Latch.DOUBLE_TAIL_MODIFIED)


@single
def double_tail_modified_self_timed() -> Params:
    """The self-timed modified double tail at the characterization's sizes."""
    return Params(latch=Latch.DOUBLE_TAIL_MODIFIED_SELF_TIMED)


def testbenches(pdk: str, params: Params, level: Level = Level.FULL) -> dict[str, TbParams]:
    """The testbench runs that characterize ``params`` in ``pdk`` at ``level``, by name (each run's
    folder), the quick ones first. ``Level.SCREEN``, no transient noise (about 25 s): the
    noise-free decisions over the input at the clock and at twice it (``metastability``,
    ``metastability_check``: the delay near metastability, and whether the comparator decides in
    time), three decisions at the small and the large input (delay, energy), one onto a DAC-like
    source (kickback), and both inputs at each supply. ``Level.SEARCH`` adds the transient-noise
    S-curve at the nominal common mode (noise, offset); ``Level.FULL`` the S-curves at the other
    common modes. Its characterization is SPICE already: ``Level.CIRCUIT`` runs what ``FULL`` does."""

    supply = importlib.import_module(f"pdk.{pdk}.hdl21.site").install.supply_voltage(h.pdk.Corner.TYP)
    # the nominal run: the supply, its common mode; each run changes what it measures
    nominal = TbParams(pdk=pdk, params=params, vdd=round(supply, 4), vin_cm_values_v=(round(NOMINAL_CM * supply, 4),))
    benches = {
        "metastability": replace(nominal, vin_diff_values_v=METASTABILITY_RUN_V),
        "metastability_check": replace(
            nominal,
            vin_diff_values_v=METASTABILITY_RUN_V,
            reset_time_s=CHECK_CLOCK_S[0],
            evaluation_time_s=CHECK_CLOCK_S[1],
        ),
        "small": replace(nominal, vin_diff_values_v=(SMALL_V,), conversions=3),
        "large": replace(nominal, vin_diff_values_v=(LARGE_V,), conversions=3),
        "kickback": replace(
            nominal,
            vin_diff_values_v=(SMALL_V,),
            source_resistance_ohm=KICKBACK_SOURCE[0],
            source_capacitance_f=KICKBACK_SOURCE[1],
        ),
    }
    for factor in SUPPLY_SWEEP:
        vdd = factor * supply
        benches[f"supply_{round(factor * 100)}"] = TbParams(
            pdk=pdk,
            params=params,
            vdd=round(vdd, 4),
            vin_cm_values_v=(round(NOMINAL_CM * vdd, 4),),
            vin_diff_values_v=(SMALL_V, LARGE_V),
            conversions=2,
        )
    fractions = {Level.SCREEN: (), Level.SEARCH: (NOMINAL_CM,), Level.FULL: CM_SWEEP, Level.CIRCUIT: CM_SWEEP}[level]
    for fraction in sorted(fractions, key=lambda fraction: fraction != NOMINAL_CM):
        benches[f"scurve_cm{round(fraction * 24)}"] = replace(
            nominal,
            vin_cm_values_v=(round(fraction * supply, 4),),
            vin_diff_values_v=SCURVE_V,
            conversions=SCURVE_DECISIONS,
            input_order="shuffled",
            noise=True,
            waveform_sample_interval_s=NOISE_STROBE_S,
        )
    return benches


def record(measurements: dict[str, Meas]) -> Record:
    """The record of one instance from the measurements of the runs of any level (``runs``): the
    metrics (``analysis.metrics``: None where its runs did not run) and the plots of its condition
    sweeps. A comparator that does not decide within the clock is recorded so
    (``decides_in_time``), not raised: an optimization learns from it."""

    decisions = {name: analyze_decisions(meas) for name, meas in measurements.items()}
    delays = {
        name: analyze_delay(
            measurements[name],
            decisions=decisions[name],
            timing=analyze_timing(measurements[name], decisions=decisions[name]),
        )
        for name in (
            "metastability",
            "metastability_check",
            "small",
            "large",
            *(f"supply_{round(f * 100)}" for f in SUPPLY_SWEEP),
        )
    }
    metastability = {
        name: analyze_metastability(measurements[name], delay=delays[name])
        for name in ("metastability", "metastability_check")
    }
    clock = analyze_clock_check(
        [measurements["metastability"], measurements["metastability_check"]],
        decisions=[decisions["metastability"], decisions["metastability_check"]],
        metastability=[metastability["metastability"], metastability["metastability_check"]],
    )
    names = [f"scurve_cm{round(fraction * 24)}" for fraction in CM_SWEEP]
    scurves = [decisions[name] for name in names if name in measurements]
    # each S-curve's fit over the common mode, as a lab campaign's captures give it
    common_mode = analyze_common_mode(scurves) if scurves else None
    nominal_run = f"scurve_cm{round(NOMINAL_CM * 24)}"
    nominal = analyze_offset_noise([decisions[nominal_run]]) if nominal_run in measurements else None
    scurve = analyze_scurve([decisions[nominal_run]]) if nominal_run in measurements else None
    supply = [delays[f"supply_{round(factor * 100)}"] for factor in SUPPLY_SWEEP]
    plots = [
        plot_metastability(metastability["metastability"]),
        plot_delay_supply_small(supply),
        plot_delay_supply_large(supply),
        plot_energy_supply(analyze_power([measurements[f"supply_{round(factor * 100)}"] for factor in SUPPLY_SWEEP])),
    ]
    if common_mode is not None:
        plots[1:1] = [plot_noise_cm(common_mode), plot_offset_cm(common_mode)]
    if scurve is not None:
        plots.append(plot_scurve(scurve))
        if scurve.total_unresolved_fraction > 0:
            plots.append(plot_scurve_unresolved(scurve))
    values = metrics(
        small=delays["small"],
        large=delays["large"],
        metastability=metastability["metastability"],
        power=analyze_power([measurements["small"], measurements["large"]]),
        kickback=analyze_kickback(measurements["kickback"]),
        supply=supply,
        clock=clock,
        common_mode=common_mode,
        nominal=nominal,
        scurve=scurve,
    )
    return Record(
        metrics=dataclasses.asdict(values),
        details=plots,
        # the runs the viewer shows the waveforms of, by label
        waves={
            "0.5 mV input": "small",
            "100 mV input": "large",
            "metastability": "metastability",
            "kickback": "kickback",
        },
    )


# ---------------------------------------------------------------- optimizations


@optimize(budget=500, pdks=(Pdk.TSMC65,), workers=48)
def adc_10bit(pdk: Pdk) -> Problem:
    """A comparator for a 10-bit converter in ``pdk``: the least energy, area and noise, its noise
    at most the converter's quantization noise at the PDK's supply, its layout within the
    resolution's square, its delay within the decision's time. Searched: every latch and tail, each
    size on a log scale, the latch devices' lengths too (TSMC65's longer ones still decide within
    the evaluation); the dynamic bias's capacitors with it."""

    supply = importlib.import_module(f"pdk.{pdk.name.lower()}.hdl21.site").install.supply_voltage(h.pdk.Corner.TYP)
    quantization_v = 2 * ADC_FULL_SCALE * supply / 2**10 / math.sqrt(12)
    space = widen(Params(input_pair=MosType.NMOS))
    space.latch = every(Latch)
    space.bias = every(Bias)
    space.diffpair_w = steps(2, 8192, log=True)
    space.diffpair_l = steps(1, 16, log=True)
    space.tail_w = steps(2, 4096, log=True)
    space.tail_l = steps(1, 64, log=True)
    space.rst_w = steps(2, 2048, log=True)
    space.latch_on_w = steps(2, 2048, log=True)
    space.latch_init_w = steps(2, 2048, log=True)
    space.latch_on_l = steps(1, 32, log=True)
    space.latch_init_l = steps(1, 32, log=True)
    space.preamp_c_ff = steps(10, 16000, log=True, when=Bias.DYNAMIC)
    space.bias_c_ff = steps(10, 64000, log=True, when=Bias.DYNAMIC)
    return Problem(
        cost={"energy_0p5mv_j": 1.0, "layout_area_um2": AREA_WEIGHT, "noise_v": (NOISE_WEIGHT, quantization_v)},
        bounds=(
            # its devices over a layout's densest packing already exceed it: no layout can meet it
            Bound("layout_area_um2", AREA_SIDE_UM[10] ** 2, since=Evidence.NETLIST),
            # the layout only adds capacitance: a design too slow before it is too slow after
            Bound("delay_0p5mv_s", DECISION_S, since=Evidence.PRELAYOUT),
            Bound("decides_in_time", True, since=Evidence.PRELAYOUT),
            # the layout moves the noise either way: judged after it alone
            Bound("noise_v", quantization_v, since=Evidence.POSTLAYOUT),
        ),
        space=space,
    )


@optimize(budget=500, pdks=(Pdk.TSMC65,), workers=48)
def adc_12bit(pdk: Pdk) -> Problem:
    """A comparator for a 12-bit converter in ``pdk``: the least energy, area and noise, its noise
    at most the converter's quantization noise at the PDK's supply, its layout within the
    resolution's square, its delay within the decision's time. Searched: every latch and tail, each
    size on a log scale, the latch devices' lengths too (TSMC65's longer ones still decide within
    the evaluation); the dynamic bias's capacitors with it."""

    supply = importlib.import_module(f"pdk.{pdk.name.lower()}.hdl21.site").install.supply_voltage(h.pdk.Corner.TYP)
    quantization_v = 2 * ADC_FULL_SCALE * supply / 2**12 / math.sqrt(12)
    space = widen(Params(input_pair=MosType.NMOS))
    space.latch = every(Latch)
    space.bias = every(Bias)
    space.diffpair_w = steps(2, 8192, log=True)
    space.diffpair_l = steps(1, 16, log=True)
    space.tail_w = steps(2, 4096, log=True)
    space.tail_l = steps(1, 64, log=True)
    space.rst_w = steps(2, 2048, log=True)
    space.latch_on_w = steps(2, 2048, log=True)
    space.latch_init_w = steps(2, 2048, log=True)
    space.latch_on_l = steps(1, 32, log=True)
    space.latch_init_l = steps(1, 32, log=True)
    space.preamp_c_ff = steps(10, 16000, log=True, when=Bias.DYNAMIC)
    space.bias_c_ff = steps(10, 64000, log=True, when=Bias.DYNAMIC)
    return Problem(
        cost={"energy_0p5mv_j": 1.0, "layout_area_um2": AREA_WEIGHT, "noise_v": (NOISE_WEIGHT, quantization_v)},
        bounds=(
            # its devices over a layout's densest packing already exceed it: no layout can meet it
            Bound("layout_area_um2", AREA_SIDE_UM[12] ** 2, since=Evidence.NETLIST),
            # the layout only adds capacitance: a design too slow before it is too slow after
            Bound("delay_0p5mv_s", DECISION_S, since=Evidence.PRELAYOUT),
            Bound("decides_in_time", True, since=Evidence.PRELAYOUT),
            # the layout moves the noise either way: judged after it alone
            Bound("noise_v", quantization_v, since=Evidence.POSTLAYOUT),
        ),
        space=space,
    )


@optimize(budget=500, pdks=(Pdk.TSMC65,), workers=48)
def adc_14bit(pdk: Pdk) -> Problem:
    """A comparator for a 14-bit converter in ``pdk``: the least energy, area and noise, its noise
    at most the converter's quantization noise at the PDK's supply, its layout within the
    resolution's square, its delay within the decision's time. Searched: every latch and tail, each
    size on a log scale, the latch devices' lengths too (TSMC65's longer ones still decide within
    the evaluation); the dynamic bias's capacitors with it."""

    supply = importlib.import_module(f"pdk.{pdk.name.lower()}.hdl21.site").install.supply_voltage(h.pdk.Corner.TYP)
    quantization_v = 2 * ADC_FULL_SCALE * supply / 2**14 / math.sqrt(12)
    space = widen(Params(input_pair=MosType.NMOS))
    space.latch = every(Latch)
    space.bias = every(Bias)
    space.diffpair_w = steps(2, 8192, log=True)
    space.diffpair_l = steps(1, 16, log=True)
    space.tail_w = steps(2, 4096, log=True)
    space.tail_l = steps(1, 64, log=True)
    space.rst_w = steps(2, 2048, log=True)
    space.latch_on_w = steps(2, 2048, log=True)
    space.latch_init_w = steps(2, 2048, log=True)
    space.latch_on_l = steps(1, 32, log=True)
    space.latch_init_l = steps(1, 32, log=True)
    space.preamp_c_ff = steps(10, 16000, log=True, when=Bias.DYNAMIC)
    space.bias_c_ff = steps(10, 64000, log=True, when=Bias.DYNAMIC)
    return Problem(
        cost={"energy_0p5mv_j": 1.0, "layout_area_um2": AREA_WEIGHT, "noise_v": (NOISE_WEIGHT, quantization_v)},
        bounds=(
            # its devices over a layout's densest packing already exceed it: no layout can meet it
            Bound("layout_area_um2", AREA_SIDE_UM[14] ** 2, since=Evidence.NETLIST),
            # the layout only adds capacitance: a design too slow before it is too slow after
            Bound("delay_0p5mv_s", DECISION_S, since=Evidence.PRELAYOUT),
            Bound("decides_in_time", True, since=Evidence.PRELAYOUT),
            # the layout moves the noise either way: judged after it alone
            Bound("noise_v", quantization_v, since=Evidence.POSTLAYOUT),
        ),
        space=space,
    )
