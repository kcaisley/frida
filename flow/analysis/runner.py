"""Explicit, manually invoked measurement -> analysis -> plot pipelines.

Each function pins its accepted input files or measurement directories. Small
campaigns list every H5 file; large campaigns use a narrow glob within a named
directory. There is intentionally no automatic discovery of the newest run
directory or of analysis pipelines.

Runners only load measurements, call analyses, pass results to later
analyses, save results with :func:`write_analysis` where another runner
needs them, and save figures. They never build reports.

Run one named pipeline from the repository root with:

    uv run python -m flow.analysis.runner adc_sample_rate_study

A target name is required. Outputs go to a timestamped directory beneath
``build/analysis/<domain>``. Each runner selects its input directories in source.
"""

from __future__ import annotations

import argparse
import dataclasses
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

import hdl21 as h
import matplotlib as mpl
import numpy as np

from flow.adc.sequences import (
    SEQUENCES,
    AdcSequence,
    symbol256_init8_samp16_comp11110000_logic11000011,
)
from flow.analysis import calc
from flow.analysis.adc import (
    analyze_adc_cdac_settling,
    analyze_adc_code_density_nonlinearity,
    analyze_adc_code_distribution,
    analyze_adc_code_spectrum,
    analyze_adc_decision_paths,
    analyze_adc_dynamic,
    analyze_adc_interferer,
    analyze_adc_noise,
    analyze_adc_operating_conditions,
    analyze_adc_power,
    analyze_adc_ramp,
    analyze_adc_timing_closure,
    analyze_adc_timing_summary,
    analyze_adc_transfer,
)
from flow.analysis.calibration1 import analyze_adc_calibration1
from flow.analysis.calibration2 import analyze_adc_calibration2
from flow.analysis.calibration3 import analyze_adc_calibration3
from flow.analysis.cdac import analyze_cdac_cap_mismatch, analyze_cdac_transition
from flow.analysis.comp import (
    analyze_comp_candidate,
    analyze_comp_common_mode,
    analyze_comp_delay,
    analyze_comp_offset_noise,
    analyze_comp_power,
    analyze_comp_timing,
)
from flow.analysis.io import read_extracted_calibration, read_measurement, read_measurement_param, write_analysis
from flow.analysis.plots import (
    plot_adc_calibration_weights,
    plot_adc_cdac_settling,
    plot_adc_code_distribution,
    plot_adc_code_noise,
    plot_adc_code_spectrum,
    plot_adc_conversion_energy,
    plot_adc_decision_path_density,
    plot_adc_dynamic,
    plot_adc_dynamic_sweep,
    plot_adc_interferer,
    plot_adc_noise_distribution_sweep,
    plot_adc_noise_sweep,
    plot_adc_power_sweep,
    plot_adc_ramp_histogram,
    plot_adc_ramp_nonlinearity,
    plot_adc_ramp_transfer,
    plot_adc_sequence_chip_overview,
    plot_adc_sequence_enob,
    plot_adc_static_nonlinearity,
    plot_adc_transfer,
    plot_cdac_cap_mismatch,
    plot_cdac_cap_mismatch_comparison,
    plot_comp_candidate_sweep,
    plot_comp_common_mode_campaign,
    plot_comp_noise_power_tradeoff,
    plot_comp_offset_noise,
    plot_comp_sampling_campaign,
    plot_comp_topology_study,
    plot_waveforms,
    style_measurement_text,
)
from flow.analysis.types import (
    AnalysisCdacCapMismatch,
    MeasAdc,
    MeasCdac,
    MeasComp,
)
from flow.delay.analysis import MeasDelay, analyze_delay_oscillation, analyze_delay_propagation
from flow.delay.plots import (
    plot_delay_line_control,
    plot_delay_line_supply,
    plot_delay_ring_control,
    plot_delay_ring_supply,
)
from flow.delay.sim import NOMINAL_CONTROL_V, NOMINAL_SUPPLY_V
from flow.latch.analysis import MeasLatch, analyze_latch_constraint, analyze_latch_sr, analyze_latch_timing
from flow.latch.plots import plot_latch_frequency, plot_latch_setup_hold, plot_latch_supply
from flow.ota.analysis import MeasOta, analyze_ota_ac
from flow.ota.plots import plot_ota_bode, plot_ota_common_mode, plot_ota_supply
from flow.ota.sim import NOMINAL_VCM_V
from flow.scans.params import load_board_map

timing_sequences = tuple(
    sequence for name, sequence in SEQUENCES if name.startswith("symbol256_init8_samp16_comp11110000_")
)

BASE_PATH = Path(__file__).resolve().parents[2]


# =============================================================================
# ADC studies
# =============================================================================


def adc_transfer_curve_study(output_dir: Path) -> tuple[Path, ...]:
    """Plot known-voltage static transfer curves from MeasAdc DC steps.

    Coverage: the archived ADC00 campaign only; its selected directory is
    currently absent locally. Each settled DC step supplies a known voltage,
    including inputs beyond either rail. No voltage reconstruction or fit,
    calibration acquisition, or internal SPICE waveforms are used.
    """
    meas_read_dir = BASE_PATH / "build/scan_adc/20260818_135848"
    paths = sorted(meas_read_dir.glob("[0-9][0-9][0-9][0-9]_*.h5"))
    if not paths:
        raise FileNotFoundError(meas_read_dir)
    groups: dict[int | None, list[MeasAdc]] = {}
    for path in paths:
        measurement = read_measurement(path)
        if not isinstance(measurement, MeasAdc):
            raise TypeError(f"{path} contains {type(measurement).__name__}, expected MeasAdc")
        groups.setdefault(measurement.index, []).append(measurement)
    artifacts = []
    for adc_index, measurements in sorted(groups.items(), key=lambda item: item[0] or 0):
        artifacts.extend(
            plot_adc_transfer(
                measurements,
                analyze_adc_transfer(measurements),
                output_path=output_dir / f"adc{adc_index or 0:02d}_transfer_curve",
            )
        )
    return tuple(artifacts)


def adc_ramp_nonlinearity_study(output_dir: Path) -> tuple[Path, ...]:
    """Plot code density and INL/DNL for the ADC00--ADC03 10-Hz sawtooth.

    Inputs are MeasAdc acquisitions, with uniform ramp occupancy assumed.
    Absolute input voltage is unused. Conversions next to each ramp wrap and
    saturated endpoint bins are excluded from linearity; the full histogram
    stays visible. No CDAC calibration data or internal SPICE waveforms are
    required.
    """
    meas_read_dir = BASE_PATH / "build/scan_adc/20260812_011910"
    paths = sorted(meas_read_dir.glob("[0-9][0-9][0-9][0-9]_*.h5"))
    if not paths:
        raise FileNotFoundError(meas_read_dir)
    artifacts = []
    for path in paths:
        measurement = read_measurement(path)
        if not isinstance(measurement, MeasAdc):
            raise TypeError(f"{path} contains {type(measurement).__name__}, expected MeasAdc")
        stem = f"adc{measurement.index or 0:02d}_{path.name.split('_', 1)[0]}"
        artifacts.extend(
            plot_adc_code_distribution(
                (measurement,),
                analyze_adc_code_distribution((measurement,)),
                output_path=output_dir / f"{stem}_code_density",
            )
        )
        ramp = analyze_adc_ramp(measurement)
        artifacts.extend(
            plot_adc_static_nonlinearity(
                measurement,
                analyze_adc_code_density_nonlinearity(measurement, ramp=ramp),
                output_path=output_dir / f"{stem}_inl_dnl",
            )
        )
    return tuple(artifacts)


