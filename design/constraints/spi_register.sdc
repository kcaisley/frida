create_clock -name spi_sclk -period 100.000 [get_ports spi_sclk]

set_input_delay 2.000 -clock spi_sclk [get_ports {rst_b spi_cs_b spi_sdi}]
set_output_delay 2.000 -clock spi_sclk [get_ports {spi_sdo spi_bits[*]}]

set_false_path -from [get_ports rst_b]
