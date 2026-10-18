# Status

| Feature | Status | File | Notes |
|---|---|---|---|
| Netlist generator | ✓ | [subckt.py](subckt.py) | `PolyRes`: the ideal resistance between the two heads. |
| Netlist tests | ✓ | [test_subckt.py](test_subckt.py) | Ports of the ideal view. |
| Simulation | ✓ | [sim.py](sim.py) | `polyres_device`: the PDK's resistor as an external module at the drawn width and length (with its substrate terminal where the model has one); `polyres_check` biases each PDK's narrowest 4 µm resistor in Spectre at its typical models: within 0.1 % of the cell's model value in TSMC65, Tower180, TPSC65 (its N+ poly resistor), IHP130 and LF150, 0.5 % in TSMC28 (its ends' width bias). |
| Simulation tests | ✓ | [test_sim.py](test_sim.py) | The devices' terminals; one TSMC65 resistor against Spectre (`-m spectre`). |
| Layout generator | ✓ | [layout.py](layout.py), [`stems/rescell.py`](../layout/stems/rescell.py) | An unsilicided P+ poly resistor as a stems row cell: one row tall (two rows sharing their VDD rail in TSMC28, whose resistor needs dummy poly beside it; in TPSC65, whose poly resistors all lie in an HV region the rails' tap counter-dope may not share, an island of its own with a substrate tap), both rails with their taps, implant bands and well band (`rowcell.rails`), so it abuts transistor and standard cells. The body runs along the row between two contact heads, each with an M1 pad, a via and an M2 pin on one track. Everything comes from the PDK's `tech.RES` (device, sheet resistance, width reduction, head resistance, markers, implant, spacings). |
| Layout tests | ✓ | [test_layout.py](test_layout.py) | Every PDK's cell is one row with both rails and both pins, its model value; short bodies lengthen to their marker area; narrow ones are rejected. |
| Layout runner | ✓ | [layout.py](layout.py) | `polyres_signoff`: a 4 µm resistor at each PDK's narrowest width, its DRC and LVS. |
| DRC runner | ✓ | [layout.py](layout.py) | Clean in all six PDKs (TSMC65 with its block waivers); TPSC65's island at 0.4-2 µm width and 10 µm or longer (its model's domain). IHP130's KLayout deck needs KLayout 0.29.11 or newer (juno has 0.30.12). |
| LVS runner | ✓ | [layout.py](layout.py) | Correct against the PDK's device in TSMC65 and TSMC28 (length and width compared; a wrong length fails), Tower180 and LF150 (their resistance compared, and equal to the cell's model value), IHP130 (width and length) and TPSC65 (its deck's own sheet over the squares). The TPSC65 resistor's layers are the kit's own cell's (streamed out of its PCell library with Virtuoso). |
| PEX runner | - | - | Not applicable: the resistance is the PDK device's (its model, checked in Spectre above); a block's extraction brings the wiring around it. |

The resistance is the PDK model's: the sheet over the squares (with the model's width reduction) plus both heads (`rescell.res_value`). Tower180's and LF150's LVS compare it, and match.

