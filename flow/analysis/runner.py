"""Explicit, manually invoked measurement -> analysis -> plot pipelines.

Each function names its input files directly. Add a pipeline only after its
capture has been inspected and the corresponding analysis has been validated.
There is intentionally no automatic discovery of run directories or analysis
pipelines; each pipeline names and validates its input campaign.

Run one named pipeline from the repository root with:

    uv run python -m flow.analysis.runner adc_noise_vs_rate

Omit the target name to run every registered pipeline. Comparator targets write
beneath ``build/analysis/comp``; the remaining targets write beneath
``build/analysis/adc``. Each analysis domain uses one timestamped directory per
invocation.
"""

from __future__ import annotations

import argparse
import csv
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from time import perf_counter

import hdl21 as h
import numpy as np

from flow.analysis.adc import (
    analyze_adc_code_distribution,
    analyze_adc_decision_paths,
    analyze_adc_dynamic,
    analyze_adc_dynamic_sweep,
    analyze_adc_noise_sweep,
    analyze_adc_power_sweep,
    analyze_adc_power_waveform,
    analyze_adc_ramp,
    analyze_adc_transfer,
    combine_adc_noise_comparison,
)
from flow.analysis.calibration1 import analyze as analyze_calibration1
from flow.analysis.calibration2 import analyze as analyze_calibration2
from flow.analysis.calibration3 import analyze as analyze_calibration3
from flow.analysis.cdac import analyze_cdac_cap_mismatch_campaign
from flow.analysis.comp import (
    analyze_comp_candidate_sweep,
    analyze_comp_offset_noise,
    classify_comp_common_mode_validity,
)
from flow.analysis.io import read_measurement
from flow.analysis.plots import (
    plot_adc_calibration_weights,
    plot_adc_code_distribution,
    plot_adc_decision_path_density,
    plot_adc_decision_paths,
    plot_adc_dynamic,
    plot_adc_noise_distribution_sweep,
    plot_adc_noise_sweep,
    plot_adc_power_sweep,
    plot_adc_power_waveform,
    plot_adc_ramp_histogram,
    plot_adc_ramp_nonlinearity,
    plot_adc_ramp_transfer,
    plot_adc_ramp_weights,
    plot_adc_transfer,
    plot_cdac_cap_mismatch,
    plot_cdac_cap_mismatch_comparison,
    plot_comp_candidate_sweep,
    plot_comp_common_mode_campaign,
    plot_comp_noise_power_tradeoff,
    plot_comp_sampling_campaign,
    plot_waveforms,
)
from flow.analysis.types import (
    MeasAdcExt,
    MeasAdcInt,
    MeasCompExt,
    MeasCompInt,
)
from flow.analysis.waveform import analyze_measurement_waveforms
from flow.scans.params import load_board_map

BASE_PATH = Path(__file__).resolve().parents[2]


def adc_transfer_curve(output_dir: Path) -> tuple[Path, ...]:
    """Plot the accepted physical ADC00 static transfer campaign."""

    adc_indices = (0,)
    expected_input_v = tuple((step - 500) * 0.0015 for step in range(1_001))
    expected_conversions = 100
    run_dir = BASE_PATH / "build/scan_adc/20260818_135848"
    measurement_paths = sorted(run_dir.glob("*.h5"))
    if len(measurement_paths) != len(adc_indices) * len(expected_input_v):
        raise ValueError(
            f"accepted ADC transfer run requires {len(adc_indices) * len(expected_input_v)} H5 files, "
            f"found {len(measurement_paths)}"
        )

    measurements_by_adc: dict[int, list[MeasAdcExt]] = {adc_index: [] for adc_index in adc_indices}
    for input_h5 in measurement_paths:
        measurement = read_measurement(input_h5)
        if not isinstance(measurement, MeasAdcExt):
            raise TypeError(f"{input_h5} contains {type(measurement).__name__}, expected MeasAdcExt")
        adc_index = measurement.param.observed_adc
        source = measurement.param.tb.vin_diff
        if (
            measurement.info.backend != "physical"
            or measurement.param.campaign != "adc_transfer"
            or measurement.param.board_id != "00"
            or adc_index not in adc_indices
            or measurement.param.tb.conversions != expected_conversions
            or not isinstance(source, h.Vdc.Params)
            or float(measurement.param.tb.vin_cm.dc) != 0.700
            or float(measurement.info.readbacks.get("actual_sample_rate_hz", 0.0)) != 10.0e6
            or int(measurement.info.readbacks.get("fastrx_lost_count", 0))
            or int(measurement.info.readbacks.get("spi_mismatches", 0))
        ):
            raise ValueError(f"{input_h5} is not an accepted pre-rework ADC transfer point")
        if len(measurement.daq.dout) != expected_conversions or not np.allclose(
            measurement.daq.vin_diff_v,
            float(source.dc),
            rtol=0.0,
            atol=1.0e-12,
        ):
            raise ValueError(f"{input_h5} contains incomplete or mislabelled transfer data")
        measurements_by_adc[adc_index].append(measurement)

    artifacts = []
    for adc_index in adc_indices:
        measurements = measurements_by_adc[adc_index]
        observed_input_v = tuple(sorted(float(measurement.param.tb.vin_diff.dc) for measurement in measurements))
        if not np.allclose(observed_input_v, expected_input_v, rtol=0.0, atol=1.0e-12):
            raise ValueError(f"ADC{adc_index:02d} transfer inputs are incomplete or duplicated")
        analysis = analyze_adc_transfer(measurements)
        artifacts.extend(
            plot_adc_transfer(
                measurements,
                analysis,
                output_path=output_dir / f"adc{adc_index:02d}_transfer_curve",
            )
        )
    return tuple(artifacts)


