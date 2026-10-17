# Status

| Feature | Status | File | Notes |
|---|---|---|---|
| Netlist generator | ✓ | [subckt.py](subckt.py) | Current sources: parallel, optionally cascoded NMOS or PMOS units on one bias, always on, switched or steered, with an optional diode reference. |
| Netlist tests | ✓ | [test_subckt.py](test_subckt.py) | Bias sharing, PMOS complements, the mirror's diode, invalid units. |
| Testbench generator | ✓ | [sim.py](sim.py) | Usb2Phy's `IdacSweepTb`: out and dump held by sources whose currents are the unit's, the bias a gate voltage or a diode reference's current, an operating point and a DC sweep of the output voltage. |
| Simulation runners | ✓ | [sim.py](sim.py) | `idac_characterization`: every unit's output sweep (0–1.2 V) over gate drives 0.35–0.85 V or reference currents 1–50 µA, enabled and, where it switches, disabled (72 TSMC65 runs); `check=True` runs Spectre's static checks at the nominal bias. |
| Analysis | ✓ | [analysis.py](analysis.py) | `MeasIdac`; `analyze_idac_output` (current, output resistance, 5 % compliance range), `analyze_idac_steering` (on-off ratio, current lost between the states: under 0.01 % for the steered units). |
| Plots | ✓ | [plots.py](plots.py) | One panel per case: the output characteristic at the nominal bias, current and output resistance versus bias, on and off current of the switched units. Run by `flow.analysis.runner idac_characterization_study`. |
| Analysis tests | ✓ | [test_analysis.py](test_analysis.py) | Synthetic sweeps of known current, resistance, knee and leakage; every plot renders. |
| Layout generator | ✓ | [layout.py](layout.py) | Standard-cell rows with cIcCreator, laygo and ALIGN from hand-written floorplans (`design/layout/idac_*.json`). |
| Layout tests | ✓ | [test_layout.py](test_layout.py) | Target registry; every floorplan places each netlist device once and escapes every connected port; every PDK writes every case. |
| Layout runner | ✓ | [layout.py](layout.py) | Four cases in all six PDKs, all 72 layouts DRC clean and LVS correct. |
| DRC runner | ✓ | [layout.py](layout.py) | gdscheck and the PDK's DRC for every layout (`row_signoff`). |
| LVS runner | ✓ | [layout.py](layout.py) | The PDK's LVS for every layout against the netlist the build placed. |
| PEX runner | ✗ | - | No extraction. |

Inspiration: Usb2Phy `NmosIdac`, `PmosIdacUnit`, cmlpi `IdacUnit`, `PmosBiasDist`; BAG `ra_bias_unit`.
