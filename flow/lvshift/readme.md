# Status

| Feature | Status | File | Notes |
|---|---|---|---|
| Netlist generator | ✓ | [subckt.py](subckt.py) | Cross-coupled level shifters from vddl to vdd: differential or single-ended input (an inverter on vddl), an optional reset, optional output inverters. Every PMOS body on vdd. |
| Netlist tests | ✓ | [test_subckt.py](test_subckt.py) | Cross-coupling, the vddl inverter with its body on vdd, the buffers, invalid shifters. |
| Testbench generator | ✓ | [sim.py](sim.py) | Input pulses at vddl (0.6 V) levels, a reset pulse, loads. |
| Simulation runners | ✓ | [sim.py](sim.py) | TSMC65 transients of the core and the shifter with an input inverter and reset. |
| Layout generator | ✓ | [layout.py](layout.py) | Standard-cell rows with cIcCreator, laygo and ALIGN from hand-written floorplans (`design/layout/lvshift_*.json`). |
| Layout tests | ✓ | [test_layout.py](test_layout.py) | Target registry; every floorplan places each netlist device once and escapes every connected port; every PDK writes every case. |
| Layout runner | ✓ | [layout.py](layout.py) | Three cases in all six PDKs, all 54 layouts DRC clean and LVS correct; vddl routed as a signal (the row cells' wells sit on vdd). |
| DRC runner | ✓ | [layout.py](layout.py) | gdscheck and the PDK's DRC for every layout (`row_signoff`). |
| LVS runner | ✓ | [layout.py](layout.py) | The PDK's LVS for every layout against the netlist the build placed. |
| PEX runner | ✗ | - | No extraction. |

Inspiration: bag3_digital `lvshift_core`, `lvshift_core_w_drivers`, `lvshift`; Usb2Phy `IloDiffLevelShift`.
