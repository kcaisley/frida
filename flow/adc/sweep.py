"""The ADC's design space (``flow.sweep``), by the behavioral converter (``flow.adc.sim``) of its
characterized blocks: the plain product of its components, each converter given by its parameters;
in TSMC65 alone, the one PDK its DAC is characterized in (``flow.capdac.sweep``).

Every converter samples on its top plates, makes one free comparison before any capacitor switches
and fires the comparator again after the last one switches: an N-bit converter has an N-1-step DAC
(``adc_bits`` is its array's ``bits``) and N + extra decisions. Its arrays are capdac's, every one
of its design space (``capdac.arrays`` and ``capdac.frida1``): each at one and two kT/C minimums of
switched capacitance (``capdac.Params.scale``, at a full scale of the reference: the full scale its
plates give is the record's ``full_scale_over_reference``), its weights built both ways
(``capdac.WeightImpl``: difference capacitors in long strips, or unit capacitors), its drivers
sized to settle each stage to half an LSB within 1 ns (``capdac.Params.settle_ps``). The
difference capacitors are labelled by the names the legacy extractions gave them, the unit
capacitors by the same with ``_unit`` (``_array_name``). Each converter's DAC is capdac's
characterization of the same array, found by its digest.

The product, nothing pruned:

- the comparators of the comparator grid (``_comparators``: five noise levels by four
  delays, FRIDA-1's StrongARM among them at its fabricated sizes);
- the samplers (``_samplers``), an on-resistance ladder: FRIDA-1's transmission gate (32
  minimum widths, minimum length) the worst, then the bootstrapped NMOS switch at 32, 64, 112 and
  160 minimum widths (``samp.boost_ladder``, each boosted alike), about a half, a
  quarter, a seventh and a tenth of the gate's resistance; none with half-size dummy switches, as
  FRIDA-1's;
- the arrays, 10 at each resolution, scale and weight build: binary, and each scheme
  (``capdac.Redundancy``: the MSBs split, the LSBs split, FRIDA's MSB redistribution)
  with 2, 4 and 6 extra cycles, every one of the binary total weight;
- the resolutions, 10, 12 and 14 bits;
- the switched capacitance, one and two times the resolution's least (``capdac.Params.scale``);
- the weight builds, difference and unit capacitors (``capdac.WeightImpl``);
- and FRIDA-1's array (``capdac.frida1``: 12 bits on MSB redistribution with 5 extra cycles, 17
  decisions, its difference capacitors) at two times the 12-bit least, near its drawn size.

20 x 5 x (10 x 3 x 2 x 2 + 1) = 12,100 converters in TSMC65. The other PDKs have none until capdac
is characterized there; their spaces stay: the arrays and the blocks the same study's but the
comparator grid the PDK's own (``flow.comp.sweep``), each array with the PDK's StrongARM noise
ladder at about FRIDA-1's speed (``_comparators``) and the widest bootstrapped switch
(``_samplers``), 484 to 605 converters a PDK. The design space is a grid (``converters``,
docs/pipeline.md): one space per resolution, its arrays, comparators and samplers values by name.

FRIDA-1 is in it twice: as a generated design (``frida1``, its sizing, which the grid also reaches)
and as its four fabricated converters (``frida1_<layers>layer_radix<radix>``, ``Fabricated``),
whose behavioral characterization is FRIDA-1's sizing alike and whose circuit runs simulate their
extractions.

Each instance's runs (``runs``) at a level (``flow.pipeline.Level``) are the behavioral campaign's,
the cheapest first, and at ``Level.CIRCUIT`` the circuit simulator's as well (``spice_*``, Spectre:
a candidate's netlist, a fabricated converter's extraction); its record (``record``) holds the
metrics and figures of whatever runs it has (the analyses of ``flow.adc.analysis``, the figures of
``flow.adc.plots``), each metric None where its runs did not run, the circuit runs' under the same
names for a candidate and a fabricated converter, so the two line up in one table.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from pathlib import Path
from typing import Any

import hdl21 as h
import hdl21.sim as hs
import numpy as np

from flow import capdac, comp, samp
from flow.analysis.io import read_cap_table
from flow.analysis.types import MeasAdc
from flow.pipeline import Level, Meas, Pdk, Plot, Record, grid, named, values, widen

from .analysis import (
    _extracted_calibration,
    analyze_calibration2,
    analyze_calibration3,
    analyze_code_spectrum,
    analyze_converter,
    analyze_decision_paths,
    analyze_dynamic,
    analyze_energy,
    analyze_hsu,
    analyze_input_noise,
    analyze_ladder,
    analyze_mismatch,
    analyze_mismatch_draws,
    analyze_mismatch_prediction,
    analyze_noise,
    analyze_noise_rms,
    analyze_operating_conditions,
    analyze_power,
    analyze_ramp,
    analyze_redundancy,
    analyze_reference,
    analyze_sequence_map,
    analyze_sequencer,
    analyze_transfer,
    metrics,
)
from .params import (
    FIN_CYCLES,
    FIN_RATES_HZ,
    FRIDA1_ARRAY,
    HSU_QUIET,
    HSU_REFERENCE_QUIET,
    INPUT_NOISE_CONVERSIONS,
    INPUT_NOISE_LEVELS,
    INPUT_NOISE_SPAN,
    LADDER,
    LADDER_NAMES,
    MISMATCH_COEFFICIENTS,
    MISMATCH_CONVERSIONS,
    MISMATCH_DRAWS,
    NOMINAL_RATE_HZ,
    RAMP_CONVERSIONS,
    RATES_HZ,
    REFERENCE_NOISE_V,
    REFERENCE_QUIET,
    REFERENCE_R_OUT_OHM,
    RESOLUTIONS,
    SINE_CONVERSIONS,
    Extraction,
    Fabricated,
    Params,
    Probes,
    Quiet,
    Recipe,
    Simulator,
    TbParams,
)
from .plots import (
    plot_calibration_weights,
    plot_code_density,
    plot_codes_rate,
    plot_dnl,
    plot_dnl_calibrated,
    plot_energy_dac_input,
    plot_energy_input,
    plot_enob_fin,
    plot_enob_ladder,
    plot_enob_rate,
    plot_hsu_rate,
    plot_inl,
    plot_inl_calibrated,
    plot_mismatch_dnl,
    plot_mismatch_inl,
    plot_mismatch_margin,
    plot_mismatch_transition_sigma,
    plot_mismatch_weight_sigma,
    plot_noise_enob_rate,
    plot_noise_input,
    plot_noise_rate,
    plot_noise_spectrum,
    plot_power_rate,
    plot_redundancy,
    plot_reference_noise,
    plot_reference_r_out,
    plot_sequence_enob,
    plot_sequence_plausible,
    plot_sequence_shift,
    plot_sequencer,
    plot_spectrum_low,
    plot_spectrum_nyquist,
    plot_trajectory,
    plot_trajectory_codes,
    plot_trajectory_final,
    plot_transfer,
)
from .sim import _Converter, _converter
from .types import AnalysisCalibration, AnalysisLadder


def _array_name(cdac: capdac.Params) -> str:
    """An array's name, by its converter's resolution, scheme and scale, as the legacy extractions
    name the difference capacitors': ``12b_binary_x1``, ``12b_msb_redist5_x2`` (FRIDA-1's),
    ``14b_lsb_split6_x2``; unit capacitors' the same with ``_unit``, ``12b_binary_x1_unit``."""
    unit = "_unit" if cdac.weight_impl is capdac.WeightImpl.UNIT_CAPS else ""
    return f"{cdac.bits}b_{cdac.redundancy.name.lower()}{cdac.extra or ''}_x{cdac.scale}{unit}"


