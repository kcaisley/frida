"""Acquire ADC data through the FPGA without controlling laboratory peripherals."""

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

from flow.analysis.io import write_measurement
from flow.analysis.types import AdcDaq, MeasAdcExt, MeasInfo
from flow.cdac import get_cdac_weights
from flow.scans.fastrx import calculate_fastrx_capture_alignment, convert_fastrx_words_to_adc
from flow.scans.params import AdcScanParams, load_board_map, validate_params
from flow.scans.plldrp import calculate_pll_frequency, select_pll_configuration, set_pll_divider
from flow.scans.scan_adc import convert_dac_caps_to_adc_weights, convert_params_to_spi_fmt
from flow.scans.seqgen import convert_params_to_seqgen_fmt


def scan(
    params: AdcScanParams,
    *,
    run_dir: Path,
    position: Literal["first", "middle", "last", "only", "abort"],
) -> Path:
    """Acquire one fixed-input ADC point using only the FPGA/BDAQ interface."""

    SI570_SETTLE_S = 0.02
    FASTRX_CAPTURE_TIMEOUT_S = 5.0
    FASTRX_TRAILING_DRAIN_S = 0.01
    MAX_RAW_FASTRX_WORDS = 20

    if position not in {"first", "middle", "last", "only", "abort"}:
        raise ValueError(f"unknown ADC scan lifecycle position {position!r}")
    if position != "abort":
        validate_params(params)
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

    if position in {"first", "only"}:
        run_dir.mkdir(parents=True, exist_ok=False)
    elif position != "abort" and not run_dir.is_dir():
        raise FileNotFoundError(2, "ADC scan run directory is not initialized", run_dir)

    from basil.dut import Dut

    map_path = Path(__file__).resolve().parent / "map_fpga.yaml"
    daq_dut = Dut(str(map_path))
    daq = None
    initialized = False
    completed = False

    try:
        daq_dut.init()
        initialized = True
        daq = daq_dut

        if position != "abort":
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

                symbol_rate_bps = float(params.symbol_rate)
                capture_alignment = calculate_fastrx_capture_alignment(
                    params,
                    **board["capture_timing_model"],
                )
                phase_advance = capture_alignment.control_phase_advance_symbols
                if phase_advance:
                    params = replace(
                        params,
                        seq_init_phase_delay_symbols=float(params.seq_init_phase_delay_symbols) - phase_advance,
                        seq_samp_phase_delay_symbols=float(params.seq_samp_phase_delay_symbols) - phase_advance,
                        seq_comp_phase_delay_symbols=float(params.seq_comp_phase_delay_symbols) - phase_advance,
                        seq_logic_phase_delay_symbols=float(params.seq_logic_phase_delay_symbols) - phase_advance,
                    )
                    scan_params = replace(scan_params, tb=params)
                    validate_params(scan_params)
                rx_sen_start_word = capture_alignment.rx_sen_start_word
                comp_idelay_taps = capture_alignment.comp_idelay_taps

                si570_frequency_hz, pll_divider_n = select_pll_configuration(symbol_rate_bps)
                sequencer_frequency_hz, serializer_frequency_hz = calculate_pll_frequency(
                    pll_divider_n,
                    input_frequency_hz=si570_frequency_hz,
                )
                daq["si570"].frequency_change(si570_frequency_hz / 1e6)
                sleep(SI570_SETTLE_S)
                set_pll_divider(daq["gpio2"], pll_divider_n)

                if not 0 <= comp_idelay_taps <= 31:
                    raise ValueError(f"COMP IDELAY taps must be in 0..31, got {comp_idelay_taps}")
                daq["gpio1"].read()
                if not daq["gpio1"]["COMP_IDELAY_RDY"].tovalue():
                    raise RuntimeError("comparator IDELAYCTRL is not ready")
                daq["gpio1"]["COMP_IDELAY_TAPS"] = comp_idelay_taps
                daq["gpio1"]["COMP_IDELAY_LOAD"] = 1
                daq["gpio1"].write()
                daq["gpio1"]["COMP_IDELAY_LOAD"] = 0
                daq["gpio1"].write()

                cap_weights = get_cdac_weights(params.dut.cdac)
                code_weights = convert_dac_caps_to_adc_weights(cap_weights)
                sequence_words = len(params.seq_init_pattern) // 8
                rx_sen_stop_word = rx_sen_start_word + len(code_weights)
                rx_sen_pattern = (
                    "0" * rx_sen_start_word + "1" * len(code_weights) + "0" * (sequence_words - rx_sen_stop_word)
                )
                sequencer_memory = convert_params_to_seqgen_fmt(params, rx_sen_pattern)
                daq["seq0"].set_data(sequencer_memory)
                daq["seq0"].set_size(sequence_words)
                daq["seq0"].set_clk_divide(1)
                daq["seq0"].set_en_ext_start(False)

                daq["fastrx0"].reset()
                daq["fastrx0"].set_en(True)
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

                expected_capture_s = params.conversions * len(params.seq_init_pattern) / symbol_rate_bps
                capture_timeout_s = max(FASTRX_CAPTURE_TIMEOUT_S, 2.0 * expected_capture_s + 2.0)
                daq["seq0"].reset()
                daq["fastrx0"].reset()
                sleep(0.001)
                daq["seq0"].set_size(sequence_words)
                daq["seq0"].set_clk_divide(1)
                daq["seq0"].set_repeat(params.conversions)
                daq["seq0"].set_en_ext_start(False)
                daq["fastrx0"].set_en(True)
                daq["fifo0"]["RESET"]
                daq["fifo0"].get_data()

                deadline = monotonic() + capture_timeout_s
                daq["seq0"].start()
                while not daq["seq0"].is_done():
                    if monotonic() >= deadline:
                        raise TimeoutError(
                            f"sequencer did not finish {params.conversions} conversions within {capture_timeout_s:g} s"
                        )
                    sleep(0.001)

                expected_fifo_bytes = 4 * params.conversions
                while int(daq["fifo0"]["FIFO_SIZE"]) < expected_fifo_bytes:
                    if monotonic() >= deadline:
                        available_bytes = int(daq["fifo0"]["FIFO_SIZE"])
                        raise TimeoutError(
                            f"FastRX delivered {available_bytes // 4}/{params.conversions} words "
                            f"within {capture_timeout_s:g} s"
                        )
                    sleep(0.001)

                sleep(FASTRX_TRAILING_DRAIN_S)
                raw_data = daq["fifo0"].get_data()
                if len(raw_data) != params.conversions:
                    raise RuntimeError(f"expected {params.conversions} FastRX words, received {len(raw_data)}")
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

                all_patterns = (
                    params.seq_init_pattern,
                    params.seq_samp_pattern,
                    params.seq_comp_pattern,
                    params.seq_logic_pattern,
                )
                active_indices = [
                    index
                    for index in range(len(params.seq_init_pattern))
                    if any(pattern[index] == "1" for pattern in all_patterns)
                ]
                active_span_symbols = active_indices[-1] - active_indices[0] + 1
                source_label = f"dc{float(params.vin_diff.dc) * 1e3:+.0f}mv".replace("+", "p").replace("-", "m")
                logic_comp_offset = float(params.seq_logic_phase_delay_symbols) - float(
                    params.seq_comp_phase_delay_symbols
                )
                logic_phase_label = f"{logic_comp_offset:+g}".replace("+", "p").replace("-", "m")
                stem = (
                    f"{variant_index:04d}_{board_id}_adc{scan_params.observed_adc:02d}_"
                    f"{float(params.symbol_rate) / 1e6:g}mbd_{source_label}_"
                    f"logic{logic_phase_label}sym_"
                    f"vcm{float(params.vin_cm.dc) * 1e3:g}mv_"
                    f"vdda{float(params.vdd_a.dc) * 1e3:g}mv_"
                    f"vddd{float(params.vdd_d.dc) * 1e3:g}mv_"
                    f"vddac{float(params.vdd_dac.dc) * 1e3:g}mv_"
                    f"t{float(scan_params.temperature_c):g}c"
                )
                h5_path = run_dir / f"{stem}.h5"
                hostname = socket.gethostname()
                measurement = MeasAdcExt(
                    info=MeasInfo(
                        schema_version=1,
                        measurement_type="MeasAdcExt",
                        backend="physical",
                        timestamp_utc=datetime.now().astimezone(),
                        instruments={"controller": hostname},
                        readbacks={
                            "actual_sample_rate_hz": symbol_rate_bps / len(params.seq_init_pattern),
                            "active_conversion_rate_hz": symbol_rate_bps / active_span_symbols,
                            "si570_frequency_hz": si570_frequency_hz,
                            "pll_divider_n": pll_divider_n,
                            "sequencer_frequency_hz": sequencer_frequency_hz,
                            "serializer_frequency_hz": serializer_frequency_hz,
                            "rx_sen_start_word": rx_sen_start_word,
                            "comp_idelay_taps": comp_idelay_taps,
                            "capture_control_phase_advance_symbols": phase_advance,
                            "capture_earliest_data_arrival_s": capture_alignment.earliest_data_arrival_s,
                            "capture_latest_data_arrival_s": capture_alignment.latest_data_arrival_s,
                            "capture_edge_s": capture_alignment.capture_edge_s,
                            "capture_setup_margin_s": capture_alignment.setup_margin_s,
                            "capture_hold_margin_s": capture_alignment.hold_margin_s,
                            "spi_mismatches": spi_mismatches,
                            "fastrx_lost_count": fastrx_lost_count,
                            "controller_hostname": hostname,
                            "peripheral_control": "manual",
                            "scope_waveform_captured": False,
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
                    wave=None,
                )
                write_measurement(h5_path, measurement)
                print(f"Saved {params.conversions} conversions and no scope record to {h5_path}")
            except Exception:
                print(f"Variant {variant_index + 1} failed; shutting down the FPGA")
                raise

        completed = True
    finally:
        should_shutdown = position in {"last", "only", "abort"} or not completed
        if should_shutdown and daq is not None:
            try:
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
        if initialized:
            daq_dut.close()
    return run_dir
