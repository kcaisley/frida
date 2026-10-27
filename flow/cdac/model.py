"""The CDAC's behavioral model: each stage's settling to half the converter's LSB, its drivers'
delay and the time constant that reproduces it, from the SPICE characterization of the same
``Params`` in the PDK (``flow.cdac.sweep``, looked up by ``flow.sweep.lookup``).

    model = cdac.model.Model.of("tsmc65", cdac.adc_array.spaces("tsmc65")["12b_msb_redist3_x2"].base)

The behavioral ADC (``flow.adc.behavioral``) starts each stage's step its driver's delay after the
LOGIC edge and settles it as one exponential; with this model's time constants a step comes within
half an LSB exactly when the testbench's does. A characterization missing from the sweep's newest
run is simulated on first use (``simulate=True``) and kept under the build's models.

``Model.drawn`` gives one of the characterization's Monte Carlo draws, the plates a converter on the
array calibrates on (``flow.adc.model``): of one condition, the run at a percentile of what no
calibration recovers.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from flow.analysis.io import read_measurement
from flow.sweep.lookup import characterized, detail
from flow.sweep.runner import ROOT

from .analysis import analyze_mismatch
from .params import Params


@dataclass(frozen=True)
class Model:
    """One CDAC's per-stage settling, C0 first, as its SPICE characterization measured it."""

    pdk: str
    params: Params
    settling_s: tuple[float, ...]  # from the state's edge to within half an LSB, the slower direction
    delay_s: tuple[float, ...]  # its driver's delay, from the state's edge to its bottom plate's 50 %
    tau_s: tuple[float, ...]  # (settling - delay) / ln(|step| / half an LSB)
    lsb_v: float

    @classmethod
    def of(cls, pdk: str, params: Params, *, simulate: bool = True) -> Model:
        record = characterized("cdac", pdk, params, simulate=simulate)
        stages = detail(record, "model_stage")["series"]
        return cls(
            pdk=pdk,
            params=params,
            settling_s=tuple(detail(record, "settling_stage")["series"]["settling"]),
            delay_s=tuple(stages["delay"]),
            tau_s=tuple(stages["time constant"]),
            lsb_v=record["metrics"]["lsb_v"],
        )

    @classmethod
    def drawn(
        cls, pdk: str, params: Params, run: str, percentile: float
    ) -> tuple[tuple[np.ndarray, np.ndarray], tuple[np.ndarray, np.ndarray]]:
        """One Monte Carlo draw of the characterization's run ``run`` (a condition of
        ``flow.cdac.sweep.runs``): its plates, (main, difference) for the P side then the N side (F,
        C0 first). The draw is the one at ``percentile`` of its runs ranked by what no calibration
        recovers, the converter's INL with its design weights breaking ties
        (``flow.cdac.analysis.analyze_mismatch``). Looked up, never simulated."""
        record = characterized("cdac", pdk, params, simulate=False)
        if run not in record.get("waves", {}):
            raise LookupError(f"the CDAC's characterization has no Monte Carlo run {run}")
        result = analyze_mismatch(read_measurement(ROOT / record["waves"][run]))
        ranked = np.lexsort((result.inl_lsb, result.gap_lsb))
        index = int(ranked[round(percentile / 100 * (len(ranked) - 1))])
        return (
            (result.main_p_f[index], result.diff_p_f[index]),
            (result.main_n_f[index], result.diff_n_f[index]),
        )
