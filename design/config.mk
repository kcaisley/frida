export PLATFORM               = tsmc65

export DESIGN_NAME            = frida_top
export DESIGN_NICKNAME        = frida

# name of sub-block directory to do first
export BLOCKS = adc

# Top-level Verilog files (hierarchical design)
export VERILOG_FILES = $(DESIGN_HOME)/$(PLATFORM)/$(DESIGN_NICKNAME)/frida_top.v \
                      $(DESIGN_HOME)/$(PLATFORM)/$(DESIGN_NICKNAME)/frida_core.v \
                      $(DESIGN_HOME)/$(PLATFORM)/$(DESIGN_NICKNAME)/spi_register.v \
                      $(DESIGN_HOME)/$(PLATFORM)/$(DESIGN_NICKNAME)/compmux.v \
                      $(DESIGN_HOME)/$(PLATFORM)/$(DESIGN_NICKNAME)/pad_blackboxes.v \
                      $(DESIGN_HOME)/$(PLATFORM)/$(DESIGN_NICKNAME)/adc/adc.v \
                      $(DESIGN_HOME)/$(PLATFORM)/$(DESIGN_NICKNAME)/adc/clkgate.v \
                      $(DESIGN_HOME)/$(PLATFORM)/$(DESIGN_NICKNAME)/adc/salogic.v \
                      $(DESIGN_HOME)/$(PLATFORM)/$(DESIGN_NICKNAME)/adc/capdriver.v \
                      $(DESIGN_HOME)/$(PLATFORM)/$(DESIGN_NICKNAME)/adc/sampdriver.v \
                      $(DESIGN_HOME)/$(PLATFORM)/$(DESIGN_NICKNAME)/adc/comp.v \
                      $(DESIGN_HOME)/$(PLATFORM)/$(DESIGN_NICKNAME)/adc/sampswitch.v \
                      $(DESIGN_HOME)/$(PLATFORM)/$(DESIGN_NICKNAME)/adc/caparray.v

# Top-level constraints
export SDC_FILE      = $(DESIGN_HOME)/$(PLATFORM)/frida/constraint.sdc

# Sealring GDS file
export SEAL_GDS = $(PLATFORM_DIR)/gds/sealring.gds

#--------------------------------------------------------
# Floorplan
# -------------------------------------------------------

# Die area: 1mm x 1mm = 1000um x 1000um
export DIE_AREA = 0 0 1000 1000

# Core area: ~600um x 600um centered (200um margin for IO pads on all sides)
export CORE_AREA = 200 200 800 800

# Pad footprint placement script
export FOOTPRINT_TCL = $(DESIGN_HOME)/$(PLATFORM)/frida/pad.tcl

# Pin placement settings for IO pads
export PLACE_PINS_ARGS = -min_distance 10 -min_distance_in_tracks

#--------------------------------------------------------
# Placement
# -------------------------------------------------------

export PLACE_DENSITY = 0.6
export MACRO_PLACE_HALO = 5 5

# PDN configuration for hierarchical design
export PDN_TCL = $(DESIGN_HOME)/$(PLATFORM)/frida/BLOCKS_grid_strategy.tcl

#--------------------------------------------------------
# Clock Tree Synthsis (CTS)
# -------------------------------------------------------

export SKIP_GATE_CLONING = 1

# Buffer list for CTS
export CTS_BUF_LIST = BUFFD0LVT BUFFD1LVT BUFFD2LVT

export CTS_BUF_DISTANCE = 80
export CTS_ARGS = -dont_use_dummy_load -sink_buffer_max_cap_derate 0.1 -delay_buffer_derate 0.3

#--------------------------------------------------------
# Routing
# -------------------------------------------------------

# Routing layer constraints - use more layers for top-level
export MAX_ROUTING_LAYER = M6

# Enable timing-driven placement
export PLACE_TIMING_DRIVEN = 1

#--------------------------------------------------------
# Finishing
# -------------------------------------------------------

export USE_FILL = 1