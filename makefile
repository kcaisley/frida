# Configuration
VENV_PYTHON := PYTHONPATH=. .venv/bin/python
FLOW_DIR := flow
BLOCKS_DIR := blocks
RESULTS_DIR := results
NETLIST_SCRIPT := $(FLOW_DIR)/netlist.py
SIM_SCRIPT := $(FLOW_DIR)/simulate.py
VIZ_SCRIPT := $(FLOW_DIR)/visualize.py
MEAS_SCRIPT := $(FLOW_DIR)/measure.py
PLOT_SCRIPT := $(FLOW_DIR)/plot.py

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
	uvx ruff check $(FLOW_DIR) $(BLOCKS_DIR)
	uvx ty check $(FLOW_DIR) $(BLOCKS_DIR)
	# Check for unused functions
	uvx vulture $(FLOW_DIR) $(BLOCKS_DIR)

clean_all:
	@if [ -z "$(filter-out $@,$(MAKECMDGOALS))" ]; then echo "Usage: make $@ <cell>"; exit 1; fi
	@cell="$(filter-out $@,$(MAKECMDGOALS))"; \
	$(MAKE) -s clean_plot $$cell; $(MAKE) -s clean_meas $$cell; $(MAKE) -s clean_sim $$cell; $(MAKE) -s clean_tb $$cell; $(MAKE) -s clean_subckt $$cell; \
	echo "Cleaned: $$cell"

subckt:
	@cell="$(filter-out $@,$(MAKECMDGOALS))"; \
	if [ -z "$$cell" ]; then \
		for block in $(BLOCKS_DIR)/*.py; do \
			[ -f "$$block" ] || continue; \
			cell_name=$$(basename "$$block" .py); \
			$(VENV_PYTHON) $(NETLIST_SCRIPT) subckt "$$block" -o "$(RESULTS_DIR)" \
				--subckt-dir="$(RESULTS_DIR)/$$cell_name/subckt" \
				--log-dir="$(RESULTS_DIR)/$$cell_name/logs" || exit 1; \
		done; \
	else \
		if [ ! -f "$(BLOCKS_DIR)/$${cell}.py" ]; then echo "Error: $(BLOCKS_DIR)/$${cell}.py not found"; exit 1; fi; \
		$(VENV_PYTHON) $(NETLIST_SCRIPT) subckt "$(BLOCKS_DIR)/$${cell}.py" -o "$(RESULTS_DIR)" \
			--subckt-dir="$(RESULTS_DIR)/$$cell/subckt" \
			--log-dir="$(RESULTS_DIR)/$$cell/logs"; \
	fi

clean_subckt:
	@if [ -z "$(filter-out $@,$(MAKECMDGOALS))" ]; then echo "Usage: make $@ <cell>"; exit 1; fi
	@cell="$(filter-out $@,$(MAKECMDGOALS))"; \
	rm -rf "$(RESULTS_DIR)/$${cell}/subckt"; echo "Cleaned: $(RESULTS_DIR)/$$cell/subckt"

tb:
	@cell="$(filter-out $@,$(MAKECMDGOALS))"; \
	if [ -z "$$cell" ]; then \
		$(MAKE) -s subckt || exit 1; \
		for block in $(BLOCKS_DIR)/*.py; do \
			[ -f "$$block" ] || continue; \
			cell_name=$$(basename "$$block" .py); \
			$(VENV_PYTHON) $(NETLIST_SCRIPT) tb "$$block" -o "$(RESULTS_DIR)" \
				--subckt-dir="$(RESULTS_DIR)/$$cell_name/subckt" \
				--tb-dir="$(RESULTS_DIR)/$$cell_name/tb" \
				--log-dir="$(RESULTS_DIR)/$$cell_name/logs" || exit 1; \
		done; \
	else \
		if [ ! -f "$(BLOCKS_DIR)/$${cell}.py" ]; then echo "Error: $(BLOCKS_DIR)/$${cell}.py not found"; exit 1; fi; \
		$(VENV_PYTHON) $(NETLIST_SCRIPT) tb "$(BLOCKS_DIR)/$${cell}.py" -o "$(RESULTS_DIR)" \
			--subckt-dir="$(RESULTS_DIR)/$$cell/subckt" \
			--tb-dir="$(RESULTS_DIR)/$$cell/tb" \
			--log-dir="$(RESULTS_DIR)/$$cell/logs"; \
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
	mkdir -p "$(RESULTS_DIR)/$$cell/sim"; \
	export CDS_LIC_FILE="$(LICENSE_SERVER)"; \
	. $(CADENCE_SPECTRE_SETUP); . $(CADENCE_PVS_SETUP); \
	$(VENV_PYTHON) $(SIM_SCRIPT) \
		--dut-netlists="$(RESULTS_DIR)/$$cell/subckt/subckt_*.sp" \
		--tb-wrappers="$(RESULTS_DIR)/$$cell/tb/tb_*.sp" \
		--outdir="$(RESULTS_DIR)/$$cell/sim" \
		--tech-filter="$(tech)" \
		--license-server="$(LICENSE_SERVER)" \
		--spectre-path="$(SPECTRE_PATH)" \
		--raw-format=nutascii </dev/null; \
	find "$(RESULTS_DIR)/$$cell/sim" -name "*.ns@0" -delete 2>/dev/null || true; \
	find "$(RESULTS_DIR)/$$cell/sim" -name "*.ahdlSimDB" -exec rm -rf {} + 2>/dev/null || true; \
	find "$(RESULTS_DIR)/$$cell/sim" -name "*.raw.psf" -exec rm -rf {} + 2>/dev/null || true

clean_sim:
	@if [ -z "$(filter-out $@,$(MAKECMDGOALS))" ]; then echo "Usage: make $@ <cell>"; exit 1; fi
	@cell="$(filter-out $@,$(MAKECMDGOALS))"; \
	rm -rf "$(RESULTS_DIR)/$${cell}/sim"; echo "Cleaned: $(RESULTS_DIR)/$$cell/sim"

viz:
	@if [ -z "$(filter-out $@,$(MAKECMDGOALS))" ]; then echo "Usage: make $@ <cell>"; exit 1; fi
	@cell="$(filter-out $@,$(MAKECMDGOALS))"; \
	if [ ! -d "$(RESULTS_DIR)/$$cell/sim" ]; then echo "Error: Run 'make sim $$cell' first"; exit 1; fi; \
	raw=$$(ls -1 "$(RESULTS_DIR)/$$cell/sim"/sim_$${cell}*.raw 2>/dev/null | head -1); \
	if [ -z "$$raw" ]; then echo "Error: No .raw files for $$cell in $(RESULTS_DIR)/$$cell/sim"; exit 1; fi; \
	$(VENV_PYTHON) $(VIZ_SCRIPT) "$$raw"; \
	[ -n "$$DISPLAY" ] && gaw "$$raw" & || echo "No DISPLAY, skipping gaw"

clean_viz:
	@if [ -z "$(filter-out $@,$(MAKECMDGOALS))" ]; then echo "Usage: make $@ <cell>"; exit 1; fi
	@cell="$(filter-out $@,$(MAKECMDGOALS))"; \
	echo "Cleaned: viz for $$cell"

meas:
	@if [ -z "$(filter-out $@,$(MAKECMDGOALS))" ]; then echo "Usage: make $@ <cell>"; exit 1; fi
	@cell="$(filter-out $@,$(MAKECMDGOALS))"; \
	if [ ! -f "$(BLOCKS_DIR)/$${cell}.py" ]; then echo "Error: $(BLOCKS_DIR)/$${cell}.py not found"; exit 1; fi; \
	if [ ! -d "$(RESULTS_DIR)/$$cell/sim" ]; then echo "Error: Run 'make sim $$cell' first"; exit 1; fi; \
	mkdir -p "$(RESULTS_DIR)/$$cell/meas"; \
	$(VENV_PYTHON) $(MEAS_SCRIPT) "$(BLOCKS_DIR)/$${cell}.py" \
		"$(RESULTS_DIR)/$$cell/sim" \
		"$(RESULTS_DIR)/$$cell/subckt" \
		"$(RESULTS_DIR)/$$cell/tb" \
		"$(RESULTS_DIR)/$$cell/meas" \
		--log-dir="$(RESULTS_DIR)/$$cell/logs"

clean_meas:
	@if [ -z "$(filter-out $@,$(MAKECMDGOALS))" ]; then echo "Usage: make $@ <cell>"; exit 1; fi
	@cell="$(filter-out $@,$(MAKECMDGOALS))"; \
	rm -rf "$(RESULTS_DIR)/$${cell}/meas"; echo "Cleaned: $(RESULTS_DIR)/$$cell/meas"

plot:
	@if [ -z "$(filter-out $@,$(MAKECMDGOALS))" ]; then echo "Usage: make $@ <cell>"; exit 1; fi
	@cell="$(filter-out $@,$(MAKECMDGOALS))"; \
	if [ ! -f "$(BLOCKS_DIR)/$${cell}.py" ]; then echo "Error: $(BLOCKS_DIR)/$${cell}.py not found"; exit 1; fi; \
	if [ ! -d "$(RESULTS_DIR)/$$cell/meas" ]; then echo "Error: Run 'make meas $$cell' first"; exit 1; fi; \
	mkdir -p "$(RESULTS_DIR)/$$cell/plot"; \
	$(VENV_PYTHON) $(PLOT_SCRIPT) "$(BLOCKS_DIR)/$${cell}.py" \
		"$(RESULTS_DIR)/$$cell/meas" \
		--outdir="$(RESULTS_DIR)/$$cell/plot" \
		--log-dir="$(RESULTS_DIR)/$$cell/logs"; \
	echo "Plotting complete: $$cell"

clean_plot:
	@if [ -z "$(filter-out $@,$(MAKECMDGOALS))" ]; then echo "Usage: make $@ <cell>"; exit 1; fi
	@cell="$(filter-out $@,$(MAKECMDGOALS))"; \
	rm -rf "$(RESULTS_DIR)/$${cell}/plot"; echo "Cleaned: $(RESULTS_DIR)/$$cell/plot"

%:
	@:
