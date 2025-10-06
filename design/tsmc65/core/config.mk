export DESIGN_NAME            = frida_core
export DESIGN_NICKNAME        = core
export PLATFORM               = tsmc65

# Top-level Verilog files (flattened design) - include platform clock gate cells and IO cells
export VERILOG_FILES = $(DESIGN_HOME)/src/frida/compmux.v \
                       $(DESIGN_HOME)/src/frida/frida_core.v \
                       $(DESIGN_HOME)/src/frida/spi_register.v \
                       $(DESIGN_HOME)/src/frida/cells_tsmc65.v \
                       $(DESIGN_HOME)/src/frida/adc_macro.v \

# Top-level constraints
export SDC_FILE      = $(DESIGN_HOME)/$(PLATFORM)/frida/core/constraint.sdc

# Additional LEF files for hierarchical macros
export ADDITIONAL_LEFS += $(PLATFORM_DIR)/lef/adc.lef

# # Verilog blackbox modules (prevent synthesis, use as pre-built macros)
# export ADDITIONAL_VERILOG_FILES = $(DESIGN_HOME)/src/frida/adc_macro.v

# Hierarchical synthesis - enabled to preserve ADC macros for placement
export SYNTH_HIERARCHICAL = 1

#--------------------------------------------------------
# Floorplan
# -------------------------------------------------------

# Die area: 540um x 540um
export DIE_AREA = 0 0 540 540

# Core area
export CORE_AREA = 0 0 540 540

# Macro placement script for 16 ADC instances - explicit 4x4 grid placement
export MACRO_PLACEMENT_TCL = $(DESIGN_HOME)/$(PLATFORM)/frida/core/macro.tcl

#--------------------------------------------------------
# Placement
# -------------------------------------------------------

export PLACE_DENSITY = 0.6
export MACRO_PLACE_HALO = 2 2

# PDN configuration for hierarchical design with multiple supply domains
export PDN_TCL = $(DESIGN_HOME)/$(PLATFORM)/frida/core/pdn.tcl

# Placement blockages for SPI register constraint
export CREATE_BLOCKAGES = $(DESIGN_HOME)/$(PLATFORM)/frida/core/create_blockages.tcl


export IO_CONSTRAINTS = $(DESIGN_HOME)/$(PLATFORM)/frida/core/io.tcl
# Pin placement settings for IO pads
# export PLACE_PINS_ARGS = -min_distance 1

export PLACE_DENSITY = 0.50

#--------------------------------------------------------
# Clock Tree Synthsis (CTS)
# -------------------------------------------------------

# Use TSMC65 buffer cells for CTS
# export CTS_BUF_LIST = BUFFD0LVT BUFFD1LVT BUFFD2LVT

# export CTS_BUF_DISTANCE = 40
# Disable clock gate cloning for mixed-signal design
# export SKIP_GATE_CLONING = 1

# Hold timing repair settings for mixed-signal design
# export HOLD_BUF_LIST = BUFFD0LVT BUFFD1LVT
# export MAX_HOLD_BUFFER_PERCENT = 40
# export HOLD_MARGIN = 0.05

# Additional repair_timing arguments to allow more hold buffers
# export REPAIR_TIMING_ADDITIONAL_ARGS = -max_buffer_percent 40

# Disable aggressive hold timing repair during CTS
# export CTS_REPAIR_HOLD_VIOLATIONS = 0

#--------------------------------------------------------
# Routing
# -------------------------------------------------------

# Routing layer constraints - TSMC65 has 6 metal layers + 2 top metals
export MIN_ROUTING_LAYER = M2
export MAX_ROUTING_LAYER = M3

#--------------------------------------------------------
# Finishing
# -------------------------------------------------------

# Only disables metal fill; FILL_CELLS in routing step still adds FEOL decap fill cells
export USE_FILL = 0