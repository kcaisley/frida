"""The amplifier's behavioral model: its open-loop response, noise and power, from the
characterization of the same ``Params`` in the PDK (``flow.ota.runs``, looked up by
``flow.sweep.lookup``).

    model = ota.Model.of("tsmc65", ota.Params())
    gain = model.gain(1e6)

The characterization gives the low-frequency gain, the unity-gain bandwidth, the phase margin, the
total input-referred noise and the supply power at the nominal input common mode, and the gain over
frequency there, which ``Model.gain`` interpolates.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from flow.sweep.lookup import characterized, detail

from .params import Params


@dataclass(frozen=True)
class Model:
    """An amplifier as its characterization measured it."""

    pdk: str
    params: Params
    gain_dc_db: float  # low-frequency differential gain at the nominal input common mode
    unity_gain_bandwidth_hz: float
    phase_margin_deg: float
    noise_in_v: float  # the output noise over the sweep, referred to the input by the low-frequency gain
    power_w: float
    frequency_hz: tuple[float, ...]  # the measured gain's frequencies
    gain_db: tuple[float, ...]

    @classmethod
    def of(cls, pdk: str, params: Params, *, simulate: bool = True) -> Model:
        record = characterized("ota", pdk, params, simulate=simulate)
        metrics = record["metrics"]
        curve = detail(record, "gain")
        return cls(
            pdk=pdk,
            params=params,
            gain_dc_db=metrics["gain_dc_db"],
            unity_gain_bandwidth_hz=metrics["unity_gain_bandwidth_hz"],
            phase_margin_deg=metrics["phase_margin_deg"],
            noise_in_v=metrics["noise_in_v"],
            power_w=metrics["power_w"],
            frequency_hz=tuple(curve["x"]),
            gain_db=tuple(curve["series"]["gain"]),
        )

    def gain(self, frequency_hz: float | np.ndarray) -> float | np.ndarray:
        """The open-loop differential gain (V/V) at ``frequency_hz``: the measured curve,
        interpolated over the frequency's logarithm and held flat past its ends."""
        gain_db = np.interp(np.log10(frequency_hz), np.log10(self.frequency_hz), self.gain_db)
        return 10 ** (gain_db / 20)
