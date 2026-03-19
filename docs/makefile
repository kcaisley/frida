TEXLIVE_BIN ?= /usr/local/texlive/2025/bin/x86_64-linux
LATEXMK_PATH := $(TEXLIVE_BIN)/latexmk
LATEXMK ?= $(if $(wildcard $(LATEXMK_PATH)),$(LATEXMK_PATH),latexmk)

OUTDIR := tex
SRCS := $(wildcard *.tex)

.PHONY: help clean reset $(SRCS)

.DEFAULT_GOAL := help

help:
	@echo "Usage:"
	@echo "  make <file.tex>       Build PDF"
	@echo "  make clean <file.tex> Clean aux files for that source"
	@echo "  make reset            Remove all aux files and PDFs"
	@echo ""
	@echo "Available TeX files:"
	@ls -1 *.tex 2>/dev/null | sed 's/^/  - /'

$(SRCS):
	mkdir -p $(OUTDIR)
	$(LATEXMK) -pdfxe -shell-escape -interaction=nonstopmode -halt-on-error -outdir=$(OUTDIR) $@
	cp -f $(OUTDIR)/$(@:.tex=.pdf) $(@:.tex=.pdf)
	@echo "Created $(@:.tex=.pdf)"

clean:
	@if [ -z "$(filter %.tex,$(MAKECMDGOALS))" ]; then \
		echo "Usage: make clean <file.tex>"; \
		exit 1; \
	fi
	$(foreach src,$(filter %.tex,$(MAKECMDGOALS)),\
		$(LATEXMK) -outdir=$(OUTDIR) -c $(src);)

reset:
	rm -rf $(OUTDIR)
	rm -f *.pdf
	@echo "Removed $(OUTDIR)/ and all PDFs"
