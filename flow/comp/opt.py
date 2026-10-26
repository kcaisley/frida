"""The comparator's optimization problems (``python -m flow opt comp --problem "adc(bits=12)"``): the
least energy, area and noise of a comparator for a converter of each resolution, within its
bounds (``params.ADC_FULL_SCALE`` and the constants after it). The first runs search NMOS input
pairs alone: the hand-written floorplans that give the layout area in a minute
(``layout.layout_floorplan``) are NMOS ones, and a design without one cannot meet the area bound.
"""

from __future__ import annotations

import importlib
import math

import hdl21 as h
from hdl21.primitives import MosType

from flow.pipeline import Problem, problem

from .params import ADC_FULL_SCALE, AREA_SIDE_UM, AREA_WEIGHT, DECISION_S, NOISE_WEIGHT


@problem(bits=(10, 12, 14))
def adc(bits: int, pdk: str) -> Problem:
    """A comparator for a ``bits``-bit converter in ``pdk``: its noise at most the converter's
    quantization noise at the PDK's supply, its layout within the resolution's square, its delay
    within the decision's time."""

    supply = importlib.import_module(f"pdk.{pdk}.hdl21.site").install.supply_voltage(h.pdk.Corner.TYP)
    quantization_v = 2 * ADC_FULL_SCALE * supply / 2**bits / math.sqrt(12)
    return Problem(
        cost={"energy_0p5mv_j": 1.0, "layout_area_um2": AREA_WEIGHT, "noise_v": (NOISE_WEIGHT, quantization_v)},
        bound={
            "noise_v": quantization_v,
            "layout_area_um2": AREA_SIDE_UM[bits] ** 2,
            "delay_0p5mv_s": DECISION_S,
            "decides_in_time": True,
        },
        fixed={"input_pair": MosType.NMOS},
    )
