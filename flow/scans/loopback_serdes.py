"""Measure the FPGA sequencer and serializer over several PLL frequencies.

Each pattern string is a space-separated list of serializer words.  Each word
is ``serdes_ratio`` bits wide and represents that many serialized time slices
for one output channel.  The function spreads each track across
``serdes_ratio`` parallel sequencer lanes, which the FPGA's 8:1 OSERDES
recombines into a single high-speed serial output.

For every tested PLL output divider, the scope captures one complete pattern
from a two-repeat sequencer run. The test counts transitions on the
connected COMP and LOGIC outputs and extracts the serialized timing from the
continuous COMP pulse train.

Run from the repository root after programming the serializer firmware:

    uv run python -m flow.scans.loopback_serdes

The three Keithley 2400s power VDD_A, VDD_D, and VDD_DAC during the test.
Their outputs are disabled and reset to 0 V when the test exits.
"""

from __future__ import annotations

import time
from pathlib import Path
from statistics import fmean
from typing import Any

import numpy as np
from yaml import safe_load

from flow.circuit.measure import find_crossings
from flow.scans.scan_adc import convert_dict_to_seqgen_fmt
from flow.scans.plldrp import (
    calculate_pll_frequency,
    select_pll_configuration,
    set_pll_divider,
)
from flow.scans.plot import SubplotSpec, plot_time_domain_csv, write_scope_csv
from flow.scans.scope import response_value, wait_for_scope_armed, wait_for_scope_capture

MAP_PATH = Path(__file__).resolve().parent / "map_fpga.yaml"
SCOPE_MAP_PATH = Path(__file__).resolve().parent / "map_scope.yaml"
SMU_MAP_PATH = Path(__file__).resolve().parent / "map_smu.yaml"
SCOPE_OUT_DIR = Path("build/scope")
SCOPE_BANDWIDTH_HZ = 2.0e9
SCOPE_VERTICAL_SCALE_V = 0.2
# These 16 requested symbol rates cause the selector to exercise Si570 inputs
# from 100 to 200 MHz and PLL output dividers from 2 to 20, including 1.6 GBd.
SERDES_TEST_SYMBOL_RATES_BPS = tuple(
    rate_mbd * 1e6 for rate_mbd in (80, 100, 125, 160, 200, 250, 320, 400, 500, 640, 800, 900, 1000, 1200, 1400, 1600)
)
SEQUENCE_REPEATS = 2
EXPECTED_TRANSITIONS = {
    "seq_init": 2,
    "seq_samp": 2,
    "seq_comp": 34,
    "seq_logic": 34,
}
COMP_TRACK = "seq_comp"
PERIOD_RELATIVE_TOLERANCE = 0.05
SCOPE_HORIZONTAL_SCALE_AT_200_MHZ_S = 20.0e-9
# Trigger on LOGIC's early marker pulse. Keep the beginning of the pattern
# visible while retaining every COMP transition and excluding repeat two.
SCOPE_POST_TRIGGER_AT_200_MHZ_S = 120.0e-9
SI570_SETTLE_TIME_S = 0.02
SCOPE_CAPTURE_SETTLE_TIME_S = 0.1
SCOPE_CAPTURE_ATTEMPTS = 3

SMU_RAILS = (
    ("smu1", "VDD_A"),
    ("smu2", "VDD_D"),
    ("smu3", "VDD_DAC"),
)
SMU_SUPPLY_V = 1.2
SMU_VOLTAGE_RANGE_V = 2.0
SMU_CURRENT_COMPLIANCE_A = 500.0e-6
SMU_SETTLE_TIME_S = 0.5
SMU_MINIMUM_LOADED_V = 1.15

