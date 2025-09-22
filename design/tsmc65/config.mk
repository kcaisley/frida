export DESIGN_NAME            = frida_top
export DESIGN_NICKNAME        = frida
export PLATFORM               = tsmc65

# Top-level Verilog files (flattened design) - include platform clock gate cells and IO cells
export VERILOG_FILES = $(DESIGN_HOME)/src/frida/adc.v \
                       $(DESIGN_HOME)/src/frida/caparray.v \
                       $(DESIGN_HOME)/src/frida/capdriver.v \
                       $(DESIGN_HOME)/src/frida/clkgate.v \
                       $(DESIGN_HOME)/src/frida/comp.v \
                       $(DESIGN_HOME)/src/frida/compmux.v \
                       $(DESIGN_HOME)/src/frida/frida_core.v \
                       $(DESIGN_HOME)/src/frida/frida_top_tsmc65.v \
                       $(DESIGN_HOME)/src/frida/salogic.v \
                       $(DESIGN_HOME)/src/frida/sampdriver.v \
                       $(DESIGN_HOME)/src/frida/sampswitch.v \
                       $(DESIGN_HOME)/src/frida/spi_register.v \
                       $(DESIGN_HOME)/src/frida/cells_tsmc65.v

# Top-level constraints
export SDC_FILE      = $(DESIGN_HOME)/$(PLATFORM)/frida/constraint.sdc

# Sealring GDS file
export SEAL_GDS = $(PLATFORM_DIR)/gds/sealring.gds

# Hierarchical synthesis - enabled to preserve ADC macros for placement
export SYNTH_HIERARCHICAL = 1

# Sub-block directory to build first (adc block)
export BLOCKS = adc

# Override DONT_USE_CELLS to be empty (top-level design doesn't need restrictions)
export DONT_USE_CELLS =

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

# Pad footprint placement script - contains place_pad commands run during floorplan
export FOOTPRINT_TCL = $(DESIGN_HOME)/$(PLATFORM)/frida/pad.tcl

# Macro placement script for 16 ADC instances - explicit 4x4 grid placement
export MACRO_PLACEMENT_TCL = $(DESIGN_HOME)/$(PLATFORM)/frida/macro.tcl

# Pin placement settings for IO pads
export PLACE_PINS_ARGS = -min_distance 10 -min_distance_in_tracks

#--------------------------------------------------------
# Placement
# -------------------------------------------------------

export PLACE_DENSITY = 0.6
export MACRO_PLACE_HALO = 5 5

# PDN configuration for hierarchical design with multiple supply domains
export PDN_TCL = $(DESIGN_HOME)/$(PLATFORM)/frida/pdn.tcl

#--------------------------------------------------------
# Clock Tree Synthsis (CTS)
# -------------------------------------------------------

# Use TSMC65 buffer cells for CTS
export CTS_BUF_LIST = BUFFD0LVT BUFFD1LVT BUFFD2LVT

export CTS_BUF_DISTANCE = 100
# Disable clock gate cloning for mixed-signal design
export SKIP_GATE_CLONING = 1

# Hold timing repair settings for mixed-signal design
export HOLD_BUF_LIST = BUFFD0LVT BUFFD1LVT
export MAX_HOLD_BUFFER_PERCENT = 40
export HOLD_MARGIN = 0.05

# Additional repair_timing arguments to allow more hold buffers
export REPAIR_TIMING_ADDITIONAL_ARGS = -max_buffer_percent 40

# Disable aggressive hold timing repair during CTS
export CTS_REPAIR_HOLD_VIOLATIONS = 0

#--------------------------------------------------------
# Routing
# -------------------------------------------------------

# Routing layer constraints - TSMC65 has 6 metal layers + 2 top metals
export MIN_ROUTING_LAYER = M1
export MAX_ROUTING_LAYER = M6

# Enable timing-driven placement for large design
export GPL_TIMING_DRIVEN = 1

#--------------------------------------------------------
# Finishing
# -------------------------------------------------------

export USE_FILL = 1