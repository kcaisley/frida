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
  -to [get_pins -of_objects [get_net dac_drive_botplate_main_p*] -filter "direction==output"]

set_max_delay 2.0 \
  -from [get_ports seq_update] \
  -to [get_pins -of_objects [get_net dac_drive_botplate_main_n*] -filter "direction==output"]

set_max_delay 2.0 \
  -from [get_ports seq_update] \
  -to [get_pins -of_objects [get_net dac_drive_botplate_diff_p*] -filter "direction==output"]

set_max_delay 2.0 \
  -from [get_ports seq_update] \
  -to [get_pins -of_objects [get_net dac_drive_botplate_diff_n*] -filter "direction==output"]

# Min delay constraints from seq_update to capacitor driver output pins
set_min_delay 0.1 \
  -from [get_ports seq_update] \
  -to [get_pins -of_objects [get_net dac_drive_botplate_main_p*] -filter "direction==output"]

set_min_delay 0.1 \
  -from [get_ports seq_update] \
  -to [get_pins -of_objects [get_net dac_drive_botplate_main_n*] -filter "direction==output"]

set_min_delay 0.1 \
  -from [get_ports seq_update] \
  -to [get_pins -of_objects [get_net dac_drive_botplate_diff_p*] -filter "direction==output"]

set_min_delay 0.1 \
  -from [get_ports seq_update] \
  -to [get_pins -of_objects [get_net dac_drive_botplate_diff_n*] -filter "direction==output"]

# Power rail constraints - exclude from timing analysis
# These are static power supplies that should not be analyzed for timing
set_false_path -through [get_nets "vdd_a"]
set_false_path -through [get_nets "vss_a"] 
set_false_path -through [get_nets "vdd_d"]
set_false_path -through [get_nets "vss_d"]
set_false_path -through [get_nets "vdd_dac"] 
set_false_path -through [get_nets "vss_dac"]