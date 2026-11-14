"""The latch's runs (docs/pipeline.md), each by its name: its single designs (``@single``: the
nine latches, flip-flops, dividers and SR latches) and its grids (``@grid``: each of the nine at
other sizes); the testbench runs that characterize one instance (``testbenches``) and the record
they make (``results``).

Each instance at the core supply (2 ns clock, data 0.5 ns before each capturing edge; an SR
latch's set and reset 5.2 ns apart): the rising and falling delays to q (from clk, or from s and
r) and the energy per cycle, and the same over the supply (90 to 110 % of its own). A latch or
flip-flop over the data offset (-200 to 300 ps in 25 ps steps): setup at a 10 % delay pushout, and
hold. A flip-flop or divider over the clock period (1 ns to 30 ps): the highest frequency at which
every edge captures (a divider's: toggles). A C2MOS or DICE latch without reset struck while
holding a 1 (1 to 200 fC on its storage node): q's dip and the critical charge. Three to 34
Spectre runs.
"""

from __future__ import annotations

import dataclasses
import importlib
import math
from dataclasses import replace

import hdl21 as h
import numpy as np

from flow.pipeline import Meas, Results, grid, single, widen

from .analysis import analyze_constraint, analyze_sr, analyze_timing, analyze_upset, metrics
from .params import (
    CLOCKED_STYLES,
    DATA_OFFSET_SWEEP_S,
    PERIOD_SWEEP_S,
    SUPPLY_SWEEP,
    UPSET_CHARGES_C,
    UPSET_NODE,
    Bench,
    Params,
    Style,
    TbParams,
)
from .plots import (
    plot_captured_frequency,
    plot_captured_offset,
    plot_clock_to_q_fall_frequency,
    plot_clock_to_q_fall_offset,
    plot_clock_to_q_rise_frequency,
    plot_clock_to_q_rise_offset,
    plot_delay_fall_supply,
    plot_delay_rise_supply,
    plot_dip_charge,
    plot_energy_supply,
    plot_held_offset,
    plot_upset_charge,
)


@single
def latch() -> Params:
    """The static C2MOS latch."""
    return Params()


@single
def latch_rst() -> Params:
    """The C2MOS latch with asynchronous reset."""
    return Params(reset=True)


@single
def flop_rst() -> Params:
    """The master-slave flip-flop with reset."""
    return Params(flop=True, reset=True)


@single
def div2() -> Params:
    """The divide-by-two flip-flop with reset."""
    return Params(flop=True, divider=True, reset=True)


@single
def flop_tspc() -> Params:
    """The TSPC flip-flop."""
    return Params(style=Style.TSPC, flop=True)


@single
def div2_tspc() -> Params:
    """The TSPC divide-by-two."""
    return Params(style=Style.TSPC, flop=True, divider=True)


@single
def latch_dice() -> Params:
    """The DICE latch, upset-immune to one node."""
    return Params(style=Style.DICE)


@single
def sr_nand() -> Params:
    """The NAND SR latch."""
    return Params(style=Style.SR_NAND)


@single
def sr_nor() -> Params:
    """The NOR SR latch."""
    return Params(style=Style.SR_NOR)


@grid
def scaled() -> dict[str, Params]:
    """Each of the nine designs with every width scaled together, half to four times its own (none
    under one unit), each by its design's name and its scale."""
    spaces = {}
    for design in (latch, latch_rst, flop_rst, div2, flop_tspc, div2_tspc, latch_dice, sr_nand, sr_nor):
        base = design()
        for scale in (0.5, 1, 2, 4):
            widths = {name: max(1, round(scale * getattr(base, name))) for name in ("n_w", "p_w", "fb_n_w", "fb_p_w")}
            spaces[f"{design.name}_x{scale:g}"] = widen(Params(**{**base.__dict__, **widths}))
    return spaces


@grid
def strong_feedback() -> dict[str, Params]:
    """Each design with feedback devices (a C2MOS latch's, flip-flop's or divider's feedback
    inverters, a DICE latch's storage devices) with those alone at twice their width; a TSPC
    circuit and an SR latch have none."""
    spaces = {}
    for design in (latch, latch_rst, flop_rst, div2, latch_dice):
        base = design()
        spaces[design.name] = widen(Params(**{**base.__dict__, "fb_n_w": 2 * base.fb_n_w, "fb_p_w": 2 * base.fb_p_w}))
    return spaces


