"""Explicit, manually invoked physical hardware scan campaigns.

Run one named campaign from the repository root, for example::

    uv run python -m flow.scans.runner adc_sine_conversion_rate

Every target owns its complete parameter recipe, lifecycle loop, and output
location. The scan modules acquire one parameter configuration per call and
contain no command-line entry points of their own.
"""

from __future__ import annotations

import argparse
import dataclasses
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

import hdl21 as h

from flow.scans import scan_adc, scan_cdac, scan_comp
from flow.scans.params import build_adc_variants

BASE_PATH = Path(__file__).resolve().parents[2]


def adc_sine_conversion_rate() -> Path:
    """Capture ADC00/ADC01 dynamic performance over 0.5--10 MSPS."""

    board_id = "00"
    adc_indices = (0, 1)
    active_conversion_rates_hz = tuple(rate * 0.25e6 for rate in range(2, 41))
    logic_offsets_symbols = (2.0,)
    conversions = 1_000_000
    vin_cm_v = 0.700
    vin_diff = h.Vsin.Params(voff=0.0, vamp=0.500, freq=9_998.770151)
    run_dir = BASE_PATH / "build/scan_adc" / datetime.now().astimezone().strftime("%Y%m%d_%H%M%S")
    variants = build_adc_variants(
        board_id=board_id,
        adc_indices=adc_indices,
        active_conversion_rates_hz=active_conversion_rates_hz,
        logic_offsets_symbols=logic_offsets_symbols,
        conversions=conversions,
        vin_cm_v=vin_cm_v,
        vin_diff=vin_diff,
    )
    active = False
    current = variants[0]
    try:
        for index, params in enumerate(variants):
            position = (
                "only"
                if len(variants) == 1
                else "first"
                if index == 0
                else "last"
                if index == len(variants) - 1
                else "middle"
            )
            current = params
            if position in {"first", "middle"}:
                active = True
            scan_adc.scan(params, run_dir=run_dir, position=position)
            if position in {"last", "only"}:
                active = False
    finally:
        if active:
            scan_adc.scan(current, run_dir=run_dir, position="abort")
    return run_dir


def adc00_fixed_input_noise() -> Path:
    """Capture ADC00 fixed-50-mV noise at 2, 6, and 10 MSPS."""

    board_id = "00"
    adc_indices = (0,)
    active_conversion_rates_hz = (2.0e6, 6.0e6, 10.0e6)
    logic_offsets_symbols = (2.0,)
    conversions = 100_000
    vin_cm_v = 0.700
    vin_diff = h.Vdc.Params(dc=0.050)
    run_dir = BASE_PATH / "build/scan_adc" / datetime.now().astimezone().strftime("%Y%m%d_%H%M%S")
    variants = build_adc_variants(
        board_id=board_id,
        adc_indices=adc_indices,
        active_conversion_rates_hz=active_conversion_rates_hz,
        logic_offsets_symbols=logic_offsets_symbols,
        conversions=conversions,
        vin_cm_v=vin_cm_v,
        vin_diff=vin_diff,
    )
    active = False
    current = variants[0]
    try:
        for index, params in enumerate(variants):
            position = (
                "only"
                if len(variants) == 1
                else "first"
                if index == 0
                else "last"
                if index == len(variants) - 1
                else "middle"
            )
            current = params
            if position in {"first", "middle"}:
                active = True
            scan_adc.scan(params, run_dir=run_dir, position=position)
            if position in {"last", "only"}:
                active = False
    finally:
        if active:
            scan_adc.scan(current, run_dir=run_dir, position="abort")
    return run_dir


