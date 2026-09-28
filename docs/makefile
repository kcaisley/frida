SHELL := /bin/bash

TEXLIVE_BIN ?= /usr/local/texlive/2026/bin/x86_64-linux
export PATH := $(TEXLIVE_BIN):$(PATH)
LATEXMK_PATH := $(TEXLIVE_BIN)/latexmk
LATEXMK ?= $(if $(wildcard $(LATEXMK_PATH)),$(LATEXMK_PATH),latexmk)
NETLISTSVG ?= npx --yes netlistsvg@1.0.2
DEBUG ?= 0

SLIDES_DIR := slides
IMAGES_DIR := images
OUTDIR := tex

THESIS_THEME_DIR := $(abspath ../libs/ubonn-thesis)
THESIS_STYLE := $(THESIS_THEME_DIR)/ubonn-thesis.sty
export TEXINPUTS := $(THESIS_THEME_DIR)//:$(TEXINPUTS)

DOCUMENT_TEX := $(wildcard *.tex)
DOCUMENT_NAMES := $(basename $(notdir $(DOCUMENT_TEX)))
DOCUMENT_PDFS := $(addprefix $(OUTDIR)/,$(addsuffix .pdf,$(DOCUMENT_NAMES)))
DOCUMENT_ALIASES := $(DOCUMENT_NAMES)

