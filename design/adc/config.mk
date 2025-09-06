export DESIGN_NAME            = adc
export TOP_DESIGN_NICKNAME    = frida
export DESIGN_NICKNAME        = ${TOP_DESIGN_NICKNAME}_${DESIGN_NAME}
export PLATFORM               = tsmc65

# -----------------------------------------------------
#  Yosys (Synthesis)
#  ----------------------------------------------------

export VERILOG_FILES = $(DESIGN_HOME)/$(PLATFORM)/${TOP_DESIGN_NICKNAME}/*.v

# Constraints
export SDC_FILE      = $(DESIGN_HOME)/$(PLATFORM)/$(TOP_DESIGN_NICKNAME)/${DESIGN_NAME}/constraint.sdc

export SYNTH_HIERARCHICAL = 1

#--------------------------------------------------------
# Floorplan
# -------------------------------------------------------

# Custom I/O placement configuration
export IO_PLACER_H = M3  # Horizontal I/O pins on M3
export IO_PLACER_V = M2  # Vertical I/O pins on M2

# Custom I/O placement constraints
export IO_CONSTRAINTS = $(DESIGN_HOME)/$(PLATFORM)/frida/adc/io.tcl

# Pin placement settings, since my tracks are 200nm tall
export PLACE_PINS_ARGS = -min_distance 5 -min_distance_in_tracks

#--------------------------------------------------------
# Placement
# -------------------------------------------------------

# Design parameters - mixed-signal layout constraints

export PLACE_DENSITY = 0.6

# These settings are mutually exclusion with CORE_UTILIZATION, CORE_MARGIN, CORE_ASPECT_RATIO
export DIE_AREA = 0 0 60 60
export CORE_AREA = 0 0 60 60

# Macro placement configuration for analog blocks  
# export MACRO_PLACEMENT_TCL = $(DESIGN_HOME)/$(PLATFORM)/frida/adc/macro_placement.tcl
export MACRO_PLACE = $(DESIGN_HOME)/$(PLATFORM)/frida/adc/macro_placement.cfg

# MACRO_PLACE_HALO settings for mixed-signal layout
export MACRO_PLACE_HALO = 1 1
export MACRO_PLACE_CHANNEL = 4 4

export PDN_TCL = $(DESIGN_HOME)/$(PLATFORM)/frida/adc/pdn.tcl

#--------------------------------------------------------
# Clock Tree Synthsis (CTS)
# -------------------------------------------------------

export SKIP_GATE_CLONING = 1

# Minimal buffer list for CTS - use smallest available buffers
export CTS_BUF_LIST = BUFFD0LVT BUFFD1LVT BUFFD2LVT

export CTS_BUF_DISTANCE = 80
export CTS_ARGS = -dont_use_dummy_load -sink_buffer_max_cap_derate 0.1 -delay_buffer_derate 0.3

#--------------------------------------------------------
# Routing
# -------------------------------------------------------

# Routing layer constraints
# Based on TSMC65LP metal stack from tcbn65lp_9lmT2.lef
export MIN_ROUTING_LAYER = M1
export MAX_ROUTING_LAYER = M4

# Skip antenna repair due to crash in mixed-signal design
export SKIP_ANTENNA_REPAIR = 1
export SKIP_DETAILED_ROUTE = 1
# Enable detailed routing debug for caparray pin coverage issues
export DETAILED_ROUTE_ARGS = -droute_end_iter 1 -verbose 2

#--------------------------------------------------------
# Finishing
# -------------------------------------------------------

export USE_FILL = 1