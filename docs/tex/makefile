# Makefile for building design review slides
# Usage: make        - Build PDF slides
#        make clean  - Remove build artifacts

INPUT = ../design_review.md
OUTPUT = design_review_slides.pdf

.PHONY: all clean

all: $(OUTPUT)

$(OUTPUT): $(INPUT)
	@echo "Building slides..."
	cd .. && pandoc design_review.md \
		-t beamer \
		--pdf-engine=xelatex \
		-V theme:default \
		-V colortheme:default \
		-V aspectratio:169 \
		-V fontsize:10pt \
		--highlight-style=tango \
		--slide-level=2 \
		-o tex/$(OUTPUT)
	@echo "Created $(OUTPUT)"

clean:
	rm -f *.aux *.log *.out *.toc *.nav *.snm *.fls *.fdb_latexmk *.synctex.gz *.vrb *.tex *.pdf
