"""The ADC's design space (``flow.sweep``), by the behavioral model (``flow.adc.model``) of its
characterized blocks: the plain product of its components, each converter given by its parameters;
in TSMC65 the full product below, in the other PDKs a smaller one.

Every converter samples on its top plates, makes one free comparison before any capacitor switches
and fires the comparator again after the last one switches: an N-bit converter has an N-1-step DAC
(``adc_bits = n_dac + 1``) and n_dac + n_extra + 1 decisions. Its arrays are the ADC study's
(``flow.cdac.caparray.layout.ADC_ARRAYS``: three-metal unit-length arrays, each sized through its 3-D
extraction in each PDK, ``flow.cdac.caparray.sizing``). Every
array's full scale is at least 80 % of the reference and its sampled noise at most its quantization
noise there: each resolution's least switched capacitance is the larger of the two constraints'
for its most demanding array, and each array switches one or two times it (``cap_scale``) at the
split between its length-scaled binary and unary rows that keeps both with its outline nearest
twice as tall as wide (one side's array: the two side by side make about a square). Its
drivers are derived from its extracted plates (``flow.cdac.capdriver.model.driver_strengths``), each stage
sized to settle in about 1 ns.

The product, nothing pruned:

- the comparators of the comparator grid (``_comparators``: five noise levels by four
  delays, FRIDA-1's StrongARM among them at its fabricated sizes);
- the samplers (``_samplers``), an on-resistance ladder: FRIDA-1's transmission gate (32
  minimum widths, minimum length) the worst, then the bootstrapped NMOS switch at 32, 64, 112 and
  160 minimum widths (``samp.boost_ladder``, each boosted alike), about a half, a
  quarter, a seventh and a tenth of the gate's resistance; none with half-size dummy switches, as
  FRIDA-1's;
- the arrays, 10 at each resolution and scale: binary, and each scheme
  (``flow.cdac.caparray.subckt.RedunStrat``: the MSBs split, the LSBs split, FRIDA's MSB redistribution)
  with 2, 4 and 6 extra cycles, every one of the binary total weight;
- the resolutions, 10, 12 and 14 bits;
- the switched capacitance, one and two times the resolution's least (``cap_scale``);
- and FRIDA-1's array (``RADIX17``: 12 bits on MSB redistribution with 5 extra cycles, 17
  decisions) at two times the 12-bit least, near its drawn size.

20 x 5 x (10 x 3 x 2 + 1) = 6,100 converters in TSMC65. In the other PDKs, where the arrays and
the blocks are the same study's but the comparator grid is the PDK's own (``flow.comp.sweep``), each
array with the PDK's StrongARM noise ladder at about FRIDA-1's speed (``_comparators``) and the widest
bootstrapped switch (``_samplers``): 244 to 305 converters a PDK. The design space is a grid
(``converters``, docs/pipeline.md): one space per resolution, its arrays, comparators and samplers
values by name.

Each instance runs the campaign (``campaign``: every capture its record needs) and records its
metrics and figures (``record``: the analyses of ``flow.adc.analysis``, the figures of
``flow.adc.plots``) for the viewer; its captures stay in memory, so its run is its record. Its
geometry metrics are those of its analog blocks (``GENERATOR``, ``flow.adc.subckt.AdcBlocks``).

The named Spectre runs (``hdl21_sample_rate`` to ``frida2_sequence``, the CLI's ``python -m flow
adc.<name>``, ``flow.adc.targets``): the generated or an extracted converter's testbenches
(``sim.testbench``), simulated side by side (``sim.simulate``), each run's measurement written
beside it (``result.h5``).
"""

from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import ProcessPoolExecutor
from dataclasses import replace
from itertools import product
from multiprocessing import get_context
from pathlib import Path

import hdl21 as h
import hdl21.sim as hs
import numpy as np
from hdl21.prefix import G

from flow import comp, samp
from flow.analysis.io import read_extracted_calibration
from flow.analysis.types import MeasAdc
from flow.cdac.caparray.layout import ADC_ARRAYS, adc_arrays
from flow.cdac.caparray.subckt import CapArrayConfig
from flow.pipeline import Pdk, Record, grid, values, widen

