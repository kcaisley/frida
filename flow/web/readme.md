# Status

| Feature | Status | File | Notes |
|---|---|---|---|
| Data | ✓ | [../sweep/runner.py](../sweep/runner.py) | `python -m flow.web export` is `python -m flow.sweep table`: each block's newest sweep (`build/sweep/<block>/<run>/`) as one table (`build/web/data/sweep/<block>.json`): a row per instance with its PDK, topology and sizing, the parameters that differ between instances, and every metric; each condition sweep's axis limits over all instances. And a file per instance (its parameters, metrics, condition sweeps, waves, layout and error), its ALIGN layout flattened onto the PDK's generic layers ([export.py](export.py)), its schematic and netlist, and the index of its waveform measurements. Nothing is simulated or laid out. |
| Server | ✓ | [\_\_main\_\_.py](__main__.py) | `serve` answers `/` from `static/`, `/data/` from `build/web/data`, and `/api/wave` with one record of a cached measurement's waveforms, read from its HDF5 file under `build/` when asked for (every k-th sample past 20 000). |
| Explorer | ✓ | [static/index.html](static/index.html), [static/js/explorer.js](static/js/explorer.js) | The page "Explorer": the blocks with a sweep; the chosen block's instances in one table (pinned to its tools column: pin, Open). A column header sorts either way and filters: tick the values to keep (PDK, topology, sizing, categorical parameters; "only" keeps one), or bound a numeric column. Beside it a scatter plot of any metric or numeric parameter against any other (log axes offered for positive columns, chosen for those spanning two decades), coloured by PDK in `CURVE_COLORS` order and marked by topology, on `flow/analysis/plots.py`'s paper. Hovering a row rings its point; hovering a point lights its row and scrolls to it; clicking a point or a row's pin pins it, ringed and labelled, across axis changes and reloads. Filters, sort, axes and pins persist per block in the browser. |
| Instance page | ✓ | [static/detail.html](static/detail.html), [static/js/detail.js](static/js/detail.js) | `detail.html?block=<block>&id=<pdk>__<topology>__<sizing>`, opened from a row: in a tab of its own: GoldenLayout panels for its summary (one table: its parameters, metrics with SI units, the ALIGN layout's size and signoff; the error of a failed instance), its condition sweeps (Analyses) on the axes every instance of the block shares (SI prefixes from the shared limits), and the shared views below on the instance alone. |
| Waveforms | ✓ | [static/js/traces.js](static/js/traces.js) | The instance's transient runs, after Surfer's waveform viewer: every net and supply current a row on one time axis, its name, range and controls beside it (hidden rows back from +), analog or digital (mid-swing threshold); wheel zoom, drag pan, right-drag span, a cursor reading every row and a marker for Δt. |
| Layout | ✓ | [static/js/layout2d.js](static/js/layout2d.js) | Canvas of the merged layers, the front end under the metals, translucent fills with a screen-fixed hatch; pan, zoom about the cursor, zoom to a box (right-drag), fit (F), ruler (K, as KLayout), pin labels (L), the shape under the cursor and its size. |
| 3D | ✓ | [static/js/layout3d.js](static/js/layout3d.js) | three.js, each layer extruded between nominal heights (an even stack, the same for every PDK), adjustable vertical scale, orbit, PNG export. Not checked by eye here: headless Chromium on this machine draws no WebGL geometry. |
| Schematic | ✓ | [static/js/panels.js](static/js/panels.js) | The instance's transistor schematic (pan, zoom), or the netlist its layout was built from. |
| Layers | ✓ | [static/js/layers.js](static/js/layers.js) | The shown layers with their fills, toggled (alt-click: only that one) or in groups, for the 2-D and 3-D views together. |
| Theme | ✓ | [static/style.css](static/style.css) | The desktop's, on both pages: dark in Nord, light in Zed's One Light; plots on Nord's dark paper in the dark theme. |
| Tests | ✓ | [test_export.py](test_export.py) | JSON conversion and thinning, layer flattening and merging on a synthetic layout, waveform indexing and serving, the server's path mapping, pinned library versions on both pages. |

Libraries come from jsDelivr at pinned versions (GoldenLayout 2.6.0, three.js 0.160.0, Plotly 2.35.2), so the browser needs the internet; the data stays on this machine.

## Use

```sh
uv run python -m flow.sweep run --blocks comp      # characterize every instance (56 workers)
uv run python -m flow.sweep layout --blocks comp   # ALIGN layouts, signed off; area and density
uv run python -m flow.web export                   # the tables and instance files
uv run python -m flow.web serve --port 8765
```

From another machine, forward the port (`ssh -L 8765:localhost:8765 <host>`) and open <http://localhost:8765>.
