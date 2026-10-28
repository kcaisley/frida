"""The capacitor array's behavioral model: each stage's main and difference capacitance and the
top plate's other load, from the 3D extraction of the same ``CapArrayConfig`` laid out in the PDK
at its split and capacitance (``python -m flow cdac.caparray.layout_extract_adc_arrays`` sizes each ADC
array through its extraction, ``flow.cdac.caparray.sizing``, and writes one table per array, named by
``flow.cdac.caparray.layout.array_name``). A unary stage has no difference plate (0).

    model = CapArrayModel.of("tsmc65", CapArrayConfig(n_dac=11, n_extra=5, cap_scale=2))
    main_f, diff_f = model.draw(unit_mismatch=0.001, rng=rng)

The top plate's load beyond the switched plates is the array's own: its coupling to the shield
and to ground in the extraction. The sampler's and comparator's input capacitance and the routing
between the blocks are not extracted for these arrays, so they are left out.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from flow.sweep.runner import ROOT

from .layout import array_name, plate_centroids_um
from .subckt import CapArrayConfig, get_caparray_weights

EXTRACTIONS = ROOT / "build/layout/caparray/extract_adc_arrays"
# Random part of Harpe's measured unit-length DAC linearity (JSSC 2018, 65 nm): 0.10 %·sqrt(fF)
UNIT_MISMATCH_HARPE = 0.0010


def calc_capacitor_mismatch(capacitance_f: np.ndarray, *, unit_mismatch: float, rng: np.random.Generator) -> np.ndarray:
    """Draw Pelgrom mismatch: sigma_C = unit_mismatch * sqrt(C * 1 fF) for every capacitor."""

    capacitance_f = np.asarray(capacitance_f, dtype=np.float64)
    return capacitance_f + rng.normal(0.0, unit_mismatch * np.sqrt(capacitance_f * 1e-15))


@dataclass(frozen=True)
class CapArrayModel:
    """One side's capacitor array as its extraction measured it."""

    pdk: str
    params: CapArrayConfig
    main_f: np.ndarray  # C0 first
    diff_f: np.ndarray
    parasitic_f: float  # the top plate's other load: to the shield and to ground
    table: Path  # the extraction's capacitance table (``read_extracted_calibration`` reads it)
    outline_um: tuple[float, float] = (0.0, 0.0)  # the drawn array's boundary (width, height), one side's
    # each stage's main and difference plate centroid (x, y um) from the array's centre (empty where
    # its extraction kept no manifest; ``flow.cdac.caparray.layout.plate_centroids_um``)
    main_xy_um: tuple[tuple[float, float], ...] = ()
    diff_xy_um: tuple[tuple[float, float], ...] = ()

    @classmethod
    def of(cls, pdk: str, params: CapArrayConfig, *, layers: int = 3) -> CapArrayModel:
        """The newest extraction of the array ``params`` names (``array_name``) in ``pdk``."""
        name = array_name(params) if params.weights is None else None
        tables = sorted(EXTRACTIONS.glob(f"*/{name}/{pdk}/{layers}l/capacitance_table.json")) if name else []
        if not tables:
            raise LookupError(
                f"no {layers}-metal extraction of {params} in {pdk}: run python -m flow cdac.caparray.layout_extract_adc_arrays"
            )
        extracted = json.loads(tables[-1].read_text())
        main_f = np.asarray(extracted["main_by_stage_ff"]) * 1e-15
        diff_f = np.asarray(extracted["diff_by_stage_ff"]) * 1e-15
        if len(main_f) != len(get_caparray_weights(params)):
            raise ValueError(f"{tables[-1]} has {len(main_f)} stages, the array {len(get_caparray_weights(params))}")
        parasitic = (extracted["topplate_shield_ff"] + extracted["topplate_ground_ff"]) * 1e-15
        manifest_path = tables[-1].with_name("geometry_manifest.json")
        manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {}
        width_um, height_um = manifest.get("outline_um", (0.0, 0.0))
        main_xy, diff_xy = plate_centroids_um(manifest) if "derived_geometry_nm" in manifest else ((), ())
        return cls(
            pdk=pdk,
            params=params,
            main_f=main_f,
            diff_f=diff_f,
            parasitic_f=parasitic,
            table=tables[-1].with_suffix(".csv"),
            outline_um=(float(width_um), float(height_um)),
            main_xy_um=main_xy,
            diff_xy_um=diff_xy,
        )

    @property
    def area_um2(self) -> float:
        """The drawn array's area, one side's (0 where its extraction kept no outline)."""
        return self.outline_um[0] * self.outline_um[1]

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