# The current scope cabling has the continuous COMP pulse train on CH2 and
# LOGIC on CH3. INIT and SAMP are intentionally not acquired.
COMP_SCOPE_CHANNEL = 2
LOGIC_SCOPE_CHANNEL = 3
TRIGGER_SCOPE_CHANNEL = LOGIC_SCOPE_CHANNEL
SCOPE_TRACKS = {
    COMP_SCOPE_CHANNEL: "seq_comp",
    LOGIC_SCOPE_CHANNEL: "seq_logic",
}
SCOPE_CHANNELS = (1, 2, 3, 4)

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
        low_v, high_v = np.percentile(signal, (1.0, 99.0))
        crossing_level_v = float((low_v + high_v) / 2.0)
        crossings = find_crossings(signal, times, crossing_level_v, rising=True)
        crossings.extend(find_crossings(signal, times, crossing_level_v, rising=False))
        crossing_times[track] = tuple(sorted(crossings))
        expected_count = EXPECTED_TRANSITIONS[track]
        assert len(crossings) == expected_count, (
            f"{track} on scope CH{channel}: expected {expected_count} transitions, measured {len(crossings)} "
            f"at {crossing_level_v:g} V"
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
    from gpib_ctypes import make_default_gpib

    make_default_gpib()
    from basil.dut import Dut

    if not 0.0 < SMU_SUPPLY_V <= 1.2:
        raise ValueError("SMU supply voltage must remain in 0..1.2 V")
    if not 0.0 < SMU_CURRENT_COMPLIANCE_A <= 500.0e-6:
        raise ValueError("SMU current compliance must remain in 0..500 uA")

    config = safe_load(MAP_PATH.read_text())
    config["transfer_layer"] = [layer for layer in config["transfer_layer"] if layer["name"] != "visa0"]
    config["hw_drivers"] = [driver for driver in config["hw_drivers"] if driver["name"] != "psu0"]
    daq = Dut(config)
    smu_dut = Dut(str(SMU_MAP_PATH))
    smus = []
    daq.init()
    try:
        smu_dut.init()
        smus = [(smu_dut[name], rail) for name, rail in SMU_RAILS]

        # Configure all three chip domains with their outputs disabled. Keep
        # these recognizable Basil operations visible because their ordering,
        # voltage ceiling, and current compliance are safety critical.
        for smu, rail in smus:
            smu.off()
            smu.set_voltage(0.0)
            smu.source_volt()
            smu.four_wire_off()
            smu.set_voltage_range(SMU_VOLTAGE_RANGE_V)
            smu.set_current_limit(SMU_CURRENT_COMPLIANCE_A)
            smu.current_sense_autorange_on()
            smu.set_current_nplc(10.0)
            smu.autozero_on()
            smu.set_voltage(SMU_SUPPLY_V)
            programmed_voltage_v = float(smu.get_source_voltage())
            programmed_compliance_a = float(smu.get_current_limit())
            if not 0.0 < programmed_voltage_v <= SMU_SUPPLY_V:
                raise RuntimeError(f"{rail}: unsafe voltage setpoint readback {programmed_voltage_v:g} V")
            if not 0.0 < programmed_compliance_a <= SMU_CURRENT_COMPLIANCE_A:
                raise RuntimeError(f"{rail}: unsafe current compliance readback {programmed_compliance_a:g} A")

        # Enable the domains back-to-back so the chip is not powered through
        # one domain for an extended interval.
        for smu, _rail in smus:
            smu.on()
        time.sleep(SMU_SETTLE_TIME_S)

        for smu, rail in smus:
            measured_voltage_v = float(smu.get_voltage())
            measured_current_a = float(smu.get_current())
            print(
                f"{rail}: {measured_voltage_v:.6f} V, "
                f"{measured_current_a * 1e6:.3f} uA "
                f"(limit {SMU_CURRENT_COMPLIANCE_A * 1e6:g} uA)"
            )
            if measured_voltage_v < SMU_MINIMUM_LOADED_V:
                raise RuntimeError(
                    f"{rail}: measured only {measured_voltage_v:g} V; the SMU is likely in current compliance"
                )
            if measured_voltage_v > SMU_SUPPLY_V + 5.0e-3:
                raise RuntimeError(f"{rail}: measured unsafe voltage {measured_voltage_v:g} V")

        daq["gpio0"]["RST_B"] = 0
        daq["gpio0"].write()
        daq["gpio0"]["RST_B"] = 1
        daq["gpio0"].write()

        memory = convert_dict_to_seqgen_fmt(
            SEQ_PATTERNS,
            SERDES_RATIO,
            SEQ_GEN_LANES,
        )
        scope_dut = Dut(str(SCOPE_MAP_PATH))
        scope_dut.init()
        try:
            scope = scope_dut["scope"]
            print(scope.get_name().strip())
            original_horizontal_scale = response_value(scope.get_horizontal_scale())
            original_horizontal_position = response_value(scope._intf.query("HORizontal:POSition?"))
            original_stop_after = response_value(scope.get_acquire_stop_after())
            original_acquire_state = response_value(scope.get_acquire_state())
            original_trigger_mode = response_value(scope.get_trigger_mode())
            original_trigger_type = response_value(scope.get_trigger_type())
            original_trigger_source = response_value(scope.get_triggr_source())
            original_trigger_slope = response_value(scope.get_trigger_edge_slope())
            original_trigger_level = response_value(scope.get_trigger_level(channel=TRIGGER_SCOPE_CHANNEL))
            original_channel_display = {
                channel: response_value(scope._intf.query(f"DISplay:GLObal:CH{channel}:STATE?"))
                for channel in SCOPE_TRACKS
            }

            try:
                scope.set_acquire_state("STOP")
                scope.set_acquire_stop_after("SEQUENCE")
                for channel in SCOPE_CHANNELS:
                    scope.set_vertical_scale(
                        SCOPE_VERTICAL_SCALE_V,
                        channel=channel,
                    )
                    scope.set_vertical_position(0.0, channel=channel)
                    scope.set_vertical_offset(0.0, channel=channel)
                    scope.set_bandwidth(SCOPE_BANDWIDTH_HZ, channel=channel)
                for channel in SCOPE_TRACKS:
                    scope._intf.write(f"DISplay:GLObal:CH{channel}:STATE ON")
                scope.set_trigger_type("EDGE")
                scope.set_trigger_source(channel=TRIGGER_SCOPE_CHANNEL)
                scope.set_trigger_edge_slope("RISE")
                scope.set_trigger_level(
                    0.0,
                    channel=TRIGGER_SCOPE_CHANNEL,
                )
                scope.set_trigger_mode("NORMAL")

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
                    # This public Basil seq_gen programming sequence is exercised
                    # by test_seqgen.py; its raw-memory packing helper is tested
                    # by test_helpers.py. Do not use TrackRegister.write(), whose
                    # legacy reversal does not match the 64-bit memory layout.
                    daq["seq0"].set_data(memory)
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
                    for capture_attempt in range(1, SCOPE_CAPTURE_ATTEMPTS + 1):
                        scope._intf.write("ACQuire:NUMACq:RESET")
                        scope.set_acquire_state("RUN")
                        acquisition_count_before = wait_for_scope_armed(scope)

                        daq["seq0"].start()
                        wait_for_scope_capture(scope, acquisition_count_before)
                        time.sleep(SCOPE_CAPTURE_SETTLE_TIME_S)
                        waveforms = scope.get_waveforms(SCOPE_TRACKS)
                        missing_channels = sorted(set(SCOPE_TRACKS).difference(waveforms))
                        if not missing_channels:
                            break
                        print(
                            f"Scope capture attempt {capture_attempt}/{SCOPE_CAPTURE_ATTEMPTS} "
                            f"did not return channels {missing_channels}; re-arming"
                        )
                    else:
                        raise RuntimeError(
                            f"scope did not return channels {missing_channels} after "
                            f"{SCOPE_CAPTURE_ATTEMPTS} acquisitions"
                        )

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

                    plot_paths = plot_time_domain_csv(
                        csv_path,
                        {
                            "seq_logic_v": SubplotSpec(ylabel="LOGIC (V)"),
                            f"{COMP_TRACK}_v": SubplotSpec(
                                ylabel="COMP (V)",
                                info_lines=(
                                    f"Si570 input: {si570_frequency_hz / 1e6:g} MHz",
                                    f"Sequencer rate: {seq_clk_hz / 1e6:g} MHz",
                                    f"Expected symbol rate: {symbol_rate_bps / 1e9:g} GBd",
                                    f"Measured symbol rate: {measured_symbol_rate_bps / 1e9:g} GBd",
                                    f"COMP crossing interval: {measured_interval_s * 1e9:g} ns",
                                    f"Scope bandwidth: "
                                    f"{float(response_value(scope.get_bandwidth(channel=COMP_SCOPE_CHANNEL))) / 1e9:.1f} GHz",
                                ),
                            ),
                        },
                        title=(f"Measured ADC LVDS sequencer inputs ({symbol_rate_bps / 1e6:g} MBd, N={divider_n})"),
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
                        f"transitions=COMP:{EXPECTED_TRANSITIONS['seq_comp']},"
                        f"LOGIC:{EXPECTED_TRANSITIONS['seq_logic']}"
                    )
            finally:
                scope.set_acquire_state("STOP")
                scope.set_horizontal_scale(original_horizontal_scale)
                scope._intf.write(f"HORizontal:POSition {original_horizontal_position}")
                scope.set_trigger_mode(original_trigger_mode)
                scope.set_trigger_type(original_trigger_type)
                scope._intf.write(f"TRIGger:A:EDGe:SOUrce {original_trigger_source}")
                scope.set_trigger_edge_slope(original_trigger_slope)
                scope.set_trigger_level(
                    original_trigger_level,
                    channel=TRIGGER_SCOPE_CHANNEL,
                )
                # Leave every analog channel in the standard high-bandwidth,
                # zero-offset state instead of restoring stale per-channel
                # offsets from an earlier measurement.
                for channel in SCOPE_CHANNELS:
                    scope.set_vertical_scale(SCOPE_VERTICAL_SCALE_V, channel=channel)
                    scope.set_vertical_position(0.0, channel=channel)
                    scope.set_vertical_offset(0.0, channel=channel)
                    scope.set_bandwidth(SCOPE_BANDWIDTH_HZ, channel=channel)
                for channel, display in original_channel_display.items():
                    scope._intf.write(f"DISplay:GLObal:CH{channel}:STATE {display}")
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
            try:
                daq.close()
            finally:
                for smu, rail in smus:
                    try:
                        smu.off()
                        smu.set_voltage(0.0)
                    except Exception as error:
                        print(f"WARNING: could not disable and zero {rail}: {error}")
                smu_dut.close()


if __name__ == "__main__":
    main()
