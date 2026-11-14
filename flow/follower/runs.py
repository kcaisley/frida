"""The followers' design space (docs/pipeline.md): its named instances (``@single``) and its grid
(``@grid``: each named follower at its other sizings); the testbench runs that characterize one
instance (``testbenches``) and the record they make (``results``).

The four followers (the NMOS and PMOS source followers, the NMOS flipped voltage follower and the
PMOS one with an output sink) at eight sizings (a source follower has no shunt device to size:
seven), in every PDK. Each instance is run on the bench every follower is characterized on
(``params``), its reference current in proportion to its current source's width: over the input
level (the supply in twelfths) the output level, small-signal gain, bandwidth, PSRR and output
impedance; at its nominal input (where a follower of its topology and input type follows: an
NMOS source follower 3/4 up the supply, a PMOS one 1/4, the flipped ones 1/2 and 1/4) those, the
supply current, the response and the output impedance over frequency and the input range over
which the gain stays within 10 % of its value there; there too, from a step of a quarter of the
supply up and back down, the slew rates, settling and overshoot; over the supply (90 and 110 % of
its own besides nominal, the input at its share of it) the gain, bandwidth and PSRR. Twenty-nine
Spectre runs.
"""

from __future__ import annotations

import dataclasses
import importlib

import hdl21 as h
from hdl21.primitives import MosType

from flow.pipeline import Meas, Results, grid, single, widen

from .analysis import analyze_impedance, analyze_slew, analyze_transfer, metrics
from .params import IREF_A, IREF_W, NOMINAL_VIN, SUPPLY_SWEEP, VIN_STEP, VIN_SWEEP, Params, Stimulus, TbParams, Topology
from .plots import (
    plot_bandwidth_supply,
    plot_bandwidth_vin,
    plot_gain_frequency,
    plot_gain_supply,
    plot_gain_vin,
    plot_psrr_supply,
    plot_psrr_vin,
    plot_vout_vin,
    plot_zout_frequency,
    plot_zout_vin,
)


@single
def source() -> Params:
    """The NMOS source follower with an NMOS current source, output-buffer sized."""
    return Params(in_w=32, bias_w=16)


@single
def source_pmos() -> Params:
    """The PMOS source follower with a PMOS current source, output-buffer sized."""
    return Params(input_xtors=MosType.PMOS, in_w=32, bias_w=16)


@single
def flipped() -> Params:
    """The NMOS flipped voltage follower."""
    return Params(topology=Topology.FLIPPED)


@single
def flipped_pmos() -> Params:
    """The PMOS flipped voltage follower with an output sink."""
    return Params(topology=Topology.FLIPPED, input_xtors=MosType.PMOS, sink=True)


@grid
def scaled() -> dict[str, Params]:
    """Each named follower at its other sizings, by name: its widths scaled together (the input
    device's, the current source's and, in a flipped follower, the shunt device's: half, as
    named, twice and four times), then one size alone doubled: the input device's width, the
    shunt device's (a flipped follower's), the input device's length, the current source's."""
    spaces = {}
    for name, base in (
        ("source", source()),
        ("source_pmos", source_pmos()),
        ("flipped", flipped()),
        ("flipped_pmos", flipped_pmos()),
    ):
        shunt = ("fb_w",) if base.topology is Topology.FLIPPED else ()
        for factor in (0.5, 1, 2, 4):
            space = widen(base)
            for width in ("in_w", "bias_w", *shunt):
                setattr(space, width, max(1, round(getattr(base, width) * factor)))
            spaces[f"{name}_x{factor:g}"] = space
        for size in ("in_w", *shunt, "in_l", "bias_l"):
            space = widen(base)
            setattr(space, size, 2 * getattr(base, size))
            spaces[f"{name}_{size}_x2"] = space
    return spaces


def testbenches(pdk: str, params: Params) -> dict[str, TbParams]:
    """The testbench runs that characterize ``params`` in ``pdk``, by name (each run's folder): at
    each input level the AC stimulus on the input (``input_vin_<twelfths>``) and on the output
    test current (``output_vin_<twelfths>``); at the nominal input, the input at its share of
    each other supply (``supply_<percent>``; the nominal one is its ``input_vin_<twelfths>``),
    and the step (``step``)."""

    supply = importlib.import_module(f"pdk.{pdk}.hdl21.site").install.supply_voltage(h.pdk.Corner.TYP)
    nominal_vin = NOMINAL_VIN[params.topology, params.input_xtors]
    nominal = TbParams(
        pdk=pdk,
        params=params,
        vdd=round(supply, 4),
        vin_v=round(nominal_vin * supply, 4),
        iref_a=IREF_A * params.bias_w / IREF_W[params.topology],
    )
    benches = {}
    for stimulus in (Stimulus.INPUT, Stimulus.OUTPUT):
        for fraction in VIN_SWEEP:
            benches[f"{stimulus.name.lower()}_vin_{round(fraction * 12)}"] = dataclasses.replace(
                nominal, stimulus=stimulus, vin_v=round(fraction * supply, 4)
            )
    for factor in SUPPLY_SWEEP:
        if factor != 1.0:
            benches[f"supply_{round(factor * 100)}"] = dataclasses.replace(
                nominal, vdd=round(factor * supply, 4), vin_v=round(nominal_vin * factor * supply, 4)
            )
    benches["step"] = dataclasses.replace(nominal, stimulus=Stimulus.STEP, step_v=round(VIN_STEP * supply, 4))
    return benches


def results(measurements: dict[str, Meas]) -> Results:
    """The record of one instance from its runs' measurements (``testbenches``): the metrics
    (``analysis.metrics``) and the plots of its sweeps over the input level and the supply and of
    its responses over frequency at the nominal input."""

    dut = measurements["step"].dut
    nominal = round(NOMINAL_VIN[dut.topology, dut.input_xtors] * 12)
    transfer = analyze_transfer([measurements[f"input_vin_{round(fraction * 12)}"] for fraction in VIN_SWEEP])
    impedance = analyze_impedance([measurements[f"output_vin_{round(fraction * 12)}"] for fraction in VIN_SWEEP])
    supply = analyze_transfer(
        [
            measurements[f"input_vin_{nominal}" if factor == 1.0 else f"supply_{round(factor * 100)}"]
            for factor in SUPPLY_SWEEP
        ]
    )
    values = metrics(transfer=transfer, impedance=impedance, slew=analyze_slew([measurements["step"]]), supply=supply)
    return Results(
        metrics=dataclasses.asdict(values),
        details=[
            plot_vout_vin(transfer),
            plot_gain_vin(transfer),
            plot_bandwidth_vin(transfer),
            plot_zout_vin(impedance),
            plot_psrr_vin(transfer),
            plot_gain_frequency(analyze_transfer([measurements[f"input_vin_{nominal}"]])),
            plot_zout_frequency(analyze_impedance([measurements[f"output_vin_{nominal}"]])),
            plot_gain_supply(supply),
            plot_bandwidth_supply(supply),
            plot_psrr_supply(supply),
        ],
        # the run the viewer shows the waveforms of, by label
        waves={"step at the nominal input": "step"},
    )
