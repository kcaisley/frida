# To Do

## `samp`

- [ ] Study the effect of sampling time in measurements and simulation. Is 20 ps needed?
- [ ] Finish analysis seperating the sampling-switch noise from the comparator input-referred offset.
- [x] Compare held differential sampling levels across all seven extracted ADC designs.
  - Historical pre-COMP window-average result: held SD decreases from 116.9 µV for FRIDA-1 one-layer radix-17 to 81.5 µV
    for FRIDA-2 three-layer. This separates held-level spread from DC offset, but does not isolate every physical noise
    source. See [sampling-noise results](cdac_pex.md#held-sampling-noise-comparison-2026-09-06).
- [ ] Simulate switch resistance vs devices size and input voltage, convert this to enob/mv error degradation vs
      bandwidth.
- [ ] Simulate samp switch noise vs varying (parameter to be specified).

## `comp`

- [ ] Better understand the relationship between the comparator and logic clocks.
  - [ ] Study the noise and metastability effects of the current design. At the planned 10 MS/s operating rate, the
    comparator has only 2–4 ns to settle.
  - [ ] Investigate the optimal timing relationship. The comparator clearly needs more time; determine how far its
    evaluation time can be pushed without reducing the following logic and CDAC-settling margins too far.
  - [ ] Measure this using the physical ADC and simulate both the full ADC and the comparator by itself.
    - [x] Run and collect the full-ADC comparison of original, extended-comparator, and continuous-100-ns timing for
          seven designs: 21 cases, each with 100 conversions.
    - [x] Repair the saved AdcTbParams type metadata and analyse the collected timing sweeps.
      - Both simulation workers succeeded; the original automatic analysis failed on the saved `__mp_main__:AdcTbParams`
        type. Campaigns: `build/remote/frida-20260906_124441_733878/` and `build/remote/frida-20260906_124442_994752/`.
  - [ ] And evaluate the other side of this problem. (Original note was incomplete.)
- [ ] Determine whether the current comparator is reaching metastability or suffering from other limitations.
  - [x] Audit dynamic comparator nodes and buffered output retention in the three FRIDA-2 baseline runs.
    - [ ] Possible incomplete transfer into the output latch was identified; a metastability probability was not
          established. Record: `build/analysis/adc/20260906_112220/comparator_reset_audit.md`.
- [ ] Investigate a new comparator with lower kickback, shorter metastability time, and better input-referred offset.
- [ ] Continue using OpenROAD to generate a comparator layout from discrete transistors represented by LEF files.

## `caparray`

- [ ] Rename the `cdac` block to caparray, and break out the driver sizing strategy into it's own `capdriver` generator.
- [ ] Verify/investigate the cdac's 800 pF of capacitance per branch
  - [ ] Original unit and capacitance definition need confirmation: documented full-ADC node loads are approximately
    0.50–1.21 pF per side; total node loading differs from effective switched capacitance.
  - [x] Check the capacitance with the new layer connected.
    - [ ] Corrected one-, two-, and three-layer extractions are tabulated in the
      [reviewed interface results](cdac_pex.md#reviewed-interface-revision-2026-09-05).
  - [x] Determine whether half of the ADCs really had only a single capacitance layer.
    - [ ] Confirmed at layout/LVS/PEX level: the historical nominal two-layer variants have disconnected upper plates.
      See the [historical connectivity checks](cdac_pex.md#five-design-radix-17-comparison-2026-09-03).
- [ ] Understand why the input range is attenuated so much and quantify the parasitic capacitance.
  - [x] Quantify main, differential, effective switched, and shunt capacitances for historical and corrected arrays.
  - [ ] Measure or simulate calibrated transfer gain and usable input range to complete the attenuation comparison.
    - [ ] Larger first DAC corrections support reduced attenuation; they do not establish the full-scale transfer range.
- [x] Generate reviewed one-, two-, and three-layer CDAC layouts, verify connectivity with negative LVS tests, and
      assemble/extract the three corrected full-ADC variants.
  - [ ] All three full-ADC variants pass the configured DRC checks and raw LVS, with xACT PEX results.
    See the [full-ADC verification record](cdac_pex.md#c0-first-full-adc-restart-2026-09-05).
- [x] Implement and use conversion-path and CDAC-settling analysis following comparator, logic, driver, and top-plate
      signals.
- [ ] Study how the CDAC initialization values affect ADC operation. The current value is `16'h5555`, but the reason for
  using it is not yet well understood.
  - [ ] Map common mode versus differential input versus initialization state. Assuming an externally applied 600 mV
    common mode, determine how best to keep the comparator near its 700 mV optimum across all input conditions.

## `capdriver`

- [ ] Create this new netlist generator, which in frida-1 was actually just an assembled layout and netlist
- [ ] In the top level frida-1 and frida-2 netlist generator, this can just be a fixed gate netlist
- [ ] Ensure fixed netlist is pulled from build, since it's composed of stdcells
- [ ] We don't need a testbench generator for it / spice runner
- [ ] But we do need a layout DRC, LVS runner on the fixed netlist and GDS.

## `seqgen`

- [ ] Determine whether a gap is needed between sampling and the first comparator decision.
  - [ ] The collected continuous-100-ns experiment removes the programmed gap, but also changes other timing;
    interpret the timing sweep above before drawing a conclusion.
- [ ] Determine whether a gap is needed after the following event. *(Original note was incomplete.)*
- [ ] Review the sequencer design from the SADC library.
  - [ ] Is it externally programmable?
  - [ ] Is it integrated into each ADC?
- [x] Correct the timing guide to show the 15 ns sampling window and all 17 decisions.
- [x] Define a continuous-100-ns sequence and bound final-decision decoding at the conversion boundary.
  - [ ] Implementation and simulation are complete; timing acceptance still requires the pending comparison analysis.

## `salogic`

- [ ] Revisit the ADC power-consumption simulations. (Original note was incomplete.)
- [ ] Finish migrating the different flows into the consistent `flow` namespace. Planning is in the FRIDA remote Codex
  `cleanup` session.
  - [x] Consolidate ADC experiment execution and move simulator diagnostics behind focused pytest targets.
  - [x] Implement concurrent remote campaign deployment, preflight, and automatic result collection.
  - [ ] Identify any remaining namespace-migration work before closing the broad cleanup item.
- [x] Unify C0-first capacitor naming and B0–B16 decision decoding across models, layout, HDL, acquisition, and
      analysis.
  - [ ] Historical silicon retains an explicit boundary mapping. See [ADC conventions](adc_conventions.md).

## Lab setup

- [x] Create manually circuit of resistors + caps, to set voltage described in `design/pcb/input_structure.txt`
- [x] Update PCB schematic decoupling capacitor C6 from 51 pF to 100 nF, in an attempt to reduce bandwidth to limit
      noise
- [ ] Identify how much noise is coming from the differential amplifier by comparing equivalent fixed-input measurements
      with and without it

## Analysis and thesis writing

- [x] Produce all-16-ADC fixed-input density comparisons for the 0 mV and 50 mV campaigns at three rates.
  - [ ] Analysis uses measurements acquired on 2026-08-24.
- [x] Complete and analyse the seven-design baseline transient-noise campaign, with 100 conversions per design.
  - [ ] The baseline uses 100 ns active conversion timing within 160 ns records; it is not continuous 10 MS/s operation.
    Results: `build/sim/adc/comparison/20260905_194921/results/`.
- [x] Add the all-channel density figure and caption to the thesis typography test document.
  - [ ] Figure-placement work in `docs/thesis/test.tex`, not a completed thesis chapter.
- [x] Document corrected CDAC geometry, extraction results, and the held sampling-noise comparison.
  - [ ] Technical material is in [the CDAC report](cdac_pex.md).
- [ ] Develop the existing thesis outline into chapter prose using the completed measurement, extraction, and
      noise-analysis material.
  - [ ] The chapter structure is in `docs/outline.tex`; it currently contains headings only.

checks track vs hold mode front end measurements, to estimate contributions of sampling noise vs comparator input
referred noise effect of sampling duration on comparator, and also full adc noise measurements affect of different
sampling rates, and comparator vs logic clock duty cycle in each, and lett logic fall during the then we should try ramp
and AB comparator methods for capacitor extraction (this depends on a low noise setup) we also need a low noise ramp for
the input to the ADC itself, to get INL/DNL measurements, and full scale measurements And we need to tests what adc
init, and which adc dac init values are optimal. Analyze measurements to prove that noise is is recovered by redundancy
