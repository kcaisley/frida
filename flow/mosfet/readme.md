# Status

| Feature | Status | File | Notes |
|---|---|---|---|
| Netlist generator | ✗ | - | No matching circuit generator here; circuits use HDL21 MOS primitives and PDK compilation. |
| Netlist tests | ✗ | - | No block-specific circuit tests. |
| Testbench generator | ✗ | - | Layout-only package. |
| Simulation runners | ✗ | - | Layout-only package. |
| Layout generator | ✓ | [primitive.py](primitive.py) | Rule-derived fingered MOSFET geometry, rails, and contacts. |
| Layout tests | ✓ | [test_primitive.py](test_primitive.py) | IHP130 layout/export smoke test, not foundry signoff. |
| Layout runner | ✓ | [primitive.py](primitive.py) | Minimum/sweep export with optional images. |
| DRC runner | ✗ | - | No standalone MOSFET runner. |
| LVS runner | ✗ | - | No standalone MOSFET runner or matching reference source. |
| PEX runner | ✗ | - | No standalone MOSFET runner. |

TODO: add pin/abstract information for the proposed placement flow; establish
matching electrical references and physical checks before treating layouts as
verified devices. See [layout integration plan](../../docs/msor.md).