def adc_ramp_nonlinearity(output_dir: Path) -> tuple[Path, ...]:
    """Compare uncalibrated DOUT with BOUT decoded by accepted CDAC weights."""

    adc_indices = (0, 1, 2, 3)
    board_id = "00"
    ramp_expected_conversions = 4_000_000
    ramp_run_dir = BASE_PATH / "build/scan_adc/20260812_011910"
    cdac_run_dirs = tuple(
        BASE_PATH / "build/scan_cdac" / name for name in ("20260804_171234", "20260804_193030", "20260804_193631")
    )
    ramp_paths = sorted(ramp_run_dir.glob("*.h5"))
    if not ramp_paths:
        raise FileNotFoundError(2, "accepted ADC ramp inputs not found", ramp_run_dir)
    ramp_by_adc = {}
    for path in ramp_paths:
        measurement = read_measurement(path)
        if not isinstance(measurement, MeasAdcExt):
            raise TypeError(f"{path} contains {type(measurement).__name__}, expected MeasAdcExt")
        adc_index = measurement.param.observed_adc
        if (
            measurement.param.campaign != "adc_ramp"
            or measurement.param.board_id != board_id
            or adc_index not in adc_indices
            or len(measurement.daq.dout) != ramp_expected_conversions
            or int(measurement.info.readbacks.get("fastrx_lost_count", 0))
            or int(measurement.info.readbacks.get("spi_mismatches", 0))
            or adc_index in ramp_by_adc
        ):
            raise ValueError(f"{path} is not a complete, valid ADC00--ADC03 ramp capture")
        ramp_by_adc[adc_index] = measurement
    if set(ramp_by_adc) != set(adc_indices):
        raise ValueError("accepted ramp run does not contain exactly ADC00--ADC03")

    cdac_paths_by_run = tuple(tuple(sorted(run_dir.glob("*.h5"))) for run_dir in cdac_run_dirs)
    if not any(cdac_paths_by_run):
        raise FileNotFoundError(2, "accepted A-to-B CDAC inputs not found", cdac_run_dirs[0])
    comparator_calibrations = load_board_map()["boards"][board_id].get("comparator_calibration", {})
    comparator_offset_v_by_adc = {
        adc_index: float(comparator_calibrations[adc_index]["offset_v"]) for adc_index in adc_indices
    }
    cdac_groups, _cdac_analyses = analyze_cdac_cap_mismatch_campaign(
        tuple(tuple(read_measurement(path) for path in paths) for paths in cdac_paths_by_run),
        adc_indices=adc_indices,
        board_id=board_id,
        comparator_offset_v_by_adc=comparator_offset_v_by_adc,
    )
    cdac_group_by_adc = {group[0].param.observed_adc: group for group in cdac_groups}
    artifacts = []
    analyses = []
    for adc_index in adc_indices:
        ramp_measurement = ramp_by_adc[adc_index]
        calibration = analyze_calibration1(
            cdac_group_by_adc[adc_index],
            comparator_offset_v=comparator_offset_v_by_adc[adc_index],
        )
        analysis = analyze_adc_ramp(ramp_measurement, calibrations=(calibration,))
        if any(curve.maximum_transfer_reversal_dout > 2.0 for curve in analysis.curves):
            raise ValueError(f"ADC{adc_index:02d} ramp transfer is not monotonic within 2 LSB")
        analyses.append(analysis)
        artifacts.extend(
            plot_adc_ramp_transfer(
                analysis,
                output_path=output_dir / f"adc{adc_index:02d}_ramp_transfer",
            )
        )
        artifacts.extend(
            plot_adc_ramp_histogram(
                analysis,
                output_path=output_dir / f"adc{adc_index:02d}_ramp_histogram",
            )
        )
        artifacts.extend(
            plot_adc_ramp_weights(
                analysis,
                output_path=output_dir / f"adc{adc_index:02d}_ramp_weights",
            )
        )
        artifacts.extend(
            plot_adc_ramp_nonlinearity(
                analysis,
                output_path=output_dir / f"adc{adc_index:02d}_ramp_nonlinearity",
            )
        )

    csv_path = output_dir / "adc00_adc03_ramp_metrics.csv"
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    with csv_path.open("w", newline="") as output:
        writer = csv.writer(output)
        writer.writerow(
            (
                "adc_index",
                "decoding",
                "sample_count",
                "retained_sample_count",
                "reset_excluded_sample_count",
                "sample_rate_hz",
                "ramp_frequency_hz",
                "maximum_abs_dnl_lsb",
                "maximum_abs_inl_lsb",
                "missing_codes",
                "maximum_transfer_reversal_dout",
            )
        )
        for analysis in analyses:
            for curve in analysis.curves:
                writer.writerow(
                    (
                        analysis.adc_index,
                        curve.decoding,
                        analysis.sample_count,
                        analysis.retained_sample_count,
                        analysis.reset_excluded_sample_count,
                        analysis.sample_rate_hz,
                        analysis.ramp_frequency_hz,
                        curve.maximum_abs_dnl,
                        curve.maximum_abs_inl,
                        curve.missing_codes,
                        curve.maximum_transfer_reversal_dout,
                    )
                )
    artifacts.append(csv_path)
    return tuple(artifacts)


def adc_calibration(output_dir: Path) -> tuple[Path, ...]:
    """Run all three ADC00 digital calibrations and compare them uniformly."""

    # TODO: Extend this target to ADC01--ADC03 after ADC00 passes the
    # independent-capture acceptance criteria.
    adc_index = 0
    board_id = "00"
    ramp_expected_conversions = 4_000_000
    ramp_run_dir = BASE_PATH / "build/scan_adc/20260812_011910"
    ramp_paths = [path for path in sorted(ramp_run_dir.glob("*.h5")) if f"adc{adc_index:02d}" in path.name]
    if len(ramp_paths) != 1:
        raise FileNotFoundError(2, "accepted ADC00 ramp input not found", ramp_run_dir)
    measurement = read_measurement(ramp_paths[0])
    if not isinstance(measurement, MeasAdcExt):
        raise TypeError(f"{ramp_paths[0]} contains {type(measurement).__name__}, expected MeasAdcExt")
    if (
        measurement.param.campaign != "adc_ramp"
        or measurement.param.observed_adc != adc_index
        or measurement.param.board_id != board_id
        or len(measurement.daq.dout) != ramp_expected_conversions
        or int(measurement.info.readbacks.get("fastrx_lost_count", 0))
        or int(measurement.info.readbacks.get("spi_mismatches", 0))
    ):
        raise ValueError(f"{ramp_paths[0]} is not a complete, valid ADC00 ramp capture")

    cdac_run_dirs = tuple(
        BASE_PATH / "build/scan_cdac" / name for name in ("20260804_171234", "20260804_193030", "20260804_193631")
    )
    cdac_paths_by_run = tuple(
        tuple(path for path in sorted(run_dir.glob("*.h5")) if f"adc{adc_index:02d}" in path.name)
        for run_dir in cdac_run_dirs
    )
    if not any(cdac_paths_by_run):
        raise FileNotFoundError(2, "accepted ADC00 A-to-B CDAC inputs not found", cdac_run_dirs[0])
    comparator_calibrations = load_board_map()["boards"][board_id].get("comparator_calibration", {})
    comparator_offset_v = float(comparator_calibrations[adc_index]["offset_v"])
    cdac_groups, _cdac_analyses = analyze_cdac_cap_mismatch_campaign(
        tuple(tuple(read_measurement(path) for path in paths) for paths in cdac_paths_by_run),
        adc_indices=(adc_index,),
        board_id=board_id,
        comparator_offset_v_by_adc={adc_index: comparator_offset_v},
    )
    cdac_measurements = cdac_groups[0]

    nominal_ramp = analyze_adc_ramp(measurement)
    calibrations = (
        analyze_calibration1(
            cdac_measurements,
            comparator_offset_v=comparator_offset_v,
        ),
        analyze_calibration2(measurement, nominal_ramp),
        analyze_calibration3(measurement, nominal_ramp),
    )
    ramp = analyze_adc_ramp(measurement, calibrations=calibrations)

    artifacts = list(
        plot_adc_calibration_weights(
            calibrations,
            output_path=output_dir / f"adc{adc_index:02d}_calibration_weights",
        )
    )
    artifacts.extend(
        plot_adc_ramp_transfer(
            ramp,
            output_path=output_dir / f"adc{adc_index:02d}_calibration_transfer",
        )
    )
    artifacts.extend(
        plot_adc_ramp_histogram(
            ramp,
            output_path=output_dir / f"adc{adc_index:02d}_calibration_code_density",
        )
    )
    artifacts.extend(
        plot_adc_ramp_nonlinearity(
            ramp,
            output_path=output_dir / f"adc{adc_index:02d}_calibration_inl_dnl",
        )
    )

    calibration_by_method = {calibration.method: calibration for calibration in calibrations}
    metrics_path = output_dir / f"adc{adc_index:02d}_calibration_metrics.csv"
    metrics_path.parent.mkdir(parents=True, exist_ok=True)
    with metrics_path.open("w", newline="") as output:
        writer = csv.writer(output)
        writer.writerow(
            (
                "decoding",
                "training_sample_count",
                "validation_sample_count",
                "weights_from_measurement",
                "output_gain",
                "output_offset_lsb",
                "maximum_abs_dnl_lsb",
                "maximum_abs_inl_lsb",
                "missing_codes",
                "maximum_transfer_reversal_lsb",
            )
        )
        for curve in ramp.curves:
            calibration = calibration_by_method.get(curve.decoding)
            writer.writerow(
                (
                    curve.decoding,
                    0 if calibration is None else calibration.training_sample_count,
                    0 if calibration is None else calibration.validation_sample_count,
                    0 if calibration is None else int(np.count_nonzero(calibration.measured_weight_mask)),
                    1.0 if calibration is None else calibration.output_gain,
                    0.0 if calibration is None else calibration.output_offset_lsb,
                    curve.maximum_abs_dnl,
                    curve.maximum_abs_inl,
                    curve.missing_codes,
                    curve.maximum_transfer_reversal_dout,
                )
            )
    artifacts.append(metrics_path)

    weights_path = output_dir / f"adc{adc_index:02d}_calibration_weights.csv"
    with weights_path.open("w", newline="") as output:
        writer = csv.writer(output)
        writer.writerow(
            (
                "decision_index",
                "ideal_weight_lsb",
                *(
                    field
                    for calibration in calibrations
                    for field in (
                        f"{calibration.method}_weight_lsb",
                        f"{calibration.method}_from_measurement",
                    )
                ),
            )
        )
        for decision_index in range(17):
            writer.writerow(
                (
                    decision_index,
                    calibrations[0].nominal_weights[decision_index],
                    *(
                        value
                        for calibration in calibrations
                        for value in (
                            calibration.calibrated_weights[decision_index],
                            bool(calibration.measured_weight_mask[decision_index]),
                        )
                    ),
                )
            )
    artifacts.append(weights_path)
    return tuple(artifacts)


