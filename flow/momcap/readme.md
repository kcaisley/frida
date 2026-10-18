# Status

| Feature | Status | File | Notes |
|---|---|---|---|
| Netlist generator | ✓ | [subckt.py](subckt.py) | `MomStyle` (difference, ring, strip) and `MomCap`, the ideal plate-to-plate view the CDAC's leaves use. |
| Netlist tests | ✓ | [test_subckt.py](test_subckt.py) | The ideal leaf keeps its shield terminal. |
| Layout generator | ✓ | [layout.py](layout.py), [`stems/capcell.py`](../layout/stems/capcell.py) | Test structures drawn by the stems engine from the PDK's rules: the plates on the top 1-3 MOM metals (`tech.MOM_LAYERS`) at the minimum width and a chosen spacing, one via per metal at each terminal's end, a solid shield plate on the metal below, every terminal a labelled pin. The CDAC's own difference unit (shield mesh, access landings) is in the same module. |
| Layout tests | ✓ | [test_layout.py](test_layout.py) | Dimensions hold a via in a minimum finger; every terminal labelled and every stack joined; the netlist's terminal pairs. |
| PEX runner | ✓ | [pex.py](pex.py) | `momcap_characterization`: every style at 1-3 metals, six lengths (1-32 µm) at the minimum spacing and three (2, 8, 32 µm) at 1.5, 2 and 3 times it, in the three PDKs with Calibre 3D extraction (405 layout-only xACT 3D runs by the structures' own net names, `flow/layout/calibre_pex.py`); about an hour on eight licences. |
| Analysis | ✓ | [analysis.py](analysis.py) | `MeasMomcap`; `analyze_momcap_fit`: C = (α/s + β) L + γ over all lengths and spacings (relative least squares), and each spacing's own affine fit. |
| Plots | ✓ | [plots.py](plots.py) | Capacitance against length at the minimum spacing with the model and its error; capacitance per length against spacing; per-length capacitance across PDKs. Run by `flow.analysis.runner momcap_characterization_study`. |
| Analysis tests | ✓ | [test_analysis.py](test_analysis.py) | Structures that follow the model exactly give back α, β, γ and every spacing's fit; every plot renders. |

## The model the generators use

`tech.MOM_MODEL[style, layers]` holds rows (spacing nm, slope fF/µm, intercept fF): in the three extracted PDKs each extracted spacing's own length fit; the CDAC (`flow.caparray.layout.mom_array_params`) interpolates them in 1/s at the spacing it draws. α/s + β summarises the trend but misses individual spacings by up to a tenth (the extraction's spacing-dependent width bias), so the generator uses the measured rows. A PDK that calibrates its production unit itself (`tech.MOM_FITS`, which its LVS deck checks) keeps that calibration.

The PDKs without 3D extraction get rows at 1, 1.5, 2 and 3 times their own minimum spacing from the α/s + β fits of the extracted ones evaluated at those spacings: TPSC65 from TSMC65 (same node), IHP130 and LF150 interpolated geometrically in log(node) between TSMC65 and Tower180. They are estimates until those PDKs are extracted.

## Results (run 20261018_021950)

Per-length capacitance at each PDK's minimum spacing, fF/µm for one, two and three stacked metals:

| PDK | Spacing (nm) | Difference | Ring | Strip | α/s + β misses a spacing by |
|---|---|---|---|---|---|
| TSMC28 | 50 | 0.138 / 0.285 / 0.431 | 0.139 / 0.286 / 0.432 | 0.074 / 0.149 / 0.222 | up to 8 % |
| TSMC65 | 100 | 0.178 / 0.362 / 0.546 | 0.177 / 0.362 / 0.545 | 0.097 / 0.194 / 0.290 | up to 12 % |
| Tower180 | 280 | 0.196 / 0.405 / 0.612 | 0.193 / 0.400 / 0.605 | 0.107 / 0.220 / 0.333 | up to 7 % |

The ring and the difference unit match (both inner fingers face the ring on two sides); the strip is about half (one neighbour). Every stacked metal adds the same per-length capacitance. The thicker 180 nm metals at almost three times the spacing give slightly more than 65 nm. TSMC65's production unit (`MOM_FITS`, 0.17 / 0.34 / 0.51 with its shield mesh) is 4-7 % below these solid-shield test structures. The ends add 0.01-0.3 fF (gamma), most in the thick 180 nm stack. The slides are in `docs/slides/2026_09_08_ringfmom.tex` (the last four), the figures in `build/analysis/momcap/<run>/`.