@grid
def long_channel() -> dict[str, Params]:
    """Each of the nine designs with every device at twice its length."""
    spaces = {}
    for design in (latch, latch_rst, flop_rst, div2, flop_tspc, div2_tspc, latch_dice, sr_nand, sr_nor):
        base = design()
        spaces[design.name] = widen(Params(**{**base.__dict__, "l": 2 * base.l}))
    return spaces


def testbenches(pdk: str, params: Params) -> dict[str, TbParams]:
    """The testbench runs that characterize ``params`` in ``pdk``, by name (each run's folder): at
    each supply (``supply_<percent>``); a latch or flip-flop at each data offset
    (``offset_<ps>ps``); a flip-flop or divider at each clock period (``period_<ps>ps``), its
    edges and its data offset scaled with a short clock; a C2MOS or DICE latch without reset struck
    with each charge (``upset_<fC>fc``)."""

    supply = importlib.import_module(f"pdk.{pdk}.hdl21.site").install.supply_voltage(h.pdk.Corner.TYP)
    nominal = TbParams(pdk=pdk, params=params, vdd=supply)
    benches = {
        f"supply_{round(factor * 100)}": replace(nominal, vdd=round(factor * supply, 4)) for factor in SUPPLY_SWEEP
    }
    if params.style in CLOCKED_STYLES and not params.divider:
        for offset in DATA_OFFSET_SWEEP_S:
            benches[f"offset_{round(offset * 1e12)}ps"] = replace(nominal, data_offset_s=offset)
    if params.flop:
        for period in PERIOD_SWEEP_S:
            benches[f"period_{round(period * 1e12)}ps"] = replace(
                nominal,
                clock_period_s=period,
                transition_time_s=min(50e-12, period / 8),
                data_offset_s=period / 4,
                reset_time_s=max(0.5e-9, 2 * period),
                cycles=12,
            )
    if params.style in UPSET_NODE and not (params.flop or params.reset):
        for charge in UPSET_CHARGES_C:
            benches[f"upset_{round(charge * 1e15)}fc"] = replace(nominal, bench=Bench.UPSET, charge_c=charge)
    return benches


def results(measurements: dict[str, Meas]) -> Results:
    """The record of one instance from its runs' measurements (``testbenches``): the metrics
    (``analysis.metrics``) and the plots of its sweeps over the supply and, where the design has
    them, over the data offset, the clock frequency and a strike's charge."""

    by_supply = [measurements[f"supply_{round(factor * 100)}"] for factor in SUPPLY_SWEEP]
    design = by_supply[0].dut
    supply = analyze_timing(by_supply) if design.style in CLOCKED_STYLES else analyze_sr(by_supply)
    plots = [plot_delay_rise_supply(supply), plot_delay_fall_supply(supply), plot_energy_supply(supply)]
    # the runs the viewer shows the waveforms of, by label
    waves = {"nominal": "supply_100"}
    constraint = period = upset = None
    if design.style in CLOCKED_STYLES and not design.divider:
        by_offset = [measurements[f"offset_{round(offset * 1e12)}ps"] for offset in DATA_OFFSET_SWEEP_S]
        offset = analyze_timing(by_offset)
        constraint = analyze_constraint(by_offset, timing=offset)
        plots += [
            plot_clock_to_q_rise_offset(offset),
            plot_clock_to_q_fall_offset(offset),
            plot_captured_offset(offset),
            plot_held_offset(offset),
        ]
    if design.flop:
        period = analyze_timing([measurements[f"period_{round(value * 1e12)}ps"] for value in PERIOD_SWEEP_S])
        plots += [
            plot_captured_frequency(period),
            plot_clock_to_q_rise_frequency(period),
            plot_clock_to_q_fall_frequency(period),
        ]
    if design.style in UPSET_NODE and not (design.flop or design.reset):
        upset = analyze_upset([measurements[f"upset_{round(charge * 1e15)}fc"] for charge in UPSET_CHARGES_C])
        plots += [plot_dip_charge(upset), plot_upset_charge(upset)]
        # the strike that flips it, or the strongest one where none does
        shown = upset.critical_charge_c if math.isfinite(upset.critical_charge_c) else UPSET_CHARGES_C[-1]
        nearest = int(np.argmin(np.abs(np.asarray(UPSET_CHARGES_C) - shown)))
        waves[f"{round(shown * 1e15)} fC strike"] = f"upset_{round(UPSET_CHARGES_C[nearest] * 1e15)}fc"
    values = metrics(supply=supply, constraint=constraint, period=period, upset=upset)
    return Results(metrics=dataclasses.asdict(values), details=plots, waves=waves)
