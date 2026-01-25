# Configuration
VENV_PYTHON := PYTHONPATH=. .venv/bin/python
RESULTS_DIR := results
NETLIST_SCRIPT := flow/netlist.py
SIM_SCRIPT := flow/simulate.py
MEAS_SCRIPT := flow/measure.py
PLOT_SCRIPT := flow/plot.py
# Cadence tools
CADENCE_SPECTRE_SETUP := /eda/cadence/2024-25/scripts/SPECTRE_24.10.078_RHELx86.sh
CADENCE_PVS_SETUP := /eda/cadence/2024-25/scripts/PVS_24.10.000_RHELx86.sh
LICENSE_SERVER := 27500@nexus.physik.uni-bonn.de
SPECTRE_PATH := /eda/cadence/2024-25/RHELx86/SPECTRE_24.10.078/bin/spectre

.PHONY: setup check subckt clean_subckt tb clean_tb sim clean_sim meas clean_meas plot clean_plot all clean_all

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
    uvx basedpyright blocks
    uvx basedpyright flow
# ============================================================
# Netlist Generation (subckt and tb)
# ============================================================

subckt:
ifndef cell
	$(error Usage: make subckt cell=<cellname>)
endif
	@if [ ! -f "blocks/$(cell).py" ]; then echo "Error: blocks/$(cell).py not found"; exit 1; fi
	$(VENV_PYTHON) $(NETLIST_SCRIPT) subckt "blocks/$(cell).py" -o "$(RESULTS_DIR)"

clean_subckt:
ifdef cell
	rm -rf "$(RESULTS_DIR)/$(cell)/subckt"
	@echo "Cleaned: $(RESULTS_DIR)/$(cell)/subckt"
else
	rm -rf $(RESULTS_DIR)/*/subckt
	@echo "Cleaned: all subckt directories"
endif

tb:
ifndef cell
	$(error Usage: make tb cell=<cellname>)
endif
	@if [ ! -f "blocks/$(cell).py" ]; then echo "Error: blocks/$(cell).py not found"; exit 1; fi
	$(VENV_PYTHON) $(NETLIST_SCRIPT) tb "blocks/$(cell).py" -o "$(RESULTS_DIR)"

clean_tb:
ifdef cell
	rm -rf "$(RESULTS_DIR)/$(cell)/tb"
	@echo "Cleaned: $(RESULTS_DIR)/$(cell)/tb"
else
	rm -rf $(RESULTS_DIR)/*/tb
	@echo "Cleaned: all tb directories"
endif

# ============================================================
# Simulation (remote execution on juno)
# ============================================================

# Remote configuration
REMOTE_HOST := juno.physik.uni-bonn.de
REMOTE_USER := kcaisley
REMOTE_PROJECT := /local/kcaisley/frida
REMOTE_VENV := $(REMOTE_PROJECT)/.venv/bin/python
NUM_PROCS := 40

# Simulation: rsync code to juno, run parallel simulations, rsync results back
# Use host=dryrun to generate input files locally without running simulator
sim:
ifndef cell
	$(error Usage: make sim cell=<cellname> [tech=<tech>] [host=dryrun])
endif
	@if [ ! -d "$(RESULTS_DIR)/$(cell)/subckt" ]; then echo "Error: Run 'make subckt cell=$(cell)' first"; exit 1; fi
	@if [ ! -d "$(RESULTS_DIR)/$(cell)/tb" ]; then echo "Error: Run 'make tb cell=$(cell)' first"; exit 1; fi
ifeq ($(host),dryrun)
	@echo "=== DRYRUN MODE: Generating input files only ==="
	$(VENV_PYTHON) $(SIM_SCRIPT) $(cell) -o $(RESULTS_DIR) --dryrun $(if $(tech),--tech=$(tech))