from .analysis import (
    analyze_calibration2,
    analyze_calibration3,
    analyze_code_spectrum,
    analyze_decision_paths,
    analyze_dynamic,
    analyze_energy,
    analyze_hsu,
    analyze_input_noise,
    analyze_ladder,
    analyze_mismatch,
    analyze_mismatch_draws,
    analyze_mismatch_prediction,
    analyze_noise_rms,
    analyze_power,
    analyze_ramp,
    analyze_redundancy,
    metrics,
)
from .params import (
    FIN_CYCLES,
    FIN_RATES_HZ,
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
    RESOLUTIONS,
    SINE_CONVERSIONS,
    Capture,
    Params,
    TbParams,
)
from .plots import (
    plot_calibration_weights,
    plot_code_density,
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
    plot_noise_input,
    plot_noise_spectrum,
    plot_power_rate,
    plot_redundancy,
    plot_reference_noise,
    plot_reference_r_out,
    plot_spectrum_low,
    plot_spectrum_nyquist,
    plot_trajectory,
    plot_trajectory_codes,
    plot_trajectory_final,
)
from .sim import SEQUENCES, simulate, symbol256_init8_samp16_comp11110000_logic11000011
from .subckt import AdcBlocks
from .types import AnalysisCalibration, AnalysisLadder


def _arrays(bits: int, cap_scale: int = 1) -> list[CapArrayConfig]:
    """A ``bits`` converter's 10 arrays at ``cap_scale``: binary, and each scheme with 2, 4 and 6
    extra cycles (``flow.cdac.caparray.layout.adc_arrays``)."""
    return adc_arrays(bits, cap_scale)


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


@grid
def converters(pdk: Pdk) -> dict[str, Params]:
    """Every comparator with every sampler and ADC array (``ADC_ARRAYS``: each resolution's arrays
    at both scales, and FRIDA-1's), one space per resolution, each array at its resolution
    (``adc_bits = n_dac + 1``): in TSMC65 the full product, elsewhere the PDK's smaller one
    (``_comparators``, ``_samplers``), each array sized through its extraction there. A converter is
    labelled by its resolution and its parts' names, ``converters(12b, cdac=12b_binary_x1,
    comp=200uV_2ns, samp=frida1)``."""
    folder = pdk.name.lower()
    spaces = {}
    for bits in RESOLUTIONS:
        space = widen(Params(adc_bits=bits, comp=comp.FRIDA1, samp=samp.FRIDA1))
        space.cdac = values({name: cdac for name, cdac in ADC_ARRAYS.items() if cdac.n_dac + 1 == bits})
        space.comp = values(_comparators(folder))
        space.samp = values(_samplers(folder))
        spaces[f"{bits}b"] = space
    return spaces


