# Status

| Feature | Status | File | Notes |
|---|---|---|---|
| Netlist generator | ✓ | [subckt.py](subckt.py) | Single/two-stage comparator variants with held differential outputs. |
| Netlist tests | ✓ | [test_subckt.py](test_subckt.py) | Default topology and output-latch wiring. |
| Testbench generator | ✓ | [sim.py](sim.py) | Common-mode/differential-input sweeps and repeated decisions. |
| Simulation runners | ✓ | [sim.py](sim.py) | Size/topology campaign and FRIDA-1-sized noise target. |
| Layout generator | ✗ | - | No generated comparator layout in this block. |
| Layout tests | ✗ | - | No block layout tests. |
| Layout runner | ✗ | - | Not implemented. |
| DRC runner | ✗ | - | No standalone comparator runner. |
| LVS runner | ✗ | - | No standalone comparator runner. |
| PEX runner | ✗ | - | No standalone comparator runner. |

TODO: investigate settling, metastability, kickback, and offset; develop the
planned transistor-placement/layout flow. See [project TODO](../../docs/todo.md#comp).
