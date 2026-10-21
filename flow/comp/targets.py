"""The comparator's targets (``python -m flow comp.<target>``)."""

from __future__ import annotations

from pathlib import Path

from flow import new_run
from flow.analysis.comp import analyze_comp_common_mode, analyze_comp_offset_noise
from flow.analysis.io import read_measurement
from flow.analysis.plots import (
    plot_comp_common_mode_campaign,
    plot_comp_offset_noise,
    plot_comp_sampling_campaign,
)
from flow.analysis.studies import BASE_PATH
from flow.analysis.types import MeasComp
from flow.comp.analysis import analyze_comp_candidate, analyze_comp_delay, analyze_comp_power, analyze_comp_timing
from flow.comp.layout import PDKS
from flow.comp.plots import (
    plot_comp_candidate_sweep,
    plot_comp_common_mode,
    plot_comp_delay,
    plot_comp_energy,
    plot_comp_noise_power_tradeoff,
)
from flow.sweep import runner as sweep_runner

from . import layout, sim


def hdl21_comp_perf_vs_size() -> Path:
    """The size sweep: 296 generated sizings and FRIDA-1, in TSMC65."""
    return sim.hdl21_comp_perf_vs_size(new_run("sim", "comp", "hdl21_comp_perf_vs_size"))


def characterization() -> Path:
    """Delay, noise and power of the six topologies over the common mode, in every PDK."""
    return sim.comp_characterization(new_run("sim", "comp", "characterization"))


def frida1_fixed_input_noise() -> Path:
    """The FRIDA-1 comparator's S-curve at a fixed input, in TSMC65."""
    return sim.frida1_fixed_input_noise(new_run("sim", "comp", "frida1_fixed_input_noise"))


def layout_frida1_manual() -> Path:
    """FRIDA-1's comparator by its hand-written floorplan, in every PDK with every tool."""
    return layout.comp_frida1_manual_all_pdks(new_run("layout", "comp", "frida1_manual"))


def layout_c040_manual() -> Path:
    """The size sweep's example double tail (c040) by its hand-written floorplan, in every PDK."""
    return layout.comp_c040_manual_all_pdks(new_run("layout", "comp", "c040_manual"))


def layout_strongarm() -> Path:
    """The characterization's StrongARM by its hand-written floorplan, in every PDK."""
    return layout.comp_strongarm_all_pdks(new_run("layout", "comp", "strongarm"))


def layout_triple_tail() -> Path:
    """The characterization's triple tail by its hand-written floorplan, in every PDK."""
    return layout.comp_triple_tail_all_pdks(new_run("layout", "comp", "triple_tail"))


def layout_double_tail() -> Path:
    """The characterization's double tail by its hand-written floorplan, in every PDK."""
    return layout.comp_double_tail_all_pdks(new_run("layout", "comp", "double_tail"))


def layout_double_tail_self_timed() -> Path:
    """The characterization's self-timed double tail by its hand-written floorplan, in every PDK."""
    return layout.comp_double_tail_self_timed_all_pdks(new_run("layout", "comp", "double_tail_self_timed"))


def layout_double_tail_modified() -> Path:
    """The characterization's modified double tail by its hand-written floorplan, in every PDK."""
    return layout.comp_double_tail_modified_all_pdks(new_run("layout", "comp", "double_tail_modified"))


def layout_double_tail_modified_self_timed() -> Path:
    """The characterization's self-timed modified double tail by its floorplan, in every PDK."""
    return layout.comp_double_tail_modified_self_timed_all_pdks(
        new_run("layout", "comp", "double_tail_modified_self_timed")
    )


def layout_frida1_auto() -> Path:
    """FRIDA-1's comparator placed by ALIGN on its own, then every tool, in every PDK."""
    return layout.comp_frida1_auto_all_pdks(new_run("layout", "comp", "frida1_auto"))


def layout_c040_auto() -> Path:
    """c040 placed by ALIGN on its own, then every tool, in every PDK."""
    return layout.comp_c040_auto_all_pdks(new_run("layout", "comp", "c040_auto"))


def layout_mos_inv() -> Path:
    """One NMOS and one PMOS row cell from each PDK's hand-written netlist, in every PDK."""
    return layout.mos_inv_all_pdks(new_run("layout", "comp", "mos_inv"))


def layout_all() -> Path:
    """Every comparator layout above, each in every PDK."""
    return layout.all_comp_layouts(new_run("layout", "comp", "all"))


