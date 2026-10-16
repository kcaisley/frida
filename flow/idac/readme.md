# Status

| Feature | Status | File | Notes |
|---|---|---|---|
| Netlist generator | ✓ | [subckt.py](subckt.py) | Current sources: parallel, optionally cascoded NMOS or PMOS units on one bias, always on, switched or steered, with an optional diode reference. |
| Netlist tests | ✓ | [test_subckt.py](test_subckt.py) | Bias sharing, PMOS complements, the mirror's diode, invalid units. |
| Testbench generator | ✓ | [sim.py](sim.py) | out and dump held by sources (their currents are the unit's), the bias a voltage or a reference current. |
| Simulation runners | ✓ | [sim.py](sim.py) | TSMC65 operating points: four steered NMOS units, the PMOS bias mirror. |
| Layout generator | ✓ | [layout.py](layout.py) | Standard-cell rows with cIcCreator, laygo and ALIGN from hand-written floorplans (`design/layout/idac_*.json`). |
| Layout tests | ✓ | [test_layout.py](test_layout.py) | Target registry; every floorplan places each netlist device once and escapes every connected port; every PDK writes every case. |
| Layout runner | ✓ | [layout.py](layout.py) | Four cases in all six PDKs, all 72 layouts DRC clean and LVS correct. |
| DRC runner | ✓ | [layout.py](layout.py) | gdscheck and the PDK's DRC for every layout (`row_signoff`). |
| LVS runner | ✓ | [layout.py](layout.py) | The PDK's LVS for every layout against the netlist the build placed. |
| PEX runner | ✗ | - | No extraction. |

Inspiration: Usb2Phy `NmosIdac`, `PmosIdacUnit`, cmlpi `IdacUnit`, `PmosBiasDist`; BAG `ra_bias_unit`.
