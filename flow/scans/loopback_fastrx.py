"""Compare physical comparator decisions against the FastRX 17-bit capture.

ADC01 converts a fixed +50 mV differential input at 0.8 V common mode. The
default run tests 80--1600 MBd in 40 MBd steps and LOGIC phase offsets -3..+3.
For each point the analytical capture equation selects RX_SEN and IDELAY,
FastRX records repeated conversions, and the scope records:

    CH1 ADC differential input
    CH2 COMP
    CH3 LOGIC
    CH4 COMP_OUT

The first 17 scope decisions are compared bit-for-bit with the first FastRX
word. Every scope waveform, ADC conversion record, and noise histogram is
saved under a new timestamped ``build/loopback_fastrx`` directory.

Run one quick point before the complete 273-point campaign:

    uv run python -m flow.scans.loopback_fastrx --smoke

Run the complete campaign:

    uv run python -m flow.scans.loopback_fastrx
"""

from __future__ import annotations

import argparse
import csv
import dataclasses
import json
import math
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from statistics import fmean, pstdev
from time import monotonic, sleep
from typing import Any

import hdl21 as h
import numpy as np
from bitarray import bitarray

from basil.HL.tektronix_oscilloscope import response_value
from flow.adc import AdcParams
from flow.cdac import CdacParams, RedunStrat, get_cdac_weights
from flow.analysis.measure import analyze_crossings
from flow.analysis.adc import analyze_adc_distribution
from flow.analysis.models import (
    AdcConversion,
    AdcSettings,
    AnalysisKind,
    AnalysisRequest,
    AnalysisSpec,
    BackendKind,
    BlockKind,
    PlotKind,
    PlotRequest,
    PlotSpec,
    SourceFormat,
    SourceSpec,
    WaveformSettings,
)
from flow.scans.params import AdcTbParams, load_board_map, validate_params
from flow.scans.plldrp import calculate_pll_frequency, select_pll_configuration, set_pll_divider
from flow.analysis.plot import render_plot
from flow.analysis.io import (
    read_run,
    to_json_data,
)
from flow.scans.results import write_adc_conversions
from flow.scans.scan_adc import (
    calculate_fastrx_capture_alignment,
    convert_dac_caps_to_adc_weights,
    convert_dout_to_normalized_dout,
    convert_fastrx_to_bout_and_dout,
    convert_params_to_seqgen_fmt,
    convert_params_to_spi_fmt,
    convert_vdiff_input_to_awg_supply,
)
from flow.scans.scope import (
    wait_for_scope_armed,
    wait_for_scope_capture,
    write_scope_csv,
)

MAP_DIR = Path(__file__).resolve().parent
OUT_DIR = Path(__file__).resolve().parents[2] / "build" / "loopback_fastrx"

BOARD_ID = "frida65a_001"
ADC_INDEX = 1
VIN_DIFF_V = 0.050
VIN_CM_V = 0.800
VDD_V = 1.200
SMU_VOLTAGE_RANGE_V = 2.0
SMU_CURRENT_COMPLIANCE_A = 500.0e-6
VIN_CM_CURRENT_LIMIT_A = 10.0e-3

DEFAULT_SYMBOL_RATES_BPS = tuple(rate_mbd * 1.0e6 for rate_mbd in range(80, 1601, 40))
DEFAULT_LOGIC_OFFSETS = (-3, -2, -1, 0, 1, 2, 3)
DEFAULT_CONVERSIONS = 1_000
SMOKE_SYMBOL_RATE_BPS = 800.0e6
SMOKE_LOGIC_OFFSET = 0
SMOKE_CONVERSIONS = 100

SCOPE_TRACKS = {
    1: "adc_vdiff",
    2: "seq_comp",
    3: "seq_logic",
    4: "comp_out",
}
SCOPE_TRIGGER_CHANNEL = 3
SCOPE_RECORD_LENGTH = 10_000
SCOPE_BANDWIDTH_HZ = 2.0e9
SCOPE_VERTICAL_SCALE_V = 0.2
SCOPE_CAPTURE_TIMEOUT_S = 5.0
SCOPE_DOWNLOAD_SETTLE_S = 0.1
SCOPE_COMP_OUT_INVERTED = True
# Sample immediately before the next COMP decision. At 1.6 GBd, 90% of the
# 5 ns decision interval was too early for the slowest physical COMP_OUT
# transitions; 98% reproduced all 140 saved scope/FastRX decision vectors.
# This fraction is used only for offline scope decoding. FPGA capture timing is
# selected independently by calculate_fastrx_capture_alignment().
SCOPE_DECISION_SAMPLE_FRACTION = 0.98

SETUP_SETTLE_S = 0.2
SMU_SETTLE_S = 0.5
SI570_SETTLE_S = 0.02
FASTRX_TIMEOUT_S = 5.0
FASTRX_TRAILING_DRAIN_S = 0.01


