# Configuration
VENV_PYTHON := PYTHONPATH=. .venv/bin/python
RESULTS_DIR := results
NETLIST_SCRIPT := flow/netlist.py
SIM_SCRIPT := flow/simulate.py
MEAS_SCRIPT := flow/measure.py

# Quiet mode: suppress command echo unless debug=1
ifeq ($(filter 1,$(debug)),)
  Q := @
  MAKEFLAGS += --no-print-directory
else
  Q :=
endif
# Cadence tools
CADENCE_SPECTRE_SETUP := /eda/cadence/2024-25/scripts/SPECTRE_24.10.078_RHELx86.sh
CADENCE_IC_SETUP := /eda/cadence/2024-25/scripts/IC_23.10.070_RHELx86.sh
CADENCE_PVS_SETUP := /eda/cadence/2024-25/scripts/PVS_24.10.000_RHELx86.sh
LICENSE_SERVER := 27500@nexus.physik.uni-bonn.de
SPECTRE_PATH := /eda/cadence/2024-25/RHELx86/SPECTRE_24.10.078/bin/spectre

.PHONY: setup check subckt clean_subckt tb clean_tb sim clean_sim meas clean_meas clean_plot all clean_all slides clean_slides help

# ============================================================
# Setup and Maintenance
# ============================================================

setup:
	@if ! command -v uv >/dev/null 2>&1; then \
		curl -LsSf https://astral.sh/uv/install.sh | sh; \
		echo "uv installed. Run 'make setup' again."; exit 0; \
	fi
	uv python install 3.11
	uv venv --clear --python 3.11 .venv
	uv pip install numpy matplotlib scipy klayout spicelib schemdraw PyQt5
	uv pip install https://fides.fe.uni-lj.si/pyopus/download/0.11.2/PyOPUS-0.11.2-cp311-cp311-linux_x86_64.whl
	@echo "Setup complete: .venv created with necessary packages"

check:
	@$(VENV_PYTHON) -c "import sys; from flow.common import check_all_cells; sys.exit(check_all_cells(cells='$(cell)'))"

lint:
	@echo "=== Running ruff ==="
	uvx ruff check flow blocks
	@echo ""
	@echo "=== Running ty ==="
	uvx ty check flow blocks
	@echo ""
	@echo "=== Running basedpyright ==="
	uvx basedpyright flow blocks --level error
# ============================================================
# Netlist Generation (subckt and tb)
# ============================================================

subckt:
ifndef cell
	$(error Usage: make subckt cell=<cellname>)
endif
	$(Q)if [ ! -f "blocks/$(cell).py" ]; then echo "Error: blocks/$(cell).py not found"; exit 1; fi
	$(Q)$(VENV_PYTHON) $(NETLIST_SCRIPT) subckt "blocks/$(cell).py" -o "$(RESULTS_DIR)" $(if $(filter 1,$(debug)),--debug)

clean_subckt:
ifdef cell
	$(Q)rm -rf "$(RESULTS_DIR)/$(cell)/subckt"
	$(Q)echo "Cleaned: $(RESULTS_DIR)/$(cell)/subckt"
else
	$(Q)rm -rf $(RESULTS_DIR)/*/subckt
	$(Q)echo "Cleaned: all subckt directories"
endif

tb:
ifndef cell
	$(error Usage: make tb cell=<cellname>)
endif
	$(Q)if [ ! -f "blocks/$(cell).py" ]; then echo "Error: blocks/$(cell).py not found"; exit 1; fi
	$(Q)$(VENV_PYTHON) $(NETLIST_SCRIPT) tb "blocks/$(cell).py" -o "$(RESULTS_DIR)" $(if $(filter 1,$(debug)),--debug)

clean_tb:
ifdef cell
	$(Q)rm -rf "$(RESULTS_DIR)/$(cell)/tb"
	$(Q)echo "Cleaned: $(RESULTS_DIR)/$(cell)/tb"
else
	$(Q)rm -rf $(RESULTS_DIR)/*/tb
	$(Q)echo "Cleaned: all tb directories"
endif

# ============================================================
# Simulation
# ============================================================

# Remote configuration
REMOTE_HOST := juno.physik.uni-bonn.de
REMOTE_USER := kcaisley
REMOTE_PROJECT := /local/kcaisley/frida
REMOTE_VENV := $(REMOTE_PROJECT)/.venv/bin/python
NUM_PROCS := 40

# Hosts that have Spectre installed (run locally on these)
SPECTRE_HOSTS := juno jupiter

# Detect current hostname (strip domain)
CURRENT_HOST := $(shell hostname -s)

# Check if current host has Spectre
HAS_SPECTRE := $(filter $(CURRENT_HOST),$(SPECTRE_HOSTS))