def adc_behavioral_nonlinearity_study(output_dir: Path) -> tuple[Path, ...]:
    """Plot code density and INL/DNL of the behavioral FRIDA-2 three-layer sawtooth.

    The inputs are the held-out behavioral MeasAdc ramp captures from
    ``flow.scans.scan_behavioral``: 1,000,000 conversions each at 10 MS/s over
    eight full-scale sawtooth periods, switching the reviewed three-layer PEX
    capacitances. Seed 0 has no random capacitor mismatch; seeds 1--4 are
    Monte Carlo draws with Harpe (0.10 %·sqrt(fF)) and Tripathi
    (0.85 %·sqrt(fF)) unit mismatch. Each INL/DNL and code-density plot shows
    the capture decoded with the ideal design weights and with the
    PEX-extracted weights, the best estimate before mismatch.
    """
    read_dir = BASE_PATH / "build/scan_behavioral/20261010_114121_frida2_ramp_code_density"
    artifacts = []
    for path in sorted(read_dir.glob("seed[0-9][0-9]_ac[0-9][0-9][0-9]_check.h5")):
        measurement = read_measurement(path)
        if not isinstance(measurement, MeasAdc):
            raise TypeError(f"{path} contains {type(measurement).__name__}, expected MeasAdc")
        extracted = read_extracted_calibration(Path(str(measurement.info.readbacks["cap_table"])), measurement)
        ramps = (analyze_adc_ramp(measurement), analyze_adc_ramp(measurement, calibration=extracted))
        stem = f"frida2_3layer_behavioral_{path.stem}"
        artifacts.extend(
            plot_adc_ramp_histogram(ramps, output_path=output_dir / f"{stem}_code_density", msmt=measurement)
        )
        artifacts.extend(
            plot_adc_ramp_nonlinearity(ramps, output_path=output_dir / f"{stem}_inl_dnl", msmt=measurement)
        )
    return tuple(artifacts)


def adc_behavioral_energy_study(output_dir: Path) -> tuple[Path, ...]:
    """Plot behavioral FRIDA-2 three-layer energy per conversion versus DC input.

    Inputs are 129 behavioral MeasAdc DC captures across the full scale, 2,000
    conversions each, with the PEX capacitances and the default alternating
    A-state. The model computes VDD_DAC; the comparator and logic rails use
    PEX-measured energy per conversion, so they are flat in input.
    """
    read_dir = BASE_PATH / "build/scan_behavioral/20261010_232352_frida2_energy_vs_input"
    measurements = []
    for path in sorted(read_dir.glob("[0-9][0-9][0-9]_vin*.h5")):
        measurement = read_measurement(path)
        if not isinstance(measurement, MeasAdc):
            raise TypeError(f"{path} contains {type(measurement).__name__}, expected MeasAdc")
        measurements.append(measurement)
    return plot_adc_conversion_energy(
        measurements,
        [analyze_adc_power(measurement) for measurement in measurements],
        output_path=output_dir / "frida2_3layer_behavioral_energy_vs_input",
    )


def adc_behavioral_sample_rate_study(output_dir: Path) -> tuple[Path, ...]:
    """Plot behavioral FRIDA-2 three-layer power and spectral ENOB versus rate.

    Inputs are nine behavioral MeasAdc sine captures (-0.5 dBFS, 8,192
    conversions) with the 160-symbol recipe at 0.2-6.4 GBd, i.e. 1.25-40 MS/s.
    VDD_DAC charge is computed; comparator, logic, and driver energies and
    leakage are fitted to the FRIDA-2 three-layer PEX transient. Each rail's
    static and dynamic power are drawn as one band. ENOB uses the PEX-extracted weights and
    is limited by the assumed 0.2-ns CDAC settling time constant at high rates.
    """
    read_dir = BASE_PATH / "build/scan_behavioral/20261010_232349_frida2_sample_rate"
    measurements = []
    for path in sorted(read_dir.glob("[0-9][0-9][0-9][0-9]mbd.h5")):
        measurement = read_measurement(path)
        if not isinstance(measurement, MeasAdc):
            raise TypeError(f"{path} contains {type(measurement).__name__}, expected MeasAdc")
        measurements.append(measurement)
    return (
        *plot_adc_power_sweep(
            measurements,
            [analyze_adc_power(measurement) for measurement in measurements],
            output_path=output_dir / "frida2_3layer_behavioral_power_vs_rate",
            rate_axis="sampling",
            merge_static=True,
        ),
        *plot_adc_dynamic_sweep(
            measurements,
            [
                analyze_adc_dynamic(
                    measurement,
                    calibration=read_extracted_calibration(
                        Path(str(measurement.info.readbacks["cap_table"])), measurement
                    ),
                )
                for measurement in measurements
            ],
            output_path=output_dir / "frida2_3layer_behavioral_enob_vs_rate",
            x_axis="sample_rate",
        ),
    )


def adc_behavioral_trajectory_study(output_dir: Path) -> tuple[Path, ...]:
    """Show redundant SAR decision paths recovering from a random first decision.

    The input is one behavioral MeasAdc: 2,000 conversions at 10 MS/s of a 0-V
    input, on the C0 threshold, with every noise source. B0 goes either way,
    and the later redundant stages bring both branches to the same codes.
    """
    path = BASE_PATH / "build/scan_behavioral/20261010_114637_frida2_trajectory/trajectory_0mv.h5"
    measurement = read_measurement(path)
    if not isinstance(measurement, MeasAdc):
        raise TypeError(f"{path} contains {type(measurement).__name__}, expected MeasAdc")
    paths = analyze_adc_decision_paths(measurement)
    return plot_adc_decision_path_density(
        measurement, paths, output_path=output_dir / "frida2_3layer_behavioral_trajectory_density"
    )


def adc_behavioral_calibration_study(output_dir: Path) -> tuple[Path, ...]:
    """Calibrate behavioral FRIDA-2 three-layer captures from a known ramp and check on fresh data.

    Each capacitor draw has a training and a held-out ramp capture (eight
    periods, 1,000,000 conversions, same capacitors, independent noise).
    Calibration 1 learns BOUT weights from the same draw's behavioral CDAC
    A-to-B switching curves, and calibrations 2 and 3 from the training
    capture alone; the held-out capture is then decoded with the nominal design
    weights, the PEX-extracted weights, and all three learned weight sets.
    """
    read_dir = BASE_PATH / "build/scan_behavioral/20261010_114121_frida2_ramp_code_density"
    cdac_dir = BASE_PATH / "build/scan_behavioral/20261010_114043_frida2_cdac_ab"
    artifacts = []
    for train_path in sorted(read_dir.glob("seed[0-9][0-9]_ac[0-9][0-9][0-9]_train.h5")):
        check_path = train_path.with_name(train_path.name.replace("_train", "_check"))
        train, check = read_measurement(train_path), read_measurement(check_path)
        if not isinstance(train, MeasAdc) or not isinstance(check, MeasAdc):
            raise TypeError(f"{train_path} and {check_path} must both contain MeasAdc")
        train_ramp = analyze_adc_ramp(train)
        # Calibration 1 learns from the same draw's CDAC A-to-B switching curves.
        draw_dir = cdac_dir / train_path.stem.removesuffix("_train")
        comparator = read_measurement(draw_dir / "comparator.h5")
        if not isinstance(comparator, MeasComp):
            raise TypeError(f"{draw_dir} must hold one MeasComp and MeasCdac switching curves")
        curves: list[MeasCdac] = []
        for curve_path in sorted(draw_dir.glob("cdac_*.h5")):
            curve = read_measurement(curve_path)
            if not isinstance(curve, MeasCdac):
                raise TypeError(f"{draw_dir} must hold one MeasComp and MeasCdac switching curves")
            curves.append(curve)
        transitions = [analyze_cdac_transition([curve], offset=analyze_comp_offset_noise([curve])) for curve in curves]
        cap_mismatch = analyze_cdac_cap_mismatch(
            curves, transitions=transitions, comparator=analyze_comp_offset_noise([comparator])
        )
        learned = (
            analyze_adc_calibration1(curves, cap_mismatch=cap_mismatch),
            analyze_adc_calibration2(train, ramp=train_ramp),
            analyze_adc_calibration3(train, ramp=train_ramp),
        )
        extracted = read_extracted_calibration(Path(str(check.info.readbacks["cap_table"])), check)
        ramps = [analyze_adc_ramp(check)] + [
            analyze_adc_ramp(check, calibration=calibration) for calibration in (extracted, *learned)
        ]
        stem = f"frida2_3layer_behavioral_{train_path.stem.removesuffix('_train')}"
        artifacts.extend(
            plot_adc_calibration_weights((extracted, *learned), output_path=output_dir / f"{stem}_weights")
        )
        artifacts.extend(
            plot_adc_ramp_nonlinearity(
                ramps, output_path=output_dir / f"{stem}_calibrated_inl_dnl", msmt=check, stacked=True
            )
        )
        artifacts.extend(
            plot_adc_ramp_histogram(ramps, output_path=output_dir / f"{stem}_calibrated_code_density", msmt=check)
        )
    return tuple(artifacts)


