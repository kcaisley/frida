# Top-level timing constraints for FRIDA chip
# 1mm x 1mm die with IO pads

# Create sequencing clocks from LVDS inputs
# These are the primary timing signals for the ADC operation
create_clock -name "seq_init" -period 100.000 [get_ports "seq_init_p_PAD"]
create_clock -name "seq_samp" -period 10.000 [get_ports "seq_samp_p_PAD"]  
create_clock -name "seq_cmp" -period 5.000 [get_ports "seq_cmp_p_PAD"]
create_clock -name "seq_logic" -period 20.000 [get_ports "seq_logic_p_PAD"]

# Create SPI clock (slower for configuration)
create_clock -name "spi_sclk" -period 100.000 [get_ports "spi_sclk_PAD"]

# Set clock uncertainty (jitter, skew, etc.)
set_clock_uncertainty 0.200 [all_clocks]

# Clock groups - seq_* clocks may be related, SPI is independent
set_clock_groups -asynchronous -group [get_clocks "spi_sclk"] \
                               -group [get_clocks "seq_init seq_samp seq_cmp seq_logic"]

# Balanced skew requirements for seq_* clock distribution to 16 ADCs
# These clocks need to arrive at all ADCs with minimal skew
# Note: OpenSTA doesn't support set_max_skew, use clock uncertainty instead
set_clock_uncertainty 0.1 [get_clocks "seq_init"]
set_clock_uncertainty 0.1 [get_clocks "seq_samp"] 
set_clock_uncertainty 0.1 [get_clocks "seq_cmp"]
set_clock_uncertainty 0.1 [get_clocks "seq_logic"]

# Input/output delays for pads
set_input_delay -clock [get_clocks "spi_sclk"] -max 2.0 [get_ports "spi_sdi_PAD"]
set_input_delay -clock [get_clocks "spi_sclk"] -min 1.0 [get_ports "spi_sdi_PAD"]
set_input_delay -clock [get_clocks "spi_sclk"] -max 2.0 [get_ports "spi_cs_b_PAD"]
set_input_delay -clock [get_clocks "spi_sclk"] -min 1.0 [get_ports "spi_cs_b_PAD"]

set_output_delay -clock [get_clocks "spi_sclk"] -max 2.0 [get_ports "spi_sdo_PAD"]
set_output_delay -clock [get_clocks "spi_sclk"] -min 1.0 [get_ports "spi_sdo_PAD"]

# Comparator output has critical timing - minimize delay
set_output_delay -clock [get_clocks "seq_cmp"] -max 1.0 [get_ports "comp_out_p_PAD"]
set_output_delay -clock [get_clocks "seq_cmp"] -min 0.5 [get_ports "comp_out_p_PAD"]

# Set driving cell for inputs (pad strength)
set_driving_cell -lib_cell "BUFFD2LVT" [all_inputs]

# Set load capacitance for outputs (pad load) 
set_load 0.1 [all_outputs]

# Set maximum transition time
set_max_transition 0.5 [current_design]

# Set maximum fanout (important for clock distribution)
set_max_fanout 20 [current_design]