# Status

| Feature | Status | File | Notes |
|---|---|---|---|
| Netlist generator | ✓ | [subckt.py](subckt.py) | NMOS, PMOS, or transmission-gate switch; PDK-compiled devices. |
| Netlist tests | ✓ | [test_subckt.py](test_subckt.py) | Generator checks. |
| Testbench generator | ✓ | [sim.py](sim.py) | Complementary clocks, DC input, and capacitive load. |
| Simulation runners | ✓ | [sim.py](sim.py) | TSMC65 transient target; not a full resistance/noise characterization. |
| Layout generator | ✗ | - | No generated sampling-switch layout in this block. |
| Layout tests | ✗ | - | No block layout tests. |
| Layout runner | ✗ | - | Not implemented. |
| DRC runner | ✗ | - | No standalone sampler runner. |
| LVS runner | ✗ | - | No standalone sampler runner. |
| PEX runner | ✗ | - | No standalone sampler runner. |

TODO: characterize sampling time, resistance versus sizing/input voltage, and
sampling noise separately from comparator offset. See [project TODO](../../docs/todo.md#samp).
