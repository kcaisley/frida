current_design adc

# Clock definitions
set seq_init_period 100.0
set seq_samp_period 50.0
set seq_comp_period 20.0
set seq_update_period 40.0
set clk_io_pct 0.2

# Create clocks for sequencing signals
create_clock -name seq_init_clk -period $seq_init_period [get_ports seq_init]
create_clock -name seq_samp_clk -period $seq_samp_period [get_ports seq_samp]
create_clock -name seq_comp_clk -period $seq_comp_period [get_ports seq_comp]
create_clock -name seq_update_clk -period $seq_update_period [get_ports seq_update]

# Set clock uncertainties
set_clock_uncertainty 0.1 [all_clocks]

# Input/Output delays
set non_clock_inputs [all_inputs -no_clocks]
set_input_delay [expr $seq_comp_period * $clk_io_pct] -clock seq_comp_clk $non_clock_inputs
set_output_delay [expr $seq_comp_period * $clk_io_pct] -clock seq_comp_clk [all_outputs]

# Clock groups (since they are independent)
set_clock_groups -asynchronous \
  -group [get_clocks seq_init_clk] \
  -group [get_clocks seq_samp_clk] \
  -group [get_clocks seq_comp_clk] \
  -group [get_clocks seq_update_clk]

# Set false paths for reset signal
set_false_path -from [get_ports rst]

# Set max delay for critical paths
set_max_delay 15.0 -from [get_ports seq_comp] -to [get_ports comp_out]