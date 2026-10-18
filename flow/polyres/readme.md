# Status

| Feature | Status | File | Notes |
|---|---|---|---|
| Netlist generator | ✓ | [subckt.py](subckt.py) | `PolyRes`: the ideal resistance between the two heads. |
| Netlist tests | ✓ | [test_subckt.py](test_subckt.py) | Ports of the ideal view. |
| Simulation | ✓ | [sim.py](sim.py) | `polyres_device`: the PDK's resistor as an external module at the drawn width and length (with its substrate terminal where the model has one); `polyres_check` biases each PDK's narrowest 4 µm resistor in Spectre at its typical models: within 0.1 % of the cell's model value in TSMC65, Tower180, TPSC65, IHP130 and LF150, 0.5 % in TSMC28 (its ends' width bias). |
| Simulation tests | ✓ | [test_sim.py](test_sim.py) | The devices' terminals; one TSMC65 resistor against Spectre (`-m spectre`). |
| Layout generator | ✓ | [layout.py](layout.py), [`stems/rescell.py`](../layout/stems/rescell.py) | An unsilicided P+ poly resistor as a stems row cell: one row tall (two rows sharing their VDD rail in TSMC28, whose resistor needs dummy poly beside it), both rails with their taps, implant bands and well band (`rowcell.rails`), so it abuts transistor and standard cells. The body runs along the row between two contact heads, each with an M1 pad, a via and an M2 pin on one track. Everything comes from the PDK's `tech.RES` (device, sheet resistance, width reduction, head resistance, markers, implant, spacings). |
| Layout tests | ✓ | [test_layout.py](test_layout.py) | Every PDK's cell is one row with both rails and both pins, its model value; short bodies lengthen to their marker area; narrow ones are rejected. |
| Layout runner | ✓ | [layout.py](layout.py) | `polyres_signoff`: a 4 µm resistor at each PDK's narrowest width, its DRC and LVS. |
| DRC runner | ✓ | [layout.py](layout.py) | Clean in TSMC65 (block waivers), TSMC28, Tower180, IHP130 and LF150. TPSC65 flags only the row frame's edge (the P+ band's end inside the well band), which a bare TPSC65 rails cell flags standalone too. IHP130's KLayout deck needs KLayout 0.29.11 or newer (`/local/kcaisley/tools/frida-layout.env` on juno). |
| LVS runner | ✓ | [layout.py](layout.py) | Correct against the PDK's device in TSMC65 and TSMC28 (length and width compared; a wrong length fails), Tower180 and LF150 (their resistance compared, and equal to the cell's model value) and IHP130 (width and length). TPSC65's encrypted deck recognizes nothing in it: none of a dozen candidate markers from the kit's layer map makes it a device. |
| PEX runner | ✗ | - | No extraction of the resistor itself. |

The resistance is the PDK model's: the sheet over the squares (with the model's width reduction) plus both heads (`rescell.res_value`). Tower180's and LF150's LVS compare it, and match.

TODO: TPSC65 LVS recognition.
