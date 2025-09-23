# Multi-Domain Power Distribution Network for FRIDA ADC (NEW APPROACH)
# Uses IFP voltage domains + layer-separated PDN grids
# Works around OpenROAD UPF limitations (Issues #5617, #7718)
#
# COMMAND OVERVIEW:
# Logical Power Domain Setup (UPF replacement):
#   1. set_voltage_domain - Associates power/ground net names with voltage domains
#   2. add_global_connection - Maps power nets to instance patterns
#   3. global_connect - Applies all the connection rules defined above
# Physical Power Delivery Implementation:
#   4. define_pdn_grid - Defines PDN grid structures for each domain
#   5. add_pdn_stripe - Creates actual power delivery stripes/geometry on metal layers
#   6. add_pdn_connect - Creates via connections between metal layers within grids
#   7. pdngen - Executes the actual PDN geometry generation
#
# IMPORTANT: Domain areas must be defined BEFORE initialize_floorplan in main flow
# This script assumes voltage domains are already created by init_floorplan.tcl
#
# Physical Layout:
# - Core area: 60x60μm (2,2 to 58,58)
# - DAC domain: Top 2 + Bottom 2 rows (~4μm each = 8μm total)
# - Digital domain: Middle rows (~44μm)
# - Analog domain: Scattered macro locations
#
# Power Domain Isolation Strategy:
# - Physical: via placement (place_capdrivers.tcl)
# - Electrical: via different metal layers per domain
# - Logical: via instance pattern matching in global connections

####################################
# STEP 1: Verify Voltage Domains Exist
####################################
# These should be created BEFORE this script runs, in init_floorplan.tcl:
#
# create_voltage_domain DAC -area {2 2 58 22.3}            # Bottom 35% (capdriver cells)
# create_voltage_domain DIGITAL -area {2 24.3 58 58}       # Top 65% (digital logic above isolation)
# create_voltage_domain ANALOG -area {8 26 50 50}          # Macro cluster area (example)
# NOTE: Isolation zone Y=22.3-24.3μm is handled by placement blockages

puts "Setting up 3-domain PDN with layer separation..."
puts "Expected voltage domains: DAC, DIGITAL, ANALOG"

####################################
# STEP 2: Associate Power Nets with Domains
####################################
# Map logical power nets to each voltage domain (PDN command)

# Digital domain: Main logic, most standard cells
set_voltage_domain -name DIGITAL -power vdd_d -ground vss_d

# DAC domain: Capacitor drivers requiring clean power
set_voltage_domain -name DAC -power vdd_dac -ground vss_dac

# Analog domain: Custom analog macros
set_voltage_domain -name ANALOG -power vdd_a -ground vss_a

####################################
# STEP 3: Global Power Connections
####################################
# Map power nets to instance types using pattern matching
# This determines which instances get which power supply

# DAC Domain Connections
# Target capdriver instances specifically for vdd_dac power
add_global_connection -net vdd_dac -inst_pattern {.*capdriver.*} -pin_pattern {^VDD$} -power
add_global_connection -net vss_dac -inst_pattern {.*capdriver.*} -pin_pattern {^VSS$} -ground

# Digital Domain Connections
# Default power for all standard cells not caught by specific patterns above
add_global_connection -net vdd_d -pin_pattern {^VDD$} -power
add_global_connection -net vss_d -pin_pattern {^VSS$} -ground

# Analog Domain Connections
# Macros with explicit analog power pins
add_global_connection -net vdd_a -pin_pattern {^vdd_a$} -power
add_global_connection -net vss_a -pin_pattern {^vss_a$} -ground

# Module-level power connections for any hierarchical blocks
add_global_connection -net vdd_d -pin_pattern {^vdd_d$} -power
add_global_connection -net vss_d -pin_pattern {^vss_d$} -ground
add_global_connection -net vdd_dac -pin_pattern {^vdd_dac$} -power
add_global_connection -net vss_dac -pin_pattern {^vss_dac$} -ground

# Apply all global connection rules
global_connect

####################################
# STEP 4: Layer-Separated PDN Grids
####################################
# Create separate grids using different metal layers to prevent shorts
# Key strategy: Each domain uses different layer stack

