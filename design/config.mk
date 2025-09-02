export DESIGN_NAME = adc
export PLATFORM = tsmc65

# -----------------------------------------------------
#  Yosys (Synthesis)
#  ----------------------------------------------------

export VERILOG_FILES = $(DESIGN_HOME)/src/frida/adc.v \
                       $(DESIGN_HOME)/src/frida/clkgate.v \
                       $(DESIGN_HOME)/src/frida/salogic.v \
                       $(DESIGN_HOME)/src/frida/capdriver.v \
                       $(DESIGN_HOME)/src/frida/sampdriver.v \
                       $(DESIGN_HOME)/src/frida/comp.v \
                       $(DESIGN_HOME)/src/frida/sampswitch.v \
                       $(DESIGN_HOME)/src/frida/caparray.v

# Remove SYNTH_BLACKBOXES - using (* blackbox *) attribute in .v files instead

# Hardened analog macro files
export ADDITIONAL_LEFS = $(PLATFORM_DIR)/lef/caparray.lef \
                        $(PLATFORM_DIR)/lef/comp.lef \
                        $(PLATFORM_DIR)/lef/sampswitch.lef

export ADDITIONAL_GDS = $(PLATFORM_DIR)/gds/caparray.gds \
                       $(PLATFORM_DIR)/gds/comp.gds \
                       $(PLATFORM_DIR)/gds/sampswitch.gds

# Note: No additional .lib files needed - macros are pure analog blocks

# If is provided, I think I don't need to set variables like ABC_CLOCK_PERIOD_IN_PS or CLOCK_PERIOD myself
export SDC_FILE      = $(DESIGN_HOME)/$(PLATFORM)/frida/constraint.sdc

export SYNTH_HIERARCHICAL = 1

#--------------------------------------------------------
# Floorplan
# -------------------------------------------------------

# Custom I/O placement configuration
# M1: DIRECTION HORIZONTAL, M2: DIRECTION VERTICAL, M3: DIRECTION HORIZONTAL
# Place P-side pins on left (M3), N-side pins on right (M3), others on bottom (M2)

# # Default I/O placer metal layer assignments
export IO_PLACER_H = M3  # Horizontal I/O pins on M3 (horizontal preferred direction)
export IO_PLACER_V = M2  # Vertical I/O pins on M2 (vertical preferred direction)

# Custom I/O placement constraints
export IO_CONSTRAINTS = $(DESIGN_HOME)/$(PLATFORM)/frida/io.tcl

# Since my trakcs are 200nm sizes, 
export PLACE_PINS_ARGS = -min_distance 5 -min_distance_in_tracks

#--------------------------------------------------------
# Placement
# -------------------------------------------------------

# Design parameters - mixed-signal layout constraints

# These settings are mutually exclusion with the ones below
export DIE_AREA = 0 0 60 55
export CORE_AREA = 0 0 60 55

# export CORE_UTILIZATION = 40
# export CORE_MARGIN = 1
# export CORE_ASPECT_RATIO = 1.4 # H/W, requires CORE_UTILIZATION (taller than wide for more left/right pin space)
export PLACE_DENSITY = 0.6  # Higher density for more compact placement

# Macro placement configuration for analog blocks
export MACRO_PLACEMENT = $(DESIGN_HOME)/$(PLATFORM)/frida/macro_placement.cfg

# Alternative method, which isn't working at the moment.
# export MACRO_PLACEMENT_TCL = $(DESIGN_HOME)/$(PLATFORM)/frida/macro_placement.tcl

# MACRO_PLACE_HALO settings for mixed-signal layout
export MACRO_PLACE_HALO = 1 1
export MACRO_PLACE_CHANNEL = 4 4

export PDN_TCL = $(DESIGN_HOME)/$(PLATFORM)/frida/pdn.tcl

#--------------------------------------------------------
# Clock Tree Synthsis (CTS)
# -------------------------------------------------------

export SKIP_GATE_CLONING = 1

# Minimal buffer list for CTS - use smallest available buffers
# BUFFD0LVT is the smallest drive strength, then BUFFD1LVT, BUFFD2LVT
export CTS_BUF_LIST = BUFFD0LVT BUFFD1LVT BUFFD2LVT

export CTS_BUF_DISTANCE = 80
export CTS_ARGS = -dont_use_dummy_load -sink_buffer_max_cap_derate 0.1 -delay_buffer_derate 0.3

#--------------------------------------------------------
# Routing
# -------------------------------------------------------

# Routing layer constraints
# Based on TSMC65LP metal stack from tcbn65lp_9lmT2.lef
export MIN_ROUTING_LAYER = M1
export MAX_ROUTING_LAYER = M5

# Enable timing-driven placement for better compactness and connectivity
# RC values configured in platforms/tsmc65/setRC.tcl from TSMC65LP specifications
export PLACE_TIMING_DRIVEN = 1

#--------------------------------------------------------
# Finishing
# -------------------------------------------------------

export USE_FILL = 1