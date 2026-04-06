# FRIDA Sequencer Waveform Generation
#
# Based on:
#   - CordiaADC/ADC_01/host/meas_config.py (sequencer setup)
#   - CordiaADC/ADC_01/host/meas_seq_11bit.csv (timing patterns)
#   - frida/spice/tb_frida_top.sp (reference timing from SPICE TB)
#
# Generates timing sequences for the 6 sequencer output signals:
#   CLK_INIT      - DAC initialization pulse
#   CLK_SAMP      - Sample-and-hold trigger
#   CLK_COMP      - Comparator clock (5ns period = 2.5ns high, 2.5ns low)
#   CLK_LOGIC     - SAR logic clock (5ns period, interleaved with CLK_COMP)
#   CLK_COMP_CAP  - Capture clock for fast_spi_rx SCLK (samples COMP_OUT)
#   SEN_COMP      - Frame enable for fast_spi_rx SEN (high during 17 capture cycles)
#
# At 400 MHz sequencer clock (2.5ns steps), one 100ns conversion = 40 steps:
#
#   Step: 0  1  2  3  4  5  6  7  8  9 10 11 12 13  ...  37 38 39
#   Time: 0    2.5  5    7.5  10   12.5 15   17.5 20      92.5 95  97.5 ns
#         |    |    |    |    |    |    |    |    |              |    |
#  INIT:  1  1  0  0  0  0  0  0  0  0  0  0  0  0  ...  0  0  0  0
#  SAMP:  0  0  1  1  1  1  0  0  0  0  0  0  0  0  ...  0  0  0  0
#  COMP:  0  0  0  0  0  0  1  0  1  0  1  0  1  0  ...  1  0  0  0
# LOGIC:  0  0  0  0  0  0  0  1  0  1  0  1  0  1  ...  0  0  0  0
#
# INIT:  2 steps (5ns)
# SAMP:  4 steps (10ns)
# COMP: 17 pulses, each 1 step high / 1 step low = 34 steps (85ns)
# LOGIC: 16 pulses, interleaved with COMP (first comp is "free" — before any DAC switch)
# Total: 2 + 4 + 34 = 40 steps = 100ns = 10 Msps

from __future__ import annotations


def generate_conversion_sequence(
    conversion_period_ns: int = 100,
    seq_clk_period_ns: float = 2.5,
    init_pulse_ns: float = 5.0,
    samp_pulse_ns: float = 10.0,
    n_comp_bits: int = 17,
    capture_delay_steps: int = 1,
) -> dict[str, list[int]]:
    """Generate sequencer waveforms for one ADC conversion cycle.

    At 400 MHz (2.5ns steps), 100ns = 40 steps:
    - CLK_INIT: 5ns pulse (2 steps) at t=0
    - CLK_SAMP: 10ns pulse (4 steps) starting at t=5ns
    - CLK_COMP: 17 pulses of 2.5ns each, starting at t=15ns
    - CLK_LOGIC: 16 pulses of 2.5ns each, interleaved with CLK_COMP
      (first comparison is free — before any DAC switching)
    - CLK_COMP_CAP: Capture clock for sampling COMP_OUT
    - SEN_COMP: Frame enable, high during all 17 capture cycles

    Args:
        conversion_period_ns: Total conversion time (default 100ns = 10 Msps)
        seq_clk_period_ns: Sequencer clock period (default 2.5ns = 400 MHz)
        init_pulse_ns: Duration of CLK_INIT pulse (default 5ns)
        samp_pulse_ns: Duration of CLK_SAMP pulse (default 10ns)
        n_comp_bits: Number of comparator bits (default 17 for 16-bit CDAC + 1 free)
        capture_delay_steps: Steps to delay CLK_COMP_CAP for propagation compensation

    Returns:
        Dictionary with keys 'CLK_INIT', 'CLK_SAMP', 'CLK_COMP', 'CLK_LOGIC',
        'CLK_COMP_CAP', 'SEN_COMP', each containing a list of 0/1 values.
    """
    n_steps = int(conversion_period_ns / seq_clk_period_ns)

    clk_init = [0] * n_steps
    clk_samp = [0] * n_steps
    clk_comp = [0] * n_steps
    clk_logic = [0] * n_steps
    clk_comp_cap = [0] * n_steps
    sen_comp = [0] * n_steps

    # Phase boundaries (in steps)
    init_steps = int(init_pulse_ns / seq_clk_period_ns)       # 2 steps
    samp_steps = int(samp_pulse_ns / seq_clk_period_ns)       # 4 steps
    samp_start = init_steps                                    # step 2
    comp_start = init_steps + samp_steps                       # step 6

    # CLK_INIT: high for init_steps
    for i in range(init_steps):
        clk_init[i] = 1

    # CLK_SAMP: high for samp_steps
    for i in range(samp_start, samp_start + samp_steps):
        clk_samp[i] = 1

    # CLK_COMP and CLK_LOGIC: interleaved from comp_start
    # Each comparison cycle = 2 steps: CLK_COMP high, then CLK_LOGIC high
    # First cycle: comp only (free comparison before any DAC switch)
    # Subsequent cycles: comp then logic (comparison then DAC switch)
    n_logic_bits = n_comp_bits - 1  # 16 DAC switches for 17 comparisons
    for bit in range(n_comp_bits):
        comp_step = comp_start + bit * 2
        if comp_step < n_steps:
            clk_comp[comp_step] = 1
        logic_step = comp_start + bit * 2 + 1
        if bit < n_logic_bits and logic_step < n_steps:
            clk_logic[logic_step] = 1

    # CLK_COMP_CAP: Capture clock for fast_spi_rx SCLK
    # Samples COMP_OUT. Delayed by capture_delay_steps to compensate for
    # round-trip propagation (FPGA -> LVDS -> chip -> comparator -> LVDS -> FPGA).
    # Sample during the CLK_LOGIC phase (result is stable after comparison).
    for bit in range(n_comp_bits):
        sample_step = comp_start + bit * 2 + 1 + capture_delay_steps
        if sample_step < n_steps:
            clk_comp_cap[sample_step] = 1

    # SEN_COMP: Frame enable for fast_spi_rx
    # High from first comparison through last capture, then goes low to flush.
    sen_start = comp_start
    last_capture = comp_start + (n_comp_bits - 1) * 2 + 1 + capture_delay_steps
    sen_end = min(last_capture + 2, n_steps)
    for i in range(sen_start, sen_end):
        sen_comp[i] = 1

    return {
        "CLK_INIT": clk_init,
        "CLK_SAMP": clk_samp,
        "CLK_COMP": clk_comp,
        "CLK_LOGIC": clk_logic,
        "CLK_COMP_CAP": clk_comp_cap,
        "SEN_COMP": sen_comp,
    }


