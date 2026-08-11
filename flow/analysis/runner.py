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
import json
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
    analyze_adc_ramp,
    analyze_adc_transfer,
    combine_adc_noise_comparison,
)
from flow.analysis.cdac import analyze_cdac_cap_mismatch
from flow.analysis.comp import (
    analyze_comp_candidate_sweep,
    analyze_comp_offset_noise,
    classify_comp_common_mode_validity,
)
from flow.analysis.io import read_measurement
from flow.analysis.plots import (
    animate_adc_decision_path_density,
    plot_adc_code_distribution,
    plot_adc_decision_path_density,
    plot_adc_decision_paths,
    plot_adc_dynamic,
    plot_adc_noise_distribution_sweep,
    plot_adc_noise_sweep,
    plot_adc_noise_violin_sweep,
    plot_adc_nonlinearity,
    plot_adc_power_sweep,
    plot_adc_ramp_histogram,
    plot_adc_ramp_transfer,
    plot_adc_transfer,
    plot_cdac_cap_mismatch,
    plot_cdac_cap_mismatch_comparison,
    plot_comp_campaign,
    plot_comp_candidate_sweep,
    plot_comp_noise_power_tradeoff,
    plot_measurement_waveforms,
)
from flow.analysis.types import MeasAdcExt, MeasAdcInt, MeasCdacExt, MeasCompExt, MeasCompInt
from flow.scans.params import load_board_map

BASE_PATH = Path(__file__).resolve().parents[2]


def adc_transfer_curve(output_dir: Path) -> tuple[Path, ...]:
    """Plot transfer curves for the configured ADC measurements."""

    INPUT_H5_BY_ADC = {
        0: BASE_PATH / "build/adc_pex_monotonic/adc_00.h5",
    }

    if not INPUT_H5_BY_ADC or any(
        not isinstance(adc_index, int) or not 0 <= adc_index < 16 for adc_index in INPUT_H5_BY_ADC
    ):
        raise ValueError("INPUT_H5_BY_ADC must map ADC indices in 0..15 to measurement files")
    artifacts = []
    for adc_index, input_h5 in INPUT_H5_BY_ADC.items():
        if not input_h5.is_file():
            raise FileNotFoundError(2, "measurement input not found", input_h5)
        measurement = read_measurement(input_h5)
        if not isinstance(measurement, (MeasAdcExt, MeasAdcInt)):
            raise TypeError(f"{input_h5} contains {type(measurement).__name__}, expected MeasAdcExt or MeasAdcInt")
        analysis = analyze_adc_transfer([measurement])
        artifacts.extend(
            plot_adc_transfer(
                [measurement],
                analysis,
                output_path=output_dir / f"adc{adc_index:02d}_transfer_curve",
            )
        )
    return tuple(artifacts)


