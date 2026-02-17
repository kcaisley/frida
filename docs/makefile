TEXLIVE_BIN ?= /usr/local/texlive/2025/bin/x86_64-linux
LATEXMK_PATH := $(TEXLIVE_BIN)/latexmk
LATEXMK ?= $(if $(wildcard $(LATEXMK_PATH)),$(LATEXMK_PATH),latexmk)

SRC ?=
PDF := $(SRC:.tex=.pdf)
BASE := $(basename $(SRC))
OUTDIR := tex

.DEFAULT_GOAL := help

.PHONY: all help docs pdf pdf-force clean clean-aux

all: help

help docs:
	@echo "Docs Makefile usage:"
	@echo "  make pdf SRC=<file.tex>        Build PDF for a TeX source in docs/"
	@echo "  make pdf-force SRC=<file.tex>  Force full rebuild"
	@echo "  make clean SRC=<file.tex>      Clean aux + generated PDF for that source"
	@echo "  make clean-aux SRC=<file.tex>  Clean aux files only"
	@echo ""
	@echo "Examples:"
	@echo "  make pdf SRC=pcb.tex"
	@echo "  make pdf SRC=design.tex"
	@echo ""
	@echo "Available TeX files:"
	@ls -1 *.tex 2>/dev/null | sed 's/^/  - /'

check-src:
	@if [ -z "$(SRC)" ]; then \
		echo "Error: SRC is required."; \
		echo "Try: make pdf SRC=pcb.tex"; \
		exit 1; \
	fi

pdf: check-src
	mkdir -p $(OUTDIR)
	$(LATEXMK) -pdfxe -shell-escape -interaction=nonstopmode -halt-on-error -outdir=$(OUTDIR) $(SRC)
	cp -f $(OUTDIR)/$(PDF) $(PDF)
	@echo "Created $(PDF)"

pdf-force: check-src
	mkdir -p $(OUTDIR)
	$(LATEXMK) -pdfxe -shell-escape -interaction=nonstopmode -halt-on-error -outdir=$(OUTDIR) -f -g $(SRC)
	cp -f $(OUTDIR)/$(PDF) $(PDF)
	@echo "Created $(PDF) (forced rebuild)"


clean-aux: check-src
	$(LATEXMK) -outdir=$(OUTDIR) -c $(SRC)

clean: check-src
	$(LATEXMK) -outdir=$(OUTDIR) -C $(SRC)
	$(RM) $(PDF)