def adc00_fixed_input_noise(output_dir: Path) -> tuple[Path, ...]:
    """Analyze the accepted post-filter ADC00 fixed-input noise capture."""

    run_dir = BASE_PATH / "build/scan_adc/20260819_113714"
    rates_mbd = (320, 960, 1600)
    expected_conversions = 100_000
    msmt_list = []
    for rate_mbd in rates_mbd:
        matches = sorted(
            run_dir.glob(
                f"*_00_adc00_{rate_mbd}mbd_dcp50mv_logicp2sym_vcm700mv_vdda1200mv_vddd1200mv_vddac1200mv_t25c.h5"
            )
        )
        if len(matches) != 1:
            raise ValueError(f"ADC00 post-filter noise campaign requires one {rate_mbd} MBd file, found {len(matches)}")
        measurement = read_measurement(matches[0])
        if not isinstance(measurement, MeasAdcExt):
            raise TypeError(f"{matches[0]} contains {type(measurement).__name__}, expected MeasAdcExt")
        if (
            measurement.param.observed_adc != 0
            or measurement.param.campaign != "adc"
            or not isinstance(measurement.param.vin_diff, h.Vdc.Params)
            or not np.isclose(float(measurement.param.vin_diff.dc), 0.050)
            or not np.isclose(float(measurement.param.vin_cm.dc), 0.700)
            or len(measurement.daq.dout) != expected_conversions
            or int(measurement.info.readbacks.get("fastrx_lost_count", 0))
            or int(measurement.info.readbacks.get("spi_mismatches", 0))
        ):
            raise ValueError(f"{matches[0]} is not a complete ADC00 post-filter fixed-input capture")
        msmt_list.append(measurement)

    analysis = analyze_adc_noise_sweep(msmt_list)
    artifacts = list(
        plot_adc_noise_sweep(
            msmt_list,
            analysis,
            output_path=output_dir / "adc00_50mv_noise_vs_conversion_rate",
        )
    )
    artifacts.extend(
        plot_adc_noise_distribution_sweep(
            msmt_list,
            analysis,
            output_path=output_dir / "adc00_50mv_output_code_distributions",
        )
    )
    for rate_msps, measurement in zip((2, 6, 10), msmt_list, strict=True):
        artifacts.extend(
            plot_adc_decision_path_density(
                measurement,
                analyze_adc_decision_paths(measurement, selection="all"),
                output_path=output_dir / f"adc00_50mv_{rate_msps}msps_decision_path_density",
            )
        )
    return tuple(artifacts)


