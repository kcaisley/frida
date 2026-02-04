# FRIDA Sequencer Waveform Generation
#
# Based on:
#   - CordiaADC/ADC_01/host/meas_config.py (sequencer setup)
#   - CordiaADC/ADC_01/host/meas_seq_11bit.csv (timing patterns)
#   - frida/spice/tb_frida_top.sp (reference timing from SPICE TB)
#
# Generates timing sequences for the 4 LVDS clock signals:
#   CLK_INIT  - DAC initialization pulse
#   CLK_SAMP  - Sample-and-hold trigger
#   CLK_COMP  - Comparator clock (200 MHz toggle)
#   CLK_LOGIC - SAR logic clock (200 MHz toggle, 2.5ns delayed)
#
# Timing diagram for one 100ns conversion cycle at 10 Msps (from tb_frida_top.sp):
#
#              0    5   15                                              100 ns
#              |    |    |                                               |
#              |    |    |                                               |
#  CLK_INIT    |‾‾‾‾|____|_______________________________________________|
#              |    |    |                                               |
#  CLK_SAMP    |____|‾‾‾‾|_______________________________________________|
#              |    |    |                                               |
#  CLK_COMP    |____|____|‾‾|__|‾‾|__|‾‾|__|‾‾|__|‾‾|__|‾‾|__|‾‾|__|‾‾|__|
#              |    |    |                                               |
#  CLK_LOGIC   |____|____|__|‾‾|__|‾‾|__|‾‾|__|‾‾|__|‾‾|__|‾‾|__|‾‾|__|‾‾|
#              |    |    |                                               |
#              |init|samp|        comp/logic alternating (17 cycles)     |
#              |    |    |                                               |

from __future__ import annotations


def generate_conversion_sequence(
    conversion_period_ns: int = 100,
    seq_clk_period_ns: float = 5.0,
    init_pulse_ns: float = 5.0,
    samp_pulse_ns: float = 10.0,
    comp_logic_period_ns: float = 5.0,
) -> dict[str, list[int]]:
    """Generate sequencer waveforms for one ADC conversion cycle.

    Based on:
        - frida/spice/tb_frida_top.sp (timing values and waveform structure)
        - frida/spice/tb_frida_top_smoketest.sp (simplified timing reference)
        - CordiaADC/ADC_01/host/meas_config.py (sequencer loading pattern)

    The timing follows the pattern from tb_frida_top.sp:
    - CLK_INIT: 5ns pulse at t=0
    - CLK_SAMP: 10ns pulse starting at t=5ns
    - CLK_COMP: 5ns period toggle starting at t=15ns
    - CLK_LOGIC: 5ns period toggle, 2.5ns delayed from CLK_COMP

    Args:
        conversion_period_ns: Total conversion time (default 100ns = 10 Msps)
        seq_clk_period_ns: Sequencer clock period (default 5ns = 200 MHz)
        init_pulse_ns: Duration of CLK_INIT pulse
        samp_pulse_ns: Duration of CLK_SAMP pulse
        comp_logic_period_ns: Period of CLK_COMP/CLK_LOGIC toggle

    Returns:
        Dictionary with keys 'CLK_INIT', 'CLK_SAMP', 'CLK_COMP', 'CLK_LOGIC',
        each containing a list of 0/1 values for each sequencer step.
    """
    # Calculate number of steps
    n_steps = int(conversion_period_ns / seq_clk_period_ns)

    # Initialize all tracks to 0
    clk_init = [0] * n_steps
    clk_samp = [0] * n_steps
    clk_comp = [0] * n_steps
    clk_logic = [0] * n_steps

    # Time indices for each phase
    init_start = 0
    init_end = int(init_pulse_ns / seq_clk_period_ns)  # step 1

    samp_start = int(5.0 / seq_clk_period_ns)  # step 1
    samp_end = int(15.0 / seq_clk_period_ns)  # step 3

    comp_start = int(15.0 / seq_clk_period_ns)  # step 3

    # CLK_INIT: pulse from 0 to init_end
    for i in range(init_start, min(init_end, n_steps)):
        clk_init[i] = 1

    # CLK_SAMP: pulse from samp_start to samp_end
    for i in range(samp_start, min(samp_end, n_steps)):
        clk_samp[i] = 1

    # CLK_COMP and CLK_LOGIC: alternating from comp_start
    # CLK_COMP toggles on even steps, CLK_LOGIC on odd steps (2.5ns offset)
    for i in range(comp_start, n_steps):
        step_in_toggle = i - comp_start
        # CLK_COMP: high on even toggle steps
        clk_comp[i] = 1 if (step_in_toggle % 2 == 0) else 0
        # CLK_LOGIC: high on odd toggle steps (2.5ns delayed)
        clk_logic[i] = 1 if (step_in_toggle % 2 == 1) else 0

    return {
        "CLK_INIT": clk_init,
        "CLK_SAMP": clk_samp,
        "CLK_COMP": clk_comp,
        "CLK_LOGIC": clk_logic,
    }


