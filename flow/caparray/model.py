"""The capacitor array's behavioral model: each stage's main and difference capacitance and the
top plate's other load, from the 3D extraction of the same ``CapArrayConfig`` laid out in the PDK
(``python -m flow caparray.layout_extract_adc_variants`` writes one table per ADC variant).

    model = CapArrayModel.of("tsmc65", CapArrayConfig(n_dac=11, n_extra=5))
    main_f, diff_f = model.draw(unit_mismatch=0.001, rng=rng)

The top plate's load beyond the switched plates is the array's own: its coupling to the shield
and to ground in the extraction. The sampler's and comparator's input capacitance and the routing
between the blocks are not extracted for these arrays, so they are left out.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from flow.adc.behavioral import calc_capacitor_mismatch
from flow.sweep.runner import ROOT

from .layout import ADC_VARIANTS
from .subckt import CapArrayConfig, get_caparray_weights

EXTRACTIONS = ROOT / "build/layout/caparray/extract_adc_variants"
IDEAL = ROOT / "build/models/caparray/ideal"  # the ideal arrays' tables, in the extractions' format
# Random part of Harpe's measured unit-length DAC linearity (JSSC 2018, 65 nm): 0.10 %·sqrt(fF)
UNIT_MISMATCH_HARPE = 0.0010


@dataclass(frozen=True)
class CapArrayModel:
    """One side's capacitor array as its extraction measured it."""

    pdk: str
    params: CapArrayConfig
    main_f: np.ndarray  # C0 first
    diff_f: np.ndarray
    parasitic_f: float  # the top plate's other load: to the shield and to ground
    table: Path  # the extraction's capacitance table (``read_extracted_calibration`` reads it)

    @classmethod
    def of(cls, pdk: str, params: CapArrayConfig, *, layers: int = 3) -> CapArrayModel:
        if params.parasitic_cap is not None:
            return cls.ideal(pdk, params)
        name = next((key for key, value in ADC_VARIANTS.items() if value == params), None)
        tables = sorted(EXTRACTIONS.glob(f"*/{name}/{pdk}/{layers}l/capacitance_table.json")) if name else []
        if not tables:
            raise LookupError(
                f"no {layers}-metal extraction of {params} in {pdk}: run python -m flow caparray.layout_extract_adc_variants"
            )
        extracted = json.loads(tables[-1].read_text())
        main_f = np.asarray(extracted["main_by_stage_ff"]) * 1e-15
        diff_f = np.asarray(extracted["diff_by_stage_ff"]) * 1e-15
        if len(main_f) != len(get_caparray_weights(params)):
            raise ValueError(f"{tables[-1]} has {len(main_f)} stages, the array {len(get_caparray_weights(params))}")
        parasitic = (extracted["topplate_shield_ff"] + extracted["topplate_ground_ff"]) * 1e-15
        return cls(
            pdk=pdk,
            params=params,
            main_f=main_f,
            diff_f=diff_f,
            parasitic_f=parasitic,
            table=tables[-1].with_suffix(".csv"),
        )

    @classmethod
    def ideal(cls, pdk: str, params: CapArrayConfig) -> CapArrayModel:
        """An array as specified rather than laid out: each stage its weight in unit capacitors, no
        difference plates, and the top plate's other load ``parasitic_cap`` (a specification's
        total less its switched capacitance: routing, the sampler, the comparator, dummies). Its
        table is the extraction's format, so the decoders read it as an extraction's."""
        weights = np.asarray(get_caparray_weights(params), dtype=np.float64)
        main_f = weights * float(params.unit_cap)
        parasitic = float(params.parasitic_cap)
        rows = "".join(f"{i},{c * 1e15:.6f},0,{c * 1e15:.6f}\n" for i, c in enumerate(main_f))
        text = "stage,main_ff,diff_ff,effective_ff\n" + rows
        table = IDEAL / f"{hashlib.sha256(f'{text}{parasitic}'.encode()).hexdigest()[:16]}.csv"
        if not table.exists():
            table.parent.mkdir(parents=True, exist_ok=True)
            table.write_text(text)
        return cls(
            pdk=pdk, params=params, main_f=main_f, diff_f=np.zeros_like(main_f), parasitic_f=parasitic, table=table
        )

    @property
    def load_f(self) -> float:
        """The top plate's whole load: every plate and the parasitic."""
        return float(np.sum(self.main_f) + np.sum(self.diff_f)) + self.parasitic_f

    def draw(self, *, unit_mismatch: float, rng: np.random.Generator) -> tuple[np.ndarray, np.ndarray]:
        """One Pelgrom draw of the main and difference plates (none where ``unit_mismatch`` is 0)."""
        if not unit_mismatch:
            return self.main_f, self.diff_f
        return (
            calc_capacitor_mismatch(self.main_f, unit_mismatch=unit_mismatch, rng=rng),
            calc_capacitor_mismatch(self.diff_f, unit_mismatch=unit_mismatch, rng=rng),
        )
