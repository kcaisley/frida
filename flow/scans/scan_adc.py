"""Acquire one physical ADC data file for each configured parameter variant."""

from __future__ import annotations

import itertools
import math
import re
from collections.abc import Mapping, Sequence
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from time import monotonic, sleep
from typing import Any

import hdl21 as h
import numpy as np
from bitarray import bitarray
from pyvisa.errors import VisaIOError

from flow.analysis.io import scope_records_to_adc_wave, write_measurement
from flow.analysis.types import AdcDaq, MeasAdcExt, MeasInfo
from flow.cdac import get_cdac_weights
from flow.scans.fastrx import calculate_fastrx_capture_alignment, convert_fastrx_words_to_adc
from flow.scans.params import AdcTbParams, build_ramp_variants, build_variants, load_board_map, validate_params
from flow.scans.plldrp import calculate_pll_frequency, select_pll_configuration, set_pll_divider
from flow.scans.scope import wait_for_scope_armed, wait_for_scope_capture
from flow.scans.seqgen import convert_params_to_seqgen_fmt

SCAN_OUTDIR = Path(__file__).resolve().parents[2] / "build" / "scan_adc"


def convert_vdiff_input_to_awg_supply(
    vin_diff: float,
    vin_cm: float,
    calibration: Mapping[str, Any] | None = None,
) -> tuple[float, float]:
    """Convert desired ADC-side Vdiff and Vin_cm to instrument setpoints.

    ``vin_diff`` is ``Vin_p - Vin_n`` at the ADC. The returned tuple is the
    single-ended AWG voltage and E3634A setpoint. This function performs no
    instrument I/O. With no explicit calibration it uses board 00 from
    ``map_board.yaml`` for convenient software tests and loopback scripts.
    """

    if calibration is None:
        calibration = load_board_map()["boards"]["00"]["input_calibration"]

    amplitude_v = abs(vin_diff)
    small_signal_limit_v = calibration.get("small_signal_maximum_abs_vdiff_v")
    blend_maximum_v = calibration.get("small_to_large_blend_maximum_abs_vdiff_v")
    if blend_maximum_v is not None:
        if small_signal_limit_v is None:
            raise ValueError("small-to-large input-calibration blend requires a small-signal limit")
        blend_maximum_v = float(blend_maximum_v)
        if not math.isfinite(blend_maximum_v) or blend_maximum_v <= float(small_signal_limit_v):
            raise ValueError("small-to-large input-calibration blend maximum must exceed the small-signal limit")
    use_small_signal = small_signal_limit_v is not None and amplitude_v <= float(small_signal_limit_v) + 1.0e-15
    use_blend = (
        small_signal_limit_v is not None
        and blend_maximum_v is not None
        and float(small_signal_limit_v) < amplitude_v < blend_maximum_v
    )
    small_signal_gain: float | None = None
    small_signal_center_v: float | None = None
    if use_small_signal or use_blend:
        common_modes = np.asarray(calibration["small_signal_common_mode_v"], dtype=np.float64)
        magnitude_values = np.asarray(
            calibration["small_signal_awg_vdiff_magnitude_v_per_vdiff"],
            dtype=np.float64,
        )
        center_values = np.asarray(calibration["small_signal_awg_center_v"], dtype=np.float64)
        if (
            common_modes.ndim != 1
            or len(common_modes) < 2
            or len(magnitude_values) != len(common_modes)
            or len(center_values) != len(common_modes)
            or not np.all(np.isfinite(common_modes))
            or not np.all(np.isfinite(magnitude_values))
            or not np.all(np.isfinite(center_values))
            or np.any(np.diff(common_modes) <= 0.0)
            or np.any(magnitude_values <= 0.0)
        ):
            raise ValueError("small-signal input calibration table is malformed")
        if not common_modes[0] <= vin_cm <= common_modes[-1]:
            raise ValueError("Vin_cm is outside the small-signal input calibration table")
        small_signal_gain = float(np.interp(vin_cm, common_modes, magnitude_values))
        small_signal_center_v = float(np.interp(vin_cm, common_modes, center_values))
    if use_small_signal:
        assert small_signal_gain is not None
        assert small_signal_center_v is not None
        awg_v_per_vdiff = small_signal_gain
        awg_center_v = small_signal_center_v
    else:
        polynomial_minimum_vin_cm_v = float(
            calibration.get("polynomial_minimum_vin_cm_v", calibration["minimum_vin_cm_v"])
        )
        polynomial_maximum_vin_cm_v = float(
            calibration.get("polynomial_maximum_vin_cm_v", calibration["maximum_vin_cm_v"])
        )
        if not polynomial_minimum_vin_cm_v <= vin_cm <= polynomial_maximum_vin_cm_v:
            raise ValueError("Vin_cm is outside the large-signal input calibration range")
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
        if use_blend:
            assert small_signal_limit_v is not None
            assert blend_maximum_v is not None
            assert small_signal_gain is not None
            assert small_signal_center_v is not None
            boundary_amplitude_v = float(small_signal_limit_v)
            boundary_basis = (
                1.0,
                boundary_amplitude_v,
                boundary_amplitude_v**2,
                common_mode_delta_v,
                boundary_amplitude_v * common_mode_delta_v,
                common_mode_delta_v**2,
            )
            polynomial_boundary_gain = sum(
                float(coefficient) * term
                for coefficient, term in zip(
                    calibration["awg_vdiff_magnitude_coefficients"],
                    boundary_basis,
                    strict=True,
                )
            )
            polynomial_boundary_center_v = sum(
                float(coefficient) * term
                for coefficient, term in zip(
                    calibration["awg_center_coefficients"],
                    boundary_basis,
                    strict=True,
                )
            )
            correction_weight = (blend_maximum_v - amplitude_v) / (blend_maximum_v - boundary_amplitude_v)
            awg_v_per_vdiff += correction_weight * (small_signal_gain - polynomial_boundary_gain)
            awg_center_v += correction_weight * (small_signal_center_v - polynomial_boundary_center_v)
    awg_voltage = awg_center_v + vin_diff * awg_v_per_vdiff
    supply_common_modes = calibration.get("vin_cm_supply_common_mode_v")
    if supply_common_modes is None:
        vin_cm_supply_voltage = (
            float(calibration["vin_cm_supply_offset_v"]) + float(calibration["vin_cm_supply_gain"]) * vin_cm
        )
    else:
        supply_common_modes_array = np.asarray(supply_common_modes, dtype=np.float64)
        supply_setpoints = np.asarray(calibration["vin_cm_supply_set_v"], dtype=np.float64)
        if (
            supply_common_modes_array.ndim != 1
            or len(supply_common_modes_array) < 2
            or len(supply_setpoints) != len(supply_common_modes_array)
            or not np.all(np.isfinite(supply_common_modes_array))
            or not np.all(np.isfinite(supply_setpoints))
            or np.any(np.diff(supply_common_modes_array) <= 0.0)
        ):
            raise ValueError("Vin_cm supply calibration table is malformed")
        if not supply_common_modes_array[0] <= vin_cm <= supply_common_modes_array[-1]:
            raise ValueError("Vin_cm is outside the supply calibration table")
        vin_cm_supply_voltage = float(np.interp(vin_cm, supply_common_modes_array, supply_setpoints))
    return awg_voltage, vin_cm_supply_voltage


