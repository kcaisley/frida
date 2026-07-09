# Documentation build manifest

Run the documentation build from this directory:

```bash
make
```

The default target builds generated image collateral first, then builds all slide/document PDFs. Source files are kept in `docs/`, `docs/slides/`, and `docs/images/`. Generated image outputs are kept in `docs/images/`; complete slide/document PDFs and LaTeX build collateral are written to `docs/tex/`.

## `netlistsvg`

Inputs:

- `images/*_netlistsvg.v`
- `images/*_netlistsvg.json`

Flow:

```text
.v -> yosys -> .json -> netlistsvg -> .svg -> rsvg-convert -> .pdf
.json -> netlistsvg -> .svg -> rsvg-convert -> .pdf
```

Outputs:

- `images/*_netlistsvg.json` for JSON generated from Verilog inputs
- `images/*_netlistsvg.svg`
- `images/*_netlistsvg.pdf`

Notes:

- `images/preamp_netlistsvg.svg` and `images/preamp_netlistsvg.pdf` are curated analog renders and are intentionally not regenerated from `images/preamp_netlistsvg.v`, because the automatic Yosys/netlistsvg path loses the MOS-symbol styling.
- The makefile sanitizes unsupported bidirectional/inout directions in netlistsvg JSONs before rendering with the current `netlistsvg` CLI.

## WaveDrom

Inputs:

- `*.json` in `docs/`
- selected WaveDrom JSON files in `docs/images/`

Flow:

```text
.json -> wavedrom-cli -> .svg -> rsvg-convert -> .pdf -> pdftoppm -> .png
```

Outputs:

- `images/*.svg`
- `images/*.pdf`
- `images/*.png`

## TeX image figures

Inputs:

- `images/*.tex`

Flow:

```text
.tex -> latexmk -> .pdf -> pdftoppm -> .png
```

Outputs:

- `images/*.pdf`
- `images/*.png`

Temporary LaTeX intermediates in `images/` are removed by the makefile cleanup step.

## TeX slides and documents

Inputs:

- `slides/*.tex`

Current slide/document sources include:

- `slides/2026_01_28_design.tex`
- `slides/2026_02_17_pcb.tex`
- `slides/2026_03_18_dpg.tex`
- `slides/2026_06_25_bringup.tex`
- `slides/2026_07_07_fsic.tex`
- `slides/2026_07_09_measurement.tex`
- `slides/beams.tex`
- `slides/detectors.tex`

Flow:

```text
slides/*.tex + generated image collateral -> latexmk -> tex/*.pdf
```

Outputs:

- `tex/*.pdf`
- LaTeX build collateral in `tex/`

The source `slides/*.tex` files should remain free of generated PDFs and LaTeX intermediate files.

## Mermaid diagrams

Inputs:

- `*.md` files containing Mermaid diagrams, when built explicitly as PNG targets

Flow:

```text
.md -> mmdc -> .png
```

Outputs:

- `*.png` next to the Markdown source, for explicit targets only
