"""The delay line and ring oscillator's behavioral model: its delay per stage over the supply, from
the characterization of the same ``Params`` in the PDK (``flow.delay.runs``, looked up by
``flow.sweep.lookup``).

    model = delay.model.Model.of("tsmc65", delay.Params(stages=4))
    delay_s = model.delay_s(supply=0.95)

A delay line delays its input by its stages' delays; a ring oscillates at the frequency two passes
around it give.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from flow.sweep.lookup import characterized, detail

from .params import Params


@dataclass(frozen=True)
class Model:
    """A delay line or ring oscillator as its characterization measured it."""

    pdk: str
    params: Params
    supply: tuple[float, ...]  # the supplies of the stage delay curve, over the PDK's nominal
    stage_delay_s: tuple[float, ...]  # the delay per stage at each

    @classmethod
    def of(cls, pdk: str, params: Params, *, simulate: bool = True) -> Model:
        record = characterized("delay", pdk, params, simulate=simulate)
        curve = detail(record, "stage_delay_supply")
        pairs = [(x, y) for x, y in zip(curve["x"], curve["series"]["stage delay"], strict=True) if y is not None]
        return cls(
            pdk=pdk,
            params=params,
            supply=tuple(x for x, _ in pairs),
            stage_delay_s=tuple(y for _, y in pairs),
        )

    def stage_delay(self, supply: float = 1.0) -> float:
        """The delay per stage at ``supply`` (over the PDK's nominal), interpolated on the measured
        curve and held flat past its ends."""
        return float(np.interp(supply, np.asarray(self.supply), np.asarray(self.stage_delay_s)))

    def delay_s(self, supply: float = 1.0) -> float:
        """A delay line's delay from its input to its output at ``supply``: its stages' delays."""
        return self.params.stages * self.stage_delay(supply)

    def oscillation_frequency_hz(self, supply: float = 1.0) -> float:
        """A ring's oscillation frequency at ``supply``."""
        # [Razavi-PLL] Sec. 3.3.2, p. 74: a ring's frequency from its gate delay
        return 1 / (2 * self.params.stages * self.stage_delay(supply))
