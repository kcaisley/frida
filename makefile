# Configuration
VENV_PYTHON := PYTHONPATH=. .venv/bin/python
RESULTS_DIR := results
SIM_DIR := results/sim
MEAS_DIR := results/meas
PLOT_DIR := results/plot
NETLIST_SCRIPT := flow/netlist.py
SIM_SCRIPT := flow/simulate.py
VIZ_SCRIPT := flow/visualize.py
MEAS_SCRIPT := flow/measure.py
PLOT_SCRIPT := flow/plot.py

# Cadence tools
CADENCE_SPECTRE_SETUP := /eda/cadence/2024-25/scripts/SPECTRE_24.10.078_RHELx86.sh
CADENCE_PVS_SETUP := /eda/cadence/2024-25/scripts/PVS_24.10.000_RHELx86.sh
LICENSE_SERVER := 27500@nexus.physik.uni-bonn.de
SPECTRE_PATH := /eda/cadence/2024-25/RHELx86/SPECTRE_24.10.078/bin/spectre

.PHONY: setup check clean_all subckt clean_subckt tb clean_tb sim clean_sim viz clean_viz meas clean_meas plot clean_plot

setup:
	@if ! command -v uv >/dev/null 2>&1; then \
		curl -LsSf https://astral.sh/uv/install.sh | sh; \
		echo "uv installed. Run 'make setup' again."; exit 0; \
	fi
	uv python install 3.14
	uv venv --clear --python 3.14 .venv
	uv pip install numpy matplotlib scipy klayout spicelib schemdraw PyQt5
	@echo "Setup complete: .venv created with necessary packages"

check:
	uvx ruff check flow blocks
	uvx ty check flow blocks
	# Check for unused functions
	uvx vulture flow blocks

clean_all:
	@if [ -z "$(filter-out $@,$(MAKECMDGOALS))" ]; then echo "Usage: make $@ <cell>"; exit 1; fi
	@cell="$(filter-out $@,$(MAKECMDGOALS))"; \
	$(MAKE) -s clean_plot $$cell; $(MAKE) -s clean_meas $$cell; $(MAKE) -s clean_sim $$cell; $(MAKE) -s clean_tb $$cell; $(MAKE) -s clean_subckt $$cell; \
	echo "Cleaned: $$cell"

