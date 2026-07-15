"""Measure the FPGA sequencer and serializer over several PLL frequencies.

Each pattern string is a space-separated list of serializer words.  Each word
is ``serdes_ratio`` bits wide and represents that many serialized time slices
for one output channel.  The function spreads each track across
``serdes_ratio`` parallel sequencer lanes, which the FPGA's 8:1 OSERDES
recombines into a single high-speed serial output.

For every tested PLL output divider, the scope captures one complete pattern
from a two-repeat sequencer run. The test counts zero crossings on all four
outputs and extracts the serialized timing from the continuous COMP pulse
train.

Run from the repository root after programming the serializer firmware:

    uv run python -m flow.scans.test_serdes
"""

from __future__ import annotations

import time
from pathlib import Path
from statistics import fmean
from typing import Any

import numpy as np
from yaml import safe_load

from flow.circuit.measure import find_crossings
from flow.scans.basic import bitarray_to_seq_gen_format
from flow.scans.plldrp import (
    calculate_pll_frequency,
    select_pll_configuration,
    set_pll_divider,
)
from flow.scans.plot import plot_scope_csv, write_scope_csv
from flow.scans.scope import response_value, wait_for_scope_armed, wait_for_scope_capture

MAP_PATH = Path(__file__).resolve().parent / "map_fpga.yaml"
SCOPE_MAP_PATH = Path(__file__).resolve().parent / "map_scope.yaml"
SCOPE_OUT_DIR = Path("build/scope")
SCOPE_BANDWIDTH_HZ = 2.0e9
# These 16 requested symbol rates cause the selector to exercise Si570 inputs
# from 100 to 200 MHz and PLL output dividers from 2 to 20, including 1.6 GBd.
SERDES_TEST_SYMBOL_RATES_BPS = tuple(
    rate_mbd * 1e6 for rate_mbd in (80, 100, 125, 160, 200, 250, 320, 400, 500, 640, 800, 900, 1000, 1200, 1400, 1600)
)
SEQUENCE_REPEATS = 2
EXPECTED_ZERO_CROSSINGS = {
    "seq_init": 2,
    "seq_samp": 2,
    "seq_comp": 34,
    "seq_logic": 34,
}
COMP_TRACK = "seq_comp"
ZERO_CROSSING_LEVEL_V = 0.0
PERIOD_RELATIVE_TOLERANCE = 0.05
SCOPE_HORIZONTAL_SCALE_AT_200_MHZ_S = 20.0e-9
# Keep the initial INIT rising edge away from the left record boundary while
# retaining the final COMP transitions at the fastest setting.
SCOPE_POST_TRIGGER_AT_200_MHZ_S = 90.0e-9
SI570_SETTLE_TIME_S = 0.02

# The current scope cabling has LOGIC on CH3 and the continuous COMP pulse
# train on CH4. Keep this physical mapping explicit so the timing extraction
# follows COMP rather than LOGIC's isolated marker pulse.
SCOPE_TRACKS = {1: "seq_init", 2: "seq_samp", 3: "seq_logic", 4: "seq_comp"}

SERDES_RATIO = 8
SEQ_GEN_LANES = 8
# fmt: off
SEQ_PATTERNS = {
    "INIT":    "00000000 11111111 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000",
    "SAMP":    "00000000 00000000 11111111 11111111 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000",
    "COMP":    "00000000 00000000 00000000 00000000 00001111 00001111 00001111 00001111 00001111 00001111 00001111 00001111 00001111 00001111 00001111 00001111 00001111 00001111 00001111 00001111 00001111 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000",
    "LOGIC":   "00000000 00001111 00000000 00000000 00000000 11110000 11110000 11110000 11110000 11110000 11110000 11110000 11110000 11110000 11110000 11110000 11110000 11110000 11110000 11110000 11110000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000",
    "RX_SEN":  "0 0 0 0 0 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 0 0 0 0 0 0 0 0 0 0",
    "RX_TEST": "0 0 0 0 1 1 0 0 0 0 0 1 0 1 1 0 0 0 0 0 1 0 0 0 0 0 0 0 0 0 0 0",
}
# fmt: on


