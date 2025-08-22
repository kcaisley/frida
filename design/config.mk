export DESIGN_NAME = frida
export PLATFORM = tsmc65

# -----------------------------------------------------
#  Yosys (Synthesis)
#  ----------------------------------------------------

export VERILOG_FILES = $(DESIGN_HOME)/src/$(DESIGN_NAME)/adc.v \
                       $(DESIGN_HOME)/src/$(DESIGN_NAME)/clkgate.v \
                       $(DESIGN_HOME)/src/$(DESIGN_NAME)/salogic.v \
                       $(DESIGN_HOME)/src/$(DESIGN_NAME)/capdriver.v

export SYNTH_BLACKBOXES = caparray sampswitch comp

# If is provided, I think I don't need to set variables like ABC_CLOCK_PERIOD_IN_PS or CLOCK_PERIOD myself
export SDC_FILE      = $(DESIGN_HOME)/$(PLATFORM)/$(DESIGN_NAME)/constraint.sdc

#--------------------------------------------------------
# Floorplan
# -------------------------------------------------------

# Design parameters - mixed-signal layout constraints
export CORE_UTILIZATION = 60
export CORE_MARGIN = 2
export CORE_ASPECT_RATIO = 0.8 # W/L, retquires CORE_UTILIZATION
export PLACE_DENSITY = 0.8  # Higher density for more compact placement

#--------------------------------------------------------
# Floorplan
# -------------------------------------------------------

# Routing layer constraints - Try M2-M4 to bypass M1 pin access issues
# Based on TSMC65LP metal stack from tcbn65lp_9lmT2.lef
export MIN_ROUTING_LAYER = M1
export MAX_ROUTING_LAYER = M4


# I/O placement configuration - based on TSMC65LP metal layer directions from LEF
# M1: DIRECTION HORIZONTAL, M2: DIRECTION VERTICAL, M3: DIRECTION HORIZONTAL
export IO_PLACER_H = M1  # Horizontal I/O pins on M1 (horizontal preferred direction)
export IO_PLACER_V = M2  # Vertical I/O pins on M2 (vertical preferred direction)

# Enable timing-driven placement for better compactness and connectivity
# RC values configured in platforms/tsmc65/setRC.tcl from TSMC65LP specifications
export PLACE_TIMING_DRIVEN = 1