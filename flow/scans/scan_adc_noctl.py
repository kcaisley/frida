"""Acquire ADC data through the FPGA with scope validation and manually supplied input and rails."""

from __future__ import annotations

import math
import socket
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from time import monotonic, sleep
from typing import Literal

import hdl21 as h
import numpy as np
from bitarray import bitarray

from flow.adc.sequences import AdcSequence
from flow.analysis.adc import analyze_scope_wave_to_bits
from flow.analysis.io import write_measurement
from flow.analysis.types import AdcDaq, MeasAdcExt, MeasInfo
from flow.caparray import get_caparray_weights
from flow.scans.fastrx import (
    convert_fastrx_words_to_adc,
    program_comp_delay,
    select_fastrx_capture_settings,
)
from flow.scans.params import AdcScanParams, load_board_map, validate_params
from flow.scans.plldrp import calculate_pll_frequency, select_pll_configuration, set_pll_divider
from flow.scans.scan_adc import convert_dac_caps_to_adc_weights, convert_params_to_spi_fmt
from flow.scans.scope import (
    crop_adc_scope_conversion,
    scope_channels,
    scope_records_to_adc_wave,
    wait_for_scope_armed,
    wait_for_scope_capture,
)
from flow.scans.seqgen import build_fastrx_capture_pattern


