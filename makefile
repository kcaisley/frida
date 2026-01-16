# Configuration
VENV_PYTHON := .venv/bin/python
RESULTS_DIR := results
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

.PHONY: setup clean_all ckt clean_ckt tb clean_tb sim clean_sim viz clean_viz meas clean_meas plot clean_plot

setup:
	@if ! command -v uv >/dev/null 2>&1; then \
		curl -LsSf https://astral.sh/uv/install.sh | sh; \
		echo "uv installed. Run 'make setup' again."; exit 0; \
	fi
	uv python install 3.14
	uv venv --python 3.14 .venv
	uv pip install klayout spicelib blosc2 wavedrom PyQt5 numpy matplotlib pandas tqdm jinja2 ipympl
	@echo "Setup complete. Activate: source .venv/bin/activate"

clean_all:
	@if [ -z "$(filter-out $@,$(MAKECMDGOALS))" ]; then echo "Usage: make $@ <cell>"; exit 1; fi
	@cell="$(filter-out $@,$(MAKECMDGOALS))"; \
	$(MAKE) -s clean_sim $$cell; $(MAKE) -s clean_tb $$cell; $(MAKE) -s clean_ckt $$cell; \
	echo "Cleaned: $$cell"

ckt:
	@if [ -z "$(filter-out $@,$(MAKECMDGOALS))" ]; then echo "Usage: make $@ <cell>"; exit 1; fi
	@cell="$(filter-out $@,$(MAKECMDGOALS))"; \
	if [ ! -f "blocks/$${cell}.py" ]; then echo "Error: blocks/$${cell}.py not found"; exit 1; fi; \
	$(VENV_PYTHON) $(NETLIST_SCRIPT) subckt "blocks/$${cell}.py" -o "$(RESULTS_DIR)/$$cell"

clean_ckt:
	@if [ -z "$(filter-out $@,$(MAKECMDGOALS))" ]; then echo "Usage: make $@ <cell>"; exit 1; fi
	@cell="$(filter-out $@,$(MAKECMDGOALS))"; \
	rm -rf "$(RESULTS_DIR)/$$cell"; echo "Cleaned: $(RESULTS_DIR)/$$cell"

tb:
	@if [ -z "$(filter-out $@,$(MAKECMDGOALS))" ]; then echo "Usage: make $@ <cell> [corner=tt]"; exit 1; fi
	@cell="$(filter-out $@,$(MAKECMDGOALS))"; corner="$${corner:-tt}"; \
	if [ ! -f "blocks/$${cell}.py" ]; then echo "Error: blocks/$${cell}.py not found"; exit 1; fi; \
	$(VENV_PYTHON) $(NETLIST_SCRIPT) tb "blocks/$${cell}.py" -o "$(RESULTS_DIR)/$$cell" -c "$$corner"

clean_tb:
	@if [ -z "$(filter-out $@,$(MAKECMDGOALS))" ]; then echo "Usage: make $@ <cell>"; exit 1; fi
	@cell="$(filter-out $@,$(MAKECMDGOALS))"; \
	rm -f "$(RESULTS_DIR)/$$cell"/tb_*.sp "$(RESULTS_DIR)/$$cell"/tb_*.json; echo "Cleaned: tb_$$cell"

sim:
	@if [ -z "$(filter-out $@,$(MAKECMDGOALS))" ]; then echo "Usage: make $@ <cell> [tech=<tech>]"; exit 1; fi
	@cell="$(filter-out $@,$(MAKECMDGOALS))"; \
	if [ ! -d "$(RESULTS_DIR)/$$cell" ]; then echo "Error: Run 'make ckt $$cell' first"; exit 1; fi; \
	export CDS_LIC_FILE="$(LICENSE_SERVER)"; \
	. $(CADENCE_SPECTRE_SETUP); . $(CADENCE_PVS_SETUP); \
	$(VENV_PYTHON) $(SIM_SCRIPT) \
		--dut-netlists="$(RESULTS_DIR)/$$cell/$${cell}_*.sp" \
		--tb-wrappers="$(RESULTS_DIR)/$$cell/tb_$${cell}_*.sp" \
		--outdir="$(RESULTS_DIR)/$$cell" \
		--tech-filter="$(tech)" \
		--license-server="$(LICENSE_SERVER)" \
		--spectre-path="$(SPECTRE_PATH)" \
		--raw-format=nutascii </dev/null; \
	find "$(RESULTS_DIR)/$$cell" -name "*.ns@0" -delete 2>/dev/null || true; \
	find "$(RESULTS_DIR)/$$cell" -name "*.ahdlSimDB" -exec rm -rf {} + 2>/dev/null || true; \
	find "$(RESULTS_DIR)/$$cell" -name "*.raw.psf" -exec rm -rf {} + 2>/dev/null || true

