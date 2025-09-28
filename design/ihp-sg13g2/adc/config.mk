export DESIGN_NAME            = adc
export TOP_DESIGN_NICKNAME    = frida
export DESIGN_NICKNAME        = ${TOP_DESIGN_NICKNAME}_${DESIGN_NAME}
export PLATFORM               = ihp-sg13g2

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
                       $(DESIGN_HOME)/src/frida/cells_ihp_sg13g2.v

# Timing constraints
export SDC_FILE      = $(DESIGN_HOME)/$(PLATFORM)/frida/adc/constraint.sdc

# Disable hierarchical synthesis to flatten OPENROAD helper modules
export SYNTH_HIERARCHICAL = 0

# Allow use of clock gate cells (override platform default that has these commented out)
export DONT_USE_CELLS = sg13g2_sighold sg13g2_dfrbp_2

# Keep specific design modules from being flattened (exclude OPENROAD_* modules)
export SYNTH_KEEP_MODULES = clkgate salogic capdriver caparray sampdriver sampswitch comp

#--------------------------------------------------------
# Floorplan
# -------------------------------------------------------

# Increased design area: 150x150 micrometers for IHP-SG13G2 to accommodate macros
export DIE_AREA = 0 0 150 150
export CORE_AREA = 5 5 145 145

export MACRO_PLACEMENT_TCL = $(DESIGN_HOME)/$(PLATFORM)/frida/adc/macro.tcl

export MACRO_PLACE_HALO = 1 1

export PDN_TCL = $(DESIGN_HOME)/$(PLATFORM)/frida/adc/pdn.tcl

#--------------------------------------------------------
# Placement
# -------------------------------------------------------

# Protect critical buffer instances from removal during global placement
export DONT_TOUCH = $(DESIGN_HOME)/$(PLATFORM)/frida/adc/dont_touch.tcl
# export MANUAL_PLACE = $(DESIGN_HOME)/$(PLATFORM)/frida/adc/manual_place.tcl

export IO_PLACER_H = Metal2  # Horizontal I/O pins on Metal2 (IHP-SG13G2)
export IO_PLACER_V = Metal3  # Vertical I/O pins on Metal3 (IHP-SG13G2)

export IO_CONSTRAINTS = $(DESIGN_HOME)/$(PLATFORM)/frida/adc/io.tcl
export PLACE_PINS_ARGS = -min_distance 5 -min_distance_in_tracks

# Standard cell placement density
export PLACE_DENSITY = 0.65

#--------------------------------------------------------
# Clock Tree Synthsis (CTS)
# -------------------------------------------------------

# export SKIP_GATE_CLONING = 1

# Buffer list for CTS - using IHP-SG13G2 buffers
# export CTS_BUF_LIST = sg13g2_buf_1 sg13g2_buf_2 sg13g2_buf_4

# export CTS_BUF_DISTANCE = 80
# export CTS_ARGS = -dont_use_dummy_load -sink_buffer_max_cap_derate 0.1 -delay_buffer_derate 0.3

#--------------------------------------------------------
# Routing
# -------------------------------------------------------

# Routing layer constraints - IHP-SG13G2 metal stack
export MIN_ROUTING_LAYER = Metal1
export MAX_ROUTING_LAYER = Metal7

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

# Disable IR drop analysis for now to avoid dictionary parsing issues
export PWR_NETS_VOLTAGES = "vdd_d 1.2 vdd_a 1.2 vdd_dac 1.2"
export GND_NETS_VOLTAGES = "vss_d 0.0 vss_a 0.0 vss_dac 0.0"

# IR drop analysis layer (required for final report)
export IR_DROP_LAYER = M1