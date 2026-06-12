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

NUM_ADCS = 1
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


# Capacitor array weights from caparray.sp, labeled left-to-right as C16..C1.
# These sum to 2047 = 2^11 - 1 (11-bit DAC range). The 17 output-bit weights
# W16..W0 are [2*C16, 2*C15, ..., 2*C1, 1], which sum to 4095 = 2^12 - 1.
# The 2x factor in W16..W1 follows the recombination shown by Liu et al.,
# IEEE JSSC 50(11), 2645-2654 (2015), Section III, DOI: 10.1109/JSSC.2015.2466475
CAP_WEIGHTS = [768, 512, 320, 192, 96, 64, 32, 24, 12, 10, 5, 4, 4, 2, 1, 1]
CODE_WEIGHTS = [2 * weight for weight in CAP_WEIGHTS] + [1]
NUM_CAPTURE_BITS = len(CODE_WEIGHTS)
DECIMATE_PHASE = 1  # Try 1 if the decoded transfer still looks phase-shifted/noisy.
MAX_RAW_FASTRX_WORDS = 2 * CONVERSIONS_PER_VIN  # Print all expected raw words; all words are still decoded.


def scpi_float(value) -> float:
    """Convert a SCPI response to float, accepting comma-separated readback strings."""
    return float(str(value).strip().split(",")[0])


def decode_conversion(spi0: int, spi1: int, data_size: int) -> tuple[str, int]:
    """Decode two FastRX words into Bbits and recombine W16..W0 into Dout.

    fast_spi_rx shifts samples left, so temporal order within each displayed word is
    left-to-right: bit DATA_SIZE-1 -> bit 0. The decimated 17-bit output is labeled
    Bbits = B16..B0 and recombined directly with CODE_WEIGHTS = W16..W0.
    """
    if DECIMATE_PHASE not in (0, 1):
        raise ValueError(f"DECIMATE_PHASE must be 0 or 1, got {DECIMATE_PHASE}")

    samples = [(spi0 >> i) & 1 for i in range(data_size - 1, -1, -1)]
    samples += [(spi1 >> i) & 1 for i in range(data_size - 1, -1, -1)]

    decimated = [samples[DECIMATE_PHASE + 2 * i] for i in range(NUM_CAPTURE_BITS)]
    Bbits = "".join(str(bit) for bit in decimated)
    Dout = sum(weight * bit for weight, bit in zip(CODE_WEIGHTS, decimated))

    alt_phase = 1 - DECIMATE_PHASE
    decimated_alt = [samples[alt_phase + 2 * i] for i in range(NUM_CAPTURE_BITS)]
    Bbits_alt = "".join(str(bit) for bit in decimated_alt)
    Dout_alt = sum(weight * bit for weight, bit in zip(CODE_WEIGHTS, decimated_alt))

    return Bbits, Dout, Bbits_alt, Dout_alt