clean_sim:
	@if [ -z "$(filter-out $@,$(MAKECMDGOALS))" ]; then echo "Usage: make $@ <cell>"; exit 1; fi
	@cell="$(filter-out $@,$(MAKECMDGOALS))"; dir="$(RESULTS_DIR)/$$cell"; \
	rm -f "$$dir"/*.log "$$dir"/*.raw "$$dir"/*.scs "$$dir"/*.error 2>/dev/null || true; \
	find "$$dir" -name "*.ns@*" -exec rm -rf {} + 2>/dev/null || true; \
	find "$$dir" -name "*.ahdlSimDB" -exec rm -rf {} + 2>/dev/null || true; \
	find "$$dir" -name "*.psf" -exec rm -rf {} + 2>/dev/null || true; \
	echo "Cleaned: sim results for $$cell"

viz:
	@if [ -z "$(filter-out $@,$(MAKECMDGOALS))" ]; then echo "Usage: make $@ <cell>"; exit 1; fi
	@cell="$(filter-out $@,$(MAKECMDGOALS))"; dir="$(RESULTS_DIR)/$$cell"; \
	if [ ! -d "$$dir" ]; then echo "Error: Run 'make sim $$cell' first"; exit 1; fi; \
	raw=$$(ls -1 "$$dir"/*.raw 2>/dev/null | head -1); \
	if [ -z "$$raw" ]; then echo "Error: No .raw files in $$dir"; exit 1; fi; \
	$(VENV_PYTHON) $(VIZ_SCRIPT) "$$raw"; \
	[ -n "$$DISPLAY" ] && gaw "$$raw" & || echo "No DISPLAY, skipping gaw"

clean_viz:
	@if [ -z "$(filter-out $@,$(MAKECMDGOALS))" ]; then echo "Usage: make $@ <cell>"; exit 1; fi
	@cell="$(filter-out $@,$(MAKECMDGOALS))"; \
	echo "Cleaned: viz for $$cell"

meas:
	@if [ -z "$(filter-out $@,$(MAKECMDGOALS))" ]; then echo "Usage: make $@ <cell>"; exit 1; fi
	@cell="$(filter-out $@,$(MAKECMDGOALS))"; dir="$(RESULTS_DIR)/$$cell"; \
	if [ ! -f "blocks/$${cell}.py" ]; then echo "Error: blocks/$${cell}.py not found"; exit 1; fi; \
	if [ ! -d "$$dir" ]; then echo "Error: Run 'make sim $$cell' first"; exit 1; fi; \
	for raw in "$$dir"/*.raw; do \
		[ -f "$$raw" ] || continue; \
		base=$$(basename "$$raw" .raw); dut=$${base#tb_}; \
		[ -f "$$dir/$${dut}.sp" ] || continue; \
		$(VENV_PYTHON) $(MEAS_SCRIPT) "$$raw" "$$dir/$${dut}.sp" "blocks/$${cell}.py"; \
	done; echo "Measurement complete: $$cell"

clean_meas:
	@if [ -z "$(filter-out $@,$(MAKECMDGOALS))" ]; then echo "Usage: make $@ <cell>"; exit 1; fi
	@cell="$(filter-out $@,$(MAKECMDGOALS))"; \
	rm -f "$(RESULTS_DIR)/$$cell"/*.raw_a "$(RESULTS_DIR)/$$cell"/*.pkl; echo "Cleaned: measurements for $$cell"

plot:
	@if [ -z "$(filter-out $@,$(MAKECMDGOALS))" ]; then echo "Usage: make $@ <cell>"; exit 1; fi
	@cell="$(filter-out $@,$(MAKECMDGOALS))"; dir="$(RESULTS_DIR)/$$cell"; \
	if [ ! -f "blocks/$${cell}.py" ]; then echo "Error: blocks/$${cell}.py not found"; exit 1; fi; \
	if [ ! -d "$$dir" ]; then echo "Error: Run 'make meas $$cell' first"; exit 1; fi; \
	$(VENV_PYTHON) $(PLOT_SCRIPT) "blocks/$${cell}.py" "$$dir"; \
	echo "Plotting complete: $$cell"

clean_plot:
	@if [ -z "$(filter-out $@,$(MAKECMDGOALS))" ]; then echo "Usage: make $@ <cell>"; exit 1; fi
	@cell="$(filter-out $@,$(MAKECMDGOALS))"; \
	rm -f "$(RESULTS_DIR)/$$cell"/*.pdf "$(RESULTS_DIR)/$$cell"/*.svg; echo "Cleaned: plots for $$cell"

%:
	@:
