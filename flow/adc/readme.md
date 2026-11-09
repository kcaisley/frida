# Status

The ADC is laid out in the [pipeline](../../docs/pipeline.md)'s stage files, `params.py` < `subckt.py` < `sim.py` < `types.py` < `analysis.py` < `plots.py` < `runs.py`, with its behavioral model (`model.py`) and its own layout flow (`layout.py`) beside them, and runs from the CLI's steps: `python -m flow adc --to record` simulates each instance's runs (`sweep.runs`, behavioral; the circuit step, `--to circuit`, adds the circuit simulator's) and records them (`runs.record`), `--to layout` lays it out (`layout.lay_out`), `--to pex` signs it off and extracts it (FRIDA-1's flavors: the Calibre signoff `lay_out` plans, which the drc, lvs and pex steps run, each in its own folder). It has no `targets.py`: its lab studies are its figures of a campaign's captures, `python -m flow.plot adc <run>` (below). It is a migrated block: `flow/test_pipeline.py` holds its stage files to the contract, import-linter's layers contract orders them, and ty checks them in CI. Outside the block its names are reached through the package: `from flow import adc`, then `adc.Params`, `adc.analyze_ramp`, `adc.AnalysisRamp`, `adc.plot_inl`.

| Feature | Status | File | Notes |
|---|---|---|---|
| Parameters | ✓ | [params.py](params.py), [test_params.py](test_params.py) | `Params` (the design: its resolution and its array, sampler and comparator; FRIDA-1's four fabricated converters, `Fabricated`, each one, `valid` in TSMC65 alone) and `TbParams` (one run: its PDK and design, its simulator and, for a fabricated converter in Spectre, its extraction, its stimulus, its supplies, the sequencer's four lines as `h.Vbit` sources playing a recipe's rows, `Recipe`, by default the default recipe's, and the behavioral converter's knobs: its capacitor draw, noise seed, quiet sources, settling scale and reference); the design space's resolutions and FRIDA-1's converter in it (`RESOLUTIONS`, `FRIDA1_BITS`, `FRIDA1_ARRAY`); the behavioral model's constants and the campaign's. |
| Netlist generator | ✓ | [subckt.py](subckt.py) | `netlist(Params)` with its nets `Nets` (FRIDA's 16 stages; any count inside): a fabricated converter (`Params.fabricated`) is its extraction's black box, the cell `adc_12b_17step` with the tape-out's pins (`fixtures/frida1_ports.scs`) bound to the canonical ports, no device inside (no regenerated FRIDA-1); a generated one, at any stage count: FRIDA's hardened 16-stage digital block, or the same RTL synthesized for the array's count (yosys onto the TSMC65 LVT cells, no placement or clock tree; C0 on register 0), and the DAC's two sides, capdac's (`xdac_p`, `xdac_n`: one `capdac.netlist` module, its requests resolved to the active PDK's devices, so the generated ADC needs a PDK), each switched by the digital block's states of its side on its side's top plate, on the DAC's supply. Its polarity is fixed, each stage's main chain non-inverting and its difference chain inverting, so the digital block's inversion controls drive nothing and `dac_diffcaps` has no effect (FRIDA-1's extracted view and the behavioral model keep it); its bottom plates are the sides' own nets (`_generated_aliases`). The extracted views stay 16, their ports and observations bound to the canonical nets in the same file. Its comparator clock's inverter is an analog device of the row cells (`mos`, fingered as the comparator's own). A record's geometry is the netlist's (`flow.sweep.geometry`): the digital block and a fabricated converter's black box are opaque cells, child cells whose contents are not counted. |
| Netlist tests | ✓ | [test_subckt.py](test_subckt.py) | Hierarchy, interfaces, and stage conventions: each side's states from the digital block, the samplers and the comparator on their top plates, no XOR or legacy driver cell, every main chain non-inverting and every difference chain inverting. Those that build the ADC bind TSMC65 and skip without its kit. |
| Testbench and runs | ✓ | [sim.py](sim.py), [test_sim.py](test_sim.py) | `testbench(TbParams)`: the generated ADC (at `dac_diffcaps` 1 alone, the subtraction it wires in: a run of it at 0 is refused), or a fabricated converter's extraction in a Spectre run (the tape-out's, `site.FRIDA1` in the TSMC65 kit, or its layout's signoff, found by `flow.sweep.lookup.laid_out` and checked: LVS correct or the two-layer flavors' accepted disconnect, the content it signed), its black box otherwise; `simulate(tb, run_dir)` runs it, by `tb.simulator`: Spectre (TSMC65 alone; `netlist.raw`, with `input.json` and the probes' map `names.json`, every probed node or the codes alone, `tb.probes`) or the behavioral converter (`capture.h5`, the converter's numbers among its readbacks); `read(raw, tb)` gives the measurement (a Spectre run's transient decoded as conversions). The behavioral converter is private here: its blocks' models from their characterizations, the SAR loop on them, and the stimulus as it sees it (a sequencer line, `h.Vbit`, as its ideal bits). |
| Runs | ✓ | [runs.py](runs.py), [test_runs.py](test_runs.py) | `testbenches(pdk, params, level)`: the behavioral campaign at `Level.SCREEN` (the ramps, the nominal sine and the noise run), `SEARCH` (every rate and input frequency, the DC inputs, the decision paths, the noise over the input, Hsu's study, each noise source alone) and `FULL` (the ENOB ladder, the sine on the DAC's draw, the reference study), and at `CIRCUIT` the circuit simulator's runs (`spice_*`, Spectre): a generated design's rates and ramp; a fabricated converter's rates on its tape-out's extraction, the one-layer radix-17 flavor's ramp and supply noise too, and every flavor's seven continuous timings on its layout's signoff extraction. The runs save the codes alone but `spice_rate_10`, whose nodes the viewer shows (`Probes`). |
| Layout | ✓ | [layout.py](layout.py) | `lay_out(params, pdk, run_dir)`, the layout step's flow for the ADC: a fabricated converter's tape-out layout with its Calibre signoff planned (`signoff.json`; the GDS gains MOM recognition only; LVS correct for the one-layer flavors, the two-layer ones' historical disconnected MOM layer accepted), its inputs the TSMC65 kit's `site.FRIDA1` (the chip's GDS, each flavor's source netlist and its capacitor array's frozen LVS source and pins); any other converter's blocks side by side, unconnected, from the blocks' own layouts (`flow.sweep.lookup.laid_out`): the comparator, the samplers and the DAC's one side (capdac's, its drivers with it) twice, the N side mirrored, each placed on the PDK's manufacturing grid, signed off by DRC alone. No full-ADC layout yet. |
| Layout tests | ✓ | [test_layout.py](test_layout.py) | The FRIDA-1 netlist preparation, each fabricated converter's cells, the blocks side by side (skipped where they are not laid out). |
| Signoff | ✓ | [layout.py](layout.py) | The kit's Calibre DRC (its waivers named), LVS (the two-layer flavors expect the disconnected-MOM mismatch) and xRC on FRIDA-1's flavors, as `lay_out` plans them, run by the drc, lvs and pex steps, each in its own folder; a signoff run (`Extraction.SIGNOFF`) finds its extraction by `flow.sweep.lookup.laid_out`. |
| Behavioral model | ✓ | [model.py](model.py), [test_model.py](test_model.py) | `Model.of(pdk, Params)`: an instance's record (`flow.sweep.lookup.characterized`) as the stand-in a higher level simulates, its ENOB and supply power over the rate (`enob_bits`, `power_w`). The behavioral converter the record measures is `sim.py`'s, private there: it composes the blocks' models (`comp`, `samp`, `capdac` model.py; each block's behavioral physics is its model's, `comp.Model.Behavioral`, `samp.Model.Behavioral` and `capdac.Model.Behavioral` with `capdac.Model.switch`), each from its own characterization (the DAC's looked up, never simulated; as designed, `capdac.Model.design`, where there is none), and runs the SAR loop on them; a run's capture carries the converter's own numbers among its readbacks (`analyze_converter`). The comparator's measured delay over the input decides when a decision is late (its SR latch then holds the last one); each stage's plates move after its driver's delay and settle with its own time constant, as capdac measured them; the DAC's plates are the array as drawn (its design's, its top plate loaded as its measured gain gives, each stage's main plate drawn so that its step at that load is the one measured: the full scale is half the measured steps' sum and the extracted weights are the plates' own steps), and its drivers draw no energy (not characterized; the record's `dac_driver_energy_j`). The reference (VDD_DAC) is ideal unless the run's `reference_*` give its driver's output resistance, its decoupling and its white noise. The run's `tau_scale` scales every stage's settling (0: ideal); its `quiet` (`Quiet`) silences the sampling noise (kT/C and jitter) or the comparator's noise, or makes the comparator (no noise, never late) or the sampler (a perfect track-and-hold, no tracking error) ideal. The SAR logic keeps its FRIDA-2 PEX energies (the digital netlist is not characterized; its clock-to-output is not modelled). A run with `drawn` converts the DAC's SPICE draw instead of a draw of `unit_mismatch`. |
| Campaign | ✓ | [runs.py](runs.py), [params.py](params.py) | `testbenches`' behavioral campaign: the runs the figures need (each a `TbParams` with the behavioral converter's knobs): two ramps on the DAC's SPICE draw (its Monte Carlo's middle condition, 0.5 %·√fF, the draw at the 90th percentile of what no calibration recovers, `capdac.Model.drawn`), the nominal rate's sine on that draw (`drawn_sine`: its ENOB with the design weights, the extracted ones (the DAC's steps as its characterization measured them, nominal) and the calibration learned from the drawn training ramp, `enob_drawn_design_bits`, `_extracted_bits`, `_calibrated_bits`), sines over ten rates, 1 to 10 MS/s, and nine input frequencies at 2/6/10 MS/s, 33 DC inputs, the trajectory point, the noise point, nine DC levels for the noise over the input, and Hsu's redundancy study: every code centre once, noise-free with the comparator's delay kept, at each rate with the array's own settling (the rate is all a fabricated converter lets one vary), against the same inputs at ideal timing at that rate (`analyze_hsu`), and the ENOB ladder (`LADDER`, its captures `LADDER_NAMES`): the 10 MS/s sine from quantization alone (ideal sampler, settling and comparator, no noise), adding the sampler's tracking error, its kT/C noise and jitter, the DAC's settling, the comparator's delay and its noise in turn, the last step `rate_10` itself (six more sines, under 1 % of an instance's time). `_campaign`'s `mismatch_draws` adds noise-free Monte Carlo ramps (capacitor draws at five Pelgrom coefficients, 0.05-0.85 %·sqrt(fF)) to check the predicted mismatch. |
| Figures | ✓ | [plots.py](plots.py), [analysis.py](analysis.py), [runs.py](runs.py), [test_plots.py](test_plots.py) | `runs.record`, from MeasAdc only, whatever made them and whatever level they ran at (a metric of a run not run None): the analyses (`analysis.py`, among them the calibrations, `analyze_calibration1` to `3`) and the viewer's details (`plots.py`, each a `@plot` of results), each one curve so compared instances stay readable (redundancy by stage; the code density, a histogram a bin a code; INL and DNL, design weights and calibrated; the decision paths, whole and their last decisions, and the histogram of the codes they end on; the noise density, input-referred (V/√Hz), its white floor, lines and their split marked, and the noise over the input; ENOB over the rate and over the input frequency; the ENOB ladder, its steps ticked by name (`Detail.x_labels`); two spectra; Hsu's integrated error over the rate at the array's own settling; power and energy, total and the DAC's; the extracted weights' error, the decisions not measured shaded; the predicted mismatch: weight and transition sigma and margin over sigma by stage, worst DNL and INL over the Pelgrom coefficient), the same specs drawing the lab's captures (the figures step over a `--run` of them, below: a figure a capture, a sweep, a calibration or a decoding); after them in `plots.py` the figures only the lab studies draw, each one curve or one map too (the static transfer of DC steps and a ramp's reconstructed one; the operating conditions over sequence and symbol rate as maps, one ADC's or a chip's, `analyze_sequence_map`: the ENOB, how many ADCs are plausible and the code shift, a sequence named by its decision word; one sequence's fixed-input noise, noise-equivalent ENOB and codes over the rate; an interferer's alias search, the best candidate marked, and each rate's strongest line; the held voltage after sampling, 25 µV bins; the top plates' settling at the first, middle and last stage on a log axis; each rail's power over one simulated conversion, its averages marked; the sequencer's programmed outputs as a timing diagram, `analyze_sequencer`), the circuit runs' (`spice_*`: the noise, its ENOB, the codes and the power over the rate, the transfer curve, the noise behind each supply and the sequence map, each figure named `spice_<figure>`, and each timing's decision paths and programmed sequence, `spice_sequence_<comp>_<logic>_<figure>`, a candidate's and an extraction's alike), and the metrics (among them the circuit runs' `spice_noise_rms_lsb`, `spice_noise_enob_bits` and `spice_power_w` at the nominal rate, the fastest rate within a bit of the slowest's ENOB, the fastest error-free rate, each noise source's share, the ladder's quantization-only ENOB and each impairment's ENOB loss where it is added (`enob_quantization_bits`, `enob_loss_<impairment>_bits`, summing to it less `enob_bits`), the calibrated INL by the better calibration on the check ramp, and the predicted 95th percentiles at the assumed matching, 0.10 %·√fF). Every ENOB is the spectral ENOB referred to full scale (`spectral_enob_fs_bits`, `flow/analysis/readme.md`) of the extracted weights' unrounded codes, which cost no rounding, so quantization alone reads the resolution the DAC's drawn steps give: the design resolution where they keep every code (an array whose lightest stages are drawn alike at the PDK's smallest capacitor loses codes, and reads less). A capture as its comparator sees it (`analyze_conversions`: `comp.AnalysisConversions`, its records, decisions, sequence, rates and supplies) is what the comparator's own views of the converter take (`comp.analyze_scope_edges`, `comp.analyze_edge_eye`, `comp.analyze_response` and their specs, `flow/comp`). |
| Mismatch statistics | ✓ | [analysis.py](analysis.py), [types.py](types.py) | Capacitor mismatch from the capacitances alone: every decision path of the nominal array, each code's width linear in every plate's Pelgrom error, so each code's DNL and INL sigma, each stage's weight and transition sigma and margin over sigma, and the 95th percentiles of the worst DNL and INL and of the missing codes. Checked against exact draws (`calc_drawn_linearity`, [test_analysis.py](test_analysis.py)). The decision paths and a drawn array's exact linearity (`calc_paths`, `calc_decision_steps` with the A state: a stage held at 1 moves the other side's capacitor, `calc_drawn_linearity`) are `flow.analysis.calc`'s, shared with the CDAC's Monte Carlo. |
| Reference | ✓ | [runs.py](runs.py), [analysis.py](analysis.py) | What the converter asks of the buffer driving its reference, apart from its own ENOB (an ideal reference's), from its `ref_*` runs (`analyze_reference`): its decoupling, decap cells over 30 % of its footprint (its DAC's two sides, each side's layout with its drivers) at the PDK's density (`DECAP_FF_PER_UM2` in its `pdk_logic`), to one significant figure (`ref_decap_f`), and the largest output resistance into it (`ref_r_max_ohm`) and white noise at it, RMS at each decision (`ref_noise_max_v`), each adding at most half the quantization noise power of the design resolution, so a buffer meeting both adds no more than it (`ref_enob_loss_max_bits` each). The figures are the ENOB lost over each, on a grid of two points a decade; each requirement is interpolated on a log scale between the grid points about the budget (a fixed grid, no bisection: the runs are known before they run), on the nominal rate's sine with its seeds, its sampler and comparator ideal (its DAC alone, settling as it does): an error the size of the quantization noise cannot be told from one capture of a converter whose own error is many times it, and the comparator does not see the reference. The loss jumps across a decade's two points where the driver's settling runs out of time, so the resistance's requirement is coarse there. |
| Design space | ✓ | [runs.py](runs.py) | `python -m flow --block adc --run converters --to record`, the grid `converters` (one space per resolution, its arrays, comparators and samplers values by name: `converters(12b, cdac=12b_binary_x1, comp=200uV_2ns, samp=frida1)`): in TSMC65, the plain product of the comparator grid (`_comparators`: five noise levels by four delays, 20, each a point of the comparator's grids such as `comp.dynamic_bias`'s `ratio=3.5, k=3`), five samplers (`_samplers`, an on-resistance ladder: FRIDA-1's transmission gate the worst, then the bootstrapped NMOS switch at 32, 64, 112 and 160 minimum widths, boosted alike, about 1/2 to 1/10 of the gate's resistance; no dummy switches, as FRIDA-1's) and the 121 ADC arrays (`_arrays`: capdac's design space, `capdac.arrays` and `capdac.frida1`, the difference capacitors named as the legacy extractions name them, the unit capacitors the same with `_unit`): at 10, 12 and 14 bits, binary and the three schemes, MSB split, LSB split and MSB redistribution, with 2, 4 and 6 extra cycles (every one of the binary total weight), at one and two times the resolution's least switched capacitance (`capdac.Params.scale`), each in difference and in unit capacitors (`capdac.WeightImpl`), and FRIDA-1's array (`capdac.frida1`, MSB redistribution with 5, 17 decisions) at 12 bits and two: 20 x 5 x 121 = 12,100 converters, nothing pruned. The grid is TSMC65's alone until capdac is characterized in the other five PDKs; their spaces keep each array with the PDK's StrongARM noise ladder at its longest tail (`_comparators`: 200 to 50 µV where its noise floor reaches them, about FRIDA-1's speed) and the widest bootstrapped switch (`_samplers`): 484 to 605 converters a PDK. Every converter samples on its top plates, compares once before any capacitor switches and again after the last: an N-bit converter has an N-1-step DAC and N + extra decisions. Each converter's DAC is capdac's characterization of the same array, found by its digest: its plates sized for a full scale of the reference, the full scale they give its record's `full_scale_over_reference` (times the scale, the quantization noise over the sampled kT/C), its drivers sized to settle each stage to half an LSB within 1 ns. Beside the grid, FRIDA-1's sizing as a generated design (`frida1`) and its four fabricated converters (`frida1_<layers>layer_radix<radix>`, `Fabricated`), all swept: their behavioral records sit in every table, their circuit runs by `python -m flow adc --to circuit --instance ...`. Each run's capture is written and read back (`capture.h5`, removed once read) and the record (`instance.json`) keeps the figures; the viewer's waves are `spice_rate_10`'s alone. Calibration 1 (CDAC S-curves) is not modelled. |

TODO: validate current assembled DRC/LVS/PEX together. Timing, settling, and noise investigations remain in the [project TODO](../../docs/todo.md).

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

These runs converted the legacy CDAC block's arrays, since retired (the DAC is capdac's now); their
records are history.

Run 20261027_021329 (2026-10-27: the 6,100 converters on 20 workers in 4 h 46 min beside other
jobs) converts each converter's sine on its CDAC's drawn array, the Monte Carlo draw at the 90th
percentile of what no calibration recovers at 0.5 %·√fF and 50 ppm/mm (the legacy block's), and decodes it
three ways: with the design weights, with the extraction's (the nominal array's) and with the
weights the converter learns from its ramps (`enob_drawn_design_bits`, `_extracted_bits`,
`_calibrated_bits`). With the quietest comparator and the widest switch, where the array limits:

- The design weights lose 0.2–1.0 bit at 10 bits, 0.3–1.2 at 12 and 0.3–2.0 at 14 against the
  nominal converter (14 bits: 10.97–12.64 against 12.93–13.05; the MSB split at x2 the worst).
- Calibrated, every array comes within 0.3 bit of its nominal ENOB at every resolution, binary
  included (14 bits: 12.76–13.23, above the nominal where the extraction's own error had cost it).
  A code a fraction of an LSB too wide costs little noise power, so the ENOB hides what the INL and
  missing codes show: the CDAC's gap, what no calibration recovers, is where the schemes differ.
- The extraction's weights recover most of the loss over all comparators and samplers (medians
  within 0.44 bit at 10 bits, 0.22 at 12 and 0.12 at 14).

LF150, run 20261027_074628 (244 converters, 13 min): the arrays whose extraction leaves a gap no
calibration recovers (binary and the LSB split, 6.7–8.2 LSB at 14 bits) stay short of
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
DAC's 2^(bits−1) − 1 units (`capdac.Redundancy`). `MSB_SPLIT` splits the `extra` most
significant binary weights into halves, which gives the free first comparison and the decisions
after it their tolerance; `LSB_SPLIT` splits the `extra` least significant weights of at least 2
(2, 4, ...), a tolerance only at the LSB end, the LSB itself kept whole (a half-unit LSB would add a
code level, not tolerance, and leave the integer codes); `MSB_REDIST` is FRIDA's paired overlay, a
run of paired powers of two taken from the MSB and added from the third stage on, its tolerance
spread over the whole chain. Every one of the design space's arrays keeps a non-negative redundancy
margin at every stage, and an ideal SAR on its weights converts every code to itself
([test_analysis.py](test_analysis.py)).

## Commands

```sh
# the generated grid, behavioral, one table
python -m flow --block adc --run converters --to table
python -m flow --block adc --run converters --from layout --to drc    # each design's blocks side by side (DRC alone)
# a candidate in Spectre, the same spice_* metrics as FRIDA-1's extractions: give it a @single first
python -m flow --block adc --run frida1 --to circuit
# FRIDA-1's fabricated layouts: Calibre DRC, LVS and PEX (their signoff runs then find them), then
# their extractions in Spectre, recorded again with the behavioral runs
for flavor in frida1_1layer_radix17 frida1_1layer_radix20 frida1_2layer_radix17 frida1_2layer_radix20; do
    python -m flow --block adc --run $flavor --to pex
    python -m flow --block adc --run $flavor --to circuit
done
```

The circuit runs are TSMC65's (the ADC's Spectre runs take its kit's includes; in another PDK it has none beyond FULL's, and the circuit step refuses it), and each extraction they simulate is checked before the first of them runs: a fabricated converter's layout must be signed off first. Each run's folder in the instance's (`sim/<run>/`, `circuit/<run>/`) keeps its deck, log, `input.json`, `names.json` and its measurement (`result.h5`); the raw output is removed once read.

Signal selection lives in `sim.py` (`_probes`) as explicit SPICE-name → analysis-alias maps per top. The same map drives Spectre saves and the decode (`names.json`, beside the raw file). Both views save every capacitor stage, C0 first (C0–C15 at FRIDA's 16); the last decision (B16 at 16 stages) has no capacitor of its own. The generated ADC's bottom plates are its DAC's sides' nets (`xdac_p.main_<stage>`, `xdac_p.diff_<stage>`; `subckt._generated_aliases`), a unit-capacitor array's main plates alone. The record keeps `spice_rate_10`'s measurement as `result.h5` (its saved traces, the next-cycle tail with them, beside the resampled records), the viewer's waves.

## Lab studies

Each study is the figures of a campaign's captures (`MeasAdc`, `MeasCdac`, the comparator's `comp.AnalysisDecisions`), drawn by the specs the record draws (`plots.py`, `capdac`'s for the DAC's mismatch): the CLI's figures step over a `--run DIR` of captures, `python -m flow.plot adc <run>`, makes every figure's result its captures give from each board and channel's captures as the analyses chain them (`flow.plot.figures`), into `<run>/figures/`: a figure a capture where its analysis takes one, a figure a sweep for a sequence over the rate (the captures that share their input, common mode and sequence, `MeasAdc.sweep`), a figure each of the three calibrations; a study of several campaigns is a folder of links to them. Every figure is drawn by matplotlib; what is not made from a channel's captures is said, not drawn. A ramp's figures decoded by each calibration its captures give take the optional priors, `flow.plot.figures("adc", [<study>], [...], priors=True)`, from Python. The runs are the lab PC's `build/scan_*` campaigns, a later run of a curve after an earlier one's:

```sh
# the static transfer curve of DC steps, the mean code and the code noise over the input
python -m flow.plot adc build/scan_adc/20260818_135848
# a ramp's code density, INL and DNL with the design weights, each ADC's captures
python -m flow.plot adc build/scan_adc/20260812_011910
# the three calibrations' weights (calibration 1 from the DAC's A-to-B curves, against each ADC's
# comparator), each ADC's capacitor mismatch (capdac's figures of analyze_cap_mismatch); then
# the ramp decoded by each calibration
mkdir build/study_calibration && cd build/study_calibration && ln -s ../scan_adc/20260812_011910 \
    ../scan_cdac/20260804_171234 ../scan_cdac/20260804_193030 ../scan_cdac/20260804_193631 \
    ../scan_comp/20260804_051653 ../scan_comp/20260804_053759 ../scan_comp/20260804_054953 . && cd -
python -m flow.plot adc build/study_calibration
python -c 'from pathlib import Path; from flow import plot; plot.figures("adc", [Path("build/study_calibration")], ["code_density", "inl_calibrated", "dnl_calibrated", "ramp_transfer"], priors=True)'
# the operating conditions over sequence and rate: each ADC's maps and the chip's (_board<g>)
python -m flow.plot adc build/scan_adc/20260926_172920_adc_sequence_static
# the interferer: each sequence's alias search over its rates and each capture's code spectrum, a run at a time
python -m flow.plot adc build/scan_adc/20261008_204141_adc_sequence_static
python -m flow.plot adc build/scan_adc/20261009_105940_adc_sequence_static
python -m flow.plot adc build/scan_adc/20261009_110638_adc_sequence_static
python -m flow.plot adc build/scan_adc/20261009_110933_adc_sequence_static
python -m flow.plot adc build/scan_adc/20261009_153529_adc_sequence_static
# the rate: each DC sweep's noise, noise-equivalent ENOB, codes and supply power; the sines' ENOB and spectra
python -m flow.plot adc build/scan_adc/20260801_194930
python -m flow.plot adc build/scan_adc/20260802_021624
python -m flow.plot adc build/scan_adc/20260802_081407
python -m flow.plot adc build/scan_adc/20260819_113714
python -m flow.plot adc build/scan_adc/20260730_215145_complete
```

A study that picked one sequence of a campaign (the rate's historical fixed-input recipe, the interferer's 4-of-8 recipe) now draws every sequence's figure, each named by its sweep: the one picked is among them. FRIDA-1's extractions in Spectre (the old sequence study's PEX cases) are its fabricated instances' circuit runs (above), their figures the record's: `python -m flow.plot adc <run> --instance frida1_1layer_radix17`.

## Shared net definitions

`Nets` in `subckt.py` declares the canonical nets once (`_nets(stages)` at another count). Its HDL21 `signals` dictionary supplies `PORTS`, `CLOCKS`, `POWER`, `CONTROLS`, and `INITIAL_STATES`. The generator and testbench copy these declarations into flat modules. The comparator, the sampler and the DAC's side (capdac's) use the same helpers in `flow/circuit/ports.py`. Unknown name overrides, duplicate names, and width mismatches fail during construction.

`testbench(tb)` reads the run's extraction's header (`sim._extraction`) in its actual positional order and requires a complete match to the canonical interface. Generated ADCs similarly read the checked-in digital header. Testbench stimuli always use C0-first indexing; the external connection adapters handle the legacy FRIDA-1 reversal. The explicit distributed PEX probe dictionary (`subckt._frida1_terminals`) stays beside the view; save selection and HDF5 conversion use the same resulting map.
