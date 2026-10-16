# Status

| Feature | Status | File | Notes |
|---|---|---|---|
| Netlist generator | ✓ | [subckt.py](subckt.py) | Static C2MOS latches with an optional asynchronous reset, master-slave and divide-by-two flip-flops, NAND and NOR SR latches. |
| Netlist tests | ✓ | [test_subckt.py](test_subckt.py) | Clocked-inverter wiring, master and slave clocks, divider feedback, SR gates, invalid latches. |
| Testbench generator | ✓ | [sim.py](sim.py) | Complementary clocks, data slower than the clock, an initial reset, set and reset pulses. |
| Simulation runners | ✓ | [sim.py](sim.py) | TSMC65 transients: divider, flip-flop with reset, NAND SR latch. |
| Layout generator | ✓ | [layout.py](layout.py) | Standard-cell rows with cIcCreator, laygo and ALIGN from hand-written floorplans (`design/layout/latch_*.json`). |
| Layout tests | ✓ | [test_layout.py](test_layout.py) | Target registry; every floorplan places each netlist device once and escapes ports the netlist connects; every PDK writes every case. |
| Layout runner | ✓ | [layout.py](layout.py) | Six cases in all six PDKs, all 108 layouts DRC clean and LVS correct. |
| DRC runner | ✓ | [layout.py](layout.py) | gdscheck and the PDK's DRC for every layout (`row_signoff`). |
| LVS runner | ✓ | [layout.py](layout.py) | The PDK's LVS for every layout against the netlist the build placed. |
| PEX runner | ✗ | - | No extraction. |

Inspiration: bag3_digital `latch`, `rst_latch`, `flop`, `rst_flop`, `div2`, `sr_latch_symmetric_core`; BAG `clk_retime_latch`, `vco_cnter_latch`, `vco_cnter_div`, `sr_nand`; ciccreator `SARLTX1`, `DFRNQNX1`.
