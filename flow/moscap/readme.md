# Status

| Feature | Status | File | Notes |
|---|---|---|---|
| Netlist generator | ✓ | [subckt.py](subckt.py) | Decoupling capacitors between the rails (gate on the other rail) and two-net capacitors, NMOS, PMOS or both, in parallel units. |
| Netlist tests | ✓ | [test_subckt.py](test_subckt.py) | Decap and two-net wiring, units, invalid capacitors. |
| Testbench generator | ✓ | [sim.py](sim.py) | BAG's MOS capacitor characterization: the AC stimulus on vdd (a decap) or on the gate plate (a two-net capacitor) at its DC bias; the stimulated source's current is the admittance. |
| Simulation runners | ✓ | [sim.py](sim.py) | `moscap_characterization`: operating point and AC response (1 MHz–100 GHz) of the decaps at supplies 0.1–1.3 V and the two-net capacitors at plate biases −1.2 to 1.2 V (76 TSMC65 runs); `check=True` runs Spectre's static checks at the nominal bias. |
| Analysis | ✓ | [analysis.py](analysis.py) | `MeasMosCap`; `analyze_moscap_cv` (capacitance, quality factor and series resistance near 1 GHz, quality corner, leakage, and their spectra). In inversion: about 25 fF for two NMOS units, against 5 fF in accumulation. |
| Plots | ✓ | [plots.py](plots.py) | One panel per case: C-V with leakage, capacitance and quality factor versus frequency, loss versus bias. Run by `flow.analysis.runner moscap_characterization_study`. |
| Analysis tests | ✓ | [test_analysis.py](test_analysis.py) | A series RC of known capacitance, resistance and corner; every plot renders. |
| Layout generator | ✓ | [layout.py](layout.py) | Standard-cell rows with cIcCreator, laygo and ALIGN from hand-written floorplans (`design/layout/moscap_*.json`). |
| Layout tests | ✓ | [test_layout.py](test_layout.py) | Target registry; every floorplan places each netlist device once and escapes every connected port; every PDK writes every case. |
| Layout runner | ✓ | [layout.py](layout.py) | Four cases in all six PDKs, all 72 layouts DRC clean and LVS correct. A decap's gate on the other rail is an M1 strap into that rail inside the cell. |
| DRC runner | ✓ | [layout.py](layout.py) | gdscheck and the PDK's DRC for every layout (`row_signoff`). |
| LVS runner | ✓ | [layout.py](layout.py) | The PDK's LVS for every layout against the netlist the build placed. |
| PEX runner | ✗ | - | No extraction. |

Inspiration: BAG `mos_cap`, `decap`, `decap_array`; the boost capacitor of the sampler's bootstrap.
