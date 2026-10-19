# Status

| Feature | Status | File | Notes |
|---|---|---|---|
| Netlist generator | ✓ | [subckt.py](subckt.py) | Generic XORs, one per stage, each mapped to its library XOR by the PDK's compile: all six PDKs (IHP130 adds the library's buffer after its single XOR for drive bands 2 and 4). `CASES`: one stage of each drive band. |
| Netlist tests | ✓ | [test_subckt.py](test_subckt.py) | Drive bands, wiring, and public-API PDK isolation. |
| Testbench generator | ✓ | [sim.py](sim.py) | Each stage drives a load capacitor (its CDAC stage's bottom plate); over two periods the state steps up and back down with the invert input low, then the invert input with the state low, so both XOR paths switch both ways; the PDK's cell library included. |
| Simulation runners | ✓ | [sim.py](sim.py) | `capdriver_characterization`: every band over loads of 10 fF–1 pF at the core supply and supplies of 75–108 % at 100 fF, in each PDK; the period grows with the load (200 ps per fF, at least 2 ns) so the weakest band settles within half of it (30 transients per PDK, all 180 in about a minute on 16 workers); `check=True` runs Spectre's static checks at the nominal point. |
| Analysis | ✓ | [analysis.py](analysis.py) | `MeasCapdriver`; `analyze_capdriver_drive` (both paths' delays, the output's 10–90 % transitions, its 1 % settling, energy per cycle over C V²; `delay`, `riseTime`, `fallTime`, `settlingTime`, `integ` of `flow.analysis.calc`), `drive_resistance_ohm` (the transitions' slope over the load, over ln 9: the sizing input). Run 20261019_004359: band 1 drives 1.6 / 1.0 kΩ (rising / falling) in TSMC65, 0.8 / 1.1 kΩ in TSMC28, 4.6–10 kΩ rising in the 130–180 nm PDKs and TPSC65; each band doubling halves it; the switching costs 5–75 % above C V². |
| Plots | ✓ | [plots.py](plots.py) | One panel per band: delays and transitions versus load (the fitted resistance in the title), delay, settling and energy versus supply; one figure set per PDK. Run by `flow.analysis.runner capdriver_characterization_study`. |
| Analysis tests | ✓ | [test_analysis.py](test_analysis.py) | A synthetic RC driver of known delay, resistance, settling and energy; every plot renders. |
| Layout generator | ✗ | - | Reuses the fixed FRIDA-1 macro; no new geometry generated. Standard-cell rows need the XOR cells in each PDK's `STD_CELLS` and its access table (`stems/stdcell_access.py`): tried 2026-10-19, the access search reaches every pin of TSMC65's, IHP130's (XOR and buffers) and LF150's cells, but no input pin of TSMC28's clock XORs, and stops on TPSC65's and Tower180's XOR cells ("no access for all pins"); left as it was until the access search handles them. The cells per band differ by PDK (TSMC65's band 4 is two parallel drive-4 cells, IHP130's bands 2 and 4 an XOR and a buffer), so the floorplan would be generated from the flattened netlist rather than written by hand. |
| Layout tests | ✓ | [test_signoff.py](test_signoff.py) | Export preservation and mocked orchestration, not physical signoff. |
| Layout runner | ✓ | [layout.py](layout.py) | Exports the fixed macro and generates its TSMC65 source. |
| DRC runner | ✓ | [layout.py](layout.py) | ✗ Seven M4-area precheck violations; foundry DRC not reached. |
| LVS runner | ✓ | [layout.py](layout.py) | ✗ DNW layout devices mismatch ordinary upstream source models. |
| PEX runner | ✗ | - | Not implemented. |

Sizing: a stage settles to 1 / 2^(N+1) of the supply in ln(2^(N+1)) R C after its delay, with R the band's `drive_resistance_ohm` and C its stage's bottom-plate capacitance.

TODO: standard-cell row layout in all six PDKs; review standalone M4 violations; provide a DNW-aware LVS source; rerun DRC/LVS before adding PEX. ADC-level driver/array separation remains incomplete. See [project TODO](../../docs/todo.md#capdriver).