def generate_multi_conversion_sequence(
    n_conversions: int,
    conversion_period_ns: int = 100,
    seq_clk_period_ns: float = 2.5,
    capture_delay_steps: int = 1,
) -> dict[str, list[int]]:
    """Generate sequencer waveforms for multiple conversion cycles.

    Args:
        n_conversions: Number of conversion cycles
        conversion_period_ns: Time per conversion (default 100ns)
        seq_clk_period_ns: Sequencer clock period (default 2.5ns)
        capture_delay_steps: Delay for CLK_COMP_CAP

    Returns:
        Dictionary with concatenated waveforms for all conversions
    """
    single = generate_conversion_sequence(
        conversion_period_ns=conversion_period_ns,
        seq_clk_period_ns=seq_clk_period_ns,
        capture_delay_steps=capture_delay_steps,
    )

    return {key: single[key] * n_conversions for key in single}


def sequence_to_csv(sequence: dict[str, list[int]], filename: str) -> None:
    """Write a sequence to CSV file.

    Args:
        sequence: Dictionary of track waveforms
        filename: Output CSV filename
    """
    tracks = [
        "CLK_INIT",
        "CLK_SAMP",
        "CLK_COMP",
        "CLK_LOGIC",
        "CLK_COMP_CAP",
        "SEN_COMP",
    ]
    n_steps = len(sequence[tracks[0]])

    with open(filename, "w") as f:
        f.write(",".join(tracks) + "\n")
        for i in range(n_steps):
            row = [str(sequence[track][i]) for track in tracks]
            f.write(",".join(row) + "\n")


def sequence_from_csv(filename: str) -> dict[str, list[int]]:
    """Load a sequence from CSV file.

    Args:
        filename: Input CSV filename

    Returns:
        Dictionary of track waveforms
    """
    with open(filename) as f:
        lines = f.readlines()

    header = lines[0].strip().split(",")
    sequence: dict[str, list[int]] = {track: [] for track in header}
    for line in lines[1:]:
        values = line.strip().split(",")
        for track, value in zip(header, values):
            sequence[track].append(int(value))

    return sequence


def print_sequence_timing(
    sequence: dict[str, list[int]], seq_clk_period_ns: float = 2.5
) -> None:
    """Print a visual representation of sequence timing.

    Args:
        sequence: Dictionary of track waveforms
        seq_clk_period_ns: Sequencer clock period for time labels
    """
    tracks = [
        "CLK_INIT",
        "CLK_SAMP",
        "CLK_COMP",
        "CLK_LOGIC",
        "CLK_COMP_CAP",
        "SEN_COMP",
    ]
    n_steps = len(sequence[tracks[0]])

    print(f"Sequence timing ({n_steps} steps, {seq_clk_period_ns}ns/step):")
    print("-" * 70)

    for track in tracks:
        waveform = sequence[track]
        chars = []
        for v in waveform:
            chars.append("_" if v == 0 else "-")
        print(f"{track:14s}: {''.join(chars)}")

    # Time axis
    print(" " * 16, end="")
    for i in range(0, n_steps, 4):
        print(f"{i * seq_clk_period_ns:4.0f}", end="")
    print(" ns")


# Default sequence for quick reference
DEFAULT_CONVERSION_SEQUENCE = generate_conversion_sequence()

if __name__ == "__main__":
    seq = generate_conversion_sequence()
    print_sequence_timing(seq)
    print()

    # Count pulses
    for track in ['CLK_INIT', 'CLK_SAMP', 'CLK_COMP', 'CLK_LOGIC']:
        data = seq[track]
        high_steps = sum(data)
        print(f'{track:14s}: {high_steps} pulses')
