"""The sampling switch's behavioral model: the held top-plate voltage, from the characterization of
the same ``SampParams`` in the PDK (``flow.samp.sweep``, looked up by ``flow.sweep.lookup``).

    model = SampModel.of("tsmc65", SampParams())
    params = model.behavioral(load_f=1.2e-12)

The characterization's on-resistance over the input level (into 1 pF, the gate at the supply)
sets the tracking lag of each side, ``R(v) C dv/dt``; the held kT/C noise follows from the load
the ADC puts on it, and the aperture jitter is assumed (the clock is not characterized).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from flow.adc.behavioral import BOLTZMANN_J_PER_K, SampBehavioralParams, samp
from flow.sweep.lookup import characterized, detail

from .subckt import SampParams

# ASSUMED RMS aperture jitter of the on-chip sampling clock (as the FRIDA-2 behavioral scans)
JITTER_S = 2e-12


@dataclass(frozen=True)
class SampModel:
    """A sampling switch as its characterization measured it."""

    pdk: str
    params: SampParams
    ron_v: tuple[float, ...]  # input levels of the on-resistance curve
    ron_ohm: tuple[float, ...]
    bandwidth_hz: float  # into 1 pF at mid-supply

    @classmethod
    def of(cls, pdk: str, params: SampParams, *, simulate: bool = True) -> SampModel:
        record = characterized("samp", pdk, params, simulate=simulate)
        curve = detail(record, "ron_vin")
        pairs = [(x, y) for x, y in zip(curve["x"], curve["series"]["on-resistance"], strict=True) if y is not None]
        return cls(
            pdk=pdk,
            params=params,
            ron_v=tuple(x for x, _ in pairs),
            ron_ohm=tuple(y for _, y in pairs),
            bandwidth_hz=record["metrics"]["bandwidth_hz"],
        )

    def behavioral(self, *, load_f: float, temperature_k: float = 300.0) -> SampBehavioralParams:
        """The behavioral ADC's sampler parameters for a top-plate load of ``load_f`` per side: the
        differential kT/C noise of the two plates, sqrt(2 k T / C)."""
        return SampBehavioralParams(
            noise_v=float(np.sqrt(2 * BOLTZMANN_J_PER_K * temperature_k / load_f)),
            jitter_s=JITTER_S,
            ron_table_v=self.ron_v,
            ron_table_ohm=self.ron_ohm,
        )

    def hold(self, vin, slope, *, load_f: dict[str, float], gate_v: float, rng: np.random.Generator):
        """Each side's held voltage (``flow.adc.behavioral.samp``)."""
        mean_load = float(np.mean(list(load_f.values())))
        return samp(self.params, self.behavioral(load_f=mean_load), vin, slope, load_f=load_f, gate_v=gate_v, rng=rng)
