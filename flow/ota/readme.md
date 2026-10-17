# Status

| Feature | Status | File | Notes |
|---|---|---|---|
| Netlist generator | ✓ | [subckt.py](subckt.py) | Five-transistor, telescopic, folded-cascode and self-biased amplifiers, NMOS or PMOS input, an optional common-source second stage (its Miller capacitor for simulation only). |
| Netlist tests | ✓ | [test_subckt.py](test_subckt.py) | Mirror polarity, cascode stacks, folding, self-biasing, second stage, invalid amplifiers. |
| Testbench generator | ✓ | [sim.py](sim.py) | Usb2Phy's op-amp bench (`OpAmp5T` `Tb`, `FcascTb`): a balun (input common mode on both inputs, ±0.5 V AC), bias references (a diode-connected copy of the devices each bias drives, fed their current from a supply of its own, so the supply current is the amplifier's), fixed cascode biases, 50 fF loads; a fully differential output adds an ideal common-mode feedback onto the load bias (its `vbp` shows as high impedance in Spectre's checks: a controlled source drives it). |
| Simulation runners | ✓ | [sim.py](sim.py) | `ota_characterization`: operating point, AC response and output noise (1 kHz–100 GHz) of every case over input common modes from 1/6 to 5/6 of the supply and supplies at 75–108 % of it, in each PDK about its own core supply (132 runs per PDK, all 792 in three minutes on 16 workers); `check=True` runs Spectre's static checks at the nominal point. Spectre writes a noise analysis's output, input and gain only in PSF, so these runs ask for PSF ASCII, which VLSIR reads. |
| Analysis | ✓ | [analysis.py](analysis.py) | `MeasOta`; `analyze_ota_ac` (DC gain, unity-gain bandwidth, phase margin, supply current, output common mode; NaN where the ideal feedback drives vbp beyond the rails, which no real feedback could hold), `analyze_ota_noise` (input-referred density, its 1 MHz spot value, RMS to the unity-gain bandwidth). At the core supply and mid-supply input in TSMC65: 20–36 dB, 0.5–1.7 GHz and 13–46 nV/√Hz for the one-stage amplifiers; `two_stage` 56 dB with a −5° margin, as expected without its Miller capacitor. The 150 and 180 nm PDKs' devices give the most gain (`telescopic` 48–50 dB); `folded` cannot hold its output common mode at the lowest supplies in five PDKs. |
| Plots | ✓ | [plots.py](plots.py) | One panel per case: Bode at the nominal point, gain and bandwidth versus input common mode, spot and integrated input noise versus input common mode, bandwidth and power versus supply; one figure set per PDK. Run by `flow.analysis.runner ota_characterization_study`. |
| Analysis tests | ✓ | [test_analysis.py](test_analysis.py) | A two-pole response of known gain, bandwidth and margin; every plot renders. |
| Layout generator | ✓ | [layout.py](layout.py) | Standard-cell rows with cIcCreator, laygo and ALIGN from hand-written floorplans (`design/layout/ota_*.json`), each pair mirrored in one row. |
| Layout tests | ✓ | [test_layout.py](test_layout.py) | Target registry; every floorplan places each netlist device once and escapes ports the netlist connects; every PDK writes every case. |
| Layout runner | ✓ | [layout.py](layout.py) | Six cases in all six PDKs, all 108 layouts DRC clean and LVS correct (the two-stage case without its Miller capacitor: the row cells draw MOS only). |
| DRC runner | ✓ | [layout.py](layout.py) | gdscheck and the PDK's DRC for every layout (`row_signoff`). |
| LVS runner | ✓ | [layout.py](layout.py) | The PDK's LVS for every layout against the netlist the build placed. |
| PEX runner | ✗ | - | No extraction. |

The differential amplifiers need a common-mode feedback outside the block (vbp sets their output common mode). Inspiration: Usb2Phy `OpAmp5T`, `Fcasc`; CT-DS-ADC `stage1_telescopic_amplifier`, `two_stage_amplifier`; bag3_analog `diffamp_self_biased`; BAG `diffamp`.
