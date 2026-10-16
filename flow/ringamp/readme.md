# Status

| Feature | Status | File | Notes |
|---|---|---|---|
| Netlist generator | ✓ | [subckt.py](subckt.py) | A single-ended ring amplifier: input inverter on common-mode tails, enable transmission gate, dead-zone stage, output inverter (19 devices). |
| Netlist tests | ✓ | [test_subckt.py](test_subckt.py) | Its stages' wiring, invalid sizes. |
| Testbench generator | ✓ | [sim.py](sim.py) | en after a quarter period, an input triangle about the common mode, fixed biases, a load. |
| Simulation runners | ✓ | [sim.py](sim.py) | TSMC65 transient over the input triangle (open loop). |
| Layout generator | ✓ | [layout.py](layout.py) | Standard-cell rows with cIcCreator, laygo and ALIGN from hand-written floorplans (`design/layout/ringamp_*.json`). |
| Layout tests | ✓ | [test_layout.py](test_layout.py) | Target registry; every floorplan places each netlist device once and escapes every connected port; every PDK writes every case. |
| Layout runner | ✓ | [layout.py](layout.py) | Two cases in all six PDKs: 35 of 36 layouts DRC clean and LVS correct; laygo finds no route for `se` in tower180 (its coarse M3 pitch), cIcCreator and ALIGN do. |
| DRC runner | ✓ | [layout.py](layout.py) | gdscheck and the PDK's DRC for every layout (`row_signoff`). |
| LVS runner | ✓ | [layout.py](layout.py) | The PDK's LVS for every layout against the netlist the build placed. |
| PEX runner | ✗ | - | No extraction. |

Inspiration: BAG `ringamp_se` (the differential `ra_diff_core` is two of them).