def _arrays(pdk: Pdk, bits: int) -> dict[str, capdac.Params]:
    """A ``bits`` converter's arrays by name (``_array_name``): capdac's grid (``capdac.arrays``) at
    ``bits``, its difference capacitors and then its unit capacitors, each at one then two kT/C
    minimums, each the binary array and then each scheme with 2, 4 and 6 extra cycles; at FRIDA-1's
    resolution its array last (``FRIDA1_ARRAY``, ``capdac.frida1``)."""
    schemes, builds = list(capdac.Redundancy), list(capdac.WeightImpl)
    swept = sorted(
        (cdac for _label, cdac in capdac.arrays.instances(pdk) if cdac.bits == bits),
        key=lambda cdac: (builds.index(cdac.weight_impl), cdac.scale, schemes.index(cdac.redundancy), cdac.extra),
    )
    frida1 = [FRIDA1_ARRAY] if FRIDA1_ARRAY.bits == bits else []
    return {_array_name(cdac): cdac for cdac in swept + frida1}


def _comparators(pdk: str) -> dict[str, comp.Params]:
    """The comparators of ``pdk``'s converters by name: TSMC65's grid, by noise and delay
    (``200uV_2ns``); elsewhere the PDK's StrongARM noise ladder at its longest tail (its comparator
    grid's, ``comp.base_strongarm``: 200 to 50 uV where its noise floor reaches them, about 2 ns at
    0.5 mV, FRIDA-1's speed), by its width factor (``k2.5``).

    TSMC65's grid: five levels of input-referred noise (rows, at the nominal common mode) by four of
    delay (columns, at 0.5 mV), each cell the characterized comparator of least energy per decision
    within 15 % of the noise and 20 % of the delay (flow/comp/readme.md), FRIDA-1's at 200 uV and
    2 ns; each from the comparator's grids by name (``comp.base_strongarm``, ``comp.dynamic_bias``)."""
    if pdk == "tsmc65":
        noise_v = (200e-6, 150e-6, 100e-6, 70e-6, 50e-6)
        delay_s = (0.5e-9, 1.0e-9, 1.5e-9, 2.0e-9)
        strongarm = {name: space.base for name, space in comp.base_strongarm.spaces(Pdk.TSMC65).items()}
        dynamic = {name: space.base for name, space in comp.dynamic_bias.spaces(Pdk.TSMC65).items()}
        cells = (
            # 0.5 ns                      1 ns                          1.5 ns                         2 ns
            strongarm["tail_l=14, k=3"],  dynamic["ratio=3.5, k=0.75"], dynamic["ratio=2.75, k=0.75"], comp.FRIDA1,  # 200 uV
            strongarm["tail_l=14, k=6"],  dynamic["ratio=3.5, k=1.5"],  dynamic["ratio=2.75, k=1.5"],  dynamic["ratio=2.25, k=1.5"],  # 150 uV
            strongarm["tail_l=14, k=12"], dynamic["ratio=3.5, k=3"],    dynamic["ratio=2.75, k=3"],    dynamic["ratio=2.25, k=3"],  # 100 uV
            strongarm["tail_l=14, k=32"], dynamic["ratio=3.5, k=6"],    dynamic["ratio=2.75, k=6"],    dynamic["ratio=2.25, k=6"],  # 70 uV
            strongarm["tail_l=14, k=64"], dynamic["ratio=3.5, k=12"],   dynamic["ratio=2.75, k=12"],   dynamic["ratio=2.25, k=12"],  # 50 uV
        )  # fmt: skip
        # each cell's noise and delay, in the cells' order (the noise outer)
        targets = [(noise, delay) for noise in noise_v for delay in delay_s]
        return {
            f"{noise * 1e6:g}uV_{delay * 1e9:g}ns": params
            for (noise, delay), params in zip(targets, cells, strict=True)
        }
    ladder = {name: space.base for name, space in comp.base_strongarm.spaces(pdk).items()}
    longest = max(params.tail_l for params in ladder.values())
    return {f"k{name.rsplit('k=', 1)[1]}": params for name, params in ladder.items() if params.tail_l == longest}


