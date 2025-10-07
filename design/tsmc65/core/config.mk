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

# Liberty files: standard cells + ADC macro
export LIB_FILES = $(PLATFORM_DIR)/lib/tcbn65lplvtwc.lib $(PLATFORM_DIR)/lib/adc.lib

# Allow empty GDS for ADC macro (analog block without GDS)
export GDS_ALLOW_EMPTY = adc

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

# Use clock buffers (CKBD*) for low-skew H-tree distribution to 16 ADC instances
# - buf_list: Clock buffers for H-tree balancing (multiple sizes for optimization)
# - balance_levels: True H-tree without clustering (for minimal skew across 500um)
# - obstruction_aware: Place buffers intelligently around 16 ADC macro blockages
# - macro_clustering_size 1: One leaf buffer per ADC macro (no clustering)
# export CTS_ARGS = -buf_list {CKBD4LVT CKBD8LVT CKBD16LVT CKBD20LVT} -balance_levels -obstruction_aware -macro_clustering_size 1 -num_static_layers 4

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