SLIDE_TEX := $(wildcard $(SLIDES_DIR)/*.tex)
SLIDE_NAMES := $(basename $(notdir $(SLIDE_TEX)))
SLIDE_PDFS := $(addprefix $(OUTDIR)/,$(addsuffix .pdf,$(SLIDE_NAMES)))
SLIDE_ALIASES := $(addsuffix .tex,$(SLIDE_NAMES))
SLIDE_INTERMEDIATES := \
	$(SLIDE_TEX:.tex=.aux) \
	$(SLIDE_TEX:.tex=.fdb_latexmk) \
	$(SLIDE_TEX:.tex=.fls) \
	$(SLIDE_TEX:.tex=.log) \
	$(SLIDE_TEX:.tex=.nav) \
	$(SLIDE_TEX:.tex=.out) \
	$(SLIDE_TEX:.tex=.pdf) \
	$(SLIDE_TEX:.tex=.snm) \
	$(SLIDE_TEX:.tex=.synctex.gz) \
	$(SLIDE_TEX:.tex=.toc) \
	$(SLIDE_TEX:.tex=.vrb) \
	$(SLIDE_TEX:.tex=.xdv)

FIGURE_TEX := $(wildcard $(IMAGES_DIR)/*.tex)
FIGURE_PDFS := $(FIGURE_TEX:.tex=.pdf)
FIGURE_INTERMEDIATES := \
	$(FIGURE_TEX:.tex=.aux) \
	$(FIGURE_TEX:.tex=.fdb_latexmk) \
	$(FIGURE_TEX:.tex=.fls) \
	$(FIGURE_TEX:.tex=.log) \
	$(FIGURE_TEX:.tex=.xdv) \
	$(FIGURE_TEX:.tex=.synctex.gz)

# preamp_netlistsvg is a curated analog render; regenerating it from Yosys
# loses the MOS-symbol styling and produces generic boxes.
NETLISTSVG_V := $(filter-out $(IMAGES_DIR)/preamp_netlistsvg.v,$(wildcard $(IMAGES_DIR)/*_netlistsvg.v))
NETLISTSVG_FROM_V_JSON := $(NETLISTSVG_V:.v=.json)
NETLISTSVG_INPUT_JSON := $(filter-out $(NETLISTSVG_FROM_V_JSON),$(wildcard $(IMAGES_DIR)/*_netlistsvg.json))
NETLISTSVG_JSON := $(sort $(NETLISTSVG_FROM_V_JSON) $(NETLISTSVG_INPUT_JSON))
NETLISTSVG_PDFS := $(NETLISTSVG_JSON:.json=.pdf) $(IMAGES_DIR)/adc_digital_netlistsvg.pdf

DOC_IMAGE_BUILD_DIR := ../build/docs/images
DEBUG_PREVIEW = $(patsubst $(IMAGES_DIR)/%,$(DOC_IMAGE_BUILD_DIR)/previews/%,$(@:.pdf=.png))

define render_debug_preview
	@if [ "$(DEBUG)" = "1" ]; then \
		mkdir -p "$(dir $(DEBUG_PREVIEW))"; \
		pdftoppm -f 1 -singlefile -png -r 200 "$@" "$(basename $(DEBUG_PREVIEW))"; \
	fi
endef

PHYS_RESULTS := \
	../phys/results/hit_rate_vs_fluence.png \
	../phys/results/max_counting_rate_vs_window.png

COLLATERAL := \
	$(FIGURE_PDFS) \
	$(NETLISTSVG_PDFS) \
	$(PHYS_RESULTS)

.PHONY: all help clean clean-image-debug clean-figure-intermediates figures netlistsvgs documents decks FORCE $(DOCUMENT_ALIASES) $(SLIDE_ALIASES)
.SECONDARY: $(NETLISTSVG_FROM_V_JSON)

.DEFAULT_GOAL := all

all: $(COLLATERAL) documents decks clean-figure-intermediates
	@echo "Built all generated collateral and TeX documents"

figures: $(FIGURE_PDFS) clean-figure-intermediates

netlistsvgs: $(NETLISTSVG_PDFS)

documents: $(DOCUMENT_PDFS)

decks: $(SLIDE_PDFS)

help:
	@echo "Usage:"
	@echo "  make                  Build generated collateral, then all TeX documents"
	@echo "  make outline          Build the thesis outline into $(OUTDIR)/outline.pdf"
	@echo "  make 2026_07_07_fsic.tex  Build one TeX document into $(OUTDIR)/2026_07_07_fsic.pdf"
	@echo "  make images/foo.pdf   Build one generated image asset"
	@echo "  make clean-image-debug  Remove image build logs and debug previews"
	@echo "  make clean            Remove generated build artifacts"
	@echo ""
	@echo "TeX sources:"
	@printf '  - %s\n' $(DOCUMENT_TEX) $(SLIDE_TEX)
	@echo ""
	@echo "Generated collateral sources:"
	@printf '  - %s\n' $(FIGURE_TEX) $(NETLISTSVG_V) $(NETLISTSVG_INPUT_JSON)

$(DOCUMENT_PDFS): $(OUTDIR)/%.pdf: %.tex
	mkdir -p $(OUTDIR)
	rm -f $(@:.pdf=.aux) $(@:.pdf=.fdb_latexmk) $(@:.pdf=.fls) $(@:.pdf=.log)
	$(LATEXMK) -pdfxe -shell-escape -interaction=nonstopmode -halt-on-error -outdir=$(OUTDIR) $<
	@echo "Created $@"

$(OUTDIR)/outline.pdf: $(THESIS_STYLE)

$(SLIDE_PDFS): $(OUTDIR)/%.pdf: $(SLIDES_DIR)/%.tex $(COLLATERAL)
	mkdir -p $(OUTDIR)
	rm -f $(@:.pdf=.aux) $(@:.pdf=.fdb_latexmk) $(@:.pdf=.fls) $(@:.pdf=.log)
	cd $(SLIDES_DIR) && $(LATEXMK) -pdfxe -shell-escape -interaction=nonstopmode -halt-on-error -outdir=../$(OUTDIR) $(notdir $<)
	@echo "Created $@"

$(OUTDIR)/2026_09_24_sequences.pdf: $(IMAGES_DIR)/daq_diagram.pdf

$(DOCUMENT_NAMES): %: $(OUTDIR)/%.pdf
	@true

$(addsuffix .tex,$(SLIDE_NAMES)): %.tex: $(OUTDIR)/%.pdf
	@true

$(IMAGES_DIR)/%.pdf: $(IMAGES_DIR)/%.tex FORCE
	@set -e; if [ "$(DEBUG)" = "1" ] || [ ! -f "$@" ] || [ "$<" -nt "$@" ]; then \
		$(LATEXMK) -pdf $(if $(filter 1,$(DEBUG)),-g,) \
			-interaction=nonstopmode -halt-on-error -outdir=$(IMAGES_DIR) $<; \
	fi
	@set -e; if [ "$(DEBUG)" != "1" ]; then \
		$(LATEXMK) -c -outdir=$(IMAGES_DIR) $<; \
		$(RM) $(@:.pdf=.synctex.gz); \
	fi
	$(render_debug_preview)
	@echo "Created $@"

$(PHYS_RESULTS) &: ../phys/model.py
	uv run python ../phys/model.py
	@echo "Created physics result plots"

$(IMAGES_DIR)/%_netlistsvg.json: $(IMAGES_DIR)/%_netlistsvg.v
	yosys -q -p "read_verilog $<; prep -top $*_netlistsvg; write_json $@"
	@echo "Created $@"

$(IMAGES_DIR)/%_netlistsvg.pdf: $(IMAGES_DIR)/%_netlistsvg.json FORCE
	@set -e; if [ "$(DEBUG)" = "1" ] || [ ! -f "$@" ] || [ "$<" -nt "$@" ]; then \
		mkdir -p $(DOC_IMAGE_BUILD_DIR); \
		python3 -c 'import json,sys; p=sys.argv[1]; o=sys.argv[2]; d=json.load(open(p));\
mods=d.get("modules",{});\
[port.update({"direction":"input"}) for m in mods.values() for port in m.get("ports",{}).values() if port.get("direction") not in ("input","output")];\
[pd.__setitem__(k,"input") for m in mods.values() for c in m.get("cells",{}).values() for pd in [c.get("port_directions",{})] for k,v in list(pd.items()) if v not in ("input","output")];\
json.dump(d,open(o,"w"))' $< $(DOC_IMAGE_BUILD_DIR)/$*_netlistsvg.tmp.json; \
		$(NETLISTSVG) $(DOC_IMAGE_BUILD_DIR)/$*_netlistsvg.tmp.json -o $(DOC_IMAGE_BUILD_DIR)/$*_netlistsvg.svg; \
		rsvg-convert -f pdf -o $@ $(DOC_IMAGE_BUILD_DIR)/$*_netlistsvg.svg; \
		if [ "$(DEBUG)" != "1" ]; then $(RM) $(DOC_IMAGE_BUILD_DIR)/$*_netlistsvg.tmp.json $(DOC_IMAGE_BUILD_DIR)/$*_netlistsvg.svg; fi; \
	fi
	$(render_debug_preview)
	@echo "Created $@"

$(IMAGES_DIR)/adc_digital_netlistsvg.pdf: $(IMAGES_DIR)/adc_digital.json FORCE
	@set -e; if [ "$(DEBUG)" = "1" ] || [ ! -f "$@" ] || [ "$<" -nt "$@" ]; then \
		mkdir -p $(DOC_IMAGE_BUILD_DIR); \
		$(NETLISTSVG) $< -o $(DOC_IMAGE_BUILD_DIR)/adc_digital_netlistsvg.svg; \
		rsvg-convert -f pdf -o $@ $(DOC_IMAGE_BUILD_DIR)/adc_digital_netlistsvg.svg; \
		if [ "$(DEBUG)" != "1" ]; then $(RM) $(DOC_IMAGE_BUILD_DIR)/adc_digital_netlistsvg.svg; fi; \
	fi
	$(render_debug_preview)
	@echo "Created $@"

$(IMAGES_DIR)/%.pdf: $(IMAGES_DIR)/%.svg FORCE
	@set -e; if [ ! -f "$@" ] || [ "$<" -nt "$@" ]; then rsvg-convert -f pdf -o $@ $<; fi
	$(render_debug_preview)
	@echo "Created $@"

$(IMAGES_DIR)/arch.png: $(IMAGES_DIR)/arch.svg
	rsvg-convert -f png -o $@ $<
	@echo "Created $@"

%.png: %.md FORCE
	echo '{"args":["--no-sandbox"]}' | mmdc -i $< -o $@ -p /dev/stdin
	mv -f $(*F)-1.png $@
	@echo "Created $@"

FORCE:

clean-figure-intermediates:
	@if [ "$(DEBUG)" != "1" ]; then $(RM) $(FIGURE_INTERMEDIATES); fi
	rm -f $(SLIDE_INTERMEDIATES)
	rm -f $(SLIDES_DIR)/*.aux $(SLIDES_DIR)/*.fdb_latexmk $(SLIDES_DIR)/*.fls $(SLIDES_DIR)/*.log $(SLIDES_DIR)/*.nav $(SLIDES_DIR)/*.out $(SLIDES_DIR)/*.pdf $(SLIDES_DIR)/*.snm $(SLIDES_DIR)/*.synctex.gz $(SLIDES_DIR)/*.toc $(SLIDES_DIR)/*.vrb $(SLIDES_DIR)/*.xdv

clean-image-debug:
	rm -f $(FIGURE_INTERMEDIATES)
	rm -rf $(DOC_IMAGE_BUILD_DIR)
	@echo "Removed image debug logs and previews"

clean: clean-image-debug
	rm -rf $(OUTDIR)
	rm -f *.aux *.fdb_latexmk *.fls *.log *.out *.synctex.gz *.xdv
	rm -f *.pdf
	rm -f $(SLIDE_INTERMEDIATES)
	rm -f $(NETLISTSVG_FROM_V_JSON) $(NETLISTSVG_PDFS)
	rm -f $(PHYS_RESULTS)
	@echo "Removed generated build artifacts"
