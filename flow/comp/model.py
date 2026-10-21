"""The comparator's behavioral model: the decision a SAR loop sees, from the characterization of
the same ``CompParams`` in the PDK (``flow.comp.sweep``, looked up by ``flow.sweep.lookup``).

    model = CompModel.of("tsmc65", CompParams(...))
    bits = model.decide(vin_diff_v, rng, vin_cm_v=0.7)

The characterization gives the input-referred noise and the systematic offset at the nominal
common mode (13/24 of the supply), the clock-to-decision delay and the supply energy per decision
at 0.5 mV, the slowest response. A comparator whose S-curve did not resolve (too slow for the
characterization's 7 ns a decision) has no noise and no model.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from flow.adc.behavioral import CompBehavioralParams, comp
from flow.sweep.lookup import characterized

from .subckt import CompParams


@dataclass(frozen=True)
class CompModel:
    """A comparator as its characterization measured it."""

    pdk: str
    params: CompParams
    noise_v: float  # input-referred RMS noise
    offset_v: float  # systematic only: the characterization has no mismatch
    delay_s: float  # clock to decision at 0.5 mV
    energy_j: float  # supply energy per decision at 0.5 mV

    @classmethod
    def of(cls, pdk: str, params: CompParams, *, simulate: bool = True) -> CompModel:
        metrics = characterized("comp", pdk, params, simulate=simulate)["metrics"]
        noise = metrics.get("noise_v")
        if noise is None or not math.isfinite(noise):
            raise ValueError(f"the comparator in {pdk} has no resolved S-curve, so no noise to model: {params}")
        return cls(
            pdk=pdk,
            params=params,
            noise_v=noise,
            offset_v=metrics.get("offset_v") or 0.0,
            delay_s=metrics["delay_0p5mv_s"],
            energy_j=metrics["energy_0p5mv_j"],
        )

    def behavioral(self) -> CompBehavioralParams:
        """The behavioral ADC's comparator parameters: a dynamic comparator draws no static power."""
        return CompBehavioralParams(
            noise_v=self.noise_v, offset_v=self.offset_v, decision_energy_j=self.energy_j, static_power_w=0.0
        )

    def decide(self, vin_diff_v: np.ndarray, rng: np.random.Generator, *, vin_cm_v: float) -> np.ndarray:
        """1 where the noisy differential input exceeds the offset."""
        return comp(self.params, self.behavioral(), vin_diff_v, rng, vin_cm_v=vin_cm_v)
