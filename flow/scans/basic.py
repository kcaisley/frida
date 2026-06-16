"""FRIDA ADC basic scan and readout script."""

from pathlib import Path
from time import sleep

from flow.scans.plot import plot_adc_transfer, write_adc_csv

# TODO:
# Check what plot looks like, for:
# - different channels
# - different common mode voltages, and the full ADC range
# - VDDA / VDDD +-10%
# - Various clock speeds
# - phase between logic and comp clock (increase clock speed of sequencer)
# - different DAC init voltages
# - with diff caps enabled / disabled

ADC_INDICES = (0,)
SELECTED_ADC_CFG = "1111111"
OTHER_ADC_CFG = "0000000"
RADIX17_CAP_WEIGHTS = [768, 512, 320, 192, 96, 64, 32, 24, 12, 10, 5, 4, 4, 2, 1, 1]
RADIX20_CAP_WEIGHTS = [768, 512, 320, 192, 128, 64, 64, 64, 64, 64, 32, 16, 8, 4, 2, 1]
ADC_CAP_WEIGHTS = {
    0: RADIX17_CAP_WEIGHTS,
    1: RADIX20_CAP_WEIGHTS,
    2: RADIX17_CAP_WEIGHTS,
    3: RADIX20_CAP_WEIGHTS,
    4: RADIX17_CAP_WEIGHTS,
    5: RADIX20_CAP_WEIGHTS,
    6: RADIX17_CAP_WEIGHTS,
    7: RADIX20_CAP_WEIGHTS,
    8: RADIX17_CAP_WEIGHTS,
    9: RADIX20_CAP_WEIGHTS,
    10: RADIX17_CAP_WEIGHTS,
    11: RADIX20_CAP_WEIGHTS,
    12: RADIX17_CAP_WEIGHTS,
    13: RADIX20_CAP_WEIGHTS,
    14: RADIX17_CAP_WEIGHTS,
    15: RADIX20_CAP_WEIGHTS,
}
ADC_CODE_WEIGHTS = {
    adc_index: [2 * weight for weight in cap_weights] + [1] for adc_index, cap_weights in ADC_CAP_WEIGHTS.items()
}
NUM_CAPTURE_BITS = len(ADC_CODE_WEIGHTS[0])
V_START_MV = 0
V_STOP_MV = 1200
V_STEP_MV = 10
VINP_SWEEP_MV = tuple(range(V_START_MV, V_STOP_MV + V_STEP_MV, V_STEP_MV))
VINP_SWEEP_V = tuple(mv / 1000.0 for mv in VINP_SWEEP_MV)
N_SWEEP_POINTS = len(VINP_SWEEP_V)
V_START = VINP_SWEEP_V[0]
V_STOP = VINP_SWEEP_V[-1]
SLEEP_TIME = 0.2
FAST_RX_DRAIN_SLEEP = 0.01
CONVERSIONS_PER_VIN = 10
SCAN_OUTDIR = Path(__file__).resolve().parents[2] / "build" / "basic_scan"


# Capacitor array weights are labeled left-to-right as C16..C1.
# The 17 output-bit weights W16..W0 are [2*C16, 2*C15, ..., 2*C1, 1].
# The 2x factor in W16..W1 follows the recombination shown by Liu et al.,
# IEEE JSSC 50(11), 2645-2654 (2015), Section III, DOI: 10.1109/JSSC.2015.2466475
NORMALIZED_CODE_MAX = 4095
DECIMATE_PHASE = 0  # Try 1 if the decoded transfer still looks phase-shifted/noisy.
MAX_RAW_FASTRX_WORDS = 2 * CONVERSIONS_PER_VIN  # Print all expected raw words; all words are still decoded.


def scpi_float(value) -> float:
    """Convert a SCPI response to float, accepting comma-separated readback strings."""
    return float(str(value).strip().split(",")[0])


def normalize_code(code: int, code_weights: list[int]) -> int:
    """Scale a weighted ADC code onto the common 0..4095 output range."""
    return round(code * NORMALIZED_CODE_MAX / sum(code_weights))


