# FRIDA Top-Level Timing Constraints for IHP-SG13G2 (updated for _PAD port names)

# Main system clock - 100 MHz
create_clock -name clk -period 10.0 [get_ports clk_PAD]

# SPI interface clocks - 10 MHz
create_clock -name spi_sclk -period 100.0 [get_ports spi_sclk_PAD]

# Input delays for SPI interface
set_input_delay -clock spi_sclk -max 5.0 [get_ports {spi_sdi_PAD spi_cs_b_PAD}]
set_input_delay -clock spi_sclk -min 1.0 [get_ports {spi_sdi_PAD spi_cs_b_PAD}]

# Output delays for SPI interface
set_output_delay -clock spi_sclk -max 5.0 [get_ports spi_sdo_PAD]
set_output_delay -clock spi_sclk -min 1.0 [get_ports spi_sdo_PAD]

# Input delays for analog signals (relaxed timing)
set_input_delay -clock clk -max 2.0 [get_ports {vin_p_PAD vin_n_PAD}]
set_input_delay -clock clk -min 0.5 [get_ports {vin_p_PAD vin_n_PAD}]

# Input delays for sequencer signals
set_input_delay -clock clk -max 2.0 [get_ports {seq_init_p_PAD seq_init_n_PAD seq_samp_p_PAD seq_samp_n_PAD seq_cmp_p_PAD seq_cmp_n_PAD seq_logic_p_PAD seq_logic_n_PAD}]
set_input_delay -clock clk -min 0.5 [get_ports {seq_init_p_PAD seq_init_n_PAD seq_samp_p_PAD seq_samp_n_PAD seq_cmp_p_PAD seq_cmp_n_PAD seq_logic_p_PAD seq_logic_n_PAD}]

# Output delays for comparator output
set_output_delay -clock clk -max 3.0 [get_ports {comp_out_p_PAD comp_out_n_PAD}]
set_output_delay -clock clk -min 0.5 [get_ports {comp_out_p_PAD comp_out_n_PAD}]

# Reset signal timing
set_input_delay -clock clk -max 1.0 [get_ports reset_b_PAD]
set_input_delay -clock clk -min 0.2 [get_ports reset_b_PAD]

# Clock uncertainty and margins
set_clock_uncertainty 0.5 [all_clocks]

# Load constraints for output ports (typical bondpad loading)
set_load 0.1 [all_outputs]

# Drive strength for input ports
set_driving_cell -lib_cell sg13g2_buf_2 [all_inputs]

# Clock networks will be handled by CTS - no need for dont_touch commands