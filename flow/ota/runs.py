"""The amplifier's design space (docs/pipeline.md): its named designs (``@single``) and each of
them at seven sizings (``@grid``); the testbench runs that characterize one instance
(``testbenches``) and the record they make (``results``).

Each instance is run on the bench every amplifier is characterized on (``params``: a 40 uA tail,
the cascodes an eighth of the supply off its middle, 50 fF on each output) at its PDK's own
supply: over the input common mode (1/6 to 5/6 of the supply, nine points) the low-frequency gain,
unity-gain bandwidth and noise, and at mid-supply input those with the phase and gain margin, -3 dB
bandwidth, PSRR and CMRR at ``outp``, power, and the gain, phase, noise density and rejections over
frequency; over the supply (90 and 110 % of its own besides nominal, the common modes at
mid-supply) the low-frequency gain, unity-gain bandwidth and power. The single-ended amplifiers
also in unity gain: a quarter-supply step (slew rates, 1 % settling) and a tenth-supply sine at
10 MHz (THD). Eleven Spectre runs, thirteen for a single-ended amplifier.
"""

from __future__ import annotations

import dataclasses
import importlib
from dataclasses import replace

import hdl21 as h
from hdl21.primitives import MosType

from flow.pipeline import Meas, Results, grid, single, widen

from .analysis import analyze_ac, analyze_distortion, analyze_noise, analyze_slew, metrics
from .params import (
    CM_SWEEP,
    NOMINAL_CM,
    SINE,
    SINE_STROBE_S,
    STEP,
    SUPPLY_SWEEP,
    VCASN,
    VCASP,
    VOUT_CM,
    Bench,
    Params,
    TbParams,
    Topology,
)
from .plots import (
    plot_cmrr,
    plot_gain,
    plot_gain_cm,
    plot_gain_supply,
    plot_noise_density,
    plot_noise_in_1mhz_cm,
    plot_noise_in_cm,
    plot_phase,
    plot_power_supply,
    plot_psrr,
    plot_spectrum,
    plot_step_response,
    plot_unity_gain_bandwidth_cm,
    plot_unity_gain_bandwidth_supply,
)


@single
def five_t() -> Params:
    """The five-transistor amplifier with an NMOS input."""
    return Params()


@single
def five_t_pmos() -> Params:
    """The five-transistor amplifier with a PMOS input."""
    return Params(input_xtors=MosType.PMOS)


@single
def telescopic() -> Params:
    """The telescopic cascode with an NMOS input."""
    return Params(topology=Topology.TELESCOPIC)


@single
def folded() -> Params:
    """The folded cascode with an NMOS input."""
    return Params(topology=Topology.FOLDED)


@single
def self_biased() -> Params:
    """The self-biased complementary amplifier."""
    return Params(topology=Topology.SELF_BIASED)


@single
def two_stage() -> Params:
    """A telescopic first stage with common-source second stages, without a Miller capacitor."""
    return Params(topology=Topology.TELESCOPIC, two_stage=True)


@grid
def sizes() -> dict[str, Params]:
    """Each named design at seven sizings, each by name: every width at 8, 16, 32 and 64 units
    (half to four times the defaults'), the input pair twice as wide (``in_w32``) or twice as long
    (``in_l4``), and the current sources, tail and load, at twice their length (``source_l8``)."""
    designs = {
        "five_t": five_t,
        "five_t_pmos": five_t_pmos,
        "telescopic": telescopic,
        "folded": folded,
        "self_biased": self_biased,
        "two_stage": two_stage,
    }
    widths = ("in_w", "tail_w", "load_w", "cas_w", "stage2_w")
    sizings = {
        **{f"w{width}": dict.fromkeys(widths, width) for width in (8, 16, 32, 64)},
        "in_w32": {"in_w": 32},
        "in_l4": {"in_l": 4},
        "source_l8": {"tail_l": 8, "load_l": 8},
    }
    return {
        f"{design}_{sizing}": widen(Params(**{**build().__dict__, **changed}))
        for design, build in designs.items()
        for sizing, changed in sizings.items()
    }


