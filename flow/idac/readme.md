# Status

| Feature | Status | File | Notes |
|---|---|---|---|
| Netlist generator | ✓ | [subckt.py](subckt.py) | Current sources: parallel, optionally cascoded NMOS or PMOS units on one bias, always on, switched or steered, with an optional diode reference. |
| Netlist tests | ✓ | [test_subckt.py](test_subckt.py) | Bias sharing, PMOS complements, the mirror's diode, invalid units. |
| Testbench generator | ✓ | [sim.py](sim.py) | Usb2Phy's `IdacSweepTb`: out and dump held by sources whose currents are the unit's, the bias a reference current into the unit's own diode or a diode-connected copy of its source device (from a supply of its own), an operating point and a DC sweep of the output voltage. |
| Simulation runners | ✓ | [sim.py](sim.py) | `idac_characterization`: every unit's output sweep (ground to the supply) over reference currents 1–50 µA, enabled and, where it switches, disabled, in each PDK about its own core supply (42 runs per PDK, all 252 in under two minutes on 16 workers); `check=True` runs Spectre's static checks at the nominal bias. |
| Analysis | ✓ | [analysis.py](analysis.py) | `MeasIdac`; `analyze_idac_output` (current, output resistance, 5 % compliance range), `analyze_idac_steering` (on-off ratio, current lost between the states: under 0.01 % for the steered units). At 10 µA two NMOS units give about 20 µA in every PDK. |
| Plots | ✓ | [plots.py](plots.py) | One panel per case: the output characteristic at the nominal bias, current and output resistance versus reference current, on and off current of the switched units; one figure set per PDK. Run by `python -m flow idac.characterization_study`. |
| Analysis tests | ✓ | [test_analysis.py](test_analysis.py) | Synthetic sweeps of known current, resistance, knee and leakage; every plot renders. |
| Layout generator | ✓ | [layout.py](layout.py) | Standard-cell rows with cIcCreator, laygo and ALIGN from hand-written floorplans (`design/layout/idac_*.json`). |
| Layout tests | ✓ | [test_layout.py](test_layout.py) | Target registry; every floorplan places each netlist device once and escapes every connected port; every PDK writes every case. |
| Layout runner | ✓ | [layout.py](layout.py) | Four cases in all six PDKs, all 72 layouts DRC clean and LVS correct. |
| DRC runner | ✓ | [layout.py](layout.py) | gdscheck and the PDK's DRC for every layout (`row_signoff`). |
| LVS runner | ✓ | [layout.py](layout.py) | The PDK's LVS for every layout against the netlist the build placed. |
| PEX runner | ✗ | - | No extraction. |

Inspiration: Usb2Phy `NmosIdac`, `PmosIdacUnit`, cmlpi `IdacUnit`, `PmosBiasDist`; BAG `ra_bias_unit`.
