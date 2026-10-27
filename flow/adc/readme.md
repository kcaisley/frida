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
| Behavioral model | ✓ | [model.py](model.py) | `AdcModel.of(pdk, AdcParams)` composes the blocks' models (`comp`, `samp`, `caparray`, `capdriver` model.py), each from its own characterization or extraction; `tb()` builds the testbench, `capture()` writes a MeasAdc. The comparator's measured delay over the input decides when a decision is late (its SR latch then holds the last one); each stage's plates move after its driver's intrinsic delay and settle with its own RC. The reference (VDD_DAC) is ideal unless `capture(reference=Reference(...))` gives its driver's output resistance, its decoupling and its white noise: each switch then draws its charge from the decoupling, which the driver restores with their RC, and the dip left and the noise reach each top plate through its plates at the reference, so the noise cancels at mid-scale and grows toward the ends. `tau_scale` scales every stage's settling (0: ideal); `quiet` silences the sampling noise (kT/C and jitter) or the comparator's noise, or makes the comparator (no noise, never late) or the sampler (a perfect track-and-hold, no tracking error) ideal. The SAR logic keeps its FRIDA-2 PEX energies (the digital netlist is not characterized; its clock-to-output is not modelled). A capture with `drawn` converts the CDAC's SPICE draw (`AdcModel.drawn`, looked up with its settling; nominal plates where none is characterized) instead of a draw of `unit_mismatch`. |
| Campaign | ✓ | [campaign.py](campaign.py) | The captures the figures need as `AdcTbParams`, the same for a SPICE run: two ramps on the CDAC's SPICE draw (`AdcModel.drawn`: its Monte Carlo's middle condition, 0.5 %·√fF and 50 ppm/mm, the draw at the 90th percentile of what no calibration recovers, `flow.cdac.model.Model.drawn`), the nominal rate's sine on that draw (`drawn_sine`: its ENOB with the design weights, the nominal extraction's and the calibration learned from the drawn training ramp, `enob_drawn_design_bits`, `_extracted_bits`, `_calibrated_bits`), sines over ten rates, 1 to 10 MS/s, and nine input frequencies at 2/6/10 MS/s, 33 DC inputs, the trajectory point, the noise point, nine DC levels for the noise over the input, and Hsu's redundancy study: every code centre once, noise-free with the comparator's delay kept, at each rate with the array's own settling (the rate is all a fabricated converter lets one vary), against the same inputs at ideal timing at that rate (`hsu_errors`), and the ENOB ladder (`LADDER`): the 10 MS/s sine from quantization alone (ideal sampler, settling and comparator, no noise), adding the sampler's tracking error, its kT/C noise and jitter, the DAC's settling, the comparator's delay and its noise in turn, the last step `rate_10` itself (six more sines, under 1 % of an instance's time). `mismatch_draws` adds noise-free Monte Carlo ramps (capacitor draws at five Pelgrom coefficients, 0.05-0.85 %·sqrt(fF)) to check the predicted mismatch. |
| Figures | ✓ | [figures.py](figures.py) | MeasAdc only, whatever made them: the viewer's details, each one curve so compared instances stay readable (redundancy by stage; the code density, a histogram a bin a code; INL and DNL, design weights and calibrated; the decision paths, whole and their last decisions, and the histogram of the codes they end on; noise density and noise over the input; ENOB over the rate and over the input frequency; the ENOB ladder, its steps ticked by name (`Detail.x_labels`); two spectra; Hsu's integrated error over the rate at the array's own settling; power and energy, total and the DAC's; the extracted weights' error; the predicted mismatch: weight and transition sigma and margin over sigma by stage, worst DNL and INL over the Pelgrom coefficient), and the metrics (among them the fastest rate within a bit of the slowest's ENOB, the fastest error-free rate, each noise source's share, the ladder's quantization-only ENOB and each impairment's ENOB loss where it is added (`enob_quantization_bits`, `enob_loss_<impairment>_bits`, summing to it less `enob_bits`), the calibrated INL by the better calibration on the check ramp, and the predicted 95th percentiles at Harpe's matching). Every ENOB is the spectral ENOB referred to full scale (`spectral_enob_fs_bits`, `flow/analysis/readme.md`) of the extracted weights' unrounded codes, so quantization alone reads the design resolution. |
| Mismatch statistics | ✓ | [statistics.py](statistics.py) | Capacitor mismatch from the capacitances alone: every decision path of the nominal array, each code's width linear in every plate's Pelgrom error, so each code's DNL and INL sigma, each stage's weight and transition sigma and margin over sigma, and the 95th percentiles of the worst DNL and INL and of the missing codes. Checked against exact draws (`calc_drawn_linearity`, [test_statistics.py](test_statistics.py)). The decision paths and a drawn array's exact linearity (`calc_paths`, `calc_decision_steps` with the A state: a stage held at 1 moves the other side's capacitor, `calc_drawn_linearity`) are `flow.analysis.calc`'s, shared with the CDAC's Monte Carlo. |
| Reference | ✓ | [reference.py](reference.py) | What the converter asks of the buffer driving its reference, apart from its own ENOB (an ideal reference's): its decoupling, decap cells over 30 % of its footprint (its two arrays') at the PDK's density (`DECAP_FF_PER_UM2` in its `pdk_logic`), to one significant figure (`ref_decap_f`), and the largest output resistance into it (`ref_r_max_ohm`) and white noise at it, RMS at each decision (`ref_noise_max_v`), each adding at most half the quantization noise power of the design resolution, so a buffer meeting both adds no more than it (`ref_enob_loss_max_bits` each). The figures are the ENOB lost over each, on a grid of two points a decade; the requirement is bisected between the last within the budget and the first over it, on the nominal rate's sine with its seeds, its sampler and comparator ideal (its DAC alone, settling as it does): an error the size of the quantization noise cannot be told from one capture of a converter whose own error is many times it, and the comparator does not see the reference. |
| Design space | ✓ | [sweep.py](sweep.py) | `python -m flow adc.sweep`, the grid `converters` (one space per resolution, its arrays, comparators and samplers values by name: `converters(12b, cdac=12b_binary_x1, comp=200uV_2ns, samp=frida1)`): in TSMC65, the plain product of the comparator grid (`COMP_GRID`: five noise levels by four delays, 20, each a point of the comparator's grids such as `comp.dynamic_bias`'s `ratio=3.5, k=3`), five samplers (`SAMPLER_STEPS`, an on-resistance ladder: FRIDA-1's transmission gate the worst, then the bootstrapped NMOS switch at 32, 64, 112 and 160 minimum widths, boosted alike, about 1/2 to 1/10 of the gate's resistance; no dummy switches, as FRIDA-1's) and the 61 ADC arrays (`flow.caparray.layout.ADC_ARRAYS`): at 10, 12 and 14 bits, binary and the three schemes, MSB split, LSB split and MSB redistribution, with 2, 4 and 6 extra cycles (every one of the binary total weight), at one and two times the resolution's least switched capacitance (`cap_scale`), and FRIDA-1's array (`RADIX17`, MSB redistribution with 5, 17 decisions) at 12 bits and two: 20 x 5 x 61 = 6,100 converters, nothing pruned. In the other five PDKs, each array with the PDK's StrongARM noise ladder at its longest tail (`comparators`: 200 to 50 µV where its noise floor reaches them, about FRIDA-1's speed) and the widest bootstrapped switch (`samplers`): 244 to 305 converters a PDK. Every converter samples on its top plates, compares once before any capacitor switches and again after the last: an N-bit converter has an N-1-step DAC and n_dac + n_extra + 1 decisions. Its array is sized through its 3-D extraction (`flow.caparray.sizing`): its full scale at least 80 % of the reference and its sampled kT/C at most its quantization noise there, each resolution's least switched capacitance the larger of the two for its most demanding array, and each array at the split between length-scaled binary and unary rows that keeps both with its outline nearest twice as tall as wide (one side's array; the two side by side make about a square). Its drivers are derived from its plates (`flow.capdriver.model.driver_strengths`). Each instance keeps its captures in memory and writes only its record (`instance.json`): the viewer shows its figures, no ADC waveform. Calibration 1 (CDAC S-curves) is not modelled. |

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
the redundancy schemes to find where each regime holds. Where the DAC's settling limits the rate,
redundancy can raise it; where the comparator's delay does, it cannot.

## Mismatch and calibration

Run 20261027_021329 (2026-10-27: the 6,100 converters on 20 workers in 4 h 46 min beside other
jobs) converts each converter's sine on its CDAC's drawn array, the Monte Carlo draw at the 90th
percentile of what no calibration recovers at 0.5 %·√fF and 50 ppm/mm (`flow/cdac`), and decodes it
three ways: with the design weights, with the extraction's (the nominal array's) and with the
weights the converter learns from its ramps (`enob_drawn_design_bits`, `_extracted_bits`,
`_calibrated_bits`). With the quietest comparator and the widest switch, where the array limits:

- The design weights lose 0.2–1.0 bit at 10 bits, 0.3–1.2 at 12 and 0.3–2.0 at 14 against the
  nominal converter (14 bits: 10.97–12.64 against 12.93–13.05; the MSB split at x2 the worst).
- Calibrated, every array comes within 0.3 bit of its nominal ENOB at every resolution, binary
  included (14 bits: 12.76–13.23, above the nominal where the extraction's own error had cost it).
  A code a fraction of an LSB too wide costs little noise power, so the ENOB hides what the INL and
  missing codes show: the CDAC's gap (`flow/cdac`) is where the schemes differ.
- The extraction's weights recover most of the loss over all comparators and samplers (medians
  within 0.44 bit at 10 bits, 0.22 at 12 and 0.12 at 14).

LF150, run 20261027_074628 (244 converters, 13 min): the arrays whose extraction leaves a gap no
calibration recovers (`flow/cdac`: binary and the LSB split, 6.7–8.2 LSB at 14 bits) stay short of
their nominal ENOB once calibrated (14 bits binary 11.73 against 12.71, 12 bits 10.53–10.69 against
11.56–11.68), where the extraction's weights decode the same draw better (14 bits binary 12.32): the
learned weights fail where a code is several LSB wide. MSB redistribution and the MSB split calibrate
to within 0.2 bit of their nominal ENOB, or above it.

IHP130, run 20261027_113126 (305 converters, 18 min): with the quietest comparator the design weights
lose 0.1–0.9 bit at 10 bits and 0.4–2.0 at 12, and calibration brings every array to within 0.5 bit
of its nominal ENOB (most within 0.05). At 14 bits the widest bootstrapped switch limits: into the
6.5 pF array it costs 2.2 bits (the comparator 0.06–0.46), so the nominal ENOB is 10.7–11.7 and the
array hides (the design weights lose 0.1–0.9 bit there).

TPSC65, run 20261027_113851 (305 converters, 17 min): the design weights lose up to 0.65 bit at 10
bits and 1.5 at 12, and calibration brings every array within 0.7 bit of its nominal ENOB (most
within 0.3). At 14 bits the switch costs 3.3 bits into the 5.7 pF array, so the nominal ENOB is
9.6–10.6 whatever the array or comparator: IHP130 and TPSC65 need a wider sampler at 14 bits.

Tower180, run 20261027_131105 (305 converters, 12 min): the design weights lose the most of any PDK,
0.1–1.0 bit at 10 bits, 0.7–3.3 at 12 and 0.8–2.9 at 14 (its arrays' INL with them reaches 16 LSB),
and calibration brings every array within 0.3 bit of its nominal ENOB (12.5–12.9 at 14 bits, the
switch costing 0.3–0.5 bit there).

TSMC28, run 20261027_133457 (244 converters, 9 min): the design weights lose 0.3–1.1 bit at 10 bits,
0.4–1.5 at 12 and up to 0.4 at 14, and calibration brings every array within 0.6 bit of its nominal
ENOB (most within 0.2; its 12-bit MSB redistribution 2 at x1, whose gap is near one LSB, among them);
at 14 bits the switch costs 1.1 bits into its 9.3 pF arrays (nominal ENOB 11.7–12.3).

## Redundancy schemes

An array's extra conversion cycles never add capacitance: each scheme redistributes the binary
DAC's 2^n_dac − 1 units (`flow.caparray.subckt.RedunStrat`). `MSB_SPLIT` splits the n_extra most
significant binary weights into halves, which gives the free first comparison and the decisions
after it their tolerance; `LSB_SPLIT` splits the n_extra least significant weights of at least 2
(2, 4, ...), a tolerance only at the LSB end, the LSB itself kept whole (a half-unit LSB would add a
code level, not tolerance, and leave the integer codes); `MSB_REDIST` is FRIDA's paired overlay, a
run of paired powers of two taken from the MSB and added from the third stage on, its tolerance
spread over the whole chain. Every one of the design space's arrays keeps a non-negative redundancy
margin at every stage, and an ideal SAR on its weights converts every code to itself
([test_behavioral.py](test_behavioral.py)).

## Simulation acquisition families

The seven entry points are `hdl21_sample_rate`, `frida1_sample_rate`, `hdl21_transfer_curve`, `frida1_transfer_curve`, `frida1_sequence`, `frida2_sequence`, and `frida1_supply_noise`. Each sequence target lists seven reviewed recipes directly: 28 FRIDA-1 and 21 FRIDA-2 cases. Separate FRIDA generations keep their explicit extraction inputs and four-by-six / three-by-eight worker budgets. Temporary seven-eighths-only campaign entry points are removed; the complete sequence targets include those cases.

New runs use `build/sim/adc/<timestamp>_<target>/`. Each case keeps `result.h5` and its native raw/deck/log files together, under flavor/sequence directories where needed. Rate case names use the programmed `mbd`, avoiding ambiguity between active conversion timing and actual repetition rate. The archived campaign paths selected by analysis are unchanged. Run `python -m flow` to list every target (the ADC's as `adc.<target>`) without starting a simulation; diagnostics remain pytest-only.

Signal selection lives in `sim.py` as explicit SPICE-name → analysis-alias maps per view. The same map drives Spectre saves and HDF5 conversion. Both views save every capacitor stage, C0 first (C0–C15 at FRIDA's 16); the last decision (B16 at 16 stages) has no capacitor of its own. Original saved traces, including the next-cycle tail, are embedded in `result.h5` alongside resampled records.

## Shared net definitions

`AdcNets` in `subckt.py` declares the canonical nets once. Its HDL21 `signals` dictionary supplies `PORTS`, `CLOCKS`, `POWER`, `CONTROLS`, and `INITIAL_STATES`. The generator and testbench copy these declarations into flat modules. The comparator, sampler, capacitor array, and driver use the same helpers in `flow/circuit/ports.py`. Unknown name overrides, duplicate names, and width mismatches fail during construction.

`AdcTb(params, pex_netlist=path)` reads the selected extracted header in its actual positional order and requires a complete match to the canonical interface. Generated ADCs similarly read the checked-in digital header. Testbench stimuli always use C0-first indexing; the external connection adapters handle the legacy FRIDA-1 reversal. The explicit distributed PEX probe dictionary stays in `sim.py`, with the FRIDA-2 net renaming derived from it; save selection and HDF5 conversion still use the same resulting map.