def validate_capture(waveforms: dict[int, Any], symbol_rate_bps: float) -> tuple[float, float]:
    """Check crossing counts and return measured COMP interval and symbol rate."""
    crossing_times: dict[str, tuple[float, ...]] = {}
    for channel, track in SCOPE_TRACKS.items():
        waveform = waveforms[channel]
        signal = np.asarray(waveform.data)
        times = waveform.x_scale.offset + np.arange(len(signal)) * waveform.x_scale.slope
        crossings = find_crossings(signal, times, ZERO_CROSSING_LEVEL_V, rising=True)
        crossings.extend(find_crossings(signal, times, ZERO_CROSSING_LEVEL_V, rising=False))
        crossing_times[track] = tuple(sorted(crossings))
        expected_count = EXPECTED_ZERO_CROSSINGS[track]
        assert len(crossings) == expected_count, (
            f"{track} on scope CH{channel}: expected {expected_count} zero crossings, measured {len(crossings)}"
        )

    comp_crossings = crossing_times[COMP_TRACK]
    comp_intervals_s = tuple(right - left for left, right in zip(comp_crossings, comp_crossings[1:]))
    measured_interval_s = fmean(comp_intervals_s)

    # Each COMP half-cycle contains four serialized unit intervals.
    expected_interval_s = 4.0 / symbol_rate_bps
    relative_error = abs(measured_interval_s - expected_interval_s) / expected_interval_s
    assert relative_error <= PERIOD_RELATIVE_TOLERANCE, (
        f"COMP mean crossing interval {measured_interval_s * 1e9:.4g} ns differs from "
        f"expected {expected_interval_s * 1e9:.4g} ns by {relative_error:.2%}; "
        f"limit is {PERIOD_RELATIVE_TOLERANCE:.0%}"
    )

    measured_symbol_rate_bps = 4.0 / measured_interval_s
    return measured_interval_s, measured_symbol_rate_bps


