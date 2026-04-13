TEXLIVE_BIN ?= /usr/local/texlive/2025/bin/x86_64-linux
LATEXMK_PATH := $(TEXLIVE_BIN)/latexmk
LATEXMK ?= $(if $(wildcard $(LATEXMK_PATH)),$(LATEXMK_PATH),latexmk)

OUTDIR := tex
SRCS := $(wildcard *.tex)

.PHONY: help clean $(SRCS)

.DEFAULT_GOAL := help

help:
	@echo "Usage:"
	@echo "  make <file.tex>   Build PDF from LaTeX source"
	@echo "  make <name.png>   Build PNG from Mermaid chart (<name.md>)"
	@echo "  make clean        Remove all build artifacts"
	@echo ""
	@echo "Available TeX files:"
	@ls -1 *.tex 2>/dev/null | sed 's/^/  - /'

$(SRCS):
	mkdir -p $(OUTDIR)
	$(LATEXMK) -pdfxe -shell-escape -interaction=nonstopmode -halt-on-error -outdir=$(OUTDIR) $@
	cp -f $(OUTDIR)/$(@:.tex=.pdf) $(@:.tex=.pdf)
	@echo "Created $(@:.tex=.pdf)"

%.png: %.md FORCE
	echo '{"args":["--no-sandbox"]}' | mmdc -i $< -o $@ -p /dev/stdin
	mv -f $(*F)-1.png $@
	@echo "Created $@"

FORCE:

clean:
	rm -rf $(OUTDIR)
	rm -f *.pdf
	@echo "Removed build artifacts"
