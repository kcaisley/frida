"""The delay line and ring oscillator's design space (docs/pipeline.md): its named chains
(``@single``) and each of them at up to seven sizes (``@grid``); the testbench runs that
characterize one instance (``testbenches``) and the record they make (``results``).

Each instance at the PDK's supply and the nominal control (8/12 of it): a ring's frequency, swing,
duty cycle, power and energy per cycle, a delay line's delays and output transitions and its energy
per input cycle (4 ns period), either one's delay per stage; over the supply (90 and 110 % of its
own besides nominal) the same. A chain with a control (starved or on a shared tail) also over the control, 5/12
of the supply to all of it, and its gain about the nominal control. Three to ten Spectre runs, of
40 ns for a ring and 16 ns for a delay line.
"""

from __future__ import annotations

import dataclasses
import importlib
import math
from dataclasses import replace

import hdl21 as h

from flow.pipeline import Meas, Results, grid, single, widen

from .analysis import analyze_oscillation, analyze_propagation, metrics
from .params import CONTROL_SWEEP, NOMINAL_CONTROL, SUPPLY_SWEEP, Control, Params, Stage, TbParams
from .plots import (
    plot_delay_fall_control,
    plot_delay_fall_supply,
    plot_delay_rise_control,
    plot_delay_rise_supply,
    plot_duty_cycle_control,
    plot_duty_cycle_supply,
    plot_energy_control,
    plot_energy_supply,
    plot_fall_time_control,
    plot_kvco_control,
    plot_oscillation_frequency_control,
    plot_oscillation_frequency_supply,
    plot_rise_time_control,
    plot_stage_delay_supply,
)


@single
def ring5() -> Params:
    """Five-stage inverter ring oscillator, enabled."""
    return Params(stages=5, ring=True)


@single
def ring5_starved() -> Params:
    """Current-starved five-stage ring VCO."""
    return Params(stages=5, ring=True, control=Control.STARVED)


@single
def ring4_coupled() -> Params:
    """Four-stage pseudo-differential coupled ring, with its injection device (held off: no run drives
    inj, so the device only loads the first stage's outputs)."""
    return Params(stages=4, ring=True, differential=True, stage=Stage.COUPLED, inject=True)


@single
def ring4_tail() -> Params:
    """Four-stage coupled ring on a shared tail."""
    return Params(stages=4, ring=True, differential=True, stage=Stage.COUPLED, control=Control.TAIL)


@single
def chain4() -> Params:
    """Four-stage inverter delay line."""
    return Params(stages=4)


@single
def chain2_coupled() -> Params:
    """Two-stage coupled differential buffer."""
    return Params(stages=2, differential=True, stage=Stage.COUPLED)


@single
def chain4_starved() -> Params:
    """Four-stage current-starved delay line."""
    return Params(stages=4, control=Control.STARVED)


