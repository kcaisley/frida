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


@dataclass(frozen=True)
class Capture:
    """One capture: its testbench, its capacitor draw (``seed``, at ``unit_mismatch``), its noise
    seed, and whether it has noise at all."""

    tb: AdcTbParams
    seed: int = 0
    noise_seed: int | None = None
    unit_mismatch: float = 0.0
    noise_free: bool = False  # no sampling or comparator noise: the capacitors' nonlinearity alone


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
