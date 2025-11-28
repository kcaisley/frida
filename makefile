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

# Netlist generation configuration
SPICE_DIR := spice
AHDL_DIR := ahdl
TECH_CONFIG := $(SPICE_DIR)/generate_netlists.toml
RESULTS_DIR := results
NETLIST_GEN := src/generate_netlists.py

# Default target
.PHONY: all gds lef strmout lefout cdlout pvsdrc viewdrc setup netlist clean_netlist sim clean_sim

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
	.venv/bin/python $(NETLIST_GEN) \
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

# Run batch Spectre simulations: make sim <family_cellname> [tech=tsmc65] [workers=4] [corner=tt]
sim:
	@if [ -z "$(filter-out $@,$(MAKECMDGOALS))" ]; then \
		echo "Usage: make sim <family_cellname> [tech=<tech>] [workers=<N>] [corner=<corner>]"; \
		echo "This will run Spectre simulations for all netlists in $(RESULTS_DIR)/<family_cellname>/"; \
		echo "Uses testbench tb_<family>.sp and tb_<family>.va based on component family"; \
		echo "Examples:"; \
		echo "  make sim samp_tgate"; \
		echo "  make sim samp_pmos tech=tsmc65"; \
		echo "  make sim comp_doubletail tech=tsmc65 workers=8"; \
		echo "  make sim samp_tgate tech=tsmc65 corner=ss"; \
		exit 1; \
	fi
	@family_cellname="$(filter-out $@,$(MAKECMDGOALS))"; \
	familyname=$$(echo "$$family_cellname" | cut -d'_' -f1); \
	cellname=$$(echo "$$family_cellname" | cut -d'_' -f2-); \
	netlists="$(RESULTS_DIR)/$${family_cellname}/*.sp"; \
	outdir="$(RESULTS_DIR)/$${family_cellname}"; \
	tech_filter="$(tech)"; \
	corner_select="$(corner)"; \
	max_workers="$(workers)"; \
	template="$(SPICE_DIR)/tb_$${familyname}.sp"; \
	testbench="$(AHDL_DIR)/tb_$${familyname}.va"; \
	if [ ! -f "$$template" ]; then \
		echo "Error: Testbench template $$template not found"; \
		exit 1; \
	fi; \
	if [ ! -f "$$testbench" ]; then \
		echo "Error: Verilog-A testbench $$testbench not found"; \
		exit 1; \
	fi; \
	if [ -z "$$tech_filter" ]; then \
		tech_filter="tsmc65"; \
	fi; \
	pdk=$$(python3 -c "import tomllib; f=open('$(TECH_CONFIG)', 'rb'); cfg=tomllib.load(f); print(cfg['$$tech_filter']['pdk_path'])" 2>/dev/null); \
	if [ -z "$$pdk" ]; then \
		echo "Error: Could not find pdk_path for tech '$$tech_filter' in $(TECH_CONFIG)"; \
		exit 1; \
	fi; \
	if [ ! -d "$${outdir}" ]; then \
		echo "Error: Directory $${outdir} not found. Run 'make netlist $${family_cellname}' first."; \
		exit 1; \
	fi; \
	corner_arg=""; \
	if [ -n "$$corner_select" ]; then \
		corner_arg="--corner=$$corner_select"; \
	fi; \
	if [ -n "$$tech_filter" ]; then \
		if [ -n "$$max_workers" ]; then \
			echo "Running Spectre simulations for $${family_cellname} (filtered: $$tech_filter, workers: $$max_workers)"; \
			.venv/bin/python src/run_simulations.py \
				--template="$$template" \
				--testbench="$$testbench" \
				--netlists="$$netlists" \
				--pdk="$$pdk" \
				--outdir="$$outdir" \
				--max-workers=$$max_workers \
				--filter="$$tech_filter" $$corner_arg </dev/null; \
		else \
			echo "Running Spectre simulations for $${family_cellname} (filtered: $$tech_filter, auto workers)"; \
			.venv/bin/python src/run_simulations.py \
				--template="$$template" \
				--testbench="$$testbench" \
				--netlists="$$netlists" \
				--pdk="$$pdk" \
				--outdir="$$outdir" \
				--filter="$$tech_filter" $$corner_arg </dev/null; \
		fi; \
	else \
		if [ -n "$$max_workers" ]; then \
			echo "Running Spectre simulations for $${family_cellname} (workers: $$max_workers)"; \
			.venv/bin/python src/run_simulations.py \
				--template="$$template" \
				--testbench="$$testbench" \
				--netlists="$$netlists" \
				--pdk="$$pdk" \
				--outdir="$$outdir" \
				--max-workers=$$max_workers $$corner_arg </dev/null; \
		else \
			echo "Running Spectre simulations for $${family_cellname} (auto workers)"; \
			.venv/bin/python src/run_simulations.py \
				--template="$$template" \
				--testbench="$$testbench" \
				--netlists="$$netlists" \
				--pdk="$$pdk" \
				--outdir="$$outdir" $$corner_arg </dev/null; \
		fi; \
	fi

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
		rm -f "$${outdir}"/*.log "$${outdir}"/*.raw "$${outdir}"/*.scs "$${outdir}"/batch_sim_*.log "$${outdir}"/netlist_gen_*.log; \
		find "$${outdir}" -name "*.ahdlSimDB" -type d -exec rm -rf {} + 2>/dev/null || true; \
		echo "Cleaned simulation results for $${family_cellname}"; \
	else \
		echo "Directory $${outdir} does not exist, nothing to clean"; \
	fi

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

# Prevent make from trying to build the argument as a target
%:
	@:

# Help target
help:
	@echo "Available targets:"
	@echo "  setup     - Create Python venv and install dependencies"
	@echo "  all       - Build all targets (default)"
	@echo "  gds <cellname>       - Generate GDS layout file (looks for src/<cellname>.py)"
	@echo "  lef <cellname>       - Generate LEF file from GDS for specified cell"
	@echo "  netlist <comp>       - Generate SPICE netlist variants (e.g. make netlist comp_doubletail)"
	@echo "  clean_netlist <comp> - Remove generated netlists (e.g. make clean_netlist comp_doubletail)"
	@echo "  sim <comp> [tech=<tech>] [workers=<N>] - Run batch Spectre simulations"
	@echo "                         (e.g. make sim comp_doubletail tech=tsmc65 workers=4)"
	@echo "  clean_sim <comp>     - Clean simulation results (logs, raw files, etc)"
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

# Dummy target to prevent make from treating arguments as targets
%:
	@:
