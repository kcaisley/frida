export DESIGN_NAME            = frida_top
export DESIGN_NICKNAME        = frida
export PLATFORM               = tsmc65

# Top-level Verilog files (hierarchical design)
export VERILOG_FILES = $(DESIGN_HOME)/$(PLATFORM)/$(DESIGN_NICKNAME)/*.v

# Top-level constraints
export SDC_FILE      = $(DESIGN_HOME)/$(PLATFORM)/$(DESIGN_NICKNAME)/constraint.sdc

# Sealring GDS file
export SEAL_GDS = $(PLATFORM_DIR)/gds/sealring.gds

# export SYNTH_HIERARCHICAL = 1

# name of sub-block directory to do first
export BLOCKS = adc

# IO Pad LEFs (Circuit Under Pad) and Fillers for top-level
export ADDITIONAL_LEFS += $(PLATFORM_DIR)/lef/LVDS_RX_CUP_pad.lef \
                         $(PLATFORM_DIR)/lef/LVDS_TX_CUP_pad.lef \
                         $(PLATFORM_DIR)/lef/CMOS_IO_CUP_pad.lef \
                         $(PLATFORM_DIR)/lef/PASSIVE_CUP_pad.lef \
                         $(PLATFORM_DIR)/lef/POWER_CUP_pad.lef \
                         $(PLATFORM_DIR)/lef/GROUND_CUP_pad.lef \
                         $(PLATFORM_DIR)/lef/SF_CORNER.lef \
                         $(PLATFORM_DIR)/lef/SF_FILLER50_CUP.lef \
                         $(PLATFORM_DIR)/lef/SF_FILLER_CUP.lef \
                         $(PLATFORM_DIR)/lef/POWERCUT_CUP.lef

# IO Pad GDS files for top-level
export ADDITIONAL_GDS += $(PLATFORM_DIR)/gds/LVDS_RX_CUP_pad.gds \
                        $(PLATFORM_DIR)/gds/LVDS_TX_CUP_pad.gds \
                        $(PLATFORM_DIR)/gds/CMOS_IO_CUP_pad.gds \
                        $(PLATFORM_DIR)/gds/PASSIVE_CUP_pad.gds \
                        $(PLATFORM_DIR)/gds/POWER_CUP_pad.gds \
                        $(PLATFORM_DIR)/gds/GROUND_CUP_pad.gds \
                        $(PLATFORM_DIR)/gds/SF_CORNER.gds \
                        $(PLATFORM_DIR)/gds/SF_FILLER50_CUP.gds \
                        $(PLATFORM_DIR)/gds/SF_FILLER_CUP.gds \
                        $(PLATFORM_DIR)/gds/POWERCUT_CUP.gds

#--------------------------------------------------------
# Floorplan
# -------------------------------------------------------

# Die area: 1mm x 1mm = 1000um x 1000um
export DIE_AREA = 0 0 1000 1000

# Core area: ~600um x 600um centered (200um margin for IO pads on all sides)
export CORE_AREA = 200 200 800 800

# Pad footprint placement script
export FOOTPRINT_TCL = $(DESIGN_HOME)/$(PLATFORM)/$(DESIGN_NICKNAME)/pad.tcl

# Pin placement settings for IO pads
export PLACE_PINS_ARGS = -min_distance 10 -min_distance_in_tracks

#--------------------------------------------------------
# Placement
# -------------------------------------------------------

export PLACE_DENSITY = 0.6
export MACRO_PLACE_HALO = 5 5

# PDN configuration for hierarchical design
export PDN_TCL = $(DESIGN_HOME)/$(PLATFORM)/$(DESIGN_NICKNAME)/BLOCKS_grid_strategy.tcl

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