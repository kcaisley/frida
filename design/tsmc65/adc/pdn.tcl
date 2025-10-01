# Example: tools/OpenROAD/src/ppl/test/sky130hd/sky130hd.pdn.tcl
# N add_global_connection, 1 global_connect, 1 define_pdn_grid, N add_pdn_stripe, N add_pdn_connect
# for each macro then: 1 define_pdn_grid, 1 add_pdn_connect

# Example: tools/OpenROAD/src/pdn/test/asap7_M1_M3_followpins_staggered.tcl
# after read_lef , read_def:
# add_global_connection, set_voltage_domain, define_pdn_grid, add_pdn_stripe, add_pdn_connect
# only then run pdngen

add_global_connection -net vdd_d -pin_pattern VDD -power
add_global_connection -net vss_d -pin_pattern VSS -ground

add_global_connection -net vdd_dac -inst_pattern {.*capdriver.*} -pin_pattern VDD -power
add_global_connection -net vss_dac -inst_pattern {.*capdriver.*} -pin_pattern VSS -ground

add_global_connection -net vdd_a -pin_pattern vdd_a -power
add_global_connection -net vss_a -pin_pattern vss_a -ground


# Set voltage domains
# TEMP_ANALOG region created with the create_voltage_domain command
set_voltage_domain -name DIGITAL -power vdd_d -ground VSS
set_voltage_domain -region ANALOG -power VIN -ground VSS

# only 1 time
global_connect







# # Map logical power nets to each voltage domain (PDN command)

# # Digital domain: Main logic, most standard cells
# set_voltage_domain -name DIGITAL -power vdd_d -ground vss_d

# # DAC domains: Capacitor drivers requiring clean power (top and bottom)
# set_voltage_domain -name DAC_BOTTOM -power vdd_dac -ground vss_dac
# set_voltage_domain -name DAC_TOP -power vdd_dac -ground vss_dac

# # Analog domain: Custom analog macros
# set_voltage_domain -name ANALOG -power vdd_a -ground vss_a



# # Create separate grids using different metal layers to prevent shorts
# # Key strategy: Each domain uses different layer stack

# # ================================================================
# # DIGITAL DOMAIN GRID (M1, M4, M5)
# # ================================================================
# puts "Creating Digital domain PDN grid (M1, M4, M5)..."

# define_pdn_grid -name digital_grid -voltage_domains {DIGITAL}

# # M1 followpins: Standard cell power rails
# # Width 0.17μm is typical for TSMC65 M1 rails
# add_pdn_stripe -grid digital_grid -layer M1 -width 0.17 -followpins

# # M4 vertical stripes: Primary distribution
# # 0.48μm width, 55μm pitch provides good current capacity
# add_pdn_stripe -grid digital_grid -layer M4 -width 0.48 -pitch 55.0 -offset 2.5

# # M5 horizontal stripes: Secondary distribution
# # 25μm pitch for good power integrity
# add_pdn_stripe -grid digital_grid -layer M5 -width 0.48 -pitch 25.0 -offset 12.5

# # Digital domain via connections
# add_pdn_connect -grid digital_grid -layers {M1 M4}
# add_pdn_connect -grid digital_grid -layers {M4 M5}

# # ================================================================
# # DAC DOMAIN GRID (M1, M2, M3)
# # ================================================================
# puts "Creating DAC domain PDN grid (M1, M2, M3)..."

# define_pdn_grid -name dac_grid -voltage_domains {DAC_BOTTOM DAC_TOP}

# # M1 followpins: Standard cell power rails for capdriver cells
# add_pdn_stripe -grid dac_grid -layer M1 -width 0.17 -followpins

# # M2 vertical stripes: DAC power distribution
# # Tighter pitch (40μm) for shorter capdriver rows
# add_pdn_stripe -grid dac_grid -layer M2 -width 0.48 -pitch 40.0 -offset 20.0

# # M3 horizontal stripes: DAC power distribution
# # 30μm pitch for good DAC current delivery
# add_pdn_stripe -grid dac_grid -layer M3 -width 0.48 -pitch 30.0 -offset 15.0

# # DAC domain via connections
# add_pdn_connect -grid dac_grid -layers {M1 M2}
# add_pdn_connect -grid dac_grid -layers {M2 M3}

# # ================================================================
# # ANALOG DOMAIN GRID (M6, M7) - Macro Level Only
# # ================================================================
# puts "Creating Analog domain PDN grid (M6, M7)..."

# define_pdn_grid -name analog_grid -voltage_domains {ANALOG}

# # M6 vertical stripes: High-level analog power
# # Used for macro-to-macro power connections, wider spacing
# add_pdn_stripe -grid analog_grid -layer M6 -width 0.48 -pitch 30.0 -offset 15.0

# # M7 horizontal stripes: Top-level analog distribution
# # Minimal routing, just macro power supply
# add_pdn_stripe -grid analog_grid -layer M7 -width 0.48 -pitch 20.0 -offset 10.0

# # Analog domain via connections
# add_pdn_connect -grid analog_grid -layers {M6 M7}

