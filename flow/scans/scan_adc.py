"""Acquire one physical ADC data file for each configured parameter variant."""

from __future__ import annotations

import json
import math
import re
from array import array
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from time import monotonic, sleep
from typing import Any, Mapping

import hdl21 as h
from bitarray import bitarray

from flow.cdac import get_cdac_weights
from flow.scans.params import AdcTbParams, build_variants, load_board_map, validate_params
from flow.scans.plldrp import calculate_pll_frequency, select_pll_configuration, set_pll_divider
from flow.analysis.io import parameter_digest, to_json_data
from flow.analysis.models import AdcConversion
from flow.scans.results import write_adc_conversions

SCAN_OUTDIR = Path(__file__).resolve().parents[2] / "build" / "scan_adc"


@dataclass(frozen=True, slots=True)
class FastRxCaptureAlignment:
    """One analytically selected FastRX word/ IDELAY capture point."""

    rx_sen_start_word: int
    comp_idelay_taps: int
    first_comp_transition_symbol: int
    data_arrival_s: float
    capture_edge_s: float
    setup_margin_s: float
    hold_margin_s: float


def convert_vdiff_input_to_awg_supply(
    vin_diff: float,
    vin_cm: float,
    calibration: Mapping[str, Any] | None = None,
) -> tuple[float, float]:
    """Convert desired ADC-side Vdiff and Vin_cm to instrument setpoints.

    ``vin_diff`` is ``Vin_p - Vin_n`` at the ADC. The returned tuple is the
    single-ended AWG voltage and E3634A setpoint. This function performs no
    instrument I/O. With no explicit calibration it uses frida65a_001 from
    ``map_board.yaml`` for convenient software tests and loopback scripts.
    """

    if calibration is None:
        calibration = load_board_map()["boards"]["frida65a_001"]["input_calibration"]

    amplitude_v = abs(vin_diff)
    common_mode_delta_v = vin_cm - float(calibration["awg_calibration_vin_cm_v"])
    basis = (
        1.0,
        amplitude_v,
        amplitude_v**2,
        common_mode_delta_v,
        amplitude_v * common_mode_delta_v,
        common_mode_delta_v**2,
    )
    awg_v_per_vdiff = sum(
        float(coefficient) * term
        for coefficient, term in zip(
            calibration["awg_vdiff_magnitude_coefficients"],
            basis,
            strict=True,
        )
    )
    awg_center_v = sum(
        float(coefficient) * term
        for coefficient, term in zip(
            calibration["awg_center_coefficients"],
            basis,
            strict=True,
        )
    )
    awg_voltage = awg_center_v - vin_diff * awg_v_per_vdiff
    vin_cm_supply_voltage = (
        float(calibration["vin_cm_supply_offset_v"]) + float(calibration["vin_cm_supply_gain"]) * vin_cm
    )
    return awg_voltage, vin_cm_supply_voltage


def convert_dac_caps_to_adc_weights(cap_weights: list[int] | tuple[int, ...]) -> list[int]:
    """Convert CDAC unit-cap weights C16..C1 to decision weights W16..W0."""

    if not cap_weights or any(
        isinstance(weight, bool) or not isinstance(weight, int) or weight <= 0 for weight in cap_weights
    ):
        raise ValueError("CDAC weights must be a non-empty sequence of positive integers")
    return [2 * weight for weight in cap_weights] + [1]


def convert_fastrx_to_bout_and_dout(
    spi_data: int,
    data_size: int,
    code_weights: list[int],
) -> tuple[str, int]:
    """Decode one FastRX word into Bout and ideal-weight raw Dout."""

    samples = [(spi_data >> index) & 1 for index in range(data_size - 1, -1, -1)]
    if len(samples) < len(code_weights):
        raise ValueError(f"FastRX DATA_SIZE={data_size} is smaller than {len(code_weights)} ADC code bits")

    bits = samples[: len(code_weights)]
    bout = "".join(str(bit) for bit in bits)
    dout = sum(weight * bit for weight, bit in zip(code_weights, bits, strict=True))
    return bout, dout


def convert_dout_to_normalized_dout(dout: int, code_weights: list[int], adc_bits: int) -> int:
    """Scale ideal-weight raw Dout onto the configured nominal ADC range."""

    if adc_bits <= 0:
        raise ValueError("adc_bits must be positive")
    return round(dout * ((1 << adc_bits) - 1) / sum(code_weights))


