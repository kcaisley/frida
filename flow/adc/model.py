"""The ADC's behavioral model: its converter (``Model``, the behavioral converter of
``flow.adc.sim``: its blocks' models, each built from the same parameters its netlist generator
takes, switched by its SAR loop) with the reference buffer's requirements it sets.

    model = Model.of("tsmc65", Params(adc_bits=12, cdac=..., samp=..., comp=...))
    tb = model.tb(conversions=8192, rate_hz=10e6, vin_diff=h.Vsin.Params(...))
    model.capture(tb, path)  # a MeasAdc, as a behavioral run writes one (flow.adc.sim.simulate)

The reference buffer's requirements a converter sets (``Model.reference_requirements``): the
largest output resistance and noise of the buffer driving its DAC's reference (VDD_DAC) for which
the error the reference adds stays within the converter's quantization noise. They are the
converter's metrics ``ref_*``, so the reference buffer is specified by the converter it serves, and
not part of the converter's ENOB (its front end's, on an ideal reference).

- The decoupling the reference node has: decap cells over ``DECAP_COVERAGE`` of the converter's
  footprint (taken as its DAC's two sides', each side's layout with its drivers), the supplies
  shared, at the PDK's decap density (``DECAP_FF_PER_UM2`` in its ``pdk_logic``), rounded to one
  significant figure (``ref_decap_f``).
- Kickback: each switch draws its charge from that capacitance and the buffer restores it through
  its output resistance, so the dip left at the next comparison is a code-dependent error: the
  largest output resistance the converter tolerates (``ref_r_max_ohm``), and the ENOB it loses over
  the resistance (figure ``reference_r_out``).
- Noise: the largest white noise at the node, RMS at each decision (``ref_noise_max_v``), and the
  ENOB lost over it (figure ``reference_noise``).

The two add in power, and each may add ``REFERENCE_SHARE`` of an ideal quantizer's noise power
(LSB^2 / 12) of the converter's resolution, so a buffer meeting both adds no more than the
quantization noise: each may cost ``ref_enob_loss_max_bits``. Each requirement is the largest value
on its grid within that loss, refined by bisection on a log scale to the next grid point that is
not. Every point converts the sine at the nominal rate with that capture's seeds, so only the
reference moves, on the converter with an ideal sampler and comparator (``REFERENCE_QUIET``): its
DAC alone, whose settling takes the time and the redundancy the reference's error competes for. An
error the size of the quantization noise cannot be told from one capture of a converter whose own
error is many times it, and the comparator does not see the reference.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import replace

import numpy as np

from flow.adc.analysis import analyze_dynamic
from flow.adc.params import (
    REFERENCE_HALVINGS,
    REFERENCE_NOISE_V,
    REFERENCE_QUIET,
    REFERENCE_R_OUT_OHM,
    REFERENCE_SHARE,
    TbParams,
)
from flow.adc.sim import _Converter
from flow.adc.types import AnalysisReference
from flow.analysis.types import MeasAdc


class Model(_Converter):
    """A SAR ADC's blocks, as their characterizations measured them (``flow.adc.sim``'s behavioral
    converter), and the reference's requirements they set."""

    def reference_requirements(self, tb: TbParams) -> AnalysisReference:
        """The reference's requirements for this converter at the run ``tb`` (the nominal rate's
        sine), and the ENOB it loses over each: ``tb`` with ``REFERENCE_QUIET``, its own draw, on
        each reference (``TbParams.reference_*``; none, ideal)."""

        base = replace(tb, quiet=REFERENCE_QUIET, drawn=False)

        def enob(reference: dict[str, float]) -> float:
            return _enob(self.capture(replace(base, **reference), None))

        enob_bits = enob({})
        budget_bits = enob_bits - _enob_floor(self.params.adc_bits, enob_bits, REFERENCE_SHARE)

        def loss(reference: dict[str, float]) -> float:
            return enob_bits - enob(reference)

        def tolerated(make: Callable[[float], dict[str, float]], grid: np.ndarray) -> tuple[list[float], float]:
            # the loss at each grid point, and the largest value within the budget: below the first
            # point over it, bisected towards it; the grid's last where none is, NaN where the first is
            losses = [loss(make(value)) for value in grid]
            over = np.flatnonzero(np.asarray(losses) > budget_bits)
            if not over.size:
                return losses, float(grid[-1])
            if over[0] == 0:
                return losses, math.nan
            low, high = float(grid[over[0] - 1]), float(grid[over[0]])
            for _ in range(REFERENCE_HALVINGS):
                middle = math.sqrt(low * high)
                low, high = (middle, high) if loss(make(middle)) <= budget_bits else (low, middle)
            return losses, low

        decap_f = self.decoupling_f
        noise_losses, noise_max_v = tolerated(lambda noise_v: {"reference_noise_v": noise_v}, REFERENCE_NOISE_V)
        # the driver's resistance only where the node has decoupling to restore
        r_out_ohm, r_losses, r_max_ohm = np.zeros(0), [], math.nan
        if decap_f > 0:
            r_out_ohm = REFERENCE_R_OUT_OHM
            r_losses, r_max_ohm = tolerated(
                lambda r_ohm: {"reference_r_ohm": r_ohm, "reference_c_f": decap_f}, REFERENCE_R_OUT_OHM
            )
        return AnalysisReference(
            group=None,
            index=None,
            dut=self.params,
            decap_f=decap_f,
            noise_v=REFERENCE_NOISE_V,
            noise_loss_bits=np.asarray(noise_losses, dtype=np.float64),
            r_out_ohm=r_out_ohm,
            r_out_loss_bits=np.asarray(r_losses, dtype=np.float64),
            noise_max_v=noise_max_v,
            r_max_ohm=r_max_ohm,
            enob_loss_max_bits=budget_bits,
        )


def _enob(measurement: MeasAdc) -> float:
    """A sine capture's spectral ENOB referred to full scale, decoded as the record's ``enob_bits``
    is (the extracted weights of its ``cap_table`` readback, unrounded)."""
    from flow.adc.sweep import _extracted  # in here: sweep imports this module

    return analyze_dynamic(measurement, calibration=_extracted(measurement)).spectral_enob_fs_bits


def _enob_floor(bits: int, enob_bits: float, share: float = 1.0) -> float:
    """The ENOB a converter of ``bits`` reaches when an error of ``share`` of its quantization noise
    power (LSB^2 / 12) adds to the noise and distortion it has at ``enob_bits``."""
    return bits - 0.5 * math.log2(2.0 ** (2 * (bits - enob_bits)) + share)
