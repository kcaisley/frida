# Status

| Feature | Status | File | Notes |
|---|---|---|---|
| Netlist generator | ✓ | [subckt.py](subckt.py) | Cross-coupled level shifters from vddl to vdd: differential or single-ended input (an inverter on vddl), an optional reset, optional output inverters. Every PMOS body on vdd. |
| Netlist tests | ✓ | [test_subckt.py](test_subckt.py) | Cross-coupling, the vddl inverter with its body on vdd, the buffers, invalid shifters. |
| Testbench generator | ✓ | [sim.py](sim.py) | bag3_digital's level shifter benches: input pulses at vddl levels (and their complement unless the shifter makes it), a reset for the first quarter period, 2 fF on every output, both supplies' currents. |
| Simulation runners | ✓ | [sim.py](sim.py) | `lvshift_characterization`: every case at input supplies 0.3–1.2 V (1.2 V out) and output supplies 1.0–1.3 V (0.6 V in), 42 TSMC65 transients; `check=True` runs Spectre's static checks at the nominal point. |
| Analysis | ✓ | [analysis.py](analysis.py) | `MeasLvShift`; `analyze_lvshift_switching` (rise and fall delay, edges followed, output levels, energy per period from both supplies, idle current). All three switch from a 0.5 V input supply; below it the cross-coupled pair wins and the input pair only draws contention current. |
| Plots | ✓ | [plots.py](plots.py) | One panel per case: delay and energy versus input supply, delay and idle current versus output supply, waveforms at the nominal supplies. Run by `flow.analysis.runner lvshift_characterization_study`. |
| Analysis tests | ✓ | [test_analysis.py](test_analysis.py) | A synthetic shifter of known delay and currents, and one that fails to switch; every plot renders. |
| Layout generator | ✓ | [layout.py](layout.py) | Standard-cell rows with cIcCreator, laygo and ALIGN from hand-written floorplans (`design/layout/lvshift_*.json`). |
| Layout tests | ✓ | [test_layout.py](test_layout.py) | Target registry; every floorplan places each netlist device once and escapes every connected port; every PDK writes every case. |
| Layout runner | ✓ | [layout.py](layout.py) | Three cases in all six PDKs, all 54 layouts DRC clean and LVS correct; vddl routed as a signal (the row cells' wells sit on vdd). |
| DRC runner | ✓ | [layout.py](layout.py) | gdscheck and the PDK's DRC for every layout (`row_signoff`). |
| LVS runner | ✓ | [layout.py](layout.py) | The PDK's LVS for every layout against the netlist the build placed. |
| PEX runner | ✗ | - | No extraction. |

Inspiration: bag3_digital `lvshift_core`, `lvshift_core_w_drivers`, `lvshift`; Usb2Phy `IloDiffLevelShift`.