def calculate_fastrx_capture_alignment(
    params: AdcTbParams,
    *,
    seqgen_pipeline_cycles: float,
    oserdes_to_output_s: float,
    external_comp_delay_s: float,
    comp_input_to_fastrx_d_s: float,
    launch_to_capture_clock_skew_s: float,
    idelay_tap_s: float,
    idelay_tap_count: int,
    minimum_setup_s: float = 0.0,
    minimum_hold_s: float = 0.0,
) -> FastRxCaptureAlignment:
    """Select the integer FastRX capture word and comparator IDELAY tap.

    The first possible COMP_OUT transition is derived from the serialized COMP
    pattern. Its arrival at the FastRX D input is the sum of its symbol
    position, the sequencer-to-OSERDES pipeline, the routed external path, the
    launch/capture clock-insertion skew, and the selected IDELAY. FastRX samples
    once per sequencer word. Every legal tap is evaluated against the next
    word-clock edge, and the point maximizing the smaller setup/ hold margin is
    returned.

    ``seq_logic`` is intentionally absent from this timing calculation. It
    updates the SAR/CDAC state for the following comparison, but COMP_OUT is
    driven directly by the comparator clocked from ``seq_comp``.
    """

    validate_params(params)
    numeric_fields = {
        "seqgen_pipeline_cycles": seqgen_pipeline_cycles,
        "oserdes_to_output_s": oserdes_to_output_s,
        "external_comp_delay_s": external_comp_delay_s,
        "comp_input_to_fastrx_d_s": comp_input_to_fastrx_d_s,
        "launch_to_capture_clock_skew_s": launch_to_capture_clock_skew_s,
        "idelay_tap_s": idelay_tap_s,
        "minimum_setup_s": minimum_setup_s,
        "minimum_hold_s": minimum_hold_s,
    }
    for field, value in numeric_fields.items():
        if not math.isfinite(value) or value < 0.0:
            raise ValueError(f"{field} must be finite and non-negative")
    if isinstance(idelay_tap_count, bool) or not isinstance(idelay_tap_count, int) or idelay_tap_count <= 0:
        raise ValueError("idelay_tap_count must be a positive integer")

    symbol_rate_bps = float(params.symbol_rate)
    sequencer_period_s = 8.0 / symbol_rate_bps

    comp_pattern = params.seq_comp_pattern
    phase_symbols = float(params.seq_comp_phase_delay_symbols)
    if not phase_symbols.is_integer():
        raise ValueError("physical seq_comp_phase_delay_symbols must be a whole number of serialized symbols")
    shift = int(phase_symbols) % len(comp_pattern)
    if shift:
        comp_pattern = comp_pattern[-shift:] + comp_pattern[:-shift]
    first_comp_transition_symbol = next(
        (
            symbol_index
            for symbol_index in range(1, len(comp_pattern))
            if comp_pattern[symbol_index] != comp_pattern[symbol_index - 1]
        ),
        -1,
    )
    if first_comp_transition_symbol < 0:
        raise ValueError("seq_comp_pattern contains no transition")

    base_arrival_s = (
        first_comp_transition_symbol / symbol_rate_bps
        + seqgen_pipeline_cycles * sequencer_period_s
        + oserdes_to_output_s
        + external_comp_delay_s
        + comp_input_to_fastrx_d_s
        + launch_to_capture_clock_skew_s
    )

    candidates: list[tuple[float, float, int, int, float, float, float]] = []
    for taps in range(idelay_tap_count):
        data_arrival_s = base_arrival_s + taps * idelay_tap_s
        capture_word = math.ceil((data_arrival_s + minimum_setup_s) / sequencer_period_s - 1.0e-12)
        capture_edge_s = capture_word * sequencer_period_s
        setup_margin_s = capture_edge_s - data_arrival_s
        hold_margin_s = data_arrival_s + sequencer_period_s - capture_edge_s
        if setup_margin_s < minimum_setup_s or hold_margin_s < minimum_hold_s:
            continue
        smaller_margin_s = min(
            setup_margin_s - minimum_setup_s,
            hold_margin_s - minimum_hold_s,
        )
        candidates.append(
            (
                smaller_margin_s,
                -abs(setup_margin_s - hold_margin_s),
                -taps,
                capture_word,
                data_arrival_s,
                setup_margin_s,
                hold_margin_s,
            )
        )

    if not candidates:
        raise ValueError("no legal FastRX capture word/ IDELAY setting satisfies the requested margins")

    (
        _smaller_margin_s,
        _negative_imbalance_s,
        negative_taps,
        capture_word,
        data_arrival_s,
        setup_margin_s,
        hold_margin_s,
    ) = max(candidates)
    return FastRxCaptureAlignment(
        rx_sen_start_word=capture_word,
        comp_idelay_taps=-negative_taps,
        first_comp_transition_symbol=first_comp_transition_symbol,
        data_arrival_s=data_arrival_s,
        capture_edge_s=capture_word * sequencer_period_s,
        setup_margin_s=setup_margin_s,
        hold_margin_s=hold_margin_s,
    )


