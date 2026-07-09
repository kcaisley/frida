# Schematic drawing conventions

These notes capture the preferred style for hand-drawn schematic and block-diagram figures in this repository, especially Circuitikz figures used in presentations.

## General style

- Prefer clean analog-schematic aesthetics over auto-generated-looking wiring.
- Use Circuitikz for transistor-level schematics and TikZ for block diagrams.
- Use European Circuitikz mode for schematics:
  ```tex
  \usepackage[european]{circuitikz}
  ...
  \begin{circuitikz}[scale=1, european]
  ```
- Use `scale=1` unless there is a strong reason not to.
- Prefer coordinates on integer or half-integer grid points where practical, but do not force ugly transistor geometry just to make every anchor land exactly on the grid.
- Use default `nmos` and `pmos` symbols. Do not tune MOS geometry to force grid alignment; the tuned symbols looked bad.
- Use actual Circuitikz anchors (`.D`, `.S`, `.G`) for wiring, rather than guessing where terminals visually end.

## Transistor placement philosophy

- Place important circuit nodes explicitly, then anchor devices by the terminal connected to that node.
- For shared drain nodes, define a coordinate and place both devices by `anchor=D`:
  ```tex
  \coordinate (XP) at (0,2);
  \node[pmos, anchor=D] (mp_xp) at (XP) {};
  \node[nmos, anchor=D] (mn_inn) at (XP) {};
  ```
- Derive intermediate nodes from real device anchors instead of hard-coding positions:
  ```tex
  \coordinate (SRCMID) at ($(mn_inn.S)!0.5!(mn_inp.S)$);
  \node[nmos, anchor=D] (mn_tail) at (SRCMID) {};
  ```
- Connect wires to terminal anchors (`mn_inn.S`, `mp_xp.G`, etc.). This avoids small visual stubs and misalignments caused by the internal dimensions of Circuitikz symbols.
- Mirroring devices is acceptable when it improves schematic readability. For example, mirror PMOS load/precharge devices so their gates point inward.

## Wires and routing

- Keep routing horizontal and vertical by default.
- Avoid arbitrary diagonal wires. For a double-tail latch, diagonal wires should only be used for intentional cross-coupled connections.
- Keep source/drain/gate stubs short. Do not add unnecessary wire length just to label a net.
- Output nodes may have short horizontal stubs if they improve readability, but avoid drawing extra wires over MOS terminal stubs because overdraw can make one side look visually thicker.
- Use consistent wire widths. Current preferred styles:
  ```tex
  wire/.style={line width=0.7pt},
  transistor/.style={line width=0.7pt},
  rail/.style={line width=1.4pt},
  ```
- For differential circuits, keep the left/right halves visually symmetric unless an intentional asymmetry is being explained.
- Route bias and clock signals from the outside edge toward device gates; avoid routing labels through the interior of the analog core.

## Rails and supply symbols

- Do not use Circuitikz `node[vdd]` for VDD rails in presentation schematics; it renders as an upward arrow.
- Prefer manually drawn thick horizontal VDD rails:
  ```tex
  \draw[rail] ($(vdd_xp)+(-0.5,0)$) -- ($(vdd_xp)+(0.5,0)$);
  ```
- Keep the vertical connection from device source to VDD rail short.
- Use the standard Circuitikz `ground` node for ground.
- Keep the ground connection stub short; avoid long dangling vertical wires before the ground symbol.
- American and European Circuitikz modes render `node[vdd]` and `node[ground]` identically, so the manual rail is intentional.

## Text, fonts, and labels

- Net names should be lowercase, monospace, and compact, e.g. `inn`, `inp`, `xp`, `xn`, `clk`.
- Device annotations should be monospace, left-aligned, and split over three lines:
  ```tex
  MP1\\w=120n\\l=100n
  ```
- Use compact nanometer notation with no spaces and no `m`: `w=480n`, not `w=480 nm`.
- Use `\ttfamily\footnotesize` for both net labels and device annotations unless the figure becomes too crowded:
  ```tex
  netlabel/.style={font=\ttfamily\footnotesize},
  devlabel/.style={font=\ttfamily\footnotesize, align=left},
  ```
- Device label clumps should be placed close to their devices but not overlap wires or neighboring labels.
- When possible, align clumps by their left edge (`align=left`, with an explicit `anchor=west` or `anchor=east` placement) so the device name, `w=...`, and `l=...` form a readable column.

## Block-diagram style

- Use TikZ rather than screenshots when the figure is explanatory instead of documentary.
- Prefer a small set of reusable styles for blocks, artifacts, arrows, terminal boxes, and callouts.
- Keep block diagrams left-to-right for flow/process slides and top-to-bottom only when it reduces crossing arrows.
- Use rounded rectangles and the presentation palette consistently; avoid mixing arbitrary fill colors.
- Put command-line or generated-file snippets in monospace terminal-like boxes, not free-floating text.
- Use short labels on arrows. Put detailed explanations in slide notes, captions, or surrounding text.
- If a diagram is used in a final deck, keep either the generating `.tex` source or a short note describing the generation path.

## Example sizing conventions

### 65 nm dynamic preamp

Assume a 65 nm process with:

- Base width: `60n`
- Minimum length: `100n`

For the 5-transistor preamp example:

- `MP1`, `MP2`: width `2x`, length `1x` → `w=120n`, `l=100n`
- `MN1`, `MN2`: width `8x`, length `1x` → `w=480n`, `l=100n`
- `MN3`: width `4x`, length `2x` → `w=240n`, `l=200n`

### 28 nm PMOS-input preamp

The PMOS-input example used in the FSiC 2026 deck uses:

- `MP1`, `MP2`: `w=480n`, `l=100n`
- `MP3`, `MP4`: `w=240n`, `l=200n`
- `MN1`, `MN2`: `w=120n`, `l=100n`

## Canonical local examples

Current reference implementations:

- 65 nm dynamic preamp source: [`docs/images/preamp_test.tex`](images/preamp_test.tex)
- 65 nm dynamic preamp PDF: [`docs/images/preamp_test.pdf`](images/preamp_test.pdf)
- 28 nm PMOS-input preamp source: [`docs/images/preamp_pmos.tex`](images/preamp_pmos.tex)
- 28 nm PMOS-input preamp PDF: [`docs/images/preamp_pmos.pdf`](images/preamp_pmos.pdf)
- Comparator testbench PDF used in the FSiC deck: [`docs/images/comp_testbench.pdf`](images/comp_testbench.pdf)

Use these as starting points for future comparator/preamp schematics rather than redrawing from scratch.

## Cleanup and regeneration plan

Keep source files only for figures that are canonical or expected to be edited again. For the FSiC 2026 deck:

1. Keep the retained rendered PDFs that are directly referenced by `docs/slides/2026_07_07_fsic.tex`.
2. Keep `.tex` sources for the canonical preamp schematics (`preamp_test.tex` and `preamp_pmos.tex`) because they encode the drawing conventions.
3. Treat temporary visual checks (`*_check*.png`, `*_render*.png`, ad-hoc compact variants) as disposable.
4. Recreate comparator and double-tail Circuitikz sources later only if those schematics return to the final deck or become canonical documentation figures.
5. For block diagrams such as `adc_block.pdf`, `adc_discrete_model.pdf`, and `arch.pdf`, either keep their original editable source if available or document the generation path before deleting intermediary files.