def spi_config_to_bytes(config: dict) -> bytes:
    """Flatten and print one 180-bit FRIDA SPI config dictionary."""
    from bitarray import bitarray

    bits = bitarray(180)
    bits.setall(0)

    dac_fields = ["dac_astate_p", "dac_bstate_p", "dac_astate_n", "dac_bstate_n"]
    for bank, field in enumerate(dac_fields):
        value = config[field]
        value_bits = bitarray(value) if isinstance(value, str) else bitarray(value)
        if len(value_bits) != 16:
            raise ValueError(f"{field} must be 16 bits, got {len(value_bits)}")
        bits[16 * bank : 16 * (bank + 1)] = value_bits

    adc_fields = ["en_init", "en_samp_p", "en_samp_n", "en_comp", "en_update", "dac_mode", "dac_diffcaps"]
    mux_sel = int(config["mux_sel"])
    if not 0 <= mux_sel < 16:
        raise ValueError(f"mux_sel must be in 0..15, got {mux_sel}")
    adc_cfg = bitarray([bool(config[field]) for field in adc_fields])
    channel_mask = config.get("channel_mask", [adc == mux_sel for adc in range(16)])
    channel_mask_bits = bitarray(channel_mask) if isinstance(channel_mask, str) else bitarray(channel_mask)
    if len(channel_mask_bits) != 16:
        raise ValueError(f"channel_mask must be 16 bits, got {len(channel_mask_bits)}")
    for adc, enabled in enumerate(channel_mask_bits):
        if enabled:
            base = 64 + 7 * adc
            bits[base : base + 7] = adc_cfg
    bits[176:180] = bitarray(f"{mux_sel:04b}"[::-1])

    dac_headers = []
    dac_values = []
    for bank, field in enumerate(dac_fields):
        start = 16 * bank
        stop = start + 15
        dac_headers.append(f"{field}[{start}:{stop}]")
        dac_values.append(str(config[field]))
    col_width = 22
    print("".join(header.ljust(col_width) for header in dac_headers))
    print("".join(value.ljust(col_width) for value in dac_values))

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

    mux_header = "MUX_SEL[176:179]"
    mux_value = bits[176:180].to01()
    print(mux_header)
    print(mux_value)

    return bits.tobytes()


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

    # Step 8: Build the voltage sweep and scan each ADC one at a time.
    voltages = VINP_SWEEP_V
    print(f"\nStarting voltage sweep for {NUM_ADCS} ADCs...")
    print(f"Cap weights C16..C1: {CAP_WEIGHTS}")
    print(f"Bit weights W16..W0: {CODE_WEIGHTS}")

    for adc_index in range(NUM_ADCS):
        print(f"\n=== Starting ADC {adc_index:02d} sweep ===")

        # DAC strings are written left-to-right into spi_bits[63:48], [47:32], [31:16], and [15:0].
        # In frida_core.v, dac_*state_*[15] gets the leftmost character and is the MSB capacitor bit.
        spi_config = {
            "dac_astate_p": "0111111111111111",  # A-state P, used in normal SAR mode
            "dac_astate_n": "0111111111111111",  # A-state N, used in normal SAR mode
            "dac_bstate_p": "1111111111111111",  # B-state P, used in calibration mode
            "dac_bstate_n": "1111111111111111",  # B-state N, used in calibration mode
            "en_init": 1,  # Enable INIT pulse (DAC reset before conversion)
            "en_samp_p": 1,  # Enable sample phase P-side
            "en_samp_n": 1,  # Enable sample phase N-side
            "en_comp": 1,  # Enable comparator clock
            "en_update": 1,  # Enable DAC update (load SAR decision into DAC)
            "dac_mode": 1,  # SAR mode (0 = calibration mode)
            "dac_diffcaps": 1,  # Enable differential caps (needed for unit caps)
            "channel_mask": "1100000000000000",  # ADC00..ADC15: 1 = receives clocks/config, 0 = disabled
            "mux_sel": adc_index,  # Select ADC to observe through the comparator mux
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
        print(f"ADC {adc_index:02d} SPI verify: {((bits[1:] ^ rb[1:]).count(1))} mismatches (skip bit 0)")

        # Clear stale capture data before each ADC sweep.
        daq["fifo0"]["RESET"]
        daq["fifo0"].get_data()

        rows = []
        for sweep_index, voltage in enumerate(voltages):
            print(f"ADC {adc_index:02d}: setting PSU to {voltage * 1000:.0f} mV ({voltage:.3f} V)")
            daq["psu0"].set_voltage(voltage)
            daq["psu0"].on()
            sleep(SLEEP_TIME)
            actual = scpi_float(daq["psu0"].get_voltage())
            print(f"ADC {adc_index:02d}: PSU readback {actual * 1000:.0f} mV ({actual:.3f} V)")
            vin_n = 0.600

            # Start the sequencer via the Basil bus. RX_EN_MUX=1 keeps FastRX enable driven
            # by the sequencer RX_EN track, so no GPIO start/holdoff signal is needed.
            daq["seq0"].start()

            # Old GPIO external-start version. If re-enabling this, also set:
            # daq["seq0"].set_en_ext_start(True)
            # daq["gpio0"]["SEQ_START"] = 1
            # daq["gpio0"].write()
            # sleep(0.001)
            # daq["gpio0"]["SEQ_START"] = 0
            # daq["gpio0"].write()

            while not daq["seq0"].is_done():  # is_done will not actually return 1, unless SEQ_START is ended.
                sleep(0.1)
                print(f"ADC {adc_index:02d}: waiting for sequencer!")

            sleep(FAST_RX_DRAIN_SLEEP)
            data = daq["fifo0"].get_data()
            print(f"ADC {adc_index:02d}: FIFO ({len(data)} words)")

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
                print(
                    f"ADC {adc_index:02d}: warning: odd FIFO word count ({len(data)}); ignoring last word for code decode"
                )

            Dout_list = []
            Bbits_list = []
            Dout_alt_list = []
            Bbits_alt_list = []
            for pair_idx in range(len(data) // 2):
                raw_word0 = int(data[2 * pair_idx])
                raw_word1 = int(data[2 * pair_idx + 1])
                id0, frame0, spi0 = daq["fastrx0"].parse_word(raw_word0)
                id1, frame1, spi1 = daq["fastrx0"].parse_word(raw_word1)
                if frame0 != frame1:
                    print(
                        f"ADC {adc_index:02d}: warning: paired FIFO words have different frames: {frame0} != {frame1}"
                    )

                Bbits, Dout, Bbits_alt, Dout_alt = decode_conversion(spi0, spi1, data_size)
                Bbits_list.append(Bbits)
                Dout_list.append(Dout)
                Bbits_alt_list.append(Bbits_alt)
                Dout_alt_list.append(Dout_alt)
                rows.append(
                    {
                        "adc": adc_index,
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
                    }
                )

            print(f"ADC {adc_index:02d}: Bbits_list B16..B0: {Bbits_list}")
            print(f"ADC {adc_index:02d}: Bbits__alt B16..B0: {Bbits_alt_list}")
            print(f"ADC {adc_index:02d}: Dout_list = sum(W16..W0 * B16..B0): {Dout_list}")
            print(f"ADC {adc_index:02d}: Dout__alt = sum(W16..W0 * B16..B0): {Dout_alt_list}")
            print(
                f"ADC {adc_index:02d}: code spread={max(Dout_list) - min(Dout_list) if Dout_list else 'n/a'}, code average={sum(Dout_list) / len(Dout_list) if Dout_list else 'n/a'}"
            )
            print(
                f"ADC {adc_index:02d}: Vdiff={(actual - vin_n) * 1000:.1f}mV, "
                f"Vin_p={voltage * 1000:.1f}mV, Vin_n={vin_n * 1000:.1f}mV\n"
            )

            # sleep based on Alex's gut feeling
            sleep(SLEEP_TIME)

        write_adc_csv(adc_index, rows, SCAN_OUTDIR)
        plot_adc_transfer(
            adc_index,
            rows,
            SCAN_OUTDIR,
            title=f"FRIDA ADC {adc_index:02d} basic voltage sweep",
            label="individual conversions",
        )
        # plot_code_histogram expects rows from repeated conversions at one fixed input voltage.

    # Step 9: Always turn off the source output and close hardware connections.
    daq["psu0"].off()
    daq.close()

    print("Done.")


if __name__ == "__main__":
    main()
