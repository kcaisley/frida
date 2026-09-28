# Documentation build manifest

Run the documentation build from this directory:

```bash
make
```

The default target builds generated image collateral first, then builds all slide/document PDFs. Source files are kept in `docs/`, `docs/slides/`, and `docs/images/`. Finished image PDFs are kept in `docs/images/`; complete slide/document PDFs and their LaTeX build files are written to `docs/tex/`.

For any image PDF target or the `figures` and `netlistsvgs` targets, use `DEBUG=1` to retain TeX build logs and temporary netlistsvg SVGs
and render a 200 DPI PNG preview of each PDF's first page. Previews go to
`build/docs/images/previews/`, mirroring the path under `docs/images/`. This
also works when the PDF already exists. Remove previews and image build
intermediates without removing the TeX sources or PDFs with:

```bash
make -C docs clean-image-debug
```

Normal builds do not create PNG previews. The source `arch.png` remains in
`docs/images/` because the root README embeds it.

## `netlistsvg`

Inputs:

- `images/*_netlistsvg.v`
- `images/*_netlistsvg.json`

Flow:

```text
.v -> yosys -> .json -> netlistsvg -> temporary .svg -> rsvg-convert -> .pdf
.json -> netlistsvg -> temporary .svg -> rsvg-convert -> .pdf
```

Outputs:

- `images/*_netlistsvg.json` for JSON generated from Verilog inputs
- `images/*_netlistsvg.pdf`

Notes:

- `images/preamp_netlistsvg.svg` and `images/preamp_netlistsvg.pdf` are curated analog renders and are intentionally not regenerated from `images/preamp_netlistsvg.v`, because the automatic Yosys/netlistsvg path loses the MOS-symbol styling.
- The makefile sanitizes unsupported bidirectional/inout directions in netlistsvg JSONs before rendering. Generated SVGs are temporary files under `build/docs/images/` and remain there in debug mode; curated SVG inputs remain in `images/`.

## SPI diagrams

Inputs:

- `images/spi_register_timing.tex`
- `images/spi_register_bitfield_memory_path.tex`

Flow:

```text
.tex -> latexmk -> .pdf
```

Outputs:

- `images/spi_register_timing.pdf`
- `images/spi_register_bitfield_memory_path.pdf`

The timing waveform uses `tikz-timing` and shows the first two and final two
bits of a 180-bit transfer. The register map uses the LaTeX `bytefield` package
to group the mux, repeated seven-bit ADC configurations, and four shared DAC
states. An indexed range formula identifies all sixteen ADC fields, and a
dotted leader expands ADC0 into its seven control bits.
`tikzpackets` is a TikZ-native option for packet
layouts, but `bytefield` fits this register map more directly. Both packages
used here are provided by the local TeX Live.

## TeX image figures

Inputs:

- `images/*.tex`

Flow:

```text
.tex -> latexmk -> .pdf
```

Outputs:

- `images/*.pdf`

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