def adc_noise_vs_rate(output_dir: Path) -> tuple[Path, ...]:
    """Compare configured physical ADC input-referred noise across rate and backends."""

    ADC_INDICES = (0, 1)
    PHYSICAL_NOISE_RUN_DIRS = {
        50: BASE_PATH / "build/scan_adc/20260801_194930",
        100: BASE_PATH / "build/scan_adc/20260802_021624",
    }
    SINE_RUN_DIR = BASE_PATH / "build/scan_adc/20260730_215145_complete"
    GENERATED_NOISE_RUN_DIR = BASE_PATH / "build/adc/hdl21gen_noise_vs_rate/20260801_0821"
    PEX_NOISE_RUN_DIR = BASE_PATH / "build/adc/frida65a_noise_vs_rate/20260731_2353"
    RATES_MBD = tuple(range(80, 1601, 40))
    SIMULATION_RATES_MSPS = (2, 6, 10)
    EXPECTED_CONVERSIONS = 100_000

    if (
        not ADC_INDICES
        or len(set(ADC_INDICES)) != len(ADC_INDICES)
        or any(not isinstance(adc_index, int) or not 0 <= adc_index < 16 for adc_index in ADC_INDICES)
    ):
        raise ValueError("ADC_INDICES must contain unique ADC indices in 0..15")
    physical_measurements: dict[int, dict[int, list[MeasAdcExt]]] = {}
    for input_mv, run_dir in PHYSICAL_NOISE_RUN_DIRS.items():
        measurements_by_adc = {}
        for adc_index in ADC_INDICES:
            adc_measurements = []
            for rate_mbd in RATES_MBD:
                matches = sorted(
                    run_dir.glob(
                        f"*_00_adc{adc_index:02d}_{rate_mbd}mbd_dcp{input_mv}mv_logicp2sym_"
                        "vcm600mv_vdda1200mv_vddd1200mv_vddac1200mv_t25c.h5"
                    )
                )
                if len(matches) != 1:
                    raise ValueError(
                        f"ADC{adc_index:02d} {input_mv} mV noise campaign requires one {rate_mbd} MBd file, "
                        f"found {len(matches)}"
                    )
                measurement = read_measurement(matches[0])
                if not isinstance(measurement, MeasAdcExt):
                    raise TypeError(f"{matches[0]} contains {type(measurement).__name__}, expected MeasAdcExt")
                adc_measurements.append(measurement)
            expected_input_v = input_mv * 1.0e-3
            if any(
                measurement.param.observed_adc != adc_index
                or not isinstance(measurement.param.tb.vin_diff, h.Vdc.Params)
                or not np.isclose(float(measurement.param.tb.vin_diff.dc), expected_input_v)
                for measurement in adc_measurements
            ):
                raise ValueError(
                    f"ADC{adc_index:02d} physical noise campaign requires a fixed {input_mv} mV differential input"
                )
            if any(
                len(measurement.daq.dout) != EXPECTED_CONVERSIONS
                or int(measurement.info.readbacks.get("fastrx_lost_count", 0))
                or int(measurement.info.readbacks.get("spi_mismatches", 0))
                for measurement in adc_measurements
            ):
                raise ValueError(
                    f"ADC{adc_index:02d} physical {input_mv} mV noise campaign contains incomplete or invalid captures"
                )
            measurements_by_adc[adc_index] = adc_measurements
        physical_measurements[input_mv] = measurements_by_adc

    generated_measurements = []
    pex_measurements = []
    for rate_msps in SIMULATION_RATES_MSPS:
        generated_path = GENERATED_NOISE_RUN_DIR / f"{rate_msps}msps_cm600mv_dc50mv/result.h5"
        generated_measurement = read_measurement(generated_path)
        if not isinstance(generated_measurement, MeasAdcInt):
            raise TypeError(f"{generated_path} contains {type(generated_measurement).__name__}, expected MeasAdcInt")
        generated_measurements.append(generated_measurement)

        pex_path = PEX_NOISE_RUN_DIR / f"{rate_msps}msps_cm600mv_dc50mv/result.h5"
        pex_measurement = read_measurement(pex_path)
        if not isinstance(pex_measurement, MeasAdcInt):
            raise TypeError(f"{pex_path} contains {type(pex_measurement).__name__}, expected MeasAdcInt")
        pex_measurements.append(pex_measurement)
    sine_measurements: dict[int, list[MeasAdcExt]] = {}
    for adc_index in ADC_INDICES:
        adc_measurements = []
        for rate_mbd in RATES_MBD:
            matches = sorted(
                SINE_RUN_DIR.glob(
                    f"*_00_adc{adc_index:02d}_{rate_mbd}mbd_sin9998.77hz_p0mv_1000mvpp_"
                    "logicp2sym_vcm600mv_vdda1200mv_vddd1200mv_vddac1200mv_t25c.h5"
                )
            )
            if len(matches) != 1:
                raise ValueError(
                    f"ADC{adc_index:02d} sine campaign requires one {rate_mbd} MBd file, found {len(matches)}"
                )
            measurement = read_measurement(matches[0])
            if not isinstance(measurement, MeasAdcExt):
                raise TypeError(f"{matches[0]} contains {type(measurement).__name__}, expected MeasAdcExt")
            if measurement.param.observed_adc != adc_index:
                raise ValueError(f"ADC{adc_index:02d} sine campaign contains a mismatched ADC index")
            adc_measurements.append(measurement)
        sine_measurements[adc_index] = adc_measurements

    generated_noise = analyze_adc_noise_sweep(generated_measurements)
    pex_noise = analyze_adc_noise_sweep(pex_measurements)
    artifacts = []
    reference_rates = None
    for adc_index in ADC_INDICES:
        dc_measurements = physical_measurements[50][adc_index]
        dc100_measurements = physical_measurements[100][adc_index]
        physical_noise = analyze_adc_noise_sweep(dc_measurements)
        physical_noise_100mv = analyze_adc_noise_sweep(dc100_measurements)
        sine_dynamic = analyze_adc_dynamic_sweep(sine_measurements[adc_index])
        order = np.argsort(physical_noise.active_conversion_rate_hz)
        physical_rates = physical_noise.active_conversion_rate_hz[order]
        if reference_rates is None:
            reference_rates = physical_rates
        elif not np.array_equal(physical_rates, reference_rates):
            raise ValueError("configured ADC physical noise sweeps use different conversion rates")
        comparison_measurements = [
            *dc_measurements,
            *dc_measurements,
            *dc100_measurements,
            *sine_measurements[adc_index],
        ]
        series_labels = [
            *("Input stimulus noise" for _ in physical_rates),
            *("Measured (50 mV DC)" for _ in dc_measurements),
            *("Measured (100 mV DC)" for _ in dc100_measurements),
            *("Measured (1 V sine)" for _ in sine_measurements[adc_index]),
        ]
        simulated_noise_sweeps = []
        if adc_index == ADC_INDICES[0]:
            simulated_noise_sweeps.extend((generated_noise, pex_noise))
            comparison_measurements.extend((*generated_measurements, *pex_measurements))
            series_labels.extend(
                (
                    *("SPICE Ideal (50 mV DC)" for _ in generated_measurements),
                    *("SPICE PEX (50 mV DC)" for _ in pex_measurements),
                )
            )

        comparison = combine_adc_noise_comparison(
            (physical_noise, physical_noise_100mv),
            sine_dynamic,
            simulated_noise_sweeps,
            series_labels=series_labels,
        )
        artifacts.extend(
            plot_adc_noise_sweep(
                comparison_measurements,
                comparison,
                output_path=output_dir / f"adc{adc_index:02d}_noise_vs_conversion_rate",
            )
        )
    return tuple(artifacts)


