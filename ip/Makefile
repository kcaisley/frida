# Makefile for Verilog simulation using iverilog
# Usage: make simulate MODULE=<module_name>
# Example: make simulate MODULE=sar

# Default settings
SIMULATOR = iverilog
VCD_VIEWER = gtkwave
SYNTHESIZER = yosys
CLEAN_FILES = *.vcd *.out *_sim synth_*.v synth_*.json synth_*.blif *.dot synth_*report.txt

# Default module (can be overridden from command line)
MODULE ?= sar
mod ?= $(MODULE)

# Use the shorter 'mod' parameter if provided, otherwise use MODULE
TARGET_MODULE = $(mod)

# File extensions
SRC_EXT = .v
TB_EXT = _tb.v
SIM_EXT = _sim
VCD_EXT = .vcd

# Derived filenames
SRC_FILE = $(TARGET_MODULE)$(SRC_EXT)
TB_FILE = $(TARGET_MODULE)$(TB_EXT)
SIM_FILE = $(TARGET_MODULE)$(SIM_EXT)
VCD_FILE = $(TARGET_MODULE)_tb$(VCD_EXT)

# Default target
.PHONY: all
all: help

# Help target
.PHONY: help
help:
	@echo "Verilog Simulation Makefile"
	@echo "=========================="
	@echo ""
	@echo "Usage:"
	@echo "  make simulate mod=<module_name>     - Compile and run simulation"
	@echo "  make synth mod=<module_name>        - Synthesize module to hardware"
	@echo "  make synth-adv mod=<module_name>    - Advanced synthesis analysis"
	@echo "  make synth-asic mod=<module_name>   - ASIC-optimized synthesis"
	@echo "  make synth-gates mod=<module_name>  - Gate-level synthesis (NAND/NOR/NOT/MUX/DFF)"
	@echo "  make wave mod=<module_name>         - Open waveform viewer"
	@echo "  make clean                          - Clean generated files"
	@echo "  make list                           - List available modules"
	@echo ""
	@echo "Examples:"
	@echo "  make simulate mod=sar               - Simulate sar.v with sar_tb.v"
	@echo "  make synth mod=sar                  - Synthesize sar.v to hardware"
	@echo "  make wave mod=sar                   - View sar_tb.vcd waveforms"
	@echo ""
	@echo "Default module: $(MODULE)"
	@echo "Note: Both 'mod=' and 'MODULE=' work (mod= is shorter)"

# List available modules (look for *_tb.v files)
.PHONY: list
list:
	@echo "Available modules (based on *_tb.v files):"
	@for tb in *_tb.v; do \
		if [ -f "$$tb" ]; then \
			module=$$(basename $$tb _tb.v); \
			src="$$module.v"; \
			if [ -f "$$src" ]; then \
				echo "  $$module ($$src + $$tb)"; \
			else \
				echo "  $$module ($$tb only - missing $$src)"; \
			fi; \
		fi; \
	done

# Compile and run simulation
.PHONY: simulate
simulate:
	@echo "Compiling and running simulation for $(TARGET_MODULE)..."
	@if [ ! -f "$(SRC_FILE)" ]; then \
		echo "Error: Source file $(SRC_FILE) not found!"; \
		exit 1; \
	fi
	@if [ ! -f "$(TB_FILE)" ]; then \
		echo "Error: Testbench file $(TB_FILE) not found!"; \
		exit 1; \
	fi
	@echo "Compiling $(TARGET_MODULE)..."
	$(SIMULATOR) -o $(SIM_FILE) $(SRC_FILE) $(TB_FILE)
	@echo "Compilation successful: $(SIM_FILE)"
	@echo "Running simulation..."
	./$(SIM_FILE)
	@echo "Simulation complete"
	@if [ -f "$(VCD_FILE)" ]; then \
		echo "VCD file generated: $(VCD_FILE)"; \
	fi

# Synthesize module to hardware
.PHONY: synth
synth:
	@echo "Synthesizing $(TARGET_MODULE) to hardware..."
	@if [ ! -f "$(SRC_FILE)" ]; then \
		echo "Error: Source file $(SRC_FILE) not found!"; \
		exit 1; \
	fi
	@echo "Running Yosys synthesis..."
	$(SYNTHESIZER) -s synth_sar.ys
	@echo "Synthesis complete! Generated files:"
	@echo "  - synth_sar.v (synthesized Verilog)"
	@echo "  - synth_sar.json (JSON netlist)"
	@echo "  - sar_synth.dot (graphical representation)"
	@echo "  - synth_report.txt (synthesis report)"

# Advanced synthesis analysis
.PHONY: synth-adv
synth-adv:
	@echo "Running advanced synthesis analysis for $(TARGET_MODULE)..."
	@if [ ! -f "$(SRC_FILE)" ]; then \
		echo "Error: Source file $(SRC_FILE) not found!"; \
		exit 1; \
	fi
	@echo "Running advanced Yosys synthesis..."
	$(SYNTHESIZER) -s synth_sar_advanced.ys
	@echo "Advanced synthesis complete! Generated files:"
	@echo "  - synth_sar_clean.v (clean synthesized Verilog)"
	@echo "  - synth_sar_detailed.json (detailed JSON netlist)"
	@echo "  - synth_sar.blif (BLIF format)"
	@echo "  - sar_detailed.dot (detailed graphical representation)"
	@echo "  - synth_detailed_report.txt (detailed synthesis report)"

# ASIC synthesis targeting specific technology
.PHONY: synth-asic
synth-asic:
	@echo "Synthesizing $(TARGET_MODULE) for ASIC technology..."
	@if [ ! -f "$(SRC_FILE)" ]; then \
		echo "Error: Source file $(SRC_FILE) not found!"; \
		exit 1; \
	fi
	@echo "Targeting: combinational logic, muxes, D-flip flops, SR latches"
	$(SYNTHESIZER) -s synth_sar_asic.ys
	@echo "ASIC synthesis complete! Generated files:"
	@echo "  - synth_sar_asic.v (ASIC-optimized Verilog)"
	@echo "  - synth_sar_asic.json (ASIC JSON netlist)"
	@echo "  - synth_sar_asic.blif (ASIC BLIF format)"
	@echo "  - sar_asic.dot (ASIC layout visualization)"
	@echo "  - synth_asic_report.txt (ASIC synthesis report)"

# Gate-level synthesis for discrete logic primitives
.PHONY: synth-gates
synth-gates:
	@echo "Synthesizing $(TARGET_MODULE) to discrete logic gates..."
	@if [ ! -f "$(SRC_FILE)" ]; then \
		echo "Error: Source file $(SRC_FILE) not found!"; \
		exit 1; \
	fi
	@echo "Targeting: NAND, NOR, NOT, MUX, DFF gates (no PDK)"
	$(SYNTHESIZER) -s synth_sar_gates.ys
	@echo "Gate-level synthesis complete! Generated files:"
	@echo "  - synth_sar_gates.v (gate-level Verilog netlist)"
	@echo "  - synth_sar_gates.json (gate-level JSON netlist)"
	@echo "  - synth_sar_gates.blif (gate-level BLIF format)"
	@echo "  - sar_gates.dot (gate-level schematic)"
	@echo "  - synth_gates_report.txt (gate count report)"

# Open waveform viewer
.PHONY: wave
wave: $(VCD_FILE)
	@echo "Opening waveform viewer for $(TARGET_MODULE)..."
	$(VCD_VIEWER) $(VCD_FILE) &

$(VCD_FILE):
	@echo "VCD file $(VCD_FILE) not found. Running simulation first..."
	@$(MAKE) simulate mod=$(TARGET_MODULE)

# Clean generated files
.PHONY: clean
clean:
	@echo "Cleaning generated files..."
	rm -f $(CLEAN_FILES)
	@echo "Clean complete"

# Force rebuild
.PHONY: rebuild
rebuild: clean simulate

# Check if required tools are installed
.PHONY: check
check:
	@echo "Checking for required tools..."
	@which $(SIMULATOR) > /dev/null || (echo "Error: $(SIMULATOR) not found!" && exit 1)
	@echo "✓ $(SIMULATOR) found"
	@which $(VCD_VIEWER) > /dev/null && echo "✓ $(VCD_VIEWER) found" || echo "⚠ $(VCD_VIEWER) not found (waveform viewing unavailable)"
	@echo "Environment check complete"

# Debug target - show variables
.PHONY: debug
debug:
	@echo "Makefile Debug Information"
	@echo "========================="
	@echo "MODULE:        $(MODULE)"
	@echo "mod:           $(mod)"
	@echo "TARGET_MODULE: $(TARGET_MODULE)"
	@echo "SRC_FILE:      $(SRC_FILE)"
	@echo "TB_FILE:       $(TB_FILE)"
	@echo "SIM_FILE:      $(SIM_FILE)"
	@echo "VCD_FILE:      $(VCD_FILE)"
	@echo "SIMULATOR:     $(SIMULATOR)"
	@echo "VCD_VIEWER:    $(VCD_VIEWER)"
