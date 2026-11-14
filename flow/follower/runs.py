"""The followers' design space (docs/pipeline.md): its named instances (``@single``) and its grid
(``@grid``: each named follower at its other sizings); the testbench runs that characterize one
instance (``testbenches``) and the record they make (``results``).

The four followers (the NMOS and PMOS source followers, the NMOS flipped voltage follower and the
PMOS one with an output sink) at eight sizings (a source follower has no shunt device to size:
seven), in every PDK. Each instance is run on the bench every follower is characterized on
(``params``), its reference current in proportion to its current source's width: over the input
level (the supply in twelfths) the output level, small-signal gain, bandwidth, PSRR and output
impedance, and from a DC sweep of the input its characteristic and gain dVout/dVin, whose input
range (the gain within 10 % of its largest) sets the nominal input, the level of 2/12 to 10/12
of the supply nearest the range's middle; there the supply current, the response and the output
impedance over frequency; from a step up and back down (a quarter of the supply for a source
follower, an eighth for a flipped one) the slew rates, transition times, settling and overshoot,
and how far the step's levels lie inside the input range, the step repeated at half its size to
tell an edge that slews from one that settles linearly; over the supply (90 and 110 % of its own
besides nominal, the input held relative to the rail its input device's source rides) the gain,
bandwidth and PSRR. The step and the supply corners are run at each level the nominal input may
take (nine), the record keeping the nominal's: 49 Spectre runs.
"""

from __future__ import annotations

import dataclasses
import importlib
import math

import hdl21 as h
from hdl21.primitives import MosType

from flow.pipeline import Meas, Results, grid, single, widen

from .analysis import analyze_characteristic, analyze_impedance, analyze_slew, analyze_transfer, metrics
from .params import (
    IREF_A,
    IREF_W,
    NOMINAL_VIN,
    SUPPLY_SWEEP,
    VIN_DC_STEP,
    VIN_STEP,
    VIN_SWEEP,
    Params,
    Stimulus,
    TbParams,
    Topology,
)
from .plots import (
    plot_bandwidth_supply,
    plot_bandwidth_vin,
    plot_gain_frequency,
    plot_gain_supply,
    plot_gain_vin,
    plot_psrr_supply,
    plot_psrr_vin,
    plot_rout_vin,
    plot_vout_vin,
    plot_zout_frequency,
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
    each input level the AC stimulus on the input (``input_vin_<twelfths>``, the middle level's
    with the input's DC sweep beside it); at each level the nominal input may take
    (``NOMINAL_VIN``), the other supplies, the input held relative to the rail its input device's
    source rides (``supply_<percent>_vin_<twelfths>``; the nominal supply's is
    ``input_vin_<twelfths>``), the step (``step_vin_<twelfths>``) and the step at half its size
    (``step_half_vin_<twelfths>``)."""

    supply = importlib.import_module(f"pdk.{pdk}.hdl21.site").install.supply_voltage(h.pdk.Corner.TYP)
    base = TbParams(
        pdk=pdk,
        params=params,
        vdd=round(supply, 4),
        vin_v=0.0,
        iref_a=IREF_A * params.bias_w / IREF_W[params.topology],
    )
    benches = {}
    for fraction in VIN_SWEEP:
        benches[f"input_vin_{round(fraction * 12)}"] = dataclasses.replace(base, vin_v=round(fraction * supply, 4))
    # the middle level's run sweeps the input in DC too, from ground to the supply: the
    # characteristic, the input range and the nominal input (analysis.analyze_characteristic)
    benches["input_vin_6"] = dataclasses.replace(benches["input_vin_6"], dc_step_v=round(VIN_DC_STEP * supply, 6))
    step_v = round(VIN_STEP[params.topology] * supply, 4)
    for fraction in NOMINAL_VIN:
        at = round(fraction * 12)
        vin_v = benches[f"input_vin_{at}"].vin_v
        for factor in SUPPLY_SWEEP:
            if factor != 1.0:
                # the input where it is at the nominal supply relative to the rail its input
                # device's source rides: the same level for an NMOS input (from ground), the same
                # distance below the supply for a PMOS one
                corner = round(factor * supply, 4)
                held = vin_v if params.input_xtors == MosType.NMOS else corner - (base.vdd - vin_v)
                benches[f"supply_{round(factor * 100)}_vin_{at}"] = dataclasses.replace(
                    base, vdd=corner, vin_v=round(held, 4)
                )
        step = dataclasses.replace(base, stimulus=Stimulus.STEP, vin_v=vin_v, step_v=step_v)
        benches[f"step_vin_{at}"] = step
        # the same step at half its size: an edge whose slope holds slews, one whose slope halves
        # does not (analysis.analyze_slew)
        benches[f"step_half_vin_{at}"] = dataclasses.replace(step, step_v=step_v / 2)
    return benches


def results(measurements: dict[str, Meas]) -> Results:
    """The record of one instance from its runs' measurements (``testbenches``): the metrics
    (``analysis.metrics``) at the nominal input, the level of ``NOMINAL_VIN`` nearest the middle
    of the input range (``analyze_characteristic``; the middle level where there is none, whose
    metrics are then NaN), and the plots of its sweeps over the input level and the supply and of
    its responses over frequency at the nominal input."""

    characteristic = analyze_characteristic(measurements["input_vin_6"])
    vdd = float(measurements["input_vin_6"].tb.vdd)
    nominal = round(characteristic.vin_nominal_v / vdd * 12) if math.isfinite(characteristic.vin_nominal_v) else 6
    levels = [measurements[f"input_vin_{round(fraction * 12)}"] for fraction in VIN_SWEEP]
    transfer = analyze_transfer(levels)
    impedance = analyze_impedance(levels)
    supply = analyze_transfer(
        [
            measurements[f"input_vin_{nominal}" if factor == 1.0 else f"supply_{round(factor * 100)}_vin_{nominal}"]
            for factor in SUPPLY_SWEEP
        ]
    )
    slew = analyze_slew([measurements[f"step_vin_{nominal}"], measurements[f"step_half_vin_{nominal}"]])
    values = metrics(transfer=transfer, impedance=impedance, characteristic=characteristic, slew=slew, supply=supply)
    return Results(
        metrics=dataclasses.asdict(values),
        details=[
            plot_vout_vin(characteristic),
            plot_gain_vin(characteristic),
            plot_bandwidth_vin(transfer, characteristic),
            plot_rout_vin(impedance, characteristic),
            plot_psrr_vin(transfer, characteristic),
            plot_gain_frequency(analyze_transfer([measurements[f"input_vin_{nominal}"]])),
            plot_zout_frequency(analyze_impedance([measurements[f"input_vin_{nominal}"]])),
            plot_gain_supply(supply),
            plot_bandwidth_supply(supply),
            plot_psrr_supply(supply),
        ],
        # the run the viewer shows the waveforms of, by label
        waves={"step at the nominal input": f"step_vin_{nominal}"},
    )
