# Status

| Feature | Status | File | Notes |
|---|---|---|---|
| Exporter | ✓ | [export.py](export.py) | Runs every block's characterization study (`flow.analysis.runner`, its pinned simulation run) once, recording the analyses each `plot_*` call is handed: one JSON per block of every result set per PDK and case (fields, and numeric properties such as hysteresis). The study's own figures as SVG. The newest layout per cell, PDK and generator from the layout runners' `summary.json` files (with their DRC and LVS results), flattened onto the generic layer keys of `layout/tech.py` and merged per layer, with its labels; each layout's netlist, and its schematic where it is transistors (`flow.util.netlist2image`). Every measurement the study reads that holds waveforms is indexed per PDK and instance (`traces.json`), each run named by the bench parameters that differ. About ten minutes for all twenty blocks on 16 workers; nothing is simulated or laid out. |
| Server | ✓ | [\_\_main\_\_.py](__main__.py) | `serve` answers `/` from `static/`, `/data/` from `build/web/data`, and `/api/wave` with one record of a cached measurement's waveforms, read from its HDF5 file under `build/` when asked for (every k-th sample past 20 000). |
| Application shell | ✓ | [static/js/app.js](static/js/app.js) | OpenROAD's web viewer as the model (toolbar, GoldenLayout's docked, stacked, maximisable panels, status bar), in Nord, dark or light (T); a panel not on the toolbar comes from its Panels menu. The panel arrangement and each block's selection persist in the browser. |
| Instances | ✓ | [static/js/panels.js](static/js/panels.js) | The page opens on it: every named instance of the block, the parameters that define it (or all of them), the PDKs with results and its layouts' signoff; rows select the instances shown everywhere else (alt-click: only that one; double-click: focus). |
| Selection | ✓ | [static/js/panels.js](static/js/panels.js) | PDKs and cases as chips, several at once (alt-click: only that one); the parameters that tell the cases apart, each value selecting its cases; the series (every selected PDK and case) with their line styles, hidden or removed one at a time; the focused case's description and parameters side by side. |
| Plot | ✓ | [static/js/plot.js](static/js/plot.js) | Plotly in `flow/analysis/plots.py`'s style: paper, black serif text, Nord curves in `CURVE_COLORS` order, inward ticks on all sides, `style_grid`'s grid; in the dark theme the same on Nord's dark paper. A result set's metric over the field it sweeps (the axis follows from the set; rise and fall, NMOS and PMOS, on and off together), every series overlaid (colour per case, dash and marker per PDK); curves over their own axis, one per sweep point, the points chosen as chips; single values per series. A plain sans font on screen; saved SVGs in Computer Modern. Units from the field names' suffixes, with SI prefixes on linear axes; log axes label decades of the base unit. Clicking a point leaves it out (its ring brings it back). SVG export, always on paper. |
| Results | ✓ | [static/js/plot.js](static/js/plot.js) | A result set's single values and the per-point ones at a chosen sweep point, one row per series; sortable, copied as tab-separated text. |
| Traces | ✓ | [static/js/traces.js](static/js/traces.js) | The focused instance's cached transient runs, after Surfer's waveform viewer: nets and supply currents chosen in a list, a row each on one time axis, analog or digital (mid-swing threshold); wheel zoom, drag pan, right-drag span, a cursor reading every row and a marker for Δt. |
| Layout | ✓ | [static/js/layout2d.js](static/js/layout2d.js) | Canvas of the merged layers, the front end under the metals, translucent fills with a screen-fixed hatch; pan, zoom about the cursor, zoom to a box (right-drag), fit (F), ruler (K, as KLayout), pin labels (L), the shape under the cursor and its size. Tiled: every selected series at one scale, a column per PDK, a row per case. A focused series without a layout gives way to the first selected one with. |
| 3D | ✓ | [static/js/layout3d.js](static/js/layout3d.js) | three.js, each layer extruded between nominal heights (an even stack, the same for every PDK: the export carries no thicknesses), adjustable vertical scale, orbit, PNG export. WebGL starts once the panel is shown. Not checked by eye here: headless Chromium on this machine draws no WebGL geometry, not even a bare three.js cube. |
| Schematic | ✓ | [static/js/panels.js](static/js/panels.js) | The focused series' transistor schematic (pan, zoom), or the netlist the layout was built from; standard-cell netlists (clkgen) have only the netlist. |
| Figures | ✓ | [static/js/panels.js](static/js/panels.js) | The study's Matplotlib figures per PDK. |
| Layers | ✓ | [static/js/layers.js](static/js/layers.js) | The shown layers with their fills, toggled (alt-click: only that one) or in groups, for the 2-D and 3-D views together. |
| Tests | ✓ | [test_export.py](test_export.py) | JSON conversion and thinning, datasets from recorded plot calls, layer flattening and merging on a synthetic layout, waveform indexing and serving, the server's path mapping, pinned library versions. |

Libraries come from jsDelivr at pinned versions (GoldenLayout 2.6.0, three.js 0.160.0, Plotly 2.35.2, CMU Serif), so the browser needs the internet; the data stays on this machine.

## Use

```sh
uv run python -m flow.web export            # all blocks; --blocks schmitt bias for a few, --no-figures to skip SVGs
uv run python -m flow.web serve --port 8765
```

From another machine, forward the port (`ssh -L 8765:localhost:8765 <host>`) and open <http://localhost:8765>. Export again after a study's pinned run or a layout changes.
