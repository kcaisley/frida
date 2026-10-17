# Status

| Feature | Status | File | Notes |
|---|---|---|---|
| Netlist generator | ✓ | [subckt.py](subckt.py) | Passive main/diff array; ideal leaf in `unit.py`. |
| Netlist tests | ✓ | [test_subckt.py](test_subckt.py), [test_unit.py](test_unit.py) | Sizing, topology, and ideal leaf. |
| Testbench generator | ✓ | [sim.py](sim.py) | Drives every stage's main bottom plate with a packed code's bit and its diff plate with the complement, into 100 fF on the top plate; an explicit code sequence or the ramp over the DAC resolution. The leaf is the ideal MOM view (`unit.py`), so the transient is the same in every PDK. |
| Simulation runners | ✓ | [sim.py](sim.py) | `caparray_characterization`: four arrays (FRIDA-1's radix 1.7, radix 2 on repeated coarse units, 11-bit binary, sub-radix 2), each stage toggled alone and the packed ramp, in each PDK (48 runs, under a minute); `frida1_transfer_curve` stays the TSMC65 FRIDA-1 reference. |
| Analysis | ✓ | [analysis.py](analysis.py) | `MeasCapArrayTran`; `analyze_caparray_weights` (each stage's top-plate step against its design weight), `analyze_caparray_transfer` (the ramp's top plate against what the design weights predict, in unit capacitors). With the ideal leaf both agree with the design to simulator precision; the extracted array's capacitances are `pex.py`'s. |
| Plots | ✓ | [plots.py](plots.py) | One panel per array: stage weights, the ramp's transfer, its error against the design weights; one figure set per PDK. Run by `flow.analysis.runner caparray_characterization_study`. |
| Analysis tests | ✓ | [test_analysis.py](test_analysis.py) | A known 3-bit array's weights and ramp; every plot renders. |
| Layout generator | ✓ | [laygen.py](laygen.py) | Works; internals need substantial cleanup, preserving the API. |
| Layout tests | ✓ | [test_subckt.py](test_subckt.py) | Geometry tests; reviewed TSMC65 fixtures also live in the PDK. |
| Layout runner | ✓ | [layout.py](layout.py) | Three named metal-stack variants. |
| DRC runner | ✓ | [layout.py](layout.py) | Shared/PDK dispatch; configured exclusions. Current end-to-end run pending. |
| LVS runner | ✓ | [layout.py](layout.py) | Recorded full-array passes; repeat with current end-to-end flow. |
| PEX runner | ✓ | [layout.py](layout.py), [pex.py](pex.py) | 3D xACT and capacitance tables; current end-to-end validation pending. |

TODO: clean up `laygen.py`; guard the nominal model's geometry range; validate PEX completeness; finish ADC-level driver/array separation. See [project TODO](../../docs/todo.md).

The planned `convert_netlist_caparray_to_measurement()` adapter consumes parasitic extraction results for design-versus-extracted capacitance, with later support for Monte Carlo capacitance variation. It currently raises `NotImplementedError`; it is not a transient waveform path.

Its prototype takes `netlist_path`, `CapArrayParams`, `net_names` and `device_names` (raw netlist identifiers → analysis aliases), and returns `MeasCapArray`. That result type reserves the run information and parameters; its capacitance payload and HDF5 registration remain to be defined.
