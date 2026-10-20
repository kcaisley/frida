# Status

| Feature | Status | File | Notes |
|---|---|---|---|
| Netlist generator | ✓ | [subckt.py](subckt.py) | NMOS, PMOS, or transmission-gate switch; half-size charge-injection dummies; bootstrapped NMOS gate (after ciccreator's SARBSSW and BAG's bootstrap, with a MOS boost capacitor); PDK-compiled devices fingered to the row cells. |
| Netlist tests | ✓ | [test_subckt.py](test_subckt.py) | Generator checks, dummies and bootstrap wiring. |
| Testbench generator | ✓ | [sim.py](sim.py) | Complementary clocks (tracking while `clk` is high), an input level, and a load capacitor; with an input step the input toggles by it once per period in mid-hold, so every track phase settles from a known step. |
| Simulation runners | ✓ | [sim.py](sim.py) | `samp_characterization`: every named switch into 1 pF at a 10 ns clock, its input stepping a twelfth of the supply each period, over input levels 1/12–11/12 of the supply and over the supply (75–108 %, mid-supply input), in each PDK (16 runs per case and PDK, all 384 in under two minutes on 16 workers); `frida1_transient` stays the TSMC65 FRIDA-1 reference. `check=True` runs Spectre's static checks. |
| Analysis | ✓ | [analysis.py](analysis.py) | `MeasSamp`; `analyze_samp_track` (track-phase time constant, on-resistance into the load, bandwidth, track error), `analyze_samp_hold` (pedestal, droop, input feedthrough). In TSMC65 into 1 pF: the transmission gates 140–560 Ω (highest at mid-supply), the NMOS switch from 140 Ω to open above 0.7 V, the bootstrapped one 210–620 Ω; pedestals within ±0.7 mV for the transmission gates, −2 mV for the NMOS switches. |
| Plots | ✓ | [plots.py](plots.py) | One panel per switch: on-resistance and track error versus input, pedestal and feedthrough versus input, on-resistance and bandwidth versus supply, the last two periods; one figure set per PDK. Run by `flow.analysis.runner samp_characterization_study`. |
| Analysis tests | ✓ | [test_analysis.py](test_analysis.py) | An ideal RC sampler of known time constant, pedestal and feedthrough; every plot renders. |
| Layout generator | ✓ | [layout.py](layout.py) | Standard-cell rows with cIcCreator, laygo and ALIGN (`flow/layout`) from hand-written floorplans (`design/layout/samp_*.json`). |
| Layout tests | ✓ | [test_layout.py](test_layout.py) | Target registry; every floorplan places each netlist device once and escapes ports the netlist connects. |
| Layout runner | ✓ | [layout.py](layout.py) | Transmission gate, transmission gate with dummies, bootstrapped switch and the NMOS switch alone (folded over two rows) in all six PDKs, all 66 layouts DRC clean and LVS correct. |
| DRC runner | ✓ | [layout.py](layout.py) | gdscheck and the PDK's DRC for every layout (`row_signoff`). |
| LVS runner | ✓ | [layout.py](layout.py) | The PDK's LVS for every layout against the netlist the build placed. |
| PEX runner | ✗ | - | No standalone sampler runner. |

The bootstrap keeps every PMOS body on vdd (the row cells' wells): the boosted node's junctions leak toward vdd while sampling. Its cascoded gate pull-down is a stack of two clocked devices (a gate on a rail has no route in the row cells).

TODO: sampling noise (kT/C) separately from comparator offset, and the resistance versus sizing. See [project TODO](../../docs/todo.md#samp).