def _samplers(pdk: str) -> dict[str, samp.Params]:
    """The samplers of ``pdk``'s converters by name: TSMC65's, an on-resistance ladder: FRIDA-1's
    transmission gate (32 minimum widths, minimum length; ``frida1``) the worst, then the
    bootstrapped NMOS switch's rungs (``samp.boost_ladder``, by name: 32 minimum widths with the
    doubled boost capacitor, then 64, 112 and 160, boosted alike), none with dummy switches;
    elsewhere the bootstrapped switch's widest rung alone, so the array and the comparator set the
    converter."""
    ladder = {f"boost_{name}": space.base for name, space in samp.boost_ladder.spaces(pdk).items()}
    if pdk == "tsmc65":
        return {"frida1": samp.FRIDA1, **ladder}
    return dict([list(ladder.items())[-1]])


# in TSMC65 alone until capdac is characterized elsewhere: a converter's DAC is its record
@grid(pdks=(Pdk.TSMC65,))
def converters(pdk: Pdk) -> dict[str, Params]:
    """Every comparator with every sampler and ADC array (``_arrays``: each resolution's arrays,
    both weight builds at both scales, and FRIDA-1's), one space per resolution, each array at its
    resolution (``adc_bits`` its ``bits``): in TSMC65 the full product; the other PDKs' spaces the
    smaller one (``_comparators``, ``_samplers``), which the grid leaves out. A converter is
    labelled by its resolution and its parts' names,
    ``converters(12b, cdac=12b_binary_x1, comp=200uV_2ns, samp=frida1)``."""
    folder = pdk.name.lower()
    spaces = {}
    for bits in RESOLUTIONS:
        arrays = _arrays(pdk, bits)
        space = widen(Params(adc_bits=bits, cdac=next(iter(arrays.values())), comp=comp.FRIDA1, samp=samp.FRIDA1))
        space.cdac = values(arrays)
        space.comp = values(_comparators(folder))
        space.samp = values(_samplers(folder))
        spaces[f"{bits}b"] = space
    return spaces


# FRIDA-1: its sizing as a generated design (the grid's point of its parts), and its four fabricated
# converters (``Fabricated``), each simulated on its extraction and laid out from its tape-out


@named
def frida1() -> Params:
    """FRIDA-1's converter as a generated design: its sizing, capdac's, the sampler's and the
    comparator's FRIDA-1 parts."""
    return Params()


@named
def frida1_1layer_radix17() -> Params:
    """FRIDA-1's fabricated converter, its DAC in one metal layer at radix 17."""
    return Fabricated.FRIDA1_1LAYER_RADIX17.params


@named
def frida1_1layer_radix20() -> Params:
    """FRIDA-1's fabricated converter, its DAC in one metal layer at radix 20."""
    return Fabricated.FRIDA1_1LAYER_RADIX20.params


@named
def frida1_2layer_radix17() -> Params:
    """FRIDA-1's fabricated converter, its DAC in two metal layers at radix 17."""
    return Fabricated.FRIDA1_2LAYER_RADIX17.params


@named
def frida1_2layer_radix20() -> Params:
    """FRIDA-1's fabricated converter, its DAC in two metal layers at radix 20."""
    return Fabricated.FRIDA1_2LAYER_RADIX20.params


def runs(pdk: str, params: Params, level: Level = Level.FULL) -> dict[str, TbParams]:
    """The runs that characterize ``params`` in ``pdk`` at ``level``, by name, each behavioral (its
    converter, ``flow.adc.sim``'s, of the blocks' characterizations), and at ``Level.CIRCUIT`` the
    circuit simulator's as well (``_spice``). Each level holds the one below it:

    - ``Level.SCREEN``: ``ramp_train`` and ``ramp_check``, ``rate_10`` and ``noise``: the linearity,
      the calibrations, the ENOB and power at the nominal rate and the output-code noise;
    - ``Level.SEARCH``: every rate, the input frequencies, the DC inputs, the decision paths, the
      noise over the input, Hsu's study and the noise of each source alone;
    - ``Level.FULL``: the ENOB ladder, the sine on the DAC's SPICE draw and the reference study;
    - ``Level.CIRCUIT``: the circuit simulator's runs.

    The behavioral runs (``_campaign``):

    - ``ramp_train`` and ``ramp_check``: eight full-scale sawtooth periods on the CDAC's SPICE draw
      (its Monte Carlo's middle condition, the draw at the 90th percentile of what no calibration
      recovers), independent noise: the code density, INL and DNL, and the calibrations learned from
      the training ramp and checked on the other.
    - ``rate_<MS/s>``: a -0.5 dBFS sine near fs/8 at each rate of ``RATES_HZ``: ENOB and power over
      the rate.
    - ``noise``: 50 mV at 10 MS/s: the output-code noise spectrum; ``noise_sampling`` and
      ``noise_comparator`` the same with one noise source alone.
    - ``fin_<MS/s>_<cycles>``: the sine at nine input frequencies up to Nyquist at 2, 6 and 10 MS/s.
    - ``dc_<n>``: 33 DC inputs across the full scale: the energy a conversion takes over the input.
    - ``trajectory``: 0 V at 10 MS/s, on the first decision's threshold: the redundant decision
      paths.
    - ``noise_input``: nine DC inputs evenly over +-90 % of the full scale at 10 MS/s, 512
      conversions each, in one staircase: the output-code noise over the input
      (``analyze_input_noise``).
    - ``hsu_r<rate>``: every ideal code centre once (a ramp of one LSB a conversion), at each rate
      of ``RATES_HZ`` with the array's own settling, noiseless but with the comparator's delay (a
      late decision holds the last bit); and ``hsu_reference_r<rate>``, the same inputs at each rate
      with ideal settling and an ideal comparator: the integrated error of each against its rate's
      reference (``analyze_hsu``) over the rate shows how fast the instance converts before the time
      a decision has costs codes, after A. H. T. Chang's thesis (MIT 2013, pp. 77-84): redundancy
      recovers settling errors, not a late comparator's. The reference at the same rate takes off
      what every array shares there (the ramp's input moves while it is sampled, more the faster the
      rate).
    - ``ladder_<step>``: the ``rate_10`` sine with the behavioral converter's impairments added one
      at a time (``LADDER``), from quantization alone (a perfect track-and-hold, no noise, ideal
      settling and an ideal comparator, decoded as ``rate_10`` is) to the converter as ``rate_10``
      has it, whose run is the last step's (``LADDER_NAMES``): what each impairment costs in ENOB
      where it is added (errors add in power, so a source costs fewer bits after larger ones: the
      order matters).
    - ``drawn_sine``: the nominal rate's sine on the DAC's draw: its ENOB before and after the
      calibration.
    - ``ref_ideal``, ``ref_noise_<k>`` and ``ref_r_<k>``: the nominal rate's sine on its own draw
      with the sampler and the comparator ideal (``REFERENCE_QUIET``), on an ideal reference and at
      each point of the reference's noise grid (``REFERENCE_NOISE_V``) and, where the converter has
      decoupling, of its driver's resistance onto it (``REFERENCE_R_OUT_OHM``): the reference
      buffer's requirements this converter sets (``analyze_reference``).
    """
    converter = _converter(pdk, params)
    found = _campaign(converter, level)
    if level is Level.CIRCUIT:
        found |= _spice(pdk, params)
    return found


