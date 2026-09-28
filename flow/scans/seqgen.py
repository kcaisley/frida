"""Pure packing of typed ADC timing patterns into FPGA sequencer memory."""

from __future__ import annotations

from array import array

from flow.adc.sim import AdcTbParams


def convert_params_to_seqgen_fmt(params: AdcTbParams, rx_sen_pattern: str) -> array[int]:
    """Pack four serializer lanes and a caller-defined RX_SEN word pattern.

    The four ``seq_*_pattern`` fields contain one bit per serialized symbol.
    ``rx_sen_pattern`` contains one bit per eight-symbol sequencer word. The
    RX_SEN may remain high across a repeat. Stop the receiver before stopping
    a sequence whose last RX_SEN word is high.
    """

    serdes_ratio = 8
    seqgen_byte_lanes = 8
    serdes_fields = (
        ("INIT", "seq_init_pattern"),
        ("SAMP", "seq_samp_pattern"),
        ("COMP", "seq_comp_pattern"),
        ("LOGIC", "seq_logic_pattern"),
    )
    rx_sen_bit = 0
    rx_test_bit = 1

    sequence_symbols = len(params.seq_init_pattern)
    sequence_words = sequence_symbols // serdes_ratio
    if not isinstance(rx_sen_pattern, str):
        raise TypeError("rx_sen_pattern must be a binary string")
    if len(rx_sen_pattern) != sequence_words:
        raise ValueError(f"rx_sen_pattern must contain {sequence_words} sequencer-word bits, got {len(rx_sen_pattern)}")
    if set(rx_sen_pattern) - {"0", "1"}:
        raise ValueError("rx_sen_pattern must contain only zero and one")

    parsed: dict[str, list[str]] = {}
    for name, pattern_field in serdes_fields:
        pattern = getattr(params, pattern_field)
        parsed[name] = [pattern[index : index + serdes_ratio] for index in range(0, sequence_symbols, serdes_ratio)]

    memory = array("B")
    for word_index in range(sequence_words):
        for name, _pattern_field in serdes_fields:
            value = 0
            for lane, bit in enumerate(parsed[name][word_index]):
                value |= int(bit) << lane
            memory.append(value)

        control = int(rx_sen_pattern[word_index]) << rx_sen_bit
        control |= 0 << rx_test_bit
        memory.append(control)
        memory.extend(0 for _ in range(seqgen_byte_lanes - 5))

    return memory


def build_fastrx_capture_pattern(params: AdcTbParams, rx_sen_start_word: int, data_size: int) -> array[int]:
    """Pack one unchanged control period with RX_SEN at the calibrated start.

    The receive window wraps modulo the period; FastRX follows RX_SEN across
    repetitions. Acquisition stops the receiver before stopping the sequencer.
    """
    words = len(params.seq_init_pattern) // 8
    if not 0 <= rx_sen_start_word < words or not 0 < data_size < words:
        raise ValueError("FastRX needs an in-range start and at least one low word per period")
    rx_sen = ["0"] * words
    for bit in range(data_size):
        rx_sen[(rx_sen_start_word + bit) % words] = "1"
    return convert_params_to_seqgen_fmt(params, "".join(rx_sen))
