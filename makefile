# FRIDA Project Makefile

# Platform configuration
PLATFORM := tsmc65

# Define cells to export: library:cell:outputname
EXPORT_CELLS := frida:comp:comp frida:sampswitch:sampswitch \
	IOlib:GROUND_CUP_pad:GROUND_CUP_pad \
	IOlib:POWER_CUP_pad:POWER_CUP_pad \
	IOlib:LVDS_RX_CUP_pad:LVDS_RX_CUP_pad \
	IOlib:CMOS_IO_CUP_pad:CMOS_IO_CUP_pad \
	IOlib:LVDS_TX_CUP_pad:LVDS_TX_CUP_pad \
	IOlib:PASSIVE_CUP_pad:PASSIVE_CUP_pad \
	IOlib:POWERCUT_CUP:POWERCUT_CUP \
	IOlib:SF_CORNER:SF_CORNER \
	IOlib:SF_FILLER25_CUP:SF_FILLER25_CUP \
	IOlib:SF_FILLER50_CUP:SF_FILLER50_CUP \
	IOlib:SF_FILLER_CUP:SF_FILLER_CUP \
	CoRDIA_ADC_01:SEALRING_mini_sic65nm_1mm_1mm_from_2mm_2mm:sealring

# PVS DRC rule file path
PVS_DRC_RULES := /eda/kits/TSMC/65LP/2024/V1.7A_1/1p9m6x1z1u/PVS_QRC/drc/cell.PLN65S_9M_6X1Z1U.23a1

# Default target
.PHONY: all gds lef strmout lefout cdlout pvsdrc viewdrc setup behavioral

all: gds caparray

# Setup Python virtual environment and install dependencies
setup:
	@echo "Creating Python virtual environment..."
	python -m venv .venv
	@echo "Activating virtual environment and installing packages..."
	.venv/bin/python -m pip install --upgrade pip
	.venv/bin/python -m pip install klayout spicelib blosc2 wavedrom PyQt5 numpy matplotlib pandas tqdm pytest cocotb cocotbext-spi jinja2
	@echo "Setup complete! Activate with: source .venv/bin/activate"

# Generate GDS for specified block, using .py script for klayout: make gds <cellname>
gds:
	@if [ -z "$(filter-out $@,$(MAKECMDGOALS))" ]; then \
		echo "Usage: make gds <cellname>"; \
		echo "This will look for src/<cellname>.py and generate tech/$(PLATFORM)/gds/<cellname>.gds"; \
		exit 1; \
	fi
	@cellname="$(filter-out $@,$(MAKECMDGOALS))"; \
	if [ ! -f "src/$${cellname}.py" ]; then \
		echo "Error: src/$${cellname}.py not found"; \
		exit 1; \
	fi; \
	mkdir -p tech/$(PLATFORM)/gds; \
	echo "Generating GDS for $${cellname}..."; \
	.venv/bin/python "src/$${cellname}.py" "tech/$(PLATFORM)/gds/$${cellname}.gds"

# Generate LEF for specified block from gds: make lef <gds cellname>
lef:
	@if [ -z "$(filter-out $@,$(MAKECMDGOALS))" ]; then \
		echo "Usage: make lef <cellname>"; \
		echo "This will convert tech/$(PLATFORM)/gds/<cellname>.gds to tech/$(PLATFORM)/lef/<cellname>.lef"; \
		exit 1; \
	fi
	@cellname="$(filter-out $@,$(MAKECMDGOALS))"; \
	if [ ! -f "tech/$(PLATFORM)/gds/$${cellname}.gds" ]; then \
		echo "Error: tech/$(PLATFORM)/gds/$${cellname}.gds not found. Run 'make gds $${cellname}' first."; \
		exit 1; \
	fi; \
	mkdir -p tech/$(PLATFORM)/lef; \
	echo "Converting GDS to LEF for $${cellname}..."; \
	.venv/bin/python src/utils/gds2lef.py "tech/$(PLATFORM)/gds/$${cellname}.gds" "tech/$(PLATFORM)/lef/$${cellname}.lef" "tech/$(PLATFORM)/tsmc65.lyt"

# View a GDS file in KLayout: make view <cellname>
view:
	@if [ -z "$(filter-out $@,$(MAKECMDGOALS))" ]; then \
		echo "Usage: make view <cellname>"; \
		echo "This will open tech/$(PLATFORM)/gds/<cellname>.gds in KLayout"; \
		exit 1; \
	fi
	@cellname="$(filter-out $@,$(MAKECMDGOALS))"; \
	if [ ! -f "tech/$(PLATFORM)/gds/$${cellname}.gds" ]; then \
		echo "Error: tech/$(PLATFORM)/gds/$${cellname}.gds not found. Run 'make gds $${cellname}' first."; \
		exit 1; \
	fi; \
	klayout -nn tech/$(PLATFORM)/$(PLATFORM).lyt -l tech/$(PLATFORM)/$(PLATFORM).lyp "tech/$(PLATFORM)/gds/$${cellname}.gds"

