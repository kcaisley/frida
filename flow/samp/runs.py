"""The sampling switch's design space (docs/pipeline.md): its grids (``@grid``: designs with some of
their parameters widened, ``widen``, every point of each) and its named instances (``@single``); the
testbench runs that characterize one instance (``runs``) and the record they make (``results``).

The characterization's switches (FRIDA-1's transmission gate, with and without dummies, the NMOS
and the PMOS switch 8 to 128 units wide, the bootstrapped NMOS switch from 32 units) and each at
twice its length, and the bootstrapped switch as an on-resistance ladder (the ADC study's
samplers), in every PDK. Each instance is run on the benches every switch is characterized on
(``params``): over the input level (1/12 to 11/12 of the supply, and the supply less half the
step), tracking 10 ns of a 15 ns clock, its input stepping by a 120th of the supply onto the level
in mid-track and off it in mid-hold: the settled switch's on-resistance into the load, the track
error, the pedestal and the input's feedthrough while holding, a bootstrap's boosted V_GS; at the
nominal input those and the bandwidth and energy a cycle; over the supply (90 and 110 % of its own besides nominal) and at the
slow, fast and hot corners, the input at its nominal level, the on-resistance and pedestal; with
the complementary clock an edge late, the pedestal; at the ADC's timing a full-scale step, the
acquisition times, and the same step at the highest supply; the hold, at 25 C and hot, its droop;
two sines of the ADC's swing, their held samples' distortion and the behavioral model's distance
from them; the held output stepped as the ADC's first decision steps it, at the lowest level a side
reaches and at the common mode, hot, its droop. Where the runs save their devices' values, their
largest voltages, the level runs' and the full-scale steps' apart from the DAC step's. Twenty-six
Spectre runs an instance.
"""

from __future__ import annotations

import importlib
import math
from dataclasses import replace

import hdl21 as h
import numpy as np

from flow import capdac
from flow.pipeline import Meas, Results, every, grid, single, steps, widen

from .analysis import (
    analyze_acquisition,
    analyze_boost,
    analyze_droop,
    analyze_energy,
    analyze_hold,
    analyze_sine,
    analyze_stress,
    analyze_track,
    metrics,
)
from .params import (
    ADC_CM,
    ADC_FULL_SCALE,
    ADC_PERIOD_S,
    ADC_PERIODS,
    ADC_STROBE_S,
    ADC_TRACK_S,
    FRIDA1,
    HOT_C,
    LEAKAGE_GMIN_S,
    LEVEL_PERIOD_S,
    LEVEL_TRACK_S,
    NOMINAL_VIN,
    SINE_AMPLITUDE,
    SINE_CYCLES,
    SINE_SAMPLES,
    SMALL_STEP,
    SUPPLY_SWEEP,
    VIN_BOTTOM,
    VIN_SWEEP,
    VIN_TOP,
    WAVE_VIN,
    Params,
    Stimulus,
    SwitchType,
    TbParams,
    _bootstrapped,
)
from .plots import (
    plot_feedthrough_vin,
    plot_pedestal_supply,
    plot_pedestal_vin,
    plot_ron_supply,
    plot_ron_vin,
    plot_track_error_vin,
    plot_vgs_vin,
)


@grid
def scaled() -> dict[str, Params]:
    """Each switch 8 to 128 units wide (a quarter to four times FRIDA-1's): the transmission gate
    with and without dummies, the NMOS and the PMOS switch, and the bootstrapped one, each width by
    name, its helpers, boost capacitor and bottom-plate switch sized together for the bench's load
    (``params._bootstrapped``: V_b' at least 0.9 V_DD by [Razavi-ADC] Eq. (3.70), p. 50, with every
    gate on the boosted node counted). The 8- and 16-unit bootstrapped switches are left out by
    ``params.valid``: the bottom-plate switch that lifts their bottom plate slowly enough has a
    gate over twice their own (``params.BOTTOM_GATE_MAX``)."""
    tgate = widen(Params(switch_type=SwitchType.TGATE))
    tgate.mos_w = steps(8, 128, n=5, log=True)
    tgate.dummy = every(bool)
    nmos = widen(Params(switch_type=SwitchType.NMOS))
    nmos.mos_w = steps(8, 128, n=5, log=True)
    pmos = widen(Params(switch_type=SwitchType.PMOS))
    pmos.mos_w = steps(8, 128, n=5, log=True)
    return {
        "tgate": tgate,
        "nmos": nmos,
        "pmos": pmos,
        **{f"bootstrap_w{width}": widen(_bootstrapped(width)) for width in (8, 16, 32, 64, 128)},
    }