def adc_fixed_input_noise_50mv() -> Path:
    """Capture ADC00/ADC01 fixed-50-mV noise over 0.5--10 MSPS."""

    board_id = "00"
    adc_indices = (0, 1)
    active_conversion_rates_hz = tuple(rate * 0.25e6 for rate in range(2, 41))
    logic_offsets_symbols = (2.0,)
    conversions = 100_000
    vin_cm_v = 0.700
    vin_diff = h.Vdc.Params(dc=0.050)
    run_dir = BASE_PATH / "build/scan_adc" / datetime.now().astimezone().strftime("%Y%m%d_%H%M%S")
    variants = build_adc_variants(
        board_id=board_id,
        adc_indices=adc_indices,
        active_conversion_rates_hz=active_conversion_rates_hz,
        logic_offsets_symbols=logic_offsets_symbols,
        conversions=conversions,
        vin_cm_v=vin_cm_v,
        vin_diff=vin_diff,
    )
    active = False
    current = variants[0]
    try:
        for index, params in enumerate(variants):
            position = (
                "only"
                if len(variants) == 1
                else "first"
                if index == 0
                else "last"
                if index == len(variants) - 1
                else "middle"
            )
            current = params
            if position in {"first", "middle"}:
                active = True
            scan_adc.scan(params, run_dir=run_dir, position=position)
            if position in {"last", "only"}:
                active = False
    finally:
        if active:
            scan_adc.scan(current, run_dir=run_dir, position="abort")
    return run_dir


def adc_fixed_input_noise_100mv() -> Path:
    """Capture ADC00/ADC01 fixed-100-mV noise over 0.5--10 MSPS."""

    board_id = "00"
    adc_indices = (0, 1)
    active_conversion_rates_hz = tuple(rate * 0.25e6 for rate in range(2, 41))
    logic_offsets_symbols = (2.0,)
    conversions = 100_000
    vin_cm_v = 0.700
    vin_diff = h.Vdc.Params(dc=0.100)
    run_dir = BASE_PATH / "build/scan_adc" / datetime.now().astimezone().strftime("%Y%m%d_%H%M%S")
    variants = build_adc_variants(
        board_id=board_id,
        adc_indices=adc_indices,
        active_conversion_rates_hz=active_conversion_rates_hz,
        logic_offsets_symbols=logic_offsets_symbols,
        conversions=conversions,
        vin_cm_v=vin_cm_v,
        vin_diff=vin_diff,
    )
    active = False
    current = variants[0]
    try:
        for index, params in enumerate(variants):
            position = (
                "only"
                if len(variants) == 1
                else "first"
                if index == 0
                else "last"
                if index == len(variants) - 1
                else "middle"
            )
            current = params
            if position in {"first", "middle"}:
                active = True
            scan_adc.scan(params, run_dir=run_dir, position=position)
            if position in {"last", "only"}:
                active = False
    finally:
        if active:
            scan_adc.scan(current, run_dir=run_dir, position="abort")
    return run_dir


def adc00_fixed_input_timing() -> Path:
    """Capture ADC00 fixed-input noise across rate and LOGIC timing."""

    board_id = "00"
    adc_indices = (0,)
    active_conversion_rates_hz = tuple(rate * 0.25e6 for rate in range(2, 41))
    logic_offsets_symbols = tuple(range(-3, 4))
    conversions = 1_000
    vin_cm_v = 0.700
    vin_diff = h.Vdc.Params(dc=0.050)
    run_dir = BASE_PATH / "build/scan_adc" / datetime.now().astimezone().strftime("%Y%m%d_%H%M%S")
    variants = build_adc_variants(
        board_id=board_id,
        adc_indices=adc_indices,
        active_conversion_rates_hz=active_conversion_rates_hz,
        logic_offsets_symbols=logic_offsets_symbols,
        conversions=conversions,
        vin_cm_v=vin_cm_v,
        vin_diff=vin_diff,
    )
    active = False
    current = variants[0]
    try:
        for index, params in enumerate(variants):
            position = (
                "only"
                if len(variants) == 1
                else "first"
                if index == 0
                else "last"
                if index == len(variants) - 1
                else "middle"
            )
            current = params
            if position in {"first", "middle"}:
                active = True
            scan_adc.scan(params, run_dir=run_dir, position=position)
            if position in {"last", "only"}:
                active = False
    finally:
        if active:
            scan_adc.scan(current, run_dir=run_dir, position="abort")
    return run_dir


