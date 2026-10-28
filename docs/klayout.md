# KLayout technology notes

- GDS Layer Numbers: Physical layer numbers and datatypes (e.g., `"M1": {"number": 15, "datatype": 0}`)
- Layer Connectivity: Stack ordering relationships (`"previous": "CO", "next": "VIA1"`)
- Material Classifications: Layer material types (`"metal"`, `"poly"`, `"diffusion"`, `"cut"`, `"implant"`, `"marker"`)
- Pin Layer Mappings: Associated pin/label layer datatypes for electrical connectivity
- Display Properties: Layer colors and fill patterns for visualization in KLayout
- Minimum Widths: Layer-specific minimum feature sizes
- Spacings: Minimum separation between features on same layer
- Enclosure Rules: Via enclosure and opposite-side clearance requirements
- Via Specifications: Via sizes, spacings, and placement rules for each via level
- Gate Rules: Minimum gate lengths, finger spacing, and poly extension requirements
- Routing Grid: Horizontal and vertical grid alignment requirements
- Cell Spacing: Standard cell height and digital placement constraints
- Capacitor Rules: Special width and spacing requirements for precision capacitors
- Implant Rules: Well and threshold voltage layer enclosure requirements
- Available Devices: Supported device types (`"nch"`, `"pch"`, `"mres"`, etc.)
- Port Mappings: Device terminal names and order (`["d","g","s","b"]`)
- Parameter Mapping: Translation between layout parameters and schematic properties
- Device Inheritance: Base device definitions that can be specialized
- PDK Library Name: Technology library identifier for device models
- Process Node: Technology node specifications and gamma correction factors
- Property Mapping: Parameter name translations between tools
- Layer properties are saved in a .lyp file. It can be produced using a Cadence .tf, display.df, and .layermap file
  - .lyp is a XML file, essentially
  - The code is in [KLayout's `tf_import` repository](https://github.com/klayoutmatthias/tf_import)
- Once shape (rects, polygons, paths, labels) are written to a cell, the database unit is multiplied if they are the integer (non D-) types
- Layers are attached to the ly = db.Layout() object via `layer1 = ly.layer(1, 2, "Poly")`
- You can get info of a layer with `ly.get_info(layer1)`
- Layouts contain a layers list, and a shapes list for each layer
- Each shapes list contains the geometries (boxes, polygons, paths, and labels) which are on that layer
- Can I define a cell, but not place instances of it?
  - I don't think so. What happens is that when you first declare a geometric object, it doesn't belong to a cell, and so nothing exists in the layout
  - But once you create a layout and create a cells, and insert the geometry to the shape list of the cells, it now exists in the layout.
  - However, if you now declare a higher level cell, and instance the original cell twice within it, when you go to open the layout, it will show the top level hierarchy cells, and the two instance of it
- Concepts like pins and named instances are not part of the GDS and OASIS specification and that still is the basis of the program. It's possible to emulate those features (and others like net information) with user properties, but the interpretation of those is strongly dependent on the tools reading these files.

## Extraction: KLayout-PEX and FasterCap

A layout extracted by its own net names (`flow.layout.signoff.run_layout_pex`: the MOM test structures, the ADC arrays) goes to FasterCap through KLayout-PEX (`flow/layout/kpex.py`) by default; `Extractor.CALIBRE` asks for the kit's own extractor instead (Calibre's xACT, or Quantus in LF150), which stays the manual check of it.

- The stack: each PDK's `pdk/<pdk>/kpex/stack.json` (private), its conductors' heights and thicknesses and the planar dielectrics of its kit's typical interconnect corner, read from the kit's ICT file (`python -m flow.layout.kpex stack <ict> PO=poly M1=metal1 ...`; a conductor without a height sits in the dielectric before it, its top at theirs). The layers, vias and pin labels are the PDK's layout tech's (`LAYERS`, `RULES`, `PIN_TEXT`).
- The model: kpex holds one dielectric between two metals, so each metal level gets its own as a film around the metal filling the level (the slabs' mean by thickness: the field between neighbours runs along them) and the via level above it another (the slabs in series: the field between levels crosses them).
- The run: kpex's own Python (`KPEX_HOME`, `-P` so that this folder's `kpex.py` does not shadow its protobuf package) runs `kpex_extract.py`: KLayout joins the conductors through the vias and names the nets by the labels, kpex builds FasterCap's model, FasterCap (`FASTERCAP`) solves it at a tolerance of 0.005 and a mesh refinement of 0.1, Galerkin's scheme. FasterCap's Maxwell matrix leaves each net's capacitance to infinity in its row sum: that goes to ground, as an extractor whose substrate is an infinite plane counts it.
- The netlist: Spectre capacitors between the nets by their labels, ground `0`, as the kits' extractors write theirs, so `flow.momcap.pex.pair_capacitances` and `flow.caparray.pex.parse_caparray_pex` read either.
- Against the kits' extractors (2026-10-27; 8 µm MOM test structures, a ring on two metals and a difference unit on three in each PDK, five structures in TSMC65, couplings above 0.05 fF): the plates' couplings, which a CDAC's weights are, agree to a median of -0.6 % (Tower180), -0.8 % (TPSC65), -2.3 % (TSMC28), +4.6 % (LF150) and -5.2 % (TSMC65, every plate between -6.1 and -4.6 %: a systematic offset of the stack, not noise); IHP130's 135 structures to -0.65 to -0.9 % (FasterCap's couplings below 0.3 fF move by up to 7 % with its tolerance, so neither extractor is the reference there). The shield's couplings agree within -8 to +11 % (TSMC28's one short structure +28 %), and the split of a net's ground most loosely (tens of percent): a kit's extractor counts an enclosed finger's field to the substrate where FasterCap ends it on the enclosing frame. TSMC28's difference unit did not finish (FasterCap's mesh outgrew 35 GB).