def _campaign(converter: _Converter, level: Level, *, mismatch_draws: int = MISMATCH_DRAWS) -> dict[str, TbParams]:
    """The behavioral runs of ``converter`` at ``level`` (``runs``); ``mismatch_draws`` capacitor
    draws a Pelgrom coefficient (``mc_<A_C %>_<draw>``) for the Monte Carlo that checks the predicted
    mismatch (``VALIDATION_DRAWS``), none by default: noise-free ramps (four periods, 16 hits a code
    at 12 bits, at least 8 at any) at each coefficient from 0.05 to 0.85 %·sqrt(fF)."""

    tb, full_scale_v, bits = converter.tb, converter.full_scale_v, converter.params.adc_bits
    amplitude_v = full_scale_v * 10 ** (-0.5 / 20)
    # a sawtooth slightly past the full scale, eight periods in the ramp; at least 64 hits a code
    # (14 bits double the ramp: calibration 3 fits its thresholds from the late branches' hits)
    ramp_conversions = max(RAMP_CONVERSIONS, 64 << bits)
    period_s = ramp_conversions / 8 / NOMINAL_RATE_HZ
    edge_v = 1.05 * full_scale_v
    ramp = h.Vpwl.Params(wave=f"0 {-edge_v:.6g} {period_s:.6g} {edge_v:.6g}")
    found = {
        role: replace(
            tb(conversions=ramp_conversions, rate_hz=NOMINAL_RATE_HZ, vin_diff=ramp),
            mismatch_seed=1,
            noise_seed=noise_seed,
            drawn=True,
        )
        for role, noise_seed in (("ramp_train", 1), ("ramp_check", 1001))
    }
    sines = {
        f"rate_{rate / 1e6:g}": tb(conversions=SINE_CONVERSIONS, rate_hz=rate, vin_diff=_sine(amplitude_v, rate, 1021))
        for rate in RATES_HZ
    }
    # the sine at the nominal rate, the ladder's last step
    nominal = sines[LADDER_NAMES[-1]]
    found[LADDER_NAMES[-1]] = nominal
    noise = tb(conversions=100_000, rate_hz=NOMINAL_RATE_HZ, vin_diff=h.Vdc.Params(dc=0.05))
    found["noise"] = noise
    if level is Level.SCREEN:
        return found

    found |= sines
    # the behavioral converter alone can keep one noise source at a time
    for name, quiet in (("noise_sampling", Quiet.COMPARATOR), ("noise_comparator", Quiet.SAMPLING)):
        found[name] = replace(noise, quiet=frozenset({quiet}))
    for rate in FIN_RATES_HZ:
        for cycles in FIN_CYCLES:
            found[f"fin_{rate / 1e6:g}_{cycles}"] = tb(
                conversions=SINE_CONVERSIONS, rate_hz=rate, vin_diff=_sine(amplitude_v, rate, cycles)
            )
    for index, vin_v in enumerate(np.linspace(-full_scale_v, full_scale_v, 33)):
        found[f"dc_{index:02d}"] = tb(
            conversions=2_000, rate_hz=NOMINAL_RATE_HZ, vin_diff=h.Vdc.Params(dc=round(float(vin_v), 6))
        )
    found["trajectory"] = tb(conversions=2_000, rate_hz=NOMINAL_RATE_HZ, vin_diff=h.Vdc.Params(dc=0.0))
    found["noise_input"] = replace(
        tb(
            conversions=INPUT_NOISE_LEVELS * INPUT_NOISE_CONVERSIONS,
            rate_hz=NOMINAL_RATE_HZ,
            vin_diff=_staircase(INPUT_NOISE_SPAN * full_scale_v, 2 * full_scale_v / (1 << bits)),
        ),
        noise_seed=2001,
    )
    for rate_index, rate in enumerate(RATES_HZ):
        found[f"hsu_r{rate_index}"] = replace(
            tb(conversions=(1 << bits) + 1, rate_hz=rate, vin_diff=_code_ramp(full_scale_v, bits, rate)),
            quiet=HSU_QUIET,
        )
        found[f"hsu_reference_r{rate_index}"] = replace(
            tb(conversions=(1 << bits) + 1, rate_hz=rate, vin_diff=_code_ramp(full_scale_v, bits, rate)),
            quiet=HSU_REFERENCE_QUIET,
            tau_scale=0.0,
        )
    if level is Level.SEARCH:
        return found

    # the ladder's steps but the last, which is the nominal rate's sine itself: its testbench and
    # seeds, fewer impairments
    for step, (_, _, quiet, tau_scale) in enumerate(LADDER[:-1]):
        found[f"ladder_{step}"] = replace(nominal, quiet=quiet, tau_scale=tau_scale)
    # the nominal rate's sine on the draw the ramps calibrate on
    found["drawn_sine"] = replace(nominal, drawn=True)
    # the reference study: the nominal sine, its own draw, sampler and comparator ideal, on each
    # reference; the driver's resistance only where the node has decoupling to restore
    ideal = replace(nominal, quiet=REFERENCE_QUIET, drawn=False)
    found["ref_ideal"] = ideal
    for index, noise_v in enumerate(REFERENCE_NOISE_V):
        found[f"ref_noise_{index}"] = replace(ideal, reference_noise_v=float(noise_v))
    decap_f = converter.decoupling_f
    if decap_f > 0:
        for index, r_ohm in enumerate(REFERENCE_R_OUT_OHM):
            found[f"ref_r_{index:02d}"] = replace(ideal, reference_r_ohm=float(r_ohm), reference_c_f=decap_f)
    # at least 8 hits a code over the four periods (14 bits double the ramp)
    mismatch_conversions = max(MISMATCH_CONVERSIONS, 8 << bits)
    mismatch_period_s = mismatch_conversions / 4 / NOMINAL_RATE_HZ
    mismatch_ramp = h.Vpwl.Params(wave=f"0 {-edge_v:.6g} {mismatch_period_s:.6g} {edge_v:.6g}")
    mismatch_tb = tb(conversions=mismatch_conversions, rate_hz=NOMINAL_RATE_HZ, vin_diff=mismatch_ramp)
    for coefficient in MISMATCH_COEFFICIENTS:
        for draw in range(mismatch_draws):
            # noise-free: the capacitors' nonlinearity alone
            found[f"mc_{coefficient * 100:g}_{draw:02d}"] = replace(
                mismatch_tb,
                mismatch_seed=100 + draw,
                unit_mismatch=coefficient,
                quiet=frozenset({Quiet.SAMPLING, Quiet.COMPARATOR}),
            )
    return found


