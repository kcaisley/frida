# Status

| Feature | Status | File | Notes |
|---|---|---|---|
| Netlist generator | ✓ | [subckt.py](subckt.py) | Clock conditioning from the PDK's library cells: non-overlapping two-phase clocks, a rising-edge pulse, a glitch-free clock gate (its enable latch the latch block's). |
| Netlist tests | ✓ | [test_subckt.py](test_subckt.py) | NOR cross-feeding, the pulse's delayed clock, the gate's latch, invalid drives. |
| Testbench generator | ✓ | [sim.py](sim.py) | Complementary clocks, en rising in the third period, loads; the library cells' SPICE included. |
| Simulation runners | ✓ | [sim.py](sim.py) | TSMC65 transients of the three functions. |
| Layout generator | ✓ | [layout.py](layout.py) | Standard-cell rows with cIcCreator, laygo and ALIGN from hand-written floorplans (`design/layout/clkgen_*.json`). |
| Layout tests | ✓ | [test_layout.py](test_layout.py) | Target registry; every floorplan places each netlist device once and escapes every connected port; every PDK writes every case. |
| Layout runner | ✓ | [layout.py](layout.py) | Three cases in all six PDKs; the logic in standard-cell rows: 51 of 54 layouts DRC clean and LVS correct. `pulse` in lf150 fails in all three tools: lf150's smallest library inverter reaches both its pins from one M3 track only, so a chain of them has no route. |
| DRC runner | ✓ | [layout.py](layout.py) | gdscheck and the PDK's DRC for every layout (`row_signoff`). |
| LVS runner | ✓ | [layout.py](layout.py) | The PDK's LVS for every layout against the netlist the build placed. |
| PEX runner | ✗ | - | No extraction. |

Inspiration: BAG `clk_local_nonoverlap`, `sar_async_pulse`; bag3_digital `clk_gate`; Usb2Phy `PulseGen`.
