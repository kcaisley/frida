# Status

| Feature | Status | File | Notes |
|---|---|---|---|
| Netlist generator | ✓ | [subckt.py](subckt.py) | Phase interpolators: weighted CMOS inverter slices on one mixing node, or CML pairs on weighted tails into shared symmetric loads. |
| Netlist tests | ✓ | [test_subckt.py](test_subckt.py) | Slice and tail weights, the mixing node, invalid weights. |
| Testbench generator | ✓ | [sim.py](sim.py) | Phases A and B a set spacing apart with their complements, full-swing (CMOS) or at CML levels, slewed (edges a quarter period), current-reference biases (from a supply of their own), 2 fF loads; the output's differential crossing. |
| Simulation runners | ✓ | [sim.py](sim.py) | `pi_characterization`: every case at spacings 0–180° (400 ps period) and periods 1 ns–100 ps (90°), in each PDK about its own core supply (84 transients per PDK, all 504 in just over two minutes on 16 workers); `check=True` runs Spectre's static checks at the nominal point. |
| Analysis | ✓ | [analysis.py](analysis.py) | `MeasPi`; `analyze_pi_phase` (delay and phase behind A, swing, duty cycle, supply current), `analyze_pi_linearity` (slope against phase B's weight share, intrinsic delay, INL, fitted to 90°). In TSMC65: slopes 0.55 (CMOS) and 0.68 (CML) for equal weights (ideal 0.5), 0.19 and 0.23 for 3:1 (ideal 0.25), INL at most 3.2°; across the PDKs the equal-weight slopes span 0.41–0.71. Beyond quadrature a 3:1 interpolator follows A alone. |
| Plots | ✓ | [plots.py](plots.py) | One panel per case: transfer and INL versus spacing, phase and swing versus frequency, waveforms at quadrature; one figure set per PDK. Run by `python -m flow pi.characterization_study`. |
| Analysis tests | ✓ | [test_analysis.py](test_analysis.py) | A linear weighted mix of two slewed phases; every plot renders. |
| Layout generator | ✓ | [layout.py](layout.py) | Standard-cell rows by ALIGN from hand-written floorplans (`design/layout/pi_*.json`). |
| Layout tests | ✓ | [test_layout.py](test_layout.py) | Target registry; every floorplan places each netlist device once and escapes every connected port; every PDK writes every case. |
| Layout runner | ✓ | [layout.py](layout.py) | Four cases in all six PDKs, all 72 layouts DRC clean and LVS correct. |
| DRC runner | ✓ | [layout.py](layout.py) | gdscheck and the PDK's DRC for every layout (`row_signoff`). |
| LVS runner | ✓ | [layout.py](layout.py) | The PDK's LVS for every layout against the netlist the build placed. |
| PEX runner | ✗ | - | No extraction. |
