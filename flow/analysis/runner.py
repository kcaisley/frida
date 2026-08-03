"""Explicit, manually invoked measurement -> analysis -> plot pipelines.

Each function names its input files directly. Add a pipeline only after its
capture has been inspected and the corresponding analysis has been validated.
There is intentionally no automatic discovery of run directories or analysis
pipelines; each pipeline names and validates its input campaign.

Run one named pipeline from the repository root with:

    uv run python -m flow.analysis.runner adc00_adc01_noise_power_and_code_diagnostics

Omit the target name to run every registered pipeline. One invocation writes
all derived artifacts beneath one timestamped ``build/analysis/adc`` directory.
"""

from __future__ import annotations

import argparse
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from time import perf_counter

import hdl21 as h
import numpy as np

from flow.analysis.adc import (
    analyze_adc_decision_paths,
    analyze_adc_dynamic,
    analyze_adc_dynamic_sweep,
    analyze_adc_noise,
    analyze_adc_noise_sweep,
    analyze_adc_power_sweep,
    analyze_adc_transfer,
)
from flow.analysis.io import read_measurement
from flow.analysis.plots import (
    animate_adc_decision_path_density,
    plot_adc_decision_path_density,
    plot_adc_decision_paths,
    plot_adc_dynamic,
    plot_adc_noise,
    plot_adc_noise_distribution_sweep,
    plot_adc_noise_sweep,
    plot_adc_noise_violin_sweep,
    plot_adc_power_sweep,
    plot_adc_transfer,
    plot_measurement_waveforms,
)
from flow.analysis.types import AnalysisAdcNoiseSweep, MeasAdc, MeasAdcExt, MeasAdcInt

BASE_PATH = Path(__file__).resolve().parents[2]
ANALYSIS_OUTPUT_BASE = BASE_PATH / "build" / "analysis" / "adc"


def _read_adc(path: Path) -> MeasAdc:
    if not path.is_file():
        raise FileNotFoundError(2, "measurement input not found", path)
    msmt = read_measurement(path)
    if not isinstance(msmt, (MeasAdcExt, MeasAdcInt)):
        raise TypeError(f"{path} contains {type(msmt).__name__}, expected MeasAdcExt or MeasAdcInt")
    return msmt


def adc00_pex_transfer(output_dir: Path) -> tuple[Path, ...]:
    """Plot the ADC00 PEX monotonic transfer measurement."""

    msmt = _read_adc(BASE_PATH / "build/adc_pex_monotonic/adc_00.h5")
    analysis = analyze_adc_transfer([msmt])
    return plot_adc_transfer(
        [msmt],
        analysis,
        output_path=output_dir / "adc00_pex_transfer",
    )


