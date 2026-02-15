TEXLIVE_BIN ?= /usr/local/texlive/2025/bin/x86_64-linux
LATEXMK_PATH := $(TEXLIVE_BIN)/latexmk
LATEXMK ?= $(if $(wildcard $(LATEXMK_PATH)),$(LATEXMK_PATH),latexmk)

SRC ?= design.tex
PDF := $(SRC:.tex=.pdf)
BASE := $(basename $(SRC))
OUTDIR := tex

.PHONY: all pdf pdf-force clean clean-aux

all: pdf

pdf:
	mkdir -p $(OUTDIR)
	$(LATEXMK) -pdfxe -shell-escape -interaction=nonstopmode -halt-on-error -outdir=$(OUTDIR) $(SRC)
	cp -f $(OUTDIR)/$(PDF) $(PDF)
	@echo "Created $(PDF)"

pdf-force:
	mkdir -p $(OUTDIR)
	$(LATEXMK) -pdfxe -shell-escape -interaction=nonstopmode -halt-on-error -outdir=$(OUTDIR) -f -g $(SRC)
	cp -f $(OUTDIR)/$(PDF) $(PDF)
	@echo "Created $(PDF) (forced rebuild)"


clean-aux:
	$(LATEXMK) -outdir=$(OUTDIR) -c $(SRC)

clean:
	$(LATEXMK) -outdir=$(OUTDIR) -C $(SRC)
	$(RM) $(PDF)
