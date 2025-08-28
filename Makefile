# FRIDA Project Makefile

# Default target
.PHONY: all clean caparray strmout lefout

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

# Define cells to export: library:cell:outputname
EXPORT_CELLS := CoRDIA_ADC_01:COMP_LATCH:comp CoRDIA_ADC_01:SAMPLE_SW:sampswitch

# Export OpenAccess cells to GDS using Cadence strmout
strmout:
	@mkdir -p logs tech/tsmc65/gds
	@echo "Exporting OpenAccess cells to GDS..."
	@for cell in $(EXPORT_CELLS); do \
		library=$$(echo $$cell | cut -d: -f1); \
		cellname=$$(echo $$cell | cut -d: -f2); \
		output=$$(echo $$cell | cut -d: -f3); \
		echo "Exporting $$library:$$cellname -> $$output.gds"; \
		(cd $(CURDIR)/tech/tsmc65/cds && . ./workspace.sh && strmout -library "$$library" -strmFile "$(CURDIR)/tech/tsmc65/gds/$$output.gds" -techLib 'tsmcN65' -topCell "$$cellname" -view 'layout' -logFile "$(CURDIR)/logs/$${output}_strmOut.log" -enableColoring) || exit 1; \
	done
	@echo "GDS export complete. Files saved to tech/tsmc65/gds/, logs in logs/"

# Export OpenAccess cells to LEF using Cadence lefout
lefout:
	@mkdir -p logs tech/tsmc65/lef
	@echo "Exporting OpenAccess cells to LEF..."
	@for cell in $(EXPORT_CELLS); do \
		library=$$(echo $$cell | cut -d: -f1); \
		cellname=$$(echo $$cell | cut -d: -f2); \
		output=$$(echo $$cell | cut -d: -f3); \
		echo "Exporting $$library:$$cellname -> $$output.lef"; \
		(cd $(CURDIR)/tech/tsmc65/cds && . ./workspace.sh && lefout -lef "$(CURDIR)/tech/tsmc65/lef/$$output.lef" -lib "$$library" -cells "$$cellname" -views "layout" -log "$(CURDIR)/logs/$${output}_lefout.log") || exit 1; \
	done
	@echo "LEF export complete. Files saved to tech/tsmc65/lef/, logs in logs/"

# Help target
help:
	@echo "Available targets:"
	@echo "  all       - Build all targets (default)"
	@echo "  caparray  - Generate caparray.gds layout file"
	@echo "  view      - Open caparray.gds in KLayout with TSMC65 tech files"
	@echo "  strmout   - Export OpenAccess cells (COMP_LATCH, SAMPLE_SW) to GDS"
	@echo "  lefout    - Export OpenAccess cells (COMP_LATCH, SAMPLE_SW) to LEF"
	@echo "  clean     - Remove generated files"
	@echo "  help      - Show this help message"