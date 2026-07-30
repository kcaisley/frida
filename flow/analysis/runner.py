"""Explicit, manually invoked measurement -> analysis -> plot pipelines.

Each function names its input files directly. Add a pipeline only after its
capture has been inspected and the corresponding analysis has been validated.
There is intentionally no automatic discovery of run directories or analysis
pipelines; each pipeline names and validates its input campaign.

Run one named pipeline from the repository root with:

    uv run python -m flow.analysis.runner physical_adc_plus2_dynamic_rate_sweep

Omit the target name to run every registered pipeline. One invocation writes
all derived artifacts beneath one timestamped ``build/analysis/adc`` directory.
"""

from __future__ import annotations

import argparse
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from time import perf_counter

from flow.analysis.adc import (
    analyze_adc_dynamic,
    analyze_adc_dynamic_sweep,
    analyze_adc_noise,
    analyze_adc_noise_sweep,
    analyze_adc_power_sweep,
    analyze_adc_transfer,
)
from flow.analysis.io import read_measurement
from flow.analysis.plots import (
    plot_adc_dynamic,
    plot_adc_dynamic_rate_sweep,
    plot_adc_noise,
    plot_adc_noise_sweep,
    plot_adc_power_sweep,
    plot_adc_transfer,
    plot_measurement_waveforms,
)
from flow.analysis.types import MeasAdcExt

BASE_PATH = Path(__file__).resolve().parents[2]
ANALYSIS_OUTPUT_BASE = BASE_PATH / "build" / "analysis" / "adc"


def _read_adc(path: Path) -> MeasAdcExt:
    if not path.is_file():
        raise FileNotFoundError(2, "measurement input not found", path)
    msmt = read_measurement(path)
    if not isinstance(msmt, MeasAdcExt):
        raise TypeError(f"{path} contains {type(msmt).__name__}, expected MeasAdcExt")
    return msmt


def behavioral_adc_transfer(output_dir: Path) -> tuple[Path, ...]:
    """Plot the current behavioral ADC HDF5 result."""

    msmt = _read_adc(BASE_PATH / "build/behavioral_scan/adc_00.h5")
    analysis = analyze_adc_transfer([msmt])
    return plot_adc_transfer(
        [msmt],
        analysis,
        output_path=output_dir / "behavioral_adc_transfer",
    )


def spice_adc_monotonic_transfer(output_dir: Path) -> tuple[Path, ...]:
    """Plot the current monotonic ADC PEX HDF5 result."""

    msmt = _read_adc(BASE_PATH / "build/adc_pex_monotonic/adc_00.h5")
    analysis = analyze_adc_transfer([msmt])
    return plot_adc_transfer(
        [msmt],
        analysis,
        output_path=output_dir / "spice_adc_monotonic_transfer",
    )


def spice_adc_noise(output_dir: Path) -> tuple[Path, ...]:
    """Plot the current fixed-input ADC PEX noise result."""

    msmt = _read_adc(BASE_PATH / "build/adc_pex_noise/adc00_dinit0101010101010101_noise_pex.h5")
    analysis = analyze_adc_noise([msmt])
    return plot_adc_noise(
        [msmt],
        analysis,
        output_path=output_dir / "spice_adc_noise",
    )


def physical_adc00_80mbd_dynamic(output_dir: Path) -> tuple[Path, ...]:
    """Analyze the validated 29 July ADC00 physical sine acquisition."""

    run_dir = BASE_PATH / "build/scan_adc/20260730_215145_complete"
    msmt = _read_adc(
        run_dir
        / (
            "0000_00_adc00_80mbd_sin9998.77hz_p0mv_1000mvpp_logicp2sym_"
            "vcm600mv_vdda1200mv_vddd1200mv_vddac1200mv_t25c.h5"
        )
    )
    analysis = analyze_adc_dynamic(msmt)
    waveform_paths = plot_measurement_waveforms(
        msmt,
        record_index=0,
        output_path=output_dir / "physical_adc00_80mbd_waveforms",
    )
    dynamic_paths = plot_adc_dynamic(
        msmt,
        analysis,
        output_path=output_dir / "physical_adc00_80mbd_dynamic",
    )
    return (*waveform_paths, *dynamic_paths)


