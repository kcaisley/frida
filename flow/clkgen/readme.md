# Status

| Feature | Status | File | Notes |
|---|---|---|---|
| Netlist generator | ✓ | [subckt.py](subckt.py) | Clock conditioning from the PDK's library cells: non-overlapping two-phase clocks, a rising-edge pulse, a glitch-free clock gate (its enable latch the latch block's). |
| Netlist tests | ✓ | [test_subckt.py](test_subckt.py) | NOR cross-feeding, the pulse's delayed clock, the gate's latch, invalid drives. |
| Testbench generator | ✓ | [sim.py](sim.py) | Usb2Phy's `PulseGenTb` and BAG's clock benches: complementary clocks, an enable rising a quarter period into the third period, 2 fF loads; the PDK's cell library included (its global supply net shows in Spectre's topology check). |
| Simulation runners | ✓ | [sim.py](sim.py) | `clkgen_characterization`: every case at supplies 0.8–1.3 V (1 ns clock) and clock periods 2 ns–100 ps (1.2 V), 42 TSMC65 transients; `check=True` runs Spectre's static checks at the nominal point. |
| Analysis | ✓ | [analysis.py](analysis.py) | `MeasClkgen`; `analyze_clkgen_timing` (clk-to-outp delay, high width, duty, the gaps between the outputs, pulses before the enable, periods pulsing after it, energy per cycle). At 1.2 V: 48 ps non-overlap, a 56 ps pulse, and a gate passing no pulse before its enable. |
| Plots | ✓ | [plots.py](plots.py) | One panel per case: delay, width and gaps versus supply; duty, pulsing and energy versus frequency; waveforms through the enable. Run by `flow.analysis.runner clkgen_characterization_study`. |
| Analysis tests | ✓ | [test_analysis.py](test_analysis.py) | A synthetic clock gate of known delay, width and gaps; every plot renders. |
| Layout generator | ✓ | [layout.py](layout.py) | Standard-cell rows with cIcCreator, laygo and ALIGN from hand-written floorplans (`design/layout/clkgen_*.json`). |
| Layout tests | ✓ | [test_layout.py](test_layout.py) | Target registry; every floorplan places each netlist device once and escapes every connected port; every PDK writes every case. |
| Layout runner | ✓ | [layout.py](layout.py) | Three cases in all six PDKs; the logic in standard-cell rows: 51 of 54 layouts DRC clean and LVS correct. `pulse` in lf150 fails in all three tools: lf150's smallest library inverter reaches both its pins from one M3 track only, so a chain of them has no route. |
| DRC runner | ✓ | [layout.py](layout.py) | gdscheck and the PDK's DRC for every layout (`row_signoff`). |
| LVS runner | ✓ | [layout.py](layout.py) | The PDK's LVS for every layout against the netlist the build placed. |
| PEX runner | ✗ | - | No extraction. |

Inspiration: BAG `clk_local_nonoverlap`, `sar_async_pulse`; bag3_digital `clk_gate`; Usb2Phy `PulseGen`.