else
	@echo "=== Syncing to $(REMOTE_HOST) ==="
	rsync -az --delete --exclude='.venv' --exclude='*.raw' ./ $(REMOTE_USER)@$(REMOTE_HOST):$(REMOTE_PROJECT)/
	@echo "=== Running simulation with $(NUM_PROCS) parallel processes ==="
	ssh $(REMOTE_USER)@$(REMOTE_HOST) "\
		cd $(REMOTE_PROJECT) && \
		source /eda/cadence/2024-25/scripts/SPECTRE_24.10.078_RHELx86.sh && \
		export CDS_LIC_FILE=$(LICENSE_SERVER) && \
		PYTHONPATH=. $(REMOTE_VENV) $(SIM_SCRIPT) $(cell) -o $(RESULTS_DIR) -j $(NUM_PROCS) $(if $(tech),--tech=$(tech))"
	@echo "=== Syncing results back ==="
	rsync -az $(REMOTE_USER)@$(REMOTE_HOST):$(REMOTE_PROJECT)/$(RESULTS_DIR)/$(cell)/sim/ $(RESULTS_DIR)/$(cell)/sim/
	@echo "=== Simulation complete ==="
endif

# Local simulation (run directly on current machine - use after SSH to juno)
# Usage: ssh juno, cd /local/kcaisley/frida, source spectre env, make sim_local cell=inv
sim_local:
ifndef cell
	$(error Usage: make sim_local cell=<cellname> [tech=<tech>] [NUM_PROCS=N])
endif
	@if [ ! -d "$(RESULTS_DIR)/$(cell)/subckt" ]; then echo "Error: Run 'make subckt cell=$(cell)' first"; exit 1; fi
	@if [ ! -d "$(RESULTS_DIR)/$(cell)/tb" ]; then echo "Error: Run 'make tb cell=$(cell)' first"; exit 1; fi
	$(VENV_PYTHON) $(SIM_SCRIPT) $(cell) -o $(RESULTS_DIR) -j $(NUM_PROCS) $(if $(tech),--tech=$(tech))

clean_sim:
ifdef cell
	rm -rf "$(RESULTS_DIR)/$(cell)/sim"
	@echo "Cleaned: $(RESULTS_DIR)/$(cell)/sim"
else
	rm -rf $(RESULTS_DIR)/*/sim
	@echo "Cleaned: all sim directories"
endif

# ============================================================
# Measurement (PyOPUS PerformanceEvaluator wrapper)
# ============================================================

meas:
ifndef cell
	$(error Usage: make meas cell=<cellname> [tech=<tech>] [corner=<corner>] [temp=<temp>])
endif
	@if [ ! -d "$(RESULTS_DIR)/$(cell)/sim" ]; then echo "Error: Run 'make sim cell=$(cell)' first"; exit 1; fi
	$(VENV_PYTHON) $(MEAS_SCRIPT) $(cell) -o "$(RESULTS_DIR)" \
		$(if $(tech),--tech=$(tech)) \
		$(if $(corner),--corner=$(corner)) \
		$(if $(temp),--temp=$(temp))

clean_meas:
ifdef cell
	rm -rf "$(RESULTS_DIR)/$(cell)/meas"
	@echo "Cleaned: $(RESULTS_DIR)/$(cell)/meas"
else
	rm -rf $(RESULTS_DIR)/*/meas
	@echo "Cleaned: all meas directories"
endif

# ============================================================
# Plotting (with query filtering)
# ============================================================

plot:
ifndef cell
	$(error Usage: make plot cell=<cellname> [tech=<tech>] [corner=<corner>] [temp=<temp>])
endif
	@if [ ! -d "$(RESULTS_DIR)/$(cell)/meas" ]; then echo "Error: Run 'make meas cell=$(cell)' first"; exit 1; fi
	$(VENV_PYTHON) $(PLOT_SCRIPT) $(cell) -o "$(RESULTS_DIR)" \
		$(if $(tech),--tech=$(tech)) \
		$(if $(corner),--corner=$(corner)) \
		$(if $(temp),--temp=$(temp))

