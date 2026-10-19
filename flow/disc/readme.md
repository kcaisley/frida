# Status

| Feature | Status | File | Notes |
|---|---|---|---|
| Netlist generator | ✓ | [subckt.py](subckt.py) | Unclocked two-stage discriminator, NMOS or PMOS input pair: a current-mirror load and a common-source second stage against a current source sharing the tail's bias (7 devices), or internal hysteresis, diode loads each beside one of a cross-coupled pair 1.5 times their strength, with a differential second stage into a mirror (11 devices). The output is high while `inp` is above `inn`. |
| Netlist tests | ✓ | [test_subckt.py](test_subckt.py) | Pair, load and second-stage wiring with and without hysteresis, the PMOS case's rails, invalid discriminators. |
| Testbench generator | ✓ | [sim.py](sim.py) | DHPT `Comparator_normal_TB`: the threshold a DC level on `inn`, the tail biased by a diode-connected copy fed 2 µA from a supply of its own, 10 fF on the output. `inp` ramps 100 mV either side of the threshold and back over 4 µs each way (trip points), or steps from 100 mV below it to an overdrive above it and back (delays). |
| Simulation runners | ✓ | [sim.py](sim.py) | `disc_characterization`: every case's triangle and steps of 2, 5, 10, 20, 50 and 100 mV, threshold at mid-supply, in each PDK at its own core supply (28 runs per PDK, all 168 in about a minute on 16 workers); `check=True` runs Spectre's static checks on the 10 mV step. |
| Analysis | ✓ | [analysis.py](analysis.py) | `MeasDisc`; `analyze_disc_trip` (the input at the output's mid-supply crossings up and down: offset, hysteresis; `cross`, `value`), `analyze_disc_delay` (each edge's delay from the input's threshold crossing, `delayMeasure`, the timewalk over the overdrive, the output's 10–90 % transitions, supply current). Run 20261019_012953: hysteresis cases trip symmetrically, ±2.4 mV (TSMC65 PMOS) to ±22 mV (LF150 PMOS), offset 0.1 mV or less; mirror loads 0.1–2 mV of systematic offset, their 0.9–6.5 mV of apparent hysteresis the triangle's 50 mV/µs times the delay; TSMC65 NMOS rising delay 22 ns at 2 mV to 1.2 ns at 100 mV (21 ns of timewalk); 1.9–4.2 µA. |
| Plots | ✓ | [plots.py](plots.py) | One panel per case: output over the triangle's input with the trip points, offset and hysteresis; rising and falling delay over the overdrive with the timewalk; one figure set per PDK. Run by `flow.analysis.runner disc_characterization_study`. |
| Analysis tests | ✓ | [test_analysis.py](test_analysis.py) | A hysteretic switch of known offset and hysteresis on the triangle, ramped output steps of known delay; every plot renders. |
| Layout generator | ✓ | [layout.py](layout.py) | Standard-cell rows with cIcCreator, laygo and ALIGN from hand-written floorplans (`design/layout/disc_*.json`). |
| Layout tests | ✓ | [test_layout.py](test_layout.py) | Target registry; every floorplan places each netlist device once and escapes every connected port; every PDK writes every case. |
| Layout runner | ✓ | [layout.py](layout.py) | Four cases in six PDKs with cIcCreator and laygo: all 48 layouts DRC clean and LVS correct. The hysteresis loads sit diodes outside, cross-coupled pair inside: the other way round, TSMC65's laygo route had three VIA2 spacing errors. ALIGN not run: `ALIGN_HOME` names a deleted install. |
| DRC runner | ✓ | [layout.py](layout.py) | gdscheck and the PDK's DRC for every layout (`row_signoff`). |
| LVS runner | ✓ | [layout.py](layout.py) | The PDK's LVS for every layout against the netlist the build placed. |
| PEX runner | ✗ | - | No extraction. |
| Monte Carlo | ✗ | - | No mismatch: DHPT's bench runs the offset with Monte Carlo. |
| Threshold trim | ✗ | - | No per-pixel trim DAC (RD53 `Comp_dyn_trim`, LF-Monopix `Discri_new`'s `ITUNE`). |

Inspiration: FE65-P2 `Comparator`, CCPD `Comparator_cont`, DHPT `Comparator_normal`, RD53B `Comparator_hyst`; Allen and Holberg's comparator with internal hysteresis; bench DHPT `Comparator_normal_TB`.
