export DESIGN_NAME            = adc
export TOP_DESIGN_NICKNAME    = frida
export DESIGN_NICKNAME        = ${TOP_DESIGN_NICKNAME}_${DESIGN_NAME}
export PLATFORM               = tsmc65

# -----------------------------------------------------
#  Yosys (Synthesis)
#  ----------------------------------------------------

# All files, including those which are just wrappers for analog macros should be included here
# For example, in flow/designs/sky130hd/chameleon/config.mk, VERILOG_FILES includes those labeled with the convenience variable of VERILOG_FILES_BLACKBOX
export VERILOG_FILES = $(DESIGN_HOME)/$(PLATFORM)/${TOP_DESIGN_NICKNAME}/*.v \
                       $(PLATFORM_DIR)/cells_dffe.v

# Constraints
export SDC_FILE      = $(DESIGN_HOME)/$(PLATFORM)/$(TOP_DESIGN_NICKNAME)/${DESIGN_NAME}/constraint.sdc

# Analog macro LEFs for ADC sub-block
export ADDITIONAL_LEFS += $(PLATFORM_DIR)/lef/caparray.lef \
                         $(PLATFORM_DIR)/lef/comp.lef \
                         $(PLATFORM_DIR)/lef/sampswitch.lef

# Analog macro GDS files for ADC sub-block
export ADDITIONAL_GDS += $(PLATFORM_DIR)/gds/caparray.gds \
                        $(PLATFORM_DIR)/gds/comp.gds \
                        $(PLATFORM_DIR)/gds/sampswitch.gds

# Analog macro library files for ADC sub-block
# Hardened macro library files listed here. The library information is immutable and used throughout all stages. Not stored in the .odb file.
export ADDITIONAL_LIBS += $(PLATFORM_DIR)/lib/caparray.lib \
                         $(PLATFORM_DIR)/lib/comp.lib \
                         $(PLATFORM_DIR)/lib/sampswitch.lib

# Disable hierarchical synthesis to flatten OPENROAD helper modules
export SYNTH_HIERARCHICAL = 0

# Keep specific design modules from being flattened (exclude OPENROAD_* modules)
export SYNTH_KEEP_MODULES = clkgate salogic capdriver caparray sampdriver sampswitch comp

#--------------------------------------------------------
# Floorplan
# -------------------------------------------------------

# These settings are mutually exclusive with CORE_UTILIZATION, CORE_MARGIN, CORE_ASPECT_RATIO
export DIE_AREA = 0 0 60 60
export CORE_AREA = 0 0 60 60

# Macro placement configuration for analog blocks  
export MACRO_PLACEMENT = $(DESIGN_HOME)/$(PLATFORM)/frida/adc/macro_placement.cfg

# MACRO_PLACE_HALO settings for mixed-signal layout
export MACRO_PLACE_HALO = 1 1
# export MACRO_PLACE_CHANNEL = 4 4

export PDN_TCL = $(DESIGN_HOME)/$(PLATFORM)/frida/adc/pdn.tcl

#--------------------------------------------------------
# Placement
# -------------------------------------------------------

export IO_PLACER_H = M3  # Horizontal I/O pins on M3
export IO_PLACER_V = M2  # Vertical I/O pins on M2

export IO_CONSTRAINTS = $(DESIGN_HOME)/$(PLATFORM)/frida/adc/io.tcl

# Pin placement settings, since my tracks are 200nm tall
export PLACE_PINS_ARGS = -min_distance 5 -min_distance_in_tracks

# Standard cell placement density
export PLACE_DENSITY = 0.6

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

# Routing layer constraints
# Based on TSMC65LP metal stack from tcbn65lp_9lmT2.lef
export MIN_ROUTING_LAYER = M1
export MAX_ROUTING_LAYER = M4

# Skip antenna repair due to crash in mixed-signal design
# export SKIP_ANTENNA_REPAIR = 1
# export SKIP_DETAILED_ROUTE = 1
# Enable detailed routing debug for caparray pin coverage issues
export DETAILED_ROUTE_ARGS = -droute_end_iter 1 -verbose 2

#--------------------------------------------------------
# Finishing
# -------------------------------------------------------

export USE_FILL = 1