def adc_behavioral_architecture_study(output_dir: Path) -> tuple[Path, ...]:
    """Compare held-out ramp linearity of redundant and binary, unit-length and unit-element arrays.

    Inputs are the behavioral architecture-variant captures: for each array
    and capacitor draw a training and a held-out eight-period ramp. The
    held-out ramp is decoded with the nominal design weights and with
    calibrations 2 and 3 learned from the training ramp alone.
    """
    read_dir = BASE_PATH / "build/scan_behavioral/20261010_115333_architecture_variants"
    artifacts = []
    for variant_dir in sorted(path for path in read_dir.iterdir() if path.is_dir()):
        for train_path in sorted(variant_dir.glob("seed[0-9][0-9]_ac[0-9][0-9][0-9]_train.h5")):
            check_path = train_path.with_name(train_path.name.replace("_train", "_check"))
            train, check = read_measurement(train_path), read_measurement(check_path)
            if not isinstance(train, MeasAdc) or not isinstance(check, MeasAdc):
                raise TypeError(f"{train_path} and {check_path} must both contain MeasAdc")
            train_ramp = analyze_adc_ramp(train)
            learned = (
                analyze_adc_calibration2(train, ramp=train_ramp),
                analyze_adc_calibration3(train, ramp=train_ramp),
            )
            ramps = [analyze_adc_ramp(check)] + [
                analyze_adc_ramp(check, calibration=calibration) for calibration in learned
            ]
            stem = f"{variant_dir.name}_{train_path.stem.removesuffix('_train')}"
            artifacts.extend(plot_adc_ramp_nonlinearity(ramps, output_path=output_dir / f"{stem}_inl_dnl", msmt=check))
            artifacts.extend(plot_adc_calibration_weights(learned, output_path=output_dir / f"{stem}_weights"))
    return tuple(artifacts)


def adc_behavioral_noise_spectrum_study(output_dir: Path) -> tuple[Path, ...]:
    """Overlay the output-code noise spectral density of each behavioral noise source.

    Inputs are three behavioral MeasAdc fixed-input captures (50 mV, 10 MS/s,
    100,000 conversions): the sampling switch's kT/C alone, the comparator
    alone, and the total ADC with both.
    Codes are decoded with the PEX-extracted weights.
    """
    read_dir = BASE_PATH / "build/scan_behavioral/20261010_114609_frida2_noise_sources"
    labels = {
        "sampling": "Sampling switch (kT/C)",
        "comparator": "Comparator",
        "baseline": "Total ADC",
    }
    spectra = []
    for name in labels:
        path = read_dir / f"noise_{name}.h5"
        measurement = read_measurement(path)
        if not isinstance(measurement, MeasAdc):
            raise TypeError(f"{path} contains {type(measurement).__name__}, expected MeasAdc")
        calibration = read_extracted_calibration(Path(str(measurement.info.readbacks["cap_table"])), measurement)
        spectra.append(analyze_adc_code_spectrum(measurement, calibration=calibration))
    return plot_adc_code_spectrum(
        spectra,
        labels=tuple(labels.values()),
        title="FRIDA-2 three-layer behavioral noise sources",
        output_path=output_dir / "frida2_3layer_behavioral_noise_spectrum",
    )


def adc_behavioral_input_frequency_study(output_dir: Path) -> tuple[Path, ...]:
    """Plot spectral ENOB and SNDR versus input frequency at 2, 6, and 10 MS/s.

    Inputs are 27 behavioral MeasAdc sine captures (-0.5 dBFS, nine input
    frequencies up to Nyquist per rate, 8,192 conversions) with every noise
    source, the input-dependent sampler, and the PEX-extracted decoding. The
    10-MS/s captures nearest DC and Nyquist also get their own spectra.
    """
    read_dir = BASE_PATH / "build/scan_behavioral/20261010_114623_frida2_input_frequency"
    measurements, dynamics = [], []
    for path in sorted(read_dir.glob("[0-9][0-9][0-9][0-9]mbd_[0-9][0-9][0-9][0-9]cycles.h5")):
        measurement = read_measurement(path)
        if not isinstance(measurement, MeasAdc):
            raise TypeError(f"{path} contains {type(measurement).__name__}, expected MeasAdc")
        calibration = read_extracted_calibration(Path(str(measurement.info.readbacks["cap_table"])), measurement)
        measurements.append(measurement)
        dynamics.append(analyze_adc_dynamic(measurement, calibration=calibration))
    artifacts = list(
        plot_adc_dynamic_sweep(
            measurements,
            dynamics,
            output_path=output_dir / "frida2_3layer_behavioral_enob_vs_input_frequency",
            x_axis="input_frequency",
        )
    )
    at_10_msps = [index for index, dynamic in enumerate(dynamics) if round(dynamic.sample_rate_hz) == 10_000_000]
    for label, index in (("low", at_10_msps[0]), ("nyquist", at_10_msps[-1])):
        artifacts.extend(
            plot_adc_dynamic(
                measurements[index],
                dynamics[index],
                output_path=output_dir / f"frida2_3layer_behavioral_10msps_{label}_spectrum",
            )
        )
    return tuple(artifacts)


def comp_behavioral_offset_noise_study(output_dir: Path) -> tuple[Path, ...]:
    """Fit offset and noise of the behavioral comparator block simulated alone.

    The input is one behavioral MeasComp from ``flow.scans.scan_behavioral``:
    61 differential inputs within +/-1.5 mV at 0.7 V common mode, 400
    decisions each. It uses the same S-curve analysis as physical comparator
    sweeps.
    """
    path = BASE_PATH / "build/scan_behavioral/20261010_073028_frida2_comparator/comparator.h5"
    measurement = read_measurement(path)
    if not isinstance(measurement, MeasComp):
        raise TypeError(f"{path} contains {type(measurement).__name__}, expected MeasComp")
    return plot_comp_offset_noise(
        [measurement],
        analyze_comp_offset_noise([measurement]),
        output_path=output_dir / "frida2_behavioral_comparator_offset_noise",
    )


