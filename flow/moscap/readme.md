# Status

| Feature | Status | File | Notes |
|---|---|---|---|
| Netlist generator | ✓ | [subckt.py](subckt.py) | Decoupling capacitors between the rails (gate on the other rail) and two-net capacitors, NMOS, PMOS or both, in parallel units. |
| Netlist tests | ✓ | [test_subckt.py](test_subckt.py) | Decap and two-net wiring, units, invalid capacitors. |
| Testbench generator | ✓ | [sim.py](sim.py) | BAG's MOS capacitor characterization: the AC stimulus on vdd (a decap) or on the gate plate (a two-net capacitor) at its DC bias; the stimulated source's current is the admittance. |
| Simulation runners | ✓ | [sim.py](sim.py) | `moscap_characterization`: operating point and AC response (1 MHz–100 GHz) of the decaps at supplies from 1/12 of the core supply to 108 % of it and the two-net capacitors at plate biases between ± the core supply, in each PDK (76 runs per PDK, all 456 in two minutes on 16 workers); `check=True` runs Spectre's static checks at the nominal bias. |
| Analysis | ✓ | [analysis.py](analysis.py) | `MeasMosCap`; `analyze_moscap_cv` (capacitance, quality factor and series resistance near 1 GHz, quality corner, leakage, and their spectra). In inversion: about 25 fF for two NMOS units in TSMC65 (6 fF in TSMC28, 67–187 fF in the other four), against 5 fF in accumulation. lf150's models and tower180's PMOS (`cap_p`) carry neither AC loss nor gate leakage: an infinite quality factor, no series resistance or corner, no leakage to draw. |
| Plots | ✓ | [plots.py](plots.py) | One panel per case: C-V with leakage, capacitance and quality factor versus frequency, loss versus bias; one figure set per PDK. Run by `python -m flow moscap.characterization_study`. |
| Analysis tests | ✓ | [test_analysis.py](test_analysis.py) | A series RC of known capacitance, resistance and corner; every plot renders. |
| Layout generator | ✓ | [layout.py](layout.py) | Standard-cell rows with cIcCreator, laygo and ALIGN from hand-written floorplans (`design/layout/moscap_*.json`). |
| Layout tests | ✓ | [test_layout.py](test_layout.py) | Target registry; every floorplan places each netlist device once and escapes every connected port; every PDK writes every case. |
| Layout runner | ✓ | [layout.py](layout.py) | Four cases in all six PDKs, all 72 layouts DRC clean and LVS correct. A decap's gate on the other rail is an M1 strap into that rail inside the cell. |
| DRC runner | ✓ | [layout.py](layout.py) | gdscheck and the PDK's DRC for every layout (`row_signoff`). |
| LVS runner | ✓ | [layout.py](layout.py) | The PDK's LVS for every layout against the netlist the build placed. |
| PEX runner | ✗ | - | No extraction. |

Inspiration: BAG `mos_cap`, `decap`, `decap_array`; the boost capacitor of the sampler's bootstrap.