@grid
def long_channel() -> dict[str, Params]:
    """Each switch at twice its length: the transmission gate with and without dummies, the NMOS
    and the PMOS switch, the bootstrapped one (sized as ``scaled``'s, for its own gate)."""
    spaces = {}
    for switch in (SwitchType.TGATE, SwitchType.NMOS, SwitchType.PMOS, SwitchType.BOOTSTRAP):
        base = _bootstrapped(32, 2) if switch is SwitchType.BOOTSTRAP else Params(switch_type=switch, mos_l=2)
        space = widen(base)
        if switch is SwitchType.TGATE:
            space.dummy = every(bool)
        spaces[switch.name.lower()] = space
    return spaces


@grid
def boost_ladder() -> dict[str, Params]:
    """The bootstrapped switch as an on-resistance ladder (the ADC study's samplers), each rung by its
    width: 32 to 160 units wide, each sized as ``scaled``'s (``params._bootstrapped``), so every
    rung is boosted alike and its on-resistance falls with its width."""
    return {f"w{width}": widen(_bootstrapped(width)) for width in (32, 64, 112, 160)}


@single
def frida1() -> Params:
    """FRIDA-1's fabricated sampler: the transmission gate, 32 units a side."""
    return FRIDA1


@single
def tgate_dummy() -> Params:
    """The transmission gate with half-size charge-injection dummies."""
    return Params(dummy=True)


@single
def nmos() -> Params:
    """The NMOS switch alone."""
    return Params(switch_type=SwitchType.NMOS)


@single
def bootstrap() -> Params:
    """The bootstrapped NMOS switch, 32 units wide, sized as ``scaled``'s (``params._bootstrapped``)."""
    return _bootstrapped(32)


