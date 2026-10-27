"""The sampling switch's design space (docs/pipeline.md): its grids (``@grid``: designs with some of
their parameters widened, ``widen``, every point of each) and its named instances (``@named``); the
testbench runs that characterize one instance (``runs``) and the record they make (``record``).

The characterization's switches (FRIDA-1's transmission gate, with and without dummies, the NMOS
switch, the bootstrapped NMOS switch) 8 to 128 units wide and at twice their length, and the
bootstrapped switch as an on-resistance ladder (the ADC study's samplers), in every PDK. Each
instance is run on the bench every switch is characterized on (``params``): over the input level
(1/12 to 11/12 of the supply) the on-resistance into the load, the track error, the pedestal and the
input's feedthrough while holding; at the nominal point (mid-supply input) those and the bandwidth
and droop; over the supply (90 to 120 % of its own, mid-supply input) the on-resistance and pedestal.
Fourteen Spectre runs, about a minute in all.
"""

from __future__ import annotations

import importlib
from dataclasses import replace

import hdl21 as h

from flow.pipeline import Meas, Record, every, grid, named, steps, widen

from .analysis import analyze_hold, analyze_track, metrics
from .params import FRIDA1, NOMINAL_VIN, SUPPLY_SWEEP, VIN_SWEEP, WAVE_VIN, Params, SwitchType, TbParams
from .plots import (
    plot_feedthrough_vin,
    plot_pedestal_supply,
    plot_pedestal_vin,
    plot_ron_supply,
    plot_ron_vin,
    plot_track_error_vin,
)


@grid
def scaled() -> dict[str, Params]:
    """Each switch 8 to 128 units wide (a quarter to four times FRIDA-1's): the transmission gate
    with and without dummies, the NMOS switch, and the bootstrapped one, each width by name, its
    boost capacitor half the switch and its helpers an eighth, none under 4 units (the finest PDK's
    minimum width)."""
    tgate = widen(Params(switch_type=SwitchType.TGATE))
    tgate.mos_w = steps(8, 128, n=5, log=True)
    tgate.dummy = every(bool)
    nmos = widen(Params(switch_type=SwitchType.NMOS))
    nmos.mos_w = steps(8, 128, n=5, log=True)
    return {
        "tgate": tgate,
        "nmos": nmos,
        **{
            f"bootstrap_w{width}": widen(
                Params(
                    switch_type=SwitchType.BOOTSTRAP, mos_w=width, boot_w=max(4, width // 8), cap_w=max(4, width // 2)
                )
            )
            for width in (8, 16, 32, 64, 128)
        },
    }


@grid
def long_channel() -> dict[str, Params]:
    """Each switch at twice its length: the transmission gate with and without dummies, the NMOS
    switch, the bootstrapped one."""
    spaces = {}
    for switch in (SwitchType.TGATE, SwitchType.NMOS, SwitchType.BOOTSTRAP):
        space = widen(Params(switch_type=switch, mos_l=2))
        if switch is SwitchType.TGATE:
            space.dummy = every(bool)
        spaces[switch.name.lower()] = space
    return spaces


@grid
def boost_ladder() -> dict[str, Params]:
    """The bootstrapped switch as an on-resistance ladder (the ADC study's samplers), each rung by its
    width: 32 to 160 units wide, its boost capacitor as wide and its helpers an eighth, so every rung
    is boosted alike and its on-resistance falls with its width; at 32 units the doubled boost
    capacitor of the base size, then 2, 3.5 and 5 times that."""
    return {
        f"w{width}": widen(Params(switch_type=SwitchType.BOOTSTRAP, mos_w=width, boot_w=width // 8, cap_w=width))
        for width in (32, 64, 112, 160)
    }


@named(swept=False)
def frida1() -> Params:
    """FRIDA-1's fabricated sampler: the transmission gate, 32 units a side."""
    return FRIDA1


@named(swept=False)
def tgate_dummy() -> Params:
    """The transmission gate with half-size charge-injection dummies."""
    return Params(dummy=True)


@named(swept=False)
def nmos() -> Params:
    """The NMOS switch alone."""
    return Params(switch_type=SwitchType.NMOS)


@named(swept=False)
def bootstrap() -> Params:
    """The bootstrapped NMOS switch."""
    return Params(switch_type=SwitchType.BOOTSTRAP)


def runs(pdk: str, params: Params) -> dict[str, TbParams]:
    """The testbench runs that characterize ``params`` in ``pdk``, by name (each run's folder): the
    input stepping a twelfth of the supply at each input level (``vin_<twelfths>``), and at
    mid-supply input at each other supply (``supply_<percent>``; the nominal one is ``vin_6``)."""

    supply = importlib.import_module(f"pdk.{pdk}.hdl21.site").install.supply_voltage(h.pdk.Corner.TYP)
    nominal = TbParams(
        pdk=pdk,
        params=params,
        vdd=round(supply, 4),
        input_voltage=round(NOMINAL_VIN * supply, 4),
        input_step_v=round(supply / 12, 4),
    )
    benches = {
        f"vin_{round(fraction * 12)}": replace(nominal, input_voltage=round(fraction * supply, 4))
        for fraction in VIN_SWEEP
    }
    for factor in SUPPLY_SWEEP:
        if factor != 1.0:
            benches[f"supply_{round(factor * 100)}"] = replace(
                nominal,
                vdd=round(factor * supply, 4),
                input_voltage=round(NOMINAL_VIN * factor * supply, 4),
                input_step_v=round(factor * supply / 12, 4),
            )
    return benches


def record(measurements: dict[str, Meas]) -> Record:
    """The record of one instance from its runs' measurements (``runs``): the metrics
    (``analysis.metrics``) and the plots of its sweeps over the input level and the supply."""

    by_vin = [measurements[f"vin_{round(fraction * 12)}"] for fraction in VIN_SWEEP]
    by_supply = [
        measurements[f"vin_{round(NOMINAL_VIN * 12)}" if factor == 1.0 else f"supply_{round(factor * 100)}"]
        for factor in SUPPLY_SWEEP
    ]
    track, hold = analyze_track(by_vin), analyze_hold(by_vin)
    supply_track, supply_hold = analyze_track(by_supply), analyze_hold(by_supply)
    return Record(
        metrics=metrics(track=track, hold=hold, supply=supply_track),
        details=[
            plot_ron_vin(track),
            plot_track_error_vin(track),
            plot_pedestal_vin(hold),
            plot_feedthrough_vin(hold),
            plot_ron_supply(supply_track),
            plot_pedestal_supply(supply_hold),
        ],
        # the runs the viewer shows the waveforms of, by label
        waves={
            f"input {round(fraction * 12)}/12 of the supply": f"vin_{round(fraction * 12)}" for fraction in WAVE_VIN
        },
    )