def adc01_fixed_input_timing() -> Path:
    """Capture ADC01 fixed-input noise across rate and LOGIC timing."""

    board_id = "00"
    adc_indices = (1,)
    active_conversion_rates_hz = tuple(rate * 0.25e6 for rate in range(2, 41))
    logic_offsets_symbols = tuple(range(-3, 4))
    conversions = 1_000
    vin_cm_v = 0.700
    vin_diff = h.Vdc.Params(dc=0.050)
    run_dir = BASE_PATH / "build/scan_adc" / datetime.now().astimezone().strftime("%Y%m%d_%H%M%S")
    variants = build_adc_variants(
        board_id=board_id,
        adc_indices=adc_indices,
        active_conversion_rates_hz=active_conversion_rates_hz,
        logic_offsets_symbols=logic_offsets_symbols,
        conversions=conversions,
        vin_cm_v=vin_cm_v,
        vin_diff=vin_diff,
    )
    active = False
    current = variants[0]
    try:
        for index, params in enumerate(variants):
            position = (
                "only"
                if len(variants) == 1
                else "first"
                if index == 0
                else "last"
                if index == len(variants) - 1
                else "middle"
            )
            current = params
            if position in {"first", "middle"}:
                active = True
            scan_adc.scan(params, run_dir=run_dir, position=position)
            if position in {"last", "only"}:
                active = False
    finally:
        if active:
            scan_adc.scan(current, run_dir=run_dir, position="abort")
    return run_dir


def adc_transfer_curve() -> Path:
    """Capture the settled static transfer of ADC00."""

    board_id = "00"
    adc_indices = (0,)
    active_conversion_rates_hz = (10.0e6,)
    logic_offsets_symbols = (2.0,)
    conversions = 100
    vin_cm_v = 0.700
    vin_diff_values_v = tuple((step - 500) * 0.0015 for step in range(1_001))
    run_dir = BASE_PATH / "build/scan_adc" / datetime.now().astimezone().strftime("%Y%m%d_%H%M%S")
    templates = build_adc_variants(
        board_id=board_id,
        adc_indices=adc_indices,
        active_conversion_rates_hz=active_conversion_rates_hz,
        logic_offsets_symbols=logic_offsets_symbols,
        conversions=conversions,
        vin_cm_v=vin_cm_v,
        vin_diff=h.Vdc.Params(dc=0.0),
        campaign="adc_transfer",
    )
    variants = [
        dataclasses.replace(template, tb=dataclasses.replace(template.tb, vin_diff=h.Vdc.Params(dc=vin_diff_v)))
        for vin_diff_v in vin_diff_values_v
        for template in templates
    ]
    active = False
    current = variants[0]
    try:
        for index, params in enumerate(variants):
            position = (
                "only"
                if len(variants) == 1
                else "first"
                if index == 0
                else "last"
                if index == len(variants) - 1
                else "middle"
            )
            current = params
            if position in {"first", "middle"}:
                active = True
            scan_adc.scan(params, run_dir=run_dir, position=position)
            if position in {"last", "only"}:
                active = False
    finally:
        if active:
            scan_adc.scan(current, run_dir=run_dir, position="abort")
    return run_dir


