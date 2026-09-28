"""FastRX capture settings, comparator-delay programming, and word decoding."""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from itertools import pairwise
from typing import TYPE_CHECKING, Any

import numpy as np

from flow.adc.sequences import SEQUENCES, AdcSequence

if TYPE_CHECKING:
    from flow.scans.params import AdcScanParams


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


@dataclass(frozen=True, slots=True)
class FastRxCapture:
    """The two independent receive controls; ADC output rows are never changed."""

    comp_delay_taps: int
    rx_sen_start_word: int

    def __post_init__(self) -> None:
        if type(self.comp_delay_taps) is not int or not 0 <= self.comp_delay_taps <= 62:
            raise ValueError("comp_delay_taps must be an integer in 0..62")
        if type(self.rx_sen_start_word) is not int or not 0 <= self.rx_sen_start_word < 32:
            raise ValueError("rx_sen_start_word must be an integer in 0..31")


def calculate_fastrx_capture_settings(
    sequence: AdcSequence,
    symbol_rate_bps: float,
    *,
    comparator_return_min_s: float,
    comparator_return_max_s: float,
    fpga_relative_path_min_s: float,
    fpga_relative_path_max_s: float,
    seqgen_pipeline_words: int,
    tap_delay_s: float,
    setup_guard_s: float,
    hold_guard_s: float,
) -> FastRxCapture:
    """Select RX_SEN and two-stage IDELAY without changing any ADC output row.

    Comparator return bounds run from the outgoing COMP pad to the COMP_OUT
    input pin. FPGA-relative path bounds include serializer clock-to-COMP pad
    and zero-tap COMP_OUT pin-to-FastRX D, minus the corresponding capture-clock
    insertion at each Vivado corner. Guards include setup/hold, clock jitter,
    measurement uncertainty, and any further chosen safety margin.
    RX_SEN may stay high across the sequence boundary, but its first word
    must refer to the current conversion.
    """

    values = (
        symbol_rate_bps,
        comparator_return_min_s,
        comparator_return_max_s,
        fpga_relative_path_min_s,
        fpga_relative_path_max_s,
        tap_delay_s,
        setup_guard_s,
        hold_guard_s,
    )
    if not all(math.isfinite(value) for value in values):
        raise ValueError("capture timing values must be finite")
    if symbol_rate_bps <= 0 or tap_delay_s <= 0 or setup_guard_s < 0 or hold_guard_s < 0:
        raise ValueError("symbol rate and tap delay must be positive; guards must be nonnegative")
    if comparator_return_min_s > comparator_return_max_s or fpga_relative_path_min_s > fpga_relative_path_max_s:
        raise ValueError("timing lower bounds must not exceed upper bounds")
    if type(seqgen_pipeline_words) is not int or seqgen_pipeline_words < 0:
        raise ValueError("seqgen_pipeline_words must be a nonnegative integer")

    comp = sequence.comp
    edge_symbols = [index for index, bit in enumerate(comp) if bit == "1" and comp[index - 1] == "0"]
    if len(edge_symbols) != 17 or any(right - left != 8 for left, right in pairwise(edge_symbols)):
        raise ValueError("capture alignment requires 17 COMP rising edges eight symbols apart")
    word_period_s = 8.0 / symbol_rate_bps
    sequence_words = len(comp) // 8
    first_edge_s = edge_symbols[0] / symbol_rate_bps
    best: tuple[float, int, int] | None = None
    for start_word in range(sequence_words):
        capture_first_s = start_word * word_period_s
        for taps in range(63):
            variable_delay_s = seqgen_pipeline_words * word_period_s + taps * tap_delay_s
            latest_data_s = first_edge_s + variable_delay_s + comparator_return_max_s + fpga_relative_path_max_s
            earliest_next_data_s = (
                first_edge_s + word_period_s + variable_delay_s + comparator_return_min_s + fpga_relative_path_min_s
            )
            setup_margin_s = capture_first_s - latest_data_s - setup_guard_s
            hold_margin_s = earliest_next_data_s - capture_first_s - hold_guard_s
            score = min(setup_margin_s, hold_margin_s)
            if score >= 0:
                candidate = (score, -taps, -start_word)
                if best is None or candidate > best:
                    best = candidate
    if best is None:
        raise ValueError("no RX_SEN word and IDELAY setting satisfy the measured timing bounds")
    return FastRxCapture(comp_delay_taps=-best[1], rx_sen_start_word=-best[2])


def select_fastrx_capture_settings(params: AdcScanParams, profiles: Sequence[dict[str, Any]] = ()) -> FastRxCapture:
    """Use explicit controls or a characterized sequence/COMP-timing match.

    Profiles belong to the board's installed two-stage bitstream. Never
    interpolate across baud rates or silently reuse single-stage calibration.
    """
    capture = params.fastrx_capture
    if capture is None:
        sequence = AdcSequence.from_tb_params(params.tb)
        catalogue = dict(SEQUENCES)
        is_catalogued = sequence in catalogue.values()
        comp_edges = [
            index for index, bit in enumerate(sequence.comp) if bit == "1" and sequence.comp[index - 1] == "0"
        ]
        regular_comp = len(comp_edges) == 17 and all(right - left == 8 for left, right in pairwise(comp_edges))
        matches = [
            profile
            for profile in profiles
            if float(profile["symbol_rate_bps"]) == float(params.tb.symbol_rate)
            and (
                catalogue.get(profile.get("sequence")) == sequence
                or (
                    "sequence" not in profile
                    and regular_comp
                    and is_catalogued
                    and profile.get("sequence_symbols") == len(sequence.comp)
                    and profile.get("first_comp_edge_symbol") == comp_edges[0]
                )
            )
        ]
        if len(matches) != 1:
            raise ValueError(
                "expected one characterized FastRX sequence or COMP-timing/baud profile; "
                "set fastrx_capture=FastRxCapture(...) explicitly for calibration"
            )
        capture = FastRxCapture(matches[0]["comp_delay_taps"], matches[0]["rx_sen_start_word"])
    if capture.rx_sen_start_word >= len(params.tb.seq_init_pattern) // 8:
        raise ValueError("rx_sen_start_word must be inside the sequencer period")
    return capture


def program_comp_delay(gpio, taps: int) -> None:
    """Load both calibrated delay counters while acquisition is stopped.

    The firmware splits the sum into floor(taps/2), ceil(taps/2). Verify the
    register ABI before writing and the actual hardware counters after loading.
    """
    if isinstance(taps, bool) or not isinstance(taps, int) or not 0 <= taps <= 62:
        raise ValueError("combined comparator delay taps must be in 0..62")
    gpio.read()
    if not gpio["COMP_IDELAY_TWO_STAGE"].tovalue():
        raise RuntimeError("two-stage comparator-delay firmware is required")
    if not gpio["COMP_IDELAY_RDY"].tovalue():
        raise RuntimeError("comparator IDELAYCTRL is not ready")
    gpio["COMP_IDELAY_TAPS"] = taps
    gpio["COMP_IDELAY_LOAD"] = 1
    try:
        gpio.write()
    finally:
        gpio["COMP_IDELAY_LOAD"] = 0
        gpio.write()
    gpio.read()
    if not gpio["COMP_IDELAY_RDY"].tovalue():
        raise RuntimeError("comparator IDELAYCTRL lost readiness")
    if gpio["COMP_IDELAY_ACTUAL"].tovalue() != taps:
        raise RuntimeError("comparator delay counter readback does not match requested taps")
