"""The charge-sensitive amplifier's behavioral model: its pulse amplitude for an injected charge,
from the characterization of the same ``Params`` in the PDK (``flow.csa.runs``, looked up by
``flow.sweep.lookup``).

    model = csa.model.Model.of("tsmc65", csa.Params())
    amplitude_v = model.amplitude(charge_c)

The characterization's amplitude over the injected charge (0.25 to 2 fC) is the model's static
transfer, interpolated between its points; its charge gain, peaking time and equivalent noise
charge at the smallest charge are kept beside it for a higher level's own dynamics and noise.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from flow.sweep.lookup import characterized, detail

from .params import Params


@dataclass(frozen=True)
class Model:
    """A charge-sensitive amplifier as its characterization measured it."""

    pdk: str
    params: Params
    charge_c: tuple[float, ...]  # injected charges of the amplitude curve
    amplitude_v: tuple[float, ...]
    charge_gain_v_per_c: float  # at the smallest charge, as the peaking time
    peaking_time_s: float
    enc_electrons: float  # NaN for a reset amplifier (no noise run)

    @classmethod
    def of(cls, pdk: str, params: Params, *, simulate: bool = True) -> Model:
        record = characterized("csa", pdk, params, simulate=simulate)
        curve = detail(record, "amplitude_charge")
        pairs = [(x, y) for x, y in zip(curve["x"], curve["series"]["amplitude"], strict=True) if y is not None]
        # a metric not measured (a reset amplifier's peaking time and ENC) is None in the record
        metrics = {name: float("nan") if value is None else value for name, value in record["metrics"].items()}
        return cls(
            pdk=pdk,
            params=params,
            charge_c=tuple(x for x, _ in pairs),
            amplitude_v=tuple(y for _, y in pairs),
            charge_gain_v_per_c=metrics["charge_gain_v_per_c"],
            peaking_time_s=metrics["peaking_time_s"],
            enc_electrons=metrics["enc_electrons"],
        )

    def amplitude(self, charge_c: np.ndarray) -> np.ndarray:
        """The pulse amplitude for each injected charge (its magnitude): the measured curve,
        interpolated, held flat past its ends."""
        return np.interp(np.abs(charge_c), np.asarray(self.charge_c), np.asarray(self.amplitude_v))