def convert_params_to_seqgen_fmt(params: AdcTbParams, rx_sen_start_word: int) -> array[int]:
    """Pack ADC timing parameters into the FPGA's 64-bit sequencer memory.

    Fixed implementation details are intentionally local: the four OSERDES
    lanes each consume eight symbols per word, the physical sequencer stores
    eight byte lanes, RX_SEN is bit zero of byte lane four, and RX_TEST is bit
    one. The FPGA does not currently expose these constants through registers.
    """

    SERDES_RATIO = 8
    SEQGEN_BYTE_LANES = 8
    SERDES_FIELDS = (
        ("INIT", "seq_init_pattern", "seq_init_phase_delay_symbols"),
        ("SAMP", "seq_samp_pattern", "seq_samp_phase_delay_symbols"),
        ("COMP", "seq_comp_pattern", "seq_comp_phase_delay_symbols"),
        ("LOGIC", "seq_logic_pattern", "seq_logic_phase_delay_symbols"),
    )
    RX_SEN_BIT = 0
    RX_TEST_BIT = 1

    validate_params(params)
    parsed: dict[str, list[str]] = {}
    sequence_symbols = len(params.seq_init_pattern)
    for name, pattern_field, phase_field in SERDES_FIELDS:
        pattern = getattr(params, pattern_field)
        phase_symbols = float(getattr(params, phase_field))
        if not phase_symbols.is_integer():
            raise ValueError(f"physical {phase_field} must be a whole number of serialized symbols")
        shift = int(phase_symbols) % sequence_symbols
        if shift:
            pattern = pattern[-shift:] + pattern[:-shift]
        parsed[name] = [pattern[index : index + SERDES_RATIO] for index in range(0, len(pattern), SERDES_RATIO)]

    sequence_words = sequence_symbols // SERDES_RATIO
    capture_bits = len(convert_dac_caps_to_adc_weights(get_cdac_weights(params.dut.cdac)))
    rx_sen_stop_word = rx_sen_start_word + capture_bits
    if rx_sen_start_word < 0 or rx_sen_stop_word >= sequence_words:
        raise ValueError(
            f"RX_SEN window {rx_sen_start_word}..{rx_sen_stop_word - 1} must leave a low word "
            f"before the {sequence_words}-word repeat"
        )
    rx_sen_words = [0] * sequence_words
    rx_sen_words[rx_sen_start_word:rx_sen_stop_word] = [1] * capture_bits

    memory = array("B")
    for word_index in range(sequence_words):
        for name, _pattern_field, _phase_field in SERDES_FIELDS:
            value = 0
            for lane, bit in enumerate(parsed[name][word_index]):
                value |= int(bit) << lane
            memory.append(value)

        control = rx_sen_words[word_index] << RX_SEN_BIT
        control |= 0 << RX_TEST_BIT
        memory.append(control)
        memory.extend(0 for _ in range(SEQGEN_BYTE_LANES - 5))

    return memory


def convert_params_to_spi_fmt(params: AdcTbParams) -> bytes:
    """Pack one complete ADC parameter configuration into the 180-bit SPI image."""

    DAC_FIELDS = (
        ("dac_astate_p", 63, 48),
        ("dac_bstate_p", 47, 32),
        ("dac_astate_n", 31, 16),
        ("dac_bstate_n", 15, 0),
    )
    ADC_FIELDS = ("en_init", "en_samp_p", "en_samp_n", "en_comp", "en_update", "dac_mode", "dac_diffcaps")
    ADC_COUNT = 16
    ADC_CONFIG_BASE = 64
    ADC_CONFIG_BITS = 7
    MUX_MSB = 179
    MUX_LSB = 176

    validate_params(params)
    if params.observed_adc is None or params.active_adc_mask is None:
        raise ValueError("physical SPI formatting requires observed_adc and active_adc_mask")

    bits = bitarray(180)
    bits.setall(0)

    for field, msb, lsb in DAC_FIELDS:
        value = "".join(str(bit) for bit in getattr(params, field))
        value_bits = bitarray(value[::-1])
        width = msb - lsb + 1
        if len(value_bits) != width:
            raise ValueError(f"{field} must be {width} bits, got {len(value_bits)}")
        bits[lsb : msb + 1] = value_bits

    active_config = bitarray([bool(getattr(params, field)) for field in ADC_FIELDS])
    inactive_config = bitarray("0" * ADC_CONFIG_BITS)
    for adc_index in range(ADC_COUNT):
        base = ADC_CONFIG_BASE + ADC_CONFIG_BITS * adc_index
        is_active = bool(params.active_adc_mask[ADC_COUNT - 1 - adc_index])
        bits[base : base + ADC_CONFIG_BITS] = active_config if is_active else inactive_config

    mux_bits = f"{params.observed_adc:04b}"
    mux_value = bitarray(mux_bits[::-1])
    bits[MUX_LSB : MUX_MSB + 1] = mux_value

    column_width = 32
    print("DAC state strings are ordered C16..C1, i.e. biggest capacitor to smallest capacitor.")
    print("".join(f"{field} spi_bits[{msb}:{lsb}]".ljust(column_width) for field, msb, lsb in DAC_FIELDS))
    print(
        "".join("".join(str(bit) for bit in getattr(params, field)).ljust(column_width) for field, _, _ in DAC_FIELDS)
    )
    print("MUX_SEL spi_bits[179:176]")
    print(mux_bits)

    return bits[::-1].tobytes()


