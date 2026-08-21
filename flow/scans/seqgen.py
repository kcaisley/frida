"""Pure packing of typed ADC timing patterns into FPGA sequencer memory."""

from __future__ import annotations

from array import array

from flow.adc.sim import AdcTbParams


def convert_params_to_seqgen_fmt(params: AdcTbParams, rx_sen_pattern: str) -> array[int]:
    """Pack four serializer lanes and a caller-defined RX_SEN word pattern.

    The four ``seq_*_pattern`` fields contain one bit per serialized symbol.
    ``rx_sen_pattern`` contains one bit per eight-symbol sequencer word. The
    final RX_SEN word must remain low so FastRX can flush a partial frame before
    the sequence repeats.
    """

    serdes_ratio = 8
    seqgen_byte_lanes = 8
    serdes_fields = (
        ("INIT", "seq_init_pattern", "seq_init_phase_delay_symbols"),
        ("SAMP", "seq_samp_pattern", "seq_samp_phase_delay_symbols"),
        ("COMP", "seq_comp_pattern", "seq_comp_phase_delay_symbols"),
        ("LOGIC", "seq_logic_pattern", "seq_logic_phase_delay_symbols"),
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
    if rx_sen_pattern[-1] != "0":
        raise ValueError("RX_SEN must leave a low word before the sequence repeats")

    parsed: dict[str, list[str]] = {}
    for name, pattern_field, phase_field in serdes_fields:
        pattern = getattr(params, pattern_field)
        phase_symbols = float(getattr(params, phase_field))
        if not phase_symbols.is_integer():
            raise ValueError(f"physical {phase_field} must be a whole number of serialized symbols")
        shift = int(phase_symbols) % sequence_symbols
        if shift:
            pattern = pattern[-shift:] + pattern[:-shift]
        parsed[name] = [pattern[index : index + serdes_ratio] for index in range(0, sequence_symbols, serdes_ratio)]

    memory = array("B")
    for word_index in range(sequence_words):
        for name, _pattern_field, _phase_field in serdes_fields:
            value = 0
            for lane, bit in enumerate(parsed[name][word_index]):
                value |= int(bit) << lane
            memory.append(value)

        control = int(rx_sen_pattern[word_index]) << rx_sen_bit
        control |= 0 << rx_test_bit
        memory.append(control)
        memory.extend(0 for _ in range(seqgen_byte_lanes - 5))

    return memory
