SHELL := /bin/bash

TEXLIVE_BIN ?= /usr/local/texlive/2025/bin/x86_64-linux
LATEXMK_PATH := $(TEXLIVE_BIN)/latexmk
LATEXMK ?= $(if $(wildcard $(LATEXMK_PATH)),$(LATEXMK_PATH),latexmk)

SLIDES_DIR := slides
IMAGES_DIR := images
OUTDIR := tex

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
FIGURE_PNGS := $(FIGURE_TEX:.tex=.png)
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
NETLISTSVG_SVG := $(NETLISTSVG_JSON:.json=.svg)
NETLISTSVG_PDFS := $(NETLISTSVG_JSON:.json=.pdf)

# WaveDrom source JSONs. Keep source JSONs; generated SVG/PDF/PNG go to images/.
WAVEDROM_JSON := \
	$(wildcard *.json) \
	$(IMAGES_DIR)/sequencer_timing.json \
	$(IMAGES_DIR)/spi_register_bitfield_memory_path.json \
	$(IMAGES_DIR)/spi_register_timing.json \
	$(IMAGES_DIR)/wavetest.json
WAVEDROM_SVG := $(patsubst %.json,$(IMAGES_DIR)/%.svg,$(notdir $(WAVEDROM_JSON)))
WAVEDROM_PDFS := $(WAVEDROM_SVG:.svg=.pdf)
WAVEDROM_PNGS := $(WAVEDROM_SVG:.svg=.png)

COLLATERAL := \
	$(FIGURE_PDFS) \
	$(FIGURE_PNGS) \
	$(NETLISTSVG_PDFS) \
	$(WAVEDROM_SVG) \
	$(WAVEDROM_PDFS) \
	$(WAVEDROM_PNGS)

.PHONY: all help clean clean-figure-intermediates figures netlistsvgs wavedroms decks $(SLIDE_ALIASES)
.SECONDARY: $(NETLISTSVG_FROM_V_JSON) $(NETLISTSVG_SVG) $(WAVEDROM_SVG)

.DEFAULT_GOAL := all

all: $(COLLATERAL) decks clean-figure-intermediates
	@echo "Built all generated collateral and TeX documents"

figures: $(FIGURE_PDFS) $(FIGURE_PNGS) clean-figure-intermediates

netlistsvgs: $(NETLISTSVG_PDFS)

wavedroms: $(WAVEDROM_SVG) $(WAVEDROM_PDFS) $(WAVEDROM_PNGS)

decks: $(SLIDE_PDFS)

help:
	@echo "Usage:"
	@echo "  make                  Build generated collateral, then all TeX documents"
	@echo "  make 2026_07_07_fsic.tex  Build one TeX document into $(OUTDIR)/2026_07_07_fsic.pdf"
	@echo "  make images/foo.pdf   Build one generated image asset"
	@echo "  make clean            Remove generated build artifacts"
	@echo ""
	@echo "TeX sources:"
	@printf '  - %s\n' $(SLIDE_TEX)
	@echo ""
	@echo "Generated collateral sources:"
	@printf '  - %s\n' $(FIGURE_TEX) $(NETLISTSVG_V) $(NETLISTSVG_INPUT_JSON) $(WAVEDROM_JSON)

$(OUTDIR)/%.pdf: $(SLIDES_DIR)/%.tex $(COLLATERAL)
	mkdir -p $(OUTDIR)
	$(LATEXMK) -pdfxe -shell-escape -interaction=nonstopmode -halt-on-error -outdir=$(OUTDIR) $<
	@echo "Created $@"

$(addsuffix .tex,$(SLIDE_NAMES)): %.tex: $(OUTDIR)/%.pdf
	@true

$(IMAGES_DIR)/%.pdf: $(IMAGES_DIR)/%.tex
	$(LATEXMK) -pdf -interaction=nonstopmode -halt-on-error -outdir=$(IMAGES_DIR) $<
	@echo "Created $@"

$(IMAGES_DIR)/%.png: $(IMAGES_DIR)/%.pdf
	pdftoppm -png -r 300 -singlefile $< $(@:.png=)
	@echo "Created $@"

$(IMAGES_DIR)/%_netlistsvg.json: $(IMAGES_DIR)/%_netlistsvg.v
	yosys -q -p "read_verilog $<; prep -top $*_netlistsvg; write_json $@"
	@echo "Created $@"

$(IMAGES_DIR)/%_netlistsvg.svg: $(IMAGES_DIR)/%_netlistsvg.json
	python3 -c 'import json,sys; p=sys.argv[1]; o=sys.argv[2]; d=json.load(open(p));\
mods=d.get("modules",{});\
[port.update({"direction":"input"}) for m in mods.values() for port in m.get("ports",{}).values() if port.get("direction") not in ("input","output")];\
[pd.__setitem__(k,"input") for m in mods.values() for c in m.get("cells",{}).values() for pd in [c.get("port_directions",{})] for k,v in list(pd.items()) if v not in ("input","output")];\
json.dump(d,open(o,"w"))' $< $@.tmp.json
	netlistsvg $@.tmp.json -o $@
	rm -f $@.tmp.json
	@echo "Created $@"

$(IMAGES_DIR)/%_netlistsvg.pdf: $(IMAGES_DIR)/%_netlistsvg.svg
	rsvg-convert -f pdf -o $@ $<
	@echo "Created $@"

$(IMAGES_DIR)/%.svg: %.json
	npx wavedrom-cli -i $< -s $@
	@echo "Created $@"

$(IMAGES_DIR)/%.svg: $(IMAGES_DIR)/%.json
	npx wavedrom-cli -i $< -s $@
	@echo "Created $@"

$(IMAGES_DIR)/%.pdf: $(IMAGES_DIR)/%.svg
	rsvg-convert -f pdf -o $@ $<
	@echo "Created $@"

$(IMAGES_DIR)/%.png: $(IMAGES_DIR)/%.svg
	rsvg-convert -f png -o $@ $<
	@echo "Created $@"

%.png: %.md FORCE
	echo '{"args":["--no-sandbox"]}' | mmdc -i $< -o $@ -p /dev/stdin
	mv -f $(*F)-1.png $@
	@echo "Created $@"

FORCE:

clean-figure-intermediates:
	rm -f $(FIGURE_INTERMEDIATES) $(SLIDE_INTERMEDIATES)
	rm -f $(SLIDES_DIR)/*.aux $(SLIDES_DIR)/*.fdb_latexmk $(SLIDES_DIR)/*.fls $(SLIDES_DIR)/*.log $(SLIDES_DIR)/*.nav $(SLIDES_DIR)/*.out $(SLIDES_DIR)/*.pdf $(SLIDES_DIR)/*.snm $(SLIDES_DIR)/*.synctex.gz $(SLIDES_DIR)/*.toc $(SLIDES_DIR)/*.vrb $(SLIDES_DIR)/*.xdv

clean:
	rm -rf $(OUTDIR)
	rm -f *.aux *.fdb_latexmk *.fls *.log *.out *.synctex.gz *.xdv
	rm -f *.pdf
	rm -f $(FIGURE_INTERMEDIATES) $(SLIDE_INTERMEDIATES)
	rm -f $(NETLISTSVG_FROM_V_JSON) $(NETLISTSVG_SVG) $(NETLISTSVG_PDFS)
	rm -f $(WAVEDROM_SVG) $(WAVEDROM_PDFS) $(WAVEDROM_PNGS)
	@echo "Removed generated build artifacts"
