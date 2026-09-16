# Status

| Feature | Status | File | Notes |
|---|---|---|---|
| Netlist generator | ✓ | [subckt.py](subckt.py) | Fixed 16-stage digital block; driver/array separation remains partial. |
| Netlist tests | ✓ | [test_subckt.py](test_subckt.py) | Hierarchy, interfaces, and stage conventions. |
| Testbench generator | ✓ | [sim.py](sim.py) | Generated ADC and extracted FRIDA-1/2 views. |
| Simulation runners | ✓ | [sim.py](sim.py) | Named timing and noise campaigns; require explicit PDK/extraction inputs. |
| Layout generator | ✓ | [laygen.py](laygen.py) | Assembles replacement blocks in a fixed template, not a new full-ADC layout. |
| Layout tests | ✓ | [test_layout.py](test_layout.py), [test_signoff.py](test_signoff.py) | Assembly compatibility and runner contracts. |
| Layout runner | ✓ | [layout.py](layout.py) | Historical FRIDA-1 and replacement-array FRIDA-2 targets. |
| DRC runner | ✓ | [layout.py](layout.py) | Shared/PDK dispatch with explicit exclusions; not unqualified signoff. |
| LVS runner | ✓ | [layout.py](layout.py) | Some historical variants explicitly expect a disconnected-MOM mismatch. |
| PEX runner | ✓ | [layout.py](layout.py) | Historical xRC and FRIDA-2 xACT; review results for the exact source revision. |

TODO: finish ADC-level driver/array composition; validate current assembled
DRC/LVS/PEX together. Timing, settling, and noise investigations remain in the
[project TODO](../../docs/todo.md).

## Simulation acquisition families

The seven entry points are `hdl21_sample_rate`, `frida1_sample_rate`,
`hdl21_transfer_curve`, `frida1_transfer_curve`, `frida1_sequence`,
`frida2_sequence`, and `frida1_supply_noise`. Sequence targets retain the four
reviewed recipes (16 FRIDA-1 and 12 FRIDA-2 cases). Separate FRIDA generations
keep their explicit extraction inputs and four-by-six / three-by-eight worker
budgets. Temporary seven-eighths-only campaign entry points are removed;
the complete sequence targets include those cases.

New runs use `build/sim/adc/<timestamp>_<target>/`. Each case keeps `result.h5`
and its native raw/deck/log files together, under flavor/sequence directories
where needed. Rate case names use the programmed `mbd`, avoiding ambiguity
between active conversion timing and actual repetition rate. The archived
campaign paths selected by analysis are unchanged. Run `python -m flow.adc.sim`
to list targets without starting a simulation; diagnostics remain pytest-only.

Signal selection lives in `sim.py` as explicit SPICE-name → analysis-alias
maps per view. The same map drives Spectre saves and HDF5 conversion. Both
PEX and generated views save all C0–C15 capacitor stages; B16 is the final
comparator decision and has no C16 capacitor. Original saved traces, including
the next-cycle tail, are embedded in `result.h5` alongside resampled records.

## Shared net definitions

`AdcNets` in `subckt.py` declares the canonical nets once. Its HDL21 `signals`
dictionary supplies `PORTS`, `CLOCKS`, `POWER`, `CONTROLS`, and `INITIAL_STATES`.
The generator and testbench copy these declarations into flat modules. The
comparator, sampler, capacitor array, and driver use the same helpers in
`flow/circuit/ports.py`. Unknown name overrides, duplicate names, and width
mismatches fail during construction.

`AdcTb(params, pex_netlist=path)` reads the selected extracted header in its
actual positional order and requires a complete match to the canonical
interface. Generated ADCs similarly read the checked-in digital header.
Testbench stimuli always use C0-first indexing; the external connection
adapters handle the legacy FRIDA-1 reversal. The explicit distributed PEX
probe dictionary stays in `sim.py`, with the FRIDA-2 net renaming derived from
it; save selection and HDF5 conversion still use the same resulting map.
