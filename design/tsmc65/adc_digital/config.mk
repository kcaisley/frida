export DESIGN_NAME            = adc_digital
export TOP_DESIGN_NICKNAME    = frida
export DESIGN_NICKNAME        = ${TOP_DESIGN_NICKNAME}_${DESIGN_NAME}
export PLATFORM               = tsmc65

# -----------------------------------------------------
#  Yosys (Synthesis)
#  ----------------------------------------------------

export VERILOG_FILES = $(DESIGN_HOME)/src/frida/adc_digital.v \
                       $(DESIGN_HOME)/src/frida/clkgate.v \
                       $(DESIGN_HOME)/src/frida/salogic.v \
                       $(DESIGN_HOME)/src/frida/sampdriver.v \
                       $(DESIGN_HOME)/src/frida/cells_tsmc65.v

# Timing constraints
export SDC_FILE      = $(DESIGN_HOME)/$(PLATFORM)/frida/adc_digital/constraint.sdc

# Disable hierarchical synthesis to flatten OPENROAD helper modules
export SYNTH_HIERARCHICAL = 0

# Allow all cells
export DONT_USE_CELLS =

# Keep specific design modules from being flattened (exclude OPENROAD_* modules)
# Note: analog macros (caparray, sampswitch, comp) removed since they're factored out
export SYNTH_KEEP_MODULES = clkgate salogic sampdriver

#--------------------------------------------------------
# Floorplan
# -------------------------------------------------------

export DIE_AREA = 0 0 60 49
export CORE_AREA = 0 0 60 49

# Create blockages for future analog macro placement areas via floorplan hook
export CREATE_BLOCKAGES = $(DESIGN_HOME)/$(PLATFORM)/frida/adc_digital/create_blockages.tcl


export PDN_TCL = $(DESIGN_HOME)/$(PLATFORM)/frida/adc_digital/pdn.tcl

#--------------------------------------------------------
# Placement
# -------------------------------------------------------

# Disable routability-driven placement due to OpenROAD bug
# ISSUE: OpenROAD v2.0-24135-gb57dad1953 crashes during routability-driven
#        global placement with this design. The crash occurs in cutFillerCells()
#        when GPL tries to inflate cell area to reduce routing congestion.
# SYMPTOM: Assertion failure in std::vector at gpl::NesterovBase::destroyFillerGCell
# TRIGGER: Any routability inflation > 0% causes vector out-of-bounds access
# WORKAROUND: Disable routability-driven placement. Timing-driven mode still works.
# TODO: Report bug to OpenROAD with design reproducer
export GPL_ROUTABILITY_DRIVEN = 0

# FRIDA project specific scripts for placement (triggered from global_place.tcl)
export DONT_TOUCH = $(DESIGN_HOME)/$(PLATFORM)/frida/adc_digital/dont_touch.tcl

export IO_PLACER_H = M3
export IO_PLACER_V = M2

# NOTE: WAIT WOULD THIS MAYBE BE THE FLOORPLANNING SPACING FOR REGIONS?
export IO_CONSTRAINTS = $(DESIGN_HOME)/$(PLATFORM)/frida/adc_digital/io.tcl
export PLACE_PINS_ARGS = -min_distance 0.8

# Standard cell placement density
export PLACE_DENSITY = 0.50

#--------------------------------------------------------
# Clock Tree Synthesis (CTS)
# -------------------------------------------------------

#--------------------------------------------------------
# Routing
# -------------------------------------------------------

# Based on TSMC65LP metal stack from tcbn65lp_9lmT2.lef
export MIN_ROUTING_LAYER = M2
export MAX_ROUTING_LAYER = M3

# Create routing blockages before global route
export PRE_GLOBAL_ROUTE_TCL = $(DESIGN_HOME)/$(PLATFORM)/frida/adc_digital/routing_blockages.tcl

# Enable detailed routing debug for caparray pin coverage issues
export DETAILED_ROUTE_ARGS = -droute_end_iter 1 -verbose 2

#--------------------------------------------------------
# Finishing
# -------------------------------------------------------

# Only disables metal fill; FILL_CELLS in routing step still adds FEOL decap fill cells
export USE_FILL = 0