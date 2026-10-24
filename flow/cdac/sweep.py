"""The CDAC's design space (``flow.sweep``): the array of every converter of ``flow.adc.sweep``
with its drivers, in TSMC65, at that converter's resolution: every ADC array (``ADC_ARRAYS``, each
sized through its extraction in TSMC65, ``flow.caparray.sizing``) at one bit more than its DAC's
steps (the free first comparison), 61 instances.

The drivers are the generic cells the ADC model stands in with, derived from the array's plates
(``flow.cdac.subckt.driver_strengths``: each stage's drive scaled with its plate to settle in about
1 ns). Each instance switches every stage alone, both ways (``flow.cdac.sim``): its settling to half
an LSB, its drivers' delay and the time constant the behavioral ADC settles it with, by stage. One
Spectre run, a few minutes beside other jobs; a window too short for a stage to settle in its first
half is doubled and run again.
"""

from __future__ import annotations

import importlib
from pathlib import Path

import hdl21 as h

from flow.caparray.subckt import CapArrayConfig
from flow.capdriver.subckt import Cells
from flow.pipeline import Plot, Record

from .subckt import Cdac, CdacParams, cdac_params


@h.paramclass
class CdacSettling:
    """A CDAC and the converter's resolution its settling is measured to."""

    dac = h.Param(dtype=CdacParams, desc="The CDAC")
    adc_bits = h.Param(dtype=int, desc="The converter's resolution: settling is to half its LSB")


def settling_params(pdk: str, config: CapArrayConfig, adc_bits: int, *, cells: Cells = Cells.GENERIC) -> CdacSettling:
    """The characterization of ``config``'s CDAC in ``pdk`` for an ``adc_bits`` converter."""
    return CdacSettling(dac=cdac_params(pdk, config, cells=cells), adc_bits=adc_bits)


def GENERATOR(params: CdacSettling) -> h.Module:
    return Cdac(params.dac)


ATTEMPTS = 3  # windows tried, each twice the last


def instances(pdk: str) -> list[CdacSettling]:
    """Each ADC instance's CDAC at its resolution, once however many converters share it."""
    from flow.adc.sweep import instances as adc_instances
    from flow.sweep.runner import digest

    arrays = {(digest(adc.cdac), adc.adc_bits): adc for adc in adc_instances(pdk)}
    settlings = (settling_params(pdk, adc.cdac, adc.adc_bits) for adc in arrays.values())
    return list({digest(settling): settling for settling in settlings}.values())


def cost(pdk: str, params: CdacSettling) -> float:
    return float(params.dac.driver.n_stages)


def characterize(run_dir: Path, pdk: str, params: CdacSettling) -> Record:
    from flow.analysis.io import write_measurement

    from .analysis import analyze_cdac_settling, full_scale_v
    from .sim import SAMPLES_PER_WINDOW, CdacTbParams, measure, settling_window_s, top_plates

    supply = round(importlib.import_module(f"pdk.{pdk}.hdl21.site").install.supply_voltage(h.pdk.Corner.TYP), 4)
    window = settling_window_s(pdk, params.dac, params.adc_bits, supply)
    for attempt in range(ATTEMPTS):
        tb = CdacTbParams(
            pdk=pdk,
            vdd=supply,
            dac=params.dac,
            adc_bits=params.adc_bits,
            window_s=window,
            waveform_sample_interval_s=window / SAMPLES_PER_WINDOW,
        )
        measurement = measure(run_dir / f"window_{attempt}", tb)
        result = analyze_cdac_settling(measurement)
        if result.settled:
            break
        window *= 2
    else:
        raise RuntimeError(f"a stage did not settle within half of a {window / 2:.3g} s window")
    path = write_measurement(run_dir / "result.h5", top_plates(measurement))
    stages = list(range(len(result.settling_s)))
    return Record(
        metrics={
            "stages": float(len(stages)),
            "full_scale_v": full_scale_v(params.dac, supply),
            "lsb_v": result.lsb_v,
            "settling_max_s": float(max(result.settling_s)),
            "settling_msb_s": float(result.settling_s[0]),
            "delay_max_s": float(max(result.delay_s)),
            "tau_max_s": float(max(result.tau_s)),
            "window_s": result.window_s,
            # the simulator's precision: the steps against the capacitances'
            "step_error_lsb": result.step_error_lsb,
        },
        details=[
            Plot(
                name="settling_stage",
                title="Settling to half an LSB by stage (the slower direction)",
                x_label="Stage (C0, the MSB, first)",
                y_label="Settling time (s)",
                x=stages,
                series={"settling": list(map(float, result.settling_s))},
            ),
            Plot(
                name="model_stage",
                title="The behavioral model's step by stage: its start and time constant",
                x_label="Stage (C0, the MSB, first)",
                y_label="Time (s)",
                x=stages,
                series={"delay": list(map(float, result.delay_s)), "time constant": list(map(float, result.tau_s))},
            ),
        ],
        waves={"settling": str(path.relative_to(Path(__file__).resolve().parents[2]))},
    )
