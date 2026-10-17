# Status

| Feature | Status | File | Notes |
|---|---|---|---|
| Netlist generator | ✓ | [subckt.py](subckt.py) | Source followers and flipped voltage followers, NMOS or PMOS input, an optional output sink on a flipped follower. |
| Netlist tests | ✓ | [test_subckt.py](test_subckt.py) | Drain and gate wiring, the flipped follower's feedback, invalid followers. |
| Testbench generator | ✓ | [sim.py](sim.py) | Usb2Phy's `UnityGainTb`: the input a DC level with 1 V of AC, current-reference biases (a diode-connected copy fed 20 µA from a supply of its own), a 100 fF load; or the AC on a test current into the output (1 V through 1 MΩ, DC blocked) for the output impedance. |
| Simulation runners | ✓ | [sim.py](sim.py) | `follower_characterization`: operating point and AC response of every case at 25 input levels from ground to the supply, the AC on the input and on the output, in each PDK about its own core supply (200 runs per PDK, all 1200 in four minutes on 16 workers); `check=True` runs Spectre's static checks at the nominal input. |
| Analysis | ✓ | [analysis.py](analysis.py) | `MeasFollower`; `analyze_follower_transfer` (output level, small-signal gain, −3 dB bandwidth, supply current), `analyze_follower_impedance` (output impedance). In TSMC65 the flipped followers reach 0.3–1.1 kΩ in their working range, the plain ones 2.2–3.6 kΩ; across the PDKs the flipped ones span 60 Ω–1.1 kΩ. |
| Plots | ✓ | [plots.py](plots.py) | One panel per case: transfer and gain, bandwidth and output impedance versus input level, gain and impedance versus frequency at each case's input of highest gain (a fixed share of the supply leaves some PDK's flipped followers outside their range); one figure set per PDK. Run by `flow.analysis.runner follower_characterization_study`. |
| Analysis tests | ✓ | [test_analysis.py](test_analysis.py) | Single-pole responses of known gain, bandwidth and impedance; every plot renders. |
| Layout generator | ✓ | [layout.py](layout.py) | Standard-cell rows with cIcCreator, laygo and ALIGN from hand-written floorplans (`design/layout/follower_*.json`). |
| Layout tests | ✓ | [test_layout.py](test_layout.py) | Target registry; every floorplan places each netlist device once and escapes every connected port; every PDK writes every case. |
| Layout runner | ✓ | [layout.py](layout.py) | Four cases in all six PDKs, all 72 layouts DRC clean and LVS correct. A source follower's drain sits on the other type's rail: the row cells tie it in-cell (`rowcell` ties, ALIGN's `far` flag). |
| DRC runner | ✓ | [layout.py](layout.py) | gdscheck and the PDK's DRC for every layout (`row_signoff`). |
| LVS runner | ✓ | [layout.py](layout.py) | The PDK's LVS for every layout against the netlist the build placed. |
| PEX runner | ✗ | - | No extraction. |

Inspiration: BAG `source_follower`, `super_source_follower_n`/`_p` (without their bias DACs); Usb2Phy `UnityGainBuffer`.
