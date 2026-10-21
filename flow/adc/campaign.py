"""An ADC's characterization campaign: every capture its figures need, as testbench parameters
(``AdcTbParams``) from a builder, the same for a SPICE run of ``AdcTb`` and for the behavioral
model (``flow.adc.model``), each of which turns one into a ``MeasAdc``.

- ``ramp_train`` and ``ramp_check``: eight full-scale sawtooth periods with one Harpe capacitor
  draw, independent noise: the code density, INL and DNL, and the calibrations learned from the
  training ramp and checked on the other.
- ``rate_<MS/s>``: a -0.5 dBFS sine near fs/8 at nine rates from 1.25 to 40 MS/s: ENOB and power
  over the rate.
- ``fin_<MS/s>_<cycles>``: the sine at nine input frequencies up to Nyquist at 2, 6 and 10 MS/s.
- ``dc_<n>``: 33 DC inputs across the full scale: the energy a conversion takes over the input.
- ``trajectory``: 0 V at 10 MS/s, on the first decision's threshold: the redundant decision paths.
- ``noise``: 50 mV at 10 MS/s: the output-code noise spectrum (the behavioral model repeats it with
  one noise source at a time).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

import hdl21 as h
import numpy as np

from flow.adc.sim import AdcTbParams

RATES_HZ = (1.25e6, 2.5e6, 5e6, 7.5e6, 10e6, 15e6, 20e6, 30e6, 40e6)
FIN_RATES_HZ = (2e6, 6e6, 10e6)
# odd cycle counts in 8,192 conversions, coprime with it, from 0.4 % to 49 % of the rate
FIN_CYCLES = (31, 101, 257, 509, 1021, 1531, 2039, 3067, 4013)
SINE_CONVERSIONS = 8_192
RAMP_CONVERSIONS = 1 << 19
NOMINAL_RATE_HZ = 10e6
# Harpe's unit-length MOM mismatch (0.10 %·sqrt(fF)) for the ramps' capacitor draw
UNIT_MISMATCH = 0.0010


@dataclass(frozen=True)
class Capture:
    """One capture: its testbench, its capacitor draw (``seed``, at ``unit_mismatch``) and its
    noise seed."""

    tb: AdcTbParams
    seed: int = 0
    noise_seed: int | None = None
    unit_mismatch: float = 0.0


Builder = Callable[..., AdcTbParams]  # (conversions=, rate_hz=, vin_diff=) -> AdcTbParams


def campaign(tb: Builder, full_scale_v: float) -> dict[str, Capture]:
    """Every capture of the campaign, by name, for an ADC whose differential full scale is
    +-``full_scale_v``."""

    amplitude_v = full_scale_v * 10 ** (-0.5 / 20)
    # a sawtooth slightly past the full scale, eight periods in the ramp
    period_s = RAMP_CONVERSIONS / 8 / NOMINAL_RATE_HZ
    edge_v = 1.05 * full_scale_v
    ramp = h.Vpwl.Params(wave=f"0 {-edge_v:.6g} {period_s:.6g} {edge_v:.6g}")
    captures = {
        role: Capture(
            tb(conversions=RAMP_CONVERSIONS, rate_hz=NOMINAL_RATE_HZ, vin_diff=ramp),
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
    return captures