def physical_adc_plus2_dynamic_rate_sweep(output_dir: Path) -> tuple[Path, ...]:
    """Analyze the consolidated, alignment-checked ADC00/ADC01 +2-symbol sweep."""

    run_dir = BASE_PATH / "build/scan_adc/20260730_215145_complete"
    measurements = []
    for adc_position, adc_index in enumerate((0, 1)):
        for rate_position, rate_mbd in enumerate(range(80, 1601, 40)):
            file_index = adc_position * 39 + rate_position
            measurements.append(
                _read_adc(
                    run_dir
                    / (
                        f"{file_index:04d}_00_"
                        f"adc{adc_index:02d}_{rate_mbd}mbd_"
                        "sin9998.77hz_p0mv_1000mvpp_logicp2sym_vcm600mv_"
                        "vdda1200mv_vddd1200mv_vddac1200mv_t25c.h5"
                    )
                )
            )
    if {
        float(msmt.param.seq_logic_phase_delay_symbols) - float(msmt.param.seq_comp_phase_delay_symbols)
        for msmt in measurements
    } != {2.0}:
        raise ValueError("physical +2-symbol pipeline received another LOGIC offset")

    dynamic = analyze_adc_dynamic_sweep(measurements)
    extreme_limit_dout = 2.0 * dynamic.residual_tail_limit_dout
    flagged = [
        (
            int(adc_index),
            float(active_rate_hz) / 1e6,
            int(negative_count),
            int(positive_count),
            float(expected_count),
            float(maximum_residual),
        )
        for (
            adc_index,
            active_rate_hz,
            negative_count,
            positive_count,
            expected_count,
            maximum_residual,
        ) in zip(
            dynamic.observed_adc,
            dynamic.active_conversion_rate_hz,
            dynamic.negative_residual_tail_count,
            dynamic.positive_residual_tail_count,
            dynamic.expected_residual_tail_count,
            dynamic.maximum_abs_residual_dout,
            strict=True,
        )
        if negative_count + positive_count > expected_count or maximum_residual > extreme_limit_dout
    ]
    if flagged:
        print(
            f"WARNING: {len(flagged)}/{len(measurements)} configurations exceed the Gaussian "
            f"±{dynamic.residual_tail_limit_dout:g}-LSB tail population or contain a residual "
            f"beyond ±{extreme_limit_dout:g} LSB"
        )
        for (
            adc_index,
            active_rate_msps,
            negative_count,
            positive_count,
            expected_count,
            maximum_residual,
        ) in flagged:
            print(
                f"  ADC{adc_index:02d} {active_rate_msps:g} MSPS: "
                f"-tail={negative_count}, +tail={positive_count}, "
                f"total={negative_count + positive_count}, expected={expected_count:.0f}; "
                f"maximum {maximum_residual:.3g} LSB"
            )
    power = analyze_adc_power_sweep(measurements)
    dynamic_paths = plot_adc_dynamic_rate_sweep(
        measurements,
        dynamic,
        output_path=output_dir / "adc00_adc01_dynamic_vs_conversion_rate",
    )
    power_paths = plot_adc_power_sweep(
        measurements,
        power,
        output_path=output_dir / "adc_power_vs_conversion_rate",
    )
    return (*dynamic_paths, *power_paths)


def physical_fastrx_alignment_boundary_sweep(output_dir: Path) -> tuple[Path, ...]:
    """Analyze the final guarded high-rate scope/FastRX checks."""

    run_dir = BASE_PATH / "build/loopback_fastrx/20260730_180321"
    measurements = [
        _read_adc(run_dir / filename)
        for filename in (
            "adc01_1400mbd_logic+2_rx08_tap20.h5",
            "adc01_1480mbd_logic+2_rx09_tap17.h5",
            "adc01_1520mbd_logic+2_rx09_tap20.h5",
            "adc01_1560mbd_logic+2_rx08_tap00.h5",
            "adc01_1600mbd_logic+2_rx09_tap03.h5",
        )
    ]
    mismatches = [int(msmt.info.readbacks["scope_fastrx_bit_mismatches"]) for msmt in measurements]
    if any(mismatches):
        raise ValueError(f"scope/FastRX alignment sweep contains bit mismatches: {mismatches}")

    noise = analyze_adc_noise_sweep(measurements)
    noise_paths = plot_adc_noise_sweep(
        measurements,
        noise,
        output_path=output_dir / "fastrx_alignment_boundary_noise",
    )
    waveform_paths = []
    for rate_mbd, index in ((1400, 0), (1520, 2), (1600, 4)):
        waveform_paths.extend(
            plot_measurement_waveforms(
                measurements[index],
                record_index=0,
                output_path=output_dir / f"fastrx_alignment_{rate_mbd}mbd_waveforms",
            )
        )
    return (*noise_paths, *waveform_paths)


def physical_adc01_seven_offset_noise_sweep(output_dir: Path) -> tuple[Path, ...]:
    """Analyze the validated ADC01 fixed-input sweep over seven LOGIC offsets."""

    run_dir = BASE_PATH / "build/loopback_fastrx/20260729_181030"
    measurement_paths = sorted(run_dir.glob("adc01_*mbd_logic*_rx*_tap*.h5"))
    if len(measurement_paths) != 39 * 7:
        raise ValueError(f"ADC01 seven-offset pipeline requires 273 HDF5 inputs, found {len(measurement_paths)}")
    measurements = [_read_adc(path) for path in measurement_paths]
    observed_points = {
        (
            float(msmt.param.symbol_rate) / 1e6,
            float(msmt.param.seq_logic_phase_delay_symbols) - float(msmt.param.seq_comp_phase_delay_symbols),
        )
        for msmt in measurements
    }
    expected_points = {
        (float(rate_mbd), float(logic_offset)) for rate_mbd in range(80, 1601, 40) for logic_offset in range(-3, 4)
    }
    if observed_points != expected_points:
        raise ValueError("ADC01 seven-offset pipeline has missing or unexpected rate/offset points")

    noise = analyze_adc_noise_sweep(measurements)
    return plot_adc_noise_sweep(
        measurements,
        noise,
        output_path=output_dir / "adc01_noise_vs_conversion_rate_and_logic_offset",
    )


TARGETS: dict[str, Callable[[Path], tuple[Path, ...]]] = {
    target.__name__: target
    for target in (
        behavioral_adc_transfer,
        spice_adc_monotonic_transfer,
        spice_adc_noise,
        physical_adc00_80mbd_dynamic,
        physical_adc_plus2_dynamic_rate_sweep,
        physical_fastrx_alignment_boundary_sweep,
        physical_adc01_seven_offset_noise_sweep,
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
    output_dir = ANALYSIS_OUTPUT_BASE / datetime.now().astimezone().strftime("%Y%m%d_%H%M%S")
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