def adc00_adc01_noise_power_and_code_diagnostics(output_dir: Path) -> tuple[Path, ...]:
    """Plot ADC00/ADC01 noise, power, code-distribution, and decision diagnostics."""

    run_dir = BASE_PATH / "build/scan_adc/20260801_194930"
    measurements = []
    for adc_position, adc_index in enumerate((0, 1)):
        for rate_position, rate_mbd in enumerate(range(80, 1601, 40)):
            file_index = adc_position * 39 + rate_position
            measurements.append(
                _read_adc(
                    run_dir
                    / (
                        f"{file_index:04d}_00_adc{adc_index:02d}_{rate_mbd}mbd_"
                        "dcp50mv_logicp2sym_vcm600mv_vdda1200mv_vddd1200mv_"
                        "vddac1200mv_t25c.h5"
                    )
                )
            )
    if any(
        not isinstance(msmt.param.vin_diff, h.Vdc.Params) or float(msmt.param.vin_diff.dc) != 0.05
        for msmt in measurements
    ):
        raise ValueError("physical DC-noise pipeline requires a fixed 50 mV differential input")
    if any(
        len(msmt.daq.dout) != 100_000
        or int(msmt.info.readbacks.get("fastrx_lost_count", 0))
        or int(msmt.info.readbacks.get("spi_mismatches", 0))
        for msmt in measurements
    ):
        raise ValueError("physical 50 mV DC-noise campaign contains incomplete or invalid captures")

    run_dir_100mv = BASE_PATH / "build/scan_adc/20260802_021624"
    measurements_100mv = []
    for adc_position, adc_index in enumerate((0, 1)):
        for rate_position, rate_mbd in enumerate(range(80, 1601, 40)):
            file_index = adc_position * 39 + rate_position
            measurements_100mv.append(
                _read_adc(
                    run_dir_100mv
                    / (
                        f"{file_index:04d}_00_adc{adc_index:02d}_{rate_mbd}mbd_"
                        "dcp100mv_logicp2sym_vcm600mv_vdda1200mv_vddd1200mv_"
                        "vddac1200mv_t25c.h5"
                    )
                )
            )
    if any(
        not isinstance(msmt.param.vin_diff, h.Vdc.Params) or float(msmt.param.vin_diff.dc) != 0.1
        for msmt in measurements_100mv
    ):
        raise ValueError("physical DC-noise pipeline requires a fixed 100 mV differential input")
    if any(
        len(msmt.daq.dout) != 100_000
        or int(msmt.info.readbacks.get("fastrx_lost_count", 0))
        or int(msmt.info.readbacks.get("spi_mismatches", 0))
        for msmt in measurements_100mv
    ):
        raise ValueError("physical 100 mV DC-noise campaign contains incomplete or invalid captures")

    physical_noise = analyze_adc_noise_sweep(measurements)
    physical_noise_100mv = analyze_adc_noise_sweep(measurements_100mv)
    generated_dir = BASE_PATH / "build/adc/hdl21gen_noise_vs_rate/20260801_0821"
    generated_measurements = [
        _read_adc(generated_dir / f"{rate_msps}msps_cm600mv_dc50mv/result.h5") for rate_msps in (2, 6, 10)
    ]
    pex_dir = BASE_PATH / "build/adc/frida65a_noise_vs_rate/20260731_2353"
    pex_measurements = [_read_adc(pex_dir / f"{rate_msps}msps_cm600mv_dc50mv/result.h5") for rate_msps in (2, 6, 10)]
    generated_noise = analyze_adc_noise_sweep(generated_measurements)
    pex_noise = analyze_adc_noise_sweep(pex_measurements)
    generated_diagnostic_paths = []
    for rate_msps, msmt in zip((2, 6, 10), generated_measurements, strict=True):
        generated_diagnostic_paths.extend(
            plot_adc_noise(
                [msmt],
                analyze_adc_noise([msmt]),
                output_path=output_dir / f"spice_hdl21gen_{rate_msps}msps_output_code_histogram",
            )
        )
        generated_diagnostic_paths.extend(
            plot_adc_decision_paths(
                msmt,
                analyze_adc_decision_paths(msmt, selection="all"),
                output_path=output_dir / f"spice_hdl21gen_{rate_msps}msps_decision_paths",
            )
        )
    sine_run_dir = BASE_PATH / "build/scan_adc/20260730_215145_complete"
    sine_adc00_measurements = [
        _read_adc(
            sine_run_dir
            / (
                f"{rate_position:04d}_00_adc00_{rate_mbd}mbd_"
                "sin9998.77hz_p0mv_1000mvpp_logicp2sym_vcm600mv_"
                "vdda1200mv_vddd1200mv_vddac1200mv_t25c.h5"
            )
        )
        for rate_position, rate_mbd in enumerate(range(80, 1601, 40))
    ]
    sine_adc00_dynamic = analyze_adc_dynamic_sweep(sine_adc00_measurements)
    sine_adc01_measurements = [
        _read_adc(
            sine_run_dir
            / (
                f"{39 + rate_position:04d}_00_adc01_{rate_mbd}mbd_"
                "sin9998.77hz_p0mv_1000mvpp_logicp2sym_vcm600mv_"
                "vdda1200mv_vddd1200mv_vddac1200mv_t25c.h5"
            )
        )
        for rate_position, rate_mbd in enumerate(range(80, 1601, 40))
    ]
    sine_adc01_dynamic = analyze_adc_dynamic_sweep(sine_adc01_measurements)
    adc00_80mbd_measurement = sine_adc00_measurements[0]
    adc00_80mbd_detail_paths = (
        *plot_measurement_waveforms(
            adc00_80mbd_measurement,
            record_index=0,
            output_path=output_dir / "adc00_80mbd_sine_waveforms",
        ),
        *plot_adc_dynamic(
            adc00_80mbd_measurement,
            analyze_adc_dynamic(adc00_80mbd_measurement),
            output_path=output_dir / "adc00_80mbd_sine_fit_and_spectrum",
        ),
    )
    sine_measurements = (*sine_adc00_measurements, *sine_adc01_measurements)
    power_paths = plot_adc_power_sweep(
        sine_measurements,
        analyze_adc_power_sweep(sine_measurements),
        output_path=output_dir / "adc_power_vs_conversion_rate",
    )
    if not np.allclose(
        (physical_noise.input_lsb_v, generated_noise.input_lsb_v, pex_noise.input_lsb_v),
        physical_noise.input_lsb_v,
        rtol=1e-12,
        atol=0.0,
    ):
        raise ValueError("physical/SPICE comparison requires one nominal input LSB scale")

    dc_adc00_selected = np.asarray([msmt.param.observed_adc == 0 for msmt in measurements])
    dc_adc01_selected = np.asarray([msmt.param.observed_adc == 1 for msmt in measurements])
    dc_adc00_measurements = [msmt for msmt in measurements if msmt.param.observed_adc == 0]
    dc_adc01_measurements = [msmt for msmt in measurements if msmt.param.observed_adc == 1]
    dc100_adc00_selected = np.asarray([msmt.param.observed_adc == 0 for msmt in measurements_100mv])
    dc100_adc01_selected = np.asarray([msmt.param.observed_adc == 1 for msmt in measurements_100mv])
    dc100_adc00_measurements = [msmt for msmt in measurements_100mv if msmt.param.observed_adc == 0]
    dc100_adc01_measurements = [msmt for msmt in measurements_100mv if msmt.param.observed_adc == 1]
    adc00_order = np.argsort(physical_noise.sample_rate_hz[dc_adc00_selected])
    adc01_order = np.argsort(physical_noise.sample_rate_hz[dc_adc01_selected])
    physical_rates = physical_noise.sample_rate_hz[dc_adc00_selected][adc00_order]
    probe_adc00_noise = physical_noise.pretrigger_vin_diff_noise_rms_v[dc_adc00_selected][adc00_order]
    probe_adc00_mean = physical_noise.pretrigger_vin_diff_mean_v[dc_adc00_selected][adc00_order]
    probe_adc01_noise = physical_noise.pretrigger_vin_diff_noise_rms_v[dc_adc01_selected][adc01_order]
    probe_adc01_mean = physical_noise.pretrigger_vin_diff_mean_v[dc_adc01_selected][adc01_order]
    compared_noise_v = np.concatenate(
        (
            probe_adc00_noise,
            physical_noise.input_referred_noise_rms_v[dc_adc00_selected],
            physical_noise_100mv.input_referred_noise_rms_v[dc100_adc00_selected],
            sine_adc00_dynamic.input_referred_noise_rms_v,
            generated_noise.input_referred_noise_rms_v,
            pex_noise.input_referred_noise_rms_v,
        )
    )
    comparison = AnalysisAdcNoiseSweep(
        sample_rate_hz=np.concatenate(
            (
                physical_rates,
                physical_noise.sample_rate_hz[dc_adc00_selected],
                physical_noise_100mv.sample_rate_hz[dc100_adc00_selected],
                sine_adc00_dynamic.active_conversion_rate_hz,
                generated_noise.sample_rate_hz,
                pex_noise.sample_rate_hz,
            )
        ),
        logic_phase_delay_symbols=np.concatenate(
            (
                np.full(len(physical_rates), 2.0),
                physical_noise.logic_phase_delay_symbols[dc_adc00_selected],
                physical_noise_100mv.logic_phase_delay_symbols[dc100_adc00_selected],
                sine_adc00_dynamic.logic_phase_delay_symbols,
                generated_noise.logic_phase_delay_symbols,
                pex_noise.logic_phase_delay_symbols,
            )
        ),
        comparator_time_percent=np.concatenate(
            (
                np.full(len(physical_rates), 75.0),
                physical_noise.comparator_time_percent[dc_adc00_selected],
                physical_noise_100mv.comparator_time_percent[dc100_adc00_selected],
                50.0 + 12.5 * sine_adc00_dynamic.logic_phase_delay_symbols,
                generated_noise.comparator_time_percent,
                pex_noise.comparator_time_percent,
            )
        ),
        input_lsb_v=physical_noise.input_lsb_v,
        input_referred_noise_rms_v=compared_noise_v,
        pretrigger_vin_diff_mean_v=np.concatenate(
            (
                probe_adc00_mean,
                physical_noise.pretrigger_vin_diff_mean_v[dc_adc00_selected],
                physical_noise_100mv.pretrigger_vin_diff_mean_v[dc100_adc00_selected],
                np.full(len(sine_adc00_measurements), np.nan),
                generated_noise.pretrigger_vin_diff_mean_v,
                pex_noise.pretrigger_vin_diff_mean_v,
            )
        ),
        pretrigger_vin_diff_noise_rms_v=np.concatenate(
            (
                probe_adc00_noise,
                physical_noise.pretrigger_vin_diff_noise_rms_v[dc_adc00_selected],
                physical_noise_100mv.pretrigger_vin_diff_noise_rms_v[dc100_adc00_selected],
                np.full(len(sine_adc00_measurements), np.nan),
                generated_noise.pretrigger_vin_diff_noise_rms_v,
                pex_noise.pretrigger_vin_diff_noise_rms_v,
            )
        ),
        mean_dout=np.zeros(len(compared_noise_v)),
        std_dout=compared_noise_v / physical_noise.input_lsb_v,
        minimum_dout=np.zeros(len(compared_noise_v), dtype=np.int64),
        maximum_dout=np.zeros(len(compared_noise_v), dtype=np.int64),
        bit_mismatches=np.zeros(len(compared_noise_v), dtype=np.int64),
    )
    comparison_measurements = (
        *dc_adc00_measurements,
        *dc_adc00_measurements,
        *dc100_adc00_measurements,
        *sine_adc00_measurements,
        *generated_measurements,
        *pex_measurements,
    )
    adc00_paths = plot_adc_noise_sweep(
        comparison_measurements,
        comparison,
        output_path=output_dir / "adc00_noise_vs_conversion_rate",
        series_labels=(
            *("Input stimulus noise" for _ in physical_rates),
            *("Measured (50 mV DC)" for _ in dc_adc00_measurements),
            *("Measured (100 mV DC)" for _ in dc100_adc00_measurements),
            *("Measured (1 V sine)" for _ in sine_adc00_measurements),
            *("SPICE Ideal (50 mV DC)" for _ in generated_measurements),
            *("SPICE PEX (50 mV DC)" for _ in pex_measurements),
        ),
        title="ADC00 input-referred noise vs conversion rate",
    )
    adc01_rates = physical_noise.sample_rate_hz[dc_adc01_selected][adc01_order]
    if not np.array_equal(adc01_rates, physical_rates):
        raise ValueError("ADC00 and ADC01 physical noise sweeps use different conversion rates")
    adc01_noise_v = np.concatenate(
        (
            probe_adc01_noise,
            physical_noise.input_referred_noise_rms_v[dc_adc01_selected],
            physical_noise_100mv.input_referred_noise_rms_v[dc100_adc01_selected],
            sine_adc01_dynamic.input_referred_noise_rms_v,
        )
    )
    adc01_comparison = AnalysisAdcNoiseSweep(
        sample_rate_hz=np.concatenate(
            (
                adc01_rates,
                physical_noise.sample_rate_hz[dc_adc01_selected],
                physical_noise_100mv.sample_rate_hz[dc100_adc01_selected],
                sine_adc01_dynamic.active_conversion_rate_hz,
            )
        ),
        logic_phase_delay_symbols=np.concatenate(
            (
                np.full(len(adc01_rates), 2.0),
                physical_noise.logic_phase_delay_symbols[dc_adc01_selected],
                physical_noise_100mv.logic_phase_delay_symbols[dc100_adc01_selected],
                sine_adc01_dynamic.logic_phase_delay_symbols,
            )
        ),
        comparator_time_percent=np.concatenate(
            (
                np.full(len(adc01_rates), 75.0),
                physical_noise.comparator_time_percent[dc_adc01_selected],
                physical_noise_100mv.comparator_time_percent[dc100_adc01_selected],
                50.0 + 12.5 * sine_adc01_dynamic.logic_phase_delay_symbols,
            )
        ),
        input_lsb_v=physical_noise.input_lsb_v,
        input_referred_noise_rms_v=adc01_noise_v,
        pretrigger_vin_diff_mean_v=np.concatenate(
            (
                probe_adc01_mean,
                physical_noise.pretrigger_vin_diff_mean_v[dc_adc01_selected],
                physical_noise_100mv.pretrigger_vin_diff_mean_v[dc100_adc01_selected],
                np.full(len(sine_adc01_measurements), np.nan),
            )
        ),
        pretrigger_vin_diff_noise_rms_v=np.concatenate(
            (
                probe_adc01_noise,
                physical_noise.pretrigger_vin_diff_noise_rms_v[dc_adc01_selected],
                physical_noise_100mv.pretrigger_vin_diff_noise_rms_v[dc100_adc01_selected],
                np.full(len(sine_adc01_measurements), np.nan),
            )
        ),
        mean_dout=np.zeros(len(adc01_noise_v)),
        std_dout=adc01_noise_v / physical_noise.input_lsb_v,
        minimum_dout=np.zeros(len(adc01_noise_v), dtype=np.int64),
        maximum_dout=np.zeros(len(adc01_noise_v), dtype=np.int64),
        bit_mismatches=np.zeros(len(adc01_noise_v), dtype=np.int64),
    )
    adc01_measurements = (
        *dc_adc01_measurements,
        *dc_adc01_measurements,
        *dc100_adc01_measurements,
        *sine_adc01_measurements,
    )
    adc01_paths = plot_adc_noise_sweep(
        adc01_measurements,
        adc01_comparison,
        output_path=output_dir / "adc01_noise_vs_conversion_rate",
        series_labels=(
            *("Input stimulus noise" for _ in adc01_rates),
            *("Measured (50 mV DC)" for _ in dc_adc01_measurements),
            *("Measured (100 mV DC)" for _ in dc100_adc01_measurements),
            *("Measured (1 V sine)" for _ in sine_adc01_measurements),
        ),
        title="ADC01 input-referred noise vs conversion rate",
    )
    adc00_distribution_paths = plot_adc_noise_distribution_sweep(
        dc_adc00_measurements,
        analyze_adc_noise_sweep(dc_adc00_measurements),
        output_path=output_dir / "adc00_50mv_dc_output_code_distributions",
        title="ADC00 50 mV fixed-input output-code distributions",
    )
    adc01_distribution_paths = plot_adc_noise_distribution_sweep(
        dc_adc01_measurements,
        analyze_adc_noise_sweep(dc_adc01_measurements),
        output_path=output_dir / "adc01_50mv_dc_output_code_distributions",
        title="ADC01 50 mV fixed-input output-code distributions",
    )
    adc00_100mv_distribution_paths = plot_adc_noise_distribution_sweep(
        dc100_adc00_measurements,
        analyze_adc_noise_sweep(dc100_adc00_measurements),
        output_path=output_dir / "adc00_100mv_dc_output_code_distributions",
        title="ADC00 100 mV fixed-input output-code distributions",
    )
    adc01_100mv_distribution_paths = plot_adc_noise_distribution_sweep(
        dc100_adc01_measurements,
        analyze_adc_noise_sweep(dc100_adc01_measurements),
        output_path=output_dir / "adc01_100mv_dc_output_code_distributions",
        title="ADC01 100 mV fixed-input output-code distributions",
    )
    adc00_violin_paths = plot_adc_noise_violin_sweep(
        dc_adc00_measurements,
        analyze_adc_noise_sweep(dc_adc00_measurements),
        output_path=output_dir / "adc00_50mv_dc_output_code_violins",
        title="ADC00 50 mV fixed-input output-code violin distributions",
    )
    adc01_violin_paths = plot_adc_noise_violin_sweep(
        dc_adc01_measurements,
        analyze_adc_noise_sweep(dc_adc01_measurements),
        output_path=output_dir / "adc01_50mv_dc_output_code_violins",
        title="ADC01 50 mV fixed-input output-code violin distributions",
    )
    adc00_100mv_violin_paths = plot_adc_noise_violin_sweep(
        dc100_adc00_measurements,
        analyze_adc_noise_sweep(dc100_adc00_measurements),
        output_path=output_dir / "adc00_100mv_dc_output_code_violins",
        title="ADC00 100 mV fixed-input output-code violin distributions",
    )
    adc01_100mv_violin_paths = plot_adc_noise_violin_sweep(
        dc100_adc01_measurements,
        analyze_adc_noise_sweep(dc100_adc01_measurements),
        output_path=output_dir / "adc01_100mv_dc_output_code_violins",
        title="ADC01 100 mV fixed-input output-code violin distributions",
    )
    decision_density_paths = []
    for input_mv, adc00_measurements, adc01_measurements in (
        (50, dc_adc00_measurements, dc_adc01_measurements),
        (100, dc100_adc00_measurements, dc100_adc01_measurements),
    ):
        for adc_index, adc_measurements in ((0, adc00_measurements), (1, adc01_measurements)):
            for rate_msps in (2, 10):
                matches = [
                    msmt
                    for msmt in adc_measurements
                    if np.isclose(float(msmt.info.readbacks["active_conversion_rate_hz"]), rate_msps * 1e6)
                ]
                if len(matches) != 1:
                    raise ValueError(
                        f"ADC{adc_index:02d} {input_mv} mV campaign does not contain one {rate_msps} MSPS run"
                    )
                analysis = analyze_adc_decision_paths(matches[0], selection="all")
                output_path = output_dir / (f"adc{adc_index:02d}_{input_mv}mv_{rate_msps}msps_decision_path_density")
                decision_density_paths.extend(
                    plot_adc_decision_path_density(matches[0], analysis, output_path=output_path)
                )
                decision_density_paths.extend(
                    animate_adc_decision_path_density(matches[0], analysis, output_path=output_path)
                )
    return (
        *adc00_paths,
        *adc01_paths,
        *adc00_distribution_paths,
        *adc01_distribution_paths,
        *adc00_100mv_distribution_paths,
        *adc01_100mv_distribution_paths,
        *adc00_violin_paths,
        *adc01_violin_paths,
        *adc00_100mv_violin_paths,
        *adc01_100mv_violin_paths,
        *power_paths,
        *generated_diagnostic_paths,
        *adc00_80mbd_detail_paths,
        *decision_density_paths,
    )