def adc_calibration_study(output_dir: Path) -> tuple[Path, ...]:
    """Compare three calibration methods on the selected ADC00 measurements.

    Coverage: ADC00's known 10-Hz ramp (MeasAdc), three reviewed CDAC
    threshold campaigns (MeasCdac), and the accepted comparator
    characterization (MeasComp). Calibration 1 extracts A-state threshold
    movements; calibrations 2/3 use ramp BOUT fits/prefix thresholds. The ramp
    validates the resulting decoders. No internal SPICE waveforms are needed.
    """

    ramp_path = BASE_PATH / (
        "build/scan_adc/20260812_011910/"
        "0000_00_adc00_160mbd_pwl10hz_m1000top1000mv_logicp0sym_"
        "vcm600mv_vdda1200mv_vddd1200mv_vddac1200mv_t25c.h5"
    )
    measurement = read_measurement(ramp_path)
    if not isinstance(measurement, MeasAdc):
        raise TypeError(f"{ramp_path} contains {type(measurement).__name__}, expected MeasAdc")
    adc_index = measurement.index
    if adc_index is None:
        raise ValueError("calibration study requires an observed ADC")
    # Comparator characterizations: the reviewed 800-mV campaigns behind the
    # board inventory's accepted comparator calibration, with every coarse and
    # fine trial. Each one is the reference point of its ADC's CDAC steps.
    comparator_read_dirs = {
        0: BASE_PATH / "build/scan_comp/20260804_051653",
        1: BASE_PATH / "build/scan_comp/20260804_053759",
        2: BASE_PATH / "build/scan_comp/20260804_051653",
        3: BASE_PATH / "build/scan_comp/20260804_054953",
    }
    # CDAC A-to-B runs, in acquisition order. Each later run atomically replaces
    # every point of the same ADC, side, element, direction, and diffcaps curve;
    # physical points from distinct acquisition sessions are never combined.
    selected_curves: dict[tuple[int, str, int, str, int], list[MeasCdac]] = {}
    for run_name in ("20260804_171234", "20260804_193030", "20260804_193631"):
        grouped_in_run: dict[tuple[int, str, int, str, int], list[MeasCdac]] = {}
        for path in sorted((BASE_PATH / "build/scan_cdac" / run_name).glob("*.h5")):
            cdac_point = read_measurement(path)
            if not isinstance(cdac_point, MeasCdac):
                raise TypeError(f"{path} contains {type(cdac_point).__name__}, expected MeasCdac")
            params = cdac_point.param
            if params.observed_adc != adc_index:
                continue
            if params.campaign != "cdac_ab":
                raise ValueError("CDAC campaign contains a point outside campaign='cdac_ab'")
            readbacks = cdac_point.info.readbacks
            if int(readbacks.get("fastrx_lost_count", 0)) or int(readbacks.get("spi_mismatches", 0)):
                raise ValueError("CDAC campaign contains a corrupt physical capture")
            if (
                params.observed_adc is None
                or params.cdac_side is None
                or params.cdac_element is None
                or params.cdac_direction is None
            ):
                raise ValueError("CDAC measurement is missing its ADC, side, element, or direction")
            curve_key = (
                params.observed_adc,
                params.cdac_side,
                params.cdac_element,
                params.cdac_direction,
                params.tb.dac_diffcaps,
            )
            grouped_in_run.setdefault(curve_key, []).append(cdac_point)
        for curve_key, curve in grouped_in_run.items():
            physical = [point for point in curve if point.info.backend == "physical"]
            if physical:
                session_ids = {point.info.readbacks.get("acquisition_session_id") for point in physical}
                completed = [point for point in physical if point.info.readbacks.get("curve_complete") is True]
                latest_timestamp = max(point.info.timestamp_utc for point in physical)
                if (
                    len(physical) != len(curve)
                    or None in session_ids
                    or len(session_ids) != 1
                    or len(completed) != 1
                    or completed[0].info.timestamp_utc != latest_timestamp
                ):
                    raise ValueError(f"CDAC campaign contains an incomplete or mixed-session curve {curve_key}")
        selected_curves.update(grouped_in_run)
    cdac_measurements: dict[int, list[MeasCdac]] = {}
    cap_mismatch: dict[int, AnalysisCdacCapMismatch] = {}
    for adc_index in sorted({curve_key[0] for curve_key in selected_curves}):
        comparator_measurements = []
        for path in sorted(comparator_read_dirs[adc_index].glob(f"*adc{adc_index:02d}*.h5")):
            comparator_point = read_measurement(path)
            if not isinstance(comparator_point, MeasComp):
                raise TypeError(f"{path} contains {type(comparator_point).__name__}, expected MeasComp")
            comparator_measurements.append(comparator_point)
        transitions = []
        cdac_measurements[adc_index] = []
        for curve_key in sorted(key for key in selected_curves if key[0] == adc_index):
            curve = selected_curves[curve_key]
            cdac_measurements[adc_index].extend(curve)
            # Fit the fine sweep stage where the curve has one.
            fit_points = [point for point in curve if point.param.sweep_stage == "fine"] or curve
            transitions.append(analyze_cdac_transition(fit_points, offset=analyze_comp_offset_noise(fit_points)))
        cap_mismatch[adc_index] = analyze_cdac_cap_mismatch(
            cdac_measurements[adc_index],
            transitions=transitions,
            comparator=analyze_comp_offset_noise(comparator_measurements),
        )

    nominal_ramp = analyze_adc_ramp(measurement)
    calibrations = (
        analyze_adc_calibration1(cdac_measurements[adc_index], cap_mismatch=cap_mismatch[adc_index]),
        analyze_adc_calibration2(measurement, ramp=nominal_ramp),
        analyze_adc_calibration3(measurement, ramp=nominal_ramp),
    )
    ramps = (nominal_ramp, *(analyze_adc_ramp(measurement, calibration=calibration) for calibration in calibrations))

    stem = f"adc{adc_index:02d}"
    return (
        *plot_adc_calibration_weights(calibrations, output_path=output_dir / f"{stem}_calibration_weights"),
        *plot_adc_ramp_transfer(ramps, output_path=output_dir / f"{stem}_calibration_transfer"),
        *plot_adc_ramp_histogram(ramps, output_path=output_dir / f"{stem}_calibration_code_density"),
        *plot_adc_ramp_nonlinearity(ramps, output_path=output_dir / f"{stem}_calibration_inl_dnl"),
    )


