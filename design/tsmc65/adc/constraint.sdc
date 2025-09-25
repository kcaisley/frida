# Our liberty file is in units of ns, so we must use the same here

current_design adc

# Create clocks for sequencing signals
# create_clock -name seq_init -period 100 -waveform {0 5} [get_ports seq_init]
# create_clock -name seq_samp -period 100 -waveform {0 5} [get_ports seq_samp]
# create_clock -name seq_comp -period 5 [get_ports seq_comp]
create_clock -name seq_update -period 5 [get_ports seq_update]

# Set clock uncertainties
set_clock_uncertainty 0.1 [all_clocks]

# No input/output delay specified now, as we aren't working at the chip level, and have no IO.

# Clock groups (since they are independent)
# Group all four clocks as mutually asynchronous
# This automatically implies fale_path between each other
set_clock_groups -asynchronous \
  -group {seq_update}

# Max delay constraints from seq_update to capacitor driver output pins
set_max_delay 2.0 \
  -from [get_ports seq_update] \
  -to [get_pins capdriver_p_main/xor_gates*xor_gate/Z]

set_max_delay 2.0 \
  -from [get_ports seq_update] \
  -to [get_pins capdriver_n_main/xor_gates*xor_gate/Z]

set_max_delay 2.0 \
  -from [get_ports seq_update] \
  -to [get_pins capdriver_p_diff/xor_gates*xor_gate/Z]

set_max_delay 2.0 \
  -from [get_ports seq_update] \
  -to [get_pins capdriver_n_diff/xor_gates*xor_gate/Z]

# Min delay constraints from seq_update to capacitor driver output pins
set_min_delay 0.1 \
  -from [get_ports seq_update] \
  -to [get_pins capdriver_p_main/xor_gates*xor_gate/Z]

set_min_delay 0.1 \
  -from [get_ports seq_update] \
  -to [get_pins capdriver_n_main/xor_gates*xor_gate/Z]

set_min_delay 0.1 \
  -from [get_ports seq_update] \
  -to [get_pins capdriver_p_diff/xor_gates*xor_gate/Z]

set_min_delay 0.1 \
  -from [get_ports seq_update] \
  -to [get_pins capdriver_n_diff/xor_gates*xor_gate/Z]