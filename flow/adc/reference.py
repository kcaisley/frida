"""The reference buffer's requirements a converter sets: the largest output resistance and noise of
the buffer driving its DAC's reference (VDD_DAC) for which the error the reference adds stays within
the converter's quantization noise. They are the converter's metrics ``ref_*``, so the reference
buffer is specified by the converter it serves, and not part of the converter's ENOB (its front
end's, on an ideal reference).

- The decoupling the reference node has: decap cells over ``DECAP_COVERAGE`` of the converter's
  footprint (taken as its two capacitor arrays'), the supplies shared, at the PDK's decap density
  (``DECAP_FF_PER_UM2`` in its ``pdk_logic``), rounded to one significant figure
  (``ref_decap_f``).
- Kickback: each switch draws its charge from that capacitance and the buffer restores it through
  its output resistance, so the dip left at the next comparison is a code-dependent error: the
  largest output resistance the converter tolerates (``ref_r_max_ohm``), and the ENOB it loses over
  the resistance (figure ``reference_r_out``).
- Noise: the largest white noise at the node, RMS at each decision (``ref_noise_max_v``), and the
  ENOB lost over it (figure ``reference_noise``).

The two add in power, and each may add ``SHARE`` of an ideal quantizer's noise power (LSB^2 / 12) of
the converter's resolution, so a buffer meeting both adds no more than the quantization noise: each
may cost ``ref_enob_loss_max_bits``. Each requirement is the largest value on its grid within that
loss, refined by bisection on a log scale to the next grid point that is not. Every point converts
the sine at the nominal rate with that capture's seeds, so only the reference moves, on the
converter with an ideal sampler and comparator (``QUIET``): its DAC alone, whose settling takes the
time and the redundancy the reference's error competes for. An error the size of the quantization
noise cannot be told from one capture of a converter whose own error is many times it, and the
comparator does not see the reference.
"""

from __future__ import annotations

import importlib
import math
from collections.abc import Callable

import numpy as np

from flow.pipeline import Plot

from .campaign import Capture
from .figures import FIGURES, dynamic_enob
from .model import IDEAL_REFERENCE, AdcModel, Reference

# the share of the converter's footprint its layout fills with decap cells (front-end-of-line area
# under the routing)
DECAP_COVERAGE = 0.30
# the share of the quantization noise power each of the two may add (together all of it)
SHARE = 0.5
# the figures' grids, two points a decade: the white noise at the node (V RMS) and the driver's
# output resistance (ohm)
NOISE_V = np.logspace(-6, -2, 9)
R_OUT_OHM = np.logspace(-1, 5, 13)
# halvings of a grid step in the bisection (to about 4 % of the value)
HALVINGS = 5
# what the reference's study silences or makes ideal in the converter (``flow.adc.model.QUIET``)
QUIET = ("sampler", "sampling", "comparator")


def enob_floor(bits: int, enob_bits: float, share: float = 1.0) -> float:
    """The ENOB a converter of ``bits`` reaches when an error of ``share`` of its quantization noise
    power (LSB^2 / 12) adds to the noise and distortion it has at ``enob_bits``."""
    return bits - 0.5 * math.log2(2.0 ** (2 * (bits - enob_bits)) + share)


def decoupling_f(model: AdcModel) -> float:
    """The reference node's decoupling: decap cells over ``DECAP_COVERAGE`` of the two arrays'
    footprint at the PDK's density, to one significant figure; NaN where the PDK gives none."""
    density = getattr(importlib.import_module(f"pdk.{model.pdk}.hdl21").pdk_logic, "DECAP_FF_PER_UM2", math.nan)
    capacitance_f = DECAP_COVERAGE * 2 * model.cdac.area_um2 * density * 1e-15
    return float(f"{capacitance_f:.0e}") if capacitance_f > 0 else math.nan


def requirements(model: AdcModel, capture: Capture) -> tuple[dict[str, float], list[Plot]]:
    """The reference's requirements for ``model``'s converter at ``capture`` (the nominal rate's
    sine), and the ENOB it loses over each."""

    def enob(reference: Reference) -> float:
        measurement = model.capture(
            capture.tb,
            None,
            seed=capture.seed,
            noise_seed=capture.noise_seed,
            unit_mismatch=capture.unit_mismatch,
            quiet=QUIET,
            tau_scale=capture.tau_scale,
            reference=reference,
        )
        return dynamic_enob(measurement)

    enob_bits = enob(IDEAL_REFERENCE)
    budget_bits = enob_bits - enob_floor(model.params.adc_bits, enob_bits, SHARE)

    def loss(reference: Reference) -> float:
        return enob_bits - enob(reference)

    def tolerated(make: Callable[[float], Reference], grid: np.ndarray) -> tuple[list[float], float]:
        # the loss at each grid point, and the largest value within the budget: below the first
        # point over it, bisected towards it; the grid's last where none is, NaN where the first is
        losses = [loss(make(value)) for value in grid]
        over = np.flatnonzero(np.asarray(losses) > budget_bits)
        if not over.size:
            return losses, float(grid[-1])
        if over[0] == 0:
            return losses, math.nan
        low, high = float(grid[over[0] - 1]), float(grid[over[0]])
        for _ in range(HALVINGS):
            middle = math.sqrt(low * high)
            low, high = (middle, high) if loss(make(middle)) <= budget_bits else (low, middle)
        return losses, low

    def plot(name: str, x_label: str, x: np.ndarray, losses: list[float]) -> Plot:
        return Plot(
            name=name,
            title=FIGURES[name],
            x_label=x_label,
            y_label="ENOB loss (bits)",
            x=[float(f"{value:.6g}") for value in x],
            series={"ENOB loss": [float(f"{value:.6g}") for value in losses]},
            x_log=True,
        )

    decap_f = decoupling_f(model)
    noise_losses, noise_max_v = tolerated(lambda noise_v: Reference(noise_v=noise_v), NOISE_V)
    details = [plot("reference_noise", "Reference noise (V RMS)", NOISE_V, noise_losses)]
    r_max_ohm = math.nan
    if decap_f > 0:
        r_losses, r_max_ohm = tolerated(lambda r_ohm: Reference(r_ohm=r_ohm, c_f=decap_f), R_OUT_OHM)
        details.append(plot("reference_r_out", "Reference output resistance (Ω)", R_OUT_OHM, r_losses))
    metrics = {
        "ref_decap_f": decap_f,
        "ref_r_max_ohm": r_max_ohm,
        "ref_noise_max_v": noise_max_v,
        "ref_enob_loss_max_bits": budget_bits,
    }
    return metrics, details
