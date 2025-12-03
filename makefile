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

# Directory paths
SPICE_DIR := spice
AHDL_DIR := ahdl
RESULTS_DIR := results

# Default target
.PHONY: all setup netlist clean_netlist testbench clean_testbench sim clean_sim clean_all

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
	uv pip install klayout spicelib blosc2 wavedrom PyQt5 numpy matplotlib pandas tqdm jinja2 ipympl
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
		--spectre-path="$(SPECTRE_PATH)" \
		--raw-format=nutascii </dev/null

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
		find "$${outdir}" -name "*.ns@*" -exec rm -rf {} + 2>/dev/null || true; \
		find "$${outdir}" -name "*.psf" -type d -exec rm -rf {} + 2>/dev/null || true; \
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

# Catch-all pattern rule to prevent make from treating arguments as targets
%:
	@:
