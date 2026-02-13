TEXLIVE_BIN ?= /usr/local/texlive/2025/bin/x86_64-linux
XELATEX_PATH := $(TEXLIVE_BIN)/xelatex
XELATEX ?= $(if $(wildcard $(XELATEX_PATH)),$(XELATEX_PATH),xelatex)

SRC ?= design.tex
PDF := $(SRC:.tex=.pdf)
BASE := $(basename $(SRC))

AUX_FILES := \
	$(BASE).aux \
	$(BASE).log \
	$(BASE).out \
	$(BASE).nav \
	$(BASE).snm \
	$(BASE).toc \
	$(BASE).vrb \
	$(BASE).fls \
	$(BASE).fdb_latexmk \
	$(BASE).synctex.gz \
	$(BASE).run.xml

.PHONY: all pdf clean clean-aux

all: pdf

pdf:
	$(XELATEX) -interaction=nonstopmode -halt-on-error -shell-escape $(SRC)
	$(XELATEX) -interaction=nonstopmode -halt-on-error -shell-escape $(SRC)
	$(RM) $(AUX_FILES)
	@echo "Created $(PDF)"

clean-aux:
	$(RM) $(AUX_FILES)

clean:
	$(RM) $(PDF) $(AUX_FILES)

