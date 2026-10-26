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

import hdl21 as h

from flow.caparray.layout import ADC_ARRAYS
from flow.caparray.model import CapArrayModel
from flow.capdriver.model import CapDriverModel, driver_strengths
from flow.capdriver.subckt import CapDriverParams, Cells, stage_strengths
from flow.pipeline import Meas, Record, family

from .analysis import analyze_settling, metrics
from .params import SAMPLES_PER_WINDOW, Params, TbParams, _Dac
from .plots import plot_model_stage, plot_settling_stage


# the arrays in TSMC65, where they are extracted; the 14-bit ones first, as they take longest
@family(pdks=("tsmc65",), pdk=lambda pdk: (pdk,), array=tuple(reversed(ADC_ARRAYS)))
def adc_array(pdk: str, array: str) -> Params:
    """The CDAC of the ADC array ``array`` (``ADC_ARRAYS``) in ``pdk``, at its converter's
    resolution: its plates as its extraction gives them (``CapArrayModel.of``), its drivers the
    generic cells derived from them (``driver_strengths``)."""
    config = ADC_ARRAYS[array]
    plates = CapArrayModel.of(pdk, config)
    return Params(
        dac=_Dac(
            driver=CapDriverParams(
                n_stages=len(plates.main_f), strengths=driver_strengths(pdk, config, plates), cells=Cells.GENERIC
            ),
            main_f=tuple(float(c) for c in plates.main_f),
            diff_f=tuple(float(c) for c in plates.diff_f),
            parasitic_f=float(plates.parasitic_f),
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
    """The one testbench run that characterizes ``params`` in ``pdk``: every stage up and back down,
    at the PDK's supply, in a window its slowest stage settles in within its first half."""
    supply = round(importlib.import_module(f"pdk.{pdk}.hdl21.site").install.supply_voltage(h.pdk.Corner.TYP), 4)
    window = _window_s(pdk, params, supply)
    return {
        "settling": TbParams(
            pdk=pdk, params=params, vdd=supply, window_s=window, waveform_sample_interval_s=window / SAMPLES_PER_WINDOW
        )
    }


def record(measurements: dict[str, Meas]) -> Record:
    """The record of one instance from its run's measurement (``runs``): the metrics
    (``analysis.metrics``), the settling and the behavioral model's step by stage (which
    ``flow.cdac.model`` reads); a stage that does not settle in its window's first half raises."""
    settling = analyze_settling(measurements["settling"])
    if not settling.settled:
        raise RuntimeError(f"a stage did not settle within half of its {settling.window_s:.3g} s window")
    return Record(
        metrics=metrics(settling=settling),
        details=[plot_settling_stage(settling), plot_model_stage(settling)],
        # the run the viewer shows the waveforms of, by label
        waves={"settling": "settling"},
    )
