"""FRIDA ADC scan and readout script."""

import csv
from array import array
from pathlib import Path
from statistics import fmean, pstdev
from time import sleep

from bitarray import bitarray

from flow.scans.instruments import instrument_dut
from flow.scans.plldrp import calculate_pll_frequency, select_pll_configuration, set_pll_divider
from flow.scans.plot import (
    plot_adc_transfer,
    plot_code_density_linearity,
    plot_code_distribution,
    plot_code_histogram,
    plot_decision_paths,
    plot_noise_histogram_grid,
    write_adc_csv,
)

SCAN_MODE = "noise"  # "transfer", "noise", or "nonlin"
INPUT_MODE = "manual"  # "manual" uses externally fixed inputs and does not initialize laboratory sources.
SETUP = "newsup_1short_vdddacferrite"
SCAN_OUTDIRS = {
    "transfer": "scan_transfer",
    "noise": "scan_noise",
    "nonlin": "scan_nonlin",
}
if SCAN_MODE not in SCAN_OUTDIRS:
    raise ValueError(f"SCAN_MODE must be one of {tuple(SCAN_OUTDIRS)}, got {SCAN_MODE!r}")
ADC_INDICES = range(0, 16)
SELECTED_ADC_CFG = "1111111"
OTHER_ADC_CFG = "0000000"
RADIX17_CAP_WEIGHTS = [768, 512, 320, 192, 96, 64, 32, 24, 12, 10, 5, 4, 4, 2, 1, 1]
RADIX20_CAP_WEIGHTS = [768, 512, 320, 192, 128, 64, 64, 64, 64, 64, 32, 16, 8, 4, 2, 1]
# ADC macro variants alternate across the SPI/mux index: even ADCs are radix17, odd ADCs are radix20.
ADC_CAP_WEIGHTS = {adc: RADIX20_CAP_WEIGHTS if adc % 2 else RADIX17_CAP_WEIGHTS for adc in range(16)}
ADC_CODE_WEIGHTS = {
    adc_index: [2 * weight for weight in cap_weights] + [1] for adc_index, cap_weights in ADC_CAP_WEIGHTS.items()
}
NUM_CAPTURE_BITS = len(ADC_CODE_WEIGHTS[0])
if INPUT_MODE not in ("manual", "awg"):
    raise ValueError(f"INPUT_MODE must be 'manual' or 'awg', got {INPUT_MODE!r}")
