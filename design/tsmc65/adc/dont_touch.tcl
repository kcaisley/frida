# Dont Touch and Pre-Placement Script for FRIDA ADC
# This script runs before global placement and handles:
# 1. Protecting critical buffer instances from removal
# 2. Placing XOR gates in capdriver instances

puts "Running dont_touch and pre-placement script"

# TODO: Add dont_touch commands here if there are specific instances to protect
# Example: set_dont_touch [get_cells {buffer_inst_name}]

# Source the XOR gate placement script
puts "Sourcing XOR gate placement script"
source [file join [file dirname [info script]] place_xor_gates.tcl]

puts "Completed dont_touch and pre-placement operations"