def decode_conversion(spi0: int, spi1: int, data_size: int, code_weights: list[int]) -> tuple[str, int, str, int]:
    """Decode two FastRX words into Bbits and recombine W16..W0 into Dout.

    fast_spi_rx shifts samples left, so temporal order within each displayed word is
    left-to-right: bit DATA_SIZE-1 -> bit 0. The decimated 17-bit output is labeled
    Bbits = B16..B0 and recombined directly with code_weights = W16..W0.
    """
    if DECIMATE_PHASE not in (0, 1):
        raise ValueError(f"DECIMATE_PHASE must be 0 or 1, got {DECIMATE_PHASE}")

    samples = [(spi0 >> i) & 1 for i in range(data_size - 1, -1, -1)]
    samples += [(spi1 >> i) & 1 for i in range(data_size - 1, -1, -1)]

    num_capture_bits = len(code_weights)
    decimated = [samples[DECIMATE_PHASE + 2 * i] for i in range(num_capture_bits)]
    Bbits = "".join(str(bit) for bit in decimated)
    Dout = sum(weight * bit for weight, bit in zip(code_weights, decimated, strict=True))

    alt_phase = 1 - DECIMATE_PHASE
    decimated_alt = [samples[alt_phase + 2 * i] for i in range(num_capture_bits)]
    Bbits_alt = "".join(str(bit) for bit in decimated_alt)
    Dout_alt = sum(weight * bit for weight, bit in zip(code_weights, decimated_alt, strict=True))

    return Bbits, Dout, Bbits_alt, Dout_alt


def spi_config_to_bytes(config: dict) -> bytes:
    """Flatten, print, and pack one 180-bit FRIDA SPI config dictionary."""
    from bitarray import bitarray

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


