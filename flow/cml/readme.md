# Status

| Feature | Status | File | Notes |
|---|---|---|---|
| Netlist generator | ✓ | [subckt.py](subckt.py) | Current-mode logic: buffers, latches, divide-by-two and XOR gates, NMOS or PMOS input, triode or symmetric MOS loads (no resistors: the row cells draw MOS only). |
| Netlist tests | ✓ | [test_subckt.py](test_subckt.py) | Pairs and loads, latch tracking and holding, the divider's crossed feedback, XOR polarity, PMOS input. |
| Testbench generator | ✓ | [sim.py](sim.py) | Differential data and clock pulses at CML levels, fixed biases, loads. |
| Simulation runners | ✓ | [sim.py](sim.py) | TSMC65 transients: the buffer and the divide-by-two (2.5 GHz from a 5 GHz clock). |
| Layout generator | ✓ | [layout.py](layout.py) | Standard-cell rows with cIcCreator, laygo and ALIGN from hand-written floorplans (`design/layout/cml_*.json`). |
| Layout tests | ✓ | [test_layout.py](test_layout.py) | Target registry; every floorplan places each netlist device once and escapes every connected port; every PDK writes every case. |
| Layout runner | ✓ | [layout.py](layout.py) | Five cases in all six PDKs, all 90 layouts DRC clean and LVS correct. |
| DRC runner | ✓ | [layout.py](layout.py) | gdscheck and the PDK's DRC for every layout (`row_signoff`). |
| LVS runner | ✓ | [layout.py](layout.py) | The PDK's LVS for every layout against the netlist the build placed. |
| PEX runner | ✗ | - | No extraction. |

Inspiration: Usb2Phy `CmlBuf`, `CmlDelayBuf`, `CmlLatch`, `CmlDiv`, `CmlXor`, `PmosCmlStage`; bag3_digital `cml_latch_res`; bag3_analog `gm_stage`.