# Export OpenAccess cells to GDS using Cadence strmout
strmout:
	@mkdir -p logs tech/$(PLATFORM)/gds
	@echo "Exporting OpenAccess cells to GDS..."
	@for cell in $(EXPORT_CELLS); do \
		library=$$(echo $$cell | cut -d: -f1); \
		cellname=$$(echo $$cell | cut -d: -f2); \
		output=$$(echo $$cell | cut -d: -f3); \
		echo "Exporting $$library:$$cellname -> $$output.gds"; \
		(cd $(CURDIR)/tech/$(PLATFORM)/cds && . ./workspace.sh && strmout -library "$$library" -strmFile "$(CURDIR)/tech/$(PLATFORM)/gds/$$output.gds" -techLib 'tsmcN65' -topCell "$$cellname" -view 'layout' -logFile "$(CURDIR)/logs/$${output}_strmOut.log" -enableColoring) || exit 1; \
	done
	@echo "GDS export complete. Files saved to tech/$(PLATFORM)/gds/, logs in logs/"

# Export OpenAccess cells to LEF using Cadence lefout
lefout:
	@mkdir -p logs tech/$(PLATFORM)/lef
	@echo "Exporting OpenAccess cells to LEF..."
	@for cell in $(EXPORT_CELLS); do \
		library=$$(echo $$cell | cut -d: -f1); \
		cellname=$$(echo $$cell | cut -d: -f2); \
		output=$$(echo $$cell | cut -d: -f3); \
		echo "Exporting $$library:$$cellname -> $$output.lef"; \
		(cd $(CURDIR)/tech/$(PLATFORM)/cds && . ./workspace.sh && lefout -lef "$(CURDIR)/tech/$(PLATFORM)/lef/$$output.lef" -lib "$$library" -cells "$$cellname" -views "layout" -log "$(CURDIR)/logs/$${output}_lefout.log" -noTech) || exit 1; \
	done
	@echo "LEF export complete. Files saved to tech/$(PLATFORM)/lef/, logs in logs/"

# Export OpenAccess cells to CDL/SPICE using oaschem2spice.py
cdlout:
	@mkdir -p logs tech/$(PLATFORM)/spice
	@echo "Exporting OpenAccess cells to CDL/SPICE..."
	@for cell in $(EXPORT_CELLS); do \
		library=$$(echo $$cell | cut -d: -f1); \
		cellname=$$(echo $$cell | cut -d: -f2); \
		output=$$(echo $$cell | cut -d: -f3); \
		echo "Exporting $$library:$$cellname -> $$output.cdl/.sp"; \
		(cd $(CURDIR)/tech/$(PLATFORM)/cds && . ./workspace.sh && .venv/bin/python $(CURDIR)/src/utils/oaschem2spice.py oa "$$library" "$$cellname" "$$output" && mv "$$output.cdl" "$(CURDIR)/tech/$(PLATFORM)/spice/$$output.cdl" && mv "$$output.sp" "$(CURDIR)/tech/$(PLATFORM)/spice/$$output.sp" && rm -f si.env) || exit 1; \
	done
	@echo "CDL/SPICE export complete. Files saved to tech/$(PLATFORM)/spice/, logs in logs/"

# Run PVS DRC on OpenAccess cells using exported GDS files
pvsdrc:
	@echo "Running PVS DRC on exported GDS files..."
	@for cell in $(EXPORT_CELLS); do \
		library=$$(echo $$cell | cut -d: -f1); \
		cellname=$$(echo $$cell | cut -d: -f2); \
		output=$$(echo $$cell | cut -d: -f3); \
		gds_file="../gds/$$output.gds"; \
		if [ -f "$(CURDIR)/tech/$(PLATFORM)/gds/$$output.gds" ]; then \
			echo "Running PVS DRC on $$output.gds (top cell: $$cellname)"; \
			(cd $(CURDIR)/tech/$(PLATFORM)/cds && . ./workspace.sh && \
			pvs -drc -top_cell "$$cellname" -gds "$$gds_file" -run_dir "$(CURDIR)/logs" -gdsrdb "$(CURDIR)/logs/$${output}_violations.gds" "$(PVS_DRC_RULES)" > /dev/null) || echo "PVS DRC failed for $$output"; \
			echo "=== DRC Results for $$output ==="; \
			if [ -f "$(CURDIR)/logs/DRC_RES.db" ]; then \
				echo "DRC_RES.db:"; \
				cat "$(CURDIR)/logs/DRC_RES.db"; \
			fi; \
			if [ -f "$(CURDIR)/logs/DRC.rep" ]; then \
				echo "Last 6 lines of DRC.rep:"; \
				tail -6 "$(CURDIR)/logs/DRC.rep"; \
			fi; \
		else \
			echo "Warning: GDS file $(CURDIR)/tech/$(PLATFORM)/gds/$$output.gds not found. Run 'make strmout' first."; \
		fi; \
	done
	@echo "PVS DRC complete. Results in logs/"

