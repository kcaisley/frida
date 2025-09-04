export PLATFORM               = tsmc65

export DESIGN_NAME            = adc
export DESIGN_NICKNAME        = frida_adc

# -----------------------------------------------------
#  Yosys (Synthesis)
#  ----------------------------------------------------

export VERILOG_FILES = $(DESIGN_HOME)/$(PLATFORM)/frida/adc/adc.v \
                       $(DESIGN_HOME)/$(PLATFORM)/frida/adc/clkgate.v \
                       $(DESIGN_HOME)/$(PLATFORM)/frida/adc/salogic.v \
                       $(DESIGN_HOME)/$(PLATFORM)/frida/adc/capdriver.v \
                       $(DESIGN_HOME)/$(PLATFORM)/frida/adc/sampdriver.v \
                       $(DESIGN_HOME)/$(PLATFORM)/frida/adc/comp.v \
                       $(DESIGN_HOME)/$(PLATFORM)/frida/adc/sampswitch.v \
                       $(DESIGN_HOME)/$(PLATFORM)/frida/adc/caparray.v

# Hardened analog macro files
export ADDITIONAL_LEFS = $(PLATFORM_DIR)/lef/caparray.lef \
                        $(PLATFORM_DIR)/lef/comp.lef \
                        $(PLATFORM_DIR)/lef/sampswitch.lef

export ADDITIONAL_GDS = $(PLATFORM_DIR)/gds/caparray.gds \
                       $(PLATFORM_DIR)/gds/comp.gds \
                       $(PLATFORM_DIR)/gds/sampswitch.gds

# Constraints
export SDC_FILE      = $(DESIGN_HOME)/$(PLATFORM)/frida/adc/constraint.sdc

#--------------------------------------------------------
# Floorplan
# -------------------------------------------------------

# Custom I/O placement configuration
export IO_PLACER_H = M3  # Horizontal I/O pins on M3
export IO_PLACER_V = M2  # Vertical I/O pins on M2

# Custom I/O placement constraints
export IO_CONSTRAINTS = $(DESIGN_HOME)/$(PLATFORM)/frida/adc/io.tcl

# Pin placement settings
export PLACE_PINS_ARGS = -min_distance 5 -min_distance_in_tracks

#--------------------------------------------------------
# Placement
# -------------------------------------------------------

# Design parameters - mixed-signal layout constraints
export CORE_UTILIZATION = 40
export CORE_ASPECT_RATIO = 1
export CORE_MARGIN = 2
export PLACE_DENSITY = 0.6

# Macro placement configuration for analog blocks
export MACRO_PLACEMENT = $(DESIGN_HOME)/$(PLATFORM)/frida/adc/macro_placement.cfg

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
export MIN_ROUTING_LAYER = M1
export MAX_ROUTING_LAYER = M4

# Skip antenna repair due to crash in mixed-signal design
export SKIP_ANTENNA_REPAIR = 1
export SKIP_DETAILED_ROUTE = 1
# Enable detailed routing debug for caparray pin coverage issues
export DETAILED_ROUTE_ARGS = -droute_end_iter 1 -verbose 2

# Enable timing-driven placement for better compactness and connectivity
export PLACE_TIMING_DRIVEN = 1

#--------------------------------------------------------
# Finishing
# -------------------------------------------------------

export USE_FILL = 1