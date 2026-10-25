"""The comparator's design space (docs/pipeline.md): its families, each the cartesian product of its
knobs (``@family``), and its named instances (``@named``); the testbench runs that characterize one
instance (``runs``) and the record they make (``record``). The runner keeps, in each PDK, what
``params.valid`` admits there; readme.md says why the space is what it is."""

from __future__ import annotations

import importlib
from dataclasses import replace

import hdl21 as h
from hdl21.primitives import MosType

from flow.pipeline import Meas, Record, family, named

from .analysis import (
    analyze_clock_check,
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
    CHECK_CLOCK_S,
    CM_SWEEP,
    FRIDA1,
    KICKBACK_SOURCE,
    LARGE_V,
    METASTABILITY_RUN_V,
    NOISE_STROBE_S,
    NOMINAL_CM,
    SCURVE_DECISIONS,
    SCURVE_V,
    SMALL_V,
    SUPPLY_SWEEP,
    TOPOLOGIES,
    TOPOLOGY_SIZES,
    Bias,
    Params,
    Stages,
    State,
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


@family(pdks=("tsmc65", "tsmc28"), topology=("strongarm", "double_tail"))
def reference(topology: str) -> Params:
    """A topology at the characterization's short-channel sizes."""
    return Params(**TOPOLOGIES[topology], **TOPOLOGY_SIZES)


# each PDK's tails (its delays: 0.5, 1, 1.5 and 2 ns at 0.5 mV) and widths (its noise levels: 200,
# 150, 100, 70 and 50 uV, where its noise floor reaches them), where the base StrongARM is the more
# frugal family; TSMC28 at TSMC65's physical sizes (three of its 40 nm units to one of 120 nm, the
# tail 840 nm long)
@family(pdks=("tsmc65",), tail_l=(14,), k=(3, 6, 12, 32, 64))
@family(pdks=("tsmc28",), tail_l=(28,), k=(18, 36, 72, 192))
@family(pdks=("tpsc65",), tail_l=(6,), k=(2, 4, 8, 16, 32))
@family(pdks=("tpsc65",), tail_l=(16, 26), k=(2,))
@family(pdks=("tpsc65",), tail_l=(36,), k=(2, 4, 8, 16, 40))
@family(pdks=("ihp130",), tail_l=(4,), k=(2.5, 4, 10, 20, 40))
@family(pdks=("ihp130",), tail_l=(11,), k=(1.5, 3, 6, 12, 24))
@family(pdks=("ihp130",), tail_l=(20,), k=(1.5, 2.5, 6, 12, 24))
@family(pdks=("ihp130",), tail_l=(28,), k=(1.25, 2, 5, 10, 20))
@family(pdks=("lf150",), tail_l=(4,), k=(1, 2, 5, 24))
@family(pdks=("lf150",), tail_l=(13,), k=(1, 2))
@family(pdks=("lf150",), tail_l=(23,), k=(1, 2, 5, 16))
@family(pdks=("lf150",), tail_l=(34,), k=(1, 1.5, 5, 10))
@family(pdks=("tower180",), tail_l=(3,), k=(2.5, 4, 10, 20, 40))
@family(pdks=("tower180",), tail_l=(9,), k=(1.5, 3, 6, 12, 24))
@family(pdks=("tower180",), tail_l=(15,), k=(1.5, 2.5, 6, 12, 24))
@family(pdks=("tower180",), tail_l=(21,), k=(1.25, 2.5, 5, 10, 20))
def base_strongarm(tail_l: int, k: float) -> Params:
    """The StrongARM at the short-channel sizes with every width times ``k`` but its tail, 4 k units
    wide and ``tail_l`` minimum lengths long: the tail's length sets the delay, ``k`` the noise."""
    widths = ("diffpair_w", "rst_w", "latch_on_w", "latch_init_w", "srlatch_n_w", "srlatch_p_w")
    sizes = {name: round(k * TOPOLOGY_SIZES[name]) for name in widths}
    return Params(**TOPOLOGIES["strongarm"], **{**TOPOLOGY_SIZES, **sizes, "tail_w": round(4 * k), "tail_l": tail_l})


# each PDK's C_TAIL/C_P (its delays) and widths (its noise levels), where the dynamic bias is the
# more frugal family
@family(pdks=("tsmc65",), ratio=(3.5, 2.75, 2.25), k=(0.75, 1.5, 3, 6, 12))
@family(pdks=("tpsc65",), ratio=(3.5,), k=(1, 2, 4, 8))
@family(pdks=("tpsc65",), ratio=(2.75,), k=(0.75, 2, 4, 8))
@family(pdks=("lf150",), ratio=(6,), k=(0.75, 2.5))
def dynamic_bias(ratio: float, k: float) -> Params:
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
        **{**TOPOLOGIES["double_tail_modified"], "preamp_bias": Bias.DYNAMIC},
        **{
            **TOPOLOGY_SIZES,
            **sizes,
            "diffpair_l": 1,
            "tail_l": 1,
            "preamp_c_ff": c_p,
            "bias_c_ff": round(ratio * c_p),
        },
    )


@named
def frida1() -> Params:
    """FRIDA-1's fabricated comparator."""
    return FRIDA1