def convert_dac_caps_to_adc_weights(cap_weights: list[int] | tuple[int, ...]) -> list[int]:
    """Convert CDAC unit-cap weights C16..C1 to decision weights W16..W0."""

    if not cap_weights or any(
        isinstance(weight, bool) or not isinstance(weight, int) or weight <= 0 for weight in cap_weights
    ):
        raise ValueError("CDAC weights must be a non-empty sequence of positive integers")
    return [2 * weight for weight in cap_weights] + [1]


def convert_dout_to_normalized_dout(dout: int, code_weights: list[int], adc_bits: int) -> int:
    """Scale ideal-weight raw Dout onto the configured nominal ADC range."""

    if adc_bits <= 0:
        raise ValueError("adc_bits must be positive")
    return round(dout * ((1 << adc_bits) - 1) / sum(code_weights))


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
    if any(right[0] <= left[0] for left, right in itertools.pairwise(points)):
        raise ValueError("PWL times must increase strictly")
    return points


def main(variants: Sequence[AdcTbParams] | None = None) -> None:
    """Run the supplied physical variants into a fresh timestamped directory."""

    SETUP_SETTLE_S = 0.2
    SMU_SETTLE_S = 0.5
    SMU_CURRENT_NPLC = 10.0
    ACTIVE_POWER_SETTLE_S = 0.1
    SI570_SETTLE_S = 0.02
    FASTRX_CAPTURE_TIMEOUT_S = 5.0
    FASTRX_TRAILING_DRAIN_S = 0.01
    MAX_RAW_FASTRX_WORDS = 20
    SCOPE_TRACKS = {
        "vin_diff_v": 1,
        "seq_comp_v": 2,
        "seq_logic_v": 3,
        "comp_out_v": 4,
    }
    SCOPE_TRIGGER_CHANNEL = 3
    SCOPE_RECORD_LENGTH = 10_000
    SCOPE_BANDWIDTH_HZ = {
        "vin_diff_v": 200.0e6,
        "seq_comp_v": 2.0e9,
        "seq_logic_v": 2.0e9,
        "comp_out_v": 2.0e9,
    }
    SCOPE_VERTICAL_SCALE_V = {
        # Use 50 mV/div so the 50 and 100 mV DC campaigns remain comfortably
        # inside CH1's zero-offset acquisition range.
        "vin_diff_v": 0.05,
        "seq_comp_v": 0.2,
        "seq_logic_v": 0.2,
        "comp_out_v": 0.2,
    }
    SCOPE_CAPTURE_TIMEOUT_S = 5.0

    variants = list(build_variants() if variants is None else variants)
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

    supply_limits = board["supply_limits"]
    minimum_supply_v = float(supply_limits["minimum_voltage_v"])
    maximum_supply_v = float(supply_limits["maximum_voltage_v"])
    signal_headroom_v = float(supply_limits["signal_headroom_v"])
    fixed_vdd_io_v = float(board["fixed_vdd_io_v"])
    calibration = board["input_calibration"]
    for params in variants:
        if not math.isclose(float(params.vdd_io.dc), fixed_vdd_io_v, abs_tol=1.0e-12):
            raise ValueError(
                f"VDD_IO is fixed at {fixed_vdd_io_v:g} V on {board_id}; variant requests {float(params.vdd_io.dc):g} V"
            )
        for rail, field in (("VDD_A", "vdd_a"), ("VDD_D", "vdd_d"), ("VDD_DAC", "vdd_dac")):
            requested_voltage_v = float(getattr(params, field).dc)
            if not minimum_supply_v <= requested_voltage_v <= maximum_supply_v:
                raise ValueError(
                    f"{rail} request {requested_voltage_v:g} V is outside {minimum_supply_v:g}..{maximum_supply_v:g} V"
                )

        vin_cm_v = float(params.vin_cm.dc)
        source = params.vin_diff
        if isinstance(source, h.Vdc.Params):
            vin_diff_min_v = vin_diff_max_v = float(source.dc)
        elif isinstance(source, h.Vsin.Params):
            if source.voff is None or source.vamp is None or source.freq is None:
                raise ValueError("sine stimulus requires voff, vamp, and freq")
            vin_diff_min_v = float(source.voff) - float(source.vamp)
            vin_diff_max_v = float(source.voff) + float(source.vamp)
        elif isinstance(source, h.Vpwl.Params):
            points = parse_pwl_wave(source.wave)
            if len(points) not in (2, 3):
                raise ValueError("physical PWL input must be a two-point ramp or three-point triangle")
            if len(points) == 3 and not math.isclose(points[0][1], points[-1][1], abs_tol=1.0e-12):
                raise ValueError("three-point physical PWL input must return to its starting voltage")
            vin_diff_min_v = min(value for _time, value in points)
            vin_diff_max_v = max(value for _time, value in points)
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
        _awg_at_min_v, vin_cm_supply_v = convert_vdiff_input_to_awg_supply(
            vin_diff_min_v,
            vin_cm_v,
            calibration,
        )
        _awg_at_max_v, second_supply_v = convert_vdiff_input_to_awg_supply(
            vin_diff_max_v,
            vin_cm_v,
            calibration,
        )
        if not math.isclose(vin_cm_supply_v, second_supply_v, abs_tol=1.0e-12):
            raise RuntimeError("Vin_cm calibration changed across differential-input endpoints")
        if not 0.0 <= vin_cm_supply_v <= maximum_supply_v:
            raise ValueError(f"calibrated Vin_cm supply request {vin_cm_supply_v:g} V is unsafe")

        minimum_input_v = -signal_headroom_v
        maximum_input_v = float(params.vdd_a.dc) + signal_headroom_v
        for vin_diff_v in (vin_diff_min_v, vin_diff_max_v):
            vin_p_v = vin_cm_v + vin_diff_v / 2.0
            vin_n_v = vin_cm_v - vin_diff_v / 2.0
            if not (
                minimum_input_v - 1.0e-12 <= vin_p_v <= maximum_input_v + 1.0e-12
                and minimum_input_v - 1.0e-12 <= vin_n_v <= maximum_input_v + 1.0e-12
            ):
                raise ValueError(
                    f"ADC inputs {(vin_p_v, vin_n_v)} V are outside {minimum_input_v:g}..{maximum_input_v:g} V"
                )

    run_timestamp = datetime.now().astimezone().strftime("%Y%m%d_%H%M%S")
    run_dir = SCAN_OUTDIR / run_timestamp
    run_dir.mkdir(parents=True, exist_ok=False)

    from gpib_ctypes import make_default_gpib

    make_default_gpib()
    from basil.dut import Dut

    map_dir = Path(__file__).resolve().parent
    daq_dut = Dut(str(map_dir / "map_fpga.yaml"))
    awg_dut = Dut(str(map_dir / "map_awg.yaml"))
    vin_cm_dut = Dut(str(map_dir / "map_supply.yaml"))
    smu_dut = Dut(str(map_dir / "map_smu.yaml"))
    scope_dut = Dut(str(map_dir / "map_scope.yaml"))
    initialized_duts = []
    daq = awg = vin_cm_supply = scope = None
    smus = []
    instrument_identities = {}

    try:
        for dut in (daq_dut, awg_dut, vin_cm_dut, smu_dut, scope_dut):
            dut.init()
            initialized_duts.append(dut)

        daq = daq_dut
        awg = awg_dut["awg"]
        vin_cm_supply = vin_cm_dut["vocm_supply"]
        scope = scope_dut["scope"]
        smus = [
            (smu_dut["smu1"], "VDD_A", "vdd_a"),
            (smu_dut["smu2"], "VDD_D", "vdd_d"),
            (smu_dut["smu3"], "VDD_DAC", "vdd_dac"),
        ]
        instrument_identities = {
            "awg": str(awg.get_name()).strip(),
            "vin_cm_supply": str(vin_cm_supply.get_name()).strip(),
            "scope": str(scope.get_name()).strip(),
            **{field: str(smu.get_name()).strip() for smu, _rail, field in smus},
        }

        awg.set_enable(0)
        vin_cm_supply.set_enable(0)
        vin_cm_supply.set_voltage(0.0)
        for smu, _rail, _field in smus:
            smu.off()
            smu.set_voltage(0.0)

        scope.set_acquire_state("STOP")
        scope.set_acquire_mode("SAMPLE")
        scope.set_acquire_stop_after("SEQUENCE")
        scope.set_horizontal_record_length(SCOPE_RECORD_LENGTH)
        scope._intf.write("HORizontal:POSition 20")
        for signal_name, channel in SCOPE_TRACKS.items():
            scope._intf.write(f"DISplay:GLObal:CH{channel}:STATE ON")
            scope.set_coupling("DC", channel=channel)
            scope.set_vertical_scale(SCOPE_VERTICAL_SCALE_V[signal_name], channel=channel)
            scope.set_vertical_position(0.0, channel=channel)
            scope.set_vertical_offset(0.0, channel=channel)
            scope.set_bandwidth(SCOPE_BANDWIDTH_HZ[signal_name], channel=channel)
        scope.set_trigger_type("EDGE")
        scope.set_trigger_source(channel=SCOPE_TRIGGER_CHANNEL)
        scope.set_trigger_edge_slope("RISE")
        scope.set_trigger_level(0.0, channel=SCOPE_TRIGGER_CHANNEL)
        scope.set_trigger_mode("NORMAL")

        for variant_index, params in enumerate(variants):
            try:
                print(
                    f"\n=== variant {variant_index + 1}/{len(variants)}: "
                    f"ADC {params.observed_adc:02d}, {float(params.symbol_rate) / 1e6:g} MBd ==="
                )
                loaded_voltage_tolerance_v = float(supply_limits["loaded_voltage_tolerance_v"])

                smu_readback = {}
                for smu, rail, field in smus:
                    requested_voltage_v = float(getattr(params, field).dc)
                    if not minimum_supply_v <= requested_voltage_v <= maximum_supply_v:
                        raise ValueError(
                            f"{rail} request {requested_voltage_v:g} V is outside "
                            f"{minimum_supply_v:g}..{maximum_supply_v:g} V"
                        )
                    smu.off()
                    smu.set_voltage(0.0)
                    smu.source_volt()
                    smu.four_wire_off()
                    smu.set_voltage_range(float(supply_limits["smu_voltage_range_v"]))
                    smu.set_current_limit(float(supply_limits["smu_current_compliance_a"]))
                    smu.current_sense_autorange_on()
                    smu.set_current_nplc(SMU_CURRENT_NPLC)
                    smu.autozero_on()
                    smu.set_voltage(requested_voltage_v)

                for smu, _rail, _field in smus:
                    smu.on()
                sleep(SMU_SETTLE_S)

                for smu, rail, field in smus:
                    requested_voltage_v = float(getattr(params, field).dc)
                    for read_attempt in range(3):
                        try:
                            measured_voltage_v = float(smu.get_voltage())
                            measured_current_a = float(smu.get_current())
                            break
                        except (UnicodeDecodeError, ValueError, VisaIOError) as error:
                            if read_attempt == 2:
                                raise RuntimeError(f"{rail} readback failed after three attempts") from error
                            print(f"WARNING: retrying malformed {rail} GPIB readback: {error}")
                            # Linux-GPIB occasionally leaves a partial reply in
                            # the device buffer. Selected-device clear discards
                            # it without changing the programmed source values.
                            smu._intf._resource.clear()
                            sleep(0.1)
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
                minimum_input_v = -signal_headroom_v
                maximum_input_v = float(params.vdd_a.dc) + signal_headroom_v
                for vin_diff_v in (vin_diff_min_v, vin_diff_max_v):
                    vin_p_v = vin_cm_v + vin_diff_v / 2.0
                    vin_n_v = vin_cm_v - vin_diff_v / 2.0
                    if not (
                        minimum_input_v - 1.0e-12 <= vin_p_v <= maximum_input_v + 1.0e-12
                        and minimum_input_v - 1.0e-12 <= vin_n_v <= maximum_input_v + 1.0e-12
                    ):
                        raise ValueError(
                            f"ADC inputs {(vin_p_v, vin_n_v)} V are outside {minimum_input_v:g}..{maximum_input_v:g} V"
                        )

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
                # 17-bit result is checked against simultaneous CH4 scope
                # captures by test_fastrx.py, including alignment-boundary
                # and maximum-rate points.
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
                    validate_params(params)
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

                # Measure active-conversion power while the parameterized
                # sequencer pattern repeats continuously. FastRX is disabled
                # for this separate power interval so its FIFO cannot grow
                # while the three slow Keithley readings are taken. Each
                # current value is one 10-NPLC average, not a time waveform.
                daq["seq0"].reset()
                daq["fastrx0"].reset()
                daq["fastrx0"].set_en(False)
                sleep(0.001)

                # Establish the static baseline after the ADC slow-control
                # image and input stimulus are configured, but while the
                # sequencer and FastRX remain stopped. The power analysis
                # subtracts these readings from the active readings below.
                for smu, rail, field in smus:
                    for read_attempt in range(3):
                        try:
                            static_voltage_v = float(smu.get_voltage())
                            static_average_current_a = float(smu.get_current())
                            break
                        except (UnicodeDecodeError, ValueError, VisaIOError) as error:
                            if read_attempt == 2:
                                raise RuntimeError(f"{rail} static readback failed after three attempts") from error
                            print(f"WARNING: retrying malformed static {rail} GPIB readback: {error}")
                            smu._intf._resource.clear()
                            sleep(0.1)
                    if static_voltage_v > maximum_supply_v + 5e-3:
                        raise RuntimeError(f"{rail} measured unsafe static voltage {static_voltage_v:g} V")
                    if static_voltage_v < float(getattr(params, field).dc) - loaded_voltage_tolerance_v:
                        raise RuntimeError(
                            f"{rail} static voltage {static_voltage_v:g} V is more than "
                            f"{loaded_voltage_tolerance_v:g} V below its setpoint"
                        )
                    smu_readback[field].update(
                        {
                            "static_voltage_v": static_voltage_v,
                            "static_average_current_a": static_average_current_a,
                            "static_average_power_w": abs(static_voltage_v * static_average_current_a),
                        }
                    )

                daq["seq0"].set_size(sequence_words)
                daq["seq0"].set_clk_divide(1)
                daq["seq0"].set_repeat(0)
                daq["seq0"].set_en_ext_start(False)
                daq["fifo0"]["RESET"]
                daq["fifo0"].get_data()
                daq["seq0"].start()
                sleep(ACTIVE_POWER_SETTLE_S)
                try:
                    for smu, rail, field in smus:
                        for read_attempt in range(3):
                            try:
                                active_voltage_v = float(smu.get_voltage())
                                active_average_current_a = float(smu.get_current())
                                break
                            except (UnicodeDecodeError, ValueError, VisaIOError) as error:
                                if read_attempt == 2:
                                    raise RuntimeError(f"{rail} active readback failed after three attempts") from error
                                print(f"WARNING: retrying malformed active {rail} GPIB readback: {error}")
                                smu._intf._resource.clear()
                                sleep(0.1)
                        if active_voltage_v > maximum_supply_v + 5e-3:
                            raise RuntimeError(f"{rail} measured unsafe active voltage {active_voltage_v:g} V")
                        if active_voltage_v < float(getattr(params, field).dc) - loaded_voltage_tolerance_v:
                            raise RuntimeError(
                                f"{rail} active voltage {active_voltage_v:g} V is more than "
                                f"{loaded_voltage_tolerance_v:g} V below its setpoint"
                            )
                        smu_readback[field].update(
                            {
                                "active_voltage_v": active_voltage_v,
                                "active_average_current_a": active_average_current_a,
                                "active_average_power_w": abs(active_voltage_v * active_average_current_a),
                            }
                        )
                finally:
                    daq["seq0"].reset()
                    sleep(0.001)

                # Capture every requested conversion in one uninterrupted
                # sequencer run. The 65,536-word FPGA FIFO feeds gigabit
                # SiTCP, whose Basil transfer layer drains continuously into
                # host memory. test_fastrx.py exercises the same unchunked
                # framing path. FIFO_SIZE is the number of bytes already
                # buffered by the host-side transfer layer.
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

                # Arm one representative four-channel scope acquisition before
                # starting the shared sequencer/FastRX run. The HDF5 writer
                # associates this record with conversion zero; the remaining
                # conversions retain only their DAQ values.
                conversion_period_s = len(params.seq_init_pattern) / symbol_rate_bps
                scope.set_horizontal_scale(conversion_period_s / 8.0)
                scope.set_acquire_state("RUN")
                acquisition_count_before = wait_for_scope_armed(
                    scope,
                    timeout_s=SCOPE_CAPTURE_TIMEOUT_S,
                )

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
                wait_for_scope_capture(
                    scope,
                    acquisition_count_before,
                    timeout_s=SCOPE_CAPTURE_TIMEOUT_S,
                )
                scope_waveforms = scope.get_waveforms(
                    {channel: name.removesuffix("_v") for name, channel in SCOPE_TRACKS.items()}
                )
                missing_scope_channels = sorted(set(SCOPE_TRACKS.values()).difference(scope_waveforms))
                if missing_scope_channels:
                    raise RuntimeError(f"scope did not return channels {missing_scope_channels}")

                fastrx_lost_count = int(daq["fastrx0"].get_lost_count())
                if fastrx_lost_count:
                    raise RuntimeError(f"FastRX lost {fastrx_lost_count} words during the continuous acquisition")

                conversion_index_values = np.arange(params.conversions, dtype=np.int64)
                conversion_times_s = conversion_index_values * conversion_period_s
                if isinstance(source, h.Vdc.Params):
                    vin_diff_values_v = np.full(params.conversions, float(source.dc))
                elif isinstance(source, h.Vsin.Params):
                    phase_rad = math.radians(float(source.phase or 0.0))
                    delay_s = float(source.td or 0.0)
                    vin_diff_values_v = np.full(params.conversions, float(source.voff))
                    active = conversion_times_s >= delay_s
                    vin_diff_values_v[active] += float(source.vamp) * np.sin(
                        2.0 * np.pi * float(source.freq) * (conversion_times_s[active] - delay_s) + phase_rad
                    )
                elif isinstance(source, h.Vpwl.Params):
                    points = parse_pwl_wave(source.wave)
                    point_times_s = np.asarray([point[0] for point in points])
                    point_values_v = np.asarray([point[1] for point in points])
                    period_s = point_times_s[-1] - point_times_s[0]
                    relative_times_s = np.mod(conversion_times_s - point_times_s[0], period_s) + point_times_s[0]
                    vin_diff_values_v = np.interp(relative_times_s, point_times_s, point_values_v)
                else:
                    raise TypeError(f"unsupported differential source type {type(source).__name__}")

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

                if isinstance(source, h.Vdc.Params):
                    source_label = f"dc{float(source.dc) * 1e3:+.0f}mv"
                elif isinstance(source, h.Vsin.Params):
                    source_label = (
                        f"sin{float(source.freq):g}hz_"
                        f"{float(source.voff) * 1e3:+g}mv_"
                        f"{2 * float(source.vamp) * 1e3:g}mvpp"
                    )
                else:
                    source_points = parse_pwl_wave(source.wave)
                    source_period_s = source_points[-1][0] - source_points[0][0]
                    source_label = (
                        f"pwl{1.0 / source_period_s:g}hz_"
                        f"{min(value for _time, value in source_points) * 1e3:+g}to"
                        f"{max(value for _time, value in source_points) * 1e3:+g}mv"
                    )
                source_label = source_label.replace("+", "p").replace("-", "m")
                logic_comp_offset = float(params.seq_logic_phase_delay_symbols) - float(
                    params.seq_comp_phase_delay_symbols
                )
                logic_phase_label = f"{logic_comp_offset:+g}".replace("+", "p").replace("-", "m")
                stem = (
                    f"{variant_index:04d}_{board_id}_adc{params.observed_adc:02d}_"
                    f"{float(params.symbol_rate) / 1e6:g}mbd_{source_label}_"
                    f"logic{logic_phase_label}sym_"
                    f"vcm{float(params.vin_cm.dc) * 1e3:g}mv_"
                    f"vdda{float(params.vdd_a.dc) * 1e3:g}mv_"
                    f"vddd{float(params.vdd_d.dc) * 1e3:g}mv_"
                    f"vddac{float(params.vdd_dac.dc) * 1e3:g}mv_"
                    f"t{float(params.temperature_c):g}c"
                )
                h5_path = run_dir / f"{stem}.h5"
                readbacks = {
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
                    "vin_cm_supply_set_v": vin_cm_supply_v,
                    "vin_cm_supply_measured_v": float(vin_cm_supply.get_voltage()),
                    "vin_cm_supply_measured_a": float(vin_cm_supply.get_current()),
                    "spi_mismatches": spi_mismatches,
                    "fastrx_lost_count": fastrx_lost_count,
                    "active_power_current_nplc": SMU_CURRENT_NPLC,
                    "scope_vin_diff_bandwidth_hz": SCOPE_BANDWIDTH_HZ["vin_diff_v"],
                    "scope_vin_diff_vertical_scale_v_per_div": SCOPE_VERTICAL_SCALE_V["vin_diff_v"],
                    "scope_record_length_requested": SCOPE_RECORD_LENGTH,
                }
                for field, values in smu_readback.items():
                    for quantity, value in values.items():
                        readbacks[f"{field}_{quantity}"] = value
                for name, value in stimulus_readback.items():
                    if isinstance(value, (str, int, float, bool)):
                        readbacks[f"stimulus_{name}"] = value

                measurement = MeasAdcExt(
                    info=MeasInfo(
                        schema_version=1,
                        measurement_type="MeasAdcExt",
                        backend="physical",
                        timestamp_utc=datetime.now().astimezone(),
                        instruments=instrument_identities,
                        readbacks=readbacks,
                    ),
                    param=params,
                    daq=AdcDaq(
                        conversion_index=conversion_index_values,
                        bout=bout_values,
                        dout_raw=dout_raw_values,
                        dout=dout_values,
                        vin_diff_v=vin_diff_values_v,
                        fastrx_word=fastrx_words,
                    ),
                    wave=scope_records_to_adc_wave(
                        [scope_waveforms],
                        [0],
                        SCOPE_TRACKS,
                    ),
                )
                write_measurement(h5_path, measurement)
                print(f"Saved {params.conversions} conversions and one scope record to {h5_path}")

                awg.set_enable(0)
                vin_cm_supply.set_enable(0)
            except Exception:
                print(f"Variant {variant_index + 1}/{len(variants)} failed; shutting down all hardware")
                raise

        print(f"Completed {len(variants)} variants in {run_dir}")
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
            except Exception as error:  # noqa: BLE001 - best-effort safety shutdown
                print(f"Warning: could not restore the default FPGA clock: {error}")
        if awg is not None:
            try:
                awg.set_DC("DEF,DEF,0")
                awg.set_enable(0)
            except Exception as error:  # noqa: BLE001 - best-effort safety shutdown
                print(f"Warning: could not disable the AWG: {error}")
        if vin_cm_supply is not None:
            try:
                vin_cm_supply.set_enable(0)
                vin_cm_supply.set_voltage(0.0)
            except Exception as error:  # noqa: BLE001 - best-effort safety shutdown
                print(f"Warning: could not disable the Vin_cm supply: {error}")
        for smu, _rail, _field in smus:
            try:
                smu.off()
                smu.set_voltage(0.0)
            except Exception as error:  # noqa: BLE001 - best-effort safety shutdown
                print(f"Warning: could not disable an SMU: {error}")
        for dut in reversed(initialized_duts):
            dut.close()


def ramp() -> None:
    """Capture the ADC00--ADC03 triangular-ramp code-density campaign.

    The parameters retain the intended -1 V to +1 V ADC differential input;
    :func:`main` applies the board calibration only while programming the AWG.
    """

    main(build_ramp_variants())


if __name__ == "__main__":
    main()
