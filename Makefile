# FRIDA Project Makefile

# Default target
.PHONY: all clean caparray

all: caparray

# Generate caparray.gds using the cdac_layout.py script
caparray: tech/tsmc65/gds/caparray.gds

tech/tsmc65/gds/caparray.gds: src/cdac_layout.py src/cdac.py
	@mkdir -p tech/tsmc65/gds
	cd src && python3 cdac_layout.py ../tech/tsmc65/gds/caparray.gds

# Clean generated files
clean:
	rm -f tech/tsmc65/gds/caparray.gds

# View the generated GDS file in KLayout
view: tech/tsmc65/gds/caparray.gds
	klayout -nn tech/tsmc65/tsmc65.lyt -l tech/tsmc65/tsmc65.lyp tech/tsmc65/gds/caparray.gds

# Help target
help:
	@echo "Available targets:"
	@echo "  all       - Build all targets (default)"
	@echo "  caparray  - Generate caparray.gds layout file"
	@echo "  view      - Open caparray.gds in KLayout with TSMC65 tech files"
	@echo "  clean     - Remove generated files"
	@echo "  help      - Show this help message"