def parse_pwl_wave(wave: str) -> tuple[tuple[float, float], ...]:
    """Parse an HDL21 PWL string into SI-valued ``(time, voltage)`` points."""

    SUFFIXES = {
        "": 1.0,
        "t": 1e12,
        "g": 1e9,
        "meg": 1e6,
        "k": 1e3,
        "m": 1e-3,
        "u": 1e-6,
        "µ": 1e-6,
        "n": 1e-9,
        "p": 1e-12,
        "f": 1e-15,
        "a": 1e-18,
    }

    tokens = wave.split()
    if len(tokens) < 4 or len(tokens) % 2:
        raise ValueError("PWL wave must contain at least two time/value pairs")

    values = []
    for token in tokens:
        match = re.fullmatch(r"([+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?)([A-Za-zµ]*)", token)
        if match is None:
            raise ValueError(f"invalid PWL number {token!r}")
        suffix = match.group(2).lower()
        if suffix not in SUFFIXES:
            raise ValueError(f"unsupported PWL suffix {match.group(2)!r}")
        values.append(float(match.group(1)) * SUFFIXES[suffix])

    points = tuple((values[index], values[index + 1]) for index in range(0, len(values), 2))
    if any(right[0] <= left[0] for left, right in zip(points, points[1:])):
        raise ValueError("PWL times must increase strictly")
    return points


