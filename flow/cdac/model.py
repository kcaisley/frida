"""The CDAC's behavioral model: each stage's settling to half the converter's LSB, its drivers'
delay and the time constant that reproduces it, from the SPICE characterization of the same
``Params`` in the PDK (``flow.cdac.sweep``, looked up by ``flow.sweep.lookup``).

    model = cdac.model.Model.of("tsmc65", cdac.adc_array(pdk="tsmc65", array="12b_msb_redist3_x2"))

The behavioral ADC (``flow.adc.behavioral``) starts each stage's step its driver's delay after the
LOGIC edge and settles it as one exponential; with this model's time constants a step comes within
half an LSB exactly when the testbench's does. A characterization missing from the sweep's newest
run is simulated on first use (``simulate=True``) and kept under the build's models.
"""

from __future__ import annotations

from dataclasses import dataclass

from flow.sweep.lookup import characterized, detail

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