def _spice(pdk: str, params: Params) -> dict[str, TbParams]:
    """The circuit simulator's runs of ``params`` (Spectre), each 100 conversions of a 50 mV input
    with transient noise unless it says otherwise, on FRIDA-1's 256-symbol recipe (a generated design
    of other than its 16 stages: its continuous one), each saving the codes and supplies alone but
    ``spice_rate_10``, which saves the nodes the viewer shows (``Probes``):

    - ``spice_rate_<2|6|10>``: at 0.32, 0.96 and 1.6 GBd;
    - ``spice_ramp``: -0.75 to 0.75 V in 10 mV steps, a conversion each, no noise, at 1.6 GBd;
    - a fabricated converter's on its tape-out's extraction (``Extraction.TAPEOUT``), and the one-layer
      radix-17 flavor's also ``spice_ramp`` and ``spice_supply_<rate>_<none|vdda|vddd|vddac|all>``,
      each rail (or all) behind 1 ohm, 1 nH and 1 pF with 1 mV rms of noise in 25 GHz; and each
      flavor's ``spice_sequence_<comp>_<logic>``, at 1.6 GBd on its layout's signoff extraction
      (``Extraction.SIGNOFF``), the seven continuous 160-symbol timings."""

    fabricated = params.fabricated
    extraction = Extraction.TAPEOUT if fabricated is not None else None
    noisy: dict[str, Any] = {"conversions": 100, "vin_diff": h.Vdc.Params(dc=0.05), "transient_noise": True}
    rates = (("2", 0.32e9), ("6", 0.96e9), ("10", 1.6e9))
    found = {
        f"spice_rate_{rate}": _spice_run(
            pdk,
            params,
            symbol_rate,
            extraction=extraction,
            probes=Probes.NODES if rate == "10" else Probes.CODES,
            **noisy,
        )
        for rate, symbol_rate in rates
    }
    ramp: dict[str, Any] = {"conversions": 151, "vin_diff": hs.LinearSweep(start=-0.75, stop=0.75, step=0.01)}
    if fabricated is None:
        found["spice_ramp"] = _spice_run(pdk, params, 1.6e9, probes=Probes.CODES, **ramp)
        return found
    if fabricated is Fabricated.FRIDA1_1LAYER_RADIX17:
        found["spice_ramp"] = _spice_run(pdk, params, 1.6e9, extraction=extraction, probes=Probes.CODES, **ramp)
        noise_rms_v = 1e-3
        rails = (
            ("none", (0.0, 0.0, 0.0)),
            ("vdda", (noise_rms_v, 0.0, 0.0)),
            ("vddd", (0.0, noise_rms_v, 0.0)),
            ("vddac", (0.0, 0.0, noise_rms_v)),
            ("all", (noise_rms_v, noise_rms_v, noise_rms_v)),
        )
        for rate, symbol_rate in rates:
            for rail, rail_noise in rails:
                found[f"spice_supply_{rate}_{rail}"] = _spice_run(
                    pdk,
                    params,
                    symbol_rate,
                    extraction=extraction,
                    probes=Probes.CODES,
                    conversions=100,
                    vin_diff=h.Vdc.Params(dc=0.05),
                    supply_series_resistance_ohm=1.0,
                    supply_series_inductance_h=1e-9,
                    supply_decoupling_capacitance_f=1e-12,
                    supply_noise_rms_v=rail_noise,
                    supply_noise_bandwidth_hz=25e9,
                )
    # COMP      LOGIC at fall  LOGIC +1 symbol
    # 11110000  00001111       10000111
    # 11111000  10000111       11000011
    # 11111100  11000011       11100001
    # 11111110  11100001       (excluded)
    for timing in (
        Recipe.SYMBOL160_INIT4_SAMP20_COMP11110000_LOGIC00001111,
        Recipe.SYMBOL160_INIT4_SAMP20_COMP11110000_LOGIC10000111,
        Recipe.SYMBOL160_INIT4_SAMP20_COMP11111000_LOGIC10000111,
        Recipe.SYMBOL160_INIT4_SAMP20_COMP11111000_LOGIC11000011,
        Recipe.SYMBOL160_INIT4_SAMP20_COMP11111100_LOGIC11000011,
        Recipe.SYMBOL160_INIT4_SAMP20_COMP11111100_LOGIC11100001,
        Recipe.SYMBOL160_INIT4_SAMP20_COMP11111110_LOGIC11100001,
    ):
        # named by its COMP and LOGIC words, symbol160_init4_samp20_<comp>_<logic>
        name = timing.name.lower().split("_", 3)[-1]
        found[f"spice_sequence_{name}"] = TbParams(
            pdk=pdk,
            params=params,
            simulator=Simulator.SPECTRE,
            extraction=Extraction.SIGNOFF,
            probes=Probes.CODES,
            **noisy,
        ).sequenced(timing.rows, symbol_rate=1.6e9)
    return found


