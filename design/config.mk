export DESIGN_NAME = frida
export PLATFORM = tsmc65

export VERILOG_FILES = $(DESIGN_HOME)/src/$(DESIGN_NAME)/adc.v \
                       $(DESIGN_HOME)/src/$(DESIGN_NAME)/clkgate.v \
                       $(DESIGN_HOME)/src/$(DESIGN_NAME)/salogic.v \
                       $(DESIGN_HOME)/src/$(DESIGN_NAME)/capdriver.v \
                       $(DESIGN_HOME)/src/$(DESIGN_NAME)/sampswitch.v \
                       $(DESIGN_HOME)/src/$(DESIGN_NAME)/caparray.v \
                       $(DESIGN_HOME)/src/$(DESIGN_NAME)/comp.v

export SDC_FILE      = $(DESIGN_HOME)/$(PLATFORM)/$(DESIGN_NAME)/constraint.sdc

# Design parameters - mixed-signal layout constraints
# export CORE_UTILIZATION = 60
export PLACE_DENSITY ?= 0.65  # Higher density for more compact placement

# Clock frequency assumption (100MHz) - from constraint.sdc timing analysis
export CLOCK_PERIOD = 10.0

# Layout constraints - Reduced core for tighter placement
# Area values in microns, reducing from 50x50um to force more compact placement  
export DIE_AREA    = 0.0 0.0 50.0 50.0  # Total die including I/O and guard bands
export CORE_AREA   = 5.0 5.0 45.0 45.0  # Digital logic placement area (40x40um)

# Routing layer constraints - Try M2-M4 to bypass M1 pin access issues
# Based on TSMC65LP metal stack from tcbn65lp_9lmT2.lef
export MIN_ROUTING_LAYER = M2  # Skip M1 to avoid pin access issues
export MAX_ROUTING_LAYER = M4  # Expanded to M4 for better routing (TSMC65: up to M9 available)

# I/O placement configuration - based on TSMC65LP metal layer directions from LEF
# M1: DIRECTION HORIZONTAL, M2: DIRECTION VERTICAL, M3: DIRECTION HORIZONTAL
export IO_PLACER_H = M1  # Horizontal I/O pins on M1 (horizontal preferred direction)
export IO_PLACER_V = M2  # Vertical I/O pins on M2 (vertical preferred direction)

# Enable timing-driven placement for better compactness and connectivity
# RC values configured in platforms/tsmc65/setRC.tcl from TSMC65LP specifications
export PLACE_TIMING_DRIVEN = 1