def testbenches(pdk: str, params: Params) -> dict[str, TbParams]:
    """The testbench runs that characterize ``params`` in ``pdk``, by name (each run's folder): the
    input stepping a 120th of the supply onto each input level in mid-track and off it in mid-hold
    (``vin_<twelfths>``, and ``vin_top`` the supply less half the step, its own steps half as
    large), at the nominal input at
    each other supply (``supply_<percent>``; the nominal one is ``vin_6``), at the slow and fast
    corners and hot (``slow``, ``fast``, ``hot``), with the complementary clock an edge late
    (``skew``); at the ADC's timing: a full-scale step at the nominal supply and at the highest
    (``acquire``, ``acquire_<percent>``), the input still at its nominal level, at 25 C and hot, at
    a gmin below the leakage they read (``droop``, ``droop_hot``), a sine of the ADC's swing by its
    cycles in the samples (``sine_<cycles>``), and the held output raised by the ADC's first step,
    hot, at the lowest level a side reaches and at the common mode (``dac_low``, ``dac_cm``). The
    level runs at the ends and the middle, the highest supply's, the full-scale steps' and the
    DAC's save every transistor's operating values."""

    supply = importlib.import_module(f"pdk.{pdk}.hdl21.site").install.supply_voltage(h.pdk.Corner.TYP)
    nominal = TbParams(
        pdk=pdk,
        params=params,
        vdd=round(supply, 4),
        input_voltage=round(NOMINAL_VIN * supply, 4),
        input_step_v=round(SMALL_STEP * supply, 4),
        track_step_v=round(SMALL_STEP * supply, 4),
        clock_period_s=LEVEL_PERIOD_S,
        clock_high_time_s=LEVEL_TRACK_S,
    )
    benches = {
        f"vin_{round(fraction * 12)}": replace(nominal, input_voltage=round(fraction * supply, 4))
        for fraction in VIN_SWEEP
    }
    # not in the reference texts: the highest level's steps half the others' (SMALL_STEP V_DD / 2),
    # so that the input, a step above its level for half the periods, reaches the supply and no
    # further: VIN_TOP V_DD + SMALL_STEP V_DD / 2 = V_DD
    # Terms: V_DD the kit's nominal supply; the level VIN_TOP of it.
    # Holds for: VIN_TOP the supply less half the step.
    benches["vin_top"] = replace(
        nominal,
        input_voltage=round(VIN_TOP * supply, 4),
        input_step_v=round(SMALL_STEP * supply / 2, 4),
        track_step_v=round(SMALL_STEP * supply / 2, 4),
    )
    for name in ("vin_1", "vin_6", "vin_top"):
        benches[name] = replace(benches[name], oppoint=True)
    highest = max(SUPPLY_SWEEP)
    for factor in SUPPLY_SWEEP:
        if factor != 1.0:
            benches[f"supply_{round(factor * 100)}"] = replace(
                nominal, vdd=round(factor * supply, 4), oppoint=factor == highest
            )
    benches["slow"] = replace(nominal, corner=h.pdk.Corner.SLOW)
    benches["fast"] = replace(nominal, corner=h.pdk.Corner.FAST)
    benches["hot"] = replace(nominal, temperature_c=HOT_C)
    # not in the reference texts: the complementary clock one clock edge (its transition time) late
    # Terms: clk_b's delay over clk's, tb.clock_skew_s.
    # Holds for: a skew of the order of the edges themselves (non-overlap of one edge).
    benches["skew"] = replace(nominal, clock_skew_s=nominal.clock_transition_time_s)
    # not in the reference texts: the converter's own worst case for the switch's stress and
    # acquisition, from flow.adc's parameters (flow.samp.params: ADC_CM, ADC_FULL_SCALE, ADC_PERIOD_S,
    # ADC_TRACK_S): as tracking starts the output stands a full scale from the input (the array
    # holds the last conversion's residue), 2 A_FS, and the input has moved there no faster than a
    # full-scale sine at the Nyquist frequency, dV/dt <= 2 pi (f_s / 2) A_FS, so over no less than
    # 2 A_FS / (pi f_s A_FS) = 2 / (pi f_s)
    # Terms: A_FS a side's full-scale amplitude, ADC_FULL_SCALE of the supply; f_s the sample rate,
    #   1 / ADC_PERIOD_S; the step between ADC_CM -+ ADC_FULL_SCALE of the supply, in mid-hold.
    # Ours against the source: the levels scale with the supply (at the highest supply too), where
    #   flow.adc states them at the nominal one.
    # Holds for: flow.adc's default converter and timing; a faster input or a larger step is not
    #   the converter's.
    acquire = replace(
        nominal,
        input_step_v=round(2 * ADC_FULL_SCALE * supply, 4),
        input_transition_time_s=2 * ADC_PERIOD_S / math.pi,
        track_step_v=0.0,
        clock_period_s=ADC_PERIOD_S,
        clock_high_time_s=ADC_TRACK_S,
        periods=4,
        oppoint=True,
    )
    benches["acquire"] = replace(acquire, input_voltage=round(ADC_CM * supply, 4))
    benches[f"acquire_{round(highest * 100)}"] = replace(
        acquire,
        vdd=round(highest * supply, 4),
        input_voltage=round(ADC_CM * highest * supply, 4),
        input_step_v=round(2 * ADC_FULL_SCALE * highest * supply, 4),
    )
    adc = replace(
        nominal,
        input_step_v=0.0,
        track_step_v=0.0,
        clock_period_s=ADC_PERIOD_S,
        clock_high_time_s=ADC_TRACK_S,
        periods=ADC_PERIODS,
        waveform_sample_interval_s=ADC_STROBE_S,
    )
    benches["droop"] = replace(adc, gmin_s=LEAKAGE_GMIN_S)
    benches["droop_hot"] = replace(adc, temperature_c=HOT_C, gmin_s=LEAKAGE_GMIN_S)
    # not in the reference texts: coherent sampling, a tone of ``cycles`` whole cycles in the
    # SINE_SAMPLES samples: f_in = cycles f_s / N
    # Terms: f_s 1 / ADC_PERIOD_S, N SINE_SAMPLES; the amplitude SINE_AMPLITUDE of the supply about
    #   ADC_CM of it.
    # Holds for: cycles coprime to N (1 and 15 of 32), so every sample is a different phase.
    for cycles in SINE_CYCLES:
        benches[f"sine_{cycles}"] = replace(
            adc,
            stimulus=Stimulus.SINE,
            input_voltage=round(ADC_CM * supply, 4),
            sine_amplitude_v=round(SINE_AMPLITUDE * supply, 4),
            sine_frequency_hz=cycles / (SINE_SAMPLES * ADC_PERIOD_S),
            periods=SINE_SAMPLES + 2,
        )
    # [Razavi-ADC] Sec. 16.2.1, p. 346: monotonic switching moves one side's top plate by its
    # capacitor's share: flow.adc's first decision raises the lower side by a_0 = V c_0 / C_p
    # Terms: V the supply (the DAC's reference); c_0 the first stage's switched capacitance, its
    #   main plate rising less its difference plate falling; C_p a side's whole top-plate
    #   capacitance with the behavioral DAC's own parasitic: flow.adc's default array
    #   (capdac.Params()), by capdac.Model.switch.
    # Ours against the source: the bench moves the held output by a source through half the load
    #   (flow.samp.sim.testbench), not by a capacitor array.
    # Holds for: flow.adc's default array; the lowest level a side reaches and the common mode.
    dac = capdac.Model.Behavioral()
    main_f, diff_f = capdac.Model.plates_f(dac, "p", capdac.Params(), supply)
    before = np.zeros((1, len(main_f)), dtype=np.int64)
    after = before.copy()
    after[0, 0] = 1
    step = round(float(capdac.Model.switch(main_f, diff_f, float(dac.parasitic_f), supply, 1, before, after)[0][0]), 4)
    for name, level in (("dac_low", VIN_BOTTOM), ("dac_cm", ADC_CM)):
        benches[name] = replace(
            adc,
            input_voltage=round(level * supply, 4),
            dac_step_v=step,
            temperature_c=HOT_C,
            oppoint=True,
            gmin_s=LEAKAGE_GMIN_S,
        )
    return benches