def adc_sequence_study(output_dir: Path) -> tuple[Path, ...]:
    """Compare 29 continuous recipes on 16 ADCs at 2/6/10 MSPS and selected PEX cases.

    Physical captures are the corrected 160-symbol, 100,000-conversion
    fixed-input campaign. The selected PEX cases cover the same seven
    continuous recipes on four FRIDA-1 and three FRIDA-2 flavors at 1600 MBd.
    Physical and PEX captures go through the same per-capture noise analysis
    and per-ADC (or per-flavor) operating-condition analysis; PEX cases also
    get timing closure. Operating-condition and timing-summary results are
    saved as analysis HDF5 files beside the figures.
    """
    read_dir = BASE_PATH / "build/scan_adc/20260926_172920_adc_sequence_static"
    paths = sorted(read_dir.glob("[0-9][0-9][0-9][0-9]_capture.h5"))
    # The pinned physical captures predate the wider INIT-associated LOGIC pulse.
    catalogue = tuple(
        dataclasses.replace(sequence, logic="00010000" + sequence.logic[8:])
        for name, sequence in SEQUENCES
        if name.startswith("symbol160_init4_samp20_")
    )
    paths_by_adc: dict[int, list[Path]] = {}
    for path in paths:
        paths_by_adc.setdefault(read_measurement_param(path).observed_adc, []).append(path)

    output_dir.mkdir(parents=True, exist_ok=True)
    artifacts: list[Path] = []
    conditions = []
    board_map = load_board_map()
    for adc_index, adc_paths in sorted(paths_by_adc.items()):
        measurements = []
        for path in adc_paths:
            measurement = read_measurement(path)
            if not isinstance(measurement, MeasAdc):
                raise TypeError(f"{path} contains {type(measurement).__name__}, expected MeasAdc")
            measurements.append(measurement)
        result = analyze_adc_operating_conditions(
            measurements, noise=[analyze_adc_noise(measurement) for measurement in measurements]
        )
        del measurements
        conditions.append(result)
        artifacts.append(write_analysis(output_dir / f"adc{adc_index:02d}_operating_conditions.h5", result))
        layers = board_map["adc_layers"]
        artifacts.extend(
            plot_adc_sequence_enob(
                result,
                sequences=catalogue,
                adc_label=(
                    f"ADC{adc_index:02d} · {board_map['adc_channels'][adc_index]}"
                    + (f" · {layers[adc_index]} layer" if adc_index in layers else "")
                ),
                output_path=output_dir / f"adc{adc_index:02d}_sequence_enob",
            )
        )
    artifacts.extend(
        plot_adc_sequence_chip_overview(
            conditions,
            sequences=catalogue,
            title=f"{len(conditions)} ADCs · fixed 50 mV input · continuous 160-symbol sequence comparison",
            output_path=output_dir / "all_adc_sequence_overview",
        )
    )

    timings = (
        "symbol160_init4_samp20_comp11110000_logic00001111",
        "symbol160_init4_samp20_comp11110000_logic10000111",
        "symbol160_init4_samp20_comp11111000_logic10000111",
        "symbol160_init4_samp20_comp11111000_logic11000011",
        "symbol160_init4_samp20_comp11111100_logic11000011",
        "symbol160_init4_samp20_comp11111100_logic11100001",
        "symbol160_init4_samp20_comp11111110_logic11100001",
    )
    campaigns = (
        (
            "frida-20260926_215421_042700",
            "20260926_221031_frida1_sequence",
            tuple(f"frida1_{layers}layer_radix{radix}" for layers in (1, 2) for radix in (17, 20)),
        ),
        (
            "frida-20260926_215427_988306",
            "20260926_221039_frida2_sequence",
            tuple(f"frida2_{layers}layer_radix17" for layers in (1, 2, 3)),
        ),
    )
    # One representative flavor supplies the seven sequence clock diagrams.
    sequence_plot_flavor = "frida2_3layer_radix17"
    for session, stamp, flavors in campaigns:
        for flavor in flavors:
            measurements = []
            for timing in timings:
                path = BASE_PATH / "build/remote" / session / "results/sim/adc" / stamp / flavor / timing / "result.h5"
                measurement = read_measurement(path)
                if not isinstance(measurement, MeasAdc):
                    raise TypeError(f"expected MeasAdc: {path}")
                case = f"{flavor}_{timing}"
                artifacts.extend(
                    plot_adc_decision_path_density(
                        measurement,
                        analyze_adc_decision_paths(measurement),
                        output_path=output_dir / f"spice_{case}_trajectory",
                    )
                )
                artifacts.extend(
                    plot_adc_cdac_settling(
                        measurement,
                        analyze_adc_cdac_settling(measurement),
                        output_path=output_dir / f"spice_{case}_cdac_settling",
                    )
                )
                artifacts.extend(
                    plot_adc_code_distribution(
                        (measurement,),
                        analyze_adc_code_distribution((measurement,)),
                        output_path=output_dir / f"spice_{case}_codes",
                    )
                )
                closure = analyze_adc_timing_closure(measurement)
                artifacts.append(
                    write_analysis(
                        output_dir / f"{case}_timing_summary.h5",
                        analyze_adc_timing_summary(measurement, closure=closure),
                    )
                )
                if flavor == sequence_plot_flavor and measurement.wave is not None:
                    # Show the second saved conversion from its INIT rise.
                    wave = measurement.wave
                    init_rise_s = calc.cross(wave.v["seq_init"][1], wave.time_s, 0.6, edge="rising", initial_high=True)
                    if not len(init_rise_s):
                        raise ValueError(f"{case} has no INIT rise in its second record")
                    with mpl.rc_context({"axes.xmargin": 0.0}):
                        artifacts.extend(
                            plot_waveforms(
                                wave,
                                record=1,
                                time_origin_s=float(init_rise_s[0]),
                                signals={
                                    "seq_init": "INIT",
                                    "seq_samp": "SAMP",
                                    "seq_comp": "COMP",
                                    "seq_logic": "LOGIC",
                                },
                                title=timing.replace("_", " "),
                                setup_lines=style_measurement_text(measurement),
                                output_path=output_dir / f"sequence_{timing}",
                            )
                        )
                print(f"Rendered PEX case {case}", flush=True)
                measurements.append(measurement)
            noise = [analyze_adc_noise(measurement) for measurement in measurements]
            artifacts.append(
                write_analysis(
                    output_dir / f"spice_{flavor}_operating_conditions.h5",
                    analyze_adc_operating_conditions(measurements, noise=noise),
                )
            )
            artifacts.extend(
                plot_adc_noise_sweep(
                    measurements,
                    noise,
                    series_labels=timings,
                    rate_axis="sampling",
                    output_path=output_dir / f"spice_{flavor}_sequence_noise",
                )
            )
            del measurements, noise
    return tuple(artifacts)


def adc_interferer_study(output_dir: Path) -> tuple[Path, ...]:
    """Locate the 6-8 MHz interferer in the output-code spectra and its amplifier-supply A/B test.

    Labels follow the interferer-hunt deck: test #4 is the 8 Oct scope re-run,
    tests #12--#15 the 9 Oct runs A/B/C/D. They share one fixed 50-mV
    input on ADC00--03, seven 160-symbol sequences at 2/6/10 MSPS, and 100,000
    conversions per capture. A and D have the THS4541 supplies unplugged or
    turned down and lack the interferer; B and C have them on, with the
    amplifier enabled and disabled. Every capture gets a code spectrum; each
    run's ADCs get an alias search over their 4of8 captures at three rates.
    Without the interferer, that search settles on slow drift near DC. The figures overlay
    the four ADCs per run for the 4of8 recipe and the runs for ADC00, and split
    ADC00's slowest 4of8 capture into lines and broadband noise per run.
    """
    runs = {
        "Test #4": "20261008_204141_adc_sequence_static",
        "Test #12: amp supplies unplugged": "20261009_105940_adc_sequence_static",
        "Test #13: amp supplies on, enabled": "20261009_110638_adc_sequence_static",
        "Test #14: amp supplies on, disabled": "20261009_110933_adc_sequence_static",
        "Test #15: amp supplies turned down": "20261009_153529_adc_sequence_static",
    }
    shown = dict(SEQUENCES)["symbol160_init4_samp20_comp11110000_logic10000111"]
    output_dir.mkdir(parents=True, exist_ok=True)
    artifacts: list[Path] = []
    comparison = []
    for run, folder in runs.items():
        stem = folder.removesuffix("_adc_sequence_static")
        measurements_by_adc: dict[int, list[MeasAdc]] = {}
        for path in sorted((BASE_PATH / "build/scan_adc" / folder).glob("[0-9][0-9][0-9][0-9]_capture.h5")):
            measurement = read_measurement(path)
            if not isinstance(measurement, MeasAdc):
                raise TypeError(f"{path} contains {type(measurement).__name__}, expected MeasAdc")
            measurements_by_adc.setdefault(measurement.param.observed_adc, []).append(measurement)
        shown_spectra = []
        interferers = []
        for adc_index, measurements in sorted(measurements_by_adc.items()):
            spectra = [analyze_adc_code_spectrum(measurement) for measurement in measurements]
            # Search one recipe, whose three rates were captured minutes apart: over
            # all recipes, the drifting interferer smears and a fixed 7.143-MHz line
            # (2856 kHz at 10 MSPS) wins instead.
            selected = [index for index, spectrum in enumerate(spectra) if spectrum.sequence == shown]
            interferer = analyze_adc_interferer(
                [measurements[index] for index in selected], spectra=[spectra[index] for index in selected]
            )
            interferers.append(interferer)
            artifacts.append(write_analysis(output_dir / f"{stem}_adc{adc_index:02d}_interferer.h5", interferer))
            shown_spectra.extend(spectrum for spectrum in spectra if spectrum.sequence == shown)
            if adc_index == 0:
                # The variance split of ADC00 at the slowest rate, codes and spectrum together.
                candidates = [pair for pair in zip(measurements, spectra, strict=True) if pair[1].sequence == shown]
                measurement, spectrum = candidates[int(np.argmin([pair[1].sample_rate_hz for pair in candidates]))]
                artifacts.extend(
                    plot_adc_code_noise(
                        measurement,
                        spectrum,
                        title=f"ADC00 code noise, {spectrum.sample_rate_hz / 1e6:g} MSPS, 4of8 recipe · {run}",
                        output_path=output_dir / f"{stem}_adc00_code_noise",
                    )
                )
        comparison.extend((run, spectrum) for spectrum in shown_spectra if spectrum.index == 0)
        artifacts.extend(
            plot_adc_code_spectrum(
                shown_spectra,
                title=f"Output-code spectra, 4of8 recipe · {run}",
                output_path=output_dir / f"{stem}_code_spectra",
            )
        )
        artifacts.extend(
            plot_adc_interferer(
                interferers,
                title=f"Interferer frequency from its aliases · {run}",
                output_path=output_dir / f"{stem}_interferer",
            )
        )
    artifacts.extend(
        plot_adc_code_spectrum(
            [spectrum for _run, spectrum in comparison],
            labels=[run.split(":")[0] for run, _spectrum in comparison],
            title="ADC00 output-code spectra, 4of8 recipe · amplifier-supply A/B",
            output_path=output_dir / "amp_supply_code_spectra",
        )
    )
    return tuple(artifacts)


