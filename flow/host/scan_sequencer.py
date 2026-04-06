"""Scan: Run the FRIDA sequencer continuously and output on PMOD/LVDS.

Usage (from ~/frida/):
    uv run --extra daq python flow/host/scan_sequencer.py
"""

import logging
import time
import warnings
from pathlib import Path

from basil.dut import Dut

from flow.host.sequences import generate_conversion_sequence, print_sequence_timing

warnings.filterwarnings("ignore", category=UserWarning, message="pkg_resources")
logging.getLogger("basil").setLevel(logging.WARNING)

# Connect to FPGA
dut = Dut(str(Path("flow/host/map_fpga.yaml")))
dut.init()
print("DAQ initialized")

# Generate the 40-step conversion sequence (2.5ns per step, 100ns total)
seq = generate_conversion_sequence()
n_steps = len(seq["CLK_INIT"])
print_sequence_timing(seq)

# Pack 6 tracks into bytes and write to seq_gen memory
tracks = ["CLK_INIT", "CLK_SAMP", "CLK_COMP", "CLK_LOGIC", "CLK_COMP_CAP", "SEN_COMP"]
for step in range(n_steps):
    byte_val = 0
    for bit, track in enumerate(tracks):
        byte_val |= seq[track][step] << bit
    dut["seq"].set_data([byte_val], addr=step)
print(f"\nSequence loaded: {n_steps} steps into seq_gen")

# Configure sequencer
dut["seq"].set_size(n_steps)
dut["seq"].set_clk_divide(1)  # no division, use 400 MHz directly
dut["seq"].set_repeat(0)  # 0 = repeat forever
# Enable external start (pulse_gen triggers seq_gen)
dut["seq"].set_en_ext_start(True)

# Configure pulse_gen to trigger continuously
dut["pulse_gen"].set_delay(1)
dut["pulse_gen"].set_width(1)
dut["pulse_gen"].set_repeat(0)  # 0 = repeat forever
dut["pulse_gen"].start()

print("Sequencer running continuously on PMOD and LVDS outputs")
print("  PMOD pins 1-4: CLK_INIT, CLK_SAMP, CLK_COMP, CLK_LOGIC")
print("  PMOD pin 10:   SEQ_CLK (400 MHz)")
print("Press Ctrl+C to stop")

try:
    while True:
        time.sleep(1)
except KeyboardInterrupt:
    dut["pulse_gen"].reset()
    dut["seq"].reset()
    print("\nStopped")
