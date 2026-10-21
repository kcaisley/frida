# Status

| Feature | Status | File | Notes |
|---|---|---|---|
| Netlist generator | ✓ | [subckt.py](subckt.py) | A single-ended ring amplifier: input inverter on common-mode tails, enable transmission gate, dead-zone stage, output inverter (19 devices). |
| Netlist tests | ✓ | [test_subckt.py](test_subckt.py) | Its stages' wiring, invalid sizes. |
| Testbench generator | ✓ | [sim.py](sim.py) | Fixed tail and dead-zone biases, 50 fF on the output; open loop a slow triangle on the input, closed loop a gain of −1 (100 fF in and feedback, 1 GΩ DC feedback, the amplifier on from the start) and a step through the input capacitor. |
| Simulation runners | ✓ | [sim.py](sim.py) | `ringamp_characterization`: both cases open loop and closed loop over dead-zone drives from 1/4 to 7/12 of the core supply, and closed loop over steps of ±1/48 to ±1/6 of it, in each PDK (32 transients per PDK, all 192 in about a minute on 16 workers); `check=True` runs Spectre's static checks on both benches. |
| Analysis | ✓ | [analysis.py](analysis.py) | `MeasRingamp`; `analyze_ringamp_transfer` (trip point, hysteresis on the ramp, gain, current at the trip), `analyze_ringamp_settling` (output step against the ideal, settling to 1 %, overshoot, quiescent current, settling charge). The sizing is untuned: in TSMC65 at 0.5 V drive the dead zone leaves about 12 mV at the input (a 100 mV step lands 24 % off), at 0.3 V the output stage never turns on, from 0.6 V the loop oscillates. Across the PDKs the smallest steps (±1/48 of the supply) mostly stay inside the dead zone and only TSMC28 lands the largest within 10 %; in lf150 no step settles to 1 % at the nominal drive. |
| Plots | ✓ | [plots.py](plots.py) | One panel per case: transfer and current per dead-zone bias, step error and quiescent current versus dead zone, error and settling versus step, the step responses; one figure set per PDK. Run by `python -m flow ringamp.characterization_study`. |
| Analysis tests | ✓ | [test_analysis.py](test_analysis.py) | A synthetic inverting transfer and an exponential closed-loop settling; every plot renders. |
| Layout generator | ✓ | [layout.py](layout.py) | Standard-cell rows with cIcCreator, laygo and ALIGN from hand-written floorplans (`design/layout/ringamp_*.json`). |
| Layout tests | ✓ | [test_layout.py](test_layout.py) | Target registry; every floorplan places each netlist device once and escapes every connected port; every PDK writes every case. |
| Layout runner | ✓ | [layout.py](layout.py) | Two cases in all six PDKs: 35 of 36 layouts DRC clean and LVS correct; laygo finds no route for `se` in tower180 (its coarse M3 pitch), cIcCreator and ALIGN do. |
| DRC runner | ✓ | [layout.py](layout.py) | gdscheck and the PDK's DRC for every layout (`row_signoff`). |
| LVS runner | ✓ | [layout.py](layout.py) | The PDK's LVS for every layout against the netlist the build placed. |
| PEX runner | ✗ | - | No extraction. |
