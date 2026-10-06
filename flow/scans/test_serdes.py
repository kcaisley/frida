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

    uv run pytest -q -s -m hw flow/scans/test_serdes.py::test_serdes_rates

The three Keithley 2400s power VDD_A, VDD_D, and VDD_DAC during the test.
Their outputs are disabled and reset to 0 V when the test exits.
Scope captures are saved under ``build/test_serdes/<timestamp>``.

For manually supplied hardware with all four sequencer clocks connected as
declared in map_scope.yaml, capture the named ADC recipes instead:

    uv run pytest -q -s -m hw flow/scans/test_serdes.py::test_adc_sequence_waveforms

This separate test uses only the FPGA and scope. It saves raw CSV, waveform
PDFs and an edge-timing report; it does not control supplies or ADC inputs.

The serializer output-word tests also use only the FPGA and scope. One sweeps
three symbol rates and seven eight-symbol high-pulse widths. The other folds
a 256-bit pattern containing all 254 nonconstant eight-bit contexts:

    uv run pytest -q -s -m hw flow/scans/test_serdes.py::test_serdes_output_words
    uv run pytest -q -s -m hw flow/scans/test_serdes.py::test_serdes_symbol_eye
"""

from __future__ import annotations

import itertools
import json
import os
import time
from dataclasses import replace
from pathlib import Path
from statistics import fmean

import numpy as np
import pytest
from yaml import safe_load

from flow.adc.sequences import SEQUENCES, AdcSequence
from flow.adc.sim import AdcTbParams
from flow.analysis import calc
from flow.analysis.plots import plot_serdes_output_word_grid, plot_serdes_symbol_eye_grid, plot_waveforms
from flow.scans.plldrp import (
    calculate_pll_frequency,
    select_pll_configuration,
    set_pll_divider,
)
from flow.scans.scope import (
    response_value,
    scope_channels,
    scope_wave,
    wait_for_scope_armed,
    wait_for_scope_capture,
    write_scope_csv,
)
from flow.scans.seqgen import convert_params_to_seqgen_fmt

duty_sequences = tuple(
    (name, sequence)
    for name, sequence in SEQUENCES
    if name.startswith(("symbol160_init4_samp20_", "symbol256_init4_samp20_"))
)

comparison_sequences = tuple(
    (name, dict(SEQUENCES)[name])
    for name in (
        "symbol256_init8_samp16_comp11110000_logic11000011",
        "symbol256_init8_samp16_comp11111100_logic00000010",
        "symbol160_init4_samp20_comp11111110_logic00000001",
    )
)

MAP_PATH = Path(__file__).resolve().parent / "map_fpga.yaml"
SCOPE_MAP_PATH = Path(__file__).resolve().parent / "map_scope.yaml"
SMU_MAP_PATH = Path(__file__).resolve().parent / "map_smu.yaml"
OUTPUT_DIR = Path(__file__).resolve().parents[2] / "build" / "test_serdes"
SCOPE_BANDWIDTH_HZ = 2.0e9
SCOPE_VERTICAL_SCALE_V = 0.2
# These 16 requested symbol rates cause the selector to exercise Si570 inputs
# from 100 to 200 MHz and PLL output dividers from 2 to 20, including 1.6 GBd.
SERDES_TEST_SYMBOL_RATES_BPS = tuple(
    rate_mbd * 1e6 for rate_mbd in (80, 100, 125, 160, 200, 250, 320, 400, 500, 640, 800, 900, 1000, 1200, 1400, 1600)
)
SEQUENCE_REPEATS = 2
EXPECTED_TRANSITIONS = {
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

# Every cyclic eight-bit word except 00000000 and 11111111 occurs here.
# Two nonconstant words repeat so the RAM program remains 256 bits long.
SERDES_EYE_PATTERN = (
    "0000000100000011000001010000011100001001000010110000110100001111"
    "0001000100110001010101000101110001100100011011000111010001111100"
    "1001010010011100101011001011010010111100110011010100110111001110"
    "1100111101001111110101010111010110110101111101101111011101111111"
)

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

# fmt: off
SEQ_PATTERNS = {
    "INIT":    "00000000 11111111 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000",
    "SAMP":    "00000000 00000000 11111111 11111111 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000",
    "COMP":    "00000000 00000000 00000000 00000000 00001111 00001111 00001111 00001111 00001111 00001111 00001111 00001111 00001111 00001111 00001111 00001111 00001111 00001111 00001111 00001111 00001111 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000",
    "LOGIC":   "00000000 00001111 00000000 00000000 00000000 11110000 11110000 11110000 11110000 11110000 11110000 11110000 11110000 11110000 11110000 11110000 11110000 11110000 11110000 11110000 11110000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000",
}
# fmt: on


def validate_capture(waveforms, symbol_rate_bps: float, tracks: dict[int, str]) -> tuple[float, float]:
    """Check crossing counts and return measured COMP interval and symbol rate."""
    crossing_times: dict[str, tuple[float, ...]] = {}
    for channel, track in tracks.items():
        waveform = waveforms[channel]
        signal = np.asarray(waveform.data, dtype=np.float64)
        time_s = waveform.x_scale.offset + np.arange(len(signal)) * waveform.x_scale.slope
        low_v, high_v = np.percentile(signal, (1.0, 99.0))
        crossing_level_v = float((low_v + high_v) / 2.0)
        crossings = []
        for rising in (True, False):
            crossings.extend(
                calc.cross(
                    signal,
                    time_s,
                    crossing_level_v,
                    edge="rising" if rising else "falling",
                )
            )
        crossing_times[track] = tuple(sorted(crossings))
        expected_count = EXPECTED_TRANSITIONS[track]
        assert len(crossings) == expected_count, (
            f"{track} on scope CH{channel}: expected {expected_count} transitions, measured {len(crossings)} "
            f"at {crossing_level_v:g} V"
        )

    comp_crossings = crossing_times[COMP_TRACK]
    comp_intervals_s = tuple(right - left for left, right in itertools.pairwise(comp_crossings))
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


@pytest.mark.hw
@pytest.mark.scope_signals("seq_comp", "seq_logic")
def test_serdes_rates(linux_gpib_interface: None) -> None:
    """Hardware: qualify sequencer serialization across all supported rates."""
    channels = scope_channels("seq_comp", "seq_logic")
    SCOPE_TRACKS = {channel: name for name, channel in channels.items()}
    TRIGGER_SCOPE_CHANNEL = channels["seq_logic"]

    from gpib_ctypes import make_default_gpib

    make_default_gpib()
    from basil.dut import Dut

    if not 0.0 < SMU_SUPPLY_V <= 1.2:
        raise ValueError("SMU supply voltage must remain in 0..1.2 V")
    if not 0.0 < SMU_CURRENT_COMPLIANCE_A <= 500.0e-6:
        raise ValueError("SMU current compliance must remain in 0..500 uA")

    run_timestamp = time.strftime("%Y%m%d_%H%M%S")
    run_dir = OUTPUT_DIR / run_timestamp
    run_dir.mkdir(parents=True, exist_ok=False)

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

        params = AdcTbParams(
            seq_init_pattern=SEQ_PATTERNS["INIT"].replace(" ", ""),
            seq_samp_pattern=SEQ_PATTERNS["SAMP"].replace(" ", ""),
            seq_comp_pattern=SEQ_PATTERNS["COMP"].replace(" ", ""),
            seq_logic_pattern=SEQ_PATTERNS["LOGIC"].replace(" ", ""),
        )
        sequence_words = len(params.seq_init_pattern) // 8
        rx_sen_pattern = "0" * 5 + "1" * 17 + "0" * (sequence_words - 22)
        memory = convert_params_to_seqgen_fmt(params, rx_sen_pattern)
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
                for channel in SCOPE_TRACKS:
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
                    daq["seq0"].set_size(len(params.seq_init_pattern) // 8)
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

                    stem = (
                        f"serdes_{target_symbol_rate_bps / 1e6:g}mbd_"
                        f"fin{si570_frequency_hz / 1e6:g}mhz_n{divider_n:02d}"
                    )
                    csv_path = run_dir / f"{stem}.csv"
                    write_scope_csv(csv_path, waveforms, SCOPE_TRACKS)

                    measured_interval_s, measured_symbol_rate_bps = validate_capture(
                        waveforms,
                        symbol_rate_bps,
                        SCOPE_TRACKS,
                    )

                    plot_paths = plot_waveforms(
                        scope_wave(waveforms, SCOPE_TRACKS),
                        title="Oscilloscope waveforms",
                        output_path=csv_path.with_suffix(""),
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
                for channel in SCOPE_TRACKS:
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
                    except Exception as error:  # noqa: BLE001 - best-effort safety shutdown
                        print(f"WARNING: could not disable and zero {rail}: {error}")
                smu_dut.close()


@pytest.mark.hw
@pytest.mark.scope_signals("seq_init", "seq_samp", "seq_comp", "seq_logic")
@pytest.mark.parametrize(
    "name,sequence",
    comparison_sequences + duty_sequences,
    ids=[name for name, _ in comparison_sequences + duty_sequences],
)
def test_adc_sequence_waveforms(name: str, sequence: AdcSequence) -> None:
    """Capture PCB differential INIT/SAMP/COMP/LOGIC; supplies stay manual.

    Requires all four clocks in map_scope.yaml; otherwise pytest skips it.
    The serializer-rate test requires COMP/LOGIC and powers SMUs.
    """
    from basil.dut import Dut

    channels = scope_channels("seq_init", "seq_samp", "seq_comp", "seq_logic")
    tracks = {channel: name.removeprefix("seq_").upper() for name, channel in channels.items()}
    init_channel = channels["seq_init"]
    symbol_rate_bps = 1.6e9
    edge_tolerance_s = 0.25e-9
    run_dir = OUTPUT_DIR / time.strftime("%Y%m%d_%H%M%S") / name
    run_dir.mkdir(parents=True, exist_ok=False)
    params = AdcTbParams(
        seq_init_pattern=sequence.init,
        seq_samp_pattern=sequence.samp,
        seq_comp_pattern=sequence.comp,
        seq_logic_pattern=sequence.logic,
    )
    sequence_words = len(sequence.init) // 8
    memory = convert_params_to_seqgen_fmt(params, "0" * sequence_words)
    config = safe_load(MAP_PATH.read_text())
    config["hw_drivers"] = [
        driver for driver in config["hw_drivers"] if driver["name"] in {"seq0", "gpio2", "i2c0", "si570"}
    ]
    config["registers"] = [register for register in config["registers"] if register["name"] in {"seq0", "gpio2"}]
    daq = Dut(config)
    scope_dut = Dut(str(SCOPE_MAP_PATH))
    scope = seq = None
    try:
        daq.init()
        seq = daq["seq0"]
        assert seq.is_ready, "sequencer must be idle before changing clocks"
        set_pll_divider(daq["gpio2"], 2)
        scope_dut.init()
        scope = scope_dut["scope"]
        # Four differential clock inputs; preserve probe calibration and termination.
        scope.set_acquire_state("STOP")
        scope.set_acquire_mode("SAMPLE")
        scope.set_acquire_stop_after("SEQUENCE")
        # Automatic timebase rounds 16 ns/div to 20 ns/div. Manual sampling
        # gives exactly 160 ns: 1000 samples at the full 6.25 GS/s rate.
        scope._intf.write("HORizontal:MODe MANual")
        scope._intf.write("HORizontal:MODe:SAMPLERate 6.25E9")
        scope.set_horizontal_record_length(1000)
        scope._intf.write("HORizontal:POSition 2.125")  # 3.4 ns before INIT.
        record_length = int(response_value(scope.get_horizontal_record_length()))
        sample_rate_hz = float(response_value(scope._intf.query("HORizontal:SAMPLERate?")))
        assert record_length / sample_rate_hz == pytest.approx(160e-9), "scope must capture a 160 ns record"
        # The instrument clamps shorter records to 1000 samples. Show only the
        # first 120 ns, retaining the 3.4 ns pretrigger margin and full raw data.
        scope._intf.write("DISplay:WAVEView1:ZOOM:ZOOM1:HORizontal:SCAle 1.333333333333")
        scope._intf.write("DISplay:WAVEView1:ZOOM:ZOOM1:HORizontal:POSition 37.5")
        scope._intf.write("DISplay:WAVEView1:ZOOM:ZOOM1:STATe ON")
        zoom_scale_s = float(response_value(scope._intf.query("DISplay:WAVEView1:ZOOM:ZOOM1:HORizontal:WINSCale?")))
        assert zoom_scale_s == pytest.approx(12e-9), "scope must display a 120 ns window"
        for channel in tracks:
            scope._intf.write(f"DISplay:GLObal:CH{channel}:STATE ON")
            scope.set_vertical_scale(0.2, channel=channel)
            scope.set_vertical_position(0.0, channel=channel)
            scope.set_vertical_offset(0.0, channel=channel)
            scope.set_coupling("DC", channel=channel)
            scope.set_bandwidth(SCOPE_BANDWIDTH_HZ, channel=channel)
        scope.set_trigger_type("EDGE")
        scope.set_trigger_source(channel=init_channel)
        scope.set_trigger_edge_slope("RISE")
        scope.set_trigger_level(0.0, channel=init_channel)
        scope.set_trigger_mode("NORMAL")

        # A arms on the first INIT; B captures the next INIT rising edge.
        scope._intf.write("TRIGger:B:STATE OFF")
        scope._intf.write("TRIGger:B:BY EVENTS")
        scope._intf.write("TRIGger:B:EVENTS:COUNt 1")
        scope._intf.write(f"TRIGger:B:EDGE:SOUrce CH{init_channel}")
        scope._intf.write("TRIGger:B:EDGE:SLOpe RISE")
        scope._intf.write("TRIGger:B:EDGE:COUPling DC")
        scope._intf.write(f"TRIGger:B:LEVel:CH{init_channel} 0")
        scope._intf.write("TRIGger:B:STATE ON")
        trigger_b = {
            key: response_value(scope._intf.query(f"TRIGger:B:{key}?"))
            for key in ("STATE", "BY", "EVENTS:COUNt", "EDGE:SOUrce", "EDGE:SLOpe")
        }
        assert trigger_b == {
            "STATE": "1",
            "BY": "EVENTS",
            "EVENTS:COUNt": "1",
            "EDGE:SOUrce": f"CH{init_channel}",
            "EDGE:SLOpe": "RISE",
        }, f"scope did not accept second-INIT triggering: {trigger_b}"

        # Use the same lane packing as the scan, with receive capture disabled.
        seq.set_data(memory)
        seq.set_size(sequence_words)
        seq.set_clk_divide(1)
        seq.set_repeat(4)
        seq.set_en_ext_start(False)
        assert bytes(seq.get_data(size=len(memory))) == bytes(memory)
        scope._intf.write("ACQuire:NUMACq:RESET")
        scope.set_acquire_state("RUN")
        before = wait_for_scope_armed(scope)
        seq.start()
        wait_for_scope_capture(scope, before)
        assert seq.is_ready, "finite sequencer run did not finish"
        waveforms = scope.get_waveforms(tracks)
        write_scope_csv(run_dir / "waveforms.csv", waveforms, tracks)
        wave = scope_wave(waveforms, tracks)
        for artifact in plot_waveforms(wave, title=name, output_path=run_dir / "waveforms"):
            print(f"Saved {name}: {artifact}")

        # Audit the second conversion selected by the A-then-B INIT trigger.
        # The end of the long recipe's idle pause lies outside the pretrigger window.
        # Zero volts is the differential crossing; no per-channel deskew is fitted.
        time_s = wave.time_s
        init_edges = calc.cross(wave.v[tracks[init_channel]][0], time_s, 0.0, edge="rising")
        assert len(init_edges), "capture must include the triggering INIT rising edge"
        origin_s = float(init_edges[np.argmin(np.abs(init_edges))])
        period_s = len(sequence.init) / symbol_rate_bps
        # Reuse the waveform plotter for an INIT-aligned overview and pulse detail.
        relative_time_s = time_s - origin_s
        for view, start_s, stop_s in (("sequence", -3.4e-9, 116.6e-9), ("pulse_detail", 40e-9, 55e-9)):
            selected = (relative_time_s >= start_s) & (relative_time_s <= stop_s)
            plot_waveforms(
                replace(
                    wave, time_s=relative_time_s[selected], v={key: trace[:, selected] for key, trace in wave.v.items()}
                ),
                title=name,
                output_path=run_dir / view,
            )
        init_index = sequence.init.index("1")
        errors = []
        observations: dict[str, dict[str, object]] = {}
        for index, (channel, track) in enumerate(tracks.items()):
            row = np.array([int(bit) for bit in getattr(sequence, track.lower())])
            signal = wave.v[track][0]
            observations[track] = {"min_v": float(signal.min()), "max_v": float(signal.max())}
            for rising in (True, False):
                edge = "rising" if rising else "falling"
                expected_indices = np.flatnonzero((row != np.roll(row, 1)) & (row == int(rising)))
                expected = np.sort(((expected_indices - init_index) % len(row)) / symbol_rate_bps)
                if len(expected):
                    assert time_s[-1] >= origin_s + expected[-1] + edge_tolerance_s, (
                        f"scope record misses the final {track} {edge} edge"
                    )
                measured = calc.cross(signal, time_s, 0.0, edge="rising" if rising else "falling") - origin_s
                measured = measured[(measured >= -edge_tolerance_s) & (measured < period_s - edge_tolerance_s)]
                edge_observations: dict[str, object] = {
                    "expected_s": expected.tolist(),
                    "measured_s": measured.tolist(),
                }
                observations[track][edge] = edge_observations
                if len(expected) != len(measured):
                    errors.append(f"{track} {edge}: expected {len(expected)} edges, measured {len(measured)}")
                elif len(expected):
                    error_s = float(np.max(np.abs(measured - expected)))
                    edge_observations["maximum_error_s"] = error_s
                    if error_s > edge_tolerance_s:
                        errors.append(f"{track} {edge}: maximum timing error {error_s * 1e9:.3f} ns")
        (run_dir / "capture.json").write_text(
            json.dumps(
                {
                    "case": name,
                    "scope": str(scope.get_name()).strip(),
                    "symbol_rate_bps": symbol_rate_bps,
                    "channels": tracks,
                    "patterns": {track: getattr(sequence, track.lower()) for track in tracks.values()},
                    "sample_interval_s": float(time_s[1] - time_s[0]),
                    "record_length": record_length,
                    "record_span_s": record_length / sample_rate_hz,
                    "display_window_s": [-3.4e-9, 116.6e-9],
                    "reference_init_s": origin_s,
                    "conversion_index": 1,
                    "trigger_b": trigger_b,
                    "edge_tolerance_s": edge_tolerance_s,
                    "observations": observations,
                    "errors": errors,
                },
                indent=2,
            )
            + "\n"
        )
        print(
            f"{name}: sample interval {(time_s[1] - time_s[0]) * 1e12:.1f} ps; {errors or 'all edges within tolerance'}"
        )
        assert not errors, "; ".join(errors)
    finally:
        try:
            if seq is not None:
                # End with all four clock outputs low; do not alter ASIC configuration.
                seq.reset()
                seq.set_data(bytes(8))
                seq.set_size(1)
                seq.set_repeat(1)
                seq.set_clk_divide(1)
                seq.set_en_ext_start(False)
                seq.start()
        finally:
            try:
                # Keep the capture settings and last waveform visible for inspection.
                if scope is not None:
                    scope.set_acquire_state("STOP")
            finally:
                scope_dut.close()
                daq.close()


@pytest.mark.hw
@pytest.mark.slow
@pytest.mark.scope_signals("seq_comp")
def test_serdes_output_words() -> None:
    """Capture eight-symbol output words with one through seven high symbols."""

    from basil.dut import Dut

    symbol_rates_bps = (320e6, 960e6, 1600e6)
    high_counts = range(1, 8)
    captures_per_case = 32
    comp_channel = scope_channels("seq_comp")["seq_comp"]
    resume_dir = os.environ.get("FRIDA_SERDES_OUTPUT_WORDS_RUN_DIR")
    run_dir = Path(resume_dir) if resume_dir else OUTPUT_DIR / time.strftime("%Y%m%d_%H%M%S") / "output_words"
    run_dir.mkdir(parents=True, exist_ok=bool(resume_dir))
    config = safe_load(MAP_PATH.read_text())
    config["hw_drivers"] = [
        driver for driver in config["hw_drivers"] if driver["name"] in {"seq0", "gpio2", "i2c0", "si570"}
    ]
    config["registers"] = [register for register in config["registers"] if register["name"] in {"seq0", "gpio2"}]
    daq = Dut(config)
    scope_dut = Dut(str(SCOPE_MAP_PATH))
    seq = scope = None
    try:
        daq.init()
        seq = daq["seq0"]
        assert seq.is_ready, "sequencer must be idle before changing clocks"
        scope_dut.init()
        scope = scope_dut["scope"]
        scope.set_acquire_state("STOP")
        scope.set_acquire_mode("SAMPLE")
        scope.set_acquire_stop_after("SEQUENCE")
        scope._intf.write("HORizontal:MODe MANual")
        scope._intf.write("HORizontal:MODe:SAMPLERate 6.25E9")
        scope.set_horizontal_record_length(1_000)
        scope._intf.write("HORizontal:POSition 10")
        scope._intf.write(f"DISplay:GLObal:CH{comp_channel}:STATE ON")
        scope.set_vertical_scale(SCOPE_VERTICAL_SCALE_V, channel=comp_channel)
        scope.set_vertical_position(0.0, channel=comp_channel)
        scope.set_vertical_offset(0.0, channel=comp_channel)
        scope.set_coupling("DC", channel=comp_channel)
        scope.set_bandwidth(SCOPE_BANDWIDTH_HZ, channel=comp_channel)
        scope._intf.write("TRIGger:B:STATE OFF")
        scope.set_trigger_type("EDGE")
        scope.set_trigger_source(channel=comp_channel)
        scope.set_trigger_edge_slope("RISE")
        scope.set_trigger_level(0.0, channel=comp_channel)
        scope.set_trigger_mode("NORMAL")
        sample_rate_hz = float(response_value(scope._intf.query("HORizontal:SAMPLERate?")))
        assert sample_rate_hz / max(symbol_rates_bps) >= 3, "scope has fewer than three samples per symbol"

        captures_by_case = {}
        for symbol_rate_bps in symbol_rates_bps:
            assert seq.is_ready, "sequencer must be idle before changing the PLL"
            si570_frequency_hz, divider_n = select_pll_configuration(symbol_rate_bps)
            daq["si570"].frequency_change(si570_frequency_hz / 1e6)
            time.sleep(SI570_SETTLE_TIME_S)
            set_pll_divider(daq["gpio2"], divider_n)
            for high_symbols in high_counts:
                case_dir = run_dir / f"{symbol_rate_bps / 1e6:g}mbd_{high_symbols}of8"
                case_dir.mkdir(exist_ok=bool(resume_dir))
                existing = sorted(case_dir.glob("capture_*.csv"))
                if [path.name for path in existing] != [f"capture_{index:03d}.csv" for index in range(len(existing))]:
                    raise ValueError(f"{case_dir} has a noncontiguous capture prefix")
                if len(existing) > captures_per_case:
                    raise ValueError(f"{case_dir} has too many captures")
                if len(existing) == captures_per_case:
                    continue
                # Quiet first/last RAM words keep COMP from toggling while idle.
                word = "1" * high_symbols + "0" * (8 - high_symbols)
                pattern = "0" * 8 + word * 30 + "0" * 8
                params = AdcTbParams(
                    symbol_rate=symbol_rate_bps,
                    seq_init_pattern="0" * 256,
                    seq_samp_pattern="0" * 256,
                    seq_comp_pattern=pattern,
                    seq_logic_pattern="0" * 256,
                )
                memory = convert_params_to_seqgen_fmt(params, "0" * 32)
                seq.reset()
                seq.set_data(bytes(seq.get_mem_size()))
                seq.set_data(memory)
                seq.set_size(32)
                seq.set_clk_divide(1)
                seq.set_repeat(4)
                seq.set_en_ext_start(False)
                assert bytes(seq.get_data(size=len(memory))) == bytes(memory)
                captures = []
                for capture_index in range(len(existing), captures_per_case):
                    scope._intf.write("ACQuire:NUMACq:RESET")
                    scope.set_acquire_state("RUN")
                    before = wait_for_scope_armed(scope, timeout_s=5.0)
                    seq.start()
                    wait_for_scope_capture(scope, before, timeout_s=5.0)
                    assert seq.is_ready, "finite sequencer run did not finish"
                    captured = scope.get_waveforms((comp_channel,))
                    if comp_channel not in captured:
                        raise RuntimeError(f"scope omitted COMP channel {comp_channel}")
                    captures.append(captured)
                    write_scope_csv(case_dir / f"capture_{capture_index:03d}.csv", captured, {comp_channel: "seq_comp"})
                captures_by_case[(int(symbol_rate_bps / 1e6), high_symbols)] = captures
        if not resume_dir:
            for path in plot_serdes_output_word_grid(
                captures_by_case,
                output_channel=comp_channel,
                output_path=run_dir / "msmt_fpga_serdes_output_words_grid",
            ):
                print(f"Saved serializer output-word result: {path}")
    finally:
        try:
            if seq is not None:
                seq.reset()
                seq.set_data(bytes(8))
                seq.set_size(1)
                seq.set_repeat(1)
                seq.set_clk_divide(1)
                seq.set_en_ext_start(False)
                seq.start()
                daq["si570"].frequency_change(200.0)
                time.sleep(SI570_SETTLE_TIME_S)
                set_pll_divider(daq["gpio2"], 2)
        finally:
            try:
                if scope is not None:
                    scope.set_acquire_state("STOP")
            finally:
                scope_dut.close()
                daq.close()


@pytest.mark.hw
@pytest.mark.slow
@pytest.mark.scope_signals("seq_init", "seq_comp")
def test_serdes_symbol_eye() -> None:
    """Fold all nonconstant eight-bit contexts into a single-symbol eye."""

    from basil.dut import Dut

    pattern = SERDES_EYE_PATTERN
    words = {(pattern + pattern)[index : index + 8] for index in range(256)}
    assert len(pattern) == 256 and len(words) == 254
    assert not words & {"00000000", "11111111"}
    symbol_rates_bps = (320e6, 960e6, 1600e6)
    captures_per_rate = 64
    channels = scope_channels("seq_init", "seq_comp")
    marker_channel, output_channel = channels["seq_init"], channels["seq_comp"]
    tracks = {marker_channel: "seq_init", output_channel: "seq_comp"}
    run_dir = OUTPUT_DIR / time.strftime("%Y%m%d_%H%M%S") / "symbol_eye"
    run_dir.mkdir(parents=True, exist_ok=False)
    config = safe_load(MAP_PATH.read_text())
    config["hw_drivers"] = [
        driver for driver in config["hw_drivers"] if driver["name"] in {"seq0", "gpio2", "i2c0", "si570"}
    ]
    config["registers"] = [register for register in config["registers"] if register["name"] in {"seq0", "gpio2"}]
    daq = Dut(config)
    scope_dut = Dut(str(SCOPE_MAP_PATH))
    seq = scope = None
    try:
        daq.init()
        seq = daq["seq0"]
        assert seq.is_ready, "sequencer must be idle before changing clocks"
        scope_dut.init()
        scope = scope_dut["scope"]
        scope.set_acquire_state("STOP")
        scope.set_acquire_mode("SAMPLE")
        scope.set_acquire_stop_after("SEQUENCE")
        scope._intf.write("HORizontal:MODe MANual")
        scope._intf.write("HORizontal:MODe:SAMPLERate 6.25E9")
        scope.set_horizontal_record_length(10_000)
        scope._intf.write("HORizontal:POSition 10")
        for channel in tracks:
            scope._intf.write(f"DISplay:GLObal:CH{channel}:STATE ON")
            scope.set_vertical_scale(SCOPE_VERTICAL_SCALE_V, channel=channel)
            scope.set_vertical_position(0.0, channel=channel)
            scope.set_vertical_offset(0.0, channel=channel)
            scope.set_coupling("DC", channel=channel)
            scope.set_bandwidth(SCOPE_BANDWIDTH_HZ, channel=channel)
        scope._intf.write("TRIGger:B:STATE OFF")
        scope.set_trigger_type("EDGE")
        scope.set_trigger_source(channel=marker_channel)
        scope.set_trigger_edge_slope("RISE")
        scope.set_trigger_level(0.0, channel=marker_channel)
        scope.set_trigger_mode("NORMAL")
        sample_rate_hz = float(response_value(scope._intf.query("HORizontal:SAMPLERate?")))
        record_length = int(response_value(scope.get_horizontal_record_length()))
        assert sample_rate_hz / max(symbol_rates_bps) >= 3, "scope has fewer than three samples per symbol"
        assert record_length / sample_rate_hz >= 256 / min(symbol_rates_bps) + 0.1e-6

        captures_by_rate = {}
        for symbol_rate_bps in symbol_rates_bps:
            assert seq.is_ready, "sequencer must be idle before changing the PLL"
            si570_frequency_hz, divider_n = select_pll_configuration(symbol_rate_bps)
            daq["si570"].frequency_change(si570_frequency_hz / 1e6)
            time.sleep(SI570_SETTLE_TIME_S)
            set_pll_divider(daq["gpio2"], divider_n)
            params = AdcTbParams(
                symbol_rate=symbol_rate_bps,
                seq_init_pattern="1" * 8 + "0" * 248,
                seq_samp_pattern="0" * 256,
                seq_comp_pattern=pattern,
                seq_logic_pattern="0" * 256,
            )
            memory = convert_params_to_seqgen_fmt(params, "0" * 32)
            seq.reset()
            seq.set_data(bytes(seq.get_mem_size()))
            seq.set_data(memory)
            seq.set_size(32)
            seq.set_clk_divide(1)
            seq.set_repeat(4)
            seq.set_en_ext_start(False)
            assert bytes(seq.get_data(size=len(memory))) == bytes(memory)
            case_dir = run_dir / f"{symbol_rate_bps / 1e6:g}mbd"
            case_dir.mkdir()
            captures = []
            for capture_index in range(captures_per_rate):
                scope._intf.write("ACQuire:NUMACq:RESET")
                scope.set_acquire_state("RUN")
                before = wait_for_scope_armed(scope, timeout_s=5.0)
                seq.start()
                wait_for_scope_capture(scope, before, timeout_s=5.0)
                assert seq.is_ready, "finite sequencer run did not finish"
                captured = scope.get_waveforms(tracks)
                if set(captured) != set(tracks):
                    raise RuntimeError(f"scope returned channels {sorted(captured)}, expected {sorted(tracks)}")
                captures.append(captured)
                write_scope_csv(case_dir / f"capture_{capture_index:03d}.csv", captured, tracks)
            captures_by_rate[int(symbol_rate_bps / 1e6)] = captures
        for path in plot_serdes_symbol_eye_grid(
            captures_by_rate,
            marker_channel=marker_channel,
            output_channel=output_channel,
            pattern=pattern,
            output_path=run_dir / "msmt_fpga_serdes_symbol_eye",
        ):
            print(f"Saved serializer symbol eye: {path}")
    finally:
        try:
            if seq is not None:
                seq.reset()
                seq.set_data(bytes(8))
                seq.set_size(1)
                seq.set_repeat(1)
                seq.set_clk_divide(1)
                seq.set_en_ext_start(False)
                seq.start()
                daq["si570"].frequency_change(200.0)
                time.sleep(SI570_SETTLE_TIME_S)
                set_pll_divider(daq["gpio2"], 2)
        finally:
            try:
                if scope is not None:
                    scope.set_acquire_state("STOP")
            finally:
                scope_dut.close()
                daq.close()