def generate_multi_conversion_sequence(
    n_conversions: int,
    conversion_period_ns: int = 100,
    seq_clk_period_ns: float = 5.0,
) -> dict[str, list[int]]:
    """Generate sequencer waveforms for multiple conversion cycles.

    Based on:
        - basil/basil/HL/seq_gen.py (set_repeat for hardware looping)
        - CordiaADC/ADC_01/host/meas.py (multi-sample acquisition pattern)

    Args:
        n_conversions: Number of conversion cycles
        conversion_period_ns: Time per conversion (default 100ns)
        seq_clk_period_ns: Sequencer clock period (default 5ns)

    Returns:
        Dictionary with concatenated waveforms for all conversions
    """
    single = generate_conversion_sequence(
        conversion_period_ns=conversion_period_ns,
        seq_clk_period_ns=seq_clk_period_ns,
    )

    return {key: single[key] * n_conversions for key in single}


def sequence_to_csv(sequence: dict[str, list[int]], filename: str) -> None:
    """Write a sequence to CSV file (CordiaADC format).

    Based on:
        - CordiaADC/ADC_01/host/meas_seq_11bit.csv (file format)
        - CordiaADC/ADC_01/host/meas_seq_13bit.csv (file format)

    The CSV format has one column per track, one row per step.
    This matches the format used by CordiaADC's meas_seq_*.csv files.

    Args:
        sequence: Dictionary of track waveforms
        filename: Output CSV filename
    """
    tracks = ["CLK_INIT", "CLK_SAMP", "CLK_COMP", "CLK_LOGIC"]
    n_steps = len(sequence[tracks[0]])

    with open(filename, "w") as f:
        # Header
        f.write(",".join(tracks) + "\n")
        # Data rows
        for i in range(n_steps):
            row = [str(sequence[track][i]) for track in tracks]
            f.write(",".join(row) + "\n")


def sequence_from_csv(filename: str) -> dict[str, list[int]]:
    """Load a sequence from CSV file.

    Based on:
        - CordiaADC/ADC_01/host/meas_config.py (CSV loading pattern)

    Args:
        filename: Input CSV filename

    Returns:
        Dictionary of track waveforms
    """
    with open(filename) as f:
        lines = f.readlines()

    # Parse header
    header = lines[0].strip().split(",")

    # Parse data
    sequence: dict[str, list[int]] = {track: [] for track in header}
    for line in lines[1:]:
        values = line.strip().split(",")
        for track, value in zip(header, values):
            sequence[track].append(int(value))

    return sequence


def print_sequence_timing(
    sequence: dict[str, list[int]], seq_clk_period_ns: float = 5.0
) -> None:
    """Print a visual representation of sequence timing.

    Based on:
        - basil/tests/test_SimSeq.py (sequence visualization concept)

    Args:
        sequence: Dictionary of track waveforms
        seq_clk_period_ns: Sequencer clock period for time labels
    """
    tracks = ["CLK_INIT", "CLK_SAMP", "CLK_COMP", "CLK_LOGIC"]
    n_steps = len(sequence[tracks[0]])

    print(f"Sequence timing ({n_steps} steps, {seq_clk_period_ns}ns/step):")
    print("-" * 60)

    for track in tracks:
        waveform = sequence[track]
        # Create ASCII waveform
        chars = []
        for v in waveform:
            chars.append("_" if v == 0 else "-")
        print(f"{track:12s}: {''.join(chars)}")

    # Time axis
    print(" " * 14, end="")
    for i in range(0, n_steps, 4):
        print(f"{i * seq_clk_period_ns:4.0f}", end="")
    print(" ns")


# Default sequence for quick reference
DEFAULT_CONVERSION_SEQUENCE = generate_conversion_sequence()

if __name__ == "__main__":
    # Generate and print default sequence
    seq = generate_conversion_sequence()
    print_sequence_timing(seq)

    # Generate 3-conversion sequence
    print("\n3-conversion sequence:")
    multi_seq = generate_multi_conversion_sequence(3)
    print(f"Total steps: {len(multi_seq['CLK_INIT'])}")
