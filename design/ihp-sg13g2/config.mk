export DESIGN_NAME            = frida_top
export DESIGN_NICKNAME        = frida
export PLATFORM               = ihp-sg13g2

# Top-level Verilog files (flattened design) - include platform clock gate cells
export VERILOG_FILES = $(HOME)/frida/rtl/adc.v \
                       $(HOME)/frida/rtl/caparray.v \
                       $(HOME)/frida/rtl/capdriver.v \
                       $(HOME)/frida/rtl/clkgate.v \
                       $(HOME)/frida/rtl/comp.v \
                       $(HOME)/frida/rtl/compmux.v \
                       $(HOME)/frida/rtl/frida_core.v \
                       $(HOME)/frida/rtl/frida_top_ihp.v \
                       $(HOME)/frida/rtl/salogic.v \
                       $(HOME)/frida/rtl/sampdriver.v \
                       $(HOME)/frida/rtl/sampswitch.v \
                       $(HOME)/frida/rtl/spi_register.v \
                       $(PLATFORM_DIR)/cells_ihp_sg13g2.v

# Top-level constraints
export SDC_FILE      = $(DESIGN_HOME)/$(PLATFORM)/constraint.sdc

# Hierarchical synthesis - enabled to preserve ADC macros for placement
export SYNTH_HIERARCHICAL = 1

# Sub-block directory to build first (adc block)
export BLOCKS = adc

# Don't use problematic cells (from platform config)
export DONT_USE_CELLS = sg13g2_sighold sg13g2_dfrbp_2

# IO Pad LEFs for IHP-SG13G2 (bondpad and IO cells) and ADC macro LEF
export ADDITIONAL_LEFS += $(PLATFORM_DIR)/lef/bondpad_70x70.lef \
                         $(PLATFORM_DIR)/lef/sg13g2_io.lef \
                         ./results/ihp-sg13g2/frida_adc/base/adc.lef

# IO Pad GDS files for IHP-SG13G2
export ADDITIONAL_GDS += $(PLATFORM_DIR)/gds/bondpad_70x70.gds \
                        $(PLATFORM_DIR)/gds/sg13g2_io.gds

# ADC macro library file
export ADDITIONAL_TYP_LIBS += ./results/ihp-sg13g2/frida_adc/base/adc_typ.lib

#--------------------------------------------------------
# Floorplan
# -------------------------------------------------------

# Die area: 1.5mm x 1.5mm for IHP-SG13G2 (larger than TSMC65)
# export DIE_AREA = 0.0 0.0 1500.0 1500.0

# Core area: 1000x1000 centered (250um margin for IO pads and bondpads)
# export CORE_AREA = 250 250 1250 1250

# Pad footprint placement script - now handles floorplan initialization
export FOOTPRINT_TCL = $(DESIGN_HOME)/$(PLATFORM)/frida/pad.tcl

# Macro placement script for 16 ADC instances - explicit 4x4 grid placement
export MACRO_PLACEMENT_TCL = $(DESIGN_HOME)/$(PLATFORM)/frida/macro.tcl

# Pin placement settings for IO pads
export PLACE_PINS_ARGS = -min_distance 10 -min_distance_in_tracks

#--------------------------------------------------------
# Placement
# -------------------------------------------------------

export PLACE_DENSITY = 0.6
export MACRO_PLACE_HALO = 10 10

# PDN configuration for hierarchical design with multiple supply domains
export PDN_TCL = $(DESIGN_HOME)/$(PLATFORM)/frida/pdn.tcl

#--------------------------------------------------------
# Clock Tree Synthsis (CTS)
# -------------------------------------------------------

# Use IHP-SG13G2 buffer cells for CTS
export CTS_BUF_LIST = sg13g2_buf_1 sg13g2_buf_2 sg13g2_buf_4

export CTS_BUF_DISTANCE = 100
# Disable clock gate cloning for mixed-signal design
export SKIP_GATE_CLONING = 1

#--------------------------------------------------------
# Routing
# -------------------------------------------------------

# Routing layer constraints - IHP-SG13G2 has 5 metal layers + 2 top metals
export MIN_ROUTING_LAYER = Metal2
export MAX_ROUTING_LAYER = Metal5

# Enable timing-driven placement for large design
export GPL_TIMING_DRIVEN = 1

#--------------------------------------------------------
# Finishing
# -------------------------------------------------------

export USE_FILL = 1

#--------------------------------------------------------
# Power Analysis for Mixed-Signal Design
# -------------------------------------------------------

# Multiple power domains for mixed-signal design
# Disable for now to avoid dictionary parsing issues at top level
# export PWR_NETS_VOLTAGES = "{vdd_d 1.2 vdd_a 1.2 vdd_dac 1.2 vdd_io 3.3}"
# export GND_NETS_VOLTAGES = "{vss_d 0.0 vss_a 0.0 vss_dac 0.0 vss_io 0.0}"