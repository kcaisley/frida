# Status

| Feature | Status | File | Notes |
|---|---|---|---|
| Netlist generator | ✓ | [subckt.py](subckt.py) | `PolyRes`: the ideal resistance between the two heads. |
| Netlist tests | ✓ | [test_subckt.py](test_subckt.py) | Ports of the ideal view. |
| Layout generator | ✓ | [layout.py](layout.py), [`stems/rescell.py`](../layout/stems/rescell.py) | An unsilicided P+ poly resistor as a stems row cell: one row tall, both rails with their taps, implant bands and well band (`rowcell.rails`), so it abuts transistor and standard cells. The body runs along the row between two contact heads, each with an M1 pad, a via and an M2 pin on one track. Everything comes from the PDK's `tech.RES` (device, sheet resistance, width reduction, head resistance, markers, implant, spacings). |
| Layout tests | ✓ | [test_layout.py](test_layout.py) | Every PDK's cell is one row with both rails and both pins, its model value; short bodies lengthen to their marker area; narrow ones are rejected. |
| Layout runner | ✓ | [layout.py](layout.py) | `polyres_signoff`: a 4 µm resistor at each PDK's narrowest width, its DRC and LVS. |
| DRC runner | ✓ | [layout.py](layout.py) | Clean in TSMC65 (block waivers), Tower180, IHP130 and LF150. TPSC65 flags only the row cells' edge (the P+ band's end inside the well band, every TPSC65 row cell's standalone). IHP130's KLayout deck needs KLayout 0.29.11 or newer (`/local/kcaisley/tools/frida-layout.env` on juno). |
| LVS runner | ✓ | [layout.py](layout.py) | Correct against the PDK's device in TSMC65 (length and width compared; a wrong length fails), Tower180 and LF150 (their resistance compared, and equal to the cell's model value). IHP130's deck extracts the device but no nets yet; TPSC65's encrypted deck extracts nothing: its recognition is unknown. |
| PEX runner | ✗ | - | No extraction of the resistor itself. |

TSMC28 has no resistor row cell: its high-R poly needs dummy poly on both sides inside the resistor implant, and a P-metal-gate cover, about 1.5 µm across, and its row is 0.9 µm.

The resistance is the PDK model's: the sheet over the squares (with the model's width reduction) plus both heads (`rescell.res_value`). Tower180's and LF150's LVS compare it, and match.

TODO: the netlist view of the PDK device for simulation (PhysicalResistor mappings); TPSC65 LVS recognition; a two-row TSMC28 cell.