subckt:
	@cell="$(filter-out $@,$(MAKECMDGOALS))"; \
	if [ -z "$$cell" ]; then \
		for block in blocks/*.py; do \
			[ -f "$$block" ] || continue; \
			cell_name=$$(basename "$$block" .py); \
			$(VENV_PYTHON) $(NETLIST_SCRIPT) subckt "$$block" -o "$(RESULTS_DIR)" || exit 1; \
		done; \
	else \
		if [ ! -f "blocks/$${cell}.py" ]; then echo "Error: blocks/$${cell}.py not found"; exit 1; fi; \
		$(VENV_PYTHON) $(NETLIST_SCRIPT) subckt "blocks/$${cell}.py" -o "$(RESULTS_DIR)"; \
	fi

clean_subckt:
	@if [ -z "$(filter-out $@,$(MAKECMDGOALS))" ]; then echo "Usage: make $@ <cell>"; exit 1; fi
	@cell="$(filter-out $@,$(MAKECMDGOALS))"; \
	rm -rf "$(RESULTS_DIR)/$${cell}/subckt"; echo "Cleaned: $(RESULTS_DIR)/$$cell/subckt"

tb:
	@cell="$(filter-out $@,$(MAKECMDGOALS))"; \
	if [ -z "$$cell" ]; then \
		$(MAKE) -s subckt || exit 1; \
		for block in blocks/*.py; do \
			[ -f "$$block" ] || continue; \
			cell_name=$$(basename "$$block" .py); \
			$(VENV_PYTHON) $(NETLIST_SCRIPT) tb "$$block" -o "$(RESULTS_DIR)" || exit 1; \
		done; \
	else \
		if [ ! -f "blocks/$${cell}.py" ]; then echo "Error: blocks/$${cell}.py not found"; exit 1; fi; \
		$(VENV_PYTHON) $(NETLIST_SCRIPT) tb "blocks/$${cell}.py" -o "$(RESULTS_DIR)"; \
	fi

clean_tb:
	@if [ -z "$(filter-out $@,$(MAKECMDGOALS))" ]; then echo "Usage: make $@ <cell>"; exit 1; fi
	@cell="$(filter-out $@,$(MAKECMDGOALS))"; \
	rm -rf "$(RESULTS_DIR)/$${cell}/tb"; echo "Cleaned: $(RESULTS_DIR)/$$cell/tb"

sim:
	@if [ -z "$(filter-out $@,$(MAKECMDGOALS))" ]; then echo "Usage: make $@ <cell> [tech=<tech>]"; exit 1; fi
	@cell="$(filter-out $@,$(MAKECMDGOALS))"; \
	if [ ! -d "$(RESULTS_DIR)/$$cell/subckt" ]; then echo "Error: Run 'make subckt $$cell' first"; exit 1; fi; \
	if [ ! -d "$(RESULTS_DIR)/$$cell/tb" ]; then echo "Error: Run 'make tb $$cell' first"; exit 1; fi; \
	mkdir -p "$(SIM_DIR)"; \
	export CDS_LIC_FILE="$(LICENSE_SERVER)"; \
	. $(CADENCE_SPECTRE_SETUP); . $(CADENCE_PVS_SETUP); \
	$(VENV_PYTHON) $(SIM_SCRIPT) \
		--dut-netlists="$(RESULTS_DIR)/$$cell/subckt/subckt_*.sp" \
		--tb-wrappers="$(RESULTS_DIR)/$$cell/tb/tb_*.sp" \
		--outdir="$(SIM_DIR)" \
		--tech-filter="$(tech)" \
		--license-server="$(LICENSE_SERVER)" \
		--spectre-path="$(SPECTRE_PATH)" \
		--raw-format=nutascii </dev/null; \
	find "$(SIM_DIR)" -name "*.ns@0" -delete 2>/dev/null || true; \
	find "$(SIM_DIR)" -name "*.ahdlSimDB" -exec rm -rf {} + 2>/dev/null || true; \
	find "$(SIM_DIR)" -name "*.raw.psf" -exec rm -rf {} + 2>/dev/null || true

clean_sim:
	@if [ -z "$(filter-out $@,$(MAKECMDGOALS))" ]; then echo "Usage: make $@ <cell>"; exit 1; fi
	@cell="$(filter-out $@,$(MAKECMDGOALS))"; \
	rm -f "$(SIM_DIR)"/sim_$${cell}*.log "$(SIM_DIR)"/sim_$${cell}*.raw "$(SIM_DIR)"/sim_$${cell}*.scs "$(SIM_DIR)"/sim_$${cell}*.error 2>/dev/null || true; \
	find "$(SIM_DIR)" -name "sim_$${cell}*.ns@*" -exec rm -rf {} + 2>/dev/null || true; \
	find "$(SIM_DIR)" -name "sim_$${cell}*.ahdlSimDB" -exec rm -rf {} + 2>/dev/null || true; \
	find "$(SIM_DIR)" -name "sim_$${cell}*.psf" -exec rm -rf {} + 2>/dev/null || true; \
	echo "Cleaned: sim results for $$cell"

viz:
	@if [ -z "$(filter-out $@,$(MAKECMDGOALS))" ]; then echo "Usage: make $@ <cell>"; exit 1; fi
	@cell="$(filter-out $@,$(MAKECMDGOALS))"; \
	if [ ! -d "$(SIM_DIR)" ]; then echo "Error: Run 'make sim $$cell' first"; exit 1; fi; \
	raw=$$(ls -1 "$(SIM_DIR)"/sim_$${cell}*.raw 2>/dev/null | head -1); \
	if [ -z "$$raw" ]; then echo "Error: No .raw files for $$cell in $(SIM_DIR)"; exit 1; fi; \
	$(VENV_PYTHON) $(VIZ_SCRIPT) "$$raw"; \
	[ -n "$$DISPLAY" ] && gaw "$$raw" & || echo "No DISPLAY, skipping gaw"

clean_viz:
	@if [ -z "$(filter-out $@,$(MAKECMDGOALS))" ]; then echo "Usage: make $@ <cell>"; exit 1; fi
	@cell="$(filter-out $@,$(MAKECMDGOALS))"; \
	echo "Cleaned: viz for $$cell"

meas:
	@if [ -z "$(filter-out $@,$(MAKECMDGOALS))" ]; then echo "Usage: make $@ <cell>"; exit 1; fi
	@cell="$(filter-out $@,$(MAKECMDGOALS))"; \
	if [ ! -f "blocks/$${cell}.py" ]; then echo "Error: blocks/$${cell}.py not found"; exit 1; fi; \
	if [ ! -d "$(SIM_DIR)" ]; then echo "Error: Run 'make sim $$cell' first"; exit 1; fi; \
	mkdir -p "$(MEAS_DIR)"; \
	$(VENV_PYTHON) $(MEAS_SCRIPT) "blocks/$${cell}.py" "$(SIM_DIR)" "$(RESULTS_DIR)/$$cell/subckt" "$(RESULTS_DIR)/$$cell/tb" "$(MEAS_DIR)"

clean_meas:
	@if [ -z "$(filter-out $@,$(MAKECMDGOALS))" ]; then echo "Usage: make $@ <cell>"; exit 1; fi
	@cell="$(filter-out $@,$(MAKECMDGOALS))"; \
	rm -f "$(MEAS_DIR)"/meas_$${cell}*.json "$(MEAS_DIR)"/meas_$${cell}*.csv; echo "Cleaned: measurements for $$cell"

plot:
	@if [ -z "$(filter-out $@,$(MAKECMDGOALS))" ]; then echo "Usage: make $@ <cell>"; exit 1; fi
	@cell="$(filter-out $@,$(MAKECMDGOALS))"; \
	if [ ! -f "blocks/$${cell}.py" ]; then echo "Error: blocks/$${cell}.py not found"; exit 1; fi; \
	if [ ! -d "$(MEAS_DIR)" ]; then echo "Error: Run 'make meas $$cell' first"; exit 1; fi; \
	mkdir -p "$(PLOT_DIR)"; \
	$(VENV_PYTHON) $(PLOT_SCRIPT) "blocks/$${cell}.py" "$(MEAS_DIR)" --outdir="$(PLOT_DIR)"; \
	echo "Plotting complete: $$cell"

clean_plot:
	@if [ -z "$(filter-out $@,$(MAKECMDGOALS))" ]; then echo "Usage: make $@ <cell>"; exit 1; fi
	@cell="$(filter-out $@,$(MAKECMDGOALS))"; \
	rm -f "$(PLOT_DIR)/$${cell}"*.pdf "$(PLOT_DIR)/$${cell}"*.svg; echo "Cleaned: plots for $$cell"

%:
	@:
