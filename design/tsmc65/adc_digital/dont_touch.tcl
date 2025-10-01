# Protect critical buffer instances from removal during placement optimization
# These instances are being removed during placement because timing and loading
# information of the capacitor array connections isn't present in the synthesis model
puts "Protecting sampdriver, clkgate, and capdriver instances from buffer removal..."

# Protect sampdriver instances (sampdriver_p and sampdriver_n)
puts "Looking for sampdriver instances..."
set sampdriver_instances [get_cells -quiet -filter "full_name =~ sampdriver_*"]
foreach inst $sampdriver_instances {
    puts "Protecting sampdriver instance: $inst"
    set_dont_touch $inst
}

# Protect internal buffer cells within sampdriver (like sampdriver_n/clk_buf.buf_cell)
# These BUFFD2LVT cells are critical for driving the capacitor array sampling switches
set sampdriver_internal [get_cells -quiet -filter "full_name =~ sampdriver_*/*"]
foreach inst $sampdriver_internal {
    puts "Protecting sampdriver internal cell: $inst"
    set_dont_touch $inst
}

# Protect clkgate instances
puts "Looking for clkgate instances..."
set clkgate_instances [get_cells -quiet -filter "full_name =~ clkgate"]
foreach inst $clkgate_instances {
    puts "Protecting clkgate instance: $inst"
    set_dont_touch $inst
}

# Protect internal clock gate cells within clkgate (clkgate_*.clkgate_cell pattern)
# These CKLNQD1LVT cells are critical for proper clock gating functionality
set clkgate_internal [get_cells -quiet -filter "full_name =~ clkgate_*.clkgate_cell"]
foreach inst $clkgate_internal {
    puts "Protecting clkgate internal cell: $inst"
    set_dont_touch $inst
}

# Also protect all CKLNQD1LVT cells specifically (TSMC65 clock gate cells)
set clkgate_cells [get_cells -quiet -filter "ref_name == CKLNQD1LVT"]
foreach inst $clkgate_cells {
    puts "Protecting CKLNQD1LVT clock gate: $inst"
    set_dont_touch $inst
}

# Actually it does look like there are extra inverters here which should be eliminated!

# # Protect capdriver instances (capdriver_p_main, capdriver_n_main, etc.)
# puts "Looking for capdriver instances..."
# set capdriver_instances [get_cells -quiet -filter "full_name =~ capdriver_*"]
# foreach inst $capdriver_instances {
#     puts "Protecting capdriver instance: $inst"
#     set_dont_touch $inst
# }

# # Protect internal XOR gate cells within capdriver
# # These XOR2D1LVT cells implement the critical DAC inversion logic
# set capdriver_xor_internal [get_cells -quiet -filter "full_name =~ capdriver_*/xor_gates*xor_gate.xor_cell"]
# foreach inst $capdriver_xor_internal {
#     puts "Protecting capdriver XOR gate: $inst"
#     set_dont_touch $inst
# }

# # Protect internal buffer cells within capdriver (drive strength critical for capacitors)
# set capdriver_buf_internal [get_cells -quiet -filter "full_name =~ capdriver_*/_*"]
# foreach inst $capdriver_buf_internal {
#     puts "Protecting capdriver internal buffer: $inst"
#     set_dont_touch $inst
# }

# Report what's protected
puts "Reporting all dont_touch instances:"
report_dont_touch