# Simulation
# Usage: make sim cell=<cellname> mode=<dryrun|single|all>
# Automatically runs remotely if current host doesn't have Spectre
sim:
ifndef cell
	$(error Usage: make sim cell=<cellname> mode=<dryrun|single|all>)
endif
ifndef mode
	$(error Usage: make sim cell=<cellname> mode=<dryrun|single|all>)
endif
	$(Q)if [ ! -d "$(RESULTS_DIR)/$(cell)/subckt" ]; then echo "Error: Run 'make subckt cell=$(cell)' first"; exit 1; fi
	$(Q)if [ ! -d "$(RESULTS_DIR)/$(cell)/tb" ]; then echo "Error: Run 'make tb cell=$(cell)' first"; exit 1; fi
ifneq ($(HAS_SPECTRE),)
	$(Q)$(VENV_PYTHON) $(SIM_SCRIPT) $(cell) -o $(RESULTS_DIR) --mode $(mode) -j $(NUM_PROCS) $(if $(tech),--tech=$(tech)) $(if $(filter 1,$(debug)),--debug)
else
	$(Q)rsync -az --mkpath flow/ $(REMOTE_USER)@$(REMOTE_HOST):$(REMOTE_PROJECT)/flow/
	$(Q)rsync -az --mkpath blocks/ $(REMOTE_USER)@$(REMOTE_HOST):$(REMOTE_PROJECT)/blocks/
	$(Q)rsync -az makefile $(REMOTE_USER)@$(REMOTE_HOST):$(REMOTE_PROJECT)/makefile
	$(Q)rsync -az --mkpath --delete $(RESULTS_DIR)/$(cell)/ $(REMOTE_USER)@$(REMOTE_HOST):$(REMOTE_PROJECT)/$(RESULTS_DIR)/$(cell)/
	@# The - prefix ignores exit status so we can sync results back even if simulation fails
	$(Q)-ssh $(REMOTE_USER)@$(REMOTE_HOST) "\
		cd $(REMOTE_PROJECT) && \
		export CDS_LIC_FILE=$(LICENSE_SERVER) && \
		source $(CADENCE_SPECTRE_SETUP) && \
		source $(CADENCE_IC_SETUP) && \
		source $(CADENCE_PVS_SETUP) && \
		PYTHONPATH=. $(REMOTE_VENV) $(SIM_SCRIPT) $(cell) -o $(RESULTS_DIR) --mode $(mode) -j $(NUM_PROCS) $(if $(tech),--tech=$(tech)) $(if $(filter 1,$(debug)),--debug)"
	$(Q)rsync -az $(REMOTE_USER)@$(REMOTE_HOST):$(REMOTE_PROJECT)/$(RESULTS_DIR)/$(cell)/sim/ $(RESULTS_DIR)/$(cell)/sim/
	$(Q)rsync -az $(REMOTE_USER)@$(REMOTE_HOST):$(REMOTE_PROJECT)/$(RESULTS_DIR)/$(cell)/files.json $(RESULTS_DIR)/$(cell)/files.json
ifeq ($(debug),1)
	@echo "=== Simulation log ==="
	@cat $(RESULTS_DIR)/$(cell)/sim/*.log 2>/dev/null || echo "No log file found"
endif
endif

clean_sim:
ifdef cell
	$(Q)rm -rf "$(RESULTS_DIR)/$(cell)/sim"
	$(Q)echo "Cleaned: $(RESULTS_DIR)/$(cell)/sim"
else
	$(Q)rm -rf $(RESULTS_DIR)/*/sim
	$(Q)echo "Cleaned: all sim directories"
endif

# ============================================================
# Measurement and Plotting (combined in measure.py)
# ============================================================

meas:
ifndef cell
	$(error Usage: make meas cell=<cellname> [tech=<tech>] [corner=<corner>] [temp=<temp>] [no_plot=1])
endif
	$(Q)if [ ! -d "$(RESULTS_DIR)/$(cell)/sim" ]; then echo "Error: Run 'make sim cell=$(cell)' first"; exit 1; fi
	$(Q)$(VENV_PYTHON) $(MEAS_SCRIPT) $(cell) -o "$(RESULTS_DIR)" $(if $(tech),--tech=$(tech)) $(if $(corner),--corner=$(corner)) $(if $(temp),--temp=$(temp)) $(if $(no_plot),--no-plot) $(if $(filter 1,$(debug)),--debug)

clean_meas:
ifdef cell
	$(Q)rm -rf "$(RESULTS_DIR)/$(cell)/meas"
	$(Q)echo "Cleaned: $(RESULTS_DIR)/$(cell)/meas"
else
	$(Q)rm -rf $(RESULTS_DIR)/*/meas
	$(Q)echo "Cleaned: all meas directories"
endif

clean_plot:
ifdef cell
	$(Q)rm -rf "$(RESULTS_DIR)/$(cell)/plot"
	$(Q)echo "Cleaned: $(RESULTS_DIR)/$(cell)/plot"
else
	$(Q)rm -rf $(RESULTS_DIR)/*/plot
	$(Q)echo "Cleaned: all plot directories"