MANUAL_VIN_P_V = 0.615  # Externally applied Vin_p in manual mode; AWG setpoint otherwise.
MANUAL_VIN_N_V = 0.615  # Externally applied Vin_n; not programmed by this script.
V_START = MANUAL_VIN_P_V
V_STOP = MANUAL_VIN_P_V
V_STEP = 0.400
VINP_SWEEP = tuple(V_START + step * V_STEP for step in range(round((V_STOP - V_START) / V_STEP) + 1))
N_SWEEP_POINTS = len(VINP_SWEEP)
SLEEP_TIME = 0.2
FAST_RX_DRAIN_SLEEP = 0.01
CONVERSIONS_PER_VIN = 10_000 if SCAN_MODE == "noise" else 10
PLOT_NOISE_DECISION_PATHS = True
NOMINAL_ADC_SAMPLE_RATES_HZ = tuple(rate_msps * 1e6 for rate_msps in range(1, 11))
ADC_ACTIVE_STEPS = 20
SERDES_RATIO = 8
SEQ_GEN_LANES = 8  # Physical seq_gen width is 64 bits because Basil packs byte-wide lanes cleanly.
SERDES_TRACKS = ("INIT", "SAMP", "COMP", "LOGIC")
CONTROL_BITS = {"RX_SEN": 0, "RX_TEST": 1}  # Packed into sequencer byte 4, i.e. seq_out[32] and seq_out[33].
SEQUENCE_STEPS = 32  # Includes idle padding after the 20 active ADC conversion periods.
RX_SEN_START_WORD_BY_RATE_HZ = {
    1_000_000: 6,
    2_000_000: 7,
    3_000_000: 7,
    4_000_000: 7,
    5_000_000: 8,
    6_000_000: 8,
    7_000_000: 8,
    8_000_000: 9,
    9_000_000: 9,
    10_000_000: 9,
}
COMP_IDELAY_TAPS_BY_RATE_HZ = {
    1_000_000: 0,
    2_000_000: 0,
    3_000_000: 0,
    4_000_000: 0,
    5_000_000: 17,
    6_000_000: 8,
    7_000_000: 12,
    8_000_000: 24,
    9_000_000: 4,
    10_000_000: 0,
}
SCAN_OUTDIR = Path(__file__).resolve().parents[2] / "build" / SCAN_OUTDIRS[SCAN_MODE] / "rate_sweep_615mv"
# fmt: off
SEQ_PATTERNS = {
    "INIT":    "00000000 11111111 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000",
    "SAMP":    "00000000 00000000 11111111 11111111 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000",
    "COMP":    "00000000 00000000 00000000 00000000 00001111 00001111 00001111 00001111 00001111 00001111 00001111 00001111 00001111 00001111 00001111 00001111 00001111 00001111 00001111 00001111 00001111 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000",
    "LOGIC":   "00000000 00001111 00000000 00000000 00000000 11110000 11110000 11110000 11110000 11110000 11110000 11110000 11110000 11110000 11110000 11110000 11110000 11110000 11110000 11110000 11110000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000",
    "RX_SEN":  "0 0 0 0 0 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 0 0 0 0 0 0 0 0 0 0",
    "RX_TEST": "0 0 0 0 1 1 0 0 0 0 0 1 0 1 1 0 0 0 0 0 1 0 0 0 0 0 0 0 0 0 0 0",
}
# fmt: on

# Capacitor array weights are labeled left-to-right as C16..C1.
# The 17 output-bit weights W16..W0 are [2*C16, 2*C15, ..., 2*C1, 1].
# The 2x factor in W16..W1 follows the recombination shown by Liu et al.,
# IEEE JSSC 50(11), 2645-2654 (2015), Section III, DOI: 10.1109/JSSC.2015.2466475
NORMALIZED_CODE_MAX = 4095
MAX_RAW_FASTRX_WORDS = 20  # Console preview only; every captured word is still decoded and saved.
ALIGNMENT_MIDSCALE_TOLERANCE_CODES = 128
ALIGNMENT_MAX_SIGMA_CODES = 50
ALIGNMENT_MAX_RANGE_CODES = 128


def scpi_float(value) -> float:
    """Convert a SCPI response to float, accepting comma-separated readback strings."""
    return float(str(value).strip().split(",")[0])


def count_csv_rows(path: Path) -> int:
    """Count data rows in a CSV file, excluding the header."""
    with path.open(newline="") as f:
        return sum(1 for _ in csv.DictReader(f))


def nominal_adc_rate_to_symbol_rate(sample_rate_hz: float) -> float:
    """Convert the 20-period nominal ADC rate into the required DDR symbol rate."""
    if sample_rate_hz <= 0:
        raise ValueError("sample_rate_hz must be positive")
    return sample_rate_hz * ADC_ACTIVE_STEPS * SERDES_RATIO


def set_comp_idelay(daq, taps: int) -> None:
    """Load one 0..31 comparator-input IDELAY setting through GPIO1."""
    if isinstance(taps, bool) or not isinstance(taps, int) or not 0 <= taps <= 31:
        raise ValueError(f"COMP IDELAY taps must be an integer in 0..31, got {taps!r}")
    daq["gpio1"].read()
    if not daq["gpio1"]["COMP_IDELAY_RDY"].tovalue():
        raise RuntimeError("comparator IDELAYCTRL is not ready")
    daq["gpio1"]["COMP_IDELAY_TAPS"] = taps
    daq["gpio1"]["COMP_IDELAY_LOAD"] = 1
    daq["gpio1"].write()
    daq["gpio1"]["COMP_IDELAY_LOAD"] = 0
    daq["gpio1"].write()


def patterns_with_rx_sen_start(start_word: int) -> dict[str, str]:
    """Return the ADC patterns with one legal 17-word FastRX capture window."""
    stop_word = start_word + NUM_CAPTURE_BITS
    if start_word < 0 or stop_word >= SEQUENCE_STEPS:
        raise ValueError(
            f"RX_SEN window {start_word}..{stop_word - 1} must leave a low word before the {SEQUENCE_STEPS}-word repeat"
        )
    patterns = dict(SEQ_PATTERNS)
    rx_sen = ["0"] * SEQUENCE_STEPS
    rx_sen[start_word:stop_word] = ["1"] * NUM_CAPTURE_BITS
    patterns["RX_SEN"] = " ".join(rx_sen)
    return patterns


def normalize_code(code: int, code_weights: list[int]) -> int:
    """Scale a weighted ADC code onto the common 0..4095 output range."""
    return round(code * NORMALIZED_CODE_MAX / sum(code_weights))


def decode_conversion(spi_data: int, data_size: int, code_weights: list[int]) -> tuple[str, int]:
    """Decode one FastRX word into Bbits and recombine W16..W0 into Dout.

    fast_spi_rx shifts samples left, so temporal order within each displayed word is
    left-to-right: bit DATA_SIZE-1 -> bit 0. The 17-bit output is labeled
    Bbits = B16..B0 and recombined directly with code_weights = W16..W0.
    """
    samples = [(spi_data >> i) & 1 for i in range(data_size - 1, -1, -1)]
    num_capture_bits = len(code_weights)
    if len(samples) < num_capture_bits:
        raise ValueError(f"FastRX DATA_SIZE={data_size} is smaller than {num_capture_bits} ADC code bits")

    bits = samples[:num_capture_bits]
    Bbits = "".join(str(bit) for bit in bits)
    Dout = sum(weight * bit for weight, bit in zip(code_weights, bits, strict=True))
    return Bbits, Dout


def bitarray_to_seq_gen_format(
    patterns: dict[str, str],
    serdes_ratio: int,
    seq_gen_lanes: int,
) -> array:
    """Build raw 64-bit sequencer memory from serializer and FastRX patterns.

    Byte lanes 0..3 are serialized by OSERDES for INIT/SAMP/COMP/LOGIC. Byte
    lane 4 is internal control: bit 0 is RX_SEN (seq_out[32]) and bit 1 is
    RX_TEST (seq_out[33]). The remaining physical 64-bit lanes are padded.
    """
    parsed: dict[str, list[str]] = {}
    seq_words: int | None = None
    for name, pattern in patterns.items():
        words = pattern.split()
        if seq_words is None:
            seq_words = len(words)
        elif len(words) != seq_words:
            raise ValueError(f"{name}: expected {seq_words} words, got {len(words)}")

        expected_width = serdes_ratio if name in SERDES_TRACKS else 1
        for word in words:
            if len(word) != expected_width or any(bit not in "01" for bit in word):
                raise ValueError(f"{name}: invalid word {word!r}; expected {expected_width} bit(s)")
        parsed[name] = words

    assert seq_words is not None
    if seq_gen_lanes < 5:
        raise ValueError("serializer plus RX_SEN/RX_TEST control byte needs at least five sequencer byte lanes")

    memory = array("B")
    for word_index in range(seq_words):
        for name in SERDES_TRACKS:
            value = 0
            for lane, bit in enumerate(parsed[name][word_index]):
                value |= int(bit) << lane
            memory.append(value)

        control = 0
        for name, bit_position in CONTROL_BITS.items():
            control |= int(parsed[name][word_index]) << bit_position
        memory.append(control)
        memory.extend(0 for _ in range(seq_gen_lanes - 5))

    expected = seq_words * seq_gen_lanes
    if len(memory) != expected:
        raise RuntimeError(f"expected {expected} bytes, built {len(memory)}")
    return memory


def spi_config_to_bytes(config: dict) -> bytes:
    """Flatten, print, and pack one 180-bit FRIDA SPI config dictionary."""

    def set_spi_field_msb_first(msb: int, lsb: int, value: str, field: str) -> None:
        """Set logical spi_bits[msb:lsb] from a human-readable MSB-first string."""
        value_bits = bitarray(value[::-1])
        width = msb - lsb + 1
        if len(value_bits) != width:
            raise ValueError(f"{field} must be {width} bits, got {len(value_bits)}")
        bits[lsb : msb + 1] = value_bits

    bits = bitarray(180)
    bits.setall(0)

    dac_fields = (
        ("dac_astate_p", 63, 48),
        ("dac_bstate_p", 47, 32),
        ("dac_astate_n", 31, 16),
        ("dac_bstate_n", 15, 0),
    )
    for field, msb, lsb in dac_fields:
        set_spi_field_msb_first(msb, lsb, config[field], field)

    adc_fields = ["en_init", "en_samp_p", "en_samp_n", "en_comp", "en_update", "dac_mode", "dac_diffcaps"]
    mux_sel = int(config["mux_sel"])
    if not 0 <= mux_sel < 16:
        raise ValueError(f"mux_sel must be in 0..15, got {mux_sel}")
    config_adc = int(config.get("config_adc", mux_sel))
    if not 0 <= config_adc < 16:
        raise ValueError(f"config_adc must be in 0..15, got {config_adc}")
    adc_cfg = bitarray([bool(config[field]) for field in adc_fields])
    selected_adc_cfg = bitarray(config.get("selected_adc_cfg", adc_cfg))
    other_adc_cfg = bitarray(config.get("other_adc_cfg", "0000000"))
    if len(selected_adc_cfg) != 7:
        raise ValueError(f"selected_adc_cfg must be 7 bits, got {len(selected_adc_cfg)}")
    if len(other_adc_cfg) != 7:
        raise ValueError(f"other_adc_cfg must be 7 bits, got {len(other_adc_cfg)}")
    for adc in range(16):
        base = 64 + 7 * adc
        bits[base : base + 7] = selected_adc_cfg if adc == config_adc else other_adc_cfg
    mux_bits = config.get("mux_bits", f"{mux_sel:04b}")
    set_spi_field_msb_first(179, 176, mux_bits, "mux_bits")

    col_width = 32
    print("DAC state strings are ordered C16..C1, i.e. biggest capacitor to smallest capacitor.")
    print("".join(f"{field} spi_bits[{msb}:{lsb}]".ljust(col_width) for field, msb, lsb in dac_fields))
    print("".join(str(config[field]).ljust(col_width) for field, _, _ in dac_fields))

    adc_headers = []
    adc_values = []
    for adc in range(16):
        base = 64 + 7 * adc
        adc_headers.append(f"ADC{adc:02d}_CFG[{base}:{base + 6}]")
        adc_values.append(bits[base : base + 7].to01())
    for chunk_start in range(0, len(adc_headers), 4):
        chunk_headers = adc_headers[chunk_start : chunk_start + 4]
        chunk_values = adc_values[chunk_start : chunk_start + 4]
        print("".join(header.ljust(col_width) for header in chunk_headers))
        print("".join(value.ljust(col_width) for value in chunk_values))

    mux_header = "MUX_SEL spi_bits[179:176]"
    mux_value = bits[176:180][::-1].to01()
    print(mux_header)
    print(mux_value)

    # Flip order, since wire transmission order is inverse of in-register order
    return bits[::-1].tobytes()


def main(
    *,
    adc_indices=ADC_INDICES,
    nominal_sample_rates_hz=NOMINAL_ADC_SAMPLE_RATES_HZ,
    conversions_per_vin: int = CONVERSIONS_PER_VIN,
    comp_idelay_taps: int | None = None,
    make_plots: bool = True,
    validate_alignment: bool = True,
    fail_on_alignment_error: bool = False,
) -> None:
    from basil.dut import Dut

    adc_indices = tuple(adc_indices)
    nominal_sample_rates_hz = tuple(float(rate) for rate in nominal_sample_rates_hz)
    if not adc_indices:
        raise ValueError("adc_indices must not be empty")
    if not nominal_sample_rates_hz:
        raise ValueError("nominal_sample_rates_hz must not be empty")
    if conversions_per_vin <= 0:
        raise ValueError("conversions_per_vin must be positive")

    # Step 1: Connect to the FPGA DAQ and, unless inputs are manual, the AWG.
    map_dir = Path(__file__).resolve().parent
    daq = Dut(str(map_dir / "map_fpga.yaml"))
    instruments = instrument_dut(map_dir / "map_awg.yaml") if INPUT_MODE == "awg" else None
    daq.init()
    summary_rows: list[dict] = []
    try:
        if instruments is not None:
            instruments.init()
            instruments["awg"].set_output_load("INFinity")
        else:
            print("Manual input mode: laboratory source control disabled")

        # Release the chip and select the physical comparator input plus sequencer SEN.
        daq["gpio0"]["RST_B"] = 0
        daq["gpio0"].write()
        daq["gpio0"]["RST_B"] = 1
        daq["gpio0"]["RX_LOOPBACK"] = 0
        daq["gpio0"]["RX_EN_MUX"] = 1
        daq["gpio0"].write()

        print(f"\nStarting {len(nominal_sample_rates_hz)}-rate scan for ADCs {adc_indices}...")
        print(f"Selected ADC config bits: {SELECTED_ADC_CFG}; other ADC config bits: {OTHER_ADC_CFG}")

        for nominal_sample_rate_hz in nominal_sample_rates_hz:
            rate_hz = round(nominal_sample_rate_hz)
            if rate_hz not in RX_SEN_START_WORD_BY_RATE_HZ:
                raise ValueError(f"no calibrated RX_SEN start word for {nominal_sample_rate_hz:g} Hz")
            rx_sen_start_word = RX_SEN_START_WORD_BY_RATE_HZ[rate_hz]
            rate_idelay_taps = COMP_IDELAY_TAPS_BY_RATE_HZ[rate_hz] if comp_idelay_taps is None else comp_idelay_taps
            rate_patterns = patterns_with_rx_sen_start(rx_sen_start_word)
            seq_words = len(rate_patterns["INIT"].split())
            if seq_words != SEQUENCE_STEPS:
                raise RuntimeError(f"sequencer pattern has {seq_words} words, expected {SEQUENCE_STEPS}")
            sequencer_memory = bitarray_to_seq_gen_format(rate_patterns, SERDES_RATIO, SEQ_GEN_LANES)

            target_symbol_rate_bps = nominal_adc_rate_to_symbol_rate(nominal_sample_rate_hz)
            si570_frequency_hz, pll_divider_n = select_pll_configuration(target_symbol_rate_bps)
            seq_clk_hz, serializer_clk_hz = calculate_pll_frequency(
                pll_divider_n,
                input_frequency_hz=si570_frequency_hz,
            )
            if seq_clk_hz / ADC_ACTIVE_STEPS != nominal_sample_rate_hz:
                raise RuntimeError("selected PLL configuration does not produce the requested nominal ADC rate")

            print(
                f"\n=== {nominal_sample_rate_hz / 1e6:g} MSPS nominal: "
                f"SEQ={seq_clk_hz / 1e6:g} MHz, symbols={target_symbol_rate_bps / 1e6:g} MBd, "
                f"Si570={si570_frequency_hz / 1e6:g} MHz, N={pll_divider_n}, "
                f"RX_SEN start={rx_sen_start_word}, IDELAY={rate_idelay_taps} ==="
            )
            daq["si570"].frequency_change(si570_frequency_hz / 1e6)
            sleep(0.02)
            set_pll_divider(daq["gpio2"], pll_divider_n)
            set_comp_idelay(daq, rate_idelay_taps)

            # The PLL transaction resets seq_gen and FastRX. Reconfigure both only
            # after the new clock pair is locked.
            daq["seq0"]._drv.set_data(sequencer_memory)
            daq["seq0"].set_size(seq_words)
            daq["seq0"].set_clk_divide(1)
            daq["seq0"].set_repeat(conversions_per_vin)
            daq["seq0"].set_en_ext_start(False)
            daq["fastrx0"].reset()
            daq["fastrx0"].set_en(True)
            data_size = daq["fastrx0"].get_size()
            if data_size != NUM_CAPTURE_BITS:
                raise RuntimeError(f"FastRX DATA_SIZE={data_size}, expected {NUM_CAPTURE_BITS} from CAP_WEIGHTS")

            rate_label = f"{nominal_sample_rate_hz / 1e6:g}msps"
            noise_plot_runs = []
            for adc_index in adc_indices:
                cap_weights = ADC_CAP_WEIGHTS[adc_index]
                radix = "radix20" if cap_weights is RADIX20_CAP_WEIGHTS else "radix17"
                code_weights = ADC_CODE_WEIGHTS[adc_index]
                mux_bits = f"{adc_index:04b}"
                case_name = f"adc_{adc_index:02d}_{rate_label}"
                print(f"\n--- ADC {adc_index:02d} ({radix}, {rate_label}) ---")
                print(f"{case_name}: bit weights W16..W0: {code_weights}")

                spi_config = {
                    "dac_astate_p": "0101010101010101",
                    "dac_astate_n": "0101010101010101",
                    "dac_bstate_p": "0000000000000000",
                    "dac_bstate_n": "0000000000000000",
                    "en_init": 1,
                    "en_samp_p": 1,
                    "en_samp_n": 1,
                    "en_comp": 1,
                    "en_update": 1,
                    "dac_mode": 1,
                    "dac_diffcaps": 1,
                    "config_adc": adc_index,
                    "selected_adc_cfg": SELECTED_ADC_CFG,
                    "other_adc_cfg": OTHER_ADC_CFG,
                    "mux_sel": adc_index,
                    "mux_bits": mux_bits,
                }

                spi_bytes = spi_config_to_bytes(spi_config)
                for _ in range(2):
                    daq["spi0"].set_data(list(spi_bytes))
                    daq["spi0"].set_size(180)
                    daq["spi0"].start()
                    daq["spi0"].wait_for_ready()

                raw = bytes(daq["spi0"].get_data(size=23))
                rb = bitarray()
                rb.frombytes(raw)
                rb = rb[:180]
                bits = bitarray()
                bits.frombytes(spi_bytes)
                bits = bits[:180]
                print(f"{case_name}: SPI verify: {((bits[1:] ^ rb[1:]).count(1))} mismatches (skip bit 0)")

                daq["fifo0"]["RESET"]
                daq["fifo0"].get_data()
                rows = []
                for sweep_index, voltage in enumerate(VINP_SWEEP):
                    if instruments is not None:
                        instruments["awg"].set_DC(f"DEF,DEF,{voltage}")
                        instruments["awg"].set_enable(1)
                        sleep(SLEEP_TIME)
                        actual = scpi_float(instruments["awg"].get_voltage_offset())
                    else:
                        print(f"{case_name}: capturing {conversions_per_vin} conversions at fixed external input")
                        actual = voltage
                    vin_n = MANUAL_VIN_N_V

                    daq["seq0"].start()
                    while not daq["seq0"].is_done():
                        sleep(0.1)
                        print(f"{case_name}: waiting for sequencer!")

                    sleep(FAST_RX_DRAIN_SLEEP)
                    data = daq["fifo0"].get_data()
                    print(f"{case_name}: FIFO ({len(data)} words for {conversions_per_vin} conversions)")
                    if len(data) != conversions_per_vin:
                        raise RuntimeError(
                            f"{case_name}: expected one 17-bit FastRX word for each of "
                            f"{conversions_per_vin} conversions, received {len(data)}"
                        )

                    for i in range(min(MAX_RAW_FASTRX_WORDS, len(data))):
                        identifier, frame_counter, spi_data = daq["fastrx0"].parse_word(int(data[i]))
                        print(
                            f"[{i}] ID={identifier:04b} frame={frame_counter:0{28 - data_size}b} "
                            f"data={spi_data:0{data_size}b}"
                        )

                    dout_list = []
                    dout_raw_list = []
                    bbits_list = []
                    for conversion_index, raw_word in enumerate(int(word) for word in data):
                        identifier, frame, spi_data = daq["fastrx0"].parse_word(raw_word)
                        bbits, dout_raw = decode_conversion(spi_data, data_size, code_weights)
                        dout = normalize_code(dout_raw, code_weights)
                        bbits_list.append(bbits)
                        dout_list.append(dout)
                        dout_raw_list.append(dout_raw)
                        rows.append(
                            {
                                "adc": adc_index,
                                "config_adc": adc_index,
                                "mux_bits": mux_bits,
                                "selected_adc_cfg": SELECTED_ADC_CFG,
                                "other_adc_cfg": OTHER_ADC_CFG,
                                "case_name": case_name,
                                "nominal_sample_rate_hz": nominal_sample_rate_hz,
                                "sequencer_frequency_hz": seq_clk_hz,
                                "serializer_frequency_hz": serializer_clk_hz,
                                "symbol_rate_bps": target_symbol_rate_bps,
                                "si570_frequency_hz": si570_frequency_hz,
                                "pll_divider_n": pll_divider_n,
                                "rx_sen_start_word": rx_sen_start_word,
                                "comp_idelay_taps": rate_idelay_taps,
                                "sweep_index": sweep_index,
                                "vin_set_v": voltage,
                                "vin_read_v": actual,
                                "vdiff_v": actual - vin_n,
                                "conversion_index": conversion_index,
                                "raw_word": raw_word,
                                "id": identifier,
                                "frame": frame,
                                "spi": spi_data,
                                "Bbits": bbits,
                                "Dout": dout,
                                "Dout_raw": dout_raw,
                            }
                        )

                    mean_code = fmean(dout_list)
                    sigma_code = pstdev(dout_list)
                    alignment_ok = (
                        abs(mean_code - NORMALIZED_CODE_MAX / 2) <= ALIGNMENT_MIDSCALE_TOLERANCE_CODES
                        and sigma_code <= ALIGNMENT_MAX_SIGMA_CODES
                        and max(dout_list) - min(dout_list) <= ALIGNMENT_MAX_RANGE_CODES
                        and len(set(dout_list)) >= 2
                    )
                    for row in rows[-len(dout_list) :]:
                        row["alignment_ok"] = alignment_ok
                    preview_count = min(MAX_RAW_FASTRX_WORDS, len(bbits_list))
                    print(f"{case_name}: first {preview_count} Bbits B16..B0: {bbits_list[:preview_count]}")
                    print(f"{case_name}: first {preview_count} Dout_raw: {dout_raw_list[:preview_count]}")
                    print(
                        f"{case_name}: mean={mean_code:.3f}, sigma={sigma_code:.3f}, "
                        f"range={min(dout_list)}..{max(dout_list)}, Vdiff={(actual - vin_n) * 1000:.1f} mV"
                    )
                    if validate_alignment and INPUT_MODE == "manual" and SCAN_MODE == "noise" and not alignment_ok:
                        message = (
                            f"{case_name}: implausible equal-input distribution (mean={mean_code:.2f}, "
                            f"sigma={sigma_code:.2f}, range={min(dout_list)}..{max(dout_list)}, "
                            f"unique={len(set(dout_list))}); "
                            "FastRX/ADC timing needs adjustment"
                        )
                        if fail_on_alignment_error:
                            raise RuntimeError(message)
                        print(f"WARNING: {message}")
                    sleep(SLEEP_TIME)

                artifact_stem = f"adc{adc_index:02d}_dinit{spi_config['dac_astate_p']}_{rate_label}"
                csv_path = SCAN_OUTDIR / f"{artifact_stem}_{SCAN_MODE}_{SETUP}.csv"
                write_adc_csv(adc_index, rows, SCAN_OUTDIR, csv_path=csv_path)
                expected_rows = len(VINP_SWEEP) * conversions_per_vin
                actual_rows = count_csv_rows(csv_path)
                if actual_rows != expected_rows:
                    raise RuntimeError(f"{csv_path} has {actual_rows} rows, expected {expected_rows}")
                print(f"{csv_path}: validated {actual_rows} rows")

                summary_rows.append(
                    {
                        "adc": adc_index,
                        "nominal_sample_rate_hz": nominal_sample_rate_hz,
                        "sequencer_frequency_hz": seq_clk_hz,
                        "symbol_rate_bps": target_symbol_rate_bps,
                        "si570_frequency_hz": si570_frequency_hz,
                        "pll_divider_n": pll_divider_n,
                        "rx_sen_start_word": rx_sen_start_word,
                        "comp_idelay_taps": rate_idelay_taps,
                        "alignment_ok": all(bool(row["alignment_ok"]) for row in rows),
                        "samples": actual_rows,
                        "mean_dout": fmean(int(row["Dout"]) for row in rows),
                        "sigma_dout": pstdev(int(row["Dout"]) for row in rows),
                        "min_dout": min(int(row["Dout"]) for row in rows),
                        "max_dout": max(int(row["Dout"]) for row in rows),
                        "csv_path": str(csv_path),
                    }
                )

                adc_cfg = {
                    "adc_index": adc_index,
                    "artifact_stem": artifact_stem,
                    "rate_label": rate_label,
                    "setup": SETUP,
                    "dac_init_state": spi_config["dac_astate_p"],
                    "dac_diffcaps": bool(spi_config["dac_diffcaps"]),
                    "num_samples": actual_rows,
                    "seq_base_freq_hz": seq_clk_hz,
                    "conversion_steps": ADC_ACTIVE_STEPS,
                    "input_ramp": "fixed external input",
                    "code_range": (1, 4094),
                    "code_weights": code_weights,
                }
                if make_plots and SCAN_MODE == "transfer":
                    plot_adc_transfer(adc_cfg, csv_path, SCAN_OUTDIR)
                elif make_plots and SCAN_MODE == "noise":
                    plot_code_histogram(adc_cfg, csv_path, SCAN_OUTDIR)
                    noise_plot_runs.append((adc_cfg, csv_path))
                    if PLOT_NOISE_DECISION_PATHS:
                        plot_decision_paths(
                            adc_cfg,
                            csv_path,
                            SCAN_OUTDIR,
                            filter_mode="all",
                            show_reference_lines=False,
                            show_mean_path=False,
                        )
                elif make_plots and SCAN_MODE == "nonlin":
                    plot_code_distribution(adc_cfg, csv_path, SCAN_OUTDIR)
                    plot_code_density_linearity(adc_cfg, csv_path, SCAN_OUTDIR)

            if make_plots and SCAN_MODE == "noise" and noise_plot_runs:
                plot_noise_histogram_grid(noise_plot_runs, SCAN_OUTDIR)

        if summary_rows:
            summary_path = SCAN_OUTDIR / f"noise_rate_summary_{SETUP}.csv"
            summary_path.parent.mkdir(parents=True, exist_ok=True)
            with summary_path.open("w", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=summary_rows[0])
                writer.writeheader()
                writer.writerows(summary_rows)
            print(f"Saved rate summary: {summary_path}")
    finally:
        try:
            daq["si570"].frequency_change(200.0)
            sleep(0.02)
            set_pll_divider(daq["gpio2"], 2)
        finally:
            if instruments is not None:
                instruments["awg"].set_enable(0)
                instruments.close()
            daq.close()

    print("Done.")


if __name__ == "__main__":
    main()
