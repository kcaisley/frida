"""The CDAC's behavioral model: each stage's settling to half the converter's LSB, its drivers'
delay and the time constant that reproduces it, from the SPICE characterization of the array with
its drivers (``flow.cdac.sweep``, looked up by ``flow.sweep.lookup``).

    model = CdacModel.of("tsmc65", adc_params)  # or (pdk, CapArrayConfig, adc_bits)

The behavioral ADC (``flow.adc.behavioral``) starts each stage's step its driver's delay after the
LOGIC edge and settles it as one exponential; with this model's time constants a step comes within
half an LSB exactly when the testbench's does. A characterization missing from the sweep's newest
run is simulated on first use (``simulate=True``) and kept under ``build/models/cdac``.
"""

from __future__ import annotations

from dataclasses import dataclass

from flow.capdriver.subckt import Cells
from flow.sweep.lookup import characterized, detail

from .sweep import CdacSettling, settling_params


@dataclass(frozen=True)
class CdacModel:
    """One CDAC's per-stage settling, C0 first, as its SPICE characterization measured it."""

    pdk: str
    params: CdacSettling
    settling_s: tuple[float, ...]  # from the state's edge to within half an LSB, the slower direction
    delay_s: tuple[float, ...]  # its driver's delay, from the state's edge to its bottom plate's 50 %
    tau_s: tuple[float, ...]  # (settling - delay) / ln(|step| / half an LSB)
    lsb_v: float

    @classmethod
    def of(
        cls,
        pdk: str,
        params,
        adc_bits: int | None = None,
        *,
        cells: Cells = Cells.GENERIC,
        simulate: bool = True,
    ) -> CdacModel:
        """The model of an ADC's CDAC (``AdcParams``: its array and resolution) or of an array
        (``CapArrayConfig``) at ``adc_bits``."""
        config = getattr(params, "cdac", params)
        bits = adc_bits if adc_bits is not None else getattr(params, "adc_bits", None)
        if bits is None:
            raise ValueError("a CDAC's settling needs the converter's resolution (adc_bits)")
        settling = settling_params(pdk, config, bits, cells=cells)
        record = characterized("cdac", pdk, settling, simulate=simulate)
        stages = detail(record, "model_stage")["series"]
        return cls(
            pdk=pdk,
            params=settling,
            settling_s=tuple(detail(record, "settling_stage")["series"]["settling"]),
            delay_s=tuple(stages["delay"]),
            tau_s=tuple(stages["time constant"]),
            lsb_v=record["metrics"]["lsb_v"],
        )