def adc_sample_rate_study(output_dir: Path) -> tuple[Path, ...]:
    """Plot measured rate dependence for selected historical sequence patterns.

    Coverage: ADC00/01 50/100-mV DC and 10-kHz sine captures at 600-mV common
    mode, plus the control alignment in ADC00's 800-mV timing campaign.
    Only the historical fixed-input sequence is currently accepted; extend the
    explicit selection after validating additional patterns in the sequence study.
    Actual rates are 0.3125--6.25 MSPS (formerly labelled 0.5--10 active MSPS);
    an actual 10-MSPS sweep of accepted new patterns still needs acquisition.
    DC panels show noise-equivalent resolution; sine panels show spectral
    ENOB/SNDR. Inputs are MeasAdc; no PEX or internal waveforms are required.
    """
    dc_read_dirs = tuple(
        BASE_PATH / "build/scan_adc" / stamp
        for stamp in (
            "20260801_194930",
            "20260802_021624",
            "20260802_081407",
        )
    )
    sine_read_dir = BASE_PATH / "build/scan_adc/20260730_215145_complete"
    selected_sequences = (symbol256_init8_samp16_comp11110000_logic11000011,)

    # Give selected library recipes the same INIT reference as acquired rows.
    sequence_labels = {}
    for sequence in selected_sequences:
        relative_sequence = sequence.relative_to_init()
        sequence_labels[relative_sequence] = f"LOGIC {timing_sequences.index(sequence) + 1}/8"

    # Select and compare DC sweeps without changing their saved acquisition phase.
    artifacts = []
    for meas_read_dir in dc_read_dirs:
        paths = sorted(meas_read_dir.glob("[0-9][0-9][0-9][0-9]_*.h5"))
        if not paths:
            raise FileNotFoundError(meas_read_dir)
        groups: dict[tuple[int | None, float, float], list[MeasAdc]] = {}
        for path in paths:
            measurement = read_measurement(path)
            if not isinstance(measurement, MeasAdc):
                raise TypeError(f"{path} contains {type(measurement).__name__}, expected MeasAdc")
            params = measurement.tb
            if not isinstance(params.vin_diff, h.Vdc.Params):
                continue
            # Compare complete rows relative to INIT; leave acquired patterns and data unchanged.
            sequence = AdcSequence.from_tb_params(params).relative_to_init()
            if sequence not in sequence_labels:
                continue
            key = (measurement.index, float(params.vin_diff.dc), float(params.vin_cm.dc))
            groups.setdefault(key, []).append(measurement)
        if not groups:
            raise ValueError(f"no selected sequences in {meas_read_dir}")
        for (adc_index, input_v, common_v), measurements in sorted(groups.items(), key=lambda item: str(item[0])):
            labels = [
                sequence_labels[AdcSequence.from_tb_params(measurement.tb).relative_to_init()]
                for measurement in measurements
            ]
            noise = [analyze_adc_noise(measurement) for measurement in measurements]
            stem = f"{meas_read_dir.name}_adc{adc_index or 0:02d}_{input_v * 1e3:g}mv_{common_v * 1e3:g}cm"
            artifacts.extend(
                plot_adc_noise_sweep(
                    measurements,
                    noise,
                    series_labels=labels,
                    rate_axis="sampling",
                    output_path=output_dir / f"{stem}_noise_vs_rate",
                )
            )
            for label in dict.fromkeys(labels):
                selected = [index for index, name in enumerate(labels) if name == label]
                artifacts.extend(
                    plot_adc_noise_distribution_sweep(
                        [measurements[index] for index in selected],
                        [noise[index] for index in selected],
                        rate_axis="sampling",
                        output_path=output_dir / f"{stem}_logic{label.split()[-1].replace('/', 'of')}_distributions",
                    )
                )

    # Spectral results use the acquired sine, separately from DC noise estimates.
    paths = sorted(sine_read_dir.glob("[0-9][0-9][0-9][0-9]_*.h5"))
    if not paths:
        raise FileNotFoundError(sine_read_dir)
    sine_groups: dict[tuple[int | None, AdcSequence], list[MeasAdc]] = {}
    for path in paths:
        measurement = read_measurement(path)
        if not isinstance(measurement, MeasAdc):
            raise TypeError(f"{path} contains {type(measurement).__name__}, expected MeasAdc")
        params = measurement.tb
        if not isinstance(params.vin_diff, h.Vsin.Params):
            continue
        # Compare complete rows relative to INIT; leave acquired patterns and data unchanged.
        sequence = AdcSequence.from_tb_params(params).relative_to_init()
        if sequence not in sequence_labels:
            continue
        sine_groups.setdefault((measurement.index, sequence), []).append(measurement)
    for (adc_index, sequence), measurements in sine_groups.items():
        sequence_name = sequence_labels[sequence].split()[-1].replace("/", "of")
        dynamic = [analyze_adc_dynamic(measurement) for measurement in measurements]
        stem = f"adc{adc_index or 0:02d}_logic{sequence_name}"
        artifacts.extend(
            plot_adc_dynamic_sweep(
                measurements,
                dynamic,
                x_axis="sample_rate",
                output_path=output_dir / f"{stem}_spectral_vs_rate",
            )
        )
        # Retain individual spectral checks at the ends of the selected sweep.
        rates = [result.sample_rate_hz for result in dynamic]
        for index in dict.fromkeys((rates.index(min(rates)), rates.index(max(rates)))):
            artifacts.extend(
                plot_adc_dynamic(
                    measurements[index],
                    dynamic[index],
                    # A decimal point would read as a file suffix; write 0.3125 as 0p3125.
                    output_path=output_dir / f"{stem}_{f'{rates[index] / 1e6:g}'.replace('.', 'p')}msps_spectrum",
                )
            )
    return tuple(artifacts)


def adc_power_study(output_dir: Path) -> tuple[Path, ...]:
    """Plot three-rail power from instrumented fixed-input MeasAdc captures.

    Coverage: ADC00/01 50/100-mV DC at 600-mV common mode over actual
    0.3125--6.25 MSPS, plus ADC00 50-mV/700-mV-common reference points.
    Requires active and baseline voltage/current or power readbacks from the
    three Keithley supplies. Manual-supply runs and PEX are not selected;
    internal SPICE waveforms are unnecessary.
    """
    meas_read_dirs = tuple(
        BASE_PATH / "build/scan_adc" / stamp
        for stamp in (
            "20260801_194930",
            "20260802_021624",
            "20260819_113714",
        )
    )
    artifacts = []
    for meas_read_dir in meas_read_dirs:
        paths = sorted(meas_read_dir.glob("[0-9][0-9][0-9][0-9]_*.h5"))
        if not paths:
            raise FileNotFoundError(meas_read_dir)
        groups: dict[tuple[int | None, float, float, AdcSequence], list[MeasAdc]] = {}
        for path in paths:
            measurement = read_measurement(path)
            if not isinstance(measurement, MeasAdc):
                raise TypeError(f"{path} contains {type(measurement).__name__}, expected MeasAdc")
            params = measurement.tb
            if not isinstance(params.vin_diff, h.Vdc.Params):
                continue
            # Compare complete rows relative to INIT; leave acquired patterns and data unchanged.
            sequence = AdcSequence.from_tb_params(params).relative_to_init()
            key = (measurement.index, float(params.vin_diff.dc), float(params.vin_cm.dc), sequence)
            groups.setdefault(key, []).append(measurement)
        for index, ((adc_index, input_v, common_v, _sequence), measurements) in enumerate(groups.items()):
            artifacts.extend(
                plot_adc_power_sweep(
                    measurements,
                    [analyze_adc_power(measurement) for measurement in measurements],
                    rate_axis="sampling",
                    output_path=output_dir
                    / f"{meas_read_dir.name}_adc{adc_index or 0:02d}_{input_v * 1e3:g}mv_{common_v * 1e3:g}cm_{index}_power",
                )
            )
    return tuple(artifacts)