@dataclass(frozen=True, slots=True)
class ScopeDecisionVector:
    """Seventeen comparator decisions extracted from one scope acquisition."""

    bits: str
    comp_threshold_v: float
    comp_out_threshold_v: float
    comp_edge_times_s: tuple[float, ...]
    sample_times_s: tuple[float, ...]
    sample_values_v: tuple[float, ...]


def extract_scope_decisions(
    times_s: np.ndarray,
    comp_v: np.ndarray,
    comp_out_v: np.ndarray,
    *,
    symbol_rate_bps: float,
    decision_count: int,
    output_inverted: bool,
) -> ScopeDecisionVector:
    """Extract one logical bit after each of the first COMP falling edges."""

    if times_s.ndim != 1 or comp_v.shape != times_s.shape or comp_out_v.shape != times_s.shape:
        raise ValueError("scope time, COMP, and COMP_OUT arrays must be one-dimensional and equal length")
    if decision_count <= 0:
        raise ValueError("decision_count must be positive")
    if len(times_s) < 2 or not np.all(np.diff(times_s) > 0.0):
        raise ValueError("scope time values must increase strictly")

    comp_low_v, comp_high_v = np.percentile(comp_v, (1.0, 99.0))
    comp_out_low_v, comp_out_high_v = np.percentile(comp_out_v, (1.0, 99.0))
    comp_threshold_v = float((comp_low_v + comp_high_v) / 2.0)
    comp_out_threshold_v = float((comp_out_low_v + comp_out_high_v) / 2.0)
    if comp_high_v - comp_low_v < 0.1:
        raise ValueError("scope COMP waveform does not have a valid logic swing")
    if comp_out_high_v - comp_out_low_v < 0.1:
        raise ValueError("scope COMP_OUT waveform does not have a valid logic swing")

    scope_run = read_run(
        SourceSpec(
            "scope_decision_vector",
            BackendKind.MEASUREMENT,
            BlockKind.GENERIC,
            SourceFormat.COLUMN_MAPPING,
            {"time_s": times_s, "seq_comp_v": comp_v},
            table_name="waveforms",
        )
    )
    crossing_result = analyze_crossings(
        AnalysisRequest(
            AnalysisSpec(
                "comp_falling_edges",
                AnalysisKind.CROSSINGS,
                (scope_run.run_id,),
                WaveformSettings(
                    signal_columns=("seq_comp_v",),
                    thresholds=(comp_threshold_v,),
                    rising=False,
                ),
            ),
            runs=(scope_run,),
        )
    )
    falling_edges_s = tuple(
        float(edge_s) for edge_s in crossing_result.table("crossings").column("crossing_axis") if edge_s >= 0.0
    )
    if len(falling_edges_s) < decision_count:
        raise ValueError(
            f"scope contains only {len(falling_edges_s)} COMP falling edges after the trigger; "
            f"expected at least {decision_count}"
        )
    comp_edge_times_s = falling_edges_s[:decision_count]

    sequencer_period_s = 8.0 / symbol_rate_bps
    sample_times_s = tuple(edge_s + SCOPE_DECISION_SAMPLE_FRACTION * sequencer_period_s for edge_s in comp_edge_times_s)
    if sample_times_s[-1] > times_s[-1]:
        raise ValueError("scope record ends before the final comparator decision sample")

    averaging_half_width_s = min(0.05 * sequencer_period_s, 0.25e-9)
    sample_values_v = []
    for sample_time_s in sample_times_s:
        selected = np.abs(times_s - sample_time_s) <= averaging_half_width_s
        if np.any(selected):
            sample_values_v.append(float(np.median(comp_out_v[selected])))
        else:
            sample_values_v.append(float(np.interp(sample_time_s, times_s, comp_out_v)))

    physical_bits = "".join("1" if sample_v > comp_out_threshold_v else "0" for sample_v in sample_values_v)
    bits = "".join("1" if bit == "0" else "0" for bit in physical_bits) if output_inverted else physical_bits
    return ScopeDecisionVector(
        bits=bits,
        comp_threshold_v=comp_threshold_v,
        comp_out_threshold_v=comp_out_threshold_v,
        comp_edge_times_s=comp_edge_times_s,
        sample_times_s=sample_times_s,
        sample_values_v=tuple(sample_values_v),
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--smoke",
        action="store_true",
        help="run only 800 MBd, LOGIC offset zero, and 100 conversions",
    )
    parser.add_argument(
        "--symbol-rates-mbd",
        type=float,
        nargs="+",
        help="diagnostic symbol-rate subset in MBd; cannot be combined with --smoke",
    )
    parser.add_argument(
        "--logic-offsets",
        type=int,
        nargs="+",
        help="diagnostic LOGIC-offset subset; cannot be combined with --smoke",
    )
    parser.add_argument(
        "--conversions",
        type=int,
        help="diagnostic conversions per point; defaults to 100 for --smoke or 1000",
    )
    args = parser.parse_args()
    if args.smoke and (args.symbol_rates_mbd or args.logic_offsets):
        parser.error("--smoke cannot be combined with explicit rates or LOGIC offsets")
    if args.conversions is not None and args.conversions <= 0:
        parser.error("--conversions must be positive")

    symbol_rates_bps = (
        (SMOKE_SYMBOL_RATE_BPS,)
        if args.smoke
        else (
            tuple(rate_mbd * 1.0e6 for rate_mbd in args.symbol_rates_mbd)
            if args.symbol_rates_mbd
            else DEFAULT_SYMBOL_RATES_BPS
        )
    )
    logic_offsets = (
        (SMOKE_LOGIC_OFFSET,)
        if args.smoke
        else (tuple(args.logic_offsets) if args.logic_offsets else DEFAULT_LOGIC_OFFSETS)
    )
    conversions = (
        args.conversions if args.conversions is not None else (SMOKE_CONVERSIONS if args.smoke else DEFAULT_CONVERSIONS)
    )
    board_map = load_board_map()
    board = board_map["boards"][BOARD_ID]
    timing_model = board["capture_timing_model"]
    flavor_name = board["adc_channels"][ADC_INDEX]
    cap_weights = tuple(board_map["adc_flavors"][flavor_name]["cdac_weights"])
    dut_params = AdcParams(
        adc_bits=12,
        n_cycles=16,
        cdac=CdacParams(
            n_dac=11,
            n_extra=5,
            redun_strat=RedunStrat.SUBRDX2_OVLY,
            weights=cap_weights,
        ),
    )
    active_adc_mask = tuple(int(index == ADC_INDEX) for index in reversed(range(16)))
    base_params = AdcTbParams(
        dut=dut_params,
        board_id=BOARD_ID,
        observed_adc=ADC_INDEX,
        active_adc_mask=active_adc_mask,
        conversions=conversions,
        vin_cm=h.Vdc.Params(dc=VIN_CM_V),
        vin_diff=h.Vdc.Params(dc=VIN_DIFF_V),
    )

    maximum_supply_v = float(board["supply_limits"]["maximum_voltage_v"])
    if not 0.0 < VDD_V <= maximum_supply_v:
        raise ValueError(f"VDD={VDD_V:g} V exceeds the board limit {maximum_supply_v:g} V")
    if abs(VIN_DIFF_V) > float(board["input_calibration"]["maximum_abs_vdiff_v"]):
        raise ValueError("requested differential input exceeds the calibrated range")
    if VIN_CM_V + abs(VIN_DIFF_V) / 2.0 > maximum_supply_v:
        raise ValueError("requested ADC positive input exceeds the 1.2 V rail")
    if VIN_CM_V - abs(VIN_DIFF_V) / 2.0 < 0.0:
        raise ValueError("requested ADC negative input is below ground")

    awg_voltage_v, vin_cm_supply_v = convert_vdiff_input_to_awg_supply(
        VIN_DIFF_V,
        VIN_CM_V,
        board["input_calibration"],
    )
    if not 0.0 <= vin_cm_supply_v <= maximum_supply_v:
        raise ValueError("calibrated Vin_cm supply request is outside 0..1.2 V")

    run_timestamp = datetime.now().astimezone().strftime("%Y%m%d_%H%M%S")
    run_dir = OUT_DIR / run_timestamp
    run_dir.mkdir(parents=True, exist_ok=False)
    summary_path = run_dir / "summary.csv"
    manifest_path = run_dir / "manifest.json"
    print(f"Saving {len(symbol_rates_bps) * len(logic_offsets)} capture points to {run_dir}")

    from gpib_ctypes import make_default_gpib

    make_default_gpib()
    from basil.dut import Dut

    daq_dut = Dut(str(MAP_DIR / "map_fpga.yaml"))
    awg_dut = Dut(str(MAP_DIR / "map_awg.yaml"))
    vin_cm_dut = Dut(str(MAP_DIR / "map_supply.yaml"))
    smu_dut = Dut(str(MAP_DIR / "map_smu.yaml"))
    scope_dut = Dut(str(MAP_DIR / "map_scope.yaml"))
    initialized_duts = []
    daq = awg = vin_cm_supply = scope = None
    smus: list[tuple[Any, str]] = []
    scope_state: dict[str, Any] | None = None
    summary_rows: list[dict[str, Any]] = []

    try:
        for instrument_dut in (
            daq_dut,
            awg_dut,
            vin_cm_dut,
            smu_dut,
            scope_dut,
        ):
            instrument_dut.init()
            initialized_duts.append(instrument_dut)

        daq = daq_dut
        awg = awg_dut["awg"]
        vin_cm_supply = vin_cm_dut["vocm_supply"]
        scope = scope_dut["scope"]
        smus = [
            (smu_dut["smu1"], "VDD_A"),
            (smu_dut["smu2"], "VDD_D"),
            (smu_dut["smu3"], "VDD_DAC"),
        ]

        # Make every stimulus safe before changing ranges or setpoints.
        awg.set_DC("DEF,DEF,0")
        awg.set_enable(0)
        vin_cm_supply.set_enable(0)
        vin_cm_supply.set_voltage(0.0)
        for smu, _rail in smus:
            smu.off()
            smu.set_voltage(0.0)

        # Configure and enable all three 1.2 V chip domains back-to-back.
        for smu, rail in smus:
            smu.source_volt()
            smu.four_wire_off()
            smu.set_voltage_range(SMU_VOLTAGE_RANGE_V)
            smu.set_current_limit(SMU_CURRENT_COMPLIANCE_A)
            smu.current_sense_autorange_on()
            smu.set_current_nplc(10.0)
            smu.autozero_on()
            smu.set_voltage(VDD_V)
            if float(smu.get_source_voltage()) > VDD_V:
                raise RuntimeError(f"{rail}: unsafe voltage setpoint readback")
            if float(smu.get_current_limit()) > SMU_CURRENT_COMPLIANCE_A:
                raise RuntimeError(f"{rail}: unsafe current-compliance readback")
        for smu, _rail in smus:
            smu.on()
        sleep(SMU_SETTLE_S)
        for smu, rail in smus:
            measured_voltage_v = float(smu.get_voltage())
            measured_current_a = float(smu.get_current())
            print(f"{rail}: {measured_voltage_v:.6f} V, {measured_current_a * 1e6:.3f} uA")
            if not 1.15 <= measured_voltage_v <= VDD_V + 5.0e-3:
                raise RuntimeError(f"{rail}: unsafe or compliance-limited voltage {measured_voltage_v:g} V")

        # Apply the fixed, calibrated differential input and common mode.
        vin_cm_supply.set_voltage_range("P25V")
        vin_cm_supply.set_current_limit(VIN_CM_CURRENT_LIMIT_A)
        vin_cm_supply.set_voltage(vin_cm_supply_v)
        vin_cm_supply.set_enable(1)
        awg.set_output_load("INFinity")
        awg.set_DC(f"DEF,DEF,{awg_voltage_v}")
        awg.set_enable(1)
        sleep(SETUP_SETTLE_S)
        print(
            f"Stimulus: target Vdiff={VIN_DIFF_V:g} V, Vin_cm={VIN_CM_V:g} V; "
            f"AWG={awg_voltage_v:.6f} V, Vin_cm supply={vin_cm_supply_v:.6f} V"
        )

        # Select the physical ADC comparator and sequencer-controlled RX_SEN.
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

        # Program and verify ADC01 once; only FPGA timing changes in the sweep.
        spi_bytes = convert_params_to_spi_fmt(base_params)
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

        # Preserve scope acquisition state. Per-channel settings are
        # intentionally left in the agreed 2 GHz, 200 mV/div, zero-offset form.
        scope_state = {
            "acquire_state": response_value(scope.get_acquire_state()),
            "acquire_stop_after": response_value(scope.get_acquire_stop_after()),
            "acquire_mode": response_value(scope.get_acquire_mode()),
            "horizontal_scale": response_value(scope.get_horizontal_scale()),
            "horizontal_record_length": response_value(scope.get_horizontal_record_length()),
            "horizontal_position": response_value(scope._intf.query("HORizontal:POSition?")),
            "trigger_mode": response_value(scope.get_trigger_mode()),
            "trigger_type": response_value(scope.get_trigger_type()),
            "trigger_source": response_value(scope.get_triggr_source()),
            "trigger_slope": response_value(scope.get_trigger_edge_slope()),
            "trigger_level": response_value(scope.get_trigger_level(channel=SCOPE_TRIGGER_CHANNEL)),
            "display": {
                channel: response_value(scope._intf.query(f"DISplay:GLObal:CH{channel}:STATE?"))
                for channel in SCOPE_TRACKS
            },
        }
        scope.set_acquire_state("STOP")
        scope.set_acquire_mode("SAMPLE")
        scope.set_acquire_stop_after("SEQUENCE")
        scope.set_horizontal_record_length(SCOPE_RECORD_LENGTH)
        for channel in SCOPE_TRACKS:
            scope._intf.write(f"DISplay:GLObal:CH{channel}:STATE ON")
            scope.set_coupling("DC", channel=channel)
            scope.set_vertical_scale(SCOPE_VERTICAL_SCALE_V, channel=channel)
            scope.set_vertical_position(0.0, channel=channel)
            scope.set_vertical_offset(0.0, channel=channel)
            scope.set_bandwidth(SCOPE_BANDWIDTH_HZ, channel=channel)
        scope.set_trigger_type("EDGE")
        scope.set_trigger_source(channel=SCOPE_TRIGGER_CHANNEL)
        scope.set_trigger_edge_slope("RISE")
        scope.set_trigger_level(0.0, channel=SCOPE_TRIGGER_CHANNEL)
        scope.set_trigger_mode("NORMAL")

        cap_weights = get_cdac_weights(base_params.dut.cdac)
        code_weights = convert_dac_caps_to_adc_weights(cap_weights)
        data_size = int(daq["fastrx0"].get_size())
        if data_size != len(code_weights):
            raise RuntimeError(f"FastRX DATA_SIZE={data_size}, expected {len(code_weights)}")
        sequence_words = len(base_params.seq_init_pattern) // 8

        for point_index, (symbol_rate_bps, logic_offset) in enumerate(
            ((symbol_rate_bps, logic_offset) for logic_offset in logic_offsets for symbol_rate_bps in symbol_rates_bps),
            start=1,
        ):
            params = dataclasses.replace(
                base_params,
                symbol_rate=symbol_rate_bps,
                seq_logic_phase_delay_symbols=logic_offset,
            )
            validate_params(params)
            alignment = calculate_fastrx_capture_alignment(
                params,
                **timing_model,
            )
            rx_sen_start_word = alignment.rx_sen_start_word
            comp_idelay_taps = alignment.comp_idelay_taps
            sequencer_memory = convert_params_to_seqgen_fmt(
                params,
                rx_sen_start_word,
            )

            si570_frequency_hz, pll_divider_n = select_pll_configuration(symbol_rate_bps)
            sequencer_frequency_hz, serializer_frequency_hz = calculate_pll_frequency(
                pll_divider_n,
                input_frequency_hz=si570_frequency_hz,
            )
            actual_symbol_rate_bps = 2.0 * serializer_frequency_hz
            if not math.isclose(actual_symbol_rate_bps, symbol_rate_bps, rel_tol=1e-12):
                raise RuntimeError("PLL selection did not reproduce the requested symbol rate")

            print(
                f"\n[{point_index}/{len(symbol_rates_bps) * len(logic_offsets)}] "
                f"{symbol_rate_bps / 1e6:g} MBd, LOGIC {logic_offset:+d}: "
                f"RX_SEN={rx_sen_start_word}, tap={comp_idelay_taps}, "
                f"predicted setup={alignment.setup_margin_s * 1e9:.3f} ns, "
                f"hold={alignment.hold_margin_s * 1e9:.3f} ns"
            )

            daq["si570"].frequency_change(si570_frequency_hz / 1e6)
            sleep(SI570_SETTLE_S)
            set_pll_divider(daq["gpio2"], pll_divider_n)

            # Program comparator IDELAY through the GPIO1 transaction exercised
            # independently by test_gpio.py.
            daq["gpio1"].read()
            if not daq["gpio1"]["COMP_IDELAY_RDY"].tovalue():
                raise RuntimeError("comparator IDELAYCTRL is not ready")
            daq["gpio1"]["COMP_IDELAY_TAPS"] = comp_idelay_taps
            daq["gpio1"]["COMP_IDELAY_LOAD"] = 1
            daq["gpio1"].write()
            daq["gpio1"]["COMP_IDELAY_LOAD"] = 0
            daq["gpio1"].write()

            # Program the 64-bit sequencer memory with the same public Basil
            # calls exercised by test_seqgen.py.
            daq["seq0"].reset()
            daq["fastrx0"].reset()
            sleep(0.001)
            daq["seq0"].set_data(sequencer_memory)
            daq["seq0"].set_size(sequence_words)
            daq["seq0"].set_clk_divide(1)
            daq["seq0"].set_repeat(conversions)
            daq["seq0"].set_en_ext_start(False)
            daq["fastrx0"].set_en(True)
            daq["fifo0"]["RESET"]
            daq["fifo0"].get_data()

            sequence_period_s = len(params.seq_init_pattern) / symbol_rate_bps
            scope.set_acquire_state("STOP")
            # Request about two complete patterns across the ten horizontal
            # divisions. This leaves margin for the scope's discrete timebase
            # rounding at rates such as 240 MBd.
            scope.set_horizontal_scale(sequence_period_s / 5.0)
            actual_horizontal_scale_s = float(response_value(scope.get_horizontal_scale()))
            horizontal_divisions = float(response_value(scope.get_horizontal_divisions()))
            record_span_s = actual_horizontal_scale_s * horizontal_divisions
            post_trigger_s = 1.02 * sequence_period_s
            if post_trigger_s >= record_span_s:
                raise RuntimeError(
                    f"scope span {record_span_s:g} s does not cover one sequence ({sequence_period_s:g} s)"
                )
            horizontal_position_percent = 100.0 * (1.0 - post_trigger_s / record_span_s)
            scope._intf.write(f"HORizontal:POSition {horizontal_position_percent:g}")
            scope._intf.write("ACQuire:NUMACq:RESET")
            scope.set_acquire_state("RUN")
            acquisition_count_before = wait_for_scope_armed(
                scope,
                timeout_s=SCOPE_CAPTURE_TIMEOUT_S,
            )

            capture_deadline = monotonic() + max(
                FASTRX_TIMEOUT_S,
                2.0 * conversions * sequence_period_s + 2.0,
            )
            daq["seq0"].start()
            wait_for_scope_capture(
                scope,
                acquisition_count_before,
                timeout_s=SCOPE_CAPTURE_TIMEOUT_S,
            )
            while not daq["seq0"].is_done():
                if monotonic() >= capture_deadline:
                    raise TimeoutError("sequencer did not finish the requested conversions")
                sleep(0.001)
            expected_fifo_bytes = 4 * conversions
            while int(daq["fifo0"]["FIFO_SIZE"]) < expected_fifo_bytes:
                if monotonic() >= capture_deadline:
                    raise TimeoutError("FastRX did not deliver every requested conversion")
                sleep(0.001)
            sleep(FASTRX_TRAILING_DRAIN_S)
            raw_data = list(daq["fifo0"].get_data())
            if len(raw_data) != conversions:
                raise RuntimeError(f"received {len(raw_data)} FastRX words, expected {conversions}")
            if int(daq["fastrx0"].get_lost_count()):
                raise RuntimeError("FastRX reported lost words")

            sleep(SCOPE_DOWNLOAD_SETTLE_S)
            waveforms = scope.get_waveforms(SCOPE_TRACKS)
            missing_channels = sorted(set(SCOPE_TRACKS).difference(waveforms))
            if missing_channels:
                raise RuntimeError(f"scope did not return channels {missing_channels}")

            stem = (
                f"adc01_{symbol_rate_bps / 1e6:04.0f}mbd_"
                f"logic{logic_offset:+d}_rx{rx_sen_start_word:02d}_"
                f"tap{comp_idelay_taps:02d}"
            )
            scope_csv_path = run_dir / f"{stem}_scope.csv"
            adc_csv_path = run_dir / f"{stem}_adc.csv"
            scope_run = read_run(
                SourceSpec(
                    f"{stem}_scope",
                    BackendKind.MEASUREMENT,
                    BlockKind.GENERIC,
                    SourceFormat.SCOPE_WAVEFORMS,
                    (waveforms, SCOPE_TRACKS),
                    table_name="waveforms",
                )
            )
            write_scope_csv(scope_csv_path, waveforms, SCOPE_TRACKS)

            scope_decisions = extract_scope_decisions(
                np.asarray(scope_run.table("waveforms").column("time_s"), dtype=float),
                np.asarray(scope_run.table("waveforms").column("seq_comp_v"), dtype=float),
                np.asarray(scope_run.table("waveforms").column("comp_out_v"), dtype=float),
                symbol_rate_bps=symbol_rate_bps,
                decision_count=data_size,
                output_inverted=SCOPE_COMP_OUT_INVERTED,
            )

            adc_rows = []
            codes = []
            first_fastrx_bits = ""
            frame_counter_modulus = 1 << (28 - data_size)
            for conversion_index, word in enumerate(raw_data):
                raw_word = int(word)
                identifier, frame, spi_data = daq["fastrx0"].parse_word(raw_word)
                if identifier != 1:
                    raise RuntimeError(f"conversion {conversion_index}: identifier={identifier}, expected 1")
                expected_frame = conversion_index % frame_counter_modulus
                if frame != expected_frame:
                    raise RuntimeError(f"conversion {conversion_index}: frame={frame}, expected {expected_frame}")
                bout, dout_raw = convert_fastrx_to_bout_and_dout(
                    spi_data,
                    data_size,
                    code_weights,
                )
                dout = convert_dout_to_normalized_dout(
                    dout_raw,
                    code_weights,
                    params.dut.adc_bits,
                )
                if conversion_index == 0:
                    first_fastrx_bits = bout
                codes.append(dout)
                adc_rows.append(
                    AdcConversion(
                        conversion_index=conversion_index,
                        raw_word=raw_word,
                        identifier=identifier,
                        frame=frame,
                        spi=spi_data,
                        bout=bout,
                        dout_raw=dout_raw,
                        dout=dout,
                    )
                )
            write_adc_conversions(adc_csv_path, adc_rows)

            bit_mismatches = sum(
                scope_bit != fastrx_bit
                for scope_bit, fastrx_bit in zip(
                    scope_decisions.bits,
                    first_fastrx_bits,
                    strict=True,
                )
            )
            mean_code = fmean(codes)
            sigma_code = pstdev(codes)
            print(
                f"scope={scope_decisions.bits}, FastRX={first_fastrx_bits}, "
                f"mismatches={bit_mismatches}/17; "
                f"mean={mean_code:.3f} LSB, sigma={sigma_code:.3f} LSB"
            )

            info_lines = (
                f"Rate: {symbol_rate_bps / 1e6:g} MBd",
                f"LOGIC phase: {logic_offset:+d} symbols",
                f"RX_SEN word / IDELAY: {rx_sen_start_word} / {comp_idelay_taps}",
                f"Scope bits: {scope_decisions.bits}",
                f"FastRX bits: {first_fastrx_bits}",
                f"Bit mismatches: {bit_mismatches}/17",
                f"ADC σ: {sigma_code:.3f} LSB",
            )
            render_plot(
                PlotRequest(
                    PlotSpec(
                        name=f"{stem}_scope",
                        kind=PlotKind.TIME_DOMAIN,
                        input_ids=(scope_run.run_id,),
                        output_path=scope_csv_path.with_suffix(".png"),
                        title=(f"ADC01 scope/FastRX capture: {symbol_rate_bps / 1e6:g} MBd, LOGIC {logic_offset:+d}"),
                        table="waveforms",
                        y_columns=(
                            "adc_vdiff_v",
                            "seq_comp_v",
                            "seq_logic_v",
                            "comp_out_v",
                        ),
                        labels={
                            "adc_vdiff_v": "CH1 ADC Vdiff (V)",
                            "seq_comp_v": "CH2 COMP (V)",
                            "seq_logic_v": "CH3 LOGIC (V)",
                            "comp_out_v": "CH4 COMP_OUT (V)",
                        },
                        info_lines={"comp_out_v": info_lines},
                    ),
                    runs=(scope_run,),
                )
            )
            adc_run = read_run(
                SourceSpec(
                    f"{stem}_adc",
                    BackendKind.MEASUREMENT,
                    BlockKind.ADC,
                    SourceFormat.ADC_CSV,
                    adc_csv_path,
                    table_name="conversions",
                    parameters={
                        "vin_diff_v": VIN_DIFF_V,
                        "vin_cm_v": VIN_CM_V,
                        "symbol_rate_bps": symbol_rate_bps,
                        "logic_offset_symbols": logic_offset,
                    },
                )
            )
            distribution_result = analyze_adc_distribution(
                AnalysisRequest(
                    AnalysisSpec(
                        f"{stem}_distribution",
                        AnalysisKind.ADC_DISTRIBUTION,
                        (adc_run.run_id,),
                        AdcSettings(adc_bits=params.dut.adc_bits),
                    ),
                    runs=(adc_run,),
                )
            )
            render_plot(
                PlotRequest(
                    PlotSpec(
                        name=f"{stem}_hist",
                        kind=PlotKind.DISTRIBUTION,
                        input_ids=(distribution_result.name,),
                        output_path=run_dir / f"{stem}_hist.png",
                        title=(
                            f"ADC01 fixed-input noise: {symbol_rate_bps / 1e6:g} MBd, LOGIC offset {logic_offset:+d}"
                        ),
                    ),
                    results=(distribution_result,),
                )
            )

            summary_rows.append(
                {
                    "symbol_rate_bps": symbol_rate_bps,
                    "active_conversion_rate_hz": symbol_rate_bps / 160.0,
                    "active_conversion_rate_msps": symbol_rate_bps / 160.0e6,
                    "logic_offset_symbols": logic_offset,
                    "comparator_time_percent": 50.0 + 12.5 * logic_offset,
                    "rx_sen_start_word": rx_sen_start_word,
                    "comp_idelay_taps": comp_idelay_taps,
                    "predicted_data_arrival_s": alignment.data_arrival_s,
                    "predicted_capture_edge_s": alignment.capture_edge_s,
                    "predicted_setup_margin_s": alignment.setup_margin_s,
                    "predicted_hold_margin_s": alignment.hold_margin_s,
                    "scope_bits": scope_decisions.bits,
                    "fastrx_bits": first_fastrx_bits,
                    "bit_mismatches": bit_mismatches,
                    "mean_dout_lsb": mean_code,
                    "sigma_dout_lsb": sigma_code,
                    "minimum_dout_lsb": min(codes),
                    "maximum_dout_lsb": max(codes),
                    "scope_csv": str(scope_csv_path),
                    "adc_csv": str(adc_csv_path),
                }
            )
            with summary_path.open("w", newline="") as output:
                writer = csv.DictWriter(output, fieldnames=list(summary_rows[0]))
                writer.writeheader()
                writer.writerows(summary_rows)

        # Render the complete rate sweep from its persisted summary table.
        # The reciprocal lower axis uses Tdecision_ns = 50 / rate_MSPS because
        # one active conversion contains twenty decision cycles.
        summary_run = read_run(
            SourceSpec(
                "fastrx_summary",
                BackendKind.MEASUREMENT,
                BlockKind.ADC,
                SourceFormat.CSV,
                summary_path,
                table_name="sweep",
            )
        )
        render_plot(
            PlotRequest(
                PlotSpec(
                    name="decision_variation_vs_conversion_rate",
                    kind=PlotKind.SWEEP,
                    input_ids=(summary_run.run_id,),
                    output_path=run_dir / "decision_variation_vs_conversion_rate.png",
                    title="Decision variation in LSB vs Conversion rate",
                    table="sweep",
                    x_column="active_conversion_rate_msps",
                    y_columns=("sigma_dout_lsb",),
                    group_column="comparator_time_percent",
                    labels={
                        "active_conversion_rate_msps": "Active conversion rate (MSPS)",
                        "sigma_dout_lsb": "Output σ (LSB)",
                    },
                    legend_title="COMP→LOGIC interval",
                    y_limit=(0.0, 10.0),
                    x_ticks=tuple(float(rate) for rate in range(1, 11)),
                    secondary_x_reciprocal=50.0,
                    secondary_x_label="Time per decision cycle (ns)",
                ),
                runs=(summary_run,),
            )
        )

        manifest_path.write_text(
            json.dumps(
                {
                    "board_id": BOARD_ID,
                    "adc_index": ADC_INDEX,
                    "vin_diff_v": VIN_DIFF_V,
                    "vin_cm_v": VIN_CM_V,
                    "conversions_per_point": conversions,
                    "scope_comp_out_inverted": SCOPE_COMP_OUT_INVERTED,
                    "timing_model": to_json_data(timing_model),
                    "points": summary_rows,
                },
                indent=2,
                sort_keys=True,
            )
            + "\n"
        )

        mismatched_points = [row for row in summary_rows if row["bit_mismatches"]]
        if mismatched_points:
            raise AssertionError(
                f"{len(mismatched_points)}/{len(summary_rows)} points did not "
                f"match all 17 scope and FastRX bits; see {summary_path}"
            )
        print(f"PASS: all {len(summary_rows)} points matched all 17 scope/FastRX bits; summary: {summary_path}")
    finally:
        if daq is not None:
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
            except Exception as error:
                print(f"WARNING: could not restore FPGA defaults: {error}")
        if awg is not None:
            try:
                awg.set_DC("DEF,DEF,0")
                awg.set_enable(0)
            except Exception as error:
                print(f"WARNING: could not disable and zero the AWG: {error}")
        if vin_cm_supply is not None:
            try:
                vin_cm_supply.set_enable(0)
                vin_cm_supply.set_voltage(0.0)
            except Exception as error:
                print(f"WARNING: could not disable and zero Vin_cm: {error}")
        for smu, rail in smus:
            try:
                smu.off()
                smu.set_voltage(0.0)
            except Exception as error:
                print(f"WARNING: could not disable and zero {rail}: {error}")
        if scope is not None and scope_state is not None:
            try:
                scope.set_acquire_state("STOP")
                scope.set_acquire_mode(scope_state["acquire_mode"])
                scope.set_horizontal_scale(scope_state["horizontal_scale"])
                scope.set_horizontal_record_length(scope_state["horizontal_record_length"])
                scope._intf.write(f"HORizontal:POSition {scope_state['horizontal_position']}")
                scope.set_trigger_mode(scope_state["trigger_mode"])
                scope.set_trigger_type(scope_state["trigger_type"])
                scope._intf.write(f"TRIGger:A:EDGe:SOUrce {scope_state['trigger_source']}")
                scope.set_trigger_edge_slope(scope_state["trigger_slope"])
                scope.set_trigger_level(
                    scope_state["trigger_level"],
                    channel=SCOPE_TRIGGER_CHANNEL,
                )
                for channel in SCOPE_TRACKS:
                    scope.set_vertical_scale(SCOPE_VERTICAL_SCALE_V, channel=channel)
                    scope.set_vertical_position(0.0, channel=channel)
                    scope.set_vertical_offset(0.0, channel=channel)
                    scope.set_bandwidth(SCOPE_BANDWIDTH_HZ, channel=channel)
                    scope._intf.write(f"DISplay:GLObal:CH{channel}:STATE {scope_state['display'][channel]}")
                scope.set_acquire_stop_after(scope_state["acquire_stop_after"])
                scope.set_acquire_state(scope_state["acquire_state"])
            except Exception as error:
                print(f"WARNING: could not fully restore scope state: {error}")
        for instrument_dut in reversed(initialized_duts):
            instrument_dut.close()


if __name__ == "__main__":
    main()