endif

# ============================================================
# Full Flow
# ============================================================

# Usage: make all cell=<cellname> [mode=single|all] [debug=1]
# Defaults: mode=single
# Automatically uses remote if current host doesn't have Spectre
all:
ifndef cell
	$(error Usage: make all cell=<cellname> [mode=single|all] [debug=1])
endif
	$(Q)$(MAKE) clean_all cell=$(cell) $(if $(filter 1,$(debug)),debug=1)
	$(Q)$(MAKE) subckt cell=$(cell) $(if $(filter 1,$(debug)),debug=1)
	$(Q)$(MAKE) tb cell=$(cell) $(if $(filter 1,$(debug)),debug=1)
	$(Q)$(MAKE) sim cell=$(cell) mode=$(or $(mode),single) $(if $(filter 1,$(debug)),debug=1)
	$(Q)$(MAKE) meas cell=$(cell) $(if $(filter 1,$(debug)),debug=1)

clean_all:
ifdef cell
	$(Q)rm -rf "$(RESULTS_DIR)/$(cell)"
else
	$(Q)rm -rf $(RESULTS_DIR)/*
endif

# ============================================================
# Documentation / Slides
# ============================================================

TEXLIVE_BIN := /usr/local/texlive/2025/bin/x86_64-linux
XELATEX := $(TEXLIVE_BIN)/xelatex

slides:
	$(Q)cd docs && $(XELATEX) -interaction=nonstopmode -shell-escape -output-directory=tex design_review.tex
	@echo "Created docs/tex/design_review.pdf"

clean_slides:
	$(Q)rm -f docs/tex/*.aux docs/tex/*.log docs/tex/*.out docs/tex/*.nav docs/tex/*.snm docs/tex/*.toc docs/tex/*.vrb docs/tex/design_review.pdf
	@echo "Cleaned: docs/tex slide artifacts"

# ============================================================
# Help
# ============================================================

help:
	@echo "Frida Circuit Design Flow"
	@echo ""
	@echo "Usage: make <target> cell=<cellname> [options]"
	@echo ""
	@echo "Targets:"
	@echo "  subckt        Generate subcircuit netlists"
	@echo "  tb            Generate testbench netlists"
	@echo "  sim           Run simulations (saves .pkl files)"
	@echo "  meas          Extract measurements and generate plots"
	@echo "  all           Run full flow (clean -> subckt -> tb -> sim -> meas)"
	@echo ""
	@echo "Documentation:"
	@echo "  slides        Build presentation slides (docs/tex/)"
	@echo ""
	@echo "Clean targets:"
	@echo "  clean_subckt  Remove subcircuit files"
	@echo "  clean_tb      Remove testbench files"
	@echo "  clean_sim     Remove simulation results"
	@echo "  clean_meas    Remove measurement results"
	@echo "  clean_plot    Remove plot files"
	@echo "  clean_slides  Remove slide build artifacts"
	@echo "  clean_all     Remove all results for cell"
	@echo ""
	@echo "Options:"
	@echo "  cell=<name>   Cell name (required for most targets)"
	@echo "  mode=<mode>   Simulation mode: dryrun, single, all (required for sim)"
	@echo "  tech=<tech>   Filter by technology (tsmc65, tsmc28, tower180)"
	@echo "  corner=<c>    Filter by corner (tt, ss, ff, sf, fs)"
	@echo "  temp=<t>      Filter by temperature (27, etc.)"
	@echo "  no_plot=1     Skip plot generation in meas target"
	@echo "  debug=1       Enable debug logging for sim/meas"
	@echo "  NUM_PROCS=N   Number of parallel processes (default: 40)"
	@echo ""
	@echo "Simulation auto-detects host:"
	@echo "  Runs locally on: $(SPECTRE_HOSTS)"
	@echo "  Otherwise SSHs to $(REMOTE_HOST)"
	@echo ""
	@echo "Simulation examples:"
	@echo "  make sim cell=comp mode=dryrun    # Show what would be simulated"
	@echo "  make sim cell=comp mode=single    # Run one sim (auto local/remote)"
	@echo "  make sim cell=comp mode=all       # Run all sims (auto local/remote)"
	@echo ""
	@echo "Other examples:"
	@echo "  make subckt cell=comp"
	@echo "  make tb cell=comp"
	@echo "  make meas cell=comp"
	@echo "  make meas cell=comp no_plot=1     # Measurements only"
	@echo ""
	@echo "Full flow examples:"
	@echo "  make all cell=comp                # clean+subckt+tb+sim(single)+meas with debug"
	@echo "  make all cell=comp mode=all       # Run all sims"
	@echo "  make all cell=comp debug=0        # Without debug output"