# =============================================================================
# Comparator and CDAC studies
# =============================================================================


def comp_system_common_mode_study(output_dir: Path) -> tuple[Path, ...]:
    """Analyze and plot separate ADC00–ADC03 comparator common-mode campaigns."""

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


def comp_system_sampling_noise_study(output_dir: Path) -> tuple[Path, ...]:
    """Analyze and plot separate ADC00–ADC03 track/hold comparator campaigns."""

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


def comp_candidate_sweep_study(output_dir: Path) -> tuple[Path, ...]:
    """Analyze the complete generated-comparator noise/power/timing campaign."""

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


def comp_topology_study(output_dir: Path) -> tuple[Path, ...]:
    """Analyze and plot delay and noise of the six simulated comparator topologies."""

    meas_read_dir = BASE_PATH / "build/sim/comp/hdl21_comp_topology_study/20261013_103009"
    topologies = (
        ("double_tail_self_timed", "Double tail self-timed"),
        ("double_tail", "Double tail"),
        ("double_tail_modified_self_timed", "Double tail modified self-timed"),
        ("double_tail_modified", "Double tail modified"),
        ("triple_tail", "Triple tail"),
        ("strongarm", "StrongARM"),
    )
    delays = []
    common_modes = []
    for name, _label in topologies:
        measurements = []
        for path in (
            meas_read_dir / "delay" / name / "result.h5",
            *sorted(meas_read_dir.glob(f"noise/{name}_cm*/result.h5")),
        ):
            measurement = read_measurement(path)
            if not isinstance(measurement, MeasComp):
                raise TypeError(f"{path} contains {type(measurement).__name__}, expected MeasComp")
            measurements.append(measurement)
        delay_measurements, scurves = measurements[:1], measurements[1:]
        delays.append(analyze_comp_delay(delay_measurements, timing=analyze_comp_timing(delay_measurements)))
        offsets = [analyze_comp_offset_noise([scurve]) for scurve in scurves]
        common_modes.append(analyze_comp_common_mode(scurves, offsets=offsets))
    return plot_comp_topology_study(
        delays,
        common_modes,
        labels=[label for _name, label in topologies],
        output_path=output_dir / "comp_topology_study",
    )


def cdac_system_cap_mismatch_study(output_dir: Path) -> tuple[Path, ...]:
    """Extract and plot ADC00–ADC03 capacitor mismatch from A-to-B transitions."""

    # Comparator characterizations: the reviewed 800-mV campaigns behind the
    # board inventory's accepted comparator calibration, with every coarse and
    # fine trial. Each one is the reference point of its ADC's CDAC steps.
    comparator_read_dirs = {
        0: BASE_PATH / "build/scan_comp/20260804_051653",
        1: BASE_PATH / "build/scan_comp/20260804_053759",
        2: BASE_PATH / "build/scan_comp/20260804_051653",
        3: BASE_PATH / "build/scan_comp/20260804_054953",
    }
    # CDAC A-to-B runs, in acquisition order. Each later run atomically replaces
    # every point of the same ADC, side, element, direction, and diffcaps curve;
    # physical points from distinct acquisition sessions are never combined.
    selected_curves: dict[tuple[int, str, int, str, int], list[MeasCdac]] = {}
    for run_name in ("20260804_171234", "20260804_193030", "20260804_193631"):
        grouped_in_run: dict[tuple[int, str, int, str, int], list[MeasCdac]] = {}
        for path in sorted((BASE_PATH / "build/scan_cdac" / run_name).glob("*.h5")):
            cdac_point = read_measurement(path)
            if not isinstance(cdac_point, MeasCdac):
                raise TypeError(f"{path} contains {type(cdac_point).__name__}, expected MeasCdac")
            params = cdac_point.param
            if params.campaign != "cdac_ab":
                raise ValueError("CDAC campaign contains a point outside campaign='cdac_ab'")
            readbacks = cdac_point.info.readbacks
            if int(readbacks.get("fastrx_lost_count", 0)) or int(readbacks.get("spi_mismatches", 0)):
                raise ValueError("CDAC campaign contains a corrupt physical capture")
            if (
                params.observed_adc is None
                or params.cdac_side is None
                or params.cdac_element is None
                or params.cdac_direction is None
            ):
                raise ValueError("CDAC measurement is missing its ADC, side, element, or direction")
            curve_key = (
                params.observed_adc,
                params.cdac_side,
                params.cdac_element,
                params.cdac_direction,
                params.tb.dac_diffcaps,
            )
            grouped_in_run.setdefault(curve_key, []).append(cdac_point)
        for curve_key, curve in grouped_in_run.items():
            physical = [point for point in curve if point.info.backend == "physical"]
            if physical:
                session_ids = {point.info.readbacks.get("acquisition_session_id") for point in physical}
                completed = [point for point in physical if point.info.readbacks.get("curve_complete") is True]
                latest_timestamp = max(point.info.timestamp_utc for point in physical)
                if (
                    len(physical) != len(curve)
                    or None in session_ids
                    or len(session_ids) != 1
                    or len(completed) != 1
                    or completed[0].info.timestamp_utc != latest_timestamp
                ):
                    raise ValueError(f"CDAC campaign contains an incomplete or mixed-session curve {curve_key}")
        selected_curves.update(grouped_in_run)
    cdac_measurements: dict[int, list[MeasCdac]] = {}
    cap_mismatch: dict[int, AnalysisCdacCapMismatch] = {}
    for adc_index in sorted({curve_key[0] for curve_key in selected_curves}):
        comparator_measurements = []
        for path in sorted(comparator_read_dirs[adc_index].glob(f"*adc{adc_index:02d}*.h5")):
            comparator_point = read_measurement(path)
            if not isinstance(comparator_point, MeasComp):
                raise TypeError(f"{path} contains {type(comparator_point).__name__}, expected MeasComp")
            comparator_measurements.append(comparator_point)
        transitions = []
        cdac_measurements[adc_index] = []
        for curve_key in sorted(key for key in selected_curves if key[0] == adc_index):
            curve = selected_curves[curve_key]
            cdac_measurements[adc_index].extend(curve)
            # Fit the fine sweep stage where the curve has one.
            fit_points = [point for point in curve if point.param.sweep_stage == "fine"] or curve
            transitions.append(analyze_cdac_transition(fit_points, offset=analyze_comp_offset_noise(fit_points)))
        cap_mismatch[adc_index] = analyze_cdac_cap_mismatch(
            cdac_measurements[adc_index],
            transitions=transitions,
            comparator=analyze_comp_offset_noise(comparator_measurements),
        )
    artifacts = []
    for adc_index, analysis in cap_mismatch.items():
        artifacts.extend(
            plot_cdac_cap_mismatch(
                cdac_measurements[adc_index],
                analysis,
                output_path=output_dir / f"adc{adc_index:02d}_cdac_cap_mismatch",
            )
        )
    artifacts.extend(
        plot_cdac_cap_mismatch_comparison(
            list(cdac_measurements.values()),
            list(cap_mismatch.values()),
            output_path=output_dir / "adc00_adc03_cdac_cap_mismatch_comparison",
        )
    )
    return tuple(artifacts)


# =============================================================================
# Building block studies
# =============================================================================


