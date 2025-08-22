current_design frida

# Our liberty file is in units of ns, so we must use the same here

# Create clocks for sequencing signals
create_clock -name seq_init -period 100 -waveform {0 5} [get_ports seq_init]
create_clock -name seq_samp -period 100 -waveform {0 5} [get_ports seq_samp]
create_clock -name seq_comp -period 5 [get_ports seq_comp]
create_clock -name seq_update -period 5 [get_ports seq_update]

# Set clock uncertainties
set_clock_uncertainty 0.5 [all_clocks]

# No input/output delay specified now, as we aren't working at the chip level, and have no IO.

# Clock groups (since they are independent)
# Group all four clocks as mutually asynchronous
# This automatically implies fale_path between each other
set_clock_groups -asynchronous \
  -group {seq_init} \
  -group {seq_samp} \
  -group {seq_comp} \
  -group {seq_update}

# Path-specific delay constraints
# Critical paths from seq_init/seq_update through salogic to capdriver outputs

# Max delay constraints for seq_init to dac_cap_botplate outputs
set_max_delay 2.0 \
  -from [get_ports seq_init] \
  -to [get_pins */capdriver_p/dac_drive*] \
  -through [get_pins */salogic_p/dac_state*]

set_max_delay 2.0 \
  -from [get_ports seq_init] \
  -to [get_pins */capdriver_n/dac_drive*] \
  -through [get_pins */salogic_n/dac_state*]

# Max delay constraints for seq_update to dac_cap_botplate outputs  
set_max_delay 2.0 \
  -from [get_ports seq_update] \
  -to [get_pins */capdriver_p/dac_drive*] \
  -through [get_pins */salogic_p/dac_state*]

set_max_delay 2.0 \
  -from [get_ports seq_update] \
  -to [get_pins */capdriver_n/dac_drive*] \
  -through [get_pins */salogic_n/dac_state*]

# Min delays aren't for hold time, but to ensure minimal timing variation between DAC bits
set_min_delay 0.1 \
  -from [get_ports seq_init] \
  -to [get_pins */capdriver_p/dac_drive*] \
  -through [get_pins */salogic_p/dac_state*]

set_min_delay 0.1 \
  -from [get_ports seq_init] \
  -to [get_pins */capdriver_n/dac_drive*] \
  -through [get_pins */salogic_n/dac_state*]

set_min_delay 0.1 \
  -from [get_ports seq_update] \
  -to [get_pins */capdriver_p/dac_drive*] \
  -through [get_pins */salogic_p/dac_state*]

set_min_delay 0.1 \
  -from [get_ports seq_update] \
  -to [get_pins */capdriver_n/dac_drive*] \
  -through [get_pins */salogic_n/dac_state*]