"""The follower's behavioral model: its output level for an input, from the characterization of the
same ``Params`` in the PDK (``flow.follower.runs``, looked up by ``flow.sweep.lookup``).

    model = follower.model.Model.of("tsmc65", follower.Params())
    vout_v = model.output(vin_v)

The characterization's output level over the input level (the input's DC sweep from ground to the
supply, ``plots.plot_vout_vin``) is the model's static transfer, interpolated between its points;
its small-signal gain, bandwidth and output resistance at the nominal input are kept beside it for
a higher level's own dynamics.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from flow.sweep.lookup import characterized, detail

from .params import Params


@dataclass(frozen=True)
class Model:
    """A follower as its characterization measured it."""

    pdk: str
    params: Params
    vin_v: tuple[float, ...]  # input levels of the output-level curve
    vout_v: tuple[float, ...]
    gain_dc: float  # at the nominal input, as the bandwidth and the output resistance
    bandwidth_hz: float
    rout_ohm: float

    @classmethod
    def of(cls, pdk: str, params: Params, *, simulate: bool = True) -> Model:
        record = characterized("follower", pdk, params, simulate=simulate)
        curve = detail(record, "vout_vin")
        pairs = [(x, y) for x, y in zip(curve["x"], curve["series"]["output"], strict=True) if y is not None]
        metrics = record["metrics"]
        return cls(
            pdk=pdk,
            params=params,
            vin_v=tuple(x for x, _ in pairs),
            vout_v=tuple(y for _, y in pairs),
            gain_dc=metrics["gain_dc"],
            bandwidth_hz=metrics["bandwidth_hz"],
            rout_ohm=metrics["rout_ohm"],
        )

    def output(self, vin_v: np.ndarray) -> np.ndarray:
        """The output level at each input level: the measured curve, interpolated, held flat past
        its ends."""
        return np.interp(vin_v, np.asarray(self.vin_v), np.asarray(self.vout_v))
