"""The sampling switch's design space (docs/pipeline.md): its grids (``@grid``: designs with some of
their parameters widened, ``widen``, every point of each) and its named instances (``@single``); the
testbench runs that characterize one instance (``runs``) and the record they make (``results``).

The characterization's switches (FRIDA-1's transmission gate, with and without dummies, the NMOS
and the PMOS switch, the bootstrapped NMOS switch) 8 to 128 units wide and at twice their length,
and the bootstrapped switch as an on-resistance ladder (the ADC study's samplers), in every PDK.
Each instance is run on the benches every switch is characterized on (``params``): over the input
level (1/12 to 11/12 of the supply, and the supply less half the step) its input stepping by a
120th of the supply: the on-resistance into the load, the track error, the pedestal and the input's
feedthrough while holding, a bootstrap's boosted V_GS; at the nominal input those and the bandwidth
and energy a cycle; over the supply (90 and 110 % of its own besides nominal) and at the slow,
fast and hot corners, the input at its nominal level, the on-resistance and pedestal; with the
complementary clock an edge late, the pedestal; at the ADC's timing a full-scale step, the
acquisition times; the hold, at 25 C and hot, its droop; two sines of the ADC's swing, their held
samples' distortion and the behavioral model's distance from them; the held output stepped as the
ADC's first decision steps it, at the lowest level a side reaches and at the common mode, hot, its
droop. Where the runs save their devices' values, their largest voltages, the level runs' apart
from the DAC step's. Twenty-five Spectre runs an instance.
"""

from __future__ import annotations