# puts "pdngen should and only should run after this..."






# # Basic Power Distribution Network for FRIDA ADC
# # Single domain approach for initial implementation

# ####################################
# # Global connections
# ####################################
# # Standard cell power connections - all use vdd_d/vss_d for now
# add_global_connection -net {vdd_d} -pin_pattern {^VDD$} -power
# add_global_connection -net {vss_d} -pin_pattern {^VSS$} -ground

# # Module-level power connections (for macros with explicit power pins)
# add_global_connection -net {vdd_d} -inst_pattern {.*} -pin_pattern {^vdd_d$} -power
# add_global_connection -net {vss_d} -inst_pattern {.*} -pin_pattern {^vss_d$} -ground

# # Analog domain connections
# add_global_connection -net {vdd_a} -inst_pattern {.*} -pin_pattern {^vdd_a$} -power
# add_global_connection -net {vss_a} -inst_pattern {.*} -pin_pattern {^vss_a$} -ground

# # DAC domain connections
# add_global_connection -net {vdd_dac} -inst_pattern {.*} -pin_pattern {^vdd_dac$} -power
# add_global_connection -net {vss_dac} -inst_pattern {.*} -pin_pattern {^vss_dac$} -ground

# global_connect

# ####################################
# # Single voltage domain
# ####################################
# set_voltage_domain -name {Core} -power {vdd_d} -ground {vss_d}

# ####################################
# # Basic PDN grid
# ####################################
# # Core domain grid (all standard cells)
# define_pdn_grid -name {core_grid} -voltage_domains {Core}

# # Add Metal1 followpins for standard cells
# add_pdn_stripe -grid {core_grid} -layer {Metal1} -width {0.17} -followpins

# # Core domain stripes (Metal4 vertical, Metal3 horizontal)
# add_pdn_stripe -grid {core_grid} -layer {Metal4} -width {0.48} -pitch {40.0} -offset {20.0}
# add_pdn_stripe -grid {core_grid} -layer {Metal3} -width {0.48} -pitch {30.0} -offset {15.0}

# # Core domain connections
# add_pdn_connect -grid {core_grid} -layers {Metal1 Metal3}
# add_pdn_connect -grid {core_grid} -layers {Metal3 Metal4}




# # from online example: https://github.com/The-OpenROAD-Project/OpenROAD/issues/2183

# # Read odb file
# read_db design_before_pdn.odb

# # Add global connections
# add_global_connection -net VDD -inst_pattern {temp_analog_1.*} -pin_pattern VPWR -power
# add_global_connection -net VDD -inst_pattern {temp_analog_1.*} -pin_pattern VPB
# add_global_connection -net VIN -inst_pattern {temp_analog_0.*} -pin_pattern VPWR -power
# add_global_connection -net VIN -inst_pattern {temp_analog_0.*} -pin_pattern VPB
# add_global_connection -net VSS -inst_pattern {.*} -pin_pattern VGND -ground
# add_global_connection -net VSS -inst_pattern {.*} -pin_pattern VNB

# # Set voltage domains
# # TEMP_ANALOG region created with the create_voltage_domain command
# set_voltage_domain -name CORE -power VDD -ground VSS
# set_voltage_domain -region TEMP_ANALOG -power VIN -ground VSS

# # Standard cell grids
# define_pdn_grid -name stdcell -pins met5 -starts_with POWER -voltage_domains CORE

# add_pdn_stripe -grid stdcell -layer met1 -width 0.49 -pitch 6.66 -offset 0 -extend_to_core_ring -followpins
# add_pdn_ring -grid stdcell -layer {met4 met5} -widths {5.0 5.0} -spacings {2.0 2.0} -core_offsets {2.0 2.0}
# add_pdn_stripe -grid stdcell -layer met4 -width 1.2 -pitch 56.0 -offset 2 -extend_to_core_ring
# add_pdn_stripe -grid stdcell -layer met5 -width 1.6 -pitch 56.0 -offset 2 -extend_to_core_ring

# add_pdn_connect -grid stdcell -layers {met4 met5}
# add_pdn_connect -grid stdcell -layers {met1 met4}

# define_pdn_grid -name stdcell_analog -pins met4 -starts_with POWER -voltage_domains TEMP_ANALOG

# add_pdn_stripe -grid stdcell_analog -layer met1 -width 0.49 -pitch 6.66 -offset 0 -extend_to_core_ring -followpins
# add_pdn_ring -grid stdcell_analog -layer {met4 met3} -widths {5.0 5.0} -spacings {2.0 2.0} -core_offsets {2.0 2.0}
# add_pdn_stripe -grid stdcell_analog -layer met4 -width 1.2 -pitch 56.0 -offset 2 -extend_to_core_ring

# add_pdn_connect -grid stdcell_analog -layers {met4 met3}
# add_pdn_connect -grid stdcell_analog -layers {met1 met4}
# add_pdn_connect -grid stdcell_analog -layers {met4 met5}

# # Run pdngen
# pdngen

# # Save resulting design
# write_db design_after_pdn.odb