def _sine(amplitude_v: float, rate_hz: float, cycles: int) -> h.Vsin.Params:
    """A sine of ``amplitude_v`` peak making ``cycles`` periods in the campaign's sine captures at
    ``rate_hz``."""
    return h.Vsin.Params(voff=0.0, vamp=amplitude_v, freq=cycles * rate_hz / SINE_CONVERSIONS)


def _staircase(span_v: float, lsb_v: float) -> h.Vpwl.Params:
    """``INPUT_NOISE_LEVELS`` DC levels about evenly over +-``span_v``, each at an ideal code's
    centre (a noise under an LSB reads differently at a code's edge and at its centre, so every
    level sits alike), each held for ``INPUT_NOISE_CONVERSIONS`` conversions at the nominal rate:
    every step falls half a conversion from the samples, in 1 ns."""

    levels = (np.floor(np.linspace(-span_v, span_v, INPUT_NOISE_LEVELS) / lsb_v) + 0.5) * lsb_v
    period_s = 1 / NOMINAL_RATE_HZ
    points = [(0.0, levels[0])]
    for index in range(1, INPUT_NOISE_LEVELS):
        step_s = (index * INPUT_NOISE_CONVERSIONS - 0.5) * period_s
        points += [(step_s - 0.5e-9, levels[index - 1]), (step_s + 0.5e-9, levels[index])]
    # back to the first level after the last conversion, so the wave repeats without a jump at the
    # first one (the sampler's slope there spans the repeat)
    end_s = INPUT_NOISE_LEVELS * INPUT_NOISE_CONVERSIONS * period_s
    points += [(end_s - 0.5 * period_s - 0.5e-9, levels[-1]), (end_s - 0.5 * period_s + 0.5e-9, levels[0])]
    points.append((end_s, levels[0]))
    return h.Vpwl.Params(wave=" ".join(f"{time:.9g} {value:.6g}" for time, value in points))


def _code_ramp(full_scale_v: float, bits: int, rate_hz: float) -> h.Vpwl.Params:
    """A ramp through every ideal code centre, (k + 0.5 - 2^(bits-1)) LSB with the LSB
    2 full_scale_v / 2^bits, one a conversion at ``rate_hz``: conversion k + 1 samples code k's
    centre. Conversion 0 is a dummy a code below: the wave repeats there, in the last half
    conversion, so its slope (which the sampler tracks) is not the ramp's."""

    lsb_v = 2 * full_scale_v / (1 << bits)
    first_v = (0.5 - (1 << (bits - 1))) * lsb_v - lsb_v  # the dummy's input, a code below code 0
    period_s = 1 / rate_hz
    top_s = ((1 << bits) + 0.5) * period_s  # half a conversion past the last
    points = (
        (0.0, first_v),
        (top_s, first_v + ((1 << bits) + 0.5) * lsb_v),
        (((1 << bits) + 1) * period_s, first_v),
    )
    return h.Vpwl.Params(wave=" ".join(f"{time:.9g} {value:.9g}" for time, value in points))


def record(measurements: dict[str, Meas]) -> Record:
    """The record of an instance from the measurements of its runs at any level (``runs``), each a
    ``MeasAdc``: the metrics (``analysis.metrics``, None where its runs did not run) and the
    figures (``flow.adc.plots``, the viewer's details, in its order) of whatever runs it has, a
    SPICE run's and a behavioral run's alike. Every capture is decoded with the design weights and
    with the "extracted" weights of its ``cap_table`` readback (``_extracted``: a PEX table, or the
    DAC's steps as its characterization measured them, or none, the design's own); the
    calibrations learn from the training ramp and are checked on the other, and the one that grades
    the check ramp best decodes the calibrated figures and metrics (calibration 3 keeps the design
    weights where its validation finds no measured weight that helps). Capacitor mismatch is
    predicted rather than drawn (``analyze_mismatch``, from the nominal array's capacitances); where
    the runs also hold the Monte Carlo ramps that check it (``mc_*``), their 95th percentiles at the
    assumed matching are reported beside the predictions. The converter's own numbers come from its
    behavioral runs' readbacks (``analyze_converter``), the reference's requirements from its
    ``ref_*`` runs (``analyze_reference``). The circuit simulator's runs (``spice_*``) add the noise,
    codes and power over the rate, the transfer curve, the noise behind each supply and the
    sequence map, each figure named ``spice_<figure>``; the viewer shows ``spice_rate_10``'s waves."""

    captures = _captures(measurements)
    spice = {name: m for name, m in captures.items() if name.startswith("spice_")}
    captures = {name: m for name, m in captures.items() if not name.startswith("spice_")}
    results: dict[str, Any] = {}
    details: list[Plot] = []

    check, train = captures.get("ramp_check"), captures.get("ramp_train")
    extracted = _extracted(check) if check else None
    design = analyze_ramp(check) if check else None
    if check:
        results["ramp"] = design
        results["extracted"] = analyze_ramp(check, calibration=extracted)
    rates = sorted((m for n, m in captures.items() if n.startswith("rate_")), key=lambda m: float(m.tb.symbol_rate))
    dynamics = [analyze_dynamic(m, calibration=_extracted(m)) for m in rates]
    powers = [analyze_power(m) for m in rates]
    fins = [analyze_dynamic(m, calibration=_extracted(m)) for n, m in captures.items() if n.startswith("fin_")]
    at_nominal = sorted(
        (d for d in fins if round(d.sample_rate_hz) == round(NOMINAL_RATE_HZ)), key=lambda d: d.input_frequency_hz
    )
    dcs = [m for n, m in sorted(captures.items()) if n.startswith("dc_")]
    learned: dict[str, AnalysisCalibration] = {}
    calibrated = best = None
    if train and check:
        train_ramp = analyze_ramp(train)
        learned["Calibration 2"] = analyze_calibration2(train, ramp=train_ramp)
        # calibration 3 fits a threshold in every late branch, and a ramp can hold too few hits there
        # to bracket one; then it is left out (``calibration3_fitted`` says so) rather than failing
        # the rest
        try:
            results["calibration3"] = learned["Calibration 3"] = analyze_calibration3(train, ramp=train_ramp)
        except ValueError:
            pass
        decoded = {label: analyze_ramp(check, calibration=calibration) for label, calibration in learned.items()}
        best = min(learned, key=lambda label: decoded[label].maximum_abs_inl)
        calibrated = results["calibrated"] = decoded[best]
    redundancy = analyze_redundancy(extracted) if extracted else None
    paths = analyze_decision_paths(captures["trajectory"]) if "trajectory" in captures else None
    noise = captures.get("noise")
    spectrum = analyze_code_spectrum(noise, calibration=_extracted(noise)) if noise else None
    input_noise = analyze_input_noise([captures["noise_input"]]) if "noise_input" in captures else None
    if input_noise is not None and len(input_noise.level_v) != INPUT_NOISE_LEVELS:
        raise ValueError(f"noise_input holds {len(input_noise.level_v)} input levels, not {INPUT_NOISE_LEVELS}")
    hsu_names = [f"hsu_{kind}r{index}" for kind in ("", "reference_") for index in range(len(RATES_HZ))]
    hsu = analyze_hsu([captures[name] for name in hsu_names]) if all(n in captures for n in hsu_names) else None
    energy = analyze_energy(dcs, power=[analyze_power(m) for m in dcs]) if dcs else None
    ladder = _ladder(captures)
    # the mismatch, predicted from the nominal array (a capture without a draw)
    mismatch = analyze_mismatch(noise) if noise else None
    prediction = analyze_mismatch_prediction(mismatch) if mismatch else None
    reference_runs = [m for n, m in captures.items() if n.startswith("ref_")]
    reference = analyze_reference(reference_runs, calibration=_extracted(reference_runs[0])) if reference_runs else None
    figures: list[tuple[Any, tuple[Callable[..., Plot], ...]]] = [
        (redundancy, (plot_redundancy,)),
        (design, (plot_code_density, plot_inl)),
        (calibrated, (plot_inl_calibrated,)),
        (design, (plot_dnl,)),
        (calibrated, (plot_dnl_calibrated,)),
        (paths, (plot_trajectory, plot_trajectory_final, plot_trajectory_codes)),
        (spectrum, (plot_noise_spectrum,)),
        (input_noise, (plot_noise_input,)),
    ]
    for result, plots in figures:
        if result is not None:
            details.extend(figure(result) for figure in plots)
    if dynamics:
        details.append(plot_enob_rate(dynamics))
    if at_nominal:
        details.append(plot_enob_fin(at_nominal))
    if ladder is not None:
        details.append(plot_enob_ladder(ladder))
    if at_nominal:
        details += [plot_spectrum_low(at_nominal[0]), plot_spectrum_nyquist(at_nominal[-1])]
    if hsu is not None:
        details.append(plot_hsu_rate(hsu))
    if powers:
        details.append(plot_power_rate(powers))
    if energy is not None:
        details += [plot_energy_input(energy), plot_energy_dac_input(energy)]
    if extracted is not None:
        details.append(plot_calibration_weights(extracted))
    if prediction is not None:
        details += [
            plot_mismatch_weight_sigma(prediction),
            plot_mismatch_transition_sigma(prediction),
            plot_mismatch_margin(prediction),
            plot_mismatch_dnl(prediction),
            plot_mismatch_inl(prediction),
        ]
    if reference is not None:
        details.append(plot_reference_noise(reference))
        # the driver's resistance only where the reference node has decoupling to restore
        if len(reference.r_out_ohm):
            details.append(plot_reference_r_out(reference))
    if "drawn_sine" in captures:
        sine = captures["drawn_sine"]
        results["drawn_design"] = analyze_dynamic(sine)
        results["drawn_extracted"] = analyze_dynamic(sine, calibration=_extracted(sine))
        if best is not None:
            results["drawn_calibrated"] = analyze_dynamic(sine, calibration=learned[best])
    draws = [m for n, m in sorted(captures.items()) if n.startswith("mc_")]
    spice_figures, spice_results, waves = _spice_record(spice)
    numbers = metrics(
        dynamics=dynamics,
        powers=powers,
        fins=at_nominal,
        noise=analyze_noise_rms(noise) if noise else None,
        input_noise=input_noise,
        hsu=hsu,
        redundancy=redundancy,
        mismatch=mismatch,
        noise_sampling=analyze_noise_rms(captures["noise_sampling"]) if "noise_sampling" in captures else None,
        noise_comparator=analyze_noise_rms(captures["noise_comparator"]) if "noise_comparator" in captures else None,
        ladder=ladder,
        draws=analyze_mismatch_draws(draws, ramps=[analyze_ramp(m) for m in draws]) if draws else None,
        converter=analyze_converter(next(iter(captures.values()))) if captures else None,
        reference=reference,
        **results,
        **spice_results,
    )
    return Record(metrics=numbers, details=details + spice_figures, waves=waves)


