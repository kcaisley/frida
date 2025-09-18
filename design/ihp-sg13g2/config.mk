export DESIGN_NAME            = frida_top
export DESIGN_NICKNAME        = frida
export PLATFORM               = ihp-sg13g2

# Top-level Verilog files (flattened design) - include platform clock gate cells and IO cells
export VERILOG_FILES = $(DESIGN_HOME)/src/frida/adc.v \
                       $(DESIGN_HOME)/src/frida/caparray.v \
                       $(DESIGN_HOME)/src/frida/capdriver.v \
                       $(DESIGN_HOME)/src/frida/clkgate.v \
                       $(DESIGN_HOME)/src/frida/comp.v \
                       $(DESIGN_HOME)/src/frida/compmux.v \
                       $(DESIGN_HOME)/src/frida/frida_core.v \
                       $(DESIGN_HOME)/src/frida/frida_top_ihp.v \
                       $(DESIGN_HOME)/src/frida/salogic.v \
                       $(DESIGN_HOME)/src/frida/sampdriver.v \
                       $(DESIGN_HOME)/src/frida/sampswitch.v \
                       $(DESIGN_HOME)/src/frida/spi_register.v \
                       $(DESIGN_HOME)/src/frida/cells_ihp_sg13g2.v \
                       $(PLATFORM_DIR)/verilog/sg13g2_io.v

# Top-level constraints
export SDC_FILE      = $(DESIGN_HOME)/$(PLATFORM)/frida/constraint.sdc

# Hierarchical synthesis - enabled to preserve ADC macros for placement
export SYNTH_HIERARCHICAL = 1

# Sub-block directory to build first (adc block)
export BLOCKS = adc

# Override DONT_USE_CELLS to be empty (top-level design doesn't need restrictions)
export DONT_USE_CELLS =

# Blackbox analog IO cells to prevent Yosys from inserting buffers in parallel actually inside the io cell modules post synthesis
export SYNTH_BLACKBOXES = sg13g2_IOPadAnalog

# IO Pad LEFs for IHP-SG13G2 (bondpad and IO cells) and ADC macro LEF
export ADDITIONAL_LEFS += $(PLATFORM_DIR)/lef/bondpad_70x70.lef \
                         $(PLATFORM_DIR)/lef/sg13g2_io.lef \
                         ./results/$(PLATFORM)/frida_adc/base/adc.lef

# IO Pad GDS files for IHP-SG13G2
export ADDITIONAL_GDS += $(PLATFORM_DIR)/gds/bondpad_70x70.gds \
                        $(PLATFORM_DIR)/gds/sg13g2_io.gds

# ADC macro library file
# export ADDITIONAL_TYP_LIBS += ./results/$(PLATFORM)/frida_adc/base/adc_typ.lib

#--------------------------------------------------------
# Floorplan
# -------------------------------------------------------

# Die area: 1.5mm x 1.5mm for IHP-SG13G2 (larger than TSMC65)
export DIE_AREA = 0.0 0.0 1600.0 1600.0

# Core area: 1000x1000 centered (250um margin for IO pads and bondpads)
export CORE_AREA = 300 300 1300 1300

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
export MACRO_PLACE_HALO = 3 3

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

# Hold timing repair settings for mixed-signal design
export HOLD_BUF_LIST = sg13g2_buf_1 sg13g2_buf_2
export MAX_HOLD_BUFFER_PERCENT = 40
export HOLD_MARGIN = 0.05

# Additional repair_timing arguments to allow more hold buffers
export REPAIR_TIMING_ADDITIONAL_ARGS = -max_buffer_percent 40

# Disable aggressive hold timing repair during CTS
export CTS_REPAIR_HOLD_VIOLATIONS = 0

#--------------------------------------------------------
# Routing
# -------------------------------------------------------

# Routing layer constraints - IHP-SG13G2 has 5 metal layers + 2 top metals
export MIN_ROUTING_LAYER = Metal1
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