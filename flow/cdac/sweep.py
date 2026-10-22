"""The CDAC's design space (``flow.sweep``): every ADC variant's array (``flow.caparray.layout``'s
``ADC_VARIANTS``, extracted in TSMC65) with its drivers, in TSMC65, named as ``flow.adc.sweep``
names them.

A topology is the resolution (10 to 14 bits), a sizing the redundant decisions and how the array
spends them; the converter's resolution is one bit more than the nominal (the free first
comparison, as ``flow.adc.sweep``'s). The drivers are the generic cells the ADC model stands in
with, at the array's strengths. Each instance switches every stage alone, both ways
(``flow.cdac.sim``): its settling to half an LSB, its drivers' delay and the time constant the
behavioral ADC settles it with, by stage. One Spectre run, under two minutes; a window too short for
a stage to settle in its first half is doubled and run again.
"""

from __future__ import annotations

import importlib
from pathlib import Path

import hdl21 as h

from flow.caparray.layout import ADC_VARIANTS, REDUNDANCY
from flow.caparray.subckt import CapArrayConfig, get_caparray_weights
from flow.capdriver.subckt import Cells
from flow.sweep import Detail, Record

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


TOPOLOGIES = {f"{bits}b": {"bits": bits} for bits in (10, 11, 12, 13, 14)}
# plus<n> FRIDA's sub-radix-2 overlay, plus<n>_start, _spread, _end and _both binary weights with n of
# them repeated at the start, along the chain, at the end or at both ends
SIZINGS = {"plus0": {"extra": 0, "variant": ""}} | {
    f"plus{extra}{suffix}": {"extra": extra, "variant": suffix} for extra in range(1, 7) for suffix in REDUNDANCY
}
ATTEMPTS = 3  # windows tried, each twice the last


def array(topology: str, sizing: str) -> CapArrayConfig:
    """The instance's ADC variant."""
    return ADC_VARIANTS[f"{TOPOLOGIES[topology]['bits']}b_plus{SIZINGS[sizing]['extra']}{SIZINGS[sizing]['variant']}"]


def params(pdk: str, topology: str, sizing: str) -> CdacSettling | None:
    if pdk != "tsmc65":  # the variants' arrays are extracted in TSMC65 only
        return None
    config = array(topology, sizing)
    return settling_params(pdk, config, config.n_dac + 1)


def cost(pdk: str, topology: str, sizing: str) -> float:
    return float(len(get_caparray_weights(array(topology, sizing))))


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
            Detail(
                name="settling_stage",
                title="Settling to half an LSB by stage (the slower direction)",
                x_label="Stage (C0, the MSB, first)",
                y_label="Settling time (s)",
                x=stages,
                series={"settling": list(map(float, result.settling_s))},
            ),
            Detail(
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
