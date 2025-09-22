# Multi-Domain Power Distribution Network for FRIDA ADC
# Supports analog, digital, and DAC power domains
#
# This PDN script creates separate power grids for three voltage domains:
# - vdd_d/vss_d: Digital domain (standard cells, logic)
# - vdd_a/vss_a: Analog domain (sampswitch, comp, caparray macros)
# - vdd_dac/vss_dac: DAC domain (capdriver standard cells)

####################################
# Global connections
####################################
# These commands map logical power net names to physical pins on instances.
# They tell OpenROAD which nets should connect to which power/ground pins.

# Standard cell power connections
# Capdriver standard cells use vdd_dac domain
# Maps the vdd_dac net to VDD pins of all capdriver instances
add_global_connection -net {vdd_dac} -inst_pattern {.*capdriver.*} -pin_pattern {^VDD$} -power
# Maps the vss_dac net to VSS pins of all capdriver instances
add_global_connection -net {vss_dac} -inst_pattern {.*capdriver.*} -pin_pattern {^VSS$} -ground

# All other standard cells use vdd_d domain
# Default mapping: vdd_d net connects to all VDD pins not caught by above rules
add_global_connection -net {vdd_d} -pin_pattern {^VDD$} -power
# Default mapping: vss_d net connects to all VSS pins not caught by above rules
add_global_connection -net {vss_d} -pin_pattern {^VSS$} -ground

# Module-level power connections (for macros with explicit power pins)
# These handle custom macros that have explicitly named power pins rather than generic VDD/VSS
# Digital domain connections for modules with explicit vdd_d/vss_d pins
add_global_connection -net {vdd_d} -inst_pattern {.*} -pin_pattern {^vdd_d$} -power
add_global_connection -net {vss_d} -inst_pattern {.*} -pin_pattern {^vss_d$} -ground

# Analog domain connections for modules with explicit vdd_a/vss_a pins
# Used by sampswitch, comp, and caparray macros
add_global_connection -net {vdd_a} -inst_pattern {.*} -pin_pattern {^vdd_a$} -power
add_global_connection -net {vss_a} -inst_pattern {.*} -pin_pattern {^vss_a$} -ground

# DAC domain connections for modules with explicit vdd_dac/vss_dac pins
add_global_connection -net {vdd_dac} -inst_pattern {.*} -pin_pattern {^vdd_dac$} -power
add_global_connection -net {vss_dac} -inst_pattern {.*} -pin_pattern {^vss_dac$} -ground

# Apply all the global connection rules defined above
global_connect

####################################
# Multiple voltage domains
####################################
# Define logical voltage domains for power planning.
# Each domain groups instances that share the same power supply.

# Core domain: Digital logic, most standard cells
set_voltage_domain -name {Core} -power {vdd_d} -ground {vss_d}
# Analog domain: Custom analog macros (sampswitch, comp, caparray)
set_voltage_domain -name {ANALOG} -power {vdd_a} -ground {vss_a}
# DAC domain: Capacitor drivers and related circuits
set_voltage_domain -name {DAC} -power {vdd_dac} -ground {vss_dac}

####################################
# Multi-domain PDN grids
####################################
# Create separate physical power grids for each voltage domain.
# Each grid defines the metal layers, widths, and routing used to distribute power.

# Digital domain grid (most standard cells)
# Associate this grid with the Core voltage domain defined above
define_pdn_grid -name {digital_grid} -voltage_domains {Core}

# Add M1 followpins for digital standard cells
# This creates M1 power rails that follow the standard cell pin layout
# Width 0.17um matches typical M1 power rail width in TSMC65
add_pdn_stripe -grid {digital_grid} -layer {M1} -width {0.17} -followpins

# Digital domain stripes (M4 vertical, M3 horizontal)
# M4 vertical stripes: 0.48um wide, spaced every 55um, offset 2.5um from edge
add_pdn_stripe -grid {digital_grid} -layer {M4} -width {0.48} -pitch {55.0} -offset {2.5}
# M3 horizontal stripes: 0.48um wide, spaced every 25um, offset 12.5um from edge
add_pdn_stripe -grid {digital_grid} -layer {M3} -width {0.48} -pitch {25.0} -offset {12.5}

# Digital domain connections - create vias between layers
# Connect M1 power rails to M3 horizontal stripes
add_pdn_connect -grid {digital_grid} -layers {M1 M3}
# Connect M3 horizontal stripes to M4 vertical stripes
add_pdn_connect -grid {digital_grid} -layers {M3 M4}

# DAC domain grid (capdriver standard cells)
# Separate grid for capacitor driver circuits that need clean DAC power
define_pdn_grid -name {dac_grid} -voltage_domains {DAC}

# Add M1 followpins for DAC standard cells
# Same as digital grid - M1 rails follow standard cell power pins
add_pdn_stripe -grid {dac_grid} -layer {M1} -width {0.17} -followpins

# DAC domain stripes (same layers as digital, but separate nets due to physical separation)
# Different pitch/offset to avoid interference with digital grid
# M4 vertical stripes: 0.48um wide, spaced every 40um, offset 20um from edge
add_pdn_stripe -grid {dac_grid} -layer {M4} -width {0.48} -pitch {40.0} -offset {20.0}
# M3 horizontal stripes: 0.48um wide, spaced every 30um, offset 15um from edge
add_pdn_stripe -grid {dac_grid} -layer {M3} -width {0.48} -pitch {30.0} -offset {15.0}

# DAC domain connections - create vias between layers
# Connect M1 power rails to M3 horizontal stripes
add_pdn_connect -grid {dac_grid} -layers {M1 M3}
# Connect M3 horizontal stripes to M4 vertical stripes
add_pdn_connect -grid {dac_grid} -layers {M3 M4}

# Analog domain grid (analog macros only - no standard cells)
define_pdn_grid -name {analog_grid} -voltage_domains {ANALOG}

# Analog domain stripes (M6 vertical, M5 horizontal for isolation from digital/DAC)
add_pdn_stripe -grid {analog_grid} -layer {M6} -width {0.48} -pitch {30.0} -offset {15.0}
add_pdn_stripe -grid {analog_grid} -layer {M5} -width {0.48} -pitch {20.0} -offset {10.0}

# Analog domain connections
add_pdn_connect -grid {analog_grid} -layers {M5 M6}