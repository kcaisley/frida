# Protect critical buffer instances from removal
puts "Protecting sampdriver, clkgate, and capdriver instances from buffer removal..."

# Protect sampdriver instances (sampdriver_p and sampdriver_n)
puts "Looking for sampdriver instances..."
set sampdriver_instances [get_cells -quiet -filter "full_name =~ sampdriver_*"]
foreach inst $sampdriver_instances {
    puts "Protecting sampdriver instance: $inst"
    set_dont_touch $inst
}

# Protect internal cells within sampdriver (like sampdriver_n/clk_buf.buf_cell)
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

# Protect internal cells within clkgate (both /_ and .clkgate_cell patterns)
set clkgate_internal [get_cells -quiet -filter "full_name =~ clkgate/* || full_name =~ clkgate_*.clkgate_cell"]
foreach inst $clkgate_internal {
    puts "Protecting clkgate internal cell: $inst"
    set_dont_touch $inst
}

# Also protect all sg13g2_lgcp_1 cells specifically
set lgcp_cells [get_cells -quiet -filter "ref_name == sg13g2_lgcp_1"]
foreach inst $lgcp_cells {
    puts "Protecting sg13g2_lgcp_1 clock gate: $inst"
    set_dont_touch $inst
}

# Protect capdriver instances (capdriver_p_main, capdriver_n_main, etc.)
puts "Looking for capdriver instances..."
set capdriver_instances [get_cells -quiet -filter "full_name =~ capdriver_*"]
foreach inst $capdriver_instances {
    puts "Protecting capdriver instance: $inst"
    set_dont_touch $inst
}

# Protect internal cells within capdriver
set capdriver_internal [get_cells -quiet -filter "full_name =~ capdriver_*/*"]
foreach inst $capdriver_internal {
    puts "Protecting capdriver internal cell: $inst"
    set_dont_touch $inst
}

# Report what's protected
puts "Reporting all dont_touch instances:"
report_dont_touch