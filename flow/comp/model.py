"""The comparator's behavioral model: the decision a SAR loop sees, from the characterization of
the same ``CompParams`` in the PDK (``flow.comp.sweep``, looked up by ``flow.sweep.lookup``).

    model = CompModel.of("tsmc65", CompParams(...))
    bits = model.decide(vin_diff_v, rng, vin_cm_v=0.7)

The characterization gives the input-referred noise and the systematic offset over the common
mode (3/8 to 5/8 of the supply; the model interpolates them at the ADC's), the clock-to-decision
delay over the input from 0.1 mV to 100 mV (its metastability: the ADC's decision is late where
it exceeds the time the SAR sequence allows), and the supply energy per decision at 0.5 mV, the
slowest response. A comparator whose S-curve did not resolve (too slow for the
characterization's 7 ns a decision) has no noise and no model.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from flow.adc.behavioral import CompBehavioralParams, comp
from flow.sweep.lookup import characterized, detail

from .subckt import CompParams


@dataclass(frozen=True)
class CompModel:
    """A comparator as its characterization measured it."""

    pdk: str
    params: CompParams
    noise_v: float  # input-referred RMS noise at the nominal common mode
    offset_v: float  # systematic only: the characterization has no mismatch
    delay_s: float  # clock to decision at 0.5 mV
    energy_j: float  # supply energy per decision at 0.5 mV
    delay_table_v: tuple[float, ...]  # ascending input magnitudes of the measured delay
    delay_table_s: tuple[float, ...]
    cm_table_v: tuple[float, ...]  # common modes of the noise and offset S-curves
    noise_table_v: tuple[float, ...]  # NaN where that S-curve did not resolve
    offset_table_v: tuple[float, ...]

    @classmethod
    def of(cls, pdk: str, params: CompParams, *, simulate: bool = True) -> CompModel:
        record = characterized("comp", pdk, params, simulate=simulate)
        metrics = record["metrics"]
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
            delay_table_v=tuple(detail(record, "metastability")["x"]),
            delay_table_s=tuple(detail(record, "metastability")["series"]["delay"]),
            cm_table_v=tuple(detail(record, "noise_cm")["x"]),
            # an S-curve that did not resolve is null in the record: NaN here
            noise_table_v=tuple(math.nan if v is None else v for v in detail(record, "noise_cm")["series"]["noise"]),
            offset_table_v=tuple(math.nan if v is None else v for v in detail(record, "offset_cm")["series"]["offset"]),
        )

    @property
    def regeneration_tau_s(self) -> float:
        """The latch's regeneration time constant: the delay's growth per e-fold fall of the input,
        between the two smallest measured inputs."""
        return (self.delay_table_s[0] - self.delay_table_s[1]) / math.log(self.delay_table_v[1] / self.delay_table_v[0])

    def behavioral(self, *, vin_cm_v: float | None = None) -> CompBehavioralParams:
        """The behavioral ADC's comparator parameters at ``vin_cm_v`` (the nominal common mode where
        None): the noise and offset interpolated over the common mode's resolved S-curves, the
        measured delay curve. A dynamic comparator draws no static power."""
        noise_v, offset_v = self.noise_v, self.offset_v
        cm = np.asarray(self.cm_table_v)
        resolved = np.isfinite(self.noise_table_v)
        if vin_cm_v is not None and np.count_nonzero(resolved) >= 2:
            noise_v = float(np.interp(vin_cm_v, cm[resolved], np.asarray(self.noise_table_v)[resolved]))
            offset_v = float(np.interp(vin_cm_v, cm[resolved], np.asarray(self.offset_table_v)[resolved]))
        return CompBehavioralParams(
            noise_v=noise_v,
            offset_v=offset_v,
            decision_energy_j=self.energy_j,
            static_power_w=0.0,
            delay_table_v=self.delay_table_v,
            delay_table_s=self.delay_table_s,
        )

    def decide(self, vin_diff_v: np.ndarray, rng: np.random.Generator, *, vin_cm_v: float) -> np.ndarray:
        """1 where the noisy differential input exceeds the offset (never late: no time limit)."""
        return comp(self.params, self.behavioral(vin_cm_v=vin_cm_v), vin_diff_v, rng, vin_cm_v=vin_cm_v)
