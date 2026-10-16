# Status

| Feature | Status | File | Notes |
|---|---|---|---|
| Netlist generator | ✓ | [subckt.py](subckt.py) | Decoupling capacitors between the rails (gate on the other rail) and two-net capacitors, NMOS, PMOS or both, in parallel units. |
| Netlist tests | ✓ | [test_subckt.py](test_subckt.py) | Decap and two-net wiring, units, invalid capacitors. |
| Testbench generator | ✓ | [sim.py](sim.py) | The AC stimulus on vdd (a decap) or on top (a two-net capacitor); the source current gives the capacitance. |
| Simulation runners | ✓ | [sim.py](sim.py) | TSMC65 AC capacitance: the two-net NMOS capacitor and the complementary decap. |
| Layout generator | ✓ | [layout.py](layout.py) | Standard-cell rows with cIcCreator, laygo and ALIGN from hand-written floorplans (`design/layout/moscap_*.json`). |
| Layout tests | ✓ | [test_layout.py](test_layout.py) | Target registry; every floorplan places each netlist device once and escapes every connected port; every PDK writes every case. |
| Layout runner | ✓ | [layout.py](layout.py) | Four cases in all six PDKs, all 72 layouts DRC clean and LVS correct. A decap's gate on the other rail is an M1 strap into that rail inside the cell. |
| DRC runner | ✓ | [layout.py](layout.py) | gdscheck and the PDK's DRC for every layout (`row_signoff`). |
| LVS runner | ✓ | [layout.py](layout.py) | The PDK's LVS for every layout against the netlist the build placed. |
| PEX runner | ✗ | - | No extraction. |

Inspiration: BAG `mos_cap`, `decap`, `decap_array`; the boost capacitor of the sampler's bootstrap.
