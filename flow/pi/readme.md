# Status

| Feature | Status | File | Notes |
|---|---|---|---|
| Netlist generator | ✓ | [subckt.py](subckt.py) | Phase interpolators: weighted CMOS inverter slices on one mixing node, or CML pairs on weighted tails into shared symmetric loads. |
| Netlist tests | ✓ | [test_subckt.py](test_subckt.py) | Slice and tail weights, the mixing node, invalid weights. |
| Testbench generator | ✓ | [sim.py](sim.py) | Usb2Phy's `PhaseInterpTb`: phases A and B a set spacing apart with their complements, full-swing (CMOS) or at CML levels, slewed (edges a quarter period), fixed biases, 2 fF loads; the output's differential crossing. |
| Simulation runners | ✓ | [sim.py](sim.py) | `pi_characterization`: every case at spacings 0–180° (400 ps period) and periods 1 ns–100 ps (90°), 84 TSMC65 transients; `check=True` runs Spectre's static checks at the nominal point. |
| Analysis | ✓ | [analysis.py](analysis.py) | `MeasPi`; `analyze_pi_phase` (delay and phase behind A, swing, duty cycle, supply current), `analyze_pi_linearity` (slope against phase B's weight share, intrinsic delay, INL, fitted to 90°). In TSMC65: slopes 0.55 and 0.57 for equal weights (ideal 0.5), 0.19 for 3:1 (ideal 0.25), INL at most 3.4°; beyond quadrature a 3:1 interpolator follows A alone. |
| Plots | ✓ | [plots.py](plots.py) | One panel per case: transfer and INL versus spacing, phase and swing versus frequency, waveforms at quadrature. Run by `flow.analysis.runner pi_characterization_study`. |
| Analysis tests | ✓ | [test_analysis.py](test_analysis.py) | A linear weighted mix of two slewed phases; every plot renders. |
| Layout generator | ✓ | [layout.py](layout.py) | Standard-cell rows with cIcCreator, laygo and ALIGN from hand-written floorplans (`design/layout/pi_*.json`). |
| Layout tests | ✓ | [test_layout.py](test_layout.py) | Target registry; every floorplan places each netlist device once and escapes every connected port; every PDK writes every case. |
| Layout runner | ✓ | [layout.py](layout.py) | Four cases in all six PDKs, all 72 layouts DRC clean and LVS correct. |
| DRC runner | ✓ | [layout.py](layout.py) | gdscheck and the PDK's DRC for every layout (`row_signoff`). |
| LVS runner | ✓ | [layout.py](layout.py) | The PDK's LVS for every layout against the netlist the build placed. |
| PEX runner | ✗ | - | No extraction. |

Inspiration: Usb2Phy flashpi `PhaseWeighter`/`WeightInv`, cmospi `FineInterp`, cmlpi `PhaseInterp`; bag3_analog `phase_interp`.
