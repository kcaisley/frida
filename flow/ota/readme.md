# Status

| Feature | Status | File | Notes |
|---|---|---|---|
| Netlist generator | ✓ | [subckt.py](subckt.py) | Five-transistor, telescopic, folded-cascode and self-biased amplifiers, NMOS or PMOS input, an optional common-source second stage (its Miller capacitor for simulation only). |
| Netlist tests | ✓ | [test_subckt.py](test_subckt.py) | Mirror polarity, cascode stacks, folding, self-biasing, second stage, invalid amplifiers. |
| Testbench generator | ✓ | [sim.py](sim.py) | Usb2Phy's op-amp bench (`OpAmp5T` `Tb`, `FcascTb`): a balun (input common mode on both inputs, ±0.5 V AC), fixed biases, 50 fF loads; a fully differential output adds an ideal common-mode feedback onto the load bias (its `vbp` shows as high impedance in Spectre's checks: a controlled source drives it). |
| Simulation runners | ✓ | [sim.py](sim.py) | `ota_characterization`: operating point and AC response (1 kHz–100 GHz) of every case over input common modes 0.2–1.0 V and supplies 0.9–1.3 V in TSMC65 (132 runs, under a minute on 16 workers); `check=True` runs Spectre's static checks at the nominal point. No noise: VLSIR's nutbin reader cannot read Spectre's noise analysis. |
| Analysis | ✓ | [analysis.py](analysis.py) | `MeasOta`; `analyze_ota_ac` (DC gain, unity-gain bandwidth, phase margin, supply current, output common mode). At 1.2 V and 0.6 V in TSMC65: 15–33 dB and 0.4–1.7 GHz for the one-stage amplifiers; `two_stage` 52 dB with a −3° margin, as expected without its Miller capacitor. |
| Plots | ✓ | [plots.py](plots.py) | One panel per case: Bode at the nominal point, gain and bandwidth versus input common mode, bandwidth and power versus supply. Run by `flow.analysis.runner ota_characterization_study`. |
| Analysis tests | ✓ | [test_analysis.py](test_analysis.py) | A two-pole response of known gain, bandwidth and margin; every plot renders. |
| Layout generator | ✓ | [layout.py](layout.py) | Standard-cell rows with cIcCreator, laygo and ALIGN from hand-written floorplans (`design/layout/ota_*.json`), each pair mirrored in one row. |
| Layout tests | ✓ | [test_layout.py](test_layout.py) | Target registry; every floorplan places each netlist device once and escapes ports the netlist connects; every PDK writes every case. |
| Layout runner | ✓ | [layout.py](layout.py) | Six cases in all six PDKs, all 108 layouts DRC clean and LVS correct (the two-stage case without its Miller capacitor: the row cells draw MOS only). |
| DRC runner | ✓ | [layout.py](layout.py) | gdscheck and the PDK's DRC for every layout (`row_signoff`). |
| LVS runner | ✓ | [layout.py](layout.py) | The PDK's LVS for every layout against the netlist the build placed. |
| PEX runner | ✗ | - | No extraction. |

The differential amplifiers need a common-mode feedback outside the block (vbp sets their output common mode). Inspiration: Usb2Phy `OpAmp5T`, `Fcasc`; CT-DS-ADC `stage1_telescopic_amplifier`, `two_stage_amplifier`; bag3_analog `diffamp_self_biased`; BAG `diffamp`.
