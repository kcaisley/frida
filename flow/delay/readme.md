# Status

| Feature | Status | File | Notes |
|---|---|---|---|
| Netlist generator | ✓ | [subckt.py](subckt.py) | Delay lines and ring oscillators: inverter or coupled pseudo-differential stages, single-ended or differential, current-starved or shared-tail control, a NAND enable and an injection device in a ring. |
| Netlist tests | ✓ | [test_subckt.py](test_subckt.py) | Stage wiring, ring closure and enable, coupling, starving and tail devices, invalid chains. |
| Testbench generator | ✓ | [sim.py](sim.py) | Complementary input pulses (a chain) or an enable step (a ring), bias sources, loads. |
| Simulation runners | ✓ | [sim.py](sim.py) | TSMC65 transients: inverter delay line, inverter, starved and coupled rings. |
| Layout generator | ✓ | [layout.py](layout.py) | Standard-cell rows with cIcCreator, laygo and ALIGN from hand-written floorplans (`design/layout/delay_*.json`). |
| Layout tests | ✓ | [test_layout.py](test_layout.py) | Target registry; every floorplan places each netlist device once and escapes ports the netlist connects; every PDK writes every case. |
| Layout runner | ✓ | [layout.py](layout.py) | Seven cases in all six PDKs: 124 of 126 layouts DRC clean and LVS correct. ALIGN's detailed router leaves a net open in `ring4_tail` (tower180) and `ring5_starved` (tpsc65); cIcCreator and laygo are clean there. |
| DRC runner | ✓ | [layout.py](layout.py) | gdscheck and the PDK's DRC for every layout (`row_signoff`). |
| LVS runner | ✓ | [layout.py](layout.py) | The PDK's LVS for every layout against the netlist the build placed. |
| PEX runner | ✗ | - | No extraction. |

Inspiration: bag3_digital `inv_chain`, `inv_diff_chain`, `current_starved_inv`; BAG `clk_delay_*`, `clk_diff_inv_coupled*`, `vco_ro_diff_coupled`, `vco_vco`; Usb2Phy `IloStage`, `IloRing`.