@named(swept=False)
def c040() -> Params:
    """The example double tail of the retired size sweep (its topology 40 at its half sizes)."""
    return Params(
        comp_stages=Stages.DOUBLE,
        preamp_diff_xtors=MosType.NMOS,
        preamp_bias=Bias.SWITCHED,
        latch_inner_on_xtors=State.CLOCK,
        latch_outer_on_xtors=State.CLOCK,
        latch_inner_init_xtors=State.SIGNAL,
        latch_outer_init_xtors=State.OMIT,
        diffpair_w=19,
        diffpair_l=5,
        tail_w=3,
        tail_l=13,
        rst_w=4,
        rst_l=1,
        latch_on_w=13,
        latch_on_l=6,
        latch_init_w=17,
        latch_init_l=17,
        srlatch_n_w=2,
        srlatch_p_w=4,
    )


@named(swept=False)
def strongarm() -> Params:
    """The StrongARM at the characterization's sizes (``reference``'s ``x1``)."""
    return Params(**TOPOLOGIES["strongarm"], **TOPOLOGY_SIZES)


@named(swept=False)
def double_tail() -> Params:
    """The double tail at the characterization's sizes (``reference``'s ``x1``)."""
    return Params(**TOPOLOGIES["double_tail"], **TOPOLOGY_SIZES)


@named(swept=False)
def triple_tail() -> Params:
    """The triple tail at the characterization's sizes."""
    return Params(**TOPOLOGIES["triple_tail"], **TOPOLOGY_SIZES)


@named(swept=False)
def double_tail_self_timed() -> Params:
    """The self-timed double tail at the characterization's sizes."""
    return Params(**TOPOLOGIES["double_tail_self_timed"], **TOPOLOGY_SIZES)


@named(swept=False)
def double_tail_modified() -> Params:
    """The modified double tail at the characterization's sizes."""
    return Params(**TOPOLOGIES["double_tail_modified"], **TOPOLOGY_SIZES)


@named(swept=False)
def double_tail_modified_self_timed() -> Params:
    """The self-timed modified double tail at the characterization's sizes."""
    return Params(**TOPOLOGIES["double_tail_modified_self_timed"], **TOPOLOGY_SIZES)


def runs(pdk: str, params: Params) -> dict[str, TbParams]:
    """The testbench runs that characterize ``params`` in ``pdk``, by name (each run's folder): the
    noise-free decisions over the input at the clock and at twice it (``metastability``,
    ``metastability_check``: the delay near metastability, and whether the comparator decides in
    time), three decisions at the small and the large input (delay, energy), one onto a DAC-like
    source (kickback), the transient-noise S-curve at each common mode (noise, offset), and both
    inputs at each supply."""

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
    for fraction in CM_SWEEP:
        benches[f"scurve_cm{round(fraction * 24)}"] = replace(
            nominal,
            vin_cm_values_v=(round(fraction * supply, 4),),
            vin_diff_values_v=SCURVE_V,
            conversions=SCURVE_DECISIONS,
            input_order="shuffled",
            noise=True,
            waveform_sample_interval_s=NOISE_STROBE_S,
        )
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
    return benches


def record(measurements: dict[str, Meas]) -> Record:
    """The record of one instance from its runs' measurements (``runs``): the metrics
    (``analysis.metrics``) and the plots of its condition sweeps; a comparator that does not decide
    within the clock raises."""

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
    if not clock.decides_in_time:
        raise RuntimeError(
            f"no decision within the {clock.evaluation_s * 1e9:g} ns evaluation: {'; '.join(clock.reasons)}"
        )
    offsets = [analyze_offset_noise([decisions[f"scurve_cm{round(fraction * 24)}"]]) for fraction in CM_SWEEP]
    nominal = offsets[CM_SWEEP.index(NOMINAL_CM)]
    scurve = analyze_scurve([decisions[f"scurve_cm{round(NOMINAL_CM * 24)}"]])
    supply = [delays[f"supply_{round(factor * 100)}"] for factor in SUPPLY_SWEEP]
    plots = [
        plot_metastability(metastability["metastability"]),
        plot_noise_cm(offsets),
        plot_offset_cm(offsets),
        plot_delay_supply_small(supply),
        plot_delay_supply_large(supply),
        plot_energy_supply(analyze_power([measurements[f"supply_{round(factor * 100)}"] for factor in SUPPLY_SWEEP])),
        plot_scurve(scurve),
    ]
    if scurve.total_unresolved_fraction > 0:
        plots.append(plot_scurve_unresolved(scurve))
    return Record(
        metrics=metrics(
            small=delays["small"],
            large=delays["large"],
            metastability=metastability["metastability"],
            power=analyze_power([measurements["small"], measurements["large"]]),
            kickback=analyze_kickback(measurements["kickback"]),
            offsets=offsets,
            nominal=nominal,
            scurve=scurve,
            supply=supply,
        ),
        details=plots,
        # the runs the viewer shows the waveforms of, by label
        waves={
            "0.5 mV input": "small",
            "100 mV input": "large",
            "metastability": "metastability",
            "kickback": "kickback",
        },
    )