def scan(
    params: AdcScanParams,
    *,
    run_dir: Path,
    position: Literal["first", "middle", "last", "only", "abort"],
) -> Path:
    """Acquire one fixed-input point and compare its first retained conversion to scope."""

    SI570_SETTLE_S = 0.02
    FASTRX_CAPTURE_TIMEOUT_S = 5.0
    FASTRX_TRAILING_DRAIN_S = 0.01
    MAX_RAW_FASTRX_WORDS = 20

    if position not in {"first", "middle", "last", "only", "abort"}:
        raise ValueError(f"unknown ADC scan lifecycle position {position!r}")
    if position != "abort":
        validate_params(params)
        if params.tb.seq_init_pattern[0] != "1" or params.tb.seq_init_pattern[-1] != "0":
            raise ValueError("ADC control sequence must start at the INIT rising edge")
    scan_params = params
    params = scan_params.tb
    if scan_params.board_id is None or (
        position != "abort" and (scan_params.observed_adc is None or scan_params.active_adc_mask is None)
    ):
        raise ValueError("every physical scan variant must select a board, observed ADC, and active ADC mask")
    if position != "abort" and not isinstance(params.vin_diff, h.Vdc.Params):
        raise ValueError("uncontrolled ADC scans require a manually applied fixed DC differential input")

    board_id = scan_params.board_id
    board = load_board_map()["boards"][board_id]
    supply_limits = board["supply_limits"]
    minimum_supply_v = float(supply_limits["minimum_voltage_v"])
    maximum_supply_v = float(supply_limits["maximum_voltage_v"])
    signal_headroom_v = float(supply_limits["signal_headroom_v"])
    fixed_vdd_io_v = float(board["fixed_vdd_io_v"])
    if position != "abort":
        if not math.isclose(float(scan_params.vdd_io.dc), fixed_vdd_io_v, abs_tol=1.0e-12):
            raise ValueError(
                f"VDD_IO is fixed at {fixed_vdd_io_v:g} V on {board_id}; "
                f"variant requests {float(scan_params.vdd_io.dc):g} V"
            )
        for rail, field in (("VDD_A", "vdd_a"), ("VDD_D", "vdd_d"), ("VDD_DAC", "vdd_dac")):
            requested_voltage_v = float(getattr(params, field).dc)
            if not minimum_supply_v <= requested_voltage_v <= maximum_supply_v:
                raise ValueError(
                    f"{rail} request {requested_voltage_v:g} V is outside {minimum_supply_v:g}..{maximum_supply_v:g} V"
                )

        vin_diff_v = float(params.vin_diff.dc)
        vin_cm_v = float(params.vin_cm.dc)
        minimum_input_v = -signal_headroom_v
        maximum_input_v = float(params.vdd_a.dc) + signal_headroom_v
        vin_p_v = vin_cm_v + vin_diff_v / 2.0
        vin_n_v = vin_cm_v - vin_diff_v / 2.0
        if not (
            minimum_input_v - 1.0e-12 <= vin_p_v <= maximum_input_v + 1.0e-12
            and minimum_input_v - 1.0e-12 <= vin_n_v <= maximum_input_v + 1.0e-12
        ):
            raise ValueError(
                f"ADC inputs {(vin_p_v, vin_n_v)} V are outside {minimum_input_v:g}..{maximum_input_v:g} V"
            )

    if position != "abort":
        select_fastrx_capture_settings(scan_params, board["fastrx_capture_settings"])

    if position in {"first", "only"}:
        run_dir.mkdir(parents=True, exist_ok=False)
    elif position != "abort" and not run_dir.is_dir():
        raise FileNotFoundError(2, "ADC scan run directory is not initialized", run_dir)

    from basil.dut import Dut

    map_path = Path(__file__).resolve().parent / "map_fpga.yaml"
    daq_dut = Dut(str(map_path))
    daq = None
    scope_dut = None
    scope = None
    initialized = False
    completed = False

    try:
        daq_dut.init()
        initialized = True
        daq = daq_dut

        if position != "abort":
            channels = scope_channels("seq_init", "seq_comp", "seq_logic", "comp_out")
            tracks = {f"{name}_v": channel for name, channel in channels.items()}
            scope_dut = Dut(str(map_path.with_name("map_scope.yaml")))
            scope_dut.init()
            scope = scope_dut["scope"]
            scope.set_acquire_state("STOP")
            scope.set_acquire_mode("SAMPLE")
            scope.set_acquire_stop_after("SEQUENCE")
            scope.set_horizontal_record_length(10_000)
            for channel in channels.values():
                scope._intf.write(f"DISplay:GLObal:CH{channel}:STATE ON")
                scope.set_coupling("DC", channel=channel)
                scope.set_vertical_scale(0.2, channel=channel)
                scope.set_vertical_position(0.0, channel=channel)
                scope.set_vertical_offset(0.0, channel=channel)
                scope.set_bandwidth(2.0e9, channel=channel)
            # COMP is quiet in the idle RAM word. A wrapped INIT word can
            # toggle repeatedly in the serializer while the sequencer is idle.
            scope._intf.write("TRIGger:B:STATE OFF")
            scope.set_trigger_type("EDGE")
            scope.set_trigger_source(channel=channels["seq_comp"])
            scope.set_trigger_edge_slope("RISE")
            scope.set_trigger_level(0.0, channel=channels["seq_comp"])
            scope.set_trigger_mode("NORMAL")
            variant_index = len(tuple(run_dir.glob("*.h5")))
            try:
                print(
                    f"\n=== {position} variant {variant_index + 1}: ADC {scan_params.observed_adc:02d}, "
                    f"{float(params.symbol_rate) / 1e6:g} MBd ==="
                )

                # Put every GPIO0 debug path in a known physical-capture state
                # before releasing the chip reset.
                daq["gpio0"]["RST_B"] = 0
                daq["gpio0"]["AMP_EN"] = 1
                daq["gpio0"]["RX_LOOPBACK"] = 0
                daq["gpio0"]["SPI_LOOPBACK"] = 0
                daq["gpio0"]["DBG_FIFO"] = 0
                daq["gpio0"]["RX_TIEHIGH"] = 0
                daq["gpio0"]["SEQ_START"] = 0
                daq["gpio0"]["RX_EN_MUX"] = 1
                daq["gpio0"].write()
                daq["gpio0"]["RST_B"] = 1
                daq["gpio0"].write()

                cap_weights = get_caparray_weights(params.dut.cdac)
                code_weights = convert_dac_caps_to_adc_weights(cap_weights)
                sequence_words = len(params.seq_init_pattern) // 8
                symbol_rate_bps = float(params.symbol_rate)
                capture_settings = select_fastrx_capture_settings(scan_params, board["fastrx_capture_settings"])
                rx_sen_start_word = capture_settings.rx_sen_start_word
                comp_idelay_taps = capture_settings.comp_delay_taps

                si570_frequency_hz, pll_divider_n = select_pll_configuration(symbol_rate_bps)
                sequencer_frequency_hz, serializer_frequency_hz = calculate_pll_frequency(
                    pll_divider_n,
                    input_frequency_hz=si570_frequency_hz,
                )
                daq["si570"].frequency_change(si570_frequency_hz / 1e6)
                sleep(SI570_SETTLE_S)
                set_pll_divider(daq["gpio2"], pll_divider_n)

                program_comp_delay(daq["gpio1"], comp_idelay_taps)

                sequencer_memory = build_fastrx_capture_pattern(
                    params,
                    rx_sen_start_word,
                    len(code_weights),
                )
                # Control rows start at INIT and are never rotated. Only a
                # wrapped RX_SEN mask can emit a leading partial receive frame.
                startup_conversions = 0
                startup_frames = int(rx_sen_start_word + len(code_weights) > sequence_words) + startup_conversions
                expected_frames = params.conversions + startup_frames
                daq["seq0"].set_en_ext_start(False)

                daq["fastrx0"].reset()
                daq["fastrx0"].set_en(False)
                data_size = int(daq["fastrx0"].get_size())
                if data_size != len(code_weights):
                    raise RuntimeError(
                        f"FastRX DATA_SIZE={data_size}, expected {len(code_weights)} from the configured CDAC"
                    )

                spi_bytes = convert_params_to_spi_fmt(scan_params)
                for _write_index in range(2):
                    daq["spi0"].set_data(list(spi_bytes))
                    daq["spi0"].set_size(180)
                    daq["spi0"].start()
                    daq["spi0"].wait_for_ready()

                raw_spi = bytes(daq["spi0"].get_data(size=23))
                readback_bits = bitarray()
                readback_bits.frombytes(raw_spi)
                expected_bits = bitarray()
                expected_bits.frombytes(spi_bytes)
                spi_mismatches = (expected_bits[:180][1:] ^ readback_bits[:180][1:]).count(1)
                if spi_mismatches:
                    raise RuntimeError(f"SPI configuration readback has {spi_mismatches} mismatches")

                expected_capture_s = (params.conversions + startup_frames + 1) * sequence_words * 8 / symbol_rate_bps
                capture_timeout_s = max(FASTRX_CAPTURE_TIMEOUT_S, 2.0 * expected_capture_s + 2.0)
                # Reset displays the last physical RAM word. Clear unused RAM
                # so it cannot enable RX before START on a short sequence.
                daq["fastrx0"].set_en(False)
                daq["seq0"].reset()
                sleep(0.001)
                daq["seq0"].set_data(bytes(daq["seq0"].get_mem_size()))
                daq["seq0"].set_data(sequencer_memory)
                daq["seq0"].set_size(sequence_words)
                daq["seq0"].set_clk_divide(1)
                daq["seq0"].set_wait(0)
                daq["seq0"].set_repeat_start(0)
                daq["seq0"].set_repeat(0)
                daq["seq0"].set_nested_repeat(0)
                daq["seq0"].set_en_ext_start(False)
                daq["fastrx0"].reset()
                sleep(FASTRX_TRAILING_DRAIN_S)
                daq["fifo0"]["RESET"]
                daq["fifo0"].get_data()

                # Arm before FPGA start; include startup and crop to DAQ conversion zero.
                conversion_period_s = len(params.seq_init_pattern) / symbol_rate_bps
                scope.set_horizontal_scale(3 * conversion_period_s / 8.0)
                scope._intf.write("HORizontal:POSition 10")
                scope.set_acquire_state("RUN")
                acquisition_count_before = wait_for_scope_armed(scope, timeout_s=5.0)

                deadline = monotonic() + capture_timeout_s
                daq["fastrx0"].set_en(True)
                daq["seq0"].start()
                try:
                    expected_fifo_bytes = 4 * expected_frames
                    while int(daq["fifo0"]["FIFO_SIZE"]) < expected_fifo_bytes:
                        if monotonic() >= deadline:
                            available_bytes = int(daq["fifo0"]["FIFO_SIZE"])
                            raise TimeoutError(
                                f"FastRX delivered {available_bytes // 4}/{expected_frames} words "
                                f"within {capture_timeout_s:g} s"
                            )
                        sleep(0.001)
                finally:
                    # Stop RX first: a high final RAM word must not generate
                    # bogus frames while the sequencer is stopped.
                    daq["fastrx0"].set_en(False)
                    daq["seq0"].reset()
                sleep(FASTRX_TRAILING_DRAIN_S)
                raw_data = daq["fifo0"].get_data()
                if len(raw_data) < expected_frames:
                    raise RuntimeError(f"expected at least {expected_frames} FastRX words, received {len(raw_data)}")
                wait_for_scope_capture(scope, acquisition_count_before, timeout_s=5.0)
                scope_waveforms = scope.get_waveforms({channel: name for name, channel in channels.items()})
                scope_wave = crop_adc_scope_conversion(
                    scope_records_to_adc_wave([scope_waveforms], [0], tracks),
                    skip_conversions=startup_conversions,
                    conversion_period_s=conversion_period_s,
                    symbol_period_s=1 / symbol_rate_bps,
                )
                fastrx_lost_count = int(daq["fastrx0"].get_lost_count())
                if fastrx_lost_count:
                    raise RuntimeError(f"FastRX lost {fastrx_lost_count} words during the continuous acquisition")

                conversion_index_values = np.arange(params.conversions, dtype=np.int64)
                vin_diff_values_v = np.full(params.conversions, float(params.vin_diff.dc))
                fastrx_words = np.asarray(raw_data, dtype=np.uint32)
                bout_values, dout_raw_values, dout_values = convert_fastrx_words_to_adc(
                    fastrx_words,
                    data_size,
                    code_weights,
                    params.dut.adc_bits,
                )
                # Keep exactly N complete conversions after validating every
                # received frame, including host-stop latency and startup frames.
                startup_words = {
                    f"startup_fastrx_word_{index}": int(word)
                    for index, word in enumerate(fastrx_words[:startup_frames])
                }
                received_frames = len(fastrx_words)
                fastrx_words = fastrx_words[startup_frames:expected_frames]
                bout_values = bout_values[startup_frames:expected_frames]
                dout_raw_values = dout_raw_values[startup_frames:expected_frames]
                dout_values = dout_values[startup_frames:expected_frames]
                frame_counter_modulus = 1 << (28 - data_size)
                for conversion_index in range(min(params.conversions, MAX_RAW_FASTRX_WORDS)):
                    word = int(fastrx_words[conversion_index])
                    identifier = (word >> 28) & 0xF
                    frame = (word >> data_size) & (frame_counter_modulus - 1)
                    spi_data = word & ((1 << data_size) - 1)
                    print(
                        f"[{conversion_index}] ID={identifier:04b} frame={frame} "
                        f"data={spi_data:0{data_size}b} Dout={int(dout_values[conversion_index])}"
                    )

                stem = f"{variant_index:04d}_capture"
                h5_path = run_dir / f"{stem}.h5"
                hostname = socket.gethostname()
                measurement = MeasAdcExt(
                    info=MeasInfo(
                        schema_version=1,
                        measurement_type="MeasAdcExt",
                        backend="physical",
                        timestamp_utc=datetime.now().astimezone(),
                        instruments={"controller": hostname, "scope": str(scope.get_name()).strip()},
                        readbacks={
                            "actual_sample_rate_hz": symbol_rate_bps / len(params.seq_init_pattern),
                            "repetition_rate_hz": symbol_rate_bps / len(params.seq_init_pattern),
                            "repetition_interval_s": len(params.seq_init_pattern) / symbol_rate_bps,
                            "nominal_conversion_rate_hz": symbol_rate_bps / 160,
                            "active_conversion_rate_hz": symbol_rate_bps
                            / AdcSequence.from_tb_params(params).conversion_symbols,
                            "si570_frequency_hz": si570_frequency_hz,
                            "pll_divider_n": pll_divider_n,
                            "sequencer_frequency_hz": sequencer_frequency_hz,
                            "serializer_frequency_hz": serializer_frequency_hz,
                            "rx_sen_start_word": rx_sen_start_word,
                            "comp_delay_taps": comp_idelay_taps,
                            "comp_delay_stages": 2,
                            "capture_control_phase_advance_symbols": 0,
                            "capture_expected_frames": expected_frames,
                            "capture_startup_conversions": startup_conversions,
                            "capture_received_frames": received_frames,
                            "capture_startup_frames": startup_frames,
                            **startup_words,
                            "spi_mismatches": spi_mismatches,
                            "fastrx_lost_count": fastrx_lost_count,
                            "controller_hostname": hostname,
                            "peripheral_control": "manual",
                            "scope_waveform_captured": True,
                            "scope_startup_conversions_skipped": startup_conversions,
                            "scope_comp_out_delay_s": board["scope_comp_out_delay_s"],
                            "scope_trigger_signal": "seq_comp",
                            "scope_trigger_edge": "rise",
                            "scope_record_length_requested": 10_000,
                            "stimulus_kind": "dc",
                            "stimulus_vin_diff_v": float(params.vin_diff.dc),
                            "stimulus_control": "manual",
                        },
                    ),
                    param=scan_params,
                    daq=AdcDaq(
                        conversion_index=conversion_index_values,
                        bout=bout_values,
                        dout_raw=dout_raw_values,
                        dout=dout_values,
                        vin_diff_v=vin_diff_values_v,
                        fastrx_word=fastrx_words,
                    ),
                    wave=scope_wave,
                )
                try:
                    comparison = analyze_scope_wave_to_bits(measurement)
                    scope_readbacks = {
                        "scope_fastrx_comparison_valid": True,
                        "scope_fastrx_bit_mismatches": comparison.mismatch_count,
                    }
                except ValueError as error:
                    # Preserve failed/stuck timing cases rather than silently treating
                    # an undecodable scope record as a zero-mismatch comparison.
                    scope_readbacks = {
                        "scope_fastrx_comparison_valid": False,
                        "scope_fastrx_comparison_error": str(error),
                    }
                measurement = replace(
                    measurement,
                    info=replace(measurement.info, readbacks=measurement.info.readbacks | scope_readbacks),
                )
                write_measurement(h5_path, measurement)
                print(f"Saved {params.conversions} conversions and one scope record to {h5_path}")
            except Exception:
                print(f"Variant {variant_index + 1} failed; shutting down the FPGA")
                raise

        completed = True
    finally:
        should_shutdown = position in {"last", "only", "abort"} or not completed
        if should_shutdown and daq is not None:
            try:
                daq["fastrx0"].set_en(False)
                daq["seq0"].reset()
                daq["gpio0"]["RST_B"] = 0
                daq["gpio0"]["AMP_EN"] = 0
                daq["gpio0"]["RX_LOOPBACK"] = 0
                daq["gpio0"]["SPI_LOOPBACK"] = 0
                daq["gpio0"]["DBG_FIFO"] = 0
                daq["gpio0"]["RX_TIEHIGH"] = 0
                daq["gpio0"]["SEQ_START"] = 0
                daq["gpio0"]["RX_EN_MUX"] = 0
                daq["gpio0"].write()
                daq["si570"].frequency_change(200.0)
                sleep(SI570_SETTLE_S)
                set_pll_divider(daq["gpio2"], 2)
            except Exception as error:  # noqa: BLE001 - best-effort safety shutdown
                print(f"Warning: could not restore the default FPGA clock: {error}")
        try:
            if scope is not None:
                scope.set_acquire_state("STOP")
        finally:
            try:
                if scope_dut is not None:
                    scope_dut.close()
            finally:
                if initialized:
                    daq_dut.close()
    return run_dir
