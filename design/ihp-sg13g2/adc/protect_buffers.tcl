# Protect critical buffer instances from removal
# This script should be sourced before remove_buffers is called

# Protect sampdriver instances and their internal buffers
set sampdriver_instances [get_cells -filter "ref_name == sampdriver"]
foreach inst $sampdriver_instances {
    puts "Protecting sampdriver instance: $inst"
    set_dont_touch $inst

    # Also protect the internal buffer cells within sampdriver
    set internal_buffers [get_cells -of_objects $inst -filter "ref_name =~ sg13g2_buf_* || ref_name =~ sg13g2_inv_*"]
    foreach buf $internal_buffers {
        puts "Protecting internal buffer: $buf"
        set_dont_touch $buf
    }
}

# Protect clkgate instances and their internal clock gate cells
set clkgate_instances [get_cells -filter "ref_name == clkgate"]
foreach inst $clkgate_instances {
    puts "Protecting clkgate instance: $inst"
    set_dont_touch $inst

    # Also protect internal clock gate cells
    set internal_gates [get_cells -of_objects $inst -filter "ref_name =~ sg13g2_lgcp_* || ref_name =~ sg13g2_buf_*"]
    foreach gate $internal_gates {
        puts "Protecting internal clock gate: $gate"
        set_dont_touch $gate
    }
}

# Protect capdriver instances and their internal buffers/logic
set capdriver_instances [get_cells -filter "ref_name == capdriver"]
foreach inst $capdriver_instances {
    puts "Protecting capdriver instance: $inst"
    set_dont_touch $inst

    # Protect internal buffer/logic cells
    set internal_cells [get_cells -of_objects $inst -filter "ref_name =~ sg13g2_buf_* || ref_name =~ sg13g2_inv_* || ref_name =~ sg13g2_xor_*"]
    foreach cell $internal_cells {
        puts "Protecting internal capdriver cell: $cell"
        set_dont_touch $cell
    }
}

puts "Buffer protection completed"