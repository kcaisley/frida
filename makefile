# FRIDA Project Makefile


# TODO:
# - remove hardcoded PLATFORM
# - factor sim pdk looping out of makefile, and into python script

# Platform configuration
PLATFORM := tsmc65
TECH_CONFIG := tech/tech.toml

# Python environment
VENV_PYTHON := .venv/bin/python

# Flow scripts
NETLIST_SCRIPT := src/generate_netlists.py
TESTBENCH_SCRIPT := src/generate_testbench.py
SIM_SCRIPT := src/run_simulations.py

# Cadence tools setup
CADENCE_SPECTRE_SETUP := /eda/cadence/2024-25/scripts/SPECTRE_24.10.078_RHELx86.sh
CADENCE_PVS_SETUP := /eda/cadence/2024-25/scripts/PVS_24.10.000_RHELx86.sh

# Spectre simulation configuration
LICENSE_SERVER := 27500@nexus.physik.uni-bonn.de
SPECTRE_PATH := /eda/cadence/2024-25/RHELx86/SPECTRE_24.10.078/bin/spectre

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

# Directory paths
SPICE_DIR := spice
AHDL_DIR := ahdl
RESULTS_DIR := results

# Default target
.PHONY: all gds lef strmout lefout cdlout pvsdrc viewdrc setup netlist clean_netlist testbench clean_testbench sim clean_sim clean_all

# Setup Python virtual environment and install dependencies using uv
setup:
	@if ! command -v uv >/dev/null 2>&1; then \
		echo "uv not found. Installing uv..."; \
		curl -LsSf https://astral.sh/uv/install.sh | sh; \
		echo "uv installed. Please run 'make setup' again or add ~/.local/bin to your PATH"; \
		exit 0; \
	fi
	@echo "Ensuring Python 3.14 is installed..."
	uv python install 3.14
	@echo "Creating Python virtual environment with Python 3.14..."
	uv venv --python 3.14 .venv
	@echo "Installing packages with uv..."
	uv pip install klayout spicelib blosc2 wavedrom PyQt5 numpy matplotlib pandas tqdm jinja2
	@echo "Setup complete! Activate with: source .venv/bin/activate"



# Generate SPICE netlist variants: make netlist <family_cellname>
netlist:
	@if [ -z "$(filter-out $@,$(MAKECMDGOALS))" ]; then \
		echo "Usage: make netlist <family_cellname>"; \
		echo "This will generate netlists from $(SPICE_DIR)/<family_cellname>.sp and $(SPICE_DIR)/<family_cellname>.toml"; \
		echo "Examples:"; \
		echo "  make netlist samp_tgate"; \
		echo "  make netlist comp_doubletail"; \
		exit 1; \
	fi
	@family_cellname="$(filter-out $@,$(MAKECMDGOALS))"; \
	template="$(SPICE_DIR)/$${family_cellname}.sp"; \
	params="$(SPICE_DIR)/$${family_cellname}.toml"; \
	outdir="$(RESULTS_DIR)/$${family_cellname}"; \
	if [ ! -f "$${template}" ]; then \
		echo "Error: Template $${template} not found"; \
		exit 1; \
	fi; \
	if [ ! -f "$${params}" ]; then \
		echo "Error: Parameters $${params} not found"; \
		exit 1; \
	fi; \
	echo "Generating netlists for $${family_cellname}"; \
	$(VENV_PYTHON) $(NETLIST_SCRIPT) \
		--template="$${template}" \
		--params="$${params}" \
		--config="$(TECH_CONFIG)" \
		--outdir="$${outdir}"

# Clean generated netlists: make clean_netlist <family_cellname>
clean_netlist:
	@if [ -z "$(filter-out $@,$(MAKECMDGOALS))" ]; then \
		echo "Usage: make clean_netlist <family_cellname>"; \
		echo "This will remove $(RESULTS_DIR)/<family_cellname>/ directory"; \
		echo "Examples:"; \
		echo "  make clean_netlist samp_tgate"; \
		echo "  make clean_netlist comp_doubletail"; \
		exit 1; \
	fi
	@family_cellname="$(filter-out $@,$(MAKECMDGOALS))"; \
	outdir="$(RESULTS_DIR)/$${family_cellname}"; \
	if [ -d "$${outdir}" ]; then \
		echo "Removing $${outdir}..."; \
		rm -rf "$${outdir}"; \
		echo "Cleaned netlists for $${family_cellname}"; \
	else \
		echo "Directory $${outdir} does not exist, nothing to clean"; \
	fi

