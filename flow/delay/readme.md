# Status

| Feature | Status | File | Notes |
|---|---|---|---|
| Netlist generator | ✓ | [subckt.py](subckt.py) | Delay lines and ring oscillators: inverter or coupled pseudo-differential stages, single-ended or differential, current-starved or shared-tail control, a NAND enable and an injection device in a ring. |
| Netlist tests | ✓ | [test_subckt.py](test_subckt.py) | Stage wiring, ring closure and enable, coupling, starving and tail devices, invalid chains. |
| Testbench generator | ✓ | [sim.py](sim.py) | One bench for every case: supply, enable, a kick-start that holds the outputs apart for 1 ns after the enable (switches to the rails: a capacitive kick left tower180's coupled rings in their common-mode latch), complementary input clock, one control voltage (`vbn`, `vctrl`, and `vdd - vbp`), output loads. |
| Simulation runners | ✓ | [sim.py](sim.py) | `delay_characterization`: in each of the six PDKs about its own core supply (TT, 25 °C), every case at 75–108 % of it and controls from 5/12 of it to all of it (0.9–1.3 V and 0.5–1.2 V in TSMC65); 91 transients per PDK, all 546 in three minutes on 16 workers; `check=True` runs Spectre's static checks at the nominal point. |
| Analysis | ✓ | [analysis.py](analysis.py) | `MeasDelay`; `analyze_delay_oscillation`, `analyze_delay_propagation` (50 % rise and fall delay, 10–90 % output transitions, energy per input cycle). At the core supply: `ring5` 9.6 GHz in TSMC65, 24.9 GHz in TSMC28, 3.2–6.3 GHz in the others; `chain4` 40 ps in TSMC65 (18–105 ps across the PDKs). |
| Plots | ✓ | [plots.py](plots.py) | One panel per case: ring frequency with energy per cycle versus supply, and with tuning gain versus control; delay line delay with energy versus supply, and with output transitions versus control; one figure set per PDK. Run by `python -m flow delay.characterization_study`. |
| Analysis tests | ✓ | [test_analysis.py](test_analysis.py) | Synthetic records of known frequency, delay, and current; every plot renders. |
| Layout generator | ✓ | [layout.py](layout.py) | Standard-cell rows with cIcCreator, laygo and ALIGN from hand-written floorplans (`design/layout/delay_*.json`). |
| Layout tests | ✓ | [test_layout.py](test_layout.py) | Target registry; every floorplan places each netlist device once and escapes ports the netlist connects; every PDK writes every case. |
| Layout runner | ✓ | [layout.py](layout.py) | Seven cases in all six PDKs: 124 of 126 layouts DRC clean and LVS correct. ALIGN's detailed router leaves a net open in `ring4_tail` (tower180) and `ring5_starved` (tpsc65); cIcCreator and laygo are clean there. |
| DRC runner | ✓ | [layout.py](layout.py) | gdscheck and the PDK's DRC for every layout (`row_signoff`). |
| LVS runner | ✓ | [layout.py](layout.py) | The PDK's LVS for every layout against the netlist the build placed. |
| PEX runner | ✗ | - | No extraction. |
