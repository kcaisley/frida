# Status

| Feature | Status | File | Notes |
|---|---|---|---|
| Netlist generator | ✓ | [subckt.py](subckt.py) | Generic XORs; TSMC65, TSMC28, and Tower180 PDK mappings. |
| Netlist tests | ✓ | [test_subckt.py](test_subckt.py) | Drive bands, wiring, and public-API PDK isolation. |
| Testbench generator | ✗ | - | No standalone testbench planned; validate in ADC integration. |
| Simulation runners | ✗ | - | No standalone simulation runner planned. |
| Layout generator | ✗ | - | Reuses the fixed FRIDA-1 macro; no new geometry generated. |
| Layout tests | ✓ | [test_signoff.py](test_signoff.py) | Export preservation and mocked orchestration, not physical signoff. |
| Layout runner | ✓ | [layout.py](layout.py) | Exports the fixed macro and generates its TSMC65 source. |
| DRC runner | ✓ | [layout.py](layout.py) | ✗ Seven M4-area precheck violations; foundry DRC not reached. |
| LVS runner | ✓ | [layout.py](layout.py) | ✗ DNW layout devices mismatch ordinary upstream source models. |
| PEX runner | ✗ | - | Not implemented. |

TODO: review standalone M4 violations; provide a DNW-aware LVS source; rerun
DRC/LVS before adding PEX. ADC-level driver/array separation remains incomplete.
See [project TODO](../../docs/todo.md#capdriver).