def adc_code_distributions(output_dir: Path) -> tuple[Path, ...]:
    """Plot configured ADC fixed-input distributions and selected decision paths."""

    ADC_INDICES = (0, 1)
    PHYSICAL_NOISE_RUN_DIRS = {
        50: BASE_PATH / "build/scan_adc/20260801_194930",
        100: BASE_PATH / "build/scan_adc/20260802_021624",
    }
    GENERATED_NOISE_RUN_DIR = BASE_PATH / "build/adc/hdl21gen_noise_vs_rate/20260801_0821"
    RATES_MBD = tuple(range(80, 1601, 40))
    SIMULATION_RATES_MSPS = (2, 6, 10)
    DECISION_PATH_RATES_MSPS = (2, 10)
    EXPECTED_CONVERSIONS = 100_000

    if (
        not ADC_INDICES
        or len(set(ADC_INDICES)) != len(ADC_INDICES)
        or any(not isinstance(adc_index, int) or not 0 <= adc_index < 16 for adc_index in ADC_INDICES)
    ):
        raise ValueError("ADC_INDICES must contain unique ADC indices in 0..15")
    physical_measurements: dict[int, dict[int, list[MeasAdcExt]]] = {}
    for input_mv, run_dir in PHYSICAL_NOISE_RUN_DIRS.items():
        measurements_by_adc = {}
        for adc_index in ADC_INDICES:
            adc_measurements = []
            for rate_mbd in RATES_MBD:
                matches = sorted(
                    run_dir.glob(
                        f"*_00_adc{adc_index:02d}_{rate_mbd}mbd_dcp{input_mv}mv_logicp2sym_"
                        "vcm600mv_vdda1200mv_vddd1200mv_vddac1200mv_t25c.h5"
                    )
                )
                if len(matches) != 1:
                    raise ValueError(
                        f"ADC{adc_index:02d} {input_mv} mV noise campaign requires one {rate_mbd} MBd file, "
                        f"found {len(matches)}"
                    )
                measurement = read_measurement(matches[0])
                if not isinstance(measurement, MeasAdcExt):
                    raise TypeError(f"{matches[0]} contains {type(measurement).__name__}, expected MeasAdcExt")
                adc_measurements.append(measurement)
            expected_input_v = input_mv * 1.0e-3
            if any(
                measurement.param.observed_adc != adc_index
                or not isinstance(measurement.param.tb.vin_diff, h.Vdc.Params)
                or not np.isclose(float(measurement.param.tb.vin_diff.dc), expected_input_v)
                for measurement in adc_measurements
            ):
                raise ValueError(
                    f"ADC{adc_index:02d} physical noise campaign requires a fixed {input_mv} mV differential input"
                )
            if any(
                len(measurement.daq.dout) != EXPECTED_CONVERSIONS
                or int(measurement.info.readbacks.get("fastrx_lost_count", 0))
                or int(measurement.info.readbacks.get("spi_mismatches", 0))
                for measurement in adc_measurements
            ):
                raise ValueError(
                    f"ADC{adc_index:02d} physical {input_mv} mV noise campaign contains incomplete or invalid captures"
                )
            measurements_by_adc[adc_index] = adc_measurements
        physical_measurements[input_mv] = measurements_by_adc

    generated_measurements = []
    for rate_msps in SIMULATION_RATES_MSPS:
        path = GENERATED_NOISE_RUN_DIR / f"{rate_msps}msps_cm600mv_dc50mv/result.h5"
        measurement = read_measurement(path)
        if not isinstance(measurement, MeasAdcInt):
            raise TypeError(f"{path} contains {type(measurement).__name__}, expected MeasAdcInt")
        generated_measurements.append(measurement)
    artifacts = []
    for input_mv in PHYSICAL_NOISE_RUN_DIRS:
        for adc_index in ADC_INDICES:
            adc_measurements = physical_measurements[input_mv][adc_index]
            artifacts.extend(
                plot_adc_noise_distribution_sweep(
                    adc_measurements,
                    analyze_adc_noise_sweep(adc_measurements),
                    output_path=output_dir / f"adc{adc_index:02d}_{input_mv}mv_dc_output_code_distributions",
                )
            )

    for rate_msps, measurement in zip(SIMULATION_RATES_MSPS, generated_measurements, strict=True):
        artifacts.extend(
            plot_adc_code_distribution(
                [measurement],
                analyze_adc_code_distribution([measurement]),
                output_path=output_dir / f"spice_hdl21gen_{rate_msps}msps_output_code_histogram",
            )
        )
        artifacts.extend(
            plot_adc_decision_paths(
                measurement,
                analyze_adc_decision_paths(measurement, selection="all"),
                output_path=output_dir / f"spice_hdl21gen_{rate_msps}msps_decision_paths",
            )
        )

    for input_mv in PHYSICAL_NOISE_RUN_DIRS:
        for adc_index in ADC_INDICES:
            adc_measurements = physical_measurements[input_mv][adc_index]
            for rate_msps in DECISION_PATH_RATES_MSPS:
                matches = [
                    measurement
                    for measurement in adc_measurements
                    if np.isclose(
                        float(measurement.info.readbacks["active_conversion_rate_hz"]),
                        rate_msps * 1e6,
                    )
                ]
                if len(matches) != 1:
                    raise ValueError(
                        f"ADC{adc_index:02d} {input_mv} mV campaign does not contain one {rate_msps} MSPS run"
                    )
                analysis = analyze_adc_decision_paths(matches[0], selection="all")
                output_path = output_dir / (f"adc{adc_index:02d}_{input_mv}mv_{rate_msps}msps_decision_path_density")
                artifacts.extend(plot_adc_decision_path_density(matches[0], analysis, output_path=output_path))
    return tuple(artifacts)


def adc_power_vs_rate(output_dir: Path) -> tuple[Path, ...]:
    """Plot measured and simulated power sweeps plus detailed waveforms."""

    ADC_INDICES = (0, 1)
    SINE_RUN_DIR = BASE_PATH / "build/scan_adc/20260730_215145_complete"
    IDEAL_RUN_DIR = BASE_PATH / "build/adc/hdl21gen_noise_vs_rate/20260801_0821"
    PEX_RUN_DIR = BASE_PATH / "build/adc/frida65a_noise_vs_rate/20260731_2353"
    RATES_MBD = tuple(range(80, 1601, 40))
    SIMULATION_RATES_MSPS = (2, 6, 10)
    DETAIL_RATE_MBD = 80
    SIMULATION_DETAIL_RATE_MSPS = 10

    if (
        not ADC_INDICES
        or len(set(ADC_INDICES)) != len(ADC_INDICES)
        or any(not isinstance(adc_index, int) or not 0 <= adc_index < 16 for adc_index in ADC_INDICES)
    ):
        raise ValueError("ADC_INDICES must contain unique ADC indices in 0..15")
    sine_measurements_by_adc: dict[int, list[MeasAdcExt]] = {}
    for adc_index in ADC_INDICES:
        adc_measurements = []
        for rate_mbd in RATES_MBD:
            matches = sorted(
                SINE_RUN_DIR.glob(
                    f"*_00_adc{adc_index:02d}_{rate_mbd}mbd_sin9998.77hz_p0mv_1000mvpp_"
                    "logicp2sym_vcm600mv_vdda1200mv_vddd1200mv_vddac1200mv_t25c.h5"
                )
            )
            if len(matches) != 1:
                raise ValueError(
                    f"ADC{adc_index:02d} sine campaign requires one {rate_mbd} MBd file, found {len(matches)}"
                )
            measurement = read_measurement(matches[0])
            if not isinstance(measurement, MeasAdcExt):
                raise TypeError(f"{matches[0]} contains {type(measurement).__name__}, expected MeasAdcExt")
            if measurement.param.observed_adc != adc_index:
                raise ValueError(f"ADC{adc_index:02d} sine campaign contains a mismatched ADC index")
            adc_measurements.append(measurement)
        sine_measurements_by_adc[adc_index] = adc_measurements

    simulation_measurements = {}
    for source, run_dir in (("ideal", IDEAL_RUN_DIR), ("pex", PEX_RUN_DIR)):
        measurements = []
        for rate_msps in SIMULATION_RATES_MSPS:
            path = run_dir / f"{rate_msps}msps_cm600mv_dc50mv/result.h5"
            measurement = read_measurement(path)
            if not isinstance(measurement, MeasAdcInt):
                raise TypeError(f"{path} contains {type(measurement).__name__}, expected MeasAdcInt")
            measurements.append(measurement)
        simulation_measurements[source] = measurements

    simulation_power = {
        source: analyze_adc_power_sweep(measurements) for source, measurements in simulation_measurements.items()
    }
    expected_simulation_rates_hz = np.asarray(SIMULATION_RATES_MSPS, dtype=np.float64) * 1e6
    for source, analysis in simulation_power.items():
        if not np.allclose(
            np.sort(analysis.active_conversion_rate_hz),
            expected_simulation_rates_hz,
            rtol=0.0,
            atol=1e-6,
        ):
            raise ValueError(f"SPICE {source} power sweep does not contain exactly 2, 6, and 10 MSPS")

    artifacts = []
    for adc_index in ADC_INDICES:
        measurements = sine_measurements_by_adc[adc_index]
        artifacts.extend(
            plot_adc_power_sweep(
                measurements,
                analyze_adc_power_sweep(measurements),
                output_path=output_dir / f"adc_power_vs_conversion_rate_adc{adc_index:02d}",
            )
        )
    for source in ("ideal", "pex"):
        measurements = simulation_measurements[source]
        analysis = simulation_power[source]
        artifacts.extend(
            plot_adc_power_sweep(
                measurements,
                analysis,
                output_path=output_dir / f"spice_{source}_power_vs_conversion_rate",
            )
        )
        detail_measurement = measurements[SIMULATION_RATES_MSPS.index(SIMULATION_DETAIL_RATE_MSPS)]
        artifacts.extend(
            plot_adc_power_waveform(
                analyze_adc_power_waveform(detail_measurement),
                output_path=output_dir / f"spice_{source}_{SIMULATION_DETAIL_RATE_MSPS}msps_supply_power",
            )
        )
    for adc_index in ADC_INDICES:
        detail_measurement = sine_measurements_by_adc[adc_index][RATES_MBD.index(DETAIL_RATE_MBD)]
        artifacts.extend(
            plot_waveforms(
                analyze_measurement_waveforms(detail_measurement),
                output_path=output_dir / f"adc{adc_index:02d}_{DETAIL_RATE_MBD}mbd_sine_waveforms",
            )
        )
        artifacts.extend(
            plot_adc_dynamic(
                detail_measurement,
                analyze_adc_dynamic(detail_measurement),
                output_path=output_dir / f"adc{adc_index:02d}_{DETAIL_RATE_MBD}mbd_sine_fit_and_spectrum",
            )
        )
    return tuple(artifacts)


