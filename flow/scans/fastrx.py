"""Pure FastRX alignment and host-side word decoding for physical scans."""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np

from flow.adc.sim import AdcTbParams
from flow.cdac import get_cdac_weights


@dataclass(frozen=True, slots=True)
class FastRxCaptureAlignment:
    """One analytically selected FastRX timing aperture."""

    rx_sen_start_word: int
    comp_idelay_taps: int
    control_phase_advance_symbols: int
    first_comp_transition_symbol: int
    earliest_data_arrival_s: float
    latest_data_arrival_s: float
    capture_edge_s: float
    setup_margin_s: float
    hold_margin_s: float


def convert_fastrx_words_to_adc(
    words: Sequence[int] | np.ndarray,
    data_size: int,
    code_weights: list[int],
    adc_bits: int,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Decode FastRX into chronological B0..B16 and 12-bit DOUT.

    The payload is transported high bit first, but the returned column index is
    the decision index: column zero is B0 and column 16 is terminal B16. Every
    decision contributes to ``dout_raw`` and the normalized D0..D11 code.
    """

    fastrx_words = np.asarray(words, dtype=np.uint32)
    if fastrx_words.ndim != 1:
        raise ValueError("FastRX words must be one-dimensional")
    if not 1 <= data_size <= 28:
        raise ValueError("FastRX data_size must be in 1..28")
    if len(code_weights) != data_size:
        raise ValueError(f"received {data_size} FastRX bits for {len(code_weights)} ADC weights")
    if adc_bits <= 0:
        raise ValueError("adc_bits must be positive")

    identifiers = (fastrx_words >> 28) & 0xF
    invalid_identifiers = np.flatnonzero(identifiers != 1)
    if invalid_identifiers.size:
        index = int(invalid_identifiers[0])
        raise RuntimeError(f"FastRX conversion {index} has identifier {int(identifiers[index]):#x}, expected 0x1")

    frame_counter_bits = 28 - data_size
    frame_counter_modulus = 1 << frame_counter_bits
    frames = (fastrx_words >> data_size) & (frame_counter_modulus - 1)
    expected_frames = np.arange(len(fastrx_words), dtype=np.uint32) % frame_counter_modulus
    invalid_frames = np.flatnonzero(frames != expected_frames)
    if invalid_frames.size:
        index = int(invalid_frames[0])
        raise RuntimeError(
            f"FastRX conversion {index} has frame {int(frames[index])}, expected {int(expected_frames[index])}"
        )

    spi_data = fastrx_words & ((1 << data_size) - 1)
    bit_positions = np.arange(data_size - 1, -1, -1, dtype=np.uint32)
    bout = ((spi_data[:, None] >> bit_positions) & 1).astype(np.uint8)
    weights = np.asarray(code_weights, dtype=np.int64)
    dout_raw = bout @ weights
    normalized_code_max = (1 << adc_bits) - 1
    dout = np.rint(dout_raw * normalized_code_max / np.sum(weights)).astype(np.int64)
    return bout, dout_raw, dout


def convert_fastrx_words_to_comp(
    words: Sequence[int] | np.ndarray,
    *,
    data_size: int,
) -> tuple[np.ndarray, np.ndarray]:
    """Validate partial FastRX frames and return decisions and frame numbers."""

    fastrx_words = np.asarray(words, dtype=np.uint32)
    if fastrx_words.ndim != 1 or len(fastrx_words) == 0:
        raise ValueError("FastRX words must be a non-empty one-dimensional sequence")
    if not 1 <= data_size <= 28:
        raise ValueError("FastRX data_size must be in 1..28")
    identifiers = (fastrx_words >> 28) & 0xF
    invalid_identifiers = np.flatnonzero(identifiers != 1)
    if invalid_identifiers.size:
        index = int(invalid_identifiers[0])
        raise RuntimeError(f"FastRX trial {index} has identifier {int(identifiers[index]):#x}, expected 0x1")

    frame_bits = 28 - data_size
    frame_modulus = 1 << frame_bits
    frames = (fastrx_words >> data_size) & (frame_modulus - 1)
    expected_frames = np.arange(len(fastrx_words), dtype=np.uint32) % frame_modulus
    invalid_frames = np.flatnonzero(frames != expected_frames)
    if invalid_frames.size:
        index = int(invalid_frames[0])
        raise RuntimeError(
            f"FastRX trial {index} has frame {int(frames[index])}, expected {int(expected_frames[index])}"
        )

    payload = fastrx_words & ((1 << data_size) - 1)
    invalid_payload = np.flatnonzero(payload & ~np.uint32(1))
    if invalid_payload.size:
        index = int(invalid_payload[0])
        raise RuntimeError(f"FastRX trial {index} has nonzero unused partial-frame bits")
    return (payload & 1).astype(np.uint8), frames.astype(np.uint32)


def calculate_fastrx_capture_alignment(
    params: AdcTbParams,
    *,
    seqgen_pipeline_cycles: float,
    oserdes_to_output_s: float,
    external_comp_delay_min_s: float,
    external_comp_delay_max_s: float,
    comp_input_to_fastrx_d_s: float,
    launch_to_capture_clock_skew_s: float,
    idelay_tap_s: float,
    idelay_tap_count: int,
    idelay_setup_backoff_taps: int,
    maximum_control_phase_advance_symbols: int,
    minimum_capture_margin_s: float,
) -> FastRxCaptureAlignment:
    """Center FastRX sampling inside the measured comparator-data aperture."""

    numeric_fields = {
        "seqgen_pipeline_cycles": seqgen_pipeline_cycles,
        "oserdes_to_output_s": oserdes_to_output_s,
        "external_comp_delay_min_s": external_comp_delay_min_s,
        "external_comp_delay_max_s": external_comp_delay_max_s,
        "comp_input_to_fastrx_d_s": comp_input_to_fastrx_d_s,
        "launch_to_capture_clock_skew_s": launch_to_capture_clock_skew_s,
        "idelay_tap_s": idelay_tap_s,
        "minimum_capture_margin_s": minimum_capture_margin_s,
    }
    for field, value in numeric_fields.items():
        if not math.isfinite(value) or value < 0.0:
            raise ValueError(f"{field} must be finite and non-negative")
    if isinstance(idelay_tap_count, bool) or not isinstance(idelay_tap_count, int) or idelay_tap_count <= 0:
        raise ValueError("idelay_tap_count must be a positive integer")
    if (
        isinstance(idelay_setup_backoff_taps, bool)
        or not isinstance(idelay_setup_backoff_taps, int)
        or idelay_setup_backoff_taps < 0
    ):
        raise ValueError("idelay_setup_backoff_taps must be a non-negative integer")
    if (
        isinstance(maximum_control_phase_advance_symbols, bool)
        or not isinstance(maximum_control_phase_advance_symbols, int)
        or not 0 <= maximum_control_phase_advance_symbols <= 7
    ):
        raise ValueError("maximum_control_phase_advance_symbols must be an integer in 0..7")
    if external_comp_delay_min_s > external_comp_delay_max_s:
        raise ValueError("external comparator minimum delay must not exceed its maximum delay")
    symbol_rate_bps = float(params.symbol_rate)
    sequencer_period_s = 8.0 / symbol_rate_bps
    sequence_words = len(params.seq_comp_pattern) // 8
    capture_bits = len(get_cdac_weights(params.dut.cdac)) + 1
    if not float(params.seq_comp_phase_delay_symbols).is_integer():
        raise ValueError("physical seq_comp_phase_delay_symbols must be a whole number of serialized symbols")

    candidates = []
    for phase_advance in range(maximum_control_phase_advance_symbols + 1):
        phase_symbols = int(params.seq_comp_phase_delay_symbols) - phase_advance
        shift = phase_symbols % len(params.seq_comp_pattern)
        comp_pattern = (
            params.seq_comp_pattern[-shift:] + params.seq_comp_pattern[:-shift] if shift else params.seq_comp_pattern
        )
        first_transition = next(
            (index for index in range(1, len(comp_pattern)) if comp_pattern[index] != comp_pattern[index - 1]),
            -1,
        )
        if first_transition < 0:
            raise ValueError("seq_comp_pattern contains no transition")
        common_delay_s = (
            first_transition / symbol_rate_bps
            + seqgen_pipeline_cycles * sequencer_period_s
            + oserdes_to_output_s
            + comp_input_to_fastrx_d_s
            + launch_to_capture_clock_skew_s
        )
        for taps in range(idelay_tap_count):
            tap_delay_s = taps * idelay_tap_s
            earliest_arrival_s = common_delay_s + external_comp_delay_min_s + tap_delay_s
            latest_arrival_s = common_delay_s + external_comp_delay_max_s + tap_delay_s
            for capture_word in range(sequence_words - capture_bits):
                capture_edge_s = capture_word * sequencer_period_s
                setup_margin_s = capture_edge_s - latest_arrival_s
                hold_margin_s = earliest_arrival_s + sequencer_period_s - capture_edge_s
                smaller_margin_s = min(setup_margin_s, hold_margin_s)
                if smaller_margin_s < minimum_capture_margin_s:
                    continue
                candidates.append(
                    (
                        smaller_margin_s,
                        -abs(setup_margin_s - hold_margin_s),
                        -phase_advance,
                        -taps,
                        capture_word,
                        phase_advance,
                        taps,
                        first_transition,
                        earliest_arrival_s,
                        latest_arrival_s,
                        setup_margin_s,
                        hold_margin_s,
                    )
                )

    if not candidates:
        raise ValueError("no safe FastRX capture aperture exists at this symbol rate")
    selected = max(candidates)
    (
        _smaller_margin_s,
        _negative_imbalance_s,
        _negative_phase_advance,
        _negative_taps,
        capture_word,
        phase_advance,
        taps,
        first_comp_transition_symbol,
        earliest_arrival_s,
        latest_arrival_s,
        setup_margin_s,
        hold_margin_s,
    ) = selected
    if idelay_tap_s > 0.0:
        hold_backoff_taps = max(
            0,
            math.floor((hold_margin_s - minimum_capture_margin_s) / idelay_tap_s + 1.0e-12),
        )
    else:
        hold_backoff_taps = 0
    applied_backoff_taps = min(taps, idelay_setup_backoff_taps, hold_backoff_taps)
    guarded_taps = taps - applied_backoff_taps
    guard_shift_s = (guarded_taps - taps) * idelay_tap_s
    taps = guarded_taps
    earliest_arrival_s += guard_shift_s
    latest_arrival_s += guard_shift_s
    setup_margin_s -= guard_shift_s
    hold_margin_s += guard_shift_s
    return FastRxCaptureAlignment(
        rx_sen_start_word=capture_word,
        comp_idelay_taps=taps,
        control_phase_advance_symbols=phase_advance,
        first_comp_transition_symbol=first_comp_transition_symbol,
        earliest_data_arrival_s=earliest_arrival_s,
        latest_data_arrival_s=latest_arrival_s,
        capture_edge_s=capture_word * sequencer_period_s,
        setup_margin_s=setup_margin_s,
        hold_margin_s=hold_margin_s,
    )


def calculate_single_sample_fastrx_capture_alignment(
    params: AdcTbParams,
    *,
    seqgen_pipeline_cycles: float,
    oserdes_to_output_s: float,
    external_comp_delay_min_s: float,
    external_comp_delay_max_s: float,
    comp_input_to_fastrx_d_s: float,
    launch_to_capture_clock_skew_s: float,
    idelay_tap_s: float,
    idelay_tap_count: int,
    idelay_setup_backoff_taps: int,
    maximum_control_phase_advance_symbols: int,
    minimum_capture_margin_s: float,
) -> FastRxCaptureAlignment:
    """Select a safe one-clock FastRX aperture after the sole COMP event."""

    numeric_fields = {
        "seqgen_pipeline_cycles": seqgen_pipeline_cycles,
        "oserdes_to_output_s": oserdes_to_output_s,
        "external_comp_delay_min_s": external_comp_delay_min_s,
        "external_comp_delay_max_s": external_comp_delay_max_s,
        "comp_input_to_fastrx_d_s": comp_input_to_fastrx_d_s,
        "launch_to_capture_clock_skew_s": launch_to_capture_clock_skew_s,
        "idelay_tap_s": idelay_tap_s,
        "minimum_capture_margin_s": minimum_capture_margin_s,
    }
    for field, value in numeric_fields.items():
        if not math.isfinite(value) or value < 0.0:
            raise ValueError(f"{field} must be finite and non-negative")
    if isinstance(idelay_tap_count, bool) or not isinstance(idelay_tap_count, int) or idelay_tap_count <= 0:
        raise ValueError("idelay_tap_count must be a positive integer")
    if (
        isinstance(idelay_setup_backoff_taps, bool)
        or not isinstance(idelay_setup_backoff_taps, int)
        or idelay_setup_backoff_taps < 0
    ):
        raise ValueError("idelay_setup_backoff_taps must be a non-negative integer")
    if (
        isinstance(maximum_control_phase_advance_symbols, bool)
        or not isinstance(maximum_control_phase_advance_symbols, int)
        or not 0 <= maximum_control_phase_advance_symbols <= 7
    ):
        raise ValueError("maximum_control_phase_advance_symbols must be an integer in 0..7")
    if external_comp_delay_min_s > external_comp_delay_max_s:
        raise ValueError("external comparator minimum delay must not exceed its maximum delay")
    if not float(params.seq_comp_phase_delay_symbols).is_integer():
        raise ValueError("physical seq_comp_phase_delay_symbols must be a whole number of serialized symbols")

    symbol_rate_bps = float(params.symbol_rate)
    sequencer_period_s = 8.0 / symbol_rate_bps
    sequence_words = len(params.seq_comp_pattern) // 8
    candidates = []
    for phase_advance in range(maximum_control_phase_advance_symbols + 1):
        phase_symbols = int(params.seq_comp_phase_delay_symbols) - phase_advance
        shift = phase_symbols % len(params.seq_comp_pattern)
        comp_pattern = (
            params.seq_comp_pattern[-shift:] + params.seq_comp_pattern[:-shift] if shift else params.seq_comp_pattern
        )
        first_transition = next(
            (index for index in range(1, len(comp_pattern)) if comp_pattern[index] != comp_pattern[index - 1]),
            -1,
        )
        if first_transition < 0:
            raise ValueError("seq_comp_pattern contains no transition")
        common_delay_s = (
            first_transition / symbol_rate_bps
            + seqgen_pipeline_cycles * sequencer_period_s
            + oserdes_to_output_s
            + comp_input_to_fastrx_d_s
            + launch_to_capture_clock_skew_s
        )
        for taps in range(idelay_tap_count):
            tap_delay_s = taps * idelay_tap_s
            earliest_arrival_s = common_delay_s + external_comp_delay_min_s + tap_delay_s
            latest_arrival_s = common_delay_s + external_comp_delay_max_s + tap_delay_s
            for capture_word in range(sequence_words - 1):
                capture_edge_s = capture_word * sequencer_period_s
                setup_margin_s = capture_edge_s - latest_arrival_s
                hold_margin_s = earliest_arrival_s + sequencer_period_s - capture_edge_s
                smaller_margin_s = min(setup_margin_s, hold_margin_s)
                if smaller_margin_s < minimum_capture_margin_s:
                    continue
                candidates.append(
                    (
                        smaller_margin_s,
                        -abs(setup_margin_s - hold_margin_s),
                        -phase_advance,
                        -taps,
                        capture_word,
                        phase_advance,
                        taps,
                        first_transition,
                        earliest_arrival_s,
                        latest_arrival_s,
                        setup_margin_s,
                        hold_margin_s,
                    )
                )
    if not candidates:
        raise ValueError("no safe one-sample FastRX capture aperture exists at this symbol rate")
    selected = max(candidates)
    (
        _smaller_margin_s,
        _negative_imbalance_s,
        _negative_phase_advance,
        _negative_taps,
        capture_word,
        phase_advance,
        taps,
        first_comp_transition_symbol,
        earliest_arrival_s,
        latest_arrival_s,
        setup_margin_s,
        hold_margin_s,
    ) = selected
    hold_backoff_taps = (
        max(0, math.floor((hold_margin_s - minimum_capture_margin_s) / idelay_tap_s + 1.0e-12))
        if idelay_tap_s > 0.0
        else 0
    )
    guarded_taps = taps - min(taps, idelay_setup_backoff_taps, hold_backoff_taps)
    guard_shift_s = (guarded_taps - taps) * idelay_tap_s
    earliest_arrival_s += guard_shift_s
    latest_arrival_s += guard_shift_s
    setup_margin_s -= guard_shift_s
    hold_margin_s += guard_shift_s
    return FastRxCaptureAlignment(
        rx_sen_start_word=capture_word,
        comp_idelay_taps=guarded_taps,
        control_phase_advance_symbols=phase_advance,
        first_comp_transition_symbol=first_comp_transition_symbol,
        earliest_data_arrival_s=earliest_arrival_s,
        latest_data_arrival_s=latest_arrival_s,
        capture_edge_s=capture_word * sequencer_period_s,
        setup_margin_s=setup_margin_s,
        hold_margin_s=hold_margin_s,
    )