def main() -> None:
    from basil.dut import Dut
    from bitarray import bitarray

    # Step 1: Connect to the DAQ hardware described by the FPGA Basil YAML map.
    daq = Dut(str(Path(__file__).resolve().parent / "map_fpga.yaml"))
    daq.init()

    # Step 2: Release chip reset.
    daq["gpio0"]["RST_B"] = 0
    daq["gpio0"].write()
    daq["gpio0"]["RST_B"] = 1
    daq["gpio0"].write()

    # Step 3: Load the shared ADC sequencer pattern.
    daq["seq0"].clear()
    # Note: Python slices are half-open: start is inclusive, end is exclusive.
    # Note: Sequencer is temporal left to right.
    # fmt: off
    #                                        0  1  2  3  4  5  6  7  8  9  10 11 12 13 14 15 16 17 18 19 20 21 22 23 24 25 26 27 28 29 30 31
    daq["seq0"]["INIT"][0:64] =    bitarray("00 11 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00")
    daq["seq0"]["SAMP"][0:64] =    bitarray("00 00 11 11 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00")
    daq["seq0"]["COMP"][0:64] =    bitarray("00 00 00 00 01 01 01 01 01 01 01 01 01 01 01 01 01 01 01 01 01 00 00 00 00 00 00 00 00 00 00 00")
    daq["seq0"]["LOGIC"][0:64] =   bitarray("00 01 00 00 00 10 10 10 10 10 10 10 10 10 10 10 10 10 10 10 10 00 00 00 00 00 00 00 00 00 00 00")
    daq["seq0"]["RX_EN"][0:64] =   bitarray("00 00 00 00 00 11 11 11 11 11 11 11 11 11 11 11 11 11 11 11 11 11 00 00 00 00 00 00 00 00 00 00")
    daq["seq0"]["RX_TEST"][0:64] = bitarray("00 00 00 00 11 11 01 01 01 01 00 11 01 11 11 01 01 01 01 00 11 00 00 00 00 00 00 00 00 00 00 00")
    # fmt: on

    # Step 4: Configure sequencer operation for software-start repeated conversions.
    daq["seq0"].write(64)  # TrackRegister.write: basil/basil/RL/TrackRegister.py#L39
    daq["seq0"].set_size(64)  # seq_gen.set_size: basil/HL/seq_gen.py#L59
    daq["seq0"].set_clk_divide(1)  # seq_gen.set_clk_divide: basil/HL/seq_gen.py#L68
    daq["seq0"].set_repeat(CONVERSIONS_PER_VIN)  # seq_gen.set_repeat: basil/HL/seq_gen.py#L77
    # daq["seq0"].set_en_ext_start(True)  # GPIO external start via gpio0.SEQ_START.
    daq["seq0"].set_en_ext_start(False)  # Software start via seq0.start().

    # Step 5: Arm FastRX and route capture enable from the sequencer RX_EN track.
    # FASTRX is a fast_spi_rx RegisterHardwareLayer (basil/HL/fast_spi_rx.py)
    # RX_LOOPBACK = 1 sets fastrx_en to be driven by seq_out[4], the RX_EN track
    # RX_LOOPBACK = 0 sets fastrx_en to be driven by gpio[6], shared with SEQ_START
    daq["gpio0"]["RX_LOOPBACK"] = 0
    daq["gpio0"].write()
    daq["fastrx0"].reset()
    daq["fastrx0"].set_en(True)

    # RX_EN_MUX=1 sets fastrx_en to be driven by seq_out[4], the RX_EN track.
    daq["gpio0"]["RX_EN_MUX"] = 1
    daq["gpio0"].write()

    # Step 6: Flush stale FIFO data and validate FastRX width before scanning.
    daq["fifo0"]["RESET"]
    daq["fifo0"].get_data()

    data_size = daq["fastrx0"].get_size()
    if data_size != NUM_CAPTURE_BITS:
        raise RuntimeError(f"FastRX DATA_SIZE={data_size}, expected {NUM_CAPTURE_BITS} from CAP_WEIGHTS")

    # Step 7: Configure the Keithley 2450 as the ADC input voltage source.
    daq["psu0"].source_volt()

    # Step 8: Build the voltage sweep and scan each requested ADC.
    voltages = VINP_SWEEP_V
    print(f"\nStarting voltage sweep for ADCs {ADC_INDICES}...")
    print(f"Selected ADC config bits: {SELECTED_ADC_CFG}; other ADC config bits: {OTHER_ADC_CFG}")
    print("ADC mux/SPI configurations:")
    for adc_index, cap_weights in ADC_CAP_WEIGHTS.items():
        radix = "radix20" if cap_weights is RADIX20_CAP_WEIGHTS else "radix17"
        print(f"  ADC{adc_index:02d}: {radix}, C16..C1={cap_weights}")

    for adc_index in ADC_INDICES:
        cap_weights = ADC_CAP_WEIGHTS[adc_index]
        radix = "radix20" if cap_weights is RADIX20_CAP_WEIGHTS else "radix17"
        code_weights = ADC_CODE_WEIGHTS[adc_index]
        mux_bits = f"{adc_index:04b}"
        case_name = f"adc_{adc_index:02d}"
        print(f"\n=== Starting ADC {adc_index:02d} sweep ({radix}) ===")
        print(
            f"{case_name}: mux_bits={mux_bits}, selected ADC{adc_index:02d} cfg={SELECTED_ADC_CFG}, other cfg={OTHER_ADC_CFG}"
        )
        print(f"{case_name}: bit weights W16..W0: {code_weights}")

        # DAC strings are MSB-first: the leftmost character becomes dac_*state_*[15].
        spi_config = {
            "dac_astate_p": "0000000000000000",  # A-state P, used in normal SAR mode
            "dac_astate_n": "0000000000000000",  # A-state N, used in normal SAR mode
            "dac_bstate_p": "0000000000000000",  # B-state P, used in calibration mode
            "dac_bstate_n": "0000000000000000",  # B-state N, used in calibration mode
            "en_init": 1,  # Enable INIT pulse (DAC reset before conversion)
            "en_samp_p": 1,  # Enable sample phase P-side
            "en_samp_n": 1,  # Enable sample phase N-side
            "en_comp": 1,  # Enable comparator clock
            "en_update": 1,  # Enable DAC update (load SAR decision into DAC)
            "dac_mode": 1,  # SAR mode (0 = calibration mode)
            "dac_diffcaps": 1,  # Enable differential caps (needed for unit caps)
            "config_adc": adc_index,  # ADC control slot receiving SELECTED_ADC_CFG
            "selected_adc_cfg": SELECTED_ADC_CFG,
            "other_adc_cfg": OTHER_ADC_CFG,
            "mux_sel": adc_index,
            "mux_bits": mux_bits,
        }

        # Program SPI twice, preserving the behavior used by the working single-ADC script.
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

        # Clear stale capture data before each ADC sweep.
        daq["fifo0"]["RESET"]
        daq["fifo0"].get_data()

        rows = []
        for sweep_index, voltage in enumerate(voltages):
            print(f"{case_name}: setting PSU to {voltage * 1000:.0f} mV ({voltage:.3f} V)")
            daq["psu0"].set_voltage(voltage)
            daq["psu0"].on()
            sleep(SLEEP_TIME)
            actual = scpi_float(daq["psu0"].get_voltage())
            print(f"{case_name}: PSU readback {actual * 1000:.0f} mV ({actual:.3f} V)")
            vin_n = 0.600

            # Start the sequencer via the Basil bus. RX_EN_MUX=1 keeps FastRX enable driven
            # by the sequencer RX_EN track, so no GPIO start/holdoff signal is needed.
            daq["seq0"].start()

            while not daq["seq0"].is_done():  # is_done will not actually return 1, unless SEQ_START is ended.
                sleep(0.1)
                print(f"{case_name}: waiting for sequencer!")

            sleep(FAST_RX_DRAIN_SLEEP)
            data = daq["fifo0"].get_data()
            print(f"{case_name}: FIFO ({len(data)} words)")

            # Show raw parsed words.
            for i in range(min(MAX_RAW_FASTRX_WORDS, len(data))):
                identifier, frame_counter, spi_data = daq["fastrx0"].parse_word(int(data[i]))
                data_str = f"{spi_data:0{data_size}b}"
                frame_str = f"{frame_counter:0{28 - data_size}b}" if 28 - data_size > 0 else ""
                if frame_str:
                    print(f"[{i}] ID={identifier:04b} frame={frame_str} data={data_str}")
                else:
                    print(f"[{i}] ID={identifier:04b} data={data_str}")

            if len(data) % 2:
                print(f"{case_name}: warning: odd FIFO word count ({len(data)}); ignoring last word for code decode")

            Dout_list = []
            Dout_raw_list = []
            Bbits_list = []
            Dout_alt_list = []
            Dout_alt_raw_list = []
            Bbits_alt_list = []
            for pair_idx in range(len(data) // 2):
                raw_word0 = int(data[2 * pair_idx])
                raw_word1 = int(data[2 * pair_idx + 1])
                id0, frame0, spi0 = daq["fastrx0"].parse_word(raw_word0)
                id1, frame1, spi1 = daq["fastrx0"].parse_word(raw_word1)
                if frame0 != frame1:
                    print(f"{case_name}: warning: paired FIFO words have different frames: {frame0} != {frame1}")

                Bbits, Dout_raw, Bbits_alt, Dout_alt_raw = decode_conversion(spi0, spi1, data_size, code_weights)
                Dout = normalize_code(Dout_raw, code_weights)
                Dout_alt = normalize_code(Dout_alt_raw, code_weights)
                Bbits_list.append(Bbits)
                Dout_list.append(Dout)
                Dout_raw_list.append(Dout_raw)
                Bbits_alt_list.append(Bbits_alt)
                Dout_alt_list.append(Dout_alt)
                Dout_alt_raw_list.append(Dout_alt_raw)
                rows.append(
                    {
                        "adc": adc_index,
                        "config_adc": adc_index,
                        "mux_bits": mux_bits,
                        "selected_adc_cfg": SELECTED_ADC_CFG,
                        "other_adc_cfg": OTHER_ADC_CFG,
                        "case_name": case_name,
                        "sweep_index": sweep_index,
                        "vin_set_v": voltage,
                        "vin_read_v": actual,
                        "vdiff_v": actual - vin_n,
                        "conversion_index": pair_idx,
                        "raw_word0": raw_word0,
                        "raw_word1": raw_word1,
                        "id0": id0,
                        "id1": id1,
                        "frame0": frame0,
                        "frame1": frame1,
                        "spi0": spi0,
                        "spi1": spi1,
                        "Bbits": Bbits,
                        "Dout": Dout,
                        "Dout_raw": Dout_raw,
                    }
                )

            print(f"{case_name}: Bbits_list B16..B0: {Bbits_list}")
            print(f"{case_name}: Bbits__alt B16..B0: {Bbits_alt_list}")
            print(f"{case_name}: Dout_raw = sum(W16..W0 * B16..B0): {Dout_raw_list}")
            print(f"{case_name}: Dout_norm 0..4095: {Dout_list}")
            print(f"{case_name}: Dout__alt_raw = sum(W16..W0 * B16..B0): {Dout_alt_raw_list}")
            print(f"{case_name}: Dout__alt_norm 0..4095: {Dout_alt_list}")
            print(
                f"{case_name}: code spread={max(Dout_list) - min(Dout_list) if Dout_list else 'n/a'}, code average={sum(Dout_list) / len(Dout_list) if Dout_list else 'n/a'}"
            )
            print(
                f"{case_name}: Vdiff={(actual - vin_n) * 1000:.1f}mV, "
                f"Vin_p={voltage * 1000:.1f}mV, Vin_n={vin_n * 1000:.1f}mV\n"
            )

            # sleep based on Alex's gut feeling
            sleep(SLEEP_TIME)

        csv_path = SCAN_OUTDIR / f"{case_name}.csv"
        plot_path = SCAN_OUTDIR / f"{case_name}_transfer.png"
        write_adc_csv(adc_index, rows, SCAN_OUTDIR, csv_path=csv_path)
        plot_adc_transfer(
            adc_index,
            rows,
            SCAN_OUTDIR,
            title=f"FRIDA ADC {adc_index:02d} voltage sweep ({radix})",
            label="individual conversions",
            plot_path=plot_path,
        )
        # plot_code_histogram expects rows from repeated conversions at one fixed input voltage.

    # Step 9: Always turn off the source output and close hardware connections.
    daq["psu0"].off()
    daq.close()

    print("Done.")


if __name__ == "__main__":
    main()