@grid
def sizes() -> dict[str, Params]:
    """Each named chain at every size it has devices for, by the chain's name and the size's:
    every width scaled together, to half, as it is, to twice and to four times (``half``,
    ``nominal``, ``double``, ``quadruple``); the coupling inverters alone doubled (``coupling``:
    coupled stages only); the starving devices and the tail doubled (``control``: controlled
    chains only); the stage inverters at twice their length (``long``)."""
    nominal = Params()
    widths = ("inv_n_w", "inv_p_w", "fb_n_w", "fb_p_w", "starve_n_w", "starve_p_w", "tail_w", "en_w", "inj_w")
    chains = {
        "ring5": ring5(),
        "ring5_starved": ring5_starved(),
        "ring4_coupled": ring4_coupled(),
        "ring4_tail": ring4_tail(),
        "chain4": chain4(),
        "chain2_coupled": chain2_coupled(),
        "chain4_starved": chain4_starved(),
    }
    spaces = {}
    for name, chain in chains.items():
        sized = {
            "half": {width: max(1, getattr(nominal, width) // 2) for width in widths},
            "nominal": {},
            "double": {width: 2 * getattr(nominal, width) for width in widths},
            "quadruple": {width: 4 * getattr(nominal, width) for width in widths},
        }
        if chain.stage is Stage.COUPLED:
            sized["coupling"] = {width: 2 * getattr(nominal, width) for width in ("fb_n_w", "fb_p_w")}
        if chain.control is not Control.NONE:
            sized["control"] = {width: 2 * getattr(nominal, width) for width in ("starve_n_w", "starve_p_w", "tail_w")}
        sized["long"] = {"inv_l": 2 * nominal.inv_l}
        for size, fields in sized.items():
            spaces[f"{name}_{size}"] = widen(Params(**{**chain.__dict__, **fields}))
    return spaces


def testbenches(pdk: str, params: Params) -> dict[str, TbParams]:
    """The testbench runs that characterize ``params`` in ``pdk``, by name (each run's folder): at
    the nominal control at each supply (``supply_<percent>``), and, a chain with a control, at the
    PDK's supply at each other control (``control_<twelfths>``; the nominal one is ``supply_100``)."""

    supply = importlib.import_module(f"pdk.{pdk}.hdl21.site").install.supply_voltage(h.pdk.Corner.TYP)
    # a ring runs the bench's 40 ns (two whole cycles to time at periods up to about 13 ns); a delay
    # line four input periods, the 3.5 its analysis reads and half a period's margin
    length = {} if params.ring else {"stop_time_s": 4 * TbParams.clock_period_s}
    nominal = TbParams(
        pdk=pdk, params=params, vdd=round(supply, 4), vcont_v=round(NOMINAL_CONTROL * supply, 4), **length
    )
    benches = {
        f"supply_{round(factor * 100)}": replace(nominal, vdd=round(factor * supply, 4)) for factor in SUPPLY_SWEEP
    }
    if params.control is not Control.NONE:
        for step in CONTROL_SWEEP:
            if not math.isclose(step, NOMINAL_CONTROL):
                benches[f"control_{round(step * 12)}"] = replace(nominal, vcont_v=round(step * supply, 4))
    return benches


def results(measurements: dict[str, Meas]) -> Results:
    """The record of one instance from its runs' measurements (``testbenches``): the metrics
    (``analysis.metrics``) and the plots of its sweeps over the supply and, a chain with a control,
    over the control; a ring's from its oscillation, a delay line's from its propagation."""

    by_supply = [measurements[f"supply_{round(factor * 100)}"] for factor in SUPPLY_SWEEP]
    design = by_supply[0].dut
    by_control = [
        measurements["supply_100" if math.isclose(step, NOMINAL_CONTROL) else f"control_{round(step * 12)}"]
        for step in (CONTROL_SWEEP if design.control is not Control.NONE else ())
    ]
    if design.ring:
        supply = analyze_oscillation(by_supply)
        control = analyze_oscillation(by_control) if by_control else None
        details = [
            plot_oscillation_frequency_supply(supply),
            plot_stage_delay_supply(supply),
            plot_energy_supply(supply),
            plot_duty_cycle_supply(supply),
        ]
        if control is not None:
            details += [
                plot_oscillation_frequency_control(control),
                plot_kvco_control(control),
                plot_energy_control(control),
                plot_duty_cycle_control(control),
            ]
        values = metrics(supply=supply, control=control)
    else:
        supply = analyze_propagation(by_supply)
        control = analyze_propagation(by_control) if by_control else None
        details = [
            plot_delay_rise_supply(supply),
            plot_delay_fall_supply(supply),
            plot_stage_delay_supply(supply),
            plot_energy_supply(supply),
        ]
        if control is not None:
            details += [
                plot_delay_rise_control(control),
                plot_delay_fall_control(control),
                plot_rise_time_control(control),
                plot_fall_time_control(control),
                plot_energy_control(control),
            ]
        values = metrics(supply=supply, control=control)
    return Results(
        metrics=dataclasses.asdict(values),
        details=details,
        # the run the viewer shows the waveforms of, by label
        waves={"nominal": "supply_100"},
    )
