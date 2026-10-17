# Status

| Feature | Status | File | Notes |
|---|---|---|---|
| Netlist generator | ✓ | [subckt.py](subckt.py) | Current-mode logic: buffers, latches, divide-by-two and XOR gates, NMOS or PMOS input, triode or symmetric MOS loads (no resistors: the row cells draw MOS only). |
| Netlist tests | ✓ | [test_subckt.py](test_subckt.py) | Pairs and loads, latch tracking and holding, the divider's crossed feedback, XOR polarity, PMOS input. |
| Testbench generator | ✓ | [sim.py](sim.py) | Usb2Phy's `CmlDivTb` `DiffClkGen`: differential data and clock between the CML levels (0.8–1.2 V, a PMOS input 0–0.4 V), fixed biases, 2 fF loads. |
| Simulation runners | ✓ | [sim.py](sim.py) | `cml_characterization`: every case at clock periods 1 ns–25 ps (data at 2.6 of them) and tail gate drives 0.4–0.8 V (95 TSMC65 transients, under a minute on 16 workers); `check=True` runs Spectre's static checks at the nominal point. |
| Analysis | ✓ | [analysis.py](analysis.py) | `MeasCml`; `analyze_cml_switching` (single-ended swing, output common mode, delay from the driving input, the share of instants where the output holds its function's value, supply current). In TSMC65 at the nominal bias: buffers work to 40 GHz (the NMOS one with 0.5 V swing, the PMOS one with only 90 mV on its levels), the XOR and the divider to 6.7 GHz, the latch to 2 GHz with data inside its setup window beyond. |
| Plots | ✓ | [plots.py](plots.py) | One panel per case: swing and delay versus frequency, swing and current versus tail bias, the waveforms at the nominal clock. Run by `flow.analysis.runner cml_characterization_study`. |
| Analysis tests | ✓ | [test_analysis.py](test_analysis.py) | Ideal buffer, XOR and divider records of known swing and delay, and an inverted one; every plot renders. |
| Layout generator | ✓ | [layout.py](layout.py) | Standard-cell rows with cIcCreator, laygo and ALIGN from hand-written floorplans (`design/layout/cml_*.json`). |
| Layout tests | ✓ | [test_layout.py](test_layout.py) | Target registry; every floorplan places each netlist device once and escapes every connected port; every PDK writes every case. |
| Layout runner | ✓ | [layout.py](layout.py) | Five cases in all six PDKs, all 90 layouts DRC clean and LVS correct. |
| DRC runner | ✓ | [layout.py](layout.py) | gdscheck and the PDK's DRC for every layout (`row_signoff`). |
| LVS runner | ✓ | [layout.py](layout.py) | The PDK's LVS for every layout against the netlist the build placed. |
| PEX runner | ✗ | - | No extraction. |

Inspiration: Usb2Phy `CmlBuf`, `CmlDelayBuf`, `CmlLatch`, `CmlDiv`, `CmlXor`, `PmosCmlStage`; bag3_digital `cml_latch_res`; bag3_analog `gm_stage`.
