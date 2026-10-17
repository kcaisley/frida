# Status

| Feature | Status | File | Notes |
|---|---|---|---|
| Netlist generator | ✓ | [subckt.py](subckt.py) | Cross-coupled level shifters from vddl to vdd: differential or single-ended input (an inverter on vddl), an optional reset, optional output inverters. Every PMOS body on vdd. |
| Netlist tests | ✓ | [test_subckt.py](test_subckt.py) | Cross-coupling, the vddl inverter with its body on vdd, the buffers, invalid shifters. |
| Testbench generator | ✓ | [sim.py](sim.py) | bag3_digital's level shifter benches: input pulses at vddl levels (and their complement unless the shifter makes it), a reset for the first quarter period, 2 fF on every output, both supplies' currents. |
| Simulation runners | ✓ | [sim.py](sim.py) | `lvshift_characterization`: every case at input supplies from a quarter of the core supply to all of it (core supply out) and output supplies 83–108 % of it (two thirds of it in: half is below ihp130's threshold), in each PDK (42 transients per PDK, all 252 in 1.5 minutes on 16 workers); `check=True` runs Spectre's static checks at the nominal point. |
| Analysis | ✓ | [analysis.py](analysis.py) | `MeasLvShift`; `analyze_lvshift_switching` (rise and fall delay where every edge of that direction was followed, edges followed, output levels, energy per period from both supplies, idle current before an input's ramp). All three switch from a 0.5 V input supply in TSMC65 and tpsc65 (0.45 V in TSMC28, 0.7 V in ihp130, 0.53–0.9 V in the 1.8 V PDKs); below it the cross-coupled pair wins and the input pair only draws contention current. |
| Plots | ✓ | [plots.py](plots.py) | One panel per case: delay and energy versus input supply, delay and idle current versus output supply, waveforms at the nominal supplies; one figure set per PDK. Run by `flow.analysis.runner lvshift_characterization_study`. |
| Analysis tests | ✓ | [test_analysis.py](test_analysis.py) | A synthetic shifter of known delay and currents, and one that fails to switch; every plot renders. |
| Layout generator | ✓ | [layout.py](layout.py) | Standard-cell rows with cIcCreator, laygo and ALIGN from hand-written floorplans (`design/layout/lvshift_*.json`). |
| Layout tests | ✓ | [test_layout.py](test_layout.py) | Target registry; every floorplan places each netlist device once and escapes every connected port; every PDK writes every case. |
| Layout runner | ✓ | [layout.py](layout.py) | Three cases in all six PDKs, all 54 layouts DRC clean and LVS correct; vddl routed as a signal (the row cells' wells sit on vdd). |
| DRC runner | ✓ | [layout.py](layout.py) | gdscheck and the PDK's DRC for every layout (`row_signoff`). |
| LVS runner | ✓ | [layout.py](layout.py) | The PDK's LVS for every layout against the netlist the build placed. |
| PEX runner | ✗ | - | No extraction. |

Inspiration: bag3_digital `lvshift_core`, `lvshift_core_w_drivers`, `lvshift`; Usb2Phy `IloDiffLevelShift`.
