"""The capacitive DAC's design space: every array of the ADC study, one grid, and FRIDA-1's array by
name (``frida1``); the testbench runs that characterize one instance (``runs``) and the record they
make (``results``).

At 10, 12 and 14 bits, at one and two kT/C minimums of switched capacitance, each with its weights
built both ways (``WeightImpl``): the binary array, and each redundant scheme with 2, 4 and 6 extra
cycles. 2 x 3 x 2 binary arrays and 3 x 3 x 3 x 2 x 2 redundant ones, 120 in all; and FRIDA-1's
fabricated array, whose 5 extra cycles the grid leaves out: 121 instances. A kit runs those its
drivers can be sized for (``params.valid``).

Each instance is the array as the PDK draws it, its drivers sized to settle each stage within its
``settle_ps`` (``flow.capdac.sim``): every stage switched alone, both ways, in a window four times
that (the measurement is valid where a stage settles in its window's first half); its settling to
half an LSB, its drivers' delay and the time constant the behavioral ADC settles it with, by
stage, at the typical corner and at the slow and fast corners; each run's settling judged against
``settle_ps`` (``settles_in_time``, a bound); and its plates' Monte Carlo at three mismatch
coefficients of a capacitor, 0.1, 0.5 and 1 %·sqrt(fF) (an assumed range: the kits give none).
"""

import importlib
import math
from dataclasses import replace

import hdl21 as h

from flow.pipeline import Bound, Evidence, Level, Meas, Results, every, grid, single, values, widen

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

# not in the reference texts: the bound every instance is judged by, each stage settling within
# settle_ps at every corner run ([Razavi-ADC] Sec. 8.2.2, p. 150: t_s), from its pre-layout
# simulation on (the layout adds the plates' parasitics)


@grid(bounds=(Bound("settles_in_time", True, since=Evidence.PRELAYOUT),))
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


@single(bounds=(Bound("settles_in_time", True, since=Evidence.PRELAYOUT),))
def frida1() -> Params:
    """FRIDA-1's fabricated array (the defaults): 12 bits in 16 stages, MSB redistribution with 5
    extra cycles, at twice the minimum capacitance."""
    return Params()


def testbenches(pdk: str, params: Params, level: Level = Level.SEARCH) -> dict[str, TbParams]:
    """The testbench runs that characterize ``params`` in ``pdk`` at ``level``: every stage up and
    back down, at the PDK's supply, in a window four times the stages' settling time, its output
    every 2000th of it (``settling``); and the plates' Monte Carlo, a hundred draws at each of the
    mismatch coefficients 0.1, 0.5 and 1 %·sqrt(fF) of a capacitor (``mc_a<0.1 %·sqrt(fF)>``); at
    ``Level.FULL`` (the flow's), the settling run at the slow corner at 90 % of the supply and hot
    (``settling_slow``) and at the fast corner at 110 % (``settling_fast``). A call without a level
    is the search's: the typical corner's runs alone."""
    supply = round(importlib.import_module(f"pdk.{pdk}.hdl21.site").install.supply_voltage(h.pdk.Corner.TYP), 4)
    # not in the reference texts: the window, four times settle_ps rounded up to 100 ps, so a step
    #   that settles within twice settle_ps does so in the window's first half (``settled``); its
    #   output every 2000th of it (2 ps at 1000 ps), well below the stages' settling
    window = math.ceil(4 * params.settle_ps / 100) * 100e-12
    settling = TbParams(pdk=pdk, params=params, vdd=supply, window_s=window, waveform_sample_interval_s=window / 2000)
    # not in the reference texts: the Monte Carlo's conditions, an assumed range of a capacitor's
    #   coefficient, 100 runs each from one seed (common random numbers: the conditions' draws are
    #   one draw scaled, so they carry one sample's spread, and their decision paths)
    benches = {"settling": settling} | {
        f"mc_a{round(pelgrom * 1000)}": replace(settling, pelgrom=pelgrom, mc_runs=100)
        for pelgrom in (0.001, 0.005, 0.010)
    }
    if level.value >= Level.FULL.value:
        # not in the reference texts: the supply corners 90 and 110 % of the nominal supply (within
        #   the kits' limits), the slow corner hot at 125 C and the fast one at 25 C; the plates drawn
        #   at the nominal supply (``nominal_vdd``)
        benches |= {
            "settling_slow": replace(
                settling, vdd=0.9 * supply, nominal_vdd=supply, corner=h.pdk.Corner.SLOW, temperature_c=125.0
            ),
            "settling_fast": replace(settling, vdd=1.1 * supply, nominal_vdd=supply, corner=h.pdk.Corner.FAST),
        }
    return benches


def results(measurements: dict[str, Meas]) -> Results:
    """The record of one instance from its runs' measurements (``runs``): the metrics
    (``analysis.metrics``), the settling and the behavioral model's step by stage (which
    ``flow.capdac.model`` reads), and the plates' Monte Carlo over its conditions; a stage that does
    not settle in its window's first half raises (its measured step would not be its final one).
    The Monte Carlo runs' measurements are kept (their drawn plates, for the converter's
    calibration)."""
    monte_carlo = {name: meas for name, meas in measurements.items() if meas.param.mc_runs}
    analyzed = {name: analyze_settling(meas) for name, meas in measurements.items() if not meas.param.mc_runs}
    for name, result in analyzed.items():
        if not result.settled:
            raise RuntimeError(f"a stage of {name} did not settle within half of its {result.window_s:.3g} s window")
    settling = analyzed.get("settling") or next(iter(analyzed.values()))
    mismatch = tuple(analyze_mismatch(meas) for meas in monte_carlo.values())
    middle = mismatch[len(mismatch) // 2 :][:1]
    figures = (
        [plot_mismatch_inl(mismatch), plot_mismatch_gap(mismatch), plot_mismatch_dac_inl(mismatch)] if mismatch else []
    )
    return Results(
        metrics=metrics(
            settling=settling,
            mismatch=mismatch,
            slow=analyzed.get("settling_slow"),
            fast=analyzed.get("settling_fast"),
        ),
        details=[
            plot_settling_stage(settling),
            plot_model_stage(settling),
            *figures,
            *(plot(result) for result in middle for plot in (plot_dac_inl, plot_dac_dnl)),
        ],
        # the runs whose measurements are kept, by label: the viewer shows the settling's waveforms
        waves={"settling": "settling"} | {name: name for name in monte_carlo},
    )