def adc_rate_characterization(output_dir: Path) -> tuple[Path, ...]:
    """Run the configured ADC rate-sweep noise, code-distribution, and power analyses."""

    return (
        *adc_noise_vs_rate(output_dir),
        *adc_code_distributions(output_dir),
        *adc_power_vs_rate(output_dir),
    )


def adc_noise_vs_comp_time(output_dir: Path) -> tuple[Path, ...]:
    """Plot ADC input-referred noise versus conversion rate and comparator timing."""

    ADC_INDICES = (0, 1)
    LOGIC_OFFSET_RUNS = {
        0: (
            BASE_PATH / "build/scan_adc/20260802_081407",
            "*_00_adc00_*mbd_dcp50mv_logic*sym_vcm800mv_*.h5",
        ),
        1: (
            BASE_PATH / "build/loopback_fastrx/20260729_181030",
            "adc01_*mbd_logic*_rx*_tap*.h5",
        ),
    }
    RATES_MBD = tuple(range(80, 1601, 40))
    LOGIC_OFFSETS = tuple(range(-3, 4))
    EXPECTED_POINTS = {
        (float(rate_mbd), float(logic_offset)) for rate_mbd in RATES_MBD for logic_offset in LOGIC_OFFSETS
    }
    EXPECTED_POINT_COUNT = len(EXPECTED_POINTS)
    EXPECTED_VIN_DIFF_V = 0.05
    EXPECTED_VIN_CM_V = 0.8

    if (
        not ADC_INDICES
        or len(set(ADC_INDICES)) != len(ADC_INDICES)
        or any(not isinstance(adc_index, int) or not 0 <= adc_index < 16 for adc_index in ADC_INDICES)
    ):
        raise ValueError("ADC_INDICES must contain unique ADC indices in 0..15")
    artifacts = []
    for adc_index in ADC_INDICES:
        adc_name = f"ADC{adc_index:02d}"
        if adc_index not in LOGIC_OFFSET_RUNS:
            raise ValueError(f"{adc_name} has no registered LOGIC-offset campaign")
        run_dir, pattern = LOGIC_OFFSET_RUNS[adc_index]
        measurement_paths = sorted(run_dir.glob(pattern))
        if len(measurement_paths) != EXPECTED_POINT_COUNT:
            raise ValueError(
                f"{adc_name} seven-offset pipeline requires {EXPECTED_POINT_COUNT} HDF5 inputs, "
                f"found {len(measurement_paths)}"
            )
        measurements = []
        for path in measurement_paths:
            measurement = read_measurement(path)
            if not isinstance(measurement, MeasAdcExt):
                raise TypeError(f"{path} contains {type(measurement).__name__}, expected MeasAdcExt")
            measurements.append(measurement)
        observed_points = {
            (
                float(measurement.param.tb.symbol_rate) / 1e6,
                float(measurement.param.tb.seq_logic_phase_delay_symbols)
                - float(measurement.param.tb.seq_comp_phase_delay_symbols),
            )
            for measurement in measurements
        }
        if observed_points != EXPECTED_POINTS:
            raise ValueError(f"{adc_name} seven-offset pipeline has missing or unexpected rate/offset points")
        if any(
            measurement.param.observed_adc != adc_index
            or not isinstance(measurement.param.tb.vin_diff, h.Vdc.Params)
            or float(measurement.param.tb.vin_diff.dc) != EXPECTED_VIN_DIFF_V
            or float(measurement.param.tb.vin_cm.dc) != EXPECTED_VIN_CM_V
            for measurement in measurements
        ):
            raise ValueError(
                f"{adc_name} seven-offset pipeline requires a {EXPECTED_VIN_DIFF_V * 1e3:g} mV DC input "
                f"at {EXPECTED_VIN_CM_V * 1e3:g} mV common mode"
            )

        noise = analyze_adc_noise_sweep(measurements)
        artifacts.extend(
            plot_adc_noise_sweep(
                measurements,
                noise,
                output_path=output_dir / f"{adc_name.lower()}_noise_vs_conversion_rate_and_logic_offset",
            )
        )
    return tuple(artifacts)


def comp_system_common_mode(output_dir: Path) -> tuple[Path, ...]:
    """Analyze and plot separate ADC00–ADC03 comparator common-mode campaigns."""

    RUN_DIRS = (BASE_PATH / "build/scan_comp/20260805_171216",)
    ADC_INDICES = (0, 1, 2, 3)
    EXPECTED_VIN_CM_V = (0.7, 0.8, 0.9, 1.0, 1.1, 1.2)
    EXPECTED_COMMON_MODES = set(EXPECTED_VIN_CM_V)

    measurement_paths = sorted(path for run_dir in RUN_DIRS for path in run_dir.glob("*.h5"))
    if not measurement_paths:
        missing = RUN_DIRS[0] if RUN_DIRS else BASE_PATH / "build/scan_comp"
        raise FileNotFoundError(2, "accepted comparator common-mode inputs not found", missing)
    measurements = []
    for path in measurement_paths:
        measurement = read_measurement(path)
        if not isinstance(measurement, MeasCompExt):
            raise TypeError(f"{path} contains {type(measurement).__name__}, expected MeasCompExt")
        if measurement.param.campaign != "comp_common_mode":
            raise ValueError(f"{path} is not a comp_common_mode point")
        if int(measurement.info.readbacks.get("fastrx_lost_count", 0)) or int(
            measurement.info.readbacks.get("spi_mismatches", 0)
        ):
            raise ValueError(f"{path} contains a corrupt physical capture")
        measurements.append(measurement)
    if {measurement.param.observed_adc for measurement in measurements} != set(ADC_INDICES):
        raise ValueError("comparator common-mode runner requires ADC00 through ADC03")

    artifacts = []
    for adc_index in ADC_INDICES:
        adc_measurements = [measurement for measurement in measurements if measurement.param.observed_adc == adc_index]
        grouped: dict[float, list[MeasCompExt]] = {}
        for measurement in adc_measurements:
            grouped.setdefault(float(measurement.param.tb.vin_cm.dc), []).append(measurement)
        board_ids = {measurement.param.board_id for measurement in adc_measurements}
        configured_vdd_a = {float(measurement.param.tb.vdd_a.dc) for measurement in adc_measurements}
        if len(board_ids) != 1 or None in board_ids or len(configured_vdd_a) != 1:
            raise ValueError(f"ADC{adc_index:02d} common-mode campaign requires one board and VDD_A")
        if set(grouped) != EXPECTED_COMMON_MODES:
            raise ValueError(f"ADC{adc_index:02d} common-mode campaign is missing a Vin_cm curve")
        groups = [grouped[value] for value in sorted(grouped)]
        analyses = [analyze_comp_offset_noise(group) for group in groups]
        analyses = list(classify_comp_common_mode_validity(groups, analyses))
        artifacts.extend(
            plot_comp_common_mode_campaign(
                groups,
                analyses,
                output_path=output_dir / f"adc{adc_index:02d}_comparator_common_mode",
            )
        )
    return tuple(artifacts)