def adc_ramp_code_density() -> Path:
    """Capture ADC00--ADC03 full-scale sawtooth code density."""

    board_id = "00"
    adc_indices = (0, 1, 2, 3)
    active_conversion_rates_hz = (1.0e6,)
    logic_offsets_symbols = (0.0,)
    conversions = 4_000_000
    vin_cm_v = 0.700
    vin_diff = h.Vpwl.Params(wave="0 -1 0.1 1")
    run_dir = BASE_PATH / "build/scan_adc" / datetime.now().astimezone().strftime("%Y%m%d_%H%M%S")
    variants = build_adc_variants(
        board_id=board_id,
        adc_indices=adc_indices,
        active_conversion_rates_hz=active_conversion_rates_hz,
        logic_offsets_symbols=logic_offsets_symbols,
        conversions=conversions,
        vin_cm_v=vin_cm_v,
        vin_diff=vin_diff,
        campaign="adc_ramp",
    )
    active = False
    current = variants[0]
    try:
        for index, params in enumerate(variants):
            position = (
                "only"
                if len(variants) == 1
                else "first"
                if index == 0
                else "last"
                if index == len(variants) - 1
                else "middle"
            )
            current = params
            if position in {"first", "middle"}:
                active = True
            scan_adc.scan(params, run_dir=run_dir, position=position)
            if position in {"last", "only"}:
                active = False
    finally:
        if active:
            scan_adc.scan(current, run_dir=run_dir, position="abort")
    return run_dir


def comp_common_mode() -> Path:
    """Capture ADC00--ADC03 comparator common-mode S-curves."""

    adc_indices = (0, 1, 2, 3)
    common_mode_values_v = (0.7, 0.8, 0.9, 1.0, 1.1, 1.2)
    minimum_v = 0.0
    maximum_v = 25.0e-3
    step_v = 100.0e-6
    conversions = 1_000
    run_dir = BASE_PATH / "build/scan_comp" / datetime.now().astimezone().strftime("%Y%m%d_%H%M%S")
    variants = scan_comp.build_common_mode_variants(
        adc_indices=adc_indices,
        common_mode_values_v=common_mode_values_v,
        minimum_v=minimum_v,
        maximum_v=maximum_v,
        step_v=step_v,
        conversions=conversions,
    )
    return scan_comp.scan(variants, run_dir=run_dir, capture_scope_per_curve=False)


def comp_sampling_noise() -> Path:
    """Capture ADC00--ADC03 complementary-CDAC track/hold S-curves."""

    adc_indices = (0, 1, 2, 3)
    coupling_percentages = (0.0, 25.0, 50.0, 75.0, 100.0)
    vin_cm_v = 0.700
    minimum_v = 0.0
    maximum_v = 25.0e-3
    step_v = 100.0e-6
    conversions = 1_000
    run_dir = BASE_PATH / "build/scan_comp" / datetime.now().astimezone().strftime("%Y%m%d_%H%M%S")
    variants = scan_comp.build_sampling_noise_variants(
        adc_indices=adc_indices,
        coupling_percentages=coupling_percentages,
        vin_cm_v=vin_cm_v,
        minimum_v=minimum_v,
        maximum_v=maximum_v,
        step_v=step_v,
        conversions=conversions,
    )
    return scan_comp.scan(variants, run_dir=run_dir, capture_scope_per_curve=False)


def comp_sampling_noise_repair() -> Path:
    """Recapture the two rejected sampling-noise curves."""

    adc_indices = (0, 1, 2, 3)
    coupling_percentages = (0.0, 25.0, 50.0, 75.0, 100.0)
    vin_cm_v = 0.700
    minimum_v = 0.0
    maximum_v = 25.0e-3
    step_v = 100.0e-6
    conversions = 1_000
    selected_curves = {
        (1, 100.0, "track"),
        (2, 75.0, "track"),
    }
    run_dir = BASE_PATH / "build/scan_comp" / datetime.now().astimezone().strftime("%Y%m%d_%H%M%S")
    variants = scan_comp.build_sampling_noise_variants(
        adc_indices=adc_indices,
        coupling_percentages=coupling_percentages,
        vin_cm_v=vin_cm_v,
        minimum_v=minimum_v,
        maximum_v=maximum_v,
        step_v=step_v,
        conversions=conversions,
        selected_curves=selected_curves,
    )
    return scan_comp.scan(variants, run_dir=run_dir, capture_scope_per_curve=False)


