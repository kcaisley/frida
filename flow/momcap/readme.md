# Status

| Feature | Status | File | Notes |
|---|---|---|---|
| Netlist generator | ✓ | [subckt.py](subckt.py) | `MomStyle` (difference, ring, strip) and `MomCap`, the plate-to-plate view the CDAC's leaves use: ideal, or, where it `varies`, its value in a Monte Carlo, C (1 + A / √(C / 1 fF) z + g (x g_x + y g_y) / \|(g_x, g_y)\|) at its centroid (x, y): Pelgrom's mismatch drawn for each capacitor (Spectre's `mismatch` statistics: each subcircuit instance its own z) and a linear process gradient in a direction drawn once a run (`process`), with a probe whose operating point is the drawn value in fF. `variation(pelgrom, gradient_per_um)` gives a simulation the conditions, the drawn variables at 0 and the statistics; zero conditions give every capacitor its value. The variation is FRIDA's, not the kit's: the PDK's recognized ring-MOM device library (`ringfmom.cdl`) stays plain CDL for LVS. |
| Netlist tests | ✓ | [test_subckt.py](test_subckt.py) | The ideal leaf keeps its shield terminal; a varying leaf's expression reads the Monte Carlo's variables and probes its value; the variation's conditions and statistics. In Spectre (`flow/circuit/test_spectre.py`, opt-in): 400 runs of three leaves give Pelgrom's sigma (0.1 % at 1 %·√fF on 100 fF), independent draws, and the gradient's spread at 50 µm. |
| Layout generator | ✓ | [layout.py](layout.py), [`stems/capcell.py`](../layout/stems/capcell.py), [`align/pdk/mom.py`](../layout/align/pdk/mom.py) | Test structures drawn by ALIGN's `MomUnit` generator on cell_fabric grids from the PDK's rules (`capcell.mom_geometry`): the plates on the top 1-3 MOM metals (`tech.MOM_LAYERS`) at the minimum width and a chosen spacing, one via per metal at each terminal's end, a solid shield plate on the metal below, every terminal a labelled pin. The CDAC's own difference unit (shield mesh, access landings) is `DifferenceUnit` in the same module. |
| Layout tests | ✓ | [test_layout.py](test_layout.py) | Dimensions hold a via in a minimum finger; every terminal labelled and every stack joined; the netlist's terminal pairs. |
| PEX runner | ✓ | [pex.py](pex.py) | `momcap_characterization`: every style at 1-3 metals, six lengths (1-32 µm) at the minimum spacing and three (2, 8, 32 µm) at 1.5, 2 and 3 times it, in all six PDKs (810 layout-only 3D extractions by the structures' own net names: Calibre xACT with each kit's rules, `flow/layout/calibre_pex.py`, and Quantus's field solver on the Assura database in LF150); about an hour per three PDKs on eight licences. Calibre's field solver runs at accuracy 1 (`PEX_FS_ACCURACY`, set by `flow/layout/calibre_pex.py`): at its default it may split a few fF of a small coupling beside a large net to the substrate. |
| Analysis | ✓ | [analysis.py](analysis.py) | `MeasMomcap`; `analyze_momcap_fit`: C = (α/s + β) L + γ over all lengths and spacings (relative least squares), and each spacing's own affine fit. |
| Plots | ✓ | [plots.py](plots.py) | Capacitance against length at the minimum spacing with the model and its error; capacitance per length against spacing; per-length capacitance across PDKs. Run by `python -m flow momcap.characterization_study`. |
| Analysis tests | ✓ | [test_analysis.py](test_analysis.py) | Structures that follow the model exactly give back α, β, γ and every spacing's fit; every plot renders. |

## The model the generators use

`tech.MOM_MODEL[style, layers]` holds rows (spacing nm, slope fF/µm, intercept fF): in each PDK, each extracted spacing's own length fit; the CDAC (`flow.cdac.caparray.layout.mom_array_params`) interpolates them in 1/s at the spacing it draws. α/s + β summarises the trend but misses individual spacings by up to a tenth (the extraction's spacing-dependent width bias), so the generator uses the measured rows. A PDK that calibrates its production unit itself (`tech.MOM_FITS`, which its LVS deck checks) keeps that calibration.

## Results (run 20261018_acc1)

Per-length capacitance at each PDK's minimum spacing (that spacing's own length fit, the `MOM_MODEL` row), fF/µm for one, two and three stacked metals:

| PDK | Spacing (nm) | Difference | Ring | Strip | α/s + β misses a spacing by |
|---|---|---|---|---|---|
| TSMC28 | 50 | 0.134 / 0.276 / 0.415 | 0.135 / 0.276 / 0.415 | 0.073 / 0.147 / 0.218 | up to 8 % |
| TSMC65 | 100 | 0.172 / 0.357 / 0.541 | 0.172 / 0.356 / 0.540 | 0.094 / 0.189 / 0.281 | up to 12 % |
| TPSC65 | 100 | 0.192 / 0.350 / 0.473 | 0.192 / 0.350 / 0.473 | 0.106 / 0.188 / 0.250 | up to 8 % |
| IHP130 | 210 | 0.231 / 0.485 / 0.737 | 0.230 / 0.485 / 0.739 | 0.124 / 0.255 / 0.385 | up to 6 % |
| LF150 | 240 | 0.183 / 0.388 / 0.589 | 0.182 / 0.388 / 0.588 | 0.096 / 0.202 / 0.304 | up to 6 % |
| Tower180 | 280 | 0.201 / 0.405 / 0.615 | 0.201 / 0.406 / 0.615 | 0.110 / 0.220 / 0.329 | up to 10 % |

The ring and the difference unit match (both inner fingers face the ring on two sides); the strip is about half (one neighbour). Every stacked metal adds the same per-length capacitance. The thicker 130-180 nm metals at two to three times the spacing give as much as 65 nm or more, IHP130's thick metals the most. TSMC65's production unit (`MOM_FITS`, 0.165 / 0.357 / 0.546 with its shield mesh, refitted at accuracy 1 with fingers to 170 µm) is 4 % below these solid-shield test structures with one metal and within 1 % with two and three. The ends add 0.01-0.3 fF (gamma), most in the thick 180 nm stack. The slides are in `docs/slides/2026_09_08_ringfmom.tex` (the last four; TSMC65's refitted production unit is checked against its extraction on the tolerance slide), the figures in `build/analysis/momcap/<run>/`.