def comp_system_sampling_noise(output_dir: Path) -> tuple[Path, ...]:
    """Analyze and plot separate ADC00–ADC03 track/hold comparator campaigns."""

    RUN_DIRS = (
        BASE_PATH / "build/scan_comp/20260805_183915",
        BASE_PATH / "build/scan_comp/20260805_192902",
    )
    ADC_INDICES = (0, 1, 2, 3)
    EXPECTED_VIN_CM_V = 0.7
    COUPLING_PERCENTAGES = (0.0, 25.0, 50.0, 75.0, 100.0)
    SAMPLING_MODES = ("track", "hold")
    EXPECTED_GROUPS = {(coupling_percent, mode) for coupling_percent in COUPLING_PERCENTAGES for mode in SAMPLING_MODES}

    run_measurement_paths = [sorted(run_dir.glob("*.h5")) for run_dir in RUN_DIRS]
    if not any(run_measurement_paths):
        missing = RUN_DIRS[0] if RUN_DIRS else BASE_PATH / "build/scan_comp"
        raise FileNotFoundError(2, "accepted comparator sampling-noise inputs not found", missing)
    measurements_by_point: dict[tuple[int, float, str, float, float], MeasCompExt] = {}
    for measurement_paths in run_measurement_paths:
        measurements_in_run: dict[tuple[int, float, str, float, float], MeasCompExt] = {}
        for path in measurement_paths:
            measurement = read_measurement(path)
            if not isinstance(measurement, MeasCompExt):
                raise TypeError(f"{path} contains {type(measurement).__name__}, expected MeasCompExt")
            if measurement.param.campaign != "comp_sampling_noise":
                raise ValueError(f"{path} is not a comp_sampling_noise point")
            if int(measurement.info.readbacks.get("fastrx_lost_count", 0)) or int(
                measurement.info.readbacks.get("spi_mismatches", 0)
            ):
                raise ValueError(f"{path} contains a corrupt physical capture")
            coupling_percent = measurement.param.requested_dac_rail_percent
            if coupling_percent is None:
                raise ValueError(f"{path} is missing its P-side VDAC coupling")
            point_key = (
                int(measurement.param.observed_adc),
                float(coupling_percent),
                measurement.param.sampling_mode,
                float(measurement.param.tb.vin_cm.dc),
                float(measurement.param.tb.vin_diff.dc),
            )
            if point_key in measurements_in_run:
                raise ValueError(f"{path} duplicates a sampling-noise point within one accepted run")
            measurements_in_run[point_key] = measurement
        measurements_by_point.update(measurements_in_run)
    measurements = list(measurements_by_point.values())
    if {measurement.param.observed_adc for measurement in measurements} != set(ADC_INDICES):
        raise ValueError("comparator sampling-noise runner requires ADC00 through ADC03")

    artifacts = []
    for adc_index in ADC_INDICES:
        adc_measurements = [measurement for measurement in measurements if measurement.param.observed_adc == adc_index]
        if {float(measurement.param.tb.vin_cm.dc) for measurement in adc_measurements} != {EXPECTED_VIN_CM_V}:
            raise ValueError(f"ADC{adc_index:02d} sampling-noise campaign requires Vin_cm = {EXPECTED_VIN_CM_V} V")
        grouped: dict[tuple[float, str], list[MeasCompExt]] = {}
        for measurement in adc_measurements:
            coupling_percent = measurement.param.requested_dac_rail_percent
            if coupling_percent is None:
                raise ValueError("sampling-noise point is missing its P-side VDAC coupling")
            grouped.setdefault((float(coupling_percent), measurement.param.sampling_mode), []).append(measurement)
        if set(grouped) != EXPECTED_GROUPS:
            raise ValueError(
                f"ADC{adc_index:02d} sampling-noise campaign requires "
                f"{len(COUPLING_PERCENTAGES)} matched track/hold couplings"
            )
        groups = [grouped[key] for key in sorted(grouped)]
        analyses = [analyze_comp_offset_noise(group) for group in groups]
        if any(analysis.validity != "valid" for analysis in analyses):
            raise ValueError(f"ADC{adc_index:02d} sampling-noise campaign contains an invalid comparator fit")
        artifacts.extend(
            plot_comp_sampling_campaign(
                groups,
                analyses,
                output_path=output_dir / f"adc{adc_index:02d}_comparator_sampling_noise",
            )
        )
    return tuple(artifacts)