def _spice_run(pdk: str, params: Params, symbol_rate: float, **fields: Any) -> TbParams:
    """A circuit run of ``params`` at ``symbol_rate`` with ``fields``: on FRIDA-1's testbench and
    256-symbol recipe where the design has FRIDA-1's stages, else each DAC state sized to the
    design's and its continuous sequence."""
    recipe = Recipe.SYMBOL256_INIT8_SAMP16_COMP11110000_LOGIC11000011
    stages = len(capdac.Model.weights(params.cdac))
    # the stages FRIDA-1's testbench and recipe are for
    if stages == len(capdac.Model.weights(Fabricated.FRIDA1_1LAYER_RADIX17.params.cdac)):
        return TbParams(pdk=pdk, params=params, simulator=Simulator.SPECTRE, **fields).sequenced(
            recipe.rows, symbol_rate=symbol_rate
        )
    states: dict[str, Any] = {
        "dac_astate_p": tuple(stage % 2 for stage in range(stages)),
        "dac_astate_n": tuple(stage % 2 for stage in range(stages)),
        "dac_bstate_p": (0,) * stages,
        "dac_bstate_n": (0,) * stages,
    }
    tb = TbParams(pdk=pdk, params=params, simulator=Simulator.SPECTRE, **states, **fields)
    return tb.continuous(stages).sequenced(symbol_rate=symbol_rate)


def _spice_named(figure: Plot) -> Plot:
    """A figure of the circuit runs, named ``spice_<figure>``."""
    return replace(figure, name=f"spice_{figure.name}")


def _spice_record(spice: dict[str, MeasAdc]) -> tuple[list[Plot], dict[str, Any], dict[str, str]]:
    """The circuit simulator's runs' figures (each a record figure named ``spice_<figure>``), their
    results for the metrics, and the run whose waves the viewer shows: the fixed input's noise, its
    noise-equivalent ENOB, its codes and the supply power over the rate (``spice_rate_*``); the
    transfer curve (``spice_ramp``); the noise over the rate behind each noisy supply
    (``spice_supply_*``, a figure a rail); the sequence map of the timings (``spice_sequence_*``),
    and each timing's decision paths and programmed sequence."""

    figures: list[Plot] = []
    results: dict[str, Any] = {}
    rates = sorted((m for n, m in spice.items() if n.startswith("spice_rate_")), key=lambda m: m.sample_rate_hz)
    if rates:
        noises = [analyze_noise(m) for m in rates]
        powers = [analyze_power(m) for m in rates]
        figures += [
            _spice_named(plot_noise_rate(noises)),
            _spice_named(plot_noise_enob_rate(noises)),
            _spice_named(plot_codes_rate(noises)),
        ]
        figures.append(_spice_named(plot_power_rate(powers)))
    if "spice_rate_10" in spice:
        results["spice_noise"] = analyze_noise(spice["spice_rate_10"])
        results["spice_power"] = analyze_power(spice["spice_rate_10"])
    if "spice_ramp" in spice:
        figures.append(_spice_named(plot_transfer(analyze_transfer([spice["spice_ramp"]]))))
    rails: dict[str, list[MeasAdc]] = {}
    for name, measurement in spice.items():
        if name.startswith("spice_supply_"):
            # spice_supply_<rate>_<rail>
            rails.setdefault(name.split("_", 3)[3], []).append(measurement)
    for rail, measurements in rails.items():
        noises = sorted((analyze_noise(m) for m in measurements), key=lambda noise: noise.sample_rate_hz)
        figures.append(replace(plot_noise_rate(noises), name=f"spice_supply_{rail}_noise_rate"))
    sequences = [m for n, m in spice.items() if n.startswith("spice_sequence_")]
    if sequences:
        conditions = analyze_operating_conditions(sequences, noise=[analyze_noise(m) for m in sequences])
        timings = analyze_sequence_map([conditions])
        figures += [
            _spice_named(plot_sequence_enob(timings)),
            _spice_named(plot_sequence_plausible(timings)),
            _spice_named(plot_sequence_shift(timings)),
        ]
        # each timing's decision paths (whole, their last decisions, the codes they end on) and its
        # programmed sequence, a figure each named by its run (spice_sequence_<comp>_<logic>_<figure>)
        for name, measurement in spice.items():
            if name.startswith("spice_sequence_"):
                paths = analyze_decision_paths(measurement)
                figures += [
                    replace(figure, name=f"{name}_{figure.name}")
                    for figure in (
                        plot_trajectory(paths),
                        plot_trajectory_final(paths),
                        plot_trajectory_codes(paths),
                        plot_sequencer(analyze_sequencer(measurement)),
                    )
                ]
    waves = {"spice_rate_10": "spice_rate_10"} if "spice_rate_10" in spice else {}
    return figures, results, waves


def _captures(measurements: dict[str, Meas]) -> dict[str, MeasAdc]:
    """The runs' measurements, each a converter's captures (``MeasAdc``, ``flow.adc.sim.read``'s)."""
    for name, measurement in measurements.items():
        if not isinstance(measurement, MeasAdc):
            raise TypeError(f"{name}: a {type(measurement).__name__}, not the converter's MeasAdc")
    return dict(measurements)  # ty: ignore[invalid-return-type]


def _extracted(measurement: MeasAdc) -> AnalysisCalibration:
    """A capture's "extracted" weights: from what its ``cap_table`` readback names (a PEX table; a
    behavioral capture's, the settling measurement its DAC's characterization keeps, each stage's
    step as measured, ``flow.analysis.io.read_cap_table``); none, a DAC designed alone: the design's
    weights."""
    path = Path(str(measurement.info.readbacks["cap_table"]))
    if path == Path():
        return _extracted_calibration(measurement, None, "Design weights, nothing extracted")
    label = "Measured-step weights" if path.suffix == ".h5" else "PEX-extracted weights"
    return _extracted_calibration(measurement, read_cap_table(path), label)


def _ladder(captures: dict[str, MeasAdc]) -> AnalysisLadder | None:
    """The ENOB ladder (``LADDER``) of the runs' captures, each step decoded as ``enob_bits`` is
    (the extracted weights, unrounded); None where the runs have no ladder (below ``Level.FULL``)."""
    if not all(name in captures for name in LADDER_NAMES):
        return None
    return analyze_ladder(
        [analyze_dynamic(captures[name], calibration=_extracted(captures[name])) for name in LADDER_NAMES]
    )
