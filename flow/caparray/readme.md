# Status

| Feature | Status | File | Notes |
|---|---|---|---|
| Netlist generator | ✓ | [subckt.py](subckt.py) | Passive main/diff array; ideal leaf in `unit.py`. |
| Netlist tests | ✓ | [test_subckt.py](test_subckt.py), [test_unit.py](test_unit.py) | Sizing, topology, and ideal leaf. |
| Testbench generator | ✓ | [sim.py](sim.py) | Drives the passive main/diff array with complementary ideal voltage sources. |
| Simulation runners | ✓ | [sim.py](sim.py) | TSMC65 code ramp; new standard-cell path still needs electrical validation. |
| Layout generator | ✓ | [laygen.py](laygen.py) | Works; internals need substantial cleanup, preserving the API. |
| Layout tests | ✓ | [test_subckt.py](test_subckt.py) | Geometry tests; reviewed TSMC65 fixtures also live in the PDK. |
| Layout runner | ✓ | [layout.py](layout.py) | Three named metal-stack variants. |
| DRC runner | ✓ | [layout.py](layout.py) | Shared/PDK dispatch; configured exclusions. Current end-to-end run pending. |
| LVS runner | ✓ | [layout.py](layout.py) | Recorded full-array passes; repeat with current end-to-end flow. |
| PEX runner | ✓ | [layout.py](layout.py), [pex.py](pex.py) | 3D xACT and capacitance tables; current end-to-end validation pending. |

TODO: clean up `laygen.py`; guard the nominal model's geometry range; validate
PEX completeness; finish ADC-level driver/array separation. See
[project TODO](../../docs/todo.md).

The planned `convert_netlist_caparray_to_measurement()` adapter consumes parasitic
extraction results for design-versus-extracted capacitance, with later support
for Monte Carlo capacitance variation. It currently raises `NotImplementedError`;
it is not the transient `MeasCdacInt` waveform path.

Its prototype takes `netlist_path`, `CapArrayParams`, `net_names` and
`device_names` (raw netlist identifiers → analysis aliases), and returns
`MeasCapArray`. That result type reserves the run information and parameters;
its capacitance payload and HDF5 registration remain to be defined.
