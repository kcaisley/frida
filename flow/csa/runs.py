"""The charge-sensitive amplifier's design space (docs/pipeline.md): its named instances
(``@single``) and its grid (``@grid``: each named amplifier at its other sizes); the testbench runs
that characterize one instance (``testbenches``) and the record they make (``results``).

The four amplifiers (the NMOS-input and PMOS-input Krummenacher amplifiers, the NMOS-input one with
a long feedback device and the one with a reset switch) at seven sizes, in every PDK. Each instance
is run on the bench every amplifier is characterized on (``params``: 100 fF of detector, the charge
through 1 fF, 10 fF of load, a 4 uA load, 10 nA of discharge, the Krummenacher reference at 45 % of
the supply) at its own supply: the response to 0.25, 0.5, 1 and 2 fC (gain, peaking and rise time
at the smallest, the gain's linearity to the largest, its time over threshold and return to the
baseline) and, but for the reset amplifier, the output noise from 1 Hz to 1 GHz without charge
(rms, and over the smallest charge's gain the ENC). Over the supply (90 and 110 % of its own
besides nominal) the smallest charge's response and the noise again. Seven to nine Spectre runs.
"""

from __future__ import annotations

import dataclasses
import importlib

import hdl21 as h
from hdl21.primitives import MosType

from flow.pipeline import Meas, Results, grid, single, widen

from .analysis import analyze_noise, analyze_pulse, analyze_supply, metrics
from .params import CHARGES_C, SUPPLY_SWEEP, VREF, Feedback, Params, Stimulus, TbParams
from .plots import (
    plot_amplitude_charge,
    plot_enc_supply,
    plot_gain_charge,
    plot_gain_supply,
    plot_noise_density,
    plot_peaking_supply,
    plot_power_supply,
    plot_pulse,
    plot_tot_charge,
)


@single
def krum() -> Params:
    """NMOS input, Krummenacher feedback."""
    return Params()


@single
def krum_pmos() -> Params:
    """PMOS input, Krummenacher feedback."""
    return Params(input_xtors=MosType.PMOS)


@single
def continuous() -> Params:
    """NMOS input, a long feedback device."""
    return Params(feedback=Feedback.CONTINUOUS, fb_l=16)


@single
def reset() -> Params:
    """NMOS input, a reset switch."""
    return Params(feedback=Feedback.RESET, fb_l=1)


@grid
def scaled() -> dict[str, Params]:
    """Each named amplifier at its other sizes, by name: the widths of its input device, cascode and
    load scaled together (half, as named, twice and four times), the input device alone twice as
    wide or as long, and the load at twice its length; the feedback as it is."""
    spaces = {}
    for name, base in (("krum", krum()), ("krum_pmos", krum_pmos()), ("continuous", continuous()), ("reset", reset())):
        for factor in (0.5, 1, 2, 4):
            space = widen(base)
            for width in ("in_w", "cas_w", "load_w"):
                setattr(space, width, int(getattr(base, width) * factor))
            spaces[f"{name}_x{factor:g}"] = space
        for size in ("in_w", "in_l", "load_l"):
            space = widen(base)
            setattr(space, size, 2 * getattr(base, size))
            spaces[f"{name}_{size}_x2"] = space
    return spaces


def testbenches(pdk: str, params: Params) -> dict[str, TbParams]:
    """The testbench runs that characterize ``params`` in ``pdk``, by name (each run's folder): at
    the PDK's supply the response to each charge (``q<attocoulombs>``) and, but for a reset
    amplifier, the noise without charge (``noise``); at each other supply the smallest charge's
    response (``supply_<percent>``) and the noise (``supply_<percent>_noise``). The Krummenacher
    reference is at its share of each supply."""

    supply = importlib.import_module(f"pdk.{pdk}.hdl21.site").install.supply_voltage(h.pdk.Corner.TYP)
    nominal = TbParams(pdk=pdk, params=params, vdd=round(supply, 4), vref_v=round(VREF * supply, 4))
    noise = params.feedback is not Feedback.RESET
    benches = {f"q{round(charge * 1e18)}": dataclasses.replace(nominal, charge_c=charge) for charge in CHARGES_C}
    if noise:
        benches["noise"] = dataclasses.replace(nominal, stimulus=Stimulus.NOISE, charge_c=0.0)
    for factor in SUPPLY_SWEEP:
        if factor == 1.0:
            continue
        point = dataclasses.replace(
            nominal, vdd=round(factor * supply, 4), vref_v=round(VREF * factor * supply, 4), charge_c=min(CHARGES_C)
        )
        benches[f"supply_{round(factor * 100)}"] = point
        if noise:
            benches[f"supply_{round(factor * 100)}_noise"] = dataclasses.replace(
                point, stimulus=Stimulus.NOISE, charge_c=0.0
            )
    return benches


def results(measurements: dict[str, Meas]) -> Results:
    """The record of one instance from its runs' measurements (``testbenches``): the metrics
    (``analysis.metrics``) and the plots of its responses over the charge, its noise and its sweep
    over the supply."""

    noisy = measurements[f"q{round(min(CHARGES_C) * 1e18)}"].dut.feedback is not Feedback.RESET
    pulse = analyze_pulse([measurements[f"q{round(charge * 1e18)}"] for charge in CHARGES_C])
    noise = analyze_noise([measurements["noise"]], pulse=pulse) if noisy else None
    # over the supply: the smallest charge's response and the noise, the 100 % point the nominal one
    pulses = [
        pulse if factor == 1.0 else analyze_pulse([measurements[f"supply_{round(factor * 100)}"]])
        for factor in SUPPLY_SWEEP
    ]
    noises = (
        [
            noise
            if factor == 1.0
            else analyze_noise([measurements[f"supply_{round(factor * 100)}_noise"]], pulse=point)
            for factor, point in zip(SUPPLY_SWEEP, pulses, strict=True)
        ]
        if noise is not None
        else None
    )
    supply = analyze_supply(pulses, noises=noises)
    return Results(
        metrics=dataclasses.asdict(metrics(pulse=pulse, noise=noise, supply=supply)),
        details=[
            plot_pulse(pulse),
            plot_amplitude_charge(pulse),
            plot_gain_charge(pulse),
            plot_tot_charge(pulse),
            *([plot_noise_density(noise)] if noise is not None else []),
            plot_gain_supply(supply),
            plot_peaking_supply(supply),
            plot_enc_supply(supply),
            plot_power_supply(supply),
        ],
        # the runs the viewer shows the waveforms of, by label
        waves={"0.25 fC": "q250", "2 fC": "q2000"},
    )