def testbenches(pdk: str, params: Params) -> dict[str, TbParams]:
    """The testbench runs that characterize ``params`` in ``pdk``, by name (each run's folder): the
    small-signal bench at each input common mode (``cm_<24ths of the supply>``) and, the common
    modes at mid-supply, at each other supply (``supply_<percent>``; the nominal one is ``cm_12``);
    and, for a single-ended amplifier, the unity-gain step (``step``) and sine (``sine``) at
    mid-supply input."""

    supply = importlib.import_module(f"pdk.{pdk}.hdl21.site").install.supply_voltage(h.pdk.Corner.TYP)
    nominal = TbParams(
        pdk=pdk,
        params=params,
        vdd=round(supply, 4),
        vin_cm_v=round(NOMINAL_CM * supply, 4),
        vout_cm_v=round(VOUT_CM * supply, 4),
        vcasn_v=round(VCASN * supply, 4),
        vcasp_v=round(VCASP * supply, 4),
    )
    benches = {
        f"cm_{round(fraction * 24)}": replace(nominal, vin_cm_v=round(fraction * supply, 4)) for fraction in CM_SWEEP
    }
    for factor in SUPPLY_SWEEP:
        if factor != 1.0:
            vdd = factor * supply
            benches[f"supply_{round(factor * 100)}"] = replace(
                nominal,
                vdd=round(vdd, 4),
                vin_cm_v=round(NOMINAL_CM * vdd, 4),
                vout_cm_v=round(VOUT_CM * vdd, 4),
                vcasn_v=round(VCASN * vdd, 4),
                vcasp_v=round(VCASP * vdd, 4),
            )
    # unity gain, single-ended only: a differential output would need a common-mode feedback circuit
    if nominal.single_ended:
        benches["step"] = replace(nominal, bench=Bench.STEP, vin_step_v=round(STEP * supply, 4))
        benches["sine"] = replace(
            nominal,
            bench=Bench.SINE,
            vin_amplitude_v=round(SINE * supply, 4),
            waveform_sample_interval_s=SINE_STROBE_S,
        )
    return benches


def results(measurements: dict[str, Meas]) -> Results:
    """The record of one instance from its runs' measurements (``testbenches``): the metrics
    (``analysis.metrics``), the plots of its response at mid-supply input and of its sweeps over
    the input common mode and the supply, and, of a single-ended amplifier, its unity-gain step
    response and output spectrum."""

    middle = f"cm_{round(NOMINAL_CM * 24)}"
    by_cm = [measurements[f"cm_{round(fraction * 24)}"] for fraction in CM_SWEEP]
    by_supply = [measurements[middle if factor == 1.0 else f"supply_{round(factor * 100)}"] for factor in SUPPLY_SWEEP]
    ac, supply = analyze_ac(by_cm), analyze_ac(by_supply)
    noise = analyze_noise(by_cm, ac=ac)
    nominal = analyze_ac([measurements[middle]])
    nominal_noise = analyze_noise([measurements[middle]], ac=nominal)
    slew = analyze_slew([measurements["step"]]) if "step" in measurements else None
    distortion = analyze_distortion([measurements["sine"]]) if "sine" in measurements else None
    return Results(
        metrics=dataclasses.asdict(metrics(ac=ac, noise=noise, supply=supply, slew=slew, distortion=distortion)),
        details=[
            plot_gain(nominal),
            plot_phase(nominal),
            plot_noise_density(nominal_noise),
            plot_psrr(nominal),
            plot_cmrr(nominal),
            plot_gain_cm(ac),
            plot_unity_gain_bandwidth_cm(ac),
            plot_noise_in_1mhz_cm(noise),
            plot_noise_in_cm(noise),
            plot_gain_supply(supply),
            plot_unity_gain_bandwidth_supply(supply),
            plot_power_supply(supply),
            *([plot_step_response(slew)] if slew is not None else []),
            *([plot_spectrum(distortion)] if distortion is not None else []),
        ],
        # the runs the viewer shows the waveforms of, by label: a single-ended amplifier's transients
        waves={
            label: run
            for label, run in (("unity-gain step", "step"), ("unity-gain sine", "sine"))
            if run in measurements
        },
    )
