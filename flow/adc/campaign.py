"""An ADC's characterization campaign: every capture its figures need, as testbench parameters
(``AdcTbParams``) from a builder, the same for a SPICE run of ``AdcTb`` and for the behavioral
model (``flow.adc.model``), each of which turns one into a ``MeasAdc``.

- ``ramp_train`` and ``ramp_check``: eight full-scale sawtooth periods with one Harpe capacitor
  draw, independent noise: the code density, INL and DNL, and the calibrations learned from the
  training ramp and checked on the other.
- ``rate_<MS/s>``: a -0.5 dBFS sine near fs/8 at ten rates, 1 to 10 MS/s: ENOB and power
  over the rate.
- ``fin_<MS/s>_<cycles>``: the sine at nine input frequencies up to Nyquist at 2, 6 and 10 MS/s.
- ``dc_<n>``: 33 DC inputs across the full scale: the energy a conversion takes over the input.
- ``trajectory``: 0 V at 10 MS/s, on the first decision's threshold: the redundant decision paths.
- ``noise``: 50 mV at 10 MS/s: the output-code noise spectrum (the behavioral model repeats it with
  one noise source at a time).
- ``noise_input``: nine DC inputs evenly over +-90 % of the full scale at 10 MS/s, 512 conversions
  each, in one staircase: the output-code noise over the input (``input_noise``), where the DAC
  rail's noise, cancelled at mid-scale, grows toward the ends.
- ``hsu_r<rate>_t<tau>``: every ideal code centre once (a ramp of one LSB a conversion), at each
  rate of ``RATES_HZ`` with the DAC's settling time constants scaled by each of ``TAU_SCALES``,
  noiseless but with the comparator's delay (a late decision holds the last bit); and
  ``hsu_reference``, the same inputs at the slowest rate with ideal settling and an ideal
  comparator: the integrated error of each against it (``hsu_errors``) maps where the time a
  decision has, against the DAC's settling, costs codes, after A. Hsu's thesis (MIT 2013, pp.
  77-84): redundancy recovers settling errors, not a late comparator's.
- ``mc_<A_C %>_<draw>``: noise-free ramps (four periods, 16 hits a code at 12 bits, at least 8 at any), 25
  capacitor draws at each Pelgrom coefficient from 0.05 to 0.85 %·sqrt(fF): the INL and DNL to
  expect for a given capacitor matching (a SPICE run draws them with the PDK's Monte Carlo).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

import hdl21 as h
import numpy as np

from flow.adc.sim import AdcTbParams
from flow.analysis.types import MeasAdc

# 1 to 10 MS/s in 1 MS/s steps: 10 MS/s is the fastest the ADC is meant to run
RATES_HZ = tuple(rate * 1e6 for rate in range(1, 11))
FIN_RATES_HZ = (2e6, 6e6, 10e6)
# odd cycle counts in 8,192 conversions, coprime with it, from 0.4 % to 49 % of the rate
FIN_CYCLES = (31, 101, 257, 509, 1021, 1531, 2039, 3067, 4013)
SINE_CONVERSIONS = 8_192
RAMP_CONVERSIONS = 1 << 19
NOMINAL_RATE_HZ = 10e6
# Harpe's unit-length MOM mismatch (0.10 %·sqrt(fF)) for the ramps' capacitor draw
UNIT_MISMATCH = 0.0010
# the mismatch study's Pelgrom coefficients: Harpe's 0.10 % (JSSC 2018, unit-length MOM, 65 nm)
# and Tripathi and Murmann's 0.85 % (TCAS-I 2014, single-layer lateral MOM), around and between
MISMATCH_COEFFICIENTS = (0.0005, 0.0010, 0.0020, 0.0040, 0.0085)
MISMATCH_DRAWS = 25
MISMATCH_CONVERSIONS = 1 << 16
# the noise over the input: this many DC levels over +-INPUT_NOISE_SPAN of the full scale, each held
# for INPUT_NOISE_CONVERSIONS conversions
INPUT_NOISE_LEVELS = 9
INPUT_NOISE_SPAN = 0.9
INPUT_NOISE_CONVERSIONS = 512
# the Hsu study's DAC settling time constants, as multiples of the model's
TAU_SCALES = (0.5, 1.0, 2.0, 4.0, 8.0, 16.0)
# its noise switched off, the comparator's delay kept (or, for the reference, ideal)
HSU_QUIET = ("sampling", "comparator_noise", "rail")
HSU_REFERENCE_QUIET = ("sampling", "comparator", "rail")


@dataclass(frozen=True)
class Capture:
    """One capture: its testbench, its capacitor draw (``seed``, at ``unit_mismatch``), its noise
    seed, whether it has noise at all, the sources it silences otherwise (``quiet``, as
    ``AdcModel.behavioral``'s) and its DAC settling time constants' scale."""

    tb: AdcTbParams
    seed: int = 0
    noise_seed: int | None = None
    unit_mismatch: float = 0.0
    noise_free: bool = False  # no sampling, comparator or rail noise: the capacitors' nonlinearity alone
    quiet: tuple[str, ...] = ()
    tau_scale: float = 1.0


Builder = Callable[..., AdcTbParams]  # (conversions=, rate_hz=, vin_diff=) -> AdcTbParams


def campaign(tb: Builder, full_scale_v: float, bits: int = 12) -> dict[str, Capture]:
    """Every capture of the campaign, by name, for a ``bits`` ADC whose differential full scale is
    +-``full_scale_v``."""

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
            unit_mismatch=UNIT_MISMATCH,
        )
        for role, noise_seed in (("ramp_train", 1), ("ramp_check", 1001))
    }

    def sine(rate_hz: float, cycles: int) -> h.Vsin.Params:
        return h.Vsin.Params(voff=0.0, vamp=amplitude_v, freq=cycles * rate_hz / SINE_CONVERSIONS)

    for rate in RATES_HZ:
        captures[f"rate_{rate / 1e6:g}"] = Capture(
            tb(conversions=SINE_CONVERSIONS, rate_hz=rate, vin_diff=sine(rate, 1021))
        )
    for rate in FIN_RATES_HZ:
        for cycles in FIN_CYCLES:
            captures[f"fin_{rate / 1e6:g}_{cycles}"] = Capture(
                tb(conversions=SINE_CONVERSIONS, rate_hz=rate, vin_diff=sine(rate, cycles))
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
    code_ramp = _code_ramp(full_scale_v, bits)
    for rate_index, rate in enumerate(RATES_HZ):
        for tau_index, tau_scale in enumerate(TAU_SCALES):
            captures[f"hsu_r{rate_index}_t{tau_index}"] = Capture(
                tb(conversions=(1 << bits) + 1, rate_hz=rate, vin_diff=code_ramp(rate)),
                quiet=HSU_QUIET,
                tau_scale=tau_scale,
            )
    captures["hsu_reference"] = Capture(
        tb(conversions=(1 << bits) + 1, rate_hz=RATES_HZ[0], vin_diff=code_ramp(RATES_HZ[0])),
        quiet=HSU_REFERENCE_QUIET,
        tau_scale=0.0,
    )
    # at least 8 hits a code over the four periods (14 bits double the ramp)
    mismatch_conversions = max(MISMATCH_CONVERSIONS, 8 << bits)
    mismatch_period_s = mismatch_conversions / 4 / NOMINAL_RATE_HZ
    mismatch_ramp = h.Vpwl.Params(wave=f"0 {-edge_v:.6g} {mismatch_period_s:.6g} {edge_v:.6g}")
    mismatch_tb = tb(conversions=mismatch_conversions, rate_hz=NOMINAL_RATE_HZ, vin_diff=mismatch_ramp)
    for coefficient in MISMATCH_COEFFICIENTS:
        for draw in range(MISMATCH_DRAWS):
            captures[f"mc_{coefficient * 100:g}_{draw:02d}"] = Capture(
                mismatch_tb, seed=100 + draw, unit_mismatch=coefficient, noise_free=True
            )
    return captures


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


def input_noise(captures: dict[str, MeasAdc]) -> tuple[np.ndarray, np.ndarray]:
    """The ``noise_input`` capture's DC levels (V, differential) and the output code's standard
    deviation at each (LSB)."""

    capture = captures["noise_input"]
    vin_v = np.asarray(capture.vin_diff_v, dtype=np.float64)
    dout = np.asarray(capture.dout, dtype=np.float64)
    levels = np.unique(np.round(vin_v, 9))
    if len(levels) != INPUT_NOISE_LEVELS:
        raise ValueError(f"noise_input holds {len(levels)} input levels, not {INPUT_NOISE_LEVELS}")
    sigma = np.array([np.std(dout[np.isclose(vin_v, level, rtol=0.0, atol=1e-9)]) for level in levels])
    return levels, sigma


def _code_ramp(full_scale_v: float, bits: int) -> Callable[[float], h.Vpwl.Params]:
    """A ramp through every ideal code centre, (k + 0.5 - 2^(bits-1)) LSB with the LSB
    2 full_scale_v / 2^bits, one a conversion at a given rate: conversion k + 1 samples code k's
    centre. Conversion 0 is a dummy a code below: the wave repeats there, in the last half
    conversion, so its slope (which the sampler tracks) is not the ramp's."""

    lsb_v = 2 * full_scale_v / (1 << bits)
    first_v = (0.5 - (1 << (bits - 1))) * lsb_v - lsb_v  # the dummy's input, a code below code 0

    def ramp(rate_hz: float) -> h.Vpwl.Params:
        period_s = 1 / rate_hz
        top_s = ((1 << bits) + 0.5) * period_s  # half a conversion past the last
        points = (
            (0.0, first_v),
            (top_s, first_v + ((1 << bits) + 0.5) * lsb_v),
            (((1 << bits) + 1) * period_s, first_v),
        )
        return h.Vpwl.Params(wave=" ".join(f"{time:.9g} {value:.9g}" for time, value in points))

    return ramp


def hsu_errors(captures: dict[str, MeasAdc]) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """The Hsu study: its rates (Hz), its settling time constants' scales, and at each (scale,
    rate) the integrated error sum_k |code_k - reference_k| (LSB) over every code centre, the
    codes decoded with the design weights and the reference the ideal-timing capture's
    (``hsu_reference``)."""

    reference = np.asarray(captures["hsu_reference"].dout, dtype=np.int64)[1:]
    errors = np.empty((len(TAU_SCALES), len(RATES_HZ)))
    for rate_index in range(len(RATES_HZ)):
        for tau_index in range(len(TAU_SCALES)):
            codes = np.asarray(captures[f"hsu_r{rate_index}_t{tau_index}"].dout, dtype=np.int64)[1:]
            errors[tau_index, rate_index] = float(np.sum(np.abs(codes - reference)))
    return np.asarray(RATES_HZ), np.asarray(TAU_SCALES), errors