plot_interactive:
ifndef cell
	$(error Usage: make plot_interactive cell=<cellname> [tech=<tech>] [corner=<corner>] [temp=<temp>])
endif
	@if [ ! -d "$(RESULTS_DIR)/$(cell)/meas" ]; then echo "Error: Run 'make meas cell=$(cell)' first"; exit 1; fi
	$(VENV_PYTHON) $(PLOT_SCRIPT) $(cell) -o "$(RESULTS_DIR)" --interactive \
		$(if $(tech),--tech=$(tech)) \
		$(if $(corner),--corner=$(corner)) \
		$(if $(temp),--temp=$(temp))

clean_plot:
ifdef cell
	rm -rf "$(RESULTS_DIR)/$(cell)/plot"
	@echo "Cleaned: $(RESULTS_DIR)/$(cell)/plot"
else
	rm -rf $(RESULTS_DIR)/*/plot
	@echo "Cleaned: all plot directories"
endif

# ============================================================
# Full Flow
# ============================================================

all:
ifndef cell
	$(error Usage: make all cell=<cellname>)
endif
	$(MAKE) subckt cell=$(cell)
	$(MAKE) tb cell=$(cell)
	$(MAKE) sim cell=$(cell)
	$(MAKE) meas cell=$(cell)
	$(MAKE) plot cell=$(cell)

clean_all:
ifdef cell
	rm -rf "$(RESULTS_DIR)/$(cell)"
	@echo "Cleaned: $(RESULTS_DIR)/$(cell)"
else
	rm -rf $(RESULTS_DIR)/*
	@echo "Cleaned: all results"
endif

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
	@echo "  sim           Run simulations (rsync to juno, run, rsync back)"
	@echo "  sim_local     Run simulations locally (use after SSH to juno)"
	@echo "  meas          Extract measurements from results"
	@echo "  plot          Generate plots from measurements"
	@echo "  all           Run full flow (subckt -> tb -> sim -> meas -> plot)"
	@echo ""
	@echo "Clean targets:"
	@echo "  clean_subckt  Remove subcircuit files"
	@echo "  clean_tb      Remove testbench files"
	@echo "  clean_sim     Remove simulation results"
	@echo "  clean_meas    Remove measurement results"
	@echo "  clean_plot    Remove plot files"
	@echo "  clean_all     Remove all results for cell"
	@echo ""
	@echo "Options:"
	@echo "  cell=<name>   Cell name (required for most targets)"
	@echo "  tech=<tech>   Filter by technology (tsmc65, tsmc28, tower180)"
	@echo "  corner=<c>    Filter by corner (tt, ss, ff, sf, fs)"
	@echo "  temp=<t>      Filter by temperature (27, etc.)"
	@echo "  NUM_PROCS=N   Number of parallel processes (default: 40)"
	@echo ""
	@echo "Examples:"
	@echo "  make subckt cell=comp"
	@echo "  make tb cell=comp"
	@echo "  make sim cell=comp tech=tsmc65"
	@echo "  make meas cell=comp"
	@echo "  make plot cell=comp tech=tsmc65 corner=tt"
	@echo "  make all cell=comp"
	@echo ""
	@echo "Manual simulation workflow (if 'make sim' times out):"
	@echo "  1. rsync -az --exclude='.venv' --exclude='*.raw' ./ juno:/local/kcaisley/frida/"
	@echo "  2. ssh juno"
	@echo "  3. cd /local/kcaisley/frida"
	@echo "  4. source /eda/cadence/2024-25/scripts/SPECTRE_24.10.078_RHELx86.sh"
	@echo "  5. export CDS_LIC_FILE=27500@nexus.physik.uni-bonn.de"
	@echo "  6. make sim_local cell=inv tech=tower180"
	@echo "  7. exit"
	@echo "  8. rsync -az juno:/local/kcaisley/frida/results/inv/sim/ results/inv/sim/"
