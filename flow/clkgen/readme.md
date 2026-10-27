# Status

| Feature | Status | File | Notes |
|---|---|---|---|
| Netlist generator | ✓ | [subckt.py](subckt.py) | Clock conditioning from the PDK's library cells: non-overlapping two-phase clocks, a rising-edge pulse, a glitch-free clock gate (its enable latch the latch block's). |
| Netlist tests | ✓ | [test_subckt.py](test_subckt.py) | NOR cross-feeding, the pulse's delayed clock, the gate's latch, invalid drives. |
| Testbench generator | ✓ | [sim.py](sim.py) | Complementary clocks, an enable rising a quarter period into the third period, 2 fF loads; the PDK's cell library included (its global supply net shows in Spectre's topology check). |
| Simulation runners | ✓ | [sim.py](sim.py) | `clkgen_characterization`: every case at supplies from 2/3 to 108 % of the core supply (1 ns clock) and clock periods 2 ns–100 ps (core supply), in each PDK (42 transients per PDK, all 252 in 1.5 minutes on 16 workers); `check=True` runs Spectre's static checks at the nominal point. |
| Analysis | ✓ | [analysis.py](analysis.py) | `MeasClkgen`; `analyze_clkgen_timing` (clk-to-outp delay, high width, duty, the gaps between the outputs, pulses before the enable, periods pulsing after it, energy per cycle). In TSMC65 at 1.2 V: 48 ps non-overlap, a 56 ps pulse, and a gate passing no pulse before its enable; 15 ps and 15 ps in TSMC28, 105–131 ps and 125–183 ps in the 130–180 nm PDKs. |
| Plots | ✓ | [plots.py](plots.py) | One panel per case: delay, width and gaps versus supply; duty, pulsing and energy versus frequency; waveforms through the enable; one figure set per PDK. Run by `python -m flow clkgen.characterization_study`. |
| Analysis tests | ✓ | [test_analysis.py](test_analysis.py) | A synthetic clock gate of known delay, width and gaps; every plot renders. |
| Layout generator | ✓ | [layout.py](layout.py) | Standard-cell rows by ALIGN from hand-written floorplans (`design/layout/clkgen_*.json`). |
| Layout tests | ✓ | [test_layout.py](test_layout.py) | Target registry; every floorplan places each netlist device once and escapes every connected port; every PDK writes every case. |
| Layout runner | ✓ | [layout.py](layout.py) | Three cases in all six PDKs; the logic in standard-cell rows (51 of 54 layouts DRC clean and LVS correct with cIcCreator, laygo and ALIGN, the first two since removed). `pulse` in lf150 fails in every tool: lf150's smallest library inverter reaches both its pins from one M3 track only, so a chain of them has no route. |
| DRC runner | ✓ | [layout.py](layout.py) | gdscheck and the PDK's DRC for every layout (`row_signoff`). |
| LVS runner | ✓ | [layout.py](layout.py) | The PDK's LVS for every layout against the netlist the build placed. |
| PEX runner | ✗ | - | No extraction. |