# ================================================================
# DIGITAL DOMAIN GRID (M1, M4, M5)
# ================================================================
puts "Creating Digital domain PDN grid (M1, M4, M5)..."

define_pdn_grid -name digital_grid -voltage_domains {DIGITAL}

# M1 followpins: Standard cell power rails
# Width 0.17μm is typical for TSMC65 M1 rails
add_pdn_stripe -grid digital_grid -layer M1 -width 0.17 -followpins

# M4 vertical stripes: Primary distribution
# 0.48μm width, 55μm pitch provides good current capacity
add_pdn_stripe -grid digital_grid -layer M4 -width 0.48 -pitch 55.0 -offset 2.5

# M5 horizontal stripes: Secondary distribution
# 25μm pitch for good power integrity
add_pdn_stripe -grid digital_grid -layer M5 -width 0.48 -pitch 25.0 -offset 12.5

# Digital domain via connections
add_pdn_connect -grid digital_grid -layers {M1 M4}
add_pdn_connect -grid digital_grid -layers {M4 M5}

# ================================================================
# DAC DOMAIN GRID (M1, M2, M3)
# ================================================================
puts "Creating DAC domain PDN grid (M1, M2, M3)..."

define_pdn_grid -name dac_grid -voltage_domains {DAC}

# M1 followpins: Standard cell power rails for capdriver cells
add_pdn_stripe -grid dac_grid -layer M1 -width 0.17 -followpins

# M2 vertical stripes: DAC power distribution
# Tighter pitch (40μm) for shorter capdriver rows
add_pdn_stripe -grid dac_grid -layer M2 -width 0.48 -pitch 40.0 -offset 20.0

# M3 horizontal stripes: DAC power distribution
# 30μm pitch for good DAC current delivery
add_pdn_stripe -grid dac_grid -layer M3 -width 0.48 -pitch 30.0 -offset 15.0

# DAC domain via connections
add_pdn_connect -grid dac_grid -layers {M1 M2}
add_pdn_connect -grid dac_grid -layers {M2 M3}

# ================================================================
# ANALOG DOMAIN GRID (M6, M7) - Macro Level Only
# ================================================================
puts "Creating Analog domain PDN grid (M6, M7)..."

define_pdn_grid -name analog_grid -voltage_domains {ANALOG}

# M6 vertical stripes: High-level analog power
# Used for macro-to-macro power connections, wider spacing
add_pdn_stripe -grid analog_grid -layer M6 -width 0.48 -pitch 30.0 -offset 15.0

# M7 horizontal stripes: Top-level analog distribution
# Minimal routing, just macro power supply
add_pdn_stripe -grid analog_grid -layer M7 -width 0.48 -pitch 20.0 -offset 10.0

# Analog domain via connections
add_pdn_connect -grid analog_grid -layers {M6 M7}

####################################
# STEP 5: Execute PDN Generation
####################################
puts "Generating multi-domain power delivery network..."

# Generate the complete PDN for all domains
pdngen

puts "✓ Multi-domain PDN generation complete"

####################################
# COORDINATION NOTES
####################################
puts "
PDN COORDINATION REQUIREMENTS:

1. VOLTAGE DOMAIN SETUP:
   • Must define voltage domains BEFORE initialize_floorplan in main flow
   • Domain areas must align with place_capdrivers.tcl isolation boundaries

2. INSTANCE PLACEMENT COORDINATION:
   • Capdriver instances must be placed in DAC domain areas (Y=2-6, Y=52-56)
   • Digital logic must be placed in DIGITAL domain area (Y=6-52)
   • Analog macros must be placed in ANALOG domain areas

3. LAYER SEPARATION VERIFICATION:
   • Digital domain: M1, M4, M5 (check for shorts)
   • DAC domain: M1, M2, M3 (check for shorts)
   • Analog domain: M6, M7 (check for shorts)
   • No cross-domain layer usage to prevent power shorts

4. POWER INTEGRITY:
   • Verify capdriver instances get vdd_dac supply
   • Verify digital logic gets vdd_d supply
   • Verify analog macros get vdd_a supply
   • Check IR drop across all domains

NEXT STEPS:
1. Update init_floorplan.tcl to create voltage domains before initialize_floorplan
2. Verify place_capdrivers.tcl places instances in correct domain areas
3. Test PDN generation for layer conflicts and power shorts
"