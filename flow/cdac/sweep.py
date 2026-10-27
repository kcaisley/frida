"""The CDAC's design space (docs/pipeline.md): the array of every converter of ``flow.adc.sweep``
with its drivers, at that converter's resolution (``adc_array``: every ADC array,
``flow.caparray.layout.ADC_ARRAYS``, sized through its extraction in TSMC65, at one bit more than
its DAC's steps, the free first comparison: 61 instances); the testbench run that characterizes one
instance (``runs``) and the record it makes (``record``).

The drivers are the generic cells the ADC model stands in with, derived from the array's plates
(``flow.capdriver.model.driver_strengths``: each stage's drive scaled with its plate to settle in
about 1 ns). Each instance switches every stage alone, both ways (``flow.cdac.sim``): its settling
to half an LSB, its drivers' delay and the time constant the behavioral ADC settles it with, by
stage. One Spectre run, a few minutes beside other jobs, in a window the drivers' characterization
says the slowest stage settles in within its first half; an instance whose stage does not raises.
"""

from __future__ import annotations

import importlib
import math
from dataclasses import replace

import hdl21 as h

from flow.caparray.layout import ADC_ARRAYS
from flow.caparray.model import CapArrayModel
from flow.caparray.subckt import get_caparray_weights
from flow.capdriver.model import CapDriverModel, driver_strengths
from flow.capdriver.subckt import CapDriverParams, Cells, stage_strengths
from flow.pipeline import Meas, Record, family

from .analysis import analyze_mismatch, analyze_settling, metrics
from .params import GRADIENTS_PER_UM, MC_RUNS, PAIR_GAP_UM, PELGROMS, SAMPLES_PER_WINDOW, Params, TbParams, _Dac
from .plots import (
    plot_dac_dnl,
    plot_dac_inl,
    plot_mismatch_dac_inl,
    plot_mismatch_gap,
    plot_mismatch_gradient,
    plot_mismatch_inl,
    plot_model_stage,
    plot_settling_stage,
)


# the arrays in each PDK where they are extracted (flow.caparray.sizing.extract_adc_arrays); the
# 14-bit ones first, as they take longest
@family(pdks=("tsmc65", "lf150", "ihp130"), pdk=lambda pdk: (pdk,), array=tuple(reversed(ADC_ARRAYS)))
def adc_array(pdk: str, array: str) -> Params:
    """The CDAC of the ADC array ``array`` (``ADC_ARRAYS``) in ``pdk``, at its converter's
    resolution: its plates as its extraction gives them (``CapArrayModel.of``), its drivers the
    generic cells derived from them (``driver_strengths``)."""
    config = ADC_ARRAYS[array]
    plates = CapArrayModel.of(pdk, config)
    # the pair about the origin: the P array left, the N array its mirror image right
    shift = (plates.outline_um[0] + PAIR_GAP_UM) / 2
    return Params(
        dac=_Dac(
            driver=CapDriverParams(
                n_stages=len(plates.main_f), strengths=driver_strengths(pdk, config, plates), cells=Cells.GENERIC
            ),
            main_f=tuple(float(c) for c in plates.main_f),
            diff_f=tuple(float(c) for c in plates.diff_f),
            parasitic_f=float(plates.parasitic_f),
            weights=tuple(get_caparray_weights(config)),
            main_p_um=tuple((x - shift, y) for x, y in plates.main_xy_um),
            diff_p_um=tuple((x - shift, y) for x, y in plates.diff_xy_um),
            main_n_um=tuple((shift - x, y) for x, y in plates.main_xy_um),
            diff_n_um=tuple((shift - x, y) for x, y in plates.diff_xy_um),
        ),
        adc_bits=config.n_dac + 1,
    )


def _window_s(pdk: str, params: Params, vdd: float) -> float:
    """A window the slowest stage settles in within its first half: twice each plate's driver
    delay and its RC settling to half an LSB from its plate's step (the drivers' characterization,
    ``flow.capdriver.model``, where it exists; else 10 kOhm over the weight and 1 ns), at least 1 ns,
    rounded up to 0.1 ns."""
    dac = params.dac
    load = sum(dac.main_f) + sum(dac.diff_f) + dac.parasitic_f
    tolerance = vdd * (sum(dac.main_f) - sum(dac.diff_f)) / load / 2**params.adc_bits  # half an LSB
    slowest = 0.0
    for strength, main, diff in zip(stage_strengths(dac.driver), dac.main_f, dac.diff_f, strict=True):
        for plate in (main, diff):
            if plate <= 0:
                continue
            try:
                driver = CapDriverModel.of(pdk, strength, load_f=plate, simulate=False)
                resistance, delay = driver.resistance_ohm, max(driver.delay_rise_s, driver.delay_fall_s)
            except (LookupError, RuntimeError):
                resistance, delay = 10e3 / strength, 1e-9
            tau = resistance * plate * (load - plate) / load
            slowest = max(slowest, delay + tau * math.log(max(2.0, 2 * vdd * plate / load / tolerance)))
    return math.ceil(max(1e-9, 2 * slowest) / 1e-10) * 1e-10


def runs(pdk: str, params: Params) -> dict[str, TbParams]:
    """The testbench runs that characterize ``params`` in ``pdk``: every stage up and back down, at
    the PDK's supply, in a window its slowest stage settles in within its first half
    (``settling``); and the plates' Monte Carlo at each Pelgrom coefficient and gradient
    (``PELGROMS`` x ``GRADIENTS_PER_UM``, ``MC_RUNS`` draws each: ``mc_a<0.1 %·sqrt(fF)>_g<ppm/mm>``)."""
    supply = round(importlib.import_module(f"pdk.{pdk}.hdl21.site").install.supply_voltage(h.pdk.Corner.TYP), 4)
    window = _window_s(pdk, params, supply)
    settling = TbParams(
        pdk=pdk, params=params, vdd=supply, window_s=window, waveform_sample_interval_s=window / SAMPLES_PER_WINDOW
    )
    return {"settling": settling} | {
        f"mc_a{round(pelgrom * 1000)}_g{round(gradient * 1e9)}": replace(
            settling, pelgrom=pelgrom, gradient_per_um=gradient, mc_runs=MC_RUNS
        )
        for pelgrom in PELGROMS
        for gradient in GRADIENTS_PER_UM
    }


def record(measurements: dict[str, Meas]) -> Record:
    """The record of one instance from its runs' measurements (``runs``): the metrics
    (``analysis.metrics``), the settling and the behavioral model's step by stage (which
    ``flow.cdac.model`` reads), and the plates' Monte Carlo over its conditions; a stage that does
    not settle in its window's first half raises. The Monte Carlo runs' measurements are kept (their
    drawn plates, for the converter's calibration)."""
    settling = analyze_settling(measurements["settling"])
    if not settling.settled:
        raise RuntimeError(f"a stage did not settle within half of its {settling.window_s:.3g} s window")
    mismatch = tuple(analyze_mismatch(meas) for name, meas in measurements.items() if name.startswith("mc_"))
    middle = (
        [plot_dac_inl(mismatch[len(mismatch) // 2]), plot_dac_dnl(mismatch[len(mismatch) // 2])] if mismatch else []
    )
    figures = (
        [
            plot_mismatch_inl(mismatch),
            plot_mismatch_gap(mismatch),
            plot_mismatch_dac_inl(mismatch),
            plot_mismatch_gradient(mismatch),
        ]
        if mismatch
        else []
    )
    return Record(
        metrics=metrics(settling=settling, mismatch=mismatch),
        details=[plot_settling_stage(settling), plot_model_stage(settling), *figures, *middle],
        # the runs whose measurements are kept, by label: the viewer shows the settling's waveforms
        waves={"settling": "settling"} | {name: name for name in measurements if name.startswith("mc_")},
    )