def campaign(
    tb: Callable[..., TbParams], full_scale_v: float, bits: int = 12, *, mismatch_draws: int = MISMATCH_DRAWS
) -> dict[str, Capture]:
    """Every capture of the campaign, by name, for a ``bits`` ADC whose differential full scale is
    +-``full_scale_v``, each a testbench from ``tb`` (``tb(conversions=, rate_hz=, vin_diff=)``);
    ``mismatch_draws`` capacitor draws a Pelgrom coefficient for the Monte Carlo that checks the
    predicted mismatch (``VALIDATION_DRAWS``), none by default.

    The captures are what the record needs, as testbench parameters (``TbParams``) from a builder,
    the same for a SPICE run of ``sim.testbench`` and for the behavioral model (``flow.adc.model``),
    each of which turns one into a ``MeasAdc``.

    - ``ramp_train`` and ``ramp_check``: eight full-scale sawtooth periods on the CDAC's SPICE draw
      (``Model.drawn``: its Monte Carlo's middle condition, the draw at the 90th percentile of what
      no calibration recovers), independent noise: the code density, INL and DNL, and the
      calibrations learned from the training ramp and checked on the other.
    - ``drawn_sine``: the nominal rate's sine on that draw: its ENOB before and after the
      calibration.
    - ``rate_<MS/s>``: a -0.5 dBFS sine near fs/8 at ten rates, 1 to 10 MS/s: ENOB and power over
      the rate.
    - ``fin_<MS/s>_<cycles>``: the sine at nine input frequencies up to Nyquist at 2, 6 and 10 MS/s.
    - ``dc_<n>``: 33 DC inputs across the full scale: the energy a conversion takes over the input.
    - ``trajectory``: 0 V at 10 MS/s, on the first decision's threshold: the redundant decision
      paths.
    - ``noise``: 50 mV at 10 MS/s: the output-code noise spectrum (the behavioral model repeats it
      with one noise source at a time).
    - ``noise_input``: nine DC inputs evenly over +-90 % of the full scale at 10 MS/s, 512
      conversions each, in one staircase: the output-code noise over the input
      (``analyze_input_noise``).
    - ``hsu_r<rate>``: every ideal code centre once (a ramp of one LSB a conversion), at each rate
      of ``RATES_HZ`` with the array's own settling, noiseless but with the comparator's delay (a
      late decision holds the last bit); and ``hsu_reference_r<rate>``, the same inputs at each rate
      with ideal settling and an ideal comparator: the integrated error of each against its rate's
      reference (``analyze_hsu``) over the rate shows how fast the instance converts before the time
      a decision has costs codes, after A. H. T. Chang's thesis (MIT 2013, pp. 77-84): redundancy
      recovers settling errors, not a late comparator's. The rate is all a fabricated converter lets
      one vary, so the study keeps to it. The reference at the same rate takes off what every array
      shares there (the ramp's input moves while it is sampled, more the faster the rate).
    - ``ladder_<step>``: the ``rate_10`` sine with the behavioral model's impairments added one at a
      time (``LADDER``), from quantization alone (a perfect track-and-hold, no noise, ideal settling
      and an ideal comparator, decoded as ``rate_10`` is) to the converter as ``rate_10`` has it,
      whose capture is the last step's (``LADDER_NAMES``): what each impairment costs in ENOB where
      it is added (errors add in power, so a source costs fewer bits after larger ones: the order
      matters).
    - ``mc_<A_C %>_<draw>``, only where ``mismatch_draws`` asks for them (the figures predict the
      mismatch from the capacitances, ``flow.adc.analysis.analyze_mismatch``; the draws check it):
      noise-free ramps (four periods, 16 hits a code at 12 bits, at least 8 at any), at each Pelgrom
      coefficient from 0.05 to 0.85 %·sqrt(fF) (a SPICE run draws them with the PDK's Monte Carlo).
    """

    amplitude_v = full_scale_v * 10 ** (-0.5 / 20)
    # a sawtooth slightly past the full scale, eight periods in the ramp; at least 64 hits a code
    # (14 bits double the ramp: calibration 3 fits its thresholds from the late branches' hits)
    ramp_conversions = max(RAMP_CONVERSIONS, 64 << bits)
    period_s = ramp_conversions / 8 / NOMINAL_RATE_HZ
    edge_v = 1.05 * full_scale_v
    ramp = h.Vpwl.Params(wave=f"0 {-edge_v:.6g} {period_s:.6g} {edge_v:.6g}")
    captures = {
        role: Capture(
            tb(conversions=ramp_conversions, rate_hz=NOMINAL_RATE_HZ, vin_diff=ramp),
            seed=1,
            noise_seed=noise_seed,
            drawn=True,
        )
        for role, noise_seed in (("ramp_train", 1), ("ramp_check", 1001))
    }

    for rate in RATES_HZ:
        captures[f"rate_{rate / 1e6:g}"] = Capture(
            tb(conversions=SINE_CONVERSIONS, rate_hz=rate, vin_diff=_sine(amplitude_v, rate, 1021))
        )
    # the ladder's steps but the last, which is the nominal rate's sine itself: its testbench and
    # seeds, fewer impairments
    nominal = captures[LADDER_NAMES[-1]]
    # the nominal rate's sine on the draw the ramps calibrate on
    captures["drawn_sine"] = replace(nominal, drawn=True)
    for step, (_, _, quiet, tau_scale) in enumerate(LADDER[:-1]):
        captures[f"ladder_{step}"] = replace(nominal, quiet=quiet, tau_scale=tau_scale)
    for rate in FIN_RATES_HZ:
        for cycles in FIN_CYCLES:
            captures[f"fin_{rate / 1e6:g}_{cycles}"] = Capture(
                tb(conversions=SINE_CONVERSIONS, rate_hz=rate, vin_diff=_sine(amplitude_v, rate, cycles))
            )
    for index, vin_v in enumerate(np.linspace(-full_scale_v, full_scale_v, 33)):
        captures[f"dc_{index:02d}"] = Capture(
            tb(conversions=2_000, rate_hz=NOMINAL_RATE_HZ, vin_diff=h.Vdc.Params(dc=round(float(vin_v), 6)))
        )
    captures["trajectory"] = Capture(tb(conversions=2_000, rate_hz=NOMINAL_RATE_HZ, vin_diff=h.Vdc.Params(dc=0.0)))
    captures["noise"] = Capture(tb(conversions=100_000, rate_hz=NOMINAL_RATE_HZ, vin_diff=h.Vdc.Params(dc=0.05)))
    captures["noise_input"] = Capture(
        tb(
            conversions=INPUT_NOISE_LEVELS * INPUT_NOISE_CONVERSIONS,
            rate_hz=NOMINAL_RATE_HZ,
            vin_diff=_staircase(INPUT_NOISE_SPAN * full_scale_v, 2 * full_scale_v / (1 << bits)),
        ),
        noise_seed=2001,
    )
    for rate_index, rate in enumerate(RATES_HZ):
        captures[f"hsu_r{rate_index}"] = Capture(
            tb(conversions=(1 << bits) + 1, rate_hz=rate, vin_diff=_code_ramp(full_scale_v, bits, rate)),
            quiet=HSU_QUIET,
        )
        captures[f"hsu_reference_r{rate_index}"] = Capture(
            tb(conversions=(1 << bits) + 1, rate_hz=rate, vin_diff=_code_ramp(full_scale_v, bits, rate)),
            quiet=HSU_REFERENCE_QUIET,
            tau_scale=0.0,
        )
    # at least 8 hits a code over the four periods (14 bits double the ramp)
    mismatch_conversions = max(MISMATCH_CONVERSIONS, 8 << bits)
    mismatch_period_s = mismatch_conversions / 4 / NOMINAL_RATE_HZ
    mismatch_ramp = h.Vpwl.Params(wave=f"0 {-edge_v:.6g} {mismatch_period_s:.6g} {edge_v:.6g}")
    mismatch_tb = tb(conversions=mismatch_conversions, rate_hz=NOMINAL_RATE_HZ, vin_diff=mismatch_ramp)
    for coefficient in MISMATCH_COEFFICIENTS:
        for draw in range(mismatch_draws):
            captures[f"mc_{coefficient * 100:g}_{draw:02d}"] = Capture(
                mismatch_tb, seed=100 + draw, unit_mismatch=coefficient, noise_free=True
            )
    return captures


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


