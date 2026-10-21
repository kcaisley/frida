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
| Behavioral model | ✓ | [model.py](model.py) | `AdcModel.of(pdk, AdcParams)` composes the blocks' models (`comp`, `samp`, `caparray`, `capdriver` model.py), each from its own characterization or extraction; `tb()` builds the testbench, `capture()` writes a MeasAdc. The comparator's measured delay over the input decides when a decision is late (its SR latch then holds the last one); each stage's plates move after its driver's intrinsic delay and settle with its own RC. The SAR logic keeps its FRIDA-2 PEX energies (the digital netlist is not characterized; its clock-to-output is not modelled). |
| Campaign | ✓ | [campaign.py](campaign.py) | The captures the figures need as `AdcTbParams`, the same for a SPICE run: two ramps (one Harpe capacitor draw), sines over eleven rates and nine input frequencies at 2/6/10 MS/s, 33 DC inputs, the trajectory point, the noise point, and the mismatch study's noise-free ramps (25 capacitor draws at each of five Pelgrom coefficients, 0.05-0.85 %·sqrt(fF)). |
| Figures | ✓ | [figures.py](figures.py) | MeasAdc only, whatever made them: the redundancy by stage (design and extracted weights), code density, INL/DNL, decision paths, ENOB and power over the rate, energy over the input, noise by source, ENOB over the input frequency, two spectra, calibration weights and calibrated INL/DNL, worst INL/DNL over capacitor mismatch (SVG), and the metrics (among them the fastest rate within half a bit of the slowest's ENOB, and the Pelgrom coefficient where 5 % of draws pass 0.5 LSB DNL). |
| Design space | ✓ | [sweep.py](sweep.py) | `python -m flow adc.sweep`: a StrongARM near FRIDA-1's and the lowest-noise double tail, FRIDA-1's transmission-gate sampler, the same 4x wider and a bootstrapped one, at 10, 11 and 12 bits, each with 0/2/4/6 redundant decisions (FRIDA's 12-bit array with 5 as well), so 10 to 18 decisions, on the three-metal arrays, in TSMC65 (78 instances, about 10 min each). Calibration 1 (CDAC S-curves) is not modelled. |

TODO: finish ADC-level driver/array composition; validate current assembled DRC/LVS/PEX together. Timing, settling, and noise investigations remain in the [project TODO](../../docs/todo.md).

## Simulation acquisition families

The seven entry points are `hdl21_sample_rate`, `frida1_sample_rate`, `hdl21_transfer_curve`, `frida1_transfer_curve`, `frida1_sequence`, `frida2_sequence`, and `frida1_supply_noise`. Each sequence target lists seven reviewed recipes directly: 28 FRIDA-1 and 21 FRIDA-2 cases. Separate FRIDA generations keep their explicit extraction inputs and four-by-six / three-by-eight worker budgets. Temporary seven-eighths-only campaign entry points are removed; the complete sequence targets include those cases.

New runs use `build/sim/adc/<timestamp>_<target>/`. Each case keeps `result.h5` and its native raw/deck/log files together, under flavor/sequence directories where needed. Rate case names use the programmed `mbd`, avoiding ambiguity between active conversion timing and actual repetition rate. The archived campaign paths selected by analysis are unchanged. Run `python -m flow` to list every target (the ADC's as `adc.<target>`) without starting a simulation; diagnostics remain pytest-only.

Signal selection lives in `sim.py` as explicit SPICE-name → analysis-alias maps per view. The same map drives Spectre saves and HDF5 conversion. Both PEX and generated views save all C0–C15 capacitor stages; B16 is the final comparator decision and has no C16 capacitor. Original saved traces, including the next-cycle tail, are embedded in `result.h5` alongside resampled records.

## Shared net definitions

`AdcNets` in `subckt.py` declares the canonical nets once. Its HDL21 `signals` dictionary supplies `PORTS`, `CLOCKS`, `POWER`, `CONTROLS`, and `INITIAL_STATES`. The generator and testbench copy these declarations into flat modules. The comparator, sampler, capacitor array, and driver use the same helpers in `flow/circuit/ports.py`. Unknown name overrides, duplicate names, and width mismatches fail during construction.

`AdcTb(params, pex_netlist=path)` reads the selected extracted header in its actual positional order and requires a complete match to the canonical interface. Generated ADCs similarly read the checked-in digital header. Testbench stimuli always use C0-first indexing; the external connection adapters handle the legacy FRIDA-1 reversal. The explicit distributed PEX probe dictionary stays in `sim.py`, with the FRIDA-2 net renaming derived from it; save selection and HDF5 conversion still use the same resulting map.