def sweep() -> None:
    """The comparator's sweep in a fresh run, every PDK: characterized, laid out, tabulated."""
    sweep_runner.run(["comp"], sweep_runner.PDKS, 36)
    sweep_runner.layout(["comp"], 28)
    sweep_runner.table(["comp"], 16)


# ---- studies: figures of archived runs, into build/analysis/<block>/<timestamp>


def behavioral_offset_noise_study() -> tuple[Path, ...]:
    """Fit offset and noise of the behavioral comparator block simulated alone.

    The input is one behavioral MeasComp from ``flow.scans.scan_behavioral``:
    61 differential inputs within +/-1.5 mV at 0.7 V common mode, 400
    decisions each. It uses the same S-curve analysis as physical comparator
    sweeps.
    """
    output_dir = new_run("analysis", "comp")
    path = BASE_PATH / "build/scan_behavioral/20261010_073028_frida2_comparator/comparator.h5"
    measurement = read_measurement(path)
    if not isinstance(measurement, MeasComp):
        raise TypeError(f"{path} contains {type(measurement).__name__}, expected MeasComp")
    return plot_comp_offset_noise(
        [measurement],
        analyze_comp_offset_noise([measurement]),
        output_path=output_dir / "frida2_behavioral_comparator_offset_noise",
    )


def system_common_mode_study() -> tuple[Path, ...]:
    """Analyze and plot separate ADC00–ADC03 comparator common-mode campaigns."""
    output_dir = new_run("analysis", "comp")

    meas_read_dir = BASE_PATH / "build/scan_comp/20260805_171216"
    measurements = []
    for path in sorted(meas_read_dir.glob("*.h5")):
        measurement = read_measurement(path)
        if not isinstance(measurement, MeasComp):
            raise TypeError(f"{path} contains {type(measurement).__name__}, expected MeasComp")
        measurements.append(measurement)

    artifacts = []
    for adc_index in sorted({measurement.index or 0 for measurement in measurements}):
        adc_measurements = [measurement for measurement in measurements if (measurement.index or 0) == adc_index]
        grouped: dict[float, list[MeasComp]] = {}
        for measurement in adc_measurements:
            grouped.setdefault(float(measurement.tb.vin_cm.dc), []).append(measurement)
        offsets = [analyze_comp_offset_noise(grouped[value]) for value in sorted(grouped)]
        artifacts.extend(
            plot_comp_common_mode_campaign(
                adc_measurements,
                offsets,
                analyze_comp_common_mode(adc_measurements, offsets=offsets),
                output_path=output_dir / f"adc{adc_index:02d}_comparator_common_mode",
            )
        )
    return tuple(artifacts)


def system_sampling_noise_study() -> tuple[Path, ...]:
    """Analyze and plot separate ADC00–ADC03 track/hold comparator campaigns."""
    output_dir = new_run("analysis", "comp")

    base_meas_read_dir = BASE_PATH / "build/scan_comp/20260805_183915"
    correction_meas_read_dir = BASE_PATH / "build/scan_comp/20260805_192902"
    base_measurements = []
    for path in sorted(base_meas_read_dir.glob("*.h5")):
        measurement = read_measurement(path)
        if not isinstance(measurement, MeasComp):
            raise TypeError(f"{path} contains {type(measurement).__name__}, expected MeasComp")
        base_measurements.append(measurement)
    correction_measurements = []
    for path in sorted(correction_meas_read_dir.glob("*.h5")):
        measurement = read_measurement(path)
        if not isinstance(measurement, MeasComp):
            raise TypeError(f"{path} contains {type(measurement).__name__}, expected MeasComp")
        correction_measurements.append(measurement)

    # A curve is one ADC, P-side rail coupling, and sampling mode. Every curve
    # in the correction run replaces the base run's curve of the same key.
    corrected_curves = {
        (
            measurement.index or 0,
            float(measurement.param.requested_dac_rail_percent or 0.0),
            measurement.param.sampling_mode,
        )
        for measurement in correction_measurements
    }
    measurements = [
        measurement
        for measurement in base_measurements
        if (
            measurement.index or 0,
            float(measurement.param.requested_dac_rail_percent or 0.0),
            measurement.param.sampling_mode,
        )
        not in corrected_curves
    ]
    measurements.extend(correction_measurements)

    artifacts = []
    for adc_index in sorted({measurement.index or 0 for measurement in measurements}):
        grouped: dict[tuple[float, str], list[MeasComp]] = {}
        for measurement in measurements:
            if (measurement.index or 0) == adc_index:
                grouped.setdefault(
                    (float(measurement.param.requested_dac_rail_percent or 0.0), measurement.param.sampling_mode), []
                ).append(measurement)
        groups = [grouped[key] for key in sorted(grouped)]
        artifacts.extend(
            plot_comp_sampling_campaign(
                groups,
                [analyze_comp_offset_noise(group) for group in groups],
                output_path=output_dir / f"adc{adc_index:02d}_comparator_sampling_noise",
            )
        )
    return tuple(artifacts)