GENERATOR = AdcBlocks
# a converter is characterized in Python alone (the behavioral model on its blocks' records, no
# circuit compiled), so a worker process runs this many as one task
tasks_per_worker = 10


def cost(pdk: str, params: Params) -> float:
    """An instance's relative run time, for the runner's longest-first order: its conversions grow
    with the codes, each conversion with its decisions."""
    return 2.0**params.adc_bits * (params.cdac.n_dac + params.cdac.n_extra + 1)


def record(captures: dict[str, MeasAdc]) -> Record:
    """The record of an instance's campaign (``campaign``) from its captures by name, ``MeasAdc``
    alone, so a SPICE campaign and the behavioral model's take the same path: the metrics
    (``analysis.metrics``) and the figures (``flow.adc.plots``, the viewer's details, in its order).
    Every capture is decoded with the design weights and with the "extracted" weights of its
    ``cap_table`` readback (a PEX table, or the behavioral model's extraction, ``_extracted``); the
    calibrations learn from the training ramp and are checked on the other, and the one that grades
    the check ramp best decodes the calibrated figures and metrics (calibration 3 keeps the design
    weights where its validation finds no measured weight that helps). Capacitor mismatch is
    predicted rather than drawn (``analyze_mismatch``, from the nominal array's capacitances); where
    the campaign also holds the Monte Carlo ramps that check it (``mc_*``,
    ``campaign(mismatch_draws=...)``), their 95th percentiles at Harpe's matching are reported
    beside the predictions. ``noise_sampling`` and ``noise_comparator`` (the noise capture with one
    source) add each source's rms noise where present, the ``ladder_*`` captures the ENOB ladder,
    ``drawn_sine`` the ENOB on the CDAC's SPICE draw."""

    check, train = captures["ramp_check"], captures["ramp_train"]
    extracted = _extracted(check)
    design = analyze_ramp(check)
    extracted_ramp = analyze_ramp(check, calibration=extracted)
    rates = sorted((m for n, m in captures.items() if n.startswith("rate_")), key=lambda m: float(m.tb.symbol_rate))
    dynamics = [analyze_dynamic(m, calibration=_extracted(m)) for m in rates]
    powers = [analyze_power(m) for m in rates]
    fins = [analyze_dynamic(m, calibration=_extracted(m)) for n, m in captures.items() if n.startswith("fin_")]
    at_nominal = sorted(
        (d for d in fins if round(d.sample_rate_hz) == round(NOMINAL_RATE_HZ)), key=lambda d: d.input_frequency_hz
    )
    dcs = [m for n, m in sorted(captures.items()) if n.startswith("dc_")]
    train_ramp = analyze_ramp(train)
    learned: dict[str, AnalysisCalibration] = {"Calibration 2": analyze_calibration2(train, ramp=train_ramp)}
    # calibration 3 fits a threshold in every late branch, and a ramp can hold too few hits there to
    # bracket one; then it is left out (``calibration3_fitted`` says so) rather than failing the rest
    calibration3 = None
    try:
        calibration3 = learned["Calibration 3"] = analyze_calibration3(train, ramp=train_ramp)
    except ValueError:
        pass
    decoded = {label: analyze_ramp(check, calibration=calibration) for label, calibration in learned.items()}
    best = min(learned, key=lambda label: decoded[label].maximum_abs_inl)
    calibrated = decoded[best]
    redundancy = analyze_redundancy(extracted)
    paths = analyze_decision_paths(captures["trajectory"])
    noise = captures["noise"]
    spectrum = analyze_code_spectrum(noise, calibration=_extracted(noise))
    input_noise = analyze_input_noise([captures["noise_input"]])
    if len(input_noise.level_v) != INPUT_NOISE_LEVELS:
        raise ValueError(f"noise_input holds {len(input_noise.level_v)} input levels, not {INPUT_NOISE_LEVELS}")
    hsu = analyze_hsu(
        [captures[f"hsu_{kind}r{index}"] for kind in ("", "reference_") for index in range(len(RATES_HZ))]
    )
    energy = analyze_energy(dcs, power=[analyze_power(m) for m in dcs])
    ladder = _ladder(captures)
    # the mismatch, predicted from the nominal array (a capture without a draw)
    mismatch = analyze_mismatch(noise)
    prediction = analyze_mismatch_prediction(mismatch)
    details = [
        plot_redundancy(redundancy),
        plot_code_density(design),
        plot_inl(design),
        plot_inl_calibrated(calibrated),
        plot_dnl(design),
        plot_dnl_calibrated(calibrated),
        plot_trajectory(paths),
        plot_trajectory_final(paths),
        plot_trajectory_codes(paths),
        plot_noise_spectrum(spectrum),
        plot_noise_input(input_noise),
        plot_enob_rate(dynamics),
        plot_enob_fin(at_nominal),
        *([plot_enob_ladder(ladder)] if ladder is not None else []),
        plot_spectrum_low(at_nominal[0]),
        plot_spectrum_nyquist(at_nominal[-1]),
        plot_hsu_rate(hsu),
        plot_power_rate(powers),
        plot_energy_input(energy),
        plot_energy_dac_input(energy),
        plot_calibration_weights(extracted),
        plot_mismatch_weight_sigma(prediction),
        plot_mismatch_transition_sigma(prediction),
        plot_mismatch_margin(prediction),
        plot_mismatch_dnl(prediction),
        plot_mismatch_inl(prediction),
    ]
    drawn = {}
    if "drawn_sine" in captures:
        sine = captures["drawn_sine"]
        drawn = {
            "drawn_design": analyze_dynamic(sine),
            "drawn_extracted": analyze_dynamic(sine, calibration=_extracted(sine)),
            "drawn_calibrated": analyze_dynamic(sine, calibration=learned[best]),
        }
    draws = [m for n, m in sorted(captures.items()) if n.startswith("mc_")]
    numbers = metrics(
        dynamics=dynamics,
        powers=powers,
        fins=at_nominal,
        ramp=design,
        extracted=extracted_ramp,
        calibrated=calibrated,
        noise=analyze_noise_rms(noise),
        input_noise=input_noise,
        hsu=hsu,
        redundancy=redundancy,
        mismatch=mismatch,
        noise_sampling=analyze_noise_rms(captures["noise_sampling"]) if "noise_sampling" in captures else None,
        noise_comparator=analyze_noise_rms(captures["noise_comparator"]) if "noise_comparator" in captures else None,
        calibration3=calibration3,
        ladder=ladder,
        draws=analyze_mismatch_draws(draws, ramps=[analyze_ramp(m) for m in draws]) if draws else None,
        **drawn,
    )
    return Record(metrics=numbers, details=details)