import importlib
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
    ADC_PERIOD_S,
    ADC_PERIODS,
    ADC_STROBE_S,
    ADC_TRACK_S,
    FRIDA1,
    HOT_C,
    LEAKAGE_GMIN_S,
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
    name, its helpers an eighth of the switch, none under 4 units (the finest PDK's minimum width),
    its boost capacitor 16 units long and wide enough for 32 times the switch's gate area and 16
    times the helpers' width more (the precharge device, eight helpers wide, loads the top plate):
    V_b' at least 0.9 V_DD at every input ([Razavi-ADC] Eq. (3.70), p. 50: C_b against C_G1 + C_G2
    + C_p)."""
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
        **{
            f"bootstrap_w{width}": widen(
                Params(
                    switch_type=SwitchType.BOOTSTRAP,
                    mos_w=width,
                    boot_w=max(4, width // 8),
                    cap_w=2 * width + 8 * max(4, width // 8),
                    cap_l=16,
                )
            )
            for width in (8, 16, 32, 64, 128)
        },
    }


@grid
def long_channel() -> dict[str, Params]:
    """Each switch at twice its length: the transmission gate with and without dummies, the NMOS
    and the PMOS switch, the bootstrapped one (its boost capacitor sized as ``scaled``'s)."""
    spaces = {}
    for switch in (SwitchType.TGATE, SwitchType.NMOS, SwitchType.PMOS, SwitchType.BOOTSTRAP):
        boost = {"cap_w": 2 * 32 * 2 + 8 * 4, "cap_l": 16} if switch is SwitchType.BOOTSTRAP else {}
        space = widen(Params(switch_type=switch, mos_l=2, **boost))
        if switch is SwitchType.TGATE:
            space.dummy = every(bool)
        spaces[switch.name.lower()] = space
    return spaces


@grid
def boost_ladder() -> dict[str, Params]:
    """The bootstrapped switch as an on-resistance ladder (the ADC study's samplers), each rung by its
    width: 32 to 160 units wide, its helpers an eighth and its boost capacitor sized as
    ``scaled``'s, so every rung is boosted alike and its on-resistance falls with its width."""
    return {
        f"w{width}": widen(
            Params(
                switch_type=SwitchType.BOOTSTRAP,
                mos_w=width,
                boot_w=width // 8,
                cap_w=2 * width + 8 * (width // 8),
                cap_l=16,
            )
        )
        for width in (32, 64, 112, 160)
    }


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
    """The bootstrapped NMOS switch, 32 units wide, its boost capacitor sized as ``scaled``'s."""
    return Params(switch_type=SwitchType.BOOTSTRAP, cap_w=2 * 32 + 8 * 4, cap_l=16)


def testbenches(pdk: str, params: Params) -> dict[str, TbParams]:
    """The testbench runs that characterize ``params`` in ``pdk``, by name (each run's folder): the
    input stepping a 120th of the supply at each input level (``vin_<twelfths>``, and ``vin_top``
    the supply less half the step), at the nominal input at each other supply
    (``supply_<percent>``; the nominal one is ``vin_6``), at the slow and fast corners and hot
    (``slow``, ``fast``, ``hot``), with the complementary clock an edge late (``skew``); at the
    ADC's timing: a full-scale step (``acquire``), the input still at its nominal level, at 25 C
    and hot, at a gmin below the leakage they read (``droop``, ``droop_hot``), a sine of the ADC's swing by its cycles in the samples
    (``sine_<cycles>``), and the held output raised by the ADC's first step, hot, at the lowest
    level a side reaches and at the common mode (``dac_low``, ``dac_cm``). The level runs at the
    ends and the middle, the highest supply's and the DAC's save every transistor's operating
    values."""

    supply = importlib.import_module(f"pdk.{pdk}.hdl21.site").install.supply_voltage(h.pdk.Corner.TYP)
    nominal = TbParams(
        pdk=pdk,
        params=params,
        vdd=round(supply, 4),
        input_voltage=round(NOMINAL_VIN * supply, 4),
        input_step_v=round(SMALL_STEP * supply, 4),
    )
    benches = {
        f"vin_{round(fraction * 12)}": replace(nominal, input_voltage=round(fraction * supply, 4))
        for fraction in VIN_SWEEP
    }
    benches["vin_top"] = replace(nominal, input_voltage=round(VIN_TOP * supply, 4))
    for name in ("vin_1", "vin_6", "vin_top"):
        benches[name] = replace(benches[name], oppoint=True)
    for factor in SUPPLY_SWEEP:
        if factor != 1.0:
            benches[f"supply_{round(factor * 100)}"] = replace(
                nominal, vdd=round(factor * supply, 4), oppoint=factor == max(SUPPLY_SWEEP)
            )
    benches["slow"] = replace(nominal, corner=h.pdk.Corner.SLOW)
    benches["fast"] = replace(nominal, corner=h.pdk.Corner.FAST)
    benches["hot"] = replace(nominal, temperature_c=HOT_C)
    benches["skew"] = replace(nominal, clock_skew_s=nominal.clock_transition_time_s)
    benches["acquire"] = replace(
        nominal,
        input_step_v=round((VIN_SWEEP[-1] - VIN_SWEEP[0]) * supply, 4),
        clock_period_s=2 * ADC_TRACK_S,
        clock_high_time_s=ADC_TRACK_S,
        periods=5,
    )
    adc = replace(
        nominal,
        input_step_v=0.0,
        clock_period_s=ADC_PERIOD_S,
        clock_high_time_s=ADC_TRACK_S,
        periods=ADC_PERIODS,
        waveform_sample_interval_s=ADC_STROBE_S,
    )
    benches["droop"] = replace(adc, gmin_s=LEAKAGE_GMIN_S)
    benches["droop_hot"] = replace(adc, temperature_c=HOT_C, gmin_s=LEAKAGE_GMIN_S)
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
    # capacitor's share; flow.adc's first decision raises the lower side by a_0 = V c_0 / C_p
    # (flow.adc.analysis): in flow.adc's default array (capdac.Params()), its first main plate
    # rising and its difference plate falling, with the behavioral DAC's own parasitic
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
    levels = [measurement for measurement in [*by_vin, *by_supply] if measurement.param.oppoint]
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