def results(measurements: dict[str, Meas]) -> Results:
    """The record of one instance from its runs' measurements (``testbenches``): the metrics
    (``analysis.metrics``) and the plots of its sweeps over the input level and the supply."""

    by_vin = [measurements[f"vin_{round(fraction * 12)}"] for fraction in VIN_SWEEP] + [measurements["vin_top"]]
    nominal = measurements[f"vin_{round(NOMINAL_VIN * 12)}"]
    by_supply = [nominal if factor == 1.0 else measurements[f"supply_{round(factor * 100)}"] for factor in SUPPLY_SWEEP]
    corners = [measurements[name] for name in ("slow", "fast", "hot")]
    track, hold = analyze_track(by_vin), analyze_hold(by_vin)
    supply_track, supply_hold = analyze_track(by_supply), analyze_hold(by_supply)
    boost = analyze_boost(by_vin)
    dac = [measurements["dac_low"], measurements["dac_cm"]]
    full_scale = [measurements[name] for name in measurements if name.startswith("acquire")]
    levels = [measurement for measurement in [*by_vin, *by_supply, *full_scale] if measurement.param.oppoint]
    return Results(
        metrics=metrics(
            track=track,
            hold=hold,
            supply=supply_track,
            supply_hold=supply_hold,
            corners=analyze_track(corners),
            corners_hold=analyze_hold(corners),
            droop=analyze_droop([measurements["droop"], measurements["droop_hot"]]),
            skew=analyze_hold([measurements["skew"]]),
            boost=boost,
            stress=analyze_stress(levels, track=track),
            dac_stress=analyze_stress(dac, track=track),
            acquisition=analyze_acquisition([measurements["acquire"]]),
            sine=analyze_sine([measurements[f"sine_{cycles}"] for cycles in SINE_CYCLES], track=track, hold=hold),
            dac=analyze_droop(dac),
            energy=analyze_energy([nominal]),
        ),
        details=[
            plot_ron_vin(track),
            plot_track_error_vin(track),
            plot_pedestal_vin(hold),
            plot_feedthrough_vin(hold),
            plot_ron_supply(supply_track),
            plot_pedestal_supply(supply_hold),
            *([plot_vgs_vin(boost)] if bool(np.isfinite(boost.vgs_v).any()) else []),
        ],
        # the runs the viewer shows the waveforms of, by label
        waves={
            f"input {round(fraction * 12)}/12 of the supply": f"vin_{round(fraction * 12)}" for fraction in WAVE_VIN
        },
    )