def _extracted(measurement: MeasAdc) -> AnalysisCalibration:
    """A capture's "extracted" weights: the extraction its ``cap_table`` readback names (a PEX table,
    or the behavioral model's extraction)."""
    return read_extracted_calibration(Path(str(measurement.info.readbacks["cap_table"])), measurement)


def _ladder(captures: dict[str, MeasAdc]) -> AnalysisLadder | None:
    """The ENOB ladder (``LADDER``) of a campaign's captures, each step decoded as ``enob_bits`` is
    (the extracted weights, unrounded); None where the campaign has no ladder (a SPICE one)."""
    if not all(name in captures for name in LADDER_NAMES):
        return None
    return analyze_ladder(
        [analyze_dynamic(captures[name], calibration=_extracted(captures[name])) for name in LADDER_NAMES]
    )


def characterize(run_dir: Path, pdk: str, params: Params) -> Record:
    """The campaign's captures, converted and kept in memory, and their record (``record``), with
    the reference's requirements the converter sets (``Model.reference_requirements``, apart from
    its own ENOB: its metrics ``ref_*`` and its figures) and the model's own metrics: the viewer
    shows the figures (the record's details) and no waveform of an ADC instance, so no capture is
    written (a run is its ``instance.json``)."""
    from .model import Model

    model = Model.of(pdk, params)
    plan = campaign(model.tb, model.full_scale_v, params.adc_bits)
    captures = {}
    for name, capture in plan.items():
        captures[name] = model.capture(
            capture.tb,
            None,
            seed=capture.seed,
            noise_seed=capture.noise_seed,
            unit_mismatch=capture.unit_mismatch,
            quiet=("sampling", "comparator") if capture.noise_free else capture.quiet,
            tau_scale=capture.tau_scale,
            drawn=capture.drawn,
        )
    # the behavioral model alone can keep one noise source at a time
    for name, quiet in (("noise_sampling", ("comparator",)), ("noise_comparator", ("sampling",))):
        captures[name] = model.capture(plan["noise"].tb, None, quiet=quiet)
    recorded = record(captures)
    # the reference buffer's requirements this converter sets, apart from its own ENOB
    reference = model.reference_requirements(plan[LADDER_NAMES[-1]])
    numbers = recorded.metrics | {
        "ref_decap_f": reference.decap_f,
        "ref_r_max_ohm": reference.r_max_ohm,
        "ref_noise_max_v": reference.noise_max_v,
        "ref_enob_loss_max_bits": reference.enob_loss_max_bits,
        "stages": float(model.stages),  # the switched capacitors a side
        "decisions": float(model.stages + 1),  # a conversion's comparator decisions
        "full_scale_v": model.full_scale_v,
        "settling_tau_s": model.settling_tau_s,
        "comp_noise_v": model.comp.noise_v,
        "comp_delay_s": model.comp.delay_s,
        **model.metastability(),
    }
    details = [*recorded.details, plot_reference_noise(reference)]
    # the driver's resistance only where the reference node has decoupling to restore
    if reference.decap_f > 0:
        details.append(plot_reference_r_out(reference))
    return Record(metrics=numbers, details=details)