def cdac_cap_mismatch() -> Path:
    """Capture the complete ADC00--ADC03 A-to-B capacitor matrix."""

    adc_indices = (0, 1, 2, 3)
    coarse_step_v = 1.0e-3
    coarse_trials = 128
    run_dir = BASE_PATH / "build/scan_cdac" / datetime.now().astimezone().strftime("%Y%m%d_%H%M%S")
    variants = scan_cdac.build_capacitor_variants(
        adc_indices=adc_indices,
        coarse_step_v=coarse_step_v,
        coarse_trials=coarse_trials,
    )
    return scan_cdac.scan(variants, run_dir=run_dir, capture_scope_per_curve=False)


def cdac_cap_mismatch_diagnostic_repair() -> Path:
    """Recapture the three diagnostic curves from the accepted campaign."""

    adc_indices = (0, 1, 2, 3)
    coarse_step_v = 1.0e-3
    coarse_trials = 128
    selected_curves = {
        (2, "n", 0, "1to0", 0),
        (2, "n", 4, "1to0", 1),
        (3, "p", 9, "0to1", 0),
    }
    run_dir = BASE_PATH / "build/scan_cdac" / datetime.now().astimezone().strftime("%Y%m%d_%H%M%S")
    variants = scan_cdac.build_capacitor_variants(
        adc_indices=adc_indices,
        coarse_step_v=coarse_step_v,
        coarse_trials=coarse_trials,
        selected_curves=selected_curves,
    )
    return scan_cdac.scan(variants, run_dir=run_dir, capture_scope_per_curve=False)


def cdac_cap_mismatch_calibration_boundary_repair() -> Path:
    """Recapture the 15 curves which crossed the old calibration boundary."""

    adc_indices = (0, 1, 2, 3)
    coarse_step_v = 1.0e-3
    coarse_trials = 128
    selected_curves = {
        (0, "n", 6, "0to1", 1),
        (0, "p", 6, "1to0", 1),
        (1, "n", 5, "0to1", 1),
        (1, "n", 6, "0to1", 1),
        (1, "n", 7, "0to1", 1),
        (1, "n", 8, "0to1", 1),
        (1, "p", 6, "1to0", 1),
        (1, "p", 7, "1to0", 1),
        (1, "p", 8, "1to0", 1),
        (1, "p", 9, "1to0", 1),
        (2, "n", 4, "1to0", 1),
        (2, "n", 6, "0to1", 1),
        (2, "p", 6, "1to0", 1),
        (3, "n", 10, "0to1", 1),
        (3, "p", 10, "1to0", 1),
    }
    run_dir = BASE_PATH / "build/scan_cdac" / datetime.now().astimezone().strftime("%Y%m%d_%H%M%S")
    variants = scan_cdac.build_capacitor_variants(
        adc_indices=adc_indices,
        coarse_step_v=coarse_step_v,
        coarse_trials=coarse_trials,
        selected_curves=selected_curves,
    )
    return scan_cdac.scan(variants, run_dir=run_dir, capture_scope_per_curve=False)


TARGETS: dict[str, Callable[[], Path]] = {
    target.__name__: target
    for target in (
        adc_sine_conversion_rate,
        adc00_fixed_input_noise,
        adc_fixed_input_noise_50mv,
        adc_fixed_input_noise_100mv,
        adc00_fixed_input_timing,
        adc01_fixed_input_timing,
        adc_transfer_curve,
        adc_ramp_code_density,
        comp_common_mode,
        comp_sampling_noise,
        comp_sampling_noise_repair,
        cdac_cap_mismatch,
        cdac_cap_mismatch_diagnostic_repair,
        cdac_cap_mismatch_calibration_boundary_repair,
    )
}


def main() -> None:
    """Run one explicitly selected physical hardware campaign."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("target", choices=sorted(TARGETS), help="physical scan campaign to run")
    args = parser.parse_args()
    run_dir = TARGETS[args.target]()
    print(f"Completed {args.target} in {run_dir}")


if __name__ == "__main__":
    main()
