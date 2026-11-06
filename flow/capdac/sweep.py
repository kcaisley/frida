"""The capacitive DAC's design space: every array of the ADC study, one grid, and FRIDA-1's array by
name (``frida1``); the testbench runs that characterize one instance (``runs``) and the record they
make (``record``).

At 10, 12 and 14 bits, at one and two kT/C minimums of switched capacitance, each with its weights
built both ways (``WeightImpl``): the binary array, and each redundant scheme with 2, 4 and 6 extra
cycles. 2 x 3 x 2 binary arrays and 3 x 3 x 3 x 2 x 2 redundant ones, 120 in all; and FRIDA-1's
fabricated array, whose 5 extra cycles the grid leaves out: 121 instances.

Each instance is the array as the PDK draws it, its drivers sized to settle each stage within its
``settle_ps`` (``flow.capdac.sim``): every stage switched alone, both ways, in a window four times
that (a stage that misses it by up to twice still settles in its window's first half): its settling
to half an LSB, its drivers' delay and the time constant the behavioral ADC settles it with, by
stage; and its plates' Monte Carlo at three Pelgrom coefficients, from an assumed 0.1 %·sqrt(fF)
to about Tripathi and Murmann's lateral MOM (0.85 %, TCAS-I 2014).
"""

import importlib
import math
from dataclasses import replace

import hdl21 as h

from flow.pipeline import Meas, Record, every, grid, named, values, widen

from .analysis import analyze_mismatch, analyze_settling, metrics
from .params import Params, Redundancy, TbParams, WeightImpl
from .plots import (
    plot_dac_dnl,
    plot_dac_inl,
    plot_mismatch_dac_inl,
    plot_mismatch_gap,
    plot_mismatch_inl,
    plot_model_stage,
    plot_settling_stage,
)


@grid
def arrays() -> dict[str, Params]:
    """The binary arrays and the redundant ones, each at every resolution, capacitance and weight build."""
    binary = widen(Params(redundancy=Redundancy.BINARY, extra=0))
    redundant = widen(Params())
    redundant.redundancy = values(Redundancy.MSB_SPLIT, Redundancy.LSB_SPLIT, Redundancy.MSB_REDIST)
    redundant.extra = values(2, 4, 6)
    for space in (binary, redundant):
        space.bits = values(10, 12, 14)
        space.scale = values(1, 2)
        space.weight_impl = every(WeightImpl)
    return {"binary": binary, "redundant": redundant}


@named
def frida1() -> Params:
    """FRIDA-1's fabricated array (the defaults): 12 bits in 16 stages, MSB redistribution with 5
    extra cycles, at twice the minimum capacitance."""
    return Params()


def runs(pdk: str, params: Params) -> dict[str, TbParams]:
    """The testbench runs that characterize ``params`` in ``pdk``: every stage up and back down, at
    the PDK's supply, in a window four times the stages' settling time, its output every 2000th of
    it (``settling``); and the plates' Monte Carlo, a hundred draws at each of Pelgrom's
    coefficients 0.1, 0.5 and 1 %·sqrt(fF) (``mc_a<0.1 %·sqrt(fF)>``)."""
    supply = round(importlib.import_module(f"pdk.{pdk}.hdl21.site").install.supply_voltage(h.pdk.Corner.TYP), 4)
    window = math.ceil(4 * params.settle_ps / 100) * 100e-12
    settling = TbParams(pdk=pdk, params=params, vdd=supply, window_s=window, waveform_sample_interval_s=window / 2000)
    return {"settling": settling} | {
        f"mc_a{round(pelgrom * 1000)}": replace(settling, pelgrom=pelgrom, mc_runs=100)
        for pelgrom in (0.001, 0.005, 0.010)
    }


def record(measurements: dict[str, Meas]) -> Record:
    """The record of one instance from its runs' measurements (``runs``): the metrics
    (``analysis.metrics``), the settling and the behavioral model's step by stage (which
    ``flow.capdac.model`` reads), and the plates' Monte Carlo over its conditions; a stage that does
    not settle in its window's first half raises. The Monte Carlo runs' measurements are kept (their
    drawn plates, for the converter's calibration)."""
    monte_carlo = {name: meas for name, meas in measurements.items() if meas.param.mc_runs}
    settling = analyze_settling(next(meas for meas in measurements.values() if not meas.param.mc_runs))
    if not settling.settled:
        raise RuntimeError(f"a stage did not settle within half of its {settling.window_s:.3g} s window")
    mismatch = tuple(analyze_mismatch(meas) for meas in monte_carlo.values())
    middle = mismatch[len(mismatch) // 2 :][:1]
    figures = (
        [plot_mismatch_inl(mismatch), plot_mismatch_gap(mismatch), plot_mismatch_dac_inl(mismatch)] if mismatch else []
    )
    return Record(
        metrics=metrics(settling=settling, mismatch=mismatch),
        details=[
            plot_settling_stage(settling),
            plot_model_stage(settling),
            *figures,
            *(plot(result) for result in middle for plot in (plot_dac_inl, plot_dac_dnl)),
        ],
        # the runs whose measurements are kept, by label: the viewer shows the settling's waveforms
        waves={"settling": "settling"} | {name: name for name in monte_carlo},
    )