# The named Spectre runs (``python -m flow adc.<name>``, ``flow.adc.targets``): each a set of
# testbenches of the generated or an extracted converter, simulated side by side in fresh processes
# (``sim.simulate``), each measurement written beside its run


def hdl21_sample_rate(run_dir: Path, *, check: bool = False) -> Path:
    """Run the generated ADC at 2, 6, and 10 MS/s with 50 mV input."""

    from flow.analysis.io import write_measurement
    from flow.circuit.results import convert_raw_adc_to_measurement, read_raw_transient

    with ProcessPoolExecutor(max_workers=3, mp_context=get_context("spawn")) as executor:
        futures = []
        for rate, symbol_rate in ((2, 0.32 * G), (6, 0.96 * G), (10, 1.6 * G)):
            params = TbParams(
                view="hdl21gen",
                symbol_rate=symbol_rate,
                conversions=1 if check else 100,
                vin_diff=h.Vdc.Params(dc=0.05),
                **symbol256_init8_samp16_comp11110000_logic11000011.as_tb_fields(),
            )
            futures.append(
                (
                    executor.submit(
                        simulate,
                        params,
                        run_dir / f"{float(symbol_rate) / 1e6:g}mbd",
                        noise=True,
                        check=check,
                    ),
                    params,
                )
            )
        for future, params in futures:
            raw_path, signal_names = future.result()
            if not check:
                measurement = convert_raw_adc_to_measurement(
                    read_raw_transient(raw_path),
                    params=params,
                    raw_path=raw_path,
                    signal_names=signal_names,
                )
                write_measurement(raw_path.parent / "result.h5", measurement)
    return run_dir


def hdl21_transfer_curve(run_dir: Path, *, check: bool = False) -> Path:
    """Run the generated ADC from -750 mV to +750 mV in 10 mV steps."""

    from flow.analysis.io import write_measurement
    from flow.circuit.results import convert_raw_adc_to_measurement, read_raw_transient

    params = TbParams(
        view="hdl21gen",
        symbol_rate=1.6 * G,
        conversions=151,
        vin_diff=hs.LinearSweep(start=-0.75, stop=0.75, step=0.01),
        **symbol256_init8_samp16_comp11110000_logic11000011.as_tb_fields(),
    )
    raw_path, signal_names = simulate(
        params,
        run_dir,
        check=check,
    )
    if not check:
        measurement = convert_raw_adc_to_measurement(
            read_raw_transient(raw_path),
            params=params,
            raw_path=raw_path,
            signal_names=signal_names,
        )
        write_measurement(run_dir / "result.h5", measurement)
    return run_dir


