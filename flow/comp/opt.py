"""The comparator's optimization problems (``python -m flow opt comp --problem "adc(bits=12)"``): the
least energy, area and noise of a comparator for a converter of each resolution, within its
bounds (``params.ADC_FULL_SCALE`` and the constants after it), over its space (``widen``). The
first runs search NMOS input pairs alone: the hand-written floorplans that give the layout area in
a minute (``layout.layout_floorplan``) are NMOS ones, and a design without one cannot meet the
area bound.
"""

from __future__ import annotations

import importlib
import math

import hdl21 as h
from hdl21.primitives import MosType

from flow.pipeline import Pdk, Problem, every, problem, steps, widen

from .params import ADC_FULL_SCALE, AREA_SIDE_UM, AREA_WEIGHT, DECISION_S, NOISE_WEIGHT, Bias, Latch, Params


@problem(bits=(10, 12, 14))
def adc(bits: int, pdk: Pdk) -> Problem:
    """A comparator for a ``bits``-bit converter in ``pdk``: its noise at most the converter's
    quantization noise at the PDK's supply, its layout within the resolution's square, its delay
    within the decision's time. Searched: every latch and tail, each size on a log scale; the latch
    devices' lengths only where a PDK's longer ones still decide within the evaluation (else held at
    the minimum), the tail no longer than a PDK's decides; the dynamic bias's capacitors with it."""

    supply = importlib.import_module(f"pdk.{pdk.name.lower()}.hdl21.site").install.supply_voltage(h.pdk.Corner.TYP)
    quantization_v = 2 * ADC_FULL_SCALE * supply / 2**bits / math.sqrt(12)
    space = widen(Params(input_pair=MosType.NMOS))
    space.latch = every(Latch)
    space.bias = every(Bias)
    space.diffpair_w = steps(2, 8192, log=True)
    space.diffpair_l = steps(1, 16, log=True)
    space.tail_w = steps(2, 4096, log=True)
    space.tail_l = steps(1, {Pdk.TSMC28: 32, Pdk.IHP130: 34, Pdk.LF150: 34}.get(pdk, 64), log=True)
    space.rst_w = steps(2, 2048, log=True)
    space.latch_on_w = steps(2, 2048, log=True)
    space.latch_init_w = steps(2, 2048, log=True)
    if pdk in (Pdk.TSMC65, Pdk.TSMC28):  # elsewhere longer latch devices do not decide in time: held at 1
        space.latch_on_l = steps(1, 32, log=True)
        space.latch_init_l = steps(1, 32, log=True)
    space.preamp_c_ff = steps(10, 16000, log=True, when=Bias.DYNAMIC)
    space.bias_c_ff = steps(10, 64000, log=True, when=Bias.DYNAMIC)
    return Problem(
        cost={"energy_0p5mv_j": 1.0, "layout_area_um2": AREA_WEIGHT, "noise_v": (NOISE_WEIGHT, quantization_v)},
        bound={
            "noise_v": quantization_v,
            "layout_area_um2": AREA_SIDE_UM[bits] ** 2,
            "delay_0p5mv_s": DECISION_S,
            "decides_in_time": True,
        },
        space=space,
    )
