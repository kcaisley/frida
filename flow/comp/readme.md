# Status

| Feature | Status | File | Notes |
|---|---|---|---|
| Netlist generator | ✓ | [subckt.py](subckt.py) | Single/two-stage comparator variants with held differential outputs. |
| Netlist tests | ✓ | [test_subckt.py](test_subckt.py) | Default topology and output-latch wiring. |
| Testbench generator | ✓ | [sim.py](sim.py) | Common-mode/differential-input sweeps and repeated decisions. |
| Simulation runners | ✓ | [sim.py](sim.py) | Size/topology campaign and FRIDA-1-sized noise target. |
| Layout generator | ✓ | [floorplan.py](../layout/floorplan.py) | Standard-cell rows with cIcCreator, laygo and ALIGN (`flow/layout`), from a hand-written floorplan or ALIGN's placement. |
| Layout tests | ✓ | [test_layout.py](test_layout.py) | Target registry and per-tool failure collection; the floorplan conversion in `flow/layout`. |
| Layout runner | ✓ | [layout.py](layout.py) | 30 per-PDK targets (frida1 and c040, manual and auto, mos_inv), five all-PDK targets, `all_comp_layouts`. |
| DRC runner | ✓ | [layout.py](layout.py) | gdscheck and the PDK's DRC for every layout (`row_signoff`). |
| LVS runner | ✓ | [layout.py](layout.py) | The PDK's LVS for every layout against the netlist the build placed. |
| PEX runner | ✗ | - | No comparator extraction. |

TODO: investigate settling, metastability, kickback, and offset; the tools placing by the floorplans' ALIGN groups. See [project TODO](../../docs/todo.md#comp).