def adc00_adc01_logic_offset_noise(output_dir: Path) -> tuple[Path, ...]:
    """Plot the matched ADC00 and ADC01 fixed-input sweeps over seven LOGIC offsets."""

    expected_points = {
        (float(rate_mbd), float(logic_offset)) for rate_mbd in range(80, 1601, 40) for logic_offset in range(-3, 4)
    }
    campaigns = (
        (
            "ADC00",
            BASE_PATH / "build/scan_adc/20260802_081407",
            "*_00_adc00_*mbd_dcp50mv_logic*sym_vcm800mv_*.h5",
        ),
        (
            "ADC01",
            BASE_PATH / "build/loopback_fastrx/20260729_181030",
            "adc01_*mbd_logic*_rx*_tap*.h5",
        ),
    )
    artifacts = []
    for adc_name, run_dir, pattern in campaigns:
        measurement_paths = sorted(run_dir.glob(pattern))
        if len(measurement_paths) != 39 * 7:
            raise ValueError(
                f"{adc_name} seven-offset pipeline requires 273 HDF5 inputs, found {len(measurement_paths)}"
            )
        measurements = [_read_adc(path) for path in measurement_paths]
        observed_points = {
            (
                float(msmt.param.symbol_rate) / 1e6,
                float(msmt.param.seq_logic_phase_delay_symbols) - float(msmt.param.seq_comp_phase_delay_symbols),
            )
            for msmt in measurements
        }
        if observed_points != expected_points:
            raise ValueError(f"{adc_name} seven-offset pipeline has missing or unexpected rate/offset points")
        if any(
            not isinstance(msmt.param.vin_diff, h.Vdc.Params)
            or float(msmt.param.vin_diff.dc) != 0.05
            or float(msmt.param.vin_cm.dc) != 0.8
            for msmt in measurements
        ):
            raise ValueError(f"{adc_name} seven-offset pipeline requires a 50 mV DC input at 800 mV common mode")

        noise = analyze_adc_noise_sweep(measurements)
        artifacts.extend(
            plot_adc_noise_sweep(
                measurements,
                noise,
                output_path=output_dir / f"{adc_name.lower()}_noise_vs_conversion_rate_and_logic_offset",
            )
        )
    return tuple(artifacts)


TARGETS: dict[str, Callable[[Path], tuple[Path, ...]]] = {
    target.__name__: target
    for target in (
        adc00_pex_transfer,
        adc00_adc01_noise_power_and_code_diagnostics,
        adc00_adc01_logic_offset_noise,
    )
}


def main() -> None:
    """Run one named analysis pipeline, or every target when none is named."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "target",
        nargs="?",
        choices=sorted(TARGETS),
        help="analysis-pipeline function to run; omit to run all targets",
    )
    args = parser.parse_args()
    output_dir = ANALYSIS_OUTPUT_BASE / datetime.now().astimezone().strftime("%Y%m%d_%H%M")
    output_dir.mkdir(parents=True, exist_ok=False)
    print(f"Analysis output: {output_dir}")
    run_all = args.target is None
    target_names = tuple(TARGETS) if run_all else (args.target,)
    for target_name in target_names:
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
