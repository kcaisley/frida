# Status

| Feature | Status | File | Notes |
|---|---|---|---|
| Netlist generator | ✓ | [subckt.py](subckt.py) | Source followers and flipped voltage followers, NMOS or PMOS input, an optional output sink on a flipped follower. |
| Netlist tests | ✓ | [test_subckt.py](test_subckt.py) | Drain and gate wiring, the flipped follower's feedback, invalid followers. |
| Testbench generator | ✓ | [sim.py](sim.py) | A DC level with the AC stimulus on vin, fixed biases, a load. |
| Simulation runners | ✓ | [sim.py](sim.py) | TSMC65 operating point and AC response: NMOS source and flipped followers. |
| Layout generator | ✓ | [layout.py](layout.py) | Standard-cell rows with cIcCreator, laygo and ALIGN from hand-written floorplans (`design/layout/follower_*.json`). |
| Layout tests | ✓ | [test_layout.py](test_layout.py) | Target registry; every floorplan places each netlist device once and escapes every connected port; every PDK writes every case. |
| Layout runner | ✓ | [layout.py](layout.py) | Four cases in all six PDKs, all 72 layouts DRC clean and LVS correct. A source follower's drain sits on the other type's rail: the row cells tie it in-cell (`rowcell` ties, ALIGN's `far` flag). |
| DRC runner | ✓ | [layout.py](layout.py) | gdscheck and the PDK's DRC for every layout (`row_signoff`). |
| LVS runner | ✓ | [layout.py](layout.py) | The PDK's LVS for every layout against the netlist the build placed. |
| PEX runner | ✗ | - | No extraction. |

Inspiration: BAG `source_follower`, `super_source_follower_n`/`_p` (without their bias DACs); Usb2Phy `UnityGainBuffer`.