def frida1_sequence(run_dir: Path, *, check: bool = False) -> Path:
    """Compare seven continuous timing recipes on four historical flavors."""

    from flow.analysis.io import write_measurement
    from flow.circuit.results import convert_raw_adc_to_measurement, read_raw_transient

    root = Path(__file__).resolve().parents[2] / "build/layout/adc"
    with ProcessPoolExecutor(max_workers=4, mp_context=get_context("spawn")) as executor:
        futures = []
        for layers in (1, 2):
            for (radix, cdac), timing in product(
                (
                    (17, CapArrayConfig()),
                    (20, CapArrayConfig(weights=(768, 512, 320, 192, 128, 64, 64, 64, 64, 64, 32, 16, 8, 4, 2, 1))),
                ),
                # COMP      LOGIC at fall  LOGIC +1 symbol
                # 11110000  00001111       10000111
                # 11111000  10000111       11000011
                # 11111100  11000011       11100001
                # 11111110  11100001       (excluded)
                (
                    "symbol160_init4_samp20_comp11110000_logic00001111",
                    "symbol160_init4_samp20_comp11110000_logic10000111",
                    "symbol160_init4_samp20_comp11111000_logic10000111",
                    "symbol160_init4_samp20_comp11111000_logic11000011",
                    "symbol160_init4_samp20_comp11111100_logic11000011",
                    "symbol160_init4_samp20_comp11111100_logic11100001",
                    "symbol160_init4_samp20_comp11111110_logic11100001",
                ),
            ):
                target = f"frida1_{layers}layer_radix{radix}"
                pex = root / target / "20260905_171235" / f"{target}.pex.netlist"
                params = TbParams(
                    view="frida1",
                    pex_cell="adc_12b_17step",
                    dut=Params(adc_bits=12, cdac=cdac),
                    symbol_rate=1.6 * G,
                    conversions=1 if check else 100,
                    vin_diff=h.Vdc.Params(dc=0.05),
                    **dict(SEQUENCES)[timing].as_tb_fields(),
                )
                futures.append(
                    (
                        executor.submit(
                            simulate,
                            params,
                            run_dir / target / timing,
                            pex_netlist=pex,
                            noise=True,
                            check=check,
                            expected_disconnect=layers == 2,
                        ),
                        params,
                    )
                )
        for future, params in futures:
            raw_path, signal_names = future.result()
            if not check:
                measurement = convert_raw_adc_to_measurement(
                    read_raw_transient(raw_path),
                    params=params,
                    raw_path=raw_path,
                    signal_names=signal_names,
                )
                write_measurement(raw_path.parent / "result.h5", measurement)
    return run_dir


def frida1_sample_rate(run_dir: Path, *, check: bool = False) -> Path:
    """Run the four original PEX flavors at 2, 6, and 10 MS/s."""

    from flow.analysis.io import write_measurement
    from flow.circuit.results import convert_raw_adc_to_measurement, read_raw_transient
    from pdk.tsmc65.hdl21 import site

    with ProcessPoolExecutor(max_workers=4, mp_context=get_context("spawn")) as executor:
        futures = []
        for layers in (1, 2):
            for radix, cdac in (
                (17, CapArrayConfig()),
                (20, CapArrayConfig(weights=(768, 512, 320, 192, 128, 64, 64, 64, 64, 64, 32, 16, 8, 4, 2, 1))),
            ):
                cell = f"adc_{layers}layer_radix{radix}"
                pex = (
                    site.ADC_PEX_NETLIST
                    if cell == "adc_1layer_radix17"
                    else site.ADC_PEX_NETLIST.parent / cell / f"{cell}.pex.netlist"
                )
                for rate, symbol_rate in ((2, 0.32 * G), (6, 0.96 * G), (10, 1.6 * G)):
                    params = TbParams(
                        view="frida1",
                        pex_cell=cell,
                        dut=Params(adc_bits=12, cdac=cdac),
                        symbol_rate=symbol_rate,
                        conversions=1 if check else 100,
                        vin_diff=h.Vdc.Params(dc=0.05),
                        **symbol256_init8_samp16_comp11110000_logic11000011.as_tb_fields(),
                    )
                    futures.append(
                        (
                            executor.submit(
                                simulate,
                                params,
                                run_dir / cell / f"{float(symbol_rate) / 1e6:g}mbd",
                                pex_netlist=pex,
                                noise=True,
                                check=check,
                            ),
                            params,
                        )
                    )
        for future, params in futures:
            raw_path, signal_names = future.result()
            if not check:
                measurement = convert_raw_adc_to_measurement(
                    read_raw_transient(raw_path),
                    params=params,
                    raw_path=raw_path,
                    signal_names=signal_names,
                )
                write_measurement(raw_path.parent / "result.h5", measurement)
    return run_dir


def frida1_transfer_curve(run_dir: Path, *, check: bool = False) -> Path:
    """Run the original extracted ADC from -750 mV to +750 mV in 10 mV steps."""

    from flow.analysis.io import write_measurement
    from flow.circuit.results import convert_raw_adc_to_measurement, read_raw_transient
    from pdk.tsmc65.hdl21 import site

    params = TbParams(
        view="frida1",
        symbol_rate=1.6 * G,
        conversions=151,
        vin_diff=hs.LinearSweep(start=-0.75, stop=0.75, step=0.01),
        **symbol256_init8_samp16_comp11110000_logic11000011.as_tb_fields(),
    )
    raw_path, signal_names = simulate(
        params,
        run_dir,
        pex_netlist=site.ADC_PEX_NETLIST,
        check=check,
    )
    if not check:
        measurement = convert_raw_adc_to_measurement(
            read_raw_transient(raw_path),
            params=params,
            raw_path=raw_path,
            signal_names=signal_names,
        )
        write_measurement(run_dir / "result.h5", measurement)
    return run_dir