# Generate testbench wrappers: make testbench <family_cellname> [corner=tt]
testbench:
	@if [ -z "$(filter-out $@,$(MAKECMDGOALS))" ]; then \
		echo "Usage: make testbench <family_cellname> [corner=<corner>]"; \
		echo "This will generate testbench wrappers for DUT netlists in $(RESULTS_DIR)/<family_cellname>/"; \
		echo "Examples:"; \
		echo "  make testbench samp_tgate"; \
		echo "  make testbench samp_tgate corner=ss"; \
		echo "  make testbench comp_doubletail corner=ff"; \
		exit 1; \
	fi
	@family_cellname="$(filter-out $@,$(MAKECMDGOALS))"; \
	familyname=$$(echo "$$family_cellname" | cut -d'_' -f1); \
	netlists="$(RESULTS_DIR)/$${family_cellname}/$${family_cellname}_*.sp"; \
	outdir="$(RESULTS_DIR)/$${family_cellname}"; \
	corner_select="$(corner)"; \
	testbench="$(AHDL_DIR)/tb_$${familyname}.va"; \
	if [ ! -f "$$testbench" ]; then \
		echo "Error: Verilog-A testbench $$testbench not found"; \
		exit 1; \
	fi; \
	if [ ! -d "$${outdir}" ]; then \
		echo "Error: Directory $${outdir} not found. Run 'make netlist $${family_cellname}' first."; \
		exit 1; \
	fi; \
	if [ -z "$$corner_select" ]; then \
		corner_select="tt"; \
	fi; \
	echo "Generating testbench wrappers for $${family_cellname} (corner: $$corner_select)..."; \
	$(VENV_PYTHON) $(TESTBENCH_SCRIPT) \
		--netlists="$$netlists" \
		--verilog-a="$$testbench" \
		--config="$(TECH_CONFIG)" \
		--corner="$$corner_select"

# Clean testbench wrappers: make clean_testbench <family_cellname>
clean_testbench:
	@if [ -z "$(filter-out $@,$(MAKECMDGOALS))" ]; then \
		echo "Usage: make clean_testbench <family_cellname>"; \
		echo "This will remove testbench wrappers (tb_*.sp) from $(RESULTS_DIR)/<family_cellname>/"; \
		echo "Examples:"; \
		echo "  make clean_testbench samp_tgate"; \
		echo "  make clean_testbench comp_doubletail"; \
		exit 1; \
	fi
	@family_cellname="$(filter-out $@,$(MAKECMDGOALS))"; \
	outdir="$(RESULTS_DIR)/$${family_cellname}"; \
	if [ -d "$${outdir}" ]; then \
		echo "Removing testbench wrappers from $${outdir}..."; \
		rm -f "$${outdir}"/tb_*.sp; \
		echo "Cleaned testbench wrappers for $${family_cellname}"; \
	else \
		echo "Directory $${outdir} does not exist, nothing to clean"; \
	fi

# Run batch Spectre simulations: make sim <family_cellname> [tech=<tech>]
sim:
	@if [ -z "$(filter-out $@,$(MAKECMDGOALS))" ]; then \
		echo "Usage: make sim <family_cellname> [tech=<tech>]"; \
		echo "This will run Spectre simulations for testbench wrappers in $(RESULTS_DIR)/<family_cellname>/"; \
		echo "Note: Run 'make testbench <family_cellname>' first to generate testbench wrappers"; \
		echo "Examples:"; \
		echo "  make sim samp_tgate"; \
		echo "  make sim samp_tgate tech=tsmc65"; \
		echo "  make sim comp_doubletail tech=tsmc28"; \
		exit 1; \
	fi
	@family_cellname="$(filter-out $@,$(MAKECMDGOALS))"; \
	dut_netlists="$(RESULTS_DIR)/$${family_cellname}/$${family_cellname}_*.sp"; \
	tb_wrappers="$(RESULTS_DIR)/$${family_cellname}/tb_$${family_cellname}_*.sp"; \
	outdir="$(RESULTS_DIR)/$${family_cellname}"; \
	tech_filter="$(tech)"; \
	if [ ! -d "$${outdir}" ]; then \
		echo "Error: Directory $${outdir} not found. Run 'make netlist $${family_cellname}' first."; \
		exit 1; \
	fi; \
	echo "Running Spectre simulations for $${family_cellname}..."; \
	export CDS_LIC_FILE="$(LICENSE_SERVER)"; \
	. $(CADENCE_SPECTRE_SETUP); \
	. $(CADENCE_PVS_SETUP); \
	$(VENV_PYTHON) $(SIM_SCRIPT) \
		--dut-netlists="$$dut_netlists" \
		--tb-wrappers="$$tb_wrappers" \
		--outdir="$$outdir" \
		--tech-filter="$$tech_filter" \
		--license-server="$(LICENSE_SERVER)" \
		--spectre-path="$(SPECTRE_PATH)" </dev/null

# View waveforms interactively: make waveform <family_cellname>
waveform:
	@if [ -z "$(filter-out $@,$(MAKECMDGOALS))" ]; then \
		echo "Usage: make waveform <family_cellname>"; \
		echo "This will launch an interactive waveform viewer for simulation results in $(RESULTS_DIR)/<family_cellname>/"; \
		echo "Note: Run 'make sim <family_cellname>' first to generate .raw files"; \
		echo "Examples:"; \
		echo "  make waveform samp_tgate"; \
		echo "  make waveform comp_doubletail"; \
		exit 1; \
	fi
	@family_cellname="$(filter-out $@,$(MAKECMDGOALS))"; \
	outdir="$(RESULTS_DIR)/$${family_cellname}"; \
	if [ ! -d "$${outdir}" ]; then \
		echo "Error: Directory $${outdir} not found. Run 'make sim $${family_cellname}' first."; \
		exit 1; \
	fi; \
	raw_count=$$(find "$${outdir}" -name "*.raw" -type f 2>/dev/null | wc -l); \
	if [ "$$raw_count" -eq 0 ]; then \
		echo "Error: No .raw files found in $${outdir}. Run 'make sim $${family_cellname}' first."; \
		exit 1; \
	fi; \
	echo "Launching waveform viewer for $${family_cellname} ($$raw_count .raw files)..."; \
	$(VENV_PYTHON) src/plot_waveforms.py "$${family_cellname}"

