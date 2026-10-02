# Capacitor figure generation

`capacitor_views.png` and `capacitor_views.pdf` combine the plan and three-layer perspective side by side of a shortened MOM capacitor element. The editable source is `/local/frida/build/summary_adc_figures/render_capacitor.py`; `/local/frida/build/summary_adc_figures/capacitor_views.tex` assembles its two views. Sources and intermediate outputs remain together in that build directory.

The Python source uses the existing `_insert_ring` and `_insert_box` helpers from `flow/caparray/laygen.py` to write `capacitor_toy.gds`. Both views then read that same GDS through KLayout. This is an illustrative shortened cell, not an extraction of the full ADC layout. Blue identifies the common electrode; orange identifies the separate main and difference electrodes. Opposite switching gives an effective element capacitance of C_eff,N = C_N,main − C_N,diff; capacitances are not calculated by this renderer.

The GDS stores three repeated metal planes and two sets of inter-plane vias. Semantic layers 200/201/202 identify common/main/difference metal on the lowest plane, 210/211/212 on the middle plane, and 220/221/222 on the highest plane. Layers 203/204/205 and 213/214/215 contain vias for the corresponding electrodes. Each inner strip has two vias near its outer end, away from the main/difference split, following docs/images/diffcaps.png. Common-electrode vias are near the outer ends of both ring rails. The stack contains 16 interlayer vias in total; vias use Nord grey in both views. These are drawing roles, not foundry layer numbers. The source supplies illustrative metal thickness and vertical pitch; dielectric, shielding, substrate and external routing are omitted.

The plan view uses vector Matplotlib rectangles. The perspective uses Matplotlib's orthographic 3D projection, Nord colors, and face lighting. Each cuboid face, including its underside, is split into triangles and rasterized with a shared per-pixel depth buffer. This replaces the previous average-depth face sorting, which incorrectly placed portions of long orange faces in front of blue rails. Rendering at 600 dpi and averaging each 2 × 2 group produces an antialiased 300 dpi image. The perspective PDF embeds this raster; the plan PDF remains vector. Every projected geometry vertex is checked against the canvas margins to catch cropping. A lower-resolution reversed-face-order render must match exactly; an independent ray/box intersection audit checks the nearest visible material and its lighting at sampled pixels. All via footprints must land fully within their matching electrodes on both adjacent metal planes. Black arrow annotations use Matplotlib’s LaTeX renderer and Computer Modern text; the combined side-by-side panel uses Latin Modern in TeX.

Regenerate from `/local/frida` using the existing virtual environment, KLayout Python module, Matplotlib, LaTeX and Poppler:

```bash
.venv/bin/python build/summary_adc_figures/render_capacitor.py
cd build/summary_adc_figures
pdflatex -interaction=batchmode -halt-on-error capacitor_views.tex
pdftoppm -r 220 -singlefile -png capacitor_views.pdf capacitor_views
cp capacitor_views.pdf capacitor_views.png ../../docs/images/report/
```

Inspect `capacitor_perspective.png` and the assembled `capacitor_views.png` after changing geometry or the camera. Labels identify the electrodes, metal stack, and interlayer vias. Keep provenance, layer assumptions, and omitted structures in the report caption. Blender is not needed for this workflow.