def comp_candidate_sweep(output_dir: Path) -> tuple[Path, ...]:
    """Analyze the complete generated-comparator noise/power/timing campaign."""

    RUN_DIR = BASE_PATH / "build/comp/frida65_candidate_scurve_power"
    EXPECTED_CANDIDATES = 297
    measurement_paths = sorted((RUN_DIR / "candidates").glob("*/result.h5"))
    if len(measurement_paths) != EXPECTED_CANDIDATES:
        raise ValueError(
            f"comparator candidate runner requires {EXPECTED_CANDIDATES} H5 results, found {len(measurement_paths)}"
        )
    measurements = []
    observed_ids = set()
    for path in measurement_paths:
        measurement = read_measurement(path)
        if not isinstance(measurement, MeasCompInt):
            raise TypeError(f"{path} contains {type(measurement).__name__}, expected MeasCompInt")
        if measurement.info.backend != "spice" or measurement.info.readbacks.get("transient_noise") is not True:
            raise ValueError(f"{path} is not a transient-noise SPICE comparator result")
        candidate_id = str(measurement.info.readbacks.get("candidate_id", ""))
        if not candidate_id:
            raise ValueError(f"{path} does not identify its comparator candidate")
        if candidate_id in observed_ids:
            raise ValueError(f"duplicate comparator result for {candidate_id!r}")
        observed_ids.add(candidate_id)
        params = measurement.param
        if (
            tuple(float(value) for value in params.vin_cm_values_v) != (0.8,)
            or not np.allclose(
                tuple(float(value) for value in params.vin_diff_values_v),
                tuple(step * 100e-6 for step in range(-30, 31)),
            )
            or params.conversions != 100
            or not np.isclose(float(params.reset_time_s), 10e-9)
            or not np.isclose(float(params.evaluation_time_s), 30e-9)
        ):
            raise ValueError(f"{path} does not use the reviewed comparator S-curve testbench")
        measurements.append(measurement)
    analysis = analyze_comp_candidate_sweep(measurements)
    profiles = np.asarray(analysis.size_profile)
    valid_resolved = (
        (np.asarray(analysis.validity) == "valid")
        & np.isfinite(analysis.noise_sigma_v)
        & (analysis.noise_sigma_v > 0.0)
        & np.isfinite(analysis.average_power_w)
        & (analysis.average_power_w > 0.0)
        & np.isfinite(analysis.maximum_settling_s)
        & (analysis.maximum_settling_s > 0.0)
        & (analysis.unresolved_fraction == 0.0)
    )
    fabricated = profiles == "fabricated"
    if np.count_nonzero(fabricated) != 1 or not np.all(valid_resolved[fabricated]):
        raise ValueError("comparator candidate campaign requires one valid, resolved fabricated baseline")
    if not np.any(valid_resolved & np.isin(profiles, ("half", "double"))):
        raise ValueError("comparator candidate campaign has no valid, resolved generated designs")
    artifacts = list(
        plot_comp_candidate_sweep(
            measurements,
            analysis,
            output_path=output_dir / "comp_candidate_noise_power_settling",
        )
    )
    artifacts.extend(
        plot_comp_noise_power_tradeoff(
            analysis,
            output_path=output_dir / "comp_candidate_noise_power_tradeoff",
        )
    )
    csv_path = output_dir / "comp_candidate_noise_power_settling.csv"
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    with csv_path.open("w", newline="") as output:
        writer = csv.writer(output)
        writer.writerow(
            (
                "area_order",
                "candidate_id",
                "candidate_label",
                "size_profile",
                "topology_index",
                "total_width_units",
                "total_active_area_units",
                "total_active_area_um2",
                "device_count",
                "comp_stages",
                "preamp_diff_xtors",
                "preamp_bias",
                "latch_inner_on_xtors",
                "latch_outer_on_xtors",
                "latch_inner_init_xtors",
                "latch_outer_init_xtors",
                "diffpair_w",
                "diffpair_l",
                "tail_w",
                "tail_l",
                "rst_w",
                "rst_l",
                "latch_on_w",
                "latch_on_l",
                "latch_init_w",
                "latch_init_l",
                "srlatch_n_w",
                "srlatch_p_w",
                "validity",
                "offset_v",
                "noise_sigma_v",
                "average_power_w",
                "energy_per_decision_j",
                "maximum_clock_to_decision_s",
                "maximum_settling_s",
                "unresolved_fraction",
            )
        )
        measurement_by_id = {
            str(measurement.info.readbacks["candidate_id"]): measurement for measurement in measurements
        }
        for index, candidate_id in enumerate(analysis.candidate_id):
            comp = measurement_by_id[candidate_id].param.comp
            writer.writerow(
                (
                    index,
                    candidate_id,
                    analysis.candidate_label[index],
                    analysis.size_profile[index],
                    analysis.topology_index[index],
                    analysis.total_width_units[index],
                    analysis.total_active_area_units[index],
                    analysis.total_active_area_um2[index],
                    analysis.device_count[index],
                    comp.comp_stages.name,
                    comp.preamp_diff_xtors.name,
                    comp.preamp_bias.name,
                    comp.latch_inner_on_xtors.name,
                    comp.latch_outer_on_xtors.name,
                    comp.latch_inner_init_xtors.name,
                    comp.latch_outer_init_xtors.name,
                    comp.diffpair_w,
                    comp.diffpair_l,
                    comp.tail_w,
                    comp.tail_l,
                    comp.rst_w,
                    comp.rst_l,
                    comp.latch_on_w,
                    comp.latch_on_l,
                    comp.latch_init_w,
                    comp.latch_init_l,
                    comp.srlatch_n_w,
                    comp.srlatch_p_w,
                    analysis.validity[index],
                    analysis.offset_v[index],
                    analysis.noise_sigma_v[index],
                    analysis.average_power_w[index],
                    analysis.energy_per_decision_j[index],
                    analysis.maximum_clock_to_decision_s[index],
                    analysis.maximum_settling_s[index],
                    analysis.unresolved_fraction[index],
                )
            )
    artifacts.append(csv_path)
    return tuple(artifacts)


def cdac_system_cap_mismatch(output_dir: Path) -> tuple[Path, ...]:
    """Extract and plot ADC00–ADC03 capacitor mismatch from A-to-B transitions."""

    adc_indices = (0, 1, 2, 3)
    board_id = "00"
    run_dirs = tuple(
        BASE_PATH / "build/scan_cdac" / name for name in ("20260804_171234", "20260804_193030", "20260804_193631")
    )
    paths_by_run = tuple(tuple(sorted(run_dir.glob("*.h5"))) for run_dir in run_dirs)
    if not any(paths_by_run):
        raise FileNotFoundError(2, "accepted A-to-B CDAC inputs not found", run_dirs[0])
    comparator_calibrations = load_board_map()["boards"][board_id].get("comparator_calibration", {})
    adc_groups, analyses = analyze_cdac_cap_mismatch_campaign(
        tuple(tuple(read_measurement(path) for path in paths) for paths in paths_by_run),
        adc_indices=adc_indices,
        board_id=board_id,
        comparator_offset_v_by_adc={
            adc_index: float(comparator_calibrations[adc_index]["offset_v"]) for adc_index in adc_indices
        },
    )
    artifacts = []
    for adc_measurements, analysis in zip(adc_groups, analyses, strict=True):
        artifacts.extend(
            plot_cdac_cap_mismatch(
                adc_measurements,
                analysis,
                output_path=output_dir / f"adc{analysis.adc_index:02d}_cdac_cap_mismatch",
            )
        )
    artifacts.extend(
        plot_cdac_cap_mismatch_comparison(
            adc_groups,
            analyses,
            output_path=output_dir / "adc00_adc03_cdac_cap_mismatch_comparison",
        )
    )
    return tuple(artifacts)


TARGETS: dict[str, Callable[[Path], tuple[Path, ...]]] = {
    target.__name__: target
    for target in (
        adc_transfer_curve,
        adc_ramp_nonlinearity,
        adc_calibration,
        adc00_fixed_input_noise,
        adc_noise_vs_rate,
        adc_code_distributions,
        adc_power_vs_rate,
        adc_rate_characterization,
        adc_noise_vs_comp_time,
        comp_system_common_mode,
        comp_system_sampling_noise,
        comp_candidate_sweep,
        cdac_system_cap_mismatch,
    )
}
AGGREGATE_TARGETS = {"adc_rate_characterization"}


def main() -> None:
    """Run one named analysis pipeline, or every target when none is named."""

    # TODO: Change analysis roots to build/analysis_<domain>/<short-datetime>.
    ANALYSIS_OUTPUT_BASE = BASE_PATH / "build/analysis"

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "target",
        nargs="?",
        choices=sorted(TARGETS),
        help="analysis-pipeline function to run; omit to run all targets",
    )
    args = parser.parse_args()
    run_all = args.target is None
    target_names = tuple(name for name in TARGETS if name not in AGGREGATE_TARGETS) if run_all else (args.target,)
    timestamp = datetime.now().astimezone().strftime("%Y%m%d_%H%M")
    output_dirs: dict[str, Path] = {}
    for target_name in target_names:
        # TODO: Route cdac_* targets to analysis_cdac instead of analysis_adc.
        domain = "comp" if target_name.startswith("comp_") else "adc"
        output_dir = output_dirs.get(domain)
        if output_dir is None:
            output_dir = ANALYSIS_OUTPUT_BASE / domain / timestamp
            output_dir.mkdir(parents=True, exist_ok=False)
            output_dirs[domain] = output_dir
            print(f"Analysis output: {output_dir}")
        start_time = perf_counter()
        try:
            artifacts = TARGETS[target_name](output_dir)
        except FileNotFoundError as error:
            if not run_all:
                raise
            runtime_s = perf_counter() - start_time
            print(f"Skipped {target_name}: missing {error.filename} after {runtime_s:.2f} s")
            continue
        runtime_s = perf_counter() - start_time
        print(f"Completed {target_name}: {len(artifacts)} artifacts in {runtime_s:.2f} s")


if __name__ == "__main__":
    main()
