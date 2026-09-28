# Documentation build manifest

Run the documentation build from this directory:

```bash
make
```

The default target builds generated image collateral first, then builds all slide/document PDFs. Source files are kept in `docs/`, `docs/slides/`, and `docs/images/`. Finished image PDFs are kept in `docs/images/`; complete slide/document PDFs and their LaTeX build files are written to `docs/tex/`.

For any image PDF target or the `figures`, `sequences`, and `netlistsvgs` targets, use `DEBUG=1` to retain TeX build logs and temporary netlistsvg SVGs
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

## ADC sequencer timing

From the repository root, generate and render the seven 160-symbol sequences
used by the recent `frida1_sequence` and `frida2_sequence` PEX simulations:

```bash
make -C docs sequences
```

Use `make -C docs DEBUG=1 sequences` to retain LaTeX logs and render PNG
previews while developing the figures. Rerun without the option to remove
the LaTeX intermediates, or run `make -C docs clean-image-debug` to remove
those and the previews together.

The generator is `docs/images/sequences/render.py`. It reads recipes from
`flow/adc/sequences.py` and writes only `tikz-timing` TeX. Each figure shows
four symbols before index 0 and eight after the next period begins. The dashed
red lines mark the sequence boundaries. Vertical guides occur every four
symbols; dotted horizontal guides mark each signal's low and high levels.
Triangular arrows mark both edges of `comp` and rising edges of `logic`.
The seven TeX/PDF pairs and the Python generator live in
`docs/images/sequences/`; debug previews live under `build/`.

For another named recipe, use `--sequence NAME --name my_timing`. For literal
rows, pass `--init`, `--samp`, `--comp`, and `--logic` binary strings. Put
one-off results outside the image directory:

```bash
uv run python docs/images/sequences/render.py \
  --output-dir build/analysis/sequences/custom --name my_timing \
  --init 11110000 --samp 00001111 --comp 00110011 --logic 00010001
latexmk -pdf -outdir=build/analysis/sequences/custom \
  build/analysis/sequences/custom/my_timing.tex
```

Python callers can also construct `flow.adc.sequences.AdcSequence` and pass it
to `render(sequence, "my_timing", output_dir=...)` from the generator module.

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