def candidate_sweep_study() -> tuple[Path, ...]:
    """Analyze the complete generated-comparator noise/power/timing campaign."""
    output_dir = new_run("analysis", "comp")

    # the August campaign with its waveforms renamed to today's CompNets (clock, comp_p/comp_n,
    # vin_*, vout_* -> clk, latch_p/latch_n, inp/inn, outp/outn); nothing else changed
    meas_read_dir = BASE_PATH / "build/comp/frida65_candidate_scurve_power_netnames/candidates"
    measurements = []
    candidates = []
    for path in sorted(meas_read_dir.glob("*/result.h5")):
        measurement = read_measurement(path)
        if not isinstance(measurement, MeasComp):
            raise TypeError(f"{path} contains {type(measurement).__name__}, expected MeasComp")
        measurements.append(measurement)
        candidates.append(
            analyze_comp_candidate(
                measurement,
                offset=analyze_comp_offset_noise([measurement]),
                timing=analyze_comp_timing([measurement]),
                power=analyze_comp_power([measurement]),
            )
        )
    if len({candidate.candidate_id for candidate in candidates}) != len(candidates):
        raise ValueError("comparator candidate campaign contains duplicate candidate IDs")
    return (
        *plot_comp_candidate_sweep(
            measurements,
            candidates,
            highlights={"c040_half_b6b25f4b": "Example double tail"},
            output_path=output_dir / "comp_candidate_noise_power_settling",
        ),
        *plot_comp_noise_power_tradeoff(
            candidates,
            highlights={"c040_half_b6b25f4b": "Example double tail"},
            output_path=output_dir / "comp_candidate_noise_power_tradeoff",
        ),
    )


def characterization_study() -> tuple[Path, ...]:
    """Compare the six comparator topologies' delay, noise, energy and offset over the common mode, in every PDK."""
    output_dir = new_run("analysis", "comp")

    meas_read_dir = BASE_PATH / "build/sim/comp/comp_characterization/20261018_003552"
    topologies = (
        ("double_tail_self_timed", "double_tail_self_timed: self-timed"),
        ("double_tail", "double_tail: double tail"),
        ("double_tail_modified_self_timed", "double_tail_modified_self_timed"),
        ("double_tail_modified", "double_tail_modified: modified double tail"),
        ("triple_tail", "triple_tail: triple tail"),
        ("strongarm", "strongarm: StrongARM"),
    )
    labels = [label for _name, label in topologies]
    artifacts = []
    for pdk in PDKS:
        sweeps = {}
        for name, _label in topologies:
            for sweep in ("delay", "noise"):
                measurements = []
                for path in sorted(meas_read_dir.glob(f"{pdk}/{name}/{sweep}/*/result.h5")):
                    measurement = read_measurement(path)
                    if not isinstance(measurement, MeasComp):
                        raise TypeError(f"{path} contains {type(measurement).__name__}, expected MeasComp")
                    measurements.append(measurement)
                sweeps[name, sweep] = sorted(measurements, key=lambda item: float(item.param.vin_cm_values_v[0]))
        delays = [
            analyze_comp_delay(sweeps[name, "delay"], timing=analyze_comp_timing(sweeps[name, "delay"]))
            for name, _label in topologies
        ]
        common_modes = [
            analyze_comp_common_mode(
                sweeps[name, "noise"], offsets=[analyze_comp_offset_noise([item]) for item in sweeps[name, "noise"]]
            )
            for name, _label in topologies
        ]
        pdk_dir = output_dir / pdk
        artifacts += [
            *plot_comp_delay(delays, labels=labels, output_path=pdk_dir / "comp_delay"),
            *plot_comp_common_mode(delays, common_modes, labels=labels, output_path=pdk_dir / "comp_common_mode"),
            *plot_comp_energy(
                [analyze_comp_power(sweeps[name, "noise"]) for name, _label in topologies],
                common_modes,
                labels=labels,
                output_path=pdk_dir / "comp_energy",
            ),
        ]
    return tuple(artifacts)
