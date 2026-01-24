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
	uv pip install numpy matplotlib scipy klayout spicelib schemdraw PyQt5 mpi4py
	uv pip install https://fides.fe.uni-lj.si/pyopus/download/0.11.2/PyOPUS-0.11.2-cp311-cp311-linux_x86_64.whl
	@echo "Setup complete: .venv created with necessary packages"

check:
	uvx ruff check flow blocks
	uvx ty check flow blocks
	uvx vulture flow blocks

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
# Simulation (MPI-based remote execution on jupiter/juno)
# ============================================================

# MPI configuration
HOSTFILE := hosts.openmpi
NUM_PROCS := 40
MPI_WRAPPER := scripts/mpi_worker.sh

# Simulation using mpirun for distributed execution
sim:
ifndef cell
	$(error Usage: make sim cell=<cellname> [tech=<tech>])
endif
	@if [ ! -d "$(RESULTS_DIR)/$(cell)/subckt" ]; then echo "Error: Run 'make subckt cell=$(cell)' first"; exit 1; fi
	@if [ ! -d "$(RESULTS_DIR)/$(cell)/tb" ]; then echo "Error: Run 'make tb cell=$(cell)' first"; exit 1; fi
	@echo "=== Running MPI simulation with $(NUM_PROCS) processes ==="
	mpirun -n $(NUM_PROCS) --hostfile $(HOSTFILE) --prefix /usr/lib64/openmpi \
		$(MPI_WRAPPER) $(SIM_SCRIPT) $(cell) -o $(RESULTS_DIR) $(if $(tech),--tech=$(tech))

# Local-only simulation (for testing without MPI)
sim_local:
ifndef cell
	$(error Usage: make sim_local cell=<cellname> [tech=<tech>])
endif
	@if [ ! -d "$(RESULTS_DIR)/$(cell)/subckt" ]; then echo "Error: Run 'make subckt cell=$(cell)' first"; exit 1; fi
	@if [ ! -d "$(RESULTS_DIR)/$(cell)/tb" ]; then echo "Error: Run 'make tb cell=$(cell)' first"; exit 1; fi
	$(VENV_PYTHON) $(SIM_SCRIPT) $(cell) -o $(RESULTS_DIR) $(if $(tech),--tech=$(tech))

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
	@echo "  sim           Run Spectre simulations (PyOPUS batch)"
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
	@echo "  NUM_PROCS=N   Number of MPI processes (default: 40)"
	@echo ""
	@echo "Examples:"
	@echo "  make subckt cell=comp"
	@echo "  make tb cell=comp"
	@echo "  make sim cell=comp tech=tsmc65"
	@echo "  make meas cell=comp"
	@echo "  make plot cell=comp tech=tsmc65 corner=tt"
	@echo "  make all cell=comp"