def frida1_supply_noise(run_dir: Path, *, check: bool = False) -> Path:
    """Run the 15 original extracted-ADC rate/supply-noise combinations."""

    from flow.analysis.io import write_measurement
    from flow.circuit.results import convert_raw_adc_to_measurement, read_raw_transient
    from pdk.tsmc65.hdl21 import site

    noise_rms_v = 1e-3
    with ProcessPoolExecutor(max_workers=4, mp_context=get_context("spawn")) as executor:
        futures = []
        for rate, symbol_rate in ((2, 0.32 * G), (6, 0.96 * G), (10, 1.6 * G)):
            for name, rail_noise in (
                ("none", (0.0, 0.0, 0.0)),
                ("vdda", (noise_rms_v, 0.0, 0.0)),
                ("vddd", (0.0, noise_rms_v, 0.0)),
                ("vddac", (0.0, 0.0, noise_rms_v)),
                ("all", (noise_rms_v, noise_rms_v, noise_rms_v)),
            ):
                params = TbParams(
                    view="frida1",
                    symbol_rate=symbol_rate,
                    conversions=1 if check else 100,
                    vin_diff=h.Vdc.Params(dc=0.05),
                    **symbol256_init8_samp16_comp11110000_logic11000011.as_tb_fields(),
                    supply_series_resistance_ohm=1.0,
                    supply_series_inductance_h=1e-9,
                    supply_decoupling_capacitance_f=1e-12,
                    supply_noise_rms_v=rail_noise,
                    supply_noise_bandwidth_hz=25e9,
                )
                futures.append(
                    (
                        executor.submit(
                            simulate,
                            params,
                            run_dir / f"{float(symbol_rate) / 1e6:g}mbd_{name}",
                            pex_netlist=site.ADC_PEX_NETLIST,
                            check=check,
                        ),
                        params,
                    )
                )
        for future, params in futures:
            raw_path, signal_names = future.result()
            if not check:
                measurement = convert_raw_adc_to_measurement(
                    read_raw_transient(raw_path),
                    params=params,
                    raw_path=raw_path,
                    signal_names=signal_names,
                )
                write_measurement(raw_path.parent / "result.h5", measurement)
    return run_dir


def frida2_sequence(run_dir: Path, *, check: bool = False) -> Path:
    """Compare named continuous timing recipes on three radix-17 stacks."""

    from flow.analysis.io import write_measurement
    from flow.circuit.results import convert_raw_adc_to_measurement, read_raw_transient

    root = Path(__file__).resolve().parents[2] / "build/layout/adc"
    with ProcessPoolExecutor(max_workers=3, mp_context=get_context("spawn")) as executor:
        futures = []
        for (layers, stamp), timing in product(
            ((1, "20260905_193440"), (2, "20260905_193629"), (3, "20260905_193816")),
            # COMP      LOGIC at fall  LOGIC +1 symbol
            # 11110000  00001111       10000111
            # 11111000  10000111       11000011
            # 11111100  11000011       11100001
            # 11111110  11100001       (excluded)
            (
                "symbol160_init4_samp20_comp11110000_logic00001111",
                "symbol160_init4_samp20_comp11110000_logic10000111",
                "symbol160_init4_samp20_comp11111000_logic10000111",
                "symbol160_init4_samp20_comp11111000_logic11000011",
                "symbol160_init4_samp20_comp11111100_logic11000011",
                "symbol160_init4_samp20_comp11111100_logic11100001",
                "symbol160_init4_samp20_comp11111110_logic11100001",
            ),
        ):
            target = f"frida2_{layers}layer_radix17"
            params = TbParams(
                view="frida2",
                pex_cell="adc_12b_17step",
                dut=Params(adc_bits=12, cdac=CapArrayConfig()),
                symbol_rate=1.6 * G,
                conversions=1 if check else 100,
                vin_diff=h.Vdc.Params(dc=0.05),
                **dict(SEQUENCES)[timing].as_tb_fields(),
            )
            futures.append(
                (
                    executor.submit(
                        simulate,
                        params,
                        run_dir / target / timing,
                        pex_netlist=root / target / stamp / f"{target}.pex.netlist",
                        noise=True,
                        check=check,
                    ),
                    params,
                )
            )
        for future, params in futures:
            raw_path, signal_names = future.result()
            if not check:
                measurement = convert_raw_adc_to_measurement(
                    read_raw_transient(raw_path),
                    params=params,
                    raw_path=raw_path,
                    signal_names=signal_names,
                )
                write_measurement(raw_path.parent / "result.h5", measurement)
    return run_dir