def adc_ramp_nonlinearity(output_dir: Path) -> tuple[Path, ...]:
    """Combine accepted ADC ramp and CDAC captures entirely in memory.

    Replace the explicit placeholders after the hardware campaigns. Each CDAC
    tuple must list every accepted HDF5 point used by its A-to-B fit. The ramp
    analysis infers AWG frequency and acquisition phase from repeated resets,
    then decodes the stored decisions with nominal and measured CDAC weights.
    No fitted weights or derived measurements are written back to HDF5.
    """

    RAMP_H5_BY_ADC = {
        0: BASE_PATH / "build/scan_adc/PLACEHOLDER_ADC00_RAMP.h5",
        1: BASE_PATH / "build/scan_adc/PLACEHOLDER_ADC01_RAMP.h5",
        2: BASE_PATH / "build/scan_adc/PLACEHOLDER_ADC02_RAMP.h5",
        3: BASE_PATH / "build/scan_adc/PLACEHOLDER_ADC03_RAMP.h5",
    }
    CDAC_H5_BY_ADC = {
        0: (BASE_PATH / "build/scan_cdac/PLACEHOLDER_ADC00_CDAC_0000.h5",),
        1: (BASE_PATH / "build/scan_cdac/PLACEHOLDER_ADC01_CDAC_0000.h5",),
        2: (BASE_PATH / "build/scan_cdac/PLACEHOLDER_ADC02_CDAC_0000.h5",),
        3: (BASE_PATH / "build/scan_cdac/PLACEHOLDER_ADC03_CDAC_0000.h5",),
    }

    if set(RAMP_H5_BY_ADC) != set(CDAC_H5_BY_ADC):
        raise ValueError("ramp and CDAC HDF5 mappings must select the same ADCs")
    board_map = load_board_map()
    artifacts = []
    for adc_index, ramp_h5 in RAMP_H5_BY_ADC.items():
        if not ramp_h5.is_file():
            raise FileNotFoundError(2, "replace the ADC ramp HDF5 placeholder", ramp_h5)
        ramp_measurement = read_measurement(ramp_h5)
        if not isinstance(ramp_measurement, MeasAdcExt):
            raise TypeError(f"{ramp_h5} contains {type(ramp_measurement).__name__}, expected MeasAdcExt")
        if ramp_measurement.param.campaign != "adc_ramp" or ramp_measurement.param.observed_adc != adc_index:
            raise ValueError(f"{ramp_h5} is not the configured ADC{adc_index:02d} ramp capture")

        cdac_paths = CDAC_H5_BY_ADC[adc_index]
        if not cdac_paths:
            raise ValueError(f"ADC{adc_index:02d} requires accepted CDAC HDF5 inputs")
        cdac_measurements = []
        for cdac_h5 in cdac_paths:
            if not cdac_h5.is_file():
                raise FileNotFoundError(2, "replace the CDAC HDF5 placeholder", cdac_h5)
            cdac_measurement = read_measurement(cdac_h5)
            if not isinstance(cdac_measurement, MeasCdacExt):
                raise TypeError(f"{cdac_h5} contains {type(cdac_measurement).__name__}, expected MeasCdacExt")
            if cdac_measurement.param.campaign != "cdac_ab" or cdac_measurement.param.observed_adc != adc_index:
                raise ValueError(f"{cdac_h5} is not an ADC{adc_index:02d} A-to-B CDAC capture")
            if cdac_measurement.param.board_id != ramp_measurement.param.board_id:
                raise ValueError("CDAC and ramp HDF5 inputs must come from the same board")
            cdac_measurements.append(cdac_measurement)
        board_id = ramp_measurement.param.board_id
        if board_id is None:
            raise ValueError("physical ADC ramp capture must identify its board")
        comparator_offset_v = float(board_map["boards"][board_id]["comparator_calibration"][adc_index]["offset_v"])
        cdac_analysis = analyze_cdac_cap_mismatch(
            cdac_measurements,
            comparator_offset_v=comparator_offset_v,
        )
        analysis = analyze_adc_ramp(ramp_measurement, cdac_analysis=cdac_analysis)
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
            plot_adc_nonlinearity(
                analysis,
                output_path=output_dir / f"adc{adc_index:02d}_ramp_nonlinearity",
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
                or not isinstance(measurement.param.vin_diff, h.Vdc.Params)
                or not np.isclose(float(measurement.param.vin_diff.dc), expected_input_v)
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
        order = np.argsort(physical_noise.sample_rate_hz)
        physical_rates = physical_noise.sample_rate_hz[order]
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
        )
        artifacts.extend(
            plot_adc_noise_sweep(
                comparison_measurements,
                comparison,
                output_path=output_dir / f"adc{adc_index:02d}_noise_vs_conversion_rate",
                series_labels=series_labels,
                title=f"ADC{adc_index:02d} input-referred noise vs conversion rate",
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
                or not isinstance(measurement.param.vin_diff, h.Vdc.Params)
                or not np.isclose(float(measurement.param.vin_diff.dc), expected_input_v)
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
                    title=f"ADC{adc_index:02d} {input_mv} mV fixed-input output-code distributions",
                )
            )

    for input_mv in PHYSICAL_NOISE_RUN_DIRS:
        for adc_index in ADC_INDICES:
            adc_measurements = physical_measurements[input_mv][adc_index]
            artifacts.extend(
                plot_adc_noise_violin_sweep(
                    adc_measurements,
                    analyze_adc_noise_sweep(adc_measurements),
                    output_path=output_dir / f"adc{adc_index:02d}_{input_mv}mv_dc_output_code_violins",
                    title=f"ADC{adc_index:02d} {input_mv} mV fixed-input output-code violin distributions",
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
                artifacts.extend(animate_adc_decision_path_density(matches[0], analysis, output_path=output_path))
    return tuple(artifacts)


def adc_power_vs_rate(output_dir: Path) -> tuple[Path, ...]:
    """Plot power sweeps and detailed 80 MBd sine captures for configured ADCs."""

    ADC_INDICES = (0, 1)
    SINE_RUN_DIR = BASE_PATH / "build/scan_adc/20260730_215145_complete"
    RATES_MBD = tuple(range(80, 1601, 40))
    DETAIL_RATE_MBD = 80

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

    sine_measurements = [
        measurement for adc_index in ADC_INDICES for measurement in sine_measurements_by_adc[adc_index]
    ]
    artifacts = []
    artifacts.extend(
        plot_adc_power_sweep(
            sine_measurements,
            analyze_adc_power_sweep(sine_measurements),
            output_path=output_dir / "adc_power_vs_conversion_rate",
        )
    )
    for adc_index in ADC_INDICES:
        detail_measurement = sine_measurements_by_adc[adc_index][RATES_MBD.index(DETAIL_RATE_MBD)]
        artifacts.extend(
            plot_measurement_waveforms(
                detail_measurement,
                record_index=0,
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
                float(measurement.param.symbol_rate) / 1e6,
                float(measurement.param.seq_logic_phase_delay_symbols)
                - float(measurement.param.seq_comp_phase_delay_symbols),
            )
            for measurement in measurements
        }
        if observed_points != EXPECTED_POINTS:
            raise ValueError(f"{adc_name} seven-offset pipeline has missing or unexpected rate/offset points")
        if any(
            measurement.param.observed_adc != adc_index
            or not isinstance(measurement.param.vin_diff, h.Vdc.Params)
            or float(measurement.param.vin_diff.dc) != EXPECTED_VIN_DIFF_V
            or float(measurement.param.vin_cm.dc) != EXPECTED_VIN_CM_V
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
            grouped.setdefault(float(measurement.param.vin_cm.dc), []).append(measurement)
        board_ids = {measurement.param.board_id for measurement in adc_measurements}
        configured_vdd_a = {float(measurement.param.vdd_a.dc) for measurement in adc_measurements}
        if len(board_ids) != 1 or None in board_ids or len(configured_vdd_a) != 1:
            raise ValueError(f"ADC{adc_index:02d} common-mode campaign requires one board and VDD_A")
        if set(grouped) != EXPECTED_COMMON_MODES:
            raise ValueError(f"ADC{adc_index:02d} common-mode campaign is missing a Vin_cm curve")
        groups = [grouped[value] for value in sorted(grouped)]
        analyses = [analyze_comp_offset_noise(group) for group in groups]
        analyses = list(classify_comp_common_mode_validity(groups, analyses))
        artifacts.extend(
            plot_comp_campaign(
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
                float(measurement.param.vin_cm.dc),
                float(measurement.param.vin_diff.dc),
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
        if {float(measurement.param.vin_cm.dc) for measurement in adc_measurements} != {EXPECTED_VIN_CM_V}:
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
        artifacts.extend(
            plot_comp_campaign(
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
    manifest_path = RUN_DIR / "manifest.json"
    if not manifest_path.is_file():
        raise FileNotFoundError(2, "comparator candidate manifest not found", manifest_path)
    manifest = json.loads(manifest_path.read_text())
    if manifest.get("campaign") != "frida65_candidate_scurve_power":
        raise ValueError("comparator candidate manifest has the wrong campaign name")
    manifest_candidates = manifest.get("candidates")
    if not isinstance(manifest_candidates, list) or len(manifest_candidates) != EXPECTED_CANDIDATES:
        raise ValueError(f"comparator candidate manifest must contain {EXPECTED_CANDIDATES} designs")
    expected_ids = {str(candidate["candidate_id"]) for candidate in manifest_candidates}
    if len(expected_ids) != EXPECTED_CANDIDATES:
        raise ValueError("comparator candidate manifest contains duplicate IDs")

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
        if candidate_id in observed_ids:
            raise ValueError(f"duplicate comparator result for {candidate_id!r}")
        observed_ids.add(candidate_id)
        params = measurement.param
        if (
            tuple(float(value) for value in params.vin_cm_values_v) != (0.8,)
            or not np.isclose(float(params.sweep_min_v), -3e-3)
            or not np.isclose(float(params.sweep_max_v), 3e-3)
            or not np.isclose(float(params.sweep_step_v), 100e-6)
            or params.conversions != 100
            or not np.isclose(float(params.reset_time_s), 10e-9)
            or not np.isclose(float(params.evaluation_time_s), 30e-9)
        ):
            raise ValueError(f"{path} does not use the reviewed comparator S-curve testbench")
        measurements.append(measurement)
    if observed_ids != expected_ids:
        missing = sorted(expected_ids.difference(observed_ids))
        unexpected = sorted(observed_ids.difference(expected_ids))
        raise ValueError(
            f"comparator candidate results do not match manifest; missing={missing}, unexpected={unexpected}"
        )

    analysis = analyze_comp_candidate_sweep(measurements)
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

    RUN_DIRS = (
        BASE_PATH / "build/scan_cdac/20260804_171234",
        BASE_PATH / "build/scan_cdac/20260804_193030",
        BASE_PATH / "build/scan_cdac/20260804_193631",
    )
    ADC_INDICES = (0, 1, 2, 3)
    CDAC_SIDES = ("p", "n")
    CDAC_ELEMENTS = tuple(range(16))
    CDAC_DIRECTIONS = ("1to0", "0to1")
    DIFFCAP_MODES = (0, 1)
    EXPECTED_CURVES = {
        (side, element, direction, diffcaps)
        for side in CDAC_SIDES
        for element in CDAC_ELEMENTS
        for direction in CDAC_DIRECTIONS
        for diffcaps in DIFFCAP_MODES
    }
    board_map = load_board_map()

    run_measurement_paths = [sorted(run_dir.glob("*.h5")) for run_dir in RUN_DIRS]
    if not any(run_measurement_paths):
        missing = RUN_DIRS[0] if RUN_DIRS else BASE_PATH / "build/scan_cdac"
        raise FileNotFoundError(2, "accepted A-to-B CDAC inputs not found", missing)
    selected_curve_measurements: dict[tuple[int, str, int, str, int], list[MeasCdacExt]] = {}
    for measurement_paths in run_measurement_paths:
        grouped_in_run: dict[tuple[int, str, int, str, int], list[MeasCdacExt]] = {}
        for path in measurement_paths:
            measurement = read_measurement(path)
            if not isinstance(measurement, MeasCdacExt):
                raise TypeError(f"{path} contains {type(measurement).__name__}, expected MeasCdacExt")
            if measurement.param.campaign != "cdac_ab":
                raise ValueError(f"{path} is not a cdac_ab point")
            if int(measurement.info.readbacks.get("fastrx_lost_count", 0)) or int(
                measurement.info.readbacks.get("spi_mismatches", 0)
            ):
                raise ValueError(f"{path} contains a corrupt physical capture")
            params = measurement.param
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
                params.dac_diffcaps,
            )
            grouped_in_run.setdefault(curve_key, []).append(measurement)
        for key, curve_measurements in grouped_in_run.items():
            physical_measurements = [
                measurement for measurement in curve_measurements if measurement.info.backend == "physical"
            ]
            if physical_measurements:
                session_ids = {
                    measurement.info.readbacks.get("acquisition_session_id") for measurement in physical_measurements
                }
                completed = [
                    measurement
                    for measurement in physical_measurements
                    if measurement.info.readbacks.get("curve_complete") is True
                ]
                latest_timestamp = max(measurement.info.timestamp_utc for measurement in physical_measurements)
                if (
                    len(physical_measurements) != len(curve_measurements)
                    or None in session_ids
                    or len(session_ids) != 1
                    or len(completed) != 1
                    or completed[0].info.timestamp_utc != latest_timestamp
                ):
                    raise ValueError(f"accepted CDAC run contains an incomplete or mixed-session curve {key}")
        # Directory order is deliberate: a later directory atomically replaces
        # every point of a selectively reacquired curve from an earlier directory.
        selected_curve_measurements.update(grouped_in_run)
    measurements = [
        measurement
        for curve_key in sorted(selected_curve_measurements)
        for measurement in selected_curve_measurements[curve_key]
    ]
    if {measurement.param.observed_adc for measurement in measurements} != set(ADC_INDICES):
        raise ValueError("A-to-B CDAC runner requires ADC00 through ADC03")

    artifacts = []
    adc_groups = []
    analyses = []
    for adc_index in ADC_INDICES:
        adc_measurements = [measurement for measurement in measurements if measurement.param.observed_adc == adc_index]
        observed_curves = {
            (
                measurement.param.cdac_side,
                measurement.param.cdac_element,
                measurement.param.cdac_direction,
                measurement.param.dac_diffcaps,
            )
            for measurement in adc_measurements
        }
        if observed_curves != EXPECTED_CURVES:
            raise ValueError(f"ADC{adc_index:02d} A-to-B CDAC campaign is incomplete")
        board_ids = {measurement.param.board_id for measurement in adc_measurements}
        if len(board_ids) != 1 or None in board_ids:
            raise ValueError(f"ADC{adc_index:02d} CDAC measurements require exactly one board_id")
        board_id = next(board_id for board_id in board_ids if board_id is not None)
        calibrations = board_map["boards"][board_id].get("comparator_calibration", {})
        calibration = calibrations.get(adc_index, calibrations.get(str(adc_index)))
        if calibration is None:
            raise ValueError(f"ADC{adc_index:02d} has no accepted comparator_calibration")
        analysis = analyze_cdac_cap_mismatch(
            adc_measurements,
            comparator_offset_v=float(calibration["offset_v"]),
        )
        adc_groups.append(adc_measurements)
        analyses.append(analysis)
        artifacts.extend(
            plot_cdac_cap_mismatch(
                adc_measurements,
                analysis,
                output_path=output_dir / f"adc{adc_index:02d}_cdac_cap_mismatch",
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