# Clean simulation results: make clean_sim <family_cellname>
clean_sim:
	@if [ -z "$(filter-out $@,$(MAKECMDGOALS))" ]; then \
		echo "Usage: make clean_sim <family_cellname>"; \
		echo "This will remove simulation results (*.log, *.raw, *.scs files) from $(RESULTS_DIR)/<family_cellname>/"; \
		echo "Examples:"; \
		echo "  make clean_sim samp_tgate"; \
		echo "  make clean_sim comp_doubletail"; \
		exit 1; \
	fi
	@family_cellname="$(filter-out $@,$(MAKECMDGOALS))"; \
	outdir="$(RESULTS_DIR)/$${family_cellname}"; \
	if [ -d "$${outdir}" ]; then \
		echo "Cleaning simulation results from $${outdir}..."; \
		rm -f "$${outdir}"/*.log "$${outdir}"/*.raw "$${outdir}"/*.scs "$${outdir}"/batch_sim_*.log "$${outdir}"/netlist_gen_*.log "$${outdir}"/*.error; \
		find "$${outdir}" -name "*.ahdlSimDB" -type d -exec rm -rf {} + 2>/dev/null || true; \
		echo "Cleaned simulation results for $${family_cellname}"; \
	else \
		echo "Directory $${outdir} does not exist, nothing to clean"; \
	fi

# Clean everything: make clean_all <family_cellname>
clean_all:
	@if [ -z "$(filter-out $@,$(MAKECMDGOALS))" ]; then \
		echo "Usage: make clean_all <family_cellname>"; \
		echo "This will remove testbench wrappers, simulation results, and netlists"; \
		echo "Examples:"; \
		echo "  make clean_all samp_tgate"; \
		echo "  make clean_all comp_doubletail"; \
		exit 1; \
	fi
	@family_cellname="$(filter-out $@,$(MAKECMDGOALS))"; \
	echo "Cleaning all generated files for $${family_cellname}..."; \
	$(MAKE) -s clean_sim $${family_cellname}; \
	$(MAKE) -s clean_testbench $${family_cellname}; \
	$(MAKE) -s clean_netlist $${family_cellname}; \
	echo "All generated files cleaned for $${family_cellname}"

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

# Help target
help:
	@echo "Available targets:"
	@echo "  setup     - Create Python venv and install dependencies"
	@echo "  all       - Build all targets (default)"
	@echo "  gds <cellname>       - Generate GDS layout file (looks for src/<cellname>.py)"
	@echo "  lef <cellname>       - Generate LEF file from GDS for specified cell"
	@echo "  netlist <comp>       - Generate SPICE netlist variants (e.g. make netlist comp_doubletail)"
	@echo "  clean_netlist <comp> - Remove generated netlists (e.g. make clean_netlist comp_doubletail)"
	@echo "  testbench <comp> [corner=<corner>] - Generate testbench wrappers (e.g. make testbench samp_tgate corner=ss)"
	@echo "  clean_testbench <comp> - Remove testbench wrappers (e.g. make clean_testbench samp_tgate)"
	@echo "  sim <comp> [tech=<tech>] - Run batch Spectre simulations (auto-calculates workers)"
	@echo "                         (e.g. make sim comp_doubletail tech=tsmc65)"
	@echo "  clean_sim <comp>     - Clean simulation results (logs, raw files, etc)"
	@echo "  clean_all <comp>     - Clean everything (netlists, testbenches, simulation results)"
	@echo "  view <cellname>      - Open GDS file in KLayout with tech files"
	@echo "  behavioral <run_script> - Run behavioral simulation (e.g. make behavioral run_oneshot)"
	@echo "  ngspice <tbname>  - Run SPICE simulation (e.g. make ngspice tb_adc_full)"
	@echo "  strmout   - Export OpenAccess cells (COMP_LATCH, SAMPLE_SW) to GDS"
	@echo "  lefout    - Export OpenAccess cells (COMP_LATCH, SAMPLE_SW) to LEF"
	@echo "  cdlout    - Export OpenAccess cells (COMP_LATCH, SAMPLE_SW) to CDL/SPICE"
	@echo "  pvsdrc    - Run PVS DRC on exported GDS files"
	@echo "  viewdrc   - View DRC results in KLayout (usage: make viewdrc <output>)"
	@echo "  completion - Enable bash TAB completion for make commands"
	@echo "  help      - Show this help message"

# Catch-all pattern rule to prevent make from treating arguments as targets
%:
	@:
