# Makefile for converting markdown tables to LaTeX and compiling to PDF
# Usage:
#   make convert FILE=table.md    # Convert markdown to LaTeX
#   make compile FILE=table.tex   # Compile LaTeX to PDF
#   make clean                    # Remove build artifacts

# Default file if not specified
FILE ?= table

# Get filename without extension
BASENAME = $(basename $(FILE))

# Lua filter for simple tables
LUA_FILTER = simple_table.lua

.PHONY: convert compile clean help

# Convert markdown file to LaTeX using pandoc + Lua filter
convert:
	@if [ ! -f "$(FILE)" ]; then \
		echo "Error: File $(FILE) not found!"; \
		exit 1; \
	fi
	@if [ ! -f "$(LUA_FILTER)" ]; then \
		echo "Error: Lua filter $(LUA_FILTER) not found!"; \
		exit 1; \
	fi
	@echo "Converting $(FILE) to LaTeX..."
	pandoc "$(FILE)" -t latex --lua-filter="$(LUA_FILTER)" -o "$(BASENAME)_raw.tex"
	@echo "Creating complete LaTeX document..."
	@printf '\\documentclass{article}\n' > "$(BASENAME)_complete.tex"
	@printf '\\usepackage{amsmath}\n' >> "$(BASENAME)_complete.tex"
	@printf '\\usepackage{booktabs}\n' >> "$(BASENAME)_complete.tex"
	@printf '\\usepackage{siunitx}\n' >> "$(BASENAME)_complete.tex"
	@printf '\n' >> "$(BASENAME)_complete.tex"
	@printf '\\begin{document}\n' >> "$(BASENAME)_complete.tex"
	@printf '\n' >> "$(BASENAME)_complete.tex"
	@cat "$(BASENAME)_raw.tex" >> "$(BASENAME)_complete.tex"
	@printf '\n' >> "$(BASENAME)_complete.tex"
	@printf '\\end{document}\n' >> "$(BASENAME)_complete.tex"
	@rm "$(BASENAME)_raw.tex"
	@echo "Created $(BASENAME)_complete.tex"

# Compile LaTeX file to PDF
compile:
	@if [ ! -f "$(FILE)" ]; then \
		echo "Error: File $(FILE) not found!"; \
		exit 1; \
	fi
	@echo "Compiling $(FILE) to PDF..."
	pdflatex "$(FILE)"
	@if [ -f "$(BASENAME).aux" ]; then \
		echo "Running second pass for references..."; \
		pdflatex "$(FILE)" > /dev/null; \
	fi
	@echo "Created $(BASENAME).pdf"

# Clean build artifacts but keep PDFs
clean:
	@echo "Cleaning build artifacts..."
	rm -f *.aux *.log *.out *.toc *.nav *.snm *.fls *.fdb_latexmk *.synctex.gz
	@echo "Build artifacts cleaned (PDFs preserved)"

# Show help
help:
	@echo "Available targets:"
	@echo "  convert FILE=input.md   - Convert markdown file to LaTeX"
	@echo "  compile FILE=input.tex  - Compile LaTeX file to PDF"
	@echo "  clean                   - Remove build artifacts (keep PDFs)"
	@echo ""
	@echo "Examples:"
	@echo "  make convert FILE=table.md"
	@echo "  make compile FILE=table_complete.tex"
	@echo "  make clean"