def main() -> None:
    from basil.dut import Dut

    config = safe_load(MAP_PATH.read_text())
    config["transfer_layer"] = [layer for layer in config["transfer_layer"] if layer["name"] != "visa0"]
    config["hw_drivers"] = [driver for driver in config["hw_drivers"] if driver["name"] != "psu0"]
    daq = Dut(config)
    daq.init()
    try:
        daq["gpio0"]["RST_B"] = 0
        daq["gpio0"].write()
        daq["gpio0"]["RST_B"] = 1
        daq["gpio0"].write()

        memory = bitarray_to_seq_gen_format(SEQ_PATTERNS, SERDES_RATIO, SEQ_GEN_LANES)
        # Write raw bytes directly to seq_gen memory, bypassing TrackRegister.
        # TrackRegister.write() does bit/byte reversal that only matches the
        # original 8-bit-wide sequencer; for the 64-bit serializer firmware the
        # reversal scrambles the OSERDES byte lanes.  _drv reaches through the
        # TrackRegister (RL) wrapper to the underlying seq_gen (HL) driver, which
        # exposes set_data() for writing sequencer memory verbatim.
        scope_dut = Dut(str(SCOPE_MAP_PATH))
        scope_dut.init()
        try:
            scope = scope_dut["scope"]
            print(scope.get_name().strip())
            original_horizontal_scale = response_value(scope.get_horizontal_scale())
            original_horizontal_position = response_value(scope._intf.query("HORizontal:POSition?"))
            original_stop_after = response_value(scope.get_acquire_stop_after())
            original_acquire_state = response_value(scope.get_acquire_state())

            try:
                scope.set_acquire_state("STOP")
                scope.set_acquire_stop_after("SEQUENCE")

                for target_symbol_rate_bps in SERDES_TEST_SYMBOL_RATES_BPS:
                    assert daq["seq0"].is_ready, "sequencer must be idle before changing the PLL divider"
                    si570_frequency_hz, divider_n = select_pll_configuration(target_symbol_rate_bps)
                    seq_clk_hz, serializer_clk_hz = calculate_pll_frequency(
                        divider_n,
                        input_frequency_hz=si570_frequency_hz,
                    )
                    symbol_rate_bps = 2.0 * serializer_clk_hz
                    assert symbol_rate_bps == target_symbol_rate_bps

                    daq["si570"].frequency_change(si570_frequency_hz / 1e6)
                    time.sleep(SI570_SETTLE_TIME_S)
                    set_pll_divider(daq["gpio2"], divider_n)

                    # Program the sequencer only after its new clock is locked,
                    # matching the clock-domain setup order used by the proven
                    # single-frequency test.
                    daq["seq0"]._drv.set_data(memory)
                    daq["seq0"].set_size(len(SEQ_PATTERNS["INIT"].split()))
                    daq["seq0"].set_clk_divide(1)
                    daq["seq0"].set_repeat(SEQUENCE_REPEATS)
                    daq["seq0"].set_en_ext_start(False)

                    clock_scale = 200.0e6 / seq_clk_hz
                    horizontal_scale_s = SCOPE_HORIZONTAL_SCALE_AT_200_MHZ_S * clock_scale
                    scope.set_acquire_state("STOP")
                    scope.set_horizontal_scale(horizontal_scale_s)
                    # The MSO54 rounds requested timebases to supported steps.
                    # Use its accepted scale to retain the complete first
                    # pattern while excluding the beginning of repeat two.
                    actual_horizontal_scale_s = float(response_value(scope.get_horizontal_scale()))
                    horizontal_divisions = float(response_value(scope.get_horizontal_divisions()))
                    record_span_s = actual_horizontal_scale_s * horizontal_divisions
                    post_trigger_s = SCOPE_POST_TRIGGER_AT_200_MHZ_S * clock_scale
                    horizontal_position_percent = 100.0 * (1.0 - post_trigger_s / record_span_s)
                    if not 0.0 <= horizontal_position_percent <= 100.0:
                        raise ValueError(
                            f"calculated invalid scope horizontal position {horizontal_position_percent:g}% "
                            f"for N={divider_n}"
                        )
                    scope._intf.write(f"HORizontal:POSition {horizontal_position_percent:g}")
                    scope.set_acquire_state("RUN")
                    acquisition_count_before = wait_for_scope_armed(scope)

                    daq["seq0"].start()
                    wait_for_scope_capture(scope, acquisition_count_before)
                    waveforms = scope.get_waveforms(SCOPE_TRACKS)

                    timestamp = time.strftime("%Y%m%d_%H%M%S")
                    stem = (
                        f"serdes_{target_symbol_rate_bps / 1e6:g}mbd_"
                        f"fin{si570_frequency_hz / 1e6:g}mhz_n{divider_n:02d}_{timestamp}"
                    )
                    csv_path = SCOPE_OUT_DIR / f"{stem}.csv"
                    write_scope_csv(csv_path, waveforms, SCOPE_TRACKS)

                    measured_interval_s, measured_symbol_rate_bps = validate_capture(
                        waveforms,
                        symbol_rate_bps,
                    )

                    plot_paths = plot_scope_csv(
                        csv_path,
                        *SCOPE_TRACKS.values(),
                        title=(f"Measured ADC LVDS sequencer inputs ({symbol_rate_bps / 1e6:g} MBd, N={divider_n})"),
                        info_lines=(
                            f"Si570 input: {si570_frequency_hz / 1e6:g} MHz",
                            f"Sequencer rate: {seq_clk_hz / 1e6:g} MHz",
                            f"Expected symbol rate: {symbol_rate_bps / 1e9:g} GBd",
                            f"Measured symbol rate: {measured_symbol_rate_bps / 1e9:g} GBd",
                            f"COMP crossing interval: {measured_interval_s * 1e9:g} ns",
                            f"Scope bandwidth: {SCOPE_BANDWIDTH_HZ / 1e9:.1f} GHz",
                        ),
                    )
                    for plot_path in plot_paths:
                        print(f"Saved scope waveform plot: {plot_path}")

                    print(
                        f"PASS target={target_symbol_rate_bps / 1e6:g} MBd: "
                        f"Si570={si570_frequency_hz / 1e6:g} MHz, N={divider_n:2d}, "
                        f"seq={seq_clk_hz / 1e6:g} MHz, "
                        f"serializer_clk={serializer_clk_hz / 1e6:g} MHz, "
                        f"measured={measured_symbol_rate_bps / 1e6:g} MBd, "
                        f"COMP interval={measured_interval_s * 1e9:g} ns, "
                        f"crossings={tuple(EXPECTED_ZERO_CROSSINGS.values())}"
                    )
            finally:
                scope.set_acquire_state("STOP")
                scope.set_horizontal_scale(original_horizontal_scale)
                scope._intf.write(f"HORizontal:POSition {original_horizontal_position}")
                scope.set_acquire_stop_after(original_stop_after)
                scope.set_acquire_state(original_acquire_state)
        finally:
            scope_dut.close()
    finally:
        try:
            daq["si570"].frequency_change(200.0)
            time.sleep(SI570_SETTLE_TIME_S)
            set_pll_divider(daq["gpio2"], 2)
        finally:
            daq.close()


if __name__ == "__main__":
    main()