def delay_characterization_study(output_dir: Path) -> tuple[Path, ...]:
    """Compare the named rings' frequency and energy, and the delay lines' delay, over supply and control."""

    meas_read_dir = BASE_PATH / "build/sim/delay/delay_characterization/20261017_120632"
    rings = (
        ("ring5", "ring5: inverter"),
        ("ring5_starved", "ring5_starved: current starved"),
        ("ring4_coupled", "ring4_coupled: coupled pseudo-differential"),
        ("ring4_tail", "ring4_tail: coupled on a shared tail"),
    )
    lines = (
        ("chain4", "chain4: inverter"),
        ("chain2_coupled", "chain2_coupled: coupled differential"),
        ("chain4_starved", "chain4_starved: current starved"),
    )
    sweeps = {}
    for name, _label in (*rings, *lines):
        measurements = []
        for path in sorted(meas_read_dir.glob(f"{name}/*/result.h5")):
            measurement = read_measurement(path)
            if not isinstance(measurement, MeasDelay):
                raise TypeError(f"{path} contains {type(measurement).__name__}, expected MeasDelay")
            measurements.append(measurement)
        # the supply sweep at the nominal control, and the control sweep at the nominal supply
        supply = [item for item in measurements if float(item.param.control_v) == NOMINAL_CONTROL_V]
        control = [item for item in measurements if float(item.param.vdd) == NOMINAL_SUPPLY_V]
        sweeps[name] = (
            sorted(supply, key=lambda item: float(item.param.vdd)),
            sorted(control, key=lambda item: float(item.param.control_v)),
        )
    ring_supply = [analyze_delay_oscillation(sweeps[name][0]) for name, _label in rings]
    ring_control = [analyze_delay_oscillation(sweeps[name][1]) for name, _label in rings]
    line_supply = [analyze_delay_propagation(sweeps[name][0]) for name, _label in lines]
    line_control = [analyze_delay_propagation(sweeps[name][1]) for name, _label in lines]
    ring_labels = [label for _name, label in rings]
    line_labels = [label for _name, label in lines]
    return (
        *plot_delay_ring_supply(ring_supply, labels=ring_labels, output_path=output_dir / "delay_ring_supply"),
        *plot_delay_ring_control(ring_control, labels=ring_labels, output_path=output_dir / "delay_ring_control"),
        *plot_delay_line_supply(line_supply, labels=line_labels, output_path=output_dir / "delay_line_supply"),
        *plot_delay_line_control(line_control, labels=line_labels, output_path=output_dir / "delay_line_control"),
    )


def latch_characterization_study(output_dir: Path) -> tuple[Path, ...]:
    """Compare the named latches' setup and hold, delay and energy over supply, and toggle limit."""

    meas_read_dir = BASE_PATH / "build/sim/latch/latch_characterization/20261017_121722"
    clocked = (
        ("latch", "latch: C2MOS"),
        ("latch_rst", "latch_rst: C2MOS with reset"),
        ("flop_rst", "flop_rst: master-slave"),
        ("div2", "div2: divide by two"),
    )
    srs = (("sr_nand", "sr_nand: NAND"), ("sr_nor", "sr_nor: NOR"))
    sweeps = {}
    for name, _label in (*clocked, *srs):
        for sweep, key in (
            ("supply", lambda item: float(item.param.vdd)),
            ("offset", lambda item: float(item.param.data_offset_s)),
            ("period", lambda item: -float(item.param.clock_period_s)),
        ):
            measurements = []
            for path in sorted(meas_read_dir.glob(f"{name}/{sweep}/*/result.h5")):
                measurement = read_measurement(path)
                if not isinstance(measurement, MeasLatch):
                    raise TypeError(f"{path} contains {type(measurement).__name__}, expected MeasLatch")
                measurements.append(measurement)
            sweeps[name, sweep] = sorted(measurements, key=key)
    offset_cases = [(name, label) for name, label in clocked if sweeps[name, "offset"]]
    period_cases = [(name, label) for name, label in clocked if sweeps[name, "period"]]
    offset_timings = [analyze_latch_timing(sweeps[name, "offset"]) for name, _label in offset_cases]
    constraints = [
        analyze_latch_constraint(sweeps[name, "offset"], timing=timing)
        for (name, _label), timing in zip(offset_cases, offset_timings, strict=True)
    ]
    return (
        *plot_latch_setup_hold(
            offset_timings,
            constraints,
            labels=[label for _name, label in offset_cases],
            output_path=output_dir / "latch_setup_hold",
        ),
        *plot_latch_supply(
            [analyze_latch_timing(sweeps[name, "supply"]) for name, _label in clocked],
            [analyze_latch_sr(sweeps[name, "supply"]) for name, _label in srs],
            labels=[label for _name, label in (*clocked, *srs)],
            output_path=output_dir / "latch_supply",
        ),
        *plot_latch_frequency(
            [analyze_latch_timing(sweeps[name, "period"]) for name, _label in period_cases],
            labels=[label for _name, label in period_cases],
            output_path=output_dir / "latch_frequency",
        ),
    )


def ota_characterization_study(output_dir: Path) -> tuple[Path, ...]:
    """Compare the named OTAs' open-loop response, input common-mode range, and supply scaling."""

    meas_read_dir = BASE_PATH / "build/sim/ota/ota_characterization/20261017_123051"
    cases = (
        ("five_t", "five_t: NMOS input"),
        ("five_t_pmos", "five_t_pmos: PMOS input"),
        ("self_biased", "self_biased: complementary"),
        ("telescopic", "telescopic: cascode"),
        ("folded", "folded: folded cascode"),
        ("two_stage", "two_stage: telescopic, CS"),
    )
    sweeps = {}
    for name, _label in cases:
        for sweep, key in (
            ("vcm", lambda item: float(item.param.vcm)),
            ("supply", lambda item: float(item.param.vdd)),
        ):
            measurements = []
            for path in sorted(meas_read_dir.glob(f"{name}/{sweep}/*/result.h5")):
                measurement = read_measurement(path)
                if not isinstance(measurement, MeasOta):
                    raise TypeError(f"{path} contains {type(measurement).__name__}, expected MeasOta")
                measurements.append(measurement)
            sweeps[name, sweep] = sorted(measurements, key=key)
    labels = [label for _name, label in cases]
    nominal = [
        analyze_ota_ac([item for item in sweeps[name, "vcm"] if float(item.param.vcm) == NOMINAL_VCM_V])
        for name, _label in cases
    ]
    return (
        *plot_ota_bode(nominal, labels=labels, output_path=output_dir / "ota_bode"),
        *plot_ota_common_mode(
            [analyze_ota_ac(sweeps[name, "vcm"]) for name, _label in cases],
            labels=labels,
            output_path=output_dir / "ota_common_mode",
        ),
        *plot_ota_supply(
            [analyze_ota_ac(sweeps[name, "supply"]) for name, _label in cases],
            labels=labels,
            output_path=output_dir / "ota_supply",
        ),
    )


def main() -> None:
    """Run one explicitly selected analysis pipeline."""
    targets: dict[str, Callable[[Path], tuple[Path, ...]]] = {
        target.__name__: target
        for target in (
            adc_transfer_curve_study,
            adc_ramp_nonlinearity_study,
            adc_behavioral_nonlinearity_study,
            adc_behavioral_energy_study,
            adc_behavioral_sample_rate_study,
            adc_behavioral_calibration_study,
            adc_behavioral_trajectory_study,
            adc_behavioral_architecture_study,
            adc_behavioral_noise_spectrum_study,
            adc_behavioral_input_frequency_study,
            adc_calibration_study,
            adc_sequence_study,
            adc_interferer_study,
            adc_sample_rate_study,
            adc_power_study,
            comp_behavioral_offset_noise_study,
            comp_system_common_mode_study,
            comp_system_sampling_noise_study,
            comp_candidate_sweep_study,
            comp_topology_study,
            cdac_system_cap_mismatch_study,
            delay_characterization_study,
            latch_characterization_study,
            ota_characterization_study,
        )
    }

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("target", choices=sorted(targets), help="analysis pipeline to run")
    args = parser.parse_args()

    domain = (
        args.target.split("_", 1)[0]
        if args.target.startswith(("comp_", "cdac_", "delay_", "latch_", "ota_"))
        else "adc"
    )
    timestamp = datetime.now().astimezone().strftime("%Y%m%d_%H%M%S")
    output_dir = BASE_PATH / "build/analysis" / domain / timestamp
    output_dir.mkdir(parents=True, exist_ok=False)
    print(f"Analysis output: {output_dir}")
    artifacts = targets[args.target](output_dir)
    print(f"Completed {args.target}: {len(artifacts)} artifacts")


if __name__ == "__main__":
    main()
