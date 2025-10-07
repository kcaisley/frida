current_design frida_core

# ============================================================================
# Source Synchronous Clock Inputs - seq_* signals from FPGA via IO pads
# ============================================================================

# Create clocks to enable CTS to build H-tree distribution networks
create_clock -name "seq_init" -period 5.000 [get_ports "seq_init"]
create_clock -name "seq_samp" -period 5.000 [get_ports "seq_samp"]
create_clock -name "seq_comp" -period 5.000 [get_ports "seq_comp"]
create_clock -name "seq_logic" -period 5.000 [get_ports "seq_logic"]

# Model IO pad drive strength (CKBD24LVT buffer inside the IO pad ring)
set_driving_cell -lib_cell "CKBD24LVT" [get_ports "seq_init seq_samp seq_comp seq_logic"]

# ============================================================================
# Source Synchronous Skew Constraints - 200ps window to 16 ADC instances
# ============================================================================

# set adc_seq_init_pins [get_pins -hierarchical "adc_array\[*\].adc_inst/seq_init"]
# set adc_seq_samp_pins [get_pins -hierarchical "adc_array\[*\].adc_inst/seq_samp"]
# set adc_seq_comp_pins [get_pins -hierarchical "adc_array\[*\].adc_inst/seq_comp"]
# set adc_seq_update_pins [get_pins -hierarchical "adc_array\[*\].adc_inst/seq_update"]

# # 200ps skew window
# set_max_delay 7.900 -from [get_ports seq_init] -to $adc_seq_init_pins -ignore_clock_latency
# set_min_delay 7.700 -from [get_ports seq_init] -to $adc_seq_init_pins -ignore_clock_latency

# set_max_delay 7.900 -from [get_ports seq_samp] -to $adc_seq_samp_pins -ignore_clock_latency
# set_min_delay 7.700 -from [get_ports seq_samp] -to $adc_seq_samp_pins -ignore_clock_latency

# set_max_delay 7.900 -from [get_ports seq_comp] -to $adc_seq_comp_pins -ignore_clock_latency
# set_min_delay 7.700 -from [get_ports seq_comp] -to $adc_seq_comp_pins -ignore_clock_latency

# set_max_delay 7.900 -from [get_ports seq_logic] -to $adc_seq_update_pins -ignore_clock_latency
# set_min_delay 7.700 -from [get_ports seq_logic] -to $adc_seq_update_pins -ignore_clock_latency

# ============================================================================
# SPI Clock (configuration interface)
# ============================================================================

# Create SPI clock (slower, for register configuration)
create_clock -name "spi_sclk" -period 100.000 [get_ports "spi_sclk"]

# Model IO pad drive strength (BUFFD2LVT for SPI interface)
set_driving_cell -lib_cell "BUFFD2LVT" [get_ports "spi_sclk"]

# One of -logically_exclusive, -physically_exclusive or -asynchronous is required
set_clock_groups -logically_exclusive \
  -group [get_clocks "spi_sclk"] \
  -group [get_clocks "seq_init seq_samp seq_comp seq_logic"]