# Makefile for Verilog simulation using iverilog
# Usage: make simulate MODULE=<module_name>
# Example: make simulate MODULE=sar

# Default settings
SIMULATOR = iverilog
VCD_VIEWER = gtkwave
CLEAN_FILES = *.vcd *.out *_sim

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
	@echo "  make wave mod=<module_name>         - Open waveform viewer"
	@echo "  make clean                          - Clean generated files"
	@echo "  make list                           - List available modules"
	@echo ""
	@echo "Examples:"
	@echo "  make simulate mod=sar               - Simulate sar.v with sar_tb.v"
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
