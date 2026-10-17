# Status

| Feature | Status | File | Notes |
|---|---|---|---|
| Netlist generator | ✓ | [subckt.py](subckt.py) | Delay lines and ring oscillators: inverter or coupled pseudo-differential stages, single-ended or differential, current-starved or shared-tail control, a NAND enable and an injection device in a ring. |
| Netlist tests | ✓ | [test_subckt.py](test_subckt.py) | Stage wiring, ring closure and enable, coupling, starving and tail devices, invalid chains. |
| Testbench generator | ✓ | [sim.py](sim.py) | One bench for every case (Usb2Phy `IloRingFreqTb`, `DiffClkGen`): supply, enable and a differential kick-start, complementary input clock, one control voltage (`vbn`, `vctrl`, and `vdd - vbp`), output loads. |
| Simulation runners | ✓ | [sim.py](sim.py) | `delay_characterization`: every case at supplies 0.9–1.3 V and controls 0.5–1.2 V in TSMC65 (84 transients, under a minute on 16 workers); `check=True` runs Spectre's static checks at the nominal point. |
| Analysis | ✓ | [analysis.py](analysis.py) | `MeasDelay`; `analyze_delay_oscillation` (ring frequency over Usb2Phy's ten-cycle window, supply current, swing, duty), `analyze_delay_propagation` (50 % rise and fall delay, 10–90 % output transitions, energy per input cycle). |
| Plots | ✓ | [plots.py](plots.py) | One panel per case: ring frequency with energy per cycle versus supply, and with tuning gain versus control; delay line delay with energy versus supply, and with output transitions versus control. Run by `flow.analysis.runner delay_characterization_study`. |
| Analysis tests | ✓ | [test_analysis.py](test_analysis.py) | Synthetic records of known frequency, delay, and current; every plot renders. |
| Layout generator | ✓ | [layout.py](layout.py) | Standard-cell rows with cIcCreator, laygo and ALIGN from hand-written floorplans (`design/layout/delay_*.json`). |
| Layout tests | ✓ | [test_layout.py](test_layout.py) | Target registry; every floorplan places each netlist device once and escapes ports the netlist connects; every PDK writes every case. |
| Layout runner | ✓ | [layout.py](layout.py) | Seven cases in all six PDKs: 124 of 126 layouts DRC clean and LVS correct. ALIGN's detailed router leaves a net open in `ring4_tail` (tower180) and `ring5_starved` (tpsc65); cIcCreator and laygo are clean there. |
| DRC runner | ✓ | [layout.py](layout.py) | gdscheck and the PDK's DRC for every layout (`row_signoff`). |
| LVS runner | ✓ | [layout.py](layout.py) | The PDK's LVS for every layout against the netlist the build placed. |
| PEX runner | ✗ | - | No extraction. |

Inspiration: bag3_digital `inv_chain`, `inv_diff_chain`, `current_starved_inv`; BAG `clk_delay_*`, `clk_diff_inv_coupled*`, `vco_ro_diff_coupled`, `vco_vco`; Usb2Phy `IloStage`, `IloRing`.