# View DRC results in KLayout with violation markers
viewdrc:
	@if [ -z "$(filter-out $@,$(MAKECMDGOALS))" ]; then \
		echo "Usage: make viewdrc <output_name>"; \
		echo "Available outputs: comp, sampswitch"; \
		exit 1; \
	fi
	@output="$(filter-out $@,$(MAKECMDGOALS))"; \
	original_gds="tech/$(PLATFORM)/gds/$$output.gds"; \
	violations_gds="logs/$${output}_violations.gds"; \
	if [ -f "$$original_gds" ] && [ -f "$$violations_gds" ]; then \
		echo "Opening $$output design with DRC violations in KLayout..."; \
		klayout -nn tech/$(PLATFORM)/$(PLATFORM).lyt -l tech/$(PLATFORM)/$(PLATFORM).lyp "$$original_gds" "$$violations_gds" & \
	else \
		echo "Missing files for $$output:"; \
		[ ! -f "$$original_gds" ] && echo "  $$original_gds not found - run 'make strmout' first"; \
		[ ! -f "$$violations_gds" ] && echo "  $$violations_gds not found - run 'make pvsdrc' first"; \
		exit 1; \
	fi

# Prevent make from trying to build the argument as a target
%:
	@:

# Run behavioral simulation: make behavioral <run_script>
behavioral:
	@if [ -z "$(filter-out $@,$(MAKECMDGOALS))" ]; then \
		echo "Usage: make behavioral <run_script>"; \
		echo "Available run scripts:"; \
		for script in src/runs/*.py; do \
			if [ -f "$$script" ]; then \
				basename="$$(basename "$$script" .py)"; \
				echo "  $$basename"; \
			fi; \
		done; \
		exit 1; \
	fi
	@run_script="$(filter-out $@,$(MAKECMDGOALS))"; \
	if [ ! -f "src/runs/$${run_script}.py" ]; then \
		echo "Error: src/runs/$${run_script}.py not found"; \
		exit 1; \
	fi; \
	echo "Running behavioral simulation: $${run_script}..."; \
	.venv/bin/python "src/runs/$${run_script}.py"

# Run SPICE simulation: make ngspice <testbench_name>
ngspice:
	@if [ -z "$(filter-out $@,$(MAKECMDGOALS))" ]; then \
		echo "Usage: make ngspice <testbench_name>"; \
		echo "Available testbenches in etc/:"; \
		for tb in etc/tb_*.sp; do \
			if [ -f "$$tb" ]; then \
				basename="$$(basename "$$tb" .sp)"; \
				echo "  $$basename"; \
			fi; \
		done; \
		exit 1; \
	fi
	@tbname="$(filter-out $@,$(MAKECMDGOALS))"; \
	if [ ! -f "etc/$${tbname}.sp" ]; then \
		echo "Error: etc/$${tbname}.sp not found"; \
		echo "Available testbenches:"; \
		for tb in etc/tb_*.sp; do \
			if [ -f "$$tb" ]; then \
				basename="$$(basename "$$tb" .sp)"; \
				echo "  $$basename"; \
			fi; \
		done; \
		exit 1; \
	fi; \
	echo "Running SPICE simulation: $${tbname}..."; \
	cd etc && ngspice -b "$${tbname}.sp"; \
	if [ -f "../src/results/$${tbname}.raw" ]; then \
		echo "Simulation completed. Results saved to src/results/$${tbname}.raw"; \
		ls -lh "../src/results/$${tbname}.raw"; \
	else \
		echo "Warning: Expected output file src/results/$${tbname}.raw not found"; \
	fi

# Help target
help:
	@echo "Available targets:"
	@echo "  setup     - Create Python venv and install dependencies"
	@echo "  all       - Build all targets (default)"
	@echo "  gds <cellname>  - Generate GDS layout file (looks for src/<cellname>.py)"
	@echo "  lef <cellname>  - Generate LEF file from GDS for specified cell"
	@echo "  view <cellname> - Open GDS file in KLayout with tech files"
	@echo "  behavioral <run_script> - Run behavioral simulation (e.g. make behavioral run_oneshot)"
	@echo "  ngspice <tbname> - Run SPICE simulation (e.g. make ngspice tb_adc_full)"
	@echo "  strmout   - Export OpenAccess cells (COMP_LATCH, SAMPLE_SW) to GDS"
	@echo "  lefout    - Export OpenAccess cells (COMP_LATCH, SAMPLE_SW) to LEF"
	@echo "  cdlout    - Export OpenAccess cells (COMP_LATCH, SAMPLE_SW) to CDL/SPICE"
	@echo "  pvsdrc    - Run PVS DRC on exported GDS files"
	@echo "  viewdrc   - View DRC results in KLayout (usage: make viewdrc <output>)"
	@echo "  help      - Show this help message"