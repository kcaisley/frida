# Status

| Feature | Status | File | Notes |
|---|---|---|---|
| Netlist generator | ✓ | [subckt.py](subckt.py), [digital.py](digital.py) | Any stage count: FRIDA's hardened 16-stage digital block, or the same RTL synthesized for the array's count (yosys onto the TSMC65 LVT cells, no placement or clock tree; C0 on register 0); the extracted views stay 16. Driver/array separation remains partial. |
| Netlist tests | ✓ | [test_subckt.py](test_subckt.py) | Hierarchy, interfaces, and stage conventions. |
| Testbench generator | ✓ | [sim.py](sim.py) | Generated ADC and extracted FRIDA-1/2 views. |
| Simulation runners | ✓ | [sim.py](sim.py) | Named timing and noise campaigns; require explicit PDK/extraction inputs. |
| Layout generator | ✓ | [laygen.py](laygen.py) | Assembles replacement blocks in a fixed template, not a new full-ADC layout. |
| Layout tests | ✓ | [test_layout.py](test_layout.py), [test_signoff.py](test_signoff.py) | Assembly compatibility and runner contracts. |
| Layout runner | ✓ | [layout.py](layout.py) | Historical FRIDA-1 and replacement-array FRIDA-2 targets. |
| DRC runner | ✓ | [layout.py](layout.py) | Shared/PDK dispatch with explicit exclusions; not unqualified signoff. |
| LVS runner | ✓ | [layout.py](layout.py) | Some historical variants explicitly expect a disconnected-MOM mismatch. |
| PEX runner | ✓ | [layout.py](layout.py) | Historical xRC and FRIDA-2 xACT; review results for the exact source revision. |
| Behavioral model | ✓ | [model.py](model.py) | `AdcModel.of(pdk, AdcParams)` composes the blocks' models (`comp`, `samp`, `caparray`, `capdriver` model.py), each from its own characterization or extraction (or an ideal array: `CapArrayConfig.parasitic_cap`); `tb()` builds the testbench, `capture()` writes a MeasAdc. The comparator's measured delay over the input decides when a decision is late (its SR latch then holds the last one); each stage's plates move after its driver's intrinsic delay and settle with its own RC; VDD_DAC noise (`RAIL_NOISE_V`, 0.5 mV rms a decision, assumed) reaches each top plate through its plates at the rail, so it cancels at mid-scale and grows toward the ends. `tau_scale` scales every stage's settling (0: ideal). The SAR logic keeps its FRIDA-2 PEX energies (the digital netlist is not characterized; its clock-to-output is not modelled). |
| Campaign | ✓ | [campaign.py](campaign.py) | The captures the figures need as `AdcTbParams`, the same for a SPICE run: two ramps (one Harpe capacitor draw), sines over ten rates, 1 to 10 MS/s, and nine input frequencies at 2/6/10 MS/s, 33 DC inputs, the trajectory point, the noise point, nine DC levels for the noise over the input, and Hsu's redundancy study: every code centre once, noise-free with the comparator's delay kept, at each rate with the array's own settling (the rate is all a fabricated converter lets one vary), against the same inputs at ideal timing at that rate (`hsu_errors`). `mismatch_draws` adds noise-free Monte Carlo ramps (capacitor draws at five Pelgrom coefficients, 0.05-0.85 %·sqrt(fF)) to check the predicted mismatch. |
| Figures | ✓ | [figures.py](figures.py) | MeasAdc only, whatever made them: the viewer's details, each one curve so compared instances stay readable (redundancy by stage; the code density, a histogram a bin a code; INL and DNL, design weights and calibrated; the decision paths, whole and their last decisions, and the histogram of the codes they end on; noise density and noise over the input; ENOB over the rate and over the input frequency; two spectra; Hsu's integrated error over the rate at the array's own settling; power and energy, total and the DAC's; the extracted weights' error; the predicted mismatch: weight and transition sigma and margin over sigma by stage, worst DNL and INL over the Pelgrom coefficient), and the metrics (among them the fastest rate within a bit of the slowest's ENOB, the fastest error-free rate, each noise source's share, the calibrated INL by the better calibration on the check ramp, and the predicted 95th percentiles at Harpe's matching). |
| Mismatch statistics | ✓ | [statistics.py](statistics.py) | Capacitor mismatch from the capacitances alone: every decision path of the nominal array, each code's width linear in every plate's Pelgrom error, so each code's DNL and INL sigma, each stage's weight and transition sigma and margin over sigma, and the 95th percentiles of the worst DNL and INL and of the missing codes. Checked against exact draws (`calc_drawn_linearity`, [test_statistics.py](test_statistics.py)). |
| Design space | ✓ | [sweep.py](sweep.py) | `python -m flow adc.sweep`: two studies in TSMC65, each converter given by its parameters (963 instances). Redundancy: five comparators (216 uV to 1.2 mV of noise, 0.13 to 4.6 ns of delay), at 10 to 14 bits, each with 0 to 6 redundant decisions spent five ways (FRIDA's sub-radix-2 overlay, or repeated binary weights at the start, along the chain, at the end or at both ends; FRIDA's array is the 12-bit overlay with 5), so 10 to 20 decisions, on the three-metal arrays; the samplers (FRIDA-1's transmission gate, the same 4x wider, a bootstrapped one) compared on the FRIDA-like comparators with binary or overlay arrays, the rest with the 4x gate (915 instances). Specification: a 14-bit converter (1.4 pF switched in 7 pF a side, FRIDA-1's transmission gate at 32 minimum widths and minimum length, a comparator near 300 uV) with sixteen proposed capacitor arrays (binary, and binary with added decisions at the LSB end, at the MSB or both, double or triple conversion at the LSB or the LSB+1, mildly non-binary steps), each given as its search steps (nominal weight plus non-binary addition, every step a capacitor) scaled to the same switched capacitance in an ideal array (`CapArrayConfig.parasitic_cap`: nothing extracted), with three comparators near 300 uV from slow (2.5 ns) to fast (0.14 ns) (48 instances). The converter samples on its top plates and adds one free first decision alike for every array, so its code has a bit more than the specification's: the arrays compare by ENOB and SNDR over the same full scale in volts. Calibration 1 (CDAC S-curves) is not modelled. |

TODO: finish ADC-level driver/array composition; validate current assembled DRC/LVS/PEX together. Timing, settling, and noise investigations remain in the [project TODO](../../docs/todo.md).

## Redundancy: when it helps

Read A. H. T. Chang, *Low-Power High-Performance SAR ADC with Redundancy and Digital Background
Calibration* (PhD thesis, MIT, 2013), pp. 73-84: redundancy shortens a
conversion where DAC settling dominates (and more as the settling slows), not where the latch delay
does, since it cannot undo a metastable decision; it may still buy tolerance to decision errors and
the redundant information digital calibration needs. The model carries his non-idealities: each
capacitor's step settles first order from its own start (his eq. 3.19, the conservative form: the
switch through the plate in series with the rest of the load, after the LOGIC edge and the driver's
delay), the steps superpose (3.18), the comparator's delay grows as the log of a falling input (3.20,
here measured, extended by the regeneration time constant) and a late decision is wrong (held, where
he forces it to 0), and the logic delay is the asynchronous loop's windows. The campaign's Hsu study
gives each instance's integrated error over the rate at its own settling; the design space spans the comparators and
the redundancy schemes to find where each regime holds. Its specification study asks the same of one
14-bit specification and the arrays proposed for it: does redundancy pay there, and in which arrays?
Where the DAC's settling limits the rate, redundancy can raise it; where the comparator's delay
does, it cannot.

## Simulation acquisition families

The seven entry points are `hdl21_sample_rate`, `frida1_sample_rate`, `hdl21_transfer_curve`, `frida1_transfer_curve`, `frida1_sequence`, `frida2_sequence`, and `frida1_supply_noise`. Each sequence target lists seven reviewed recipes directly: 28 FRIDA-1 and 21 FRIDA-2 cases. Separate FRIDA generations keep their explicit extraction inputs and four-by-six / three-by-eight worker budgets. Temporary seven-eighths-only campaign entry points are removed; the complete sequence targets include those cases.

New runs use `build/sim/adc/<timestamp>_<target>/`. Each case keeps `result.h5` and its native raw/deck/log files together, under flavor/sequence directories where needed. Rate case names use the programmed `mbd`, avoiding ambiguity between active conversion timing and actual repetition rate. The archived campaign paths selected by analysis are unchanged. Run `python -m flow` to list every target (the ADC's as `adc.<target>`) without starting a simulation; diagnostics remain pytest-only.

Signal selection lives in `sim.py` as explicit SPICE-name → analysis-alias maps per view. The same map drives Spectre saves and HDF5 conversion. Both views save every capacitor stage, C0 first (C0–C15 at FRIDA's 16); the last decision (B16 at 16 stages) has no capacitor of its own. Original saved traces, including the next-cycle tail, are embedded in `result.h5` alongside resampled records.

## Shared net definitions

`AdcNets` in `subckt.py` declares the canonical nets once. Its HDL21 `signals` dictionary supplies `PORTS`, `CLOCKS`, `POWER`, `CONTROLS`, and `INITIAL_STATES`. The generator and testbench copy these declarations into flat modules. The comparator, sampler, capacitor array, and driver use the same helpers in `flow/circuit/ports.py`. Unknown name overrides, duplicate names, and width mismatches fail during construction.

`AdcTb(params, pex_netlist=path)` reads the selected extracted header in its actual positional order and requires a complete match to the canonical interface. Generated ADCs similarly read the checked-in digital header. Testbench stimuli always use C0-first indexing; the external connection adapters handle the legacy FRIDA-1 reversal. The explicit distributed PEX probe dictionary stays in `sim.py`, with the FRIDA-2 net renaming derived from it; save selection and HDF5 conversion still use the same resulting map.
