export DESIGN_NAME            = adc
export TOP_DESIGN_NICKNAME    = frida
export DESIGN_NICKNAME        = ${TOP_DESIGN_NICKNAME}_${DESIGN_NAME}
export PLATFORM               = tsmc65

# -----------------------------------------------------
#  Yosys (Synthesis)
#  ----------------------------------------------------

export VERILOG_FILES = $(DESIGN_HOME)/src/frida/adc.v \
                       $(DESIGN_HOME)/src/frida/caparray.v \
                       $(DESIGN_HOME)/src/frida/capdriver.v \
                       $(DESIGN_HOME)/src/frida/clkgate.v \
                       $(DESIGN_HOME)/src/frida/comp.v \
                       $(DESIGN_HOME)/src/frida/salogic.v \
                       $(DESIGN_HOME)/src/frida/sampdriver.v \
                       $(DESIGN_HOME)/src/frida/sampswitch.v \
                       $(DESIGN_HOME)/src/frida/cells_tsmc65.v

# Timing constraints
export SDC_FILE      = $(DESIGN_HOME)/$(PLATFORM)/frida/adc/constraint.sdc

# Disable hierarchical synthesis to flatten OPENROAD helper modules
export SYNTH_HIERARCHICAL = 0

# Allow all cells
export DONT_USE_CELLS =

# Keep specific design modules from being flattened (exclude OPENROAD_* modules)
export SYNTH_KEEP_MODULES = clkgate salogic capdriver caparray sampdriver sampswitch comp

#--------------------------------------------------------
# Floorplan
# -------------------------------------------------------

# Design area: 60x60 micrometers for TSMC65 to accommodate macros

# export CREATE_REGIONS = $(DESIGN_HOME)/$(PLATFORM)/frida/adc/create_regions.tcl

export DIE_AREA = 0 0 60 59.4
export CORE_AREA = 0 0 60 59.4

export MACRO_PLACEMENT_TCL = $(DESIGN_HOME)/$(PLATFORM)/frida/adc/macro.tcl

export MACRO_PLACE_HALO = 1 1

# export PDN_TCL = $(DESIGN_HOME)/$(PLATFORM)/frida/adc/pdn.tcl
export PDN_TCL = \

#--------------------------------------------------------
# Placement
# -------------------------------------------------------

# FRIDA project specific scripts for placement (triggered from global_place.tcl)
export DONT_TOUCH = $(DESIGN_HOME)/$(PLATFORM)/frida/adc/dont_touch.tcl
# export MANUAL_PLACE = $(DESIGN_HOME)/$(PLATFORM)/frida/adc/manual_place.tcl

export IO_PLACER_H = M3  # Horizontal I/O pins on M3
export IO_PLACER_V = M2  # Vertical I/O pins on M2

# NOTE: WAIT WOULD THIS MAYBE BE THE FLOORPLANNING SPACING FOR REGIONS?
export IO_CONSTRAINTS = $(DESIGN_HOME)/$(PLATFORM)/frida/adc/io.tcl
export PLACE_PINS_ARGS = -min_distance 5 -min_distance_in_tracks

# Standard cell placement density
export PLACE_DENSITY = 0.65

#--------------------------------------------------------
# Clock Tree Synthsis (CTS)
# -------------------------------------------------------

# export SKIP_GATE_CLONING = 1

# Minimal buffer list for CTS - use smallest available buffers
# export CTS_BUF_LIST = BUFFD0LVT BUFFD1LVT BUFFD2LVT

# export CTS_BUF_DISTANCE = 80
# export CTS_ARGS = -dont_use_dummy_load -sink_buffer_max_cap_derate 0.1 -delay_buffer_derate 0.3

#--------------------------------------------------------
# Routing
# -------------------------------------------------------

# Based on TSMC65LP metal stack from tcbn65lp_9lmT2.lef
export MIN_ROUTING_LAYER = M1
export MAX_ROUTING_LAYER = M6

# Skip antenna repair due to crash in mixed-signal design
# export SKIP_ANTENNA_REPAIR = 1
# export SKIP_DETAILED_ROUTE = 1
# Enable detailed routing debug for caparray pin coverage issues
export DETAILED_ROUTE_ARGS = -droute_end_iter 1 -verbose 2

#--------------------------------------------------------
# Finishing
# -------------------------------------------------------

# Only disables metal fill; FILL_CELLS in routing step still adds FEOL decap fill cells
export USE_FILL = 0

#--------------------------------------------------------
# Power Analysis
# -------------------------------------------------------

# Power analysis settings
export PWR_NETS_VOLTAGES = "vdd_d 1.2 vdd_a 1.2 vdd_dac 1.2"
export GND_NETS_VOLTAGES = "vss_d 0.0 vss_a 0.0 vss_dac 0.0"

# IR drop analysis layer (required for final report)
export IR_DROP_LAYER = M1