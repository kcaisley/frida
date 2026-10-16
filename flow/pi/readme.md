# Status

| Feature | Status | File | Notes |
|---|---|---|---|
| Netlist generator | ✓ | [subckt.py](subckt.py) | Phase interpolators: weighted CMOS inverter slices on one mixing node, or CML pairs on weighted tails into shared symmetric loads. |
| Netlist tests | ✓ | [test_subckt.py](test_subckt.py) | Slice and tail weights, the mixing node, invalid weights. |
| Testbench generator | ✓ | [sim.py](sim.py) | Two phases a quarter period apart, full swing (CMOS) or CML levels, fixed biases, loads. |
| Simulation runners | ✓ | [sim.py](sim.py) | TSMC65 transients of the CMOS and CML interpolators at equal weights. |
| Layout generator | ✓ | [layout.py](layout.py) | Standard-cell rows with cIcCreator, laygo and ALIGN from hand-written floorplans (`design/layout/pi_*.json`). |
| Layout tests | ✓ | [test_layout.py](test_layout.py) | Target registry; every floorplan places each netlist device once and escapes every connected port; every PDK writes every case. |
| Layout runner | ✓ | [layout.py](layout.py) | Four cases in all six PDKs, all 72 layouts DRC clean and LVS correct. |
| DRC runner | ✓ | [layout.py](layout.py) | gdscheck and the PDK's DRC for every layout (`row_signoff`). |
| LVS runner | ✓ | [layout.py](layout.py) | The PDK's LVS for every layout against the netlist the build placed. |
| PEX runner | ✗ | - | No extraction. |

Inspiration: Usb2Phy flashpi `PhaseWeighter`/`WeightInv`, cmospi `FineInterp`, cmlpi `PhaseInterp`; bag3_analog `phase_interp`.
