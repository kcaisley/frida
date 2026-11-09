"""The ADC's behavioral model: one converter's characterization (``flow.adc.search``'s record, looked
up by ``flow.sweep.lookup``) as the stand-in a higher level of the hierarchy simulates.

    model = Model.of("tsmc65", Params(adc_bits=12, cdac=..., samp=..., comp=...))
    model.enob_bits(10e6), model.power_w(10e6)

The converter its record measures is the behavioral one of ``flow.adc.sim`` (its blocks'
characterizations, switched by its SAR loop); this model reads what that converter gave, its ENOB
and supply power over the conversion rate (the record's figures ``enob_rate`` and ``power_rate``),
interpolated between the rates its runs converted at.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from flow.sweep.lookup import characterized, detail

from .params import Params


@dataclass(frozen=True)
class Model:
    """A SAR ADC as its characterization measured it: its ENOB and supply power over the rate."""

    pdk: str
    params: Params
    rate_hz: tuple[float, ...]  # the rates its runs converted at, ascending
    enob: tuple[float, ...]  # the spectral ENOB referred to full scale at each
    power: tuple[float, ...]  # the supply power (W) at each

    @classmethod
    def of(cls, pdk: str, params: Params, *, simulate: bool = True) -> Model:
        """The model of ``params`` in ``pdk``: its record (``flow.sweep.lookup.characterized``;
        ``simulate=False`` only looks, never characterizes)."""
        record = characterized("adc", pdk, params, simulate=simulate)
        enob, power = detail(record, "enob_rate"), detail(record, "power_rate")
        if enob["x"] != power["x"]:
            raise ValueError(f"the ADC record's ENOB and power are not over the same rates: {record['id']}")
        # a rate where the output no longer follows the input has no ENOB (null)
        rows = [
            (rate, bits, watts)
            for rate, bits, watts in zip(enob["x"], enob["series"]["ENOB"], power["series"]["Total"], strict=True)
            if bits is not None and watts is not None
        ]
        return cls(
            pdk=pdk,
            params=params,
            rate_hz=tuple(row[0] for row in rows),
            enob=tuple(row[1] for row in rows),
            power=tuple(row[2] for row in rows),
        )

    def enob_bits(self, rate_hz: float) -> float:
        """The ENOB at ``rate_hz``, interpolated over the rate on a log scale (the end's beyond)."""
        return float(np.interp(np.log(rate_hz), np.log(self.rate_hz), self.enob))

    def power_w(self, rate_hz: float) -> float:
        """The supply power (W) at ``rate_hz``, interpolated on log scales (the end's beyond)."""
        return float(np.exp(np.interp(np.log(rate_hz), np.log(self.rate_hz), np.log(self.power))))