def main() -> None:
    """Run every configured physical variant into a fresh timestamped directory."""

    SETUP_SETTLE_S = 0.2
    SMU_SETTLE_S = 0.5
    SI570_SETTLE_S = 0.02
    FASTRX_CAPTURE_TIMEOUT_S = 5.0
    FASTRX_TRAILING_DRAIN_S = 0.01
    CSV_WRITE_BATCH_ROWS = 10_000
    MAX_RAW_FASTRX_WORDS = 20

    variants = build_variants()
    if not variants:
        raise ValueError("build_variants() returned no ADC configurations")
    for params in variants:
        validate_params(params)
        if params.board_id is None or params.observed_adc is None or params.active_adc_mask is None:
            raise ValueError("every physical scan variant must select a board, observed ADC, and active ADC mask")

    board_ids = {params.board_id for params in variants}
    if len(board_ids) != 1:
        raise ValueError("one physical scan invocation can operate on exactly one board_id")
    board_id = next(iter(board_ids))
    board_map = load_board_map()
    board = board_map["boards"][board_id]

    run_timestamp = datetime.now().astimezone().strftime("%Y%m%d_%H%M%S")
    run_dir = SCAN_OUTDIR / run_timestamp
    run_dir.mkdir(parents=True, exist_ok=False)
    manifest_path = run_dir / "manifest.json"

    manifest = {
        "schema_version": 1,
        "started_at": datetime.now().astimezone().isoformat(),
        "board_id": board_id,
        "board_map": str(Path(__file__).resolve().parent / "map_board.yaml"),
        "board_configuration": to_json_data(board),
        "status": "running",
        "variants": [],
    }

    for index, params in enumerate(variants):
        source = params.vin_diff
        if isinstance(source, h.Vdc.Params):
            source_label = f"dc{float(source.dc) * 1e3:+.0f}mv".replace("+", "p").replace("-", "m")
        elif isinstance(source, h.Vsin.Params):
            source_label = (
                (f"sin{float(source.freq):g}hz_{float(source.voff) * 1e3:+g}mv_{2 * float(source.vamp) * 1e3:g}mvpp")
                .replace("+", "p")
                .replace("-", "m")
            )
        elif isinstance(source, h.Vpwl.Params):
            source_points = parse_pwl_wave(source.wave)
            source_period_s = source_points[-1][0] - source_points[0][0]
            source_min_v = min(value for _time, value in source_points)
            source_max_v = max(value for _time, value in source_points)
            source_label = (
                (f"pwl{1.0 / source_period_s:g}hz_{source_min_v * 1e3:+g}to{source_max_v * 1e3:+g}mv")
                .replace("+", "p")
                .replace("-", "m")
            )
        else:
            raise TypeError(f"unsupported differential source type {type(source).__name__}")

        stem = (
            f"{index:04d}_{board_id}_adc{params.observed_adc:02d}_"
            f"{float(params.symbol_rate) / 1e6:g}mbd_{source_label}_"
            f"vcm{float(params.vin_cm.dc) * 1e3:g}mv_"
            f"vdda{float(params.vdd_a.dc) * 1e3:g}mv_"
            f"vddd{float(params.vdd_d.dc) * 1e3:g}mv_"
            f"vddac{float(params.vdd_dac.dc) * 1e3:g}mv_"
            f"t{float(params.temperature_c):g}c_{parameter_digest(params)}"
        )
        manifest["variants"].append(
            {
                "index": index,
                "parameter_digest": parameter_digest(params),
                "csv_path": f"{stem}.csv",
                "status": "pending",
                "parameters": to_json_data(params),
            }
        )
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")

    from gpib_ctypes import make_default_gpib

    make_default_gpib()
    from basil.dut import Dut

    map_dir = Path(__file__).resolve().parent
    daq_dut = Dut(str(map_dir / "map_fpga.yaml"))
    awg_dut = Dut(str(map_dir / "map_awg.yaml"))
    vin_cm_dut = Dut(str(map_dir / "map_supply.yaml"))
    smu_dut = Dut(str(map_dir / "map_smu.yaml"))
    initialized_duts = []
    daq = awg = vin_cm_supply = None
    smus = []

    try:
        for dut in (daq_dut, awg_dut, vin_cm_dut, smu_dut):
            dut.init()
            initialized_duts.append(dut)

        daq = daq_dut
        awg = awg_dut["awg"]
        vin_cm_supply = vin_cm_dut["vocm_supply"]
        smus = [
            (smu_dut["smu1"], "VDD_A", "vdd_a"),
            (smu_dut["smu2"], "VDD_D", "vdd_d"),
            (smu_dut["smu3"], "VDD_DAC", "vdd_dac"),
        ]

        awg.set_enable(0)
        vin_cm_supply.set_enable(0)
        vin_cm_supply.set_voltage(0.0)
        for smu, _rail, _field in smus:
            smu.off()
            smu.set_voltage(0.0)

        for variant_entry, params in zip(manifest["variants"], variants, strict=True):
            try:
                print(
                    f"\n=== variant {variant_entry['index'] + 1}/{len(variants)}: "
                    f"ADC {params.observed_adc:02d}, {float(params.symbol_rate) / 1e6:g} MBd ==="
                )
                supply_limits = board["supply_limits"]
                maximum_supply_v = float(supply_limits["maximum_voltage_v"])
                loaded_voltage_tolerance_v = float(supply_limits["loaded_voltage_tolerance_v"])
                fixed_vdd_io_v = float(board["fixed_vdd_io_v"])
                if not math.isclose(float(params.vdd_io.dc), fixed_vdd_io_v, abs_tol=1e-12):
                    raise ValueError(
                        f"VDD_IO is fixed at {fixed_vdd_io_v:g} V on {board_id}; "
                        f"variant requests {float(params.vdd_io.dc):g} V"
                    )

                smu_readback = {}
                for smu, rail, field in smus:
                    requested_voltage_v = float(getattr(params, field).dc)
                    if not 0.0 < requested_voltage_v <= maximum_supply_v:
                        raise ValueError(
                            f"{rail} request {requested_voltage_v:g} V is outside 0..{maximum_supply_v:g} V"
                        )
                    smu.off()
                    smu.set_voltage(0.0)
                    smu.source_volt()
                    smu.four_wire_off()
                    smu.set_voltage_range(float(supply_limits["smu_voltage_range_v"]))
                    smu.set_current_limit(float(supply_limits["smu_current_compliance_a"]))
                    smu.current_sense_autorange_on()
                    smu.set_current_nplc(10.0)
                    smu.autozero_on()
                    smu.set_voltage(requested_voltage_v)

                for smu, _rail, _field in smus:
                    smu.on()
                sleep(SMU_SETTLE_S)

                for smu, rail, field in smus:
                    requested_voltage_v = float(getattr(params, field).dc)
                    measured_voltage_v = float(smu.get_voltage())
                    measured_current_a = float(smu.get_current())
                    if measured_voltage_v > maximum_supply_v + 5e-3:
                        raise RuntimeError(f"{rail} measured unsafe voltage {measured_voltage_v:g} V")
                    if measured_voltage_v < requested_voltage_v - loaded_voltage_tolerance_v:
                        raise RuntimeError(
                            f"{rail} loaded voltage {measured_voltage_v:g} V is more than "
                            f"{loaded_voltage_tolerance_v:g} V below its "
                            f"{requested_voltage_v:g} V setpoint"
                        )
                    smu_readback[field] = {
                        "requested_voltage_v": requested_voltage_v,
                        "measured_voltage_v": measured_voltage_v,
                        "measured_current_a": measured_current_a,
                    }

                vin_cm_v = float(params.vin_cm.dc)
                calibration = board["input_calibration"]
                source = params.vin_diff
                if isinstance(source, h.Vdc.Params):
                    vin_diff_min_v = vin_diff_max_v = float(source.dc)
                    awg_voltage_v, vin_cm_supply_v = convert_vdiff_input_to_awg_supply(
                        vin_diff_min_v,
                        vin_cm_v,
                        calibration,
                    )
                    awg.set_DC(f"DEF,DEF,{awg_voltage_v}")
                    stimulus_readback = {
                        "kind": "dc",
                        "vin_diff_v": vin_diff_min_v,
                        "awg_voltage_v": awg_voltage_v,
                    }
                elif isinstance(source, h.Vsin.Params):
                    if source.voff is None or source.vamp is None or source.freq is None:
                        raise ValueError("sine stimulus requires voff, vamp, and freq")
                    vin_diff_min_v = float(source.voff) - float(source.vamp)
                    vin_diff_max_v = float(source.voff) + float(source.vamp)
                    awg_at_min_v, vin_cm_supply_v = convert_vdiff_input_to_awg_supply(
                        vin_diff_min_v,
                        vin_cm_v,
                        calibration,
                    )
                    awg_at_max_v, second_supply_v = convert_vdiff_input_to_awg_supply(
                        vin_diff_max_v,
                        vin_cm_v,
                        calibration,
                    )
                    if not math.isclose(vin_cm_supply_v, second_supply_v, abs_tol=1e-12):
                        raise RuntimeError("Vin_cm calibration changed across sine endpoints")
                    awg_amplitude_vpp = abs(awg_at_max_v - awg_at_min_v)
                    awg_offset_v = (awg_at_max_v + awg_at_min_v) / 2.0
                    awg.set_sin(f"{float(source.freq)},{awg_amplitude_vpp},{awg_offset_v}")
                    stimulus_readback = {
                        "kind": "sine",
                        "vin_diff_min_v": vin_diff_min_v,
                        "vin_diff_max_v": vin_diff_max_v,
                        "frequency_hz": float(source.freq),
                        "awg_amplitude_vpp": awg_amplitude_vpp,
                        "awg_offset_v": awg_offset_v,
                    }
                elif isinstance(source, h.Vpwl.Params):
                    points = parse_pwl_wave(source.wave)
                    if len(points) not in (2, 3):
                        raise ValueError("physical PWL input must be a two-point ramp or three-point triangle")
                    period_s = points[-1][0] - points[0][0]
                    if len(points) == 3:
                        if not math.isclose(points[0][1], points[-1][1], abs_tol=1e-12):
                            raise ValueError("three-point physical PWL input must return to its starting voltage")
                        symmetry = 100.0 * (points[1][0] - points[0][0]) / period_s
                    else:
                        symmetry = 100.0
                    vin_diff_min_v = min(value for _time, value in points)
                    vin_diff_max_v = max(value for _time, value in points)
                    awg_at_min_v, vin_cm_supply_v = convert_vdiff_input_to_awg_supply(
                        vin_diff_min_v,
                        vin_cm_v,
                        calibration,
                    )
                    awg_at_max_v, second_supply_v = convert_vdiff_input_to_awg_supply(
                        vin_diff_max_v,
                        vin_cm_v,
                        calibration,
                    )
                    if not math.isclose(vin_cm_supply_v, second_supply_v, abs_tol=1e-12):
                        raise RuntimeError("Vin_cm calibration changed across PWL endpoints")
                    awg_amplitude_vpp = abs(awg_at_max_v - awg_at_min_v)
                    awg_offset_v = (awg_at_max_v + awg_at_min_v) / 2.0
                    awg.set_ramp(f"{1.0 / period_s},{awg_amplitude_vpp},{awg_offset_v}")
                    awg.set_function_ramp_symmetry(symmetry)
                    stimulus_readback = {
                        "kind": "pwl",
                        "points": points,
                        "frequency_hz": 1.0 / period_s,
                        "awg_amplitude_vpp": awg_amplitude_vpp,
                        "awg_offset_v": awg_offset_v,
                        "ramp_symmetry_percent": symmetry,
                    }
                else:
                    raise TypeError(f"unsupported differential source type {type(source).__name__}")

                maximum_abs_vdiff_v = float(calibration["maximum_abs_vdiff_v"])
                minimum_vin_cm_v = float(calibration["minimum_vin_cm_v"])
                maximum_vin_cm_v = float(calibration["maximum_vin_cm_v"])
                if max(abs(vin_diff_min_v), abs(vin_diff_max_v)) > maximum_abs_vdiff_v:
                    raise ValueError(f"requested Vdiff exceeds the calibrated +/-{maximum_abs_vdiff_v:g} V range")
                if not minimum_vin_cm_v <= vin_cm_v <= maximum_vin_cm_v:
                    raise ValueError(
                        f"requested Vin_cm={vin_cm_v:g} V is outside the calibrated "
                        f"{minimum_vin_cm_v:g}..{maximum_vin_cm_v:g} V range"
                    )
                if not 0.0 <= vin_cm_supply_v <= maximum_supply_v:
                    raise ValueError(f"calibrated Vin_cm supply request {vin_cm_supply_v:g} V is unsafe")
                if vin_cm_v + vin_diff_max_v / 2.0 > maximum_supply_v or vin_cm_v - vin_diff_max_v / 2.0 < 0.0:
                    raise ValueError("requested positive Vdiff endpoint drives an ADC input outside its supply rails")
                if vin_cm_v + vin_diff_min_v / 2.0 > maximum_supply_v or vin_cm_v - vin_diff_min_v / 2.0 < 0.0:
                    raise ValueError("requested negative Vdiff endpoint drives an ADC input outside its supply rails")

                vin_cm_supply.set_enable(0)
                vin_cm_supply.set_voltage_range("P25V")
                vin_cm_supply.set_current_limit(float(supply_limits["vin_cm_current_limit_a"]))
                vin_cm_supply.set_voltage(vin_cm_supply_v)
                vin_cm_supply.set_enable(1)
                awg.set_output_load("INFinity")
                awg.set_enable(1)
                sleep(SETUP_SETTLE_S)
                stimulus_readback.update(
                    {
                        "awg_enabled": str(awg.get_enable()).strip(),
                        "awg_offset_readback_v": float(str(awg.get_voltage_offset()).strip().split(",")[0]),
                    }
                )
                if not isinstance(source, h.Vdc.Params):
                    stimulus_readback.update(
                        {
                            "awg_frequency_readback_hz": float(str(awg.get_frequency()).strip().split(",")[0]),
                            "awg_amplitude_readback_vpp": float(str(awg.get_voltage_high()).strip().split(",")[0])
                            - float(str(awg.get_voltage_low()).strip().split(",")[0]),
                        }
                    )

                # Put every GPIO0 debug path in a known physical-capture state
                # before releasing the chip reset. This prevents state left by
                # loopback diagnostics from replacing COMP_OUT or the FIFO.
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

                # Derive the FastRX capture word and comparator IDELAY from
                # the routed FPGA and measured external-path timing. The
                # equation is software-tested in test_helpers.py and its exact
                # 17-bit result was checked against simultaneous CH4 scope
                # captures by loopback_fastrx.py at 140 rate/LOGIC points.
                capture_alignment = calculate_fastrx_capture_alignment(
                    params,
                    **board["capture_timing_model"],
                )
                rx_sen_start_word = capture_alignment.rx_sen_start_word
                comp_idelay_taps = capture_alignment.comp_idelay_taps

                # Program the Si570 and the PLL's atomic request,
                # acknowledgement, and lock transaction. The calculation and
                # hardware transaction are tested independently in test_plldrp.py.
                si570_frequency_hz, pll_divider_n = select_pll_configuration(symbol_rate_bps)
                sequencer_frequency_hz, serializer_frequency_hz = calculate_pll_frequency(
                    pll_divider_n,
                    input_frequency_hz=si570_frequency_hz,
                )
                daq["si570"].frequency_change(si570_frequency_hz / 1e6)
                sleep(SI570_SETTLE_S)
                set_pll_divider(daq["gpio2"], pll_divider_n)

                # Program the comparator-input IDELAY through GPIO1. These
                # visible Basil register operations are exercised by the
                # state-restoring hardware checks in test_gpio.py.
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

                # Program raw 64-bit sequencer memory through Basil's public
                # seq_gen API. test_seqgen.py exercises the hardware readback;
                # test_helpers.py checks the software-only memory packing.
                cap_weights = get_cdac_weights(params.dut.cdac)
                code_weights = convert_dac_caps_to_adc_weights(cap_weights)
                sequencer_memory = convert_params_to_seqgen_fmt(params, rx_sen_start_word)
                sequence_words = len(params.seq_init_pattern) // 8
                daq["seq0"].set_data(sequencer_memory)
                daq["seq0"].set_size(sequence_words)
                daq["seq0"].set_clk_divide(1)
                daq["seq0"].set_en_ext_start(False)

                # Configure FastRX for exactly one CDAC decision vector per
                # sequencer repeat. DATA_SIZE is read from the implemented FPGA.
                daq["fastrx0"].reset()
                daq["fastrx0"].set_en(True)
                data_size = int(daq["fastrx0"].get_size())
                if data_size != len(code_weights):
                    raise RuntimeError(
                        f"FastRX DATA_SIZE={data_size}, expected {len(code_weights)} from the configured CDAC"
                    )

                # Program and read back the chip's 180-bit SPI image. Its
                # parameter-to-wire-order conversion is tested in test_helpers.py.
                spi_bytes = convert_params_to_spi_fmt(params)
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

                # Capture every requested conversion in one uninterrupted
                # sequencer run. The 65,536-word FPGA FIFO feeds gigabit
                # SiTCP, whose Basil transfer layer drains continuously into
                # host memory. test_fastrx.py exercises the same unchunked
                # framing path. FIFO_SIZE is the number of bytes already
                # buffered by the host-side transfer layer.
                csv_path = run_dir / variant_entry["csv_path"]
                frame_counter_bits = 28 - data_size
                frame_counter_modulus = 1 << frame_counter_bits
                expected_capture_s = params.conversions * len(params.seq_init_pattern) / symbol_rate_bps
                capture_timeout_s = max(
                    FASTRX_CAPTURE_TIMEOUT_S,
                    2.0 * expected_capture_s + 2.0,
                )

                # seq_gen soft reset preserves its waveform RAM. Reset and
                # re-arm the producer and receiver once, before the continuous
                # acquisition, and clear any previously buffered TCP data.
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

                # Allow the final word to cross the FastRX CDC, FPGA output
                # FIFO, TCP socket, and background host readout thread.
                sleep(FASTRX_TRAILING_DRAIN_S)
                raw_data = daq["fifo0"].get_data()
                if len(raw_data) != params.conversions:
                    raise RuntimeError(f"expected {params.conversions} FastRX words, received {len(raw_data)}")

                fastrx_lost_count = int(daq["fastrx0"].get_lost_count())
                if fastrx_lost_count:
                    raise RuntimeError(f"FastRX lost {fastrx_lost_count} words during the continuous acquisition")

                # Decode and write in bounded host-memory batches. These CSV
                # batches do not interrupt or segment the physical capture.
                rows_written = 0
                preview_rows = []
                rows = []
                for conversion_index, word in enumerate(raw_data):
                    raw_word = int(word)
                    identifier, frame, spi_data = daq["fastrx0"].parse_word(raw_word)
                    if identifier != 1:
                        raise RuntimeError(
                            f"FastRX conversion {conversion_index} has identifier {identifier:#x}, expected 0x1"
                        )
                    expected_frame = conversion_index % frame_counter_modulus
                    if frame != expected_frame:
                        raise RuntimeError(
                            f"FastRX conversion {conversion_index} has frame {frame}, expected {expected_frame}"
                        )
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
                    row = AdcConversion(
                        conversion_index=conversion_index,
                        raw_word=raw_word,
                        identifier=identifier,
                        frame=frame,
                        spi=spi_data,
                        bout=bout,
                        dout_raw=dout_raw,
                        dout=dout,
                    )
                    rows.append(row)
                    if len(preview_rows) < MAX_RAW_FASTRX_WORDS:
                        preview_rows.append(row)
                    if len(rows) == CSV_WRITE_BATCH_ROWS or conversion_index + 1 == params.conversions:
                        rows_written += write_adc_conversions(
                            csv_path,
                            rows,
                            append=rows_written > 0,
                        )
                        rows = []

                for row in preview_rows:
                    print(
                        f"[{row.conversion_index}] ID={row.identifier:04b} frame={row.frame} "
                        f"data={row.spi:0{data_size}b} Dout={row.dout}"
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

                variant_entry.update(
                    {
                        "status": "complete",
                        "rows": rows_written,
                        "derived": {
                            "cap_weights": cap_weights,
                            "code_weights": code_weights,
                            "capture_bits": len(code_weights),
                            "sequence_words": sequence_words,
                            "actual_sample_rate_hz": symbol_rate_bps / len(params.seq_init_pattern),
                            "active_conversion_rate_hz": symbol_rate_bps / active_span_symbols,
                            "si570_frequency_hz": si570_frequency_hz,
                            "pll_divider_n": pll_divider_n,
                            "sequencer_frequency_hz": sequencer_frequency_hz,
                            "serializer_frequency_hz": serializer_frequency_hz,
                            "rx_sen_start_word": rx_sen_start_word,
                            "comp_idelay_taps": comp_idelay_taps,
                            "capture_data_arrival_s": capture_alignment.data_arrival_s,
                            "capture_edge_s": capture_alignment.capture_edge_s,
                            "capture_setup_margin_s": capture_alignment.setup_margin_s,
                            "capture_hold_margin_s": capture_alignment.hold_margin_s,
                        },
                        "readback": {
                            "smu": smu_readback,
                            "vin_cm_supply_set_v": vin_cm_supply_v,
                            "vin_cm_supply_measured_v": float(vin_cm_supply.get_voltage()),
                            "vin_cm_supply_measured_a": float(vin_cm_supply.get_current()),
                            "stimulus": stimulus_readback,
                            "spi_mismatches": spi_mismatches,
                            "fastrx_lost_count": fastrx_lost_count,
                        },
                    }
                )
                manifest_path.write_text(json.dumps(to_json_data(manifest), indent=2, sort_keys=True) + "\n")
                print(f"Saved {rows_written} conversions to {csv_path}")

                awg.set_enable(0)
                vin_cm_supply.set_enable(0)
            except Exception as error:
                variant_entry["status"] = "failed"
                variant_entry["error"] = f"{type(error).__name__}: {error}"
                manifest["status"] = "failed"
                manifest_path.write_text(json.dumps(to_json_data(manifest), indent=2, sort_keys=True) + "\n")
                raise

        manifest["status"] = "complete"
        manifest["completed_at"] = datetime.now().astimezone().isoformat()
        manifest_path.write_text(json.dumps(to_json_data(manifest), indent=2, sort_keys=True) + "\n")
        print(f"Completed {len(variants)} variants; manifest: {manifest_path}")
    except Exception as error:
        manifest["status"] = "failed"
        manifest["error"] = f"{type(error).__name__}: {error}"
        manifest_path.write_text(json.dumps(to_json_data(manifest), indent=2, sort_keys=True) + "\n")
        raise
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
                print(f"Warning: could not restore the default FPGA clock: {error}")
        if awg is not None:
            try:
                awg.set_DC("DEF,DEF,0")
                awg.set_enable(0)
            except Exception as error:
                print(f"Warning: could not disable the AWG: {error}")
        if vin_cm_supply is not None:
            try:
                vin_cm_supply.set_enable(0)
                vin_cm_supply.set_voltage(0.0)
            except Exception as error:
                print(f"Warning: could not disable the Vin_cm supply: {error}")
        for smu, _rail, _field in smus:
            try:
                smu.off()
                smu.set_voltage(0.0)
            except Exception as error:
                print(f"Warning: could not disable an SMU: {error}")
        for dut in reversed(initialized_duts):
            dut.close()


if __name__ == "__main__":
    main()
