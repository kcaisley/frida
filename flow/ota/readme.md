# Status

| Feature | Status | File | Notes |
|---|---|---|---|
| Netlist generator | ✓ | [subckt.py](subckt.py) | Five-transistor, telescopic, folded-cascode and self-biased amplifiers, NMOS or PMOS input, an optional common-source second stage (its Miller capacitor for simulation only). |
| Netlist tests | ✓ | [test_subckt.py](test_subckt.py) | Mirror polarity, cascode stacks, folding, self-biasing, second stage, invalid amplifiers. |
| Testbench generator | ✓ | [sim.py](sim.py) | Open loop with a DC-only unity-gain feedback (1 GOhm, 1 F) and fixed biases. |
| Simulation runners | ✓ | [sim.py](sim.py) | TSMC65 operating point and AC response of the single-ended amplifiers. |
| Layout generator | ✓ | [layout.py](layout.py) | Standard-cell rows with cIcCreator, laygo and ALIGN from hand-written floorplans (`design/layout/ota_*.json`), each pair mirrored in one row. |
| Layout tests | ✓ | [test_layout.py](test_layout.py) | Target registry; every floorplan places each netlist device once and escapes ports the netlist connects; every PDK writes every case. |
| Layout runner | ✓ | [layout.py](layout.py) | Six cases in all six PDKs, all 108 layouts DRC clean and LVS correct (the two-stage case without its Miller capacitor: the row cells draw MOS only). |
| DRC runner | ✓ | [layout.py](layout.py) | gdscheck and the PDK's DRC for every layout (`row_signoff`). |
| LVS runner | ✓ | [layout.py](layout.py) | The PDK's LVS for every layout against the netlist the build placed. |
| PEX runner | ✗ | - | No extraction. |

The differential amplifiers need a common-mode feedback outside the block (vbp sets their output common mode). Inspiration: Usb2Phy `OpAmp5T`, `Fcasc`; CT-DS-ADC `stage1_telescopic_amplifier`, `two_stage_amplifier`; bag3_analog `diffamp_self_biased`; BAG `diffamp`.
