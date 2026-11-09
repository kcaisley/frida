"""The ADC's design space (``flow.sweep``), by the behavioral converter (``flow.adc.sim``) of its
characterized blocks: the plain product of its components, each converter given by its parameters;
in TSMC65 alone, the one PDK its DAC is characterized in (``flow.capdac.runs``).

Every converter samples on its top plates, makes one free comparison before any capacitor switches
and fires the comparator again after the last one switches: an N-bit converter has an N-1-step DAC
(``adc_bits`` is its array's ``bits``) and N + extra decisions. Its arrays are capdac's, every one
of its design space (``capdac.arrays`` and ``capdac.frida1``): each at one and two kT/C minimums of
switched capacitance (``capdac.Params.scale``, at a full scale of the reference: the full scale its
plates give is the record's ``full_scale_over_reference``), its weights built both ways
(``capdac.WeightImpl``: difference capacitors in long strips, or unit capacitors), its drivers
sized to settle each stage to half an LSB within 1 ns (``capdac.Params.settle_ps``). The
difference capacitors are labelled by the names the legacy extractions gave them, the unit
capacitors by the same with ``_unit``. Each converter's DAC is capdac's
characterization of the same array, found by its digest.

The product, nothing pruned:

- the comparators of the comparator grid (five noise levels by four
  delays, FRIDA-1's StrongARM among them at its fabricated sizes);
- the samplers, an on-resistance ladder: FRIDA-1's transmission gate (32
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
comparator grid the PDK's own (``flow.comp.runs``), each array with the PDK's StrongARM noise
ladder at about FRIDA-1's speed and the widest bootstrapped switch, 484 to 605 converters a PDK. The design space is a grid (``converters``,
docs/pipeline.md): one space per resolution, its arrays, comparators and samplers values by name.

FRIDA-1 is in it twice: as a generated design (``frida1``, its sizing, which the grid also reaches)
and as its four fabricated converters (``frida1_<layers>layer_radix<radix>``, ``Fabricated``),
whose behavioral characterization is FRIDA-1's sizing alike and whose circuit runs simulate their
extractions.

Each instance's testbenches (``testbenches``, built by ``flow.adc.sim``) at a level (``flow.pipeline.Level``) are the behavioral campaign's,
the cheapest first, and at ``Level.CIRCUIT`` the circuit simulator's as well (``spice_*``, Spectre:
a candidate's netlist, a fabricated converter's extraction); its record (``record``) holds the
metrics and figures of whatever runs it has (the analyses of ``flow.adc.analysis``, the figures of
``flow.adc.plots``), each metric None where its runs did not run, the circuit runs' under the same
names for a candidate and a fabricated converter, so the two line up in one table.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from typing import Any

from flow import capdac, comp, samp
from flow.analysis.types import MeasAdc
from flow.pipeline import Level, Meas, Pdk, Plot, Record, grid, single, values, widen

from .analysis import (
    analyze_calibration2,
    analyze_calibration3,
    analyze_code_spectrum,
    analyze_converter,
    analyze_decision_paths,
    analyze_dynamic,
    analyze_energy,
    analyze_extracted,
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
    FRIDA1_ARRAY,
    INPUT_NOISE_LEVELS,
    LADDER_NAMES,
    NOMINAL_RATE_HZ,
    RATES_HZ,
    RESOLUTIONS,
    Fabricated,
    Params,
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
from .sim import behavioral_testbenches, spice_testbenches
from .types import AnalysisCalibration


# in TSMC65 alone until capdac is characterized elsewhere: a converter's DAC is its record
@grid(pdks=(Pdk.TSMC65,))
def converters(pdk: Pdk) -> dict[str, Params]:
    """Every comparator with every sampler and ADC array, one space per resolution, each array at
    its resolution (``adc_bits`` its ``bits``): in TSMC65 the full product; the other PDKs' spaces the
    smaller one, which the grid leaves out. A converter is labelled by its resolution and its parts'
    names, ``converters(12b, cdac=12b_binary_x1, comp=200uV_2ns, samp=frida1)``.

    - The arrays: capdac's grid (``capdac.arrays``) at the resolution, its difference capacitors and
      then its unit capacitors, each at one then two kT/C minimums, each the binary array and then
      each scheme with 2, 4 and 6 extra cycles; at FRIDA-1's resolution its array last
      (``FRIDA1_ARRAY``, ``capdac.frida1``); each by the name the legacy extractions gave it,
      ``12b_binary_x1``, ``12b_msb_redist5_x2`` (FRIDA-1's), ``14b_lsb_split6_x2``, unit capacitors'
      the same with ``_unit``.
    - The comparators: TSMC65's grid by noise and delay (``200uV_2ns``): five levels of
      input-referred noise (rows, at the nominal common mode) by four of delay (columns, at
      0.5 mV), each cell the characterized comparator of least energy per decision within 15 % of
      the noise and 20 % of the delay (flow/comp/readme.md), FRIDA-1's at 200 uV and 2 ns, each from
      the comparator's grids by name (``comp.base_strongarm``, ``comp.dynamic_bias``); elsewhere the
      PDK's StrongARM noise ladder at its longest tail, by its width factor (``k2.5``).
    - The samplers: TSMC65's an on-resistance ladder, FRIDA-1's transmission gate (``frida1``) the
      worst, then the bootstrapped NMOS switch's rungs (``samp.boost_ladder``, ``boost_<rung>``),
      none with dummy switches; elsewhere the bootstrapped switch's widest rung alone."""
    strongarm = {name: space.base for name, space in comp.base_strongarm.spaces(pdk).items()}
    boost = {f"boost_{name}": space.base for name, space in samp.boost_ladder.spaces(pdk).items()}
    if pdk is Pdk.TSMC65:
        dynamic = {name: space.base for name, space in comp.dynamic_bias.spaces(pdk).items()}
        cells = (
            # 0.5 ns                      1 ns                          1.5 ns                         2 ns
            strongarm["tail_l=14, k=3"],  dynamic["ratio=3.5, k=0.75"], dynamic["ratio=2.75, k=0.75"], comp.FRIDA1,  # 200 uV
            strongarm["tail_l=14, k=6"],  dynamic["ratio=3.5, k=1.5"],  dynamic["ratio=2.75, k=1.5"],  dynamic["ratio=2.25, k=1.5"],  # 150 uV
            strongarm["tail_l=14, k=12"], dynamic["ratio=3.5, k=3"],    dynamic["ratio=2.75, k=3"],    dynamic["ratio=2.25, k=3"],  # 100 uV
            strongarm["tail_l=14, k=32"], dynamic["ratio=3.5, k=6"],    dynamic["ratio=2.75, k=6"],    dynamic["ratio=2.25, k=6"],  # 70 uV
            strongarm["tail_l=14, k=64"], dynamic["ratio=3.5, k=12"],   dynamic["ratio=2.75, k=12"],   dynamic["ratio=2.25, k=12"],  # 50 uV
        )  # fmt: skip
        # each cell's noise and delay, in the cells' order (the noise outer)
        targets = [
            (noise, delay) for noise in (200e-6, 150e-6, 100e-6, 70e-6, 50e-6) for delay in (0.5e-9, 1e-9, 1.5e-9, 2e-9)
        ]
        comparators = {
            f"{noise * 1e6:g}uV_{delay * 1e9:g}ns": params
            for (noise, delay), params in zip(targets, cells, strict=True)
        }
        samplers = {"frida1": samp.FRIDA1, **boost}
    else:
        longest = max(params.tail_l for params in strongarm.values())
        comparators = {f"k{name.rsplit('k=', 1)[1]}": p for name, p in strongarm.items() if p.tail_l == longest}
        samplers = dict([list(boost.items())[-1]])
    schemes, builds = list(capdac.Redundancy), list(capdac.WeightImpl)
    spaces = {}
    for bits in RESOLUTIONS:
        swept = sorted(
            (cdac for _label, cdac in capdac.arrays.instances(pdk) if cdac.bits == bits),
            key=lambda cdac: (builds.index(cdac.weight_impl), cdac.scale, schemes.index(cdac.redundancy), cdac.extra),
        )
        arrays = {
            f"{cdac.bits}b_{cdac.redundancy.name.lower()}{cdac.extra or ''}_x{cdac.scale}"
            f"{'_unit' if cdac.weight_impl is capdac.WeightImpl.UNIT_CAPS else ''}": cdac
            for cdac in [*swept, *([FRIDA1_ARRAY] if FRIDA1_ARRAY.bits == bits else [])]
        }
        space = widen(Params(adc_bits=bits, cdac=next(iter(arrays.values())), comp=comp.FRIDA1, samp=samp.FRIDA1))
        space.cdac = values(arrays)
        space.comp = values(comparators)
        space.samp = values(samplers)
        spaces[f"{bits}b"] = space
    return spaces


@single
def frida1() -> Params:
    """FRIDA-1's converter as a generated design: its sizing, capdac's, the sampler's and the
    comparator's FRIDA-1 parts."""
    return Params()


@single
def frida1_1layer_radix17() -> Params:
    """FRIDA-1's fabricated converter, its DAC in one metal layer at radix 17."""
    return Fabricated.FRIDA1_1LAYER_RADIX17.params


@single
def frida1_1layer_radix20() -> Params:
    """FRIDA-1's fabricated converter, its DAC in one metal layer at radix 20."""
    return Fabricated.FRIDA1_1LAYER_RADIX20.params


@single
def frida1_2layer_radix17() -> Params:
    """FRIDA-1's fabricated converter, its DAC in two metal layers at radix 17."""
    return Fabricated.FRIDA1_2LAYER_RADIX17.params


@single
def frida1_2layer_radix20() -> Params:
    """FRIDA-1's fabricated converter, its DAC in two metal layers at radix 20."""
    return Fabricated.FRIDA1_2LAYER_RADIX20.params


def testbenches(pdk: str, params: Params, level: Level = Level.FULL) -> dict[str, TbParams]:
    """The runs that characterize ``params`` in ``pdk`` at ``level``, by name, each behavioral (its
    converter, ``flow.adc.sim``'s, of the blocks' characterizations), and at ``Level.CIRCUIT`` the
    circuit simulator's as well (``sim.spice_testbenches``). Each level holds the one below it:

    - ``Level.SCREEN``: ``ramp_train`` and ``ramp_check``, ``rate_10`` and ``noise``: the linearity,
      the calibrations, the ENOB and power at the nominal rate and the output-code noise;
    - ``Level.SEARCH``: every rate, the input frequencies, the DC inputs, the decision paths, the
      noise over the input, Hsu's study and the noise of each source alone;
    - ``Level.FULL``: the ENOB ladder, the sine on the DAC's SPICE draw and the reference study;
    - ``Level.CIRCUIT``: the circuit simulator's runs, in TSMC65 (its kit's includes; elsewhere none:
      FULL's runs), each extraction they simulate checked first.

    The behavioral runs (``sim.behavioral_testbenches``):

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
    found = behavioral_testbenches(pdk, params, level)
    if level is Level.CIRCUIT:
        found |= spice_testbenches(pdk, params)
    return found


def record(measurements: dict[str, Meas]) -> Record:
    """The record of an instance from the measurements of its runs at any level (``testbenches``), each a
    ``MeasAdc``: the metrics (``analysis.metrics``, None where its runs did not run) and the
    figures (``flow.adc.plots``, the viewer's details, in its order) of whatever runs it has, a
    SPICE run's and a behavioral run's alike. Every capture is decoded with the design weights and
    with the "extracted" weights of its ``cap_table`` readback (``analyze_extracted``: a PEX table, or the
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

    for name, measurement in measurements.items():
        if not isinstance(measurement, MeasAdc):
            raise TypeError(f"{name}: a {type(measurement).__name__}, not the converter's MeasAdc")
    captures: dict[str, MeasAdc] = dict(measurements)  # ty: ignore[invalid-assignment]
    spice = {name: m for name, m in captures.items() if name.startswith("spice_")}
    captures = {name: m for name, m in captures.items() if not name.startswith("spice_")}
    results: dict[str, Any] = {}
    details: list[Plot] = []

    check, train = captures.get("ramp_check"), captures.get("ramp_train")
    extracted = analyze_extracted(check) if check else None
    design = analyze_ramp(check) if check else None
    if check:
        results["ramp"] = design
        results["extracted"] = analyze_ramp(check, calibration=extracted)
    rates = sorted((m for n, m in captures.items() if n.startswith("rate_")), key=lambda m: float(m.tb.symbol_rate))
    dynamics = [analyze_dynamic(m, calibration=analyze_extracted(m)) for m in rates]
    powers = [analyze_power(m) for m in rates]
    fins = [analyze_dynamic(m, calibration=analyze_extracted(m)) for n, m in captures.items() if n.startswith("fin_")]
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
    spectrum = analyze_code_spectrum(noise, calibration=analyze_extracted(noise)) if noise else None
    input_noise = analyze_input_noise([captures["noise_input"]]) if "noise_input" in captures else None
    if input_noise is not None and len(input_noise.level_v) != INPUT_NOISE_LEVELS:
        raise ValueError(f"noise_input holds {len(input_noise.level_v)} input levels, not {INPUT_NOISE_LEVELS}")
    hsu_names = [f"hsu_{kind}r{index}" for kind in ("", "reference_") for index in range(len(RATES_HZ))]
    hsu = analyze_hsu([captures[name] for name in hsu_names]) if all(n in captures for n in hsu_names) else None
    energy = analyze_energy(dcs, power=[analyze_power(m) for m in dcs]) if dcs else None
    # the ENOB ladder (``LADDER``), each step decoded as ``enob_bits`` is (the extracted weights,
    # unrounded); none below ``Level.FULL``
    ladder = (
        analyze_ladder([analyze_dynamic(captures[n], calibration=analyze_extracted(captures[n])) for n in LADDER_NAMES])
        if all(name in captures for name in LADDER_NAMES)
        else None
    )
    # the mismatch, predicted from the nominal array (a capture without a draw)
    mismatch = analyze_mismatch(noise) if noise else None
    prediction = analyze_mismatch_prediction(mismatch) if mismatch else None
    reference_runs = [m for n, m in captures.items() if n.startswith("ref_")]
    reference = (
        analyze_reference(reference_runs, calibration=analyze_extracted(reference_runs[0])) if reference_runs else None
    )
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
        results["drawn_extracted"] = analyze_dynamic(sine, calibration=analyze_extracted(sine))
        if best is not None:
            results["drawn_calibrated"] = analyze_dynamic(sine, calibration=learned[best])
    draws = [m for n, m in sorted(captures.items()) if n.startswith("mc_")]
    # the circuit simulator's runs: the fixed input's noise, its noise-equivalent ENOB, its codes and
    # the supply power over the rate (spice_rate_*); the transfer curve (spice_ramp); the noise over
    # the rate behind each noisy supply (spice_supply_*, a figure a rail); the sequence map of the
    # timings (spice_sequence_*) and each timing's decision paths and programmed sequence; each
    # figure named spice_<figure>
    spice_figures: list[Plot] = []
    spice_results: dict[str, Any] = {}
    spice_rates = sorted((m for n, m in spice.items() if n.startswith("spice_rate_")), key=lambda m: m.sample_rate_hz)
    if spice_rates:
        spice_noises = [analyze_noise(m) for m in spice_rates]
        spice_figures += [
            replace(figure, name=f"spice_{figure.name}")
            for figure in (
                plot_noise_rate(spice_noises),
                plot_noise_enob_rate(spice_noises),
                plot_codes_rate(spice_noises),
                plot_power_rate([analyze_power(m) for m in spice_rates]),
            )
        ]
    if "spice_rate_10" in spice:
        spice_results["spice_noise"] = analyze_noise(spice["spice_rate_10"])
        spice_results["spice_power"] = analyze_power(spice["spice_rate_10"])
    if "spice_ramp" in spice:
        transfer = plot_transfer(analyze_transfer([spice["spice_ramp"]]))
        spice_figures.append(replace(transfer, name=f"spice_{transfer.name}"))
    rails: dict[str, list[MeasAdc]] = {}
    for name, measurement in spice.items():
        if name.startswith("spice_supply_"):  # spice_supply_<rate>_<rail>
            rails.setdefault(name.split("_", 3)[3], []).append(measurement)
    for rail, rail_runs in rails.items():
        rail_noises = sorted((analyze_noise(m) for m in rail_runs), key=lambda noise: noise.sample_rate_hz)
        spice_figures.append(replace(plot_noise_rate(rail_noises), name=f"spice_supply_{rail}_noise_rate"))
    sequences = [m for n, m in spice.items() if n.startswith("spice_sequence_")]
    if sequences:
        conditions = analyze_operating_conditions(sequences, noise=[analyze_noise(m) for m in sequences])
        timings = analyze_sequence_map([conditions])
        spice_figures += [
            replace(figure, name=f"spice_{figure.name}")
            for figure in (plot_sequence_enob(timings), plot_sequence_plausible(timings), plot_sequence_shift(timings))
        ]
        # each timing's decision paths (whole, their last decisions, the codes they end on) and its
        # programmed sequence, a figure each named by its run (spice_sequence_<comp>_<logic>_<figure>)
        for name, measurement in spice.items():
            if name.startswith("spice_sequence_"):
                sequence_paths = analyze_decision_paths(measurement)
                spice_figures += [
                    replace(figure, name=f"{name}_{figure.name}")
                    for figure in (
                        plot_trajectory(sequence_paths),
                        plot_trajectory_final(sequence_paths),
                        plot_trajectory_codes(sequence_paths),
                        plot_sequencer(analyze_sequencer(measurement)),
                    )
                ]
    waves = {"spice_rate_10": "spice_rate_10"} if "spice_rate_10" in spice else {}
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
