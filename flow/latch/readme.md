# Status

| Feature | Status | File | Notes |
|---|---|---|---|
| Netlist generator | ✓ | [subckt.py](subckt.py) | Static C2MOS latches with an optional asynchronous reset, master-slave and divide-by-two flip-flops, NAND and NOR SR latches. |
| Netlist tests | ✓ | [test_subckt.py](test_subckt.py) | Clocked-inverter wiring, master and slave clocks, divider feedback, SR gates, invalid latches. |
| Testbench generator | ✓ | [sim.py](sim.py) | One bench for every case (bag3_digital's sequential timing benches): complementary clocks, data toggling once per cycle a set offset before each capturing edge (a flip-flop's rising, a latch's closing edge), an initial reset, set and reset pulses, output loads. |
| Simulation runners | ✓ | [sim.py](sim.py) | `latch_characterization`: every case at supplies 0.9–1.3 V, the latches and flip-flop over data offsets −200 to 300 ps, the flip-flop and divider over clock periods 2 ns to 60 ps (203 TSMC65 transients, under a minute on 16 workers); `check=True` runs Spectre's static checks at the nominal point. |
| Analysis | ✓ | [analysis.py](analysis.py) | `MeasLatch`; `analyze_latch_timing` (launch-to-q delays, edges taking the new or keeping the old value, energy per cycle), `analyze_latch_constraint` (setup at a 10 % delay pushout, hold), `analyze_latch_sr` (set and reset delays). In TSMC65 at 1.2 V: latch setup 60 ps and hold −40 ps, flip-flop 50 ps and −30 ps; the divider toggles to 10 GHz. |
| Plots | ✓ | [plots.py](plots.py) | One panel per case: setup and hold curves, delay and energy versus supply, flip-flop and divider speed versus clock frequency. Run by `flow.analysis.runner latch_characterization_study`. |
| Analysis tests | ✓ | [test_analysis.py](test_analysis.py) | A synthetic flip-flop of known setup and clock-to-q, a synthetic SR latch; every plot renders. |
| Layout generator | ✓ | [layout.py](layout.py) | Standard-cell rows with cIcCreator, laygo and ALIGN from hand-written floorplans (`design/layout/latch_*.json`). |
| Layout tests | ✓ | [test_layout.py](test_layout.py) | Target registry; every floorplan places each netlist device once and escapes ports the netlist connects; every PDK writes every case. |
| Layout runner | ✓ | [layout.py](layout.py) | Six cases in all six PDKs, all 108 layouts DRC clean and LVS correct. |
| DRC runner | ✓ | [layout.py](layout.py) | gdscheck and the PDK's DRC for every layout (`row_signoff`). |
| LVS runner | ✓ | [layout.py](layout.py) | The PDK's LVS for every layout against the netlist the build placed. |
| PEX runner | ✗ | - | No extraction. |

Inspiration: bag3_digital `latch`, `rst_latch`, `flop`, `rst_flop`, `div2`, `sr_latch_symmetric_core`; BAG `clk_retime_latch`, `vco_cnter_latch`, `vco_cnter_div`, `sr_nand`; ciccreator `SARLTX1`, `DFRNQNX1`.
