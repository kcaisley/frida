"""The latch's behavioral model: when its output follows its data, from the characterization of
the same ``Params`` in the PDK (``flow.latch.runs``, looked up by ``flow.sweep.lookup``).

    model = latch.model.Model.of("tsmc65", latch.Params(flop=True, reset=True))
    taken = model.captures(data_offset_s)
    q_s = edge_s + model.delay_s(rising=True)

The characterization gives the delays to q rising and falling at the nominal supply (a flip-flop's
from its clock, a latch's from d while it is open, an SR latch's from set and reset), the energy per
cycle drawn from the supply by the latch and by its inputs' drivers,
and a latch's or flip-flop's setup and hold: data that changes at least the setup before a
capturing edge is taken, data that changes at least the hold after it is not, and between the two
the model does not say.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from flow.sweep.lookup import characterized

from .params import Params


@dataclass(frozen=True)
class Model:
    """A latch, flip-flop, divider or SR latch as its characterization measured it."""

    pdk: str
    params: Params
    delay_rise_s: float  # to q rising, at the nominal supply
    delay_fall_s: float  # to q falling
    energy_per_cycle_j: float
    setup_s: float  # NaN for a design without a clocked data input (a divider, an SR latch)
    hold_s: float

    @classmethod
    def of(cls, pdk: str, params: Params, *, simulate: bool = True) -> Model:
        metrics = characterized("latch", pdk, params, simulate=simulate)["metrics"]
        return cls(
            pdk=pdk,
            params=params,
            delay_rise_s=float(metrics["delay_rise_s"]),
            delay_fall_s=float(metrics["delay_fall_s"]),
            energy_per_cycle_j=float(metrics["energy_per_cycle_j"]),
            # a record keeps NaN as null
            setup_s=float("nan") if metrics["setup_s"] is None else float(metrics["setup_s"]),
            hold_s=float("nan") if metrics["hold_s"] is None else float(metrics["hold_s"]),
        )

    def delay_s(self, *, rising: bool) -> float:
        """The delay from the launching edge to q's mid-supply crossing, rising or falling."""
        return self.delay_rise_s if rising else self.delay_fall_s

    def captures(self, data_offset_s: np.ndarray) -> np.ndarray:
        """Whether data that crosses mid-supply ``data_offset_s`` before a capturing edge (negative:
        after it) is taken: 1 from the setup time on, 0 where it changes at least the hold time
        after the edge, NaN between the two."""
        offset = np.asarray(data_offset_s, dtype=np.float64)
        return np.where(offset >= self.setup_s, 1.0, np.where(-offset >= self.hold_s, 0.0, np.nan))
