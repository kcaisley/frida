# To Do

## `samp`

- [ ] Study the effect of increased sampling time in measurements and simulation. Is 20 ps needed?
- [ ] Finish separating the sampling-switch noise from the comparator input-referred offset.

## `comp`

- [ ] Better understand the relationship between the comparator and logic clocks.
  - [ ] Study the noise and metastability effects of the current design. At the planned 10 MS/s operating rate, the
    comparator has only 2–4 ns to settle.
  - [ ] Investigate the optimal timing relationship. The comparator clearly needs more time; determine how far its
    evaluation time can be pushed without reducing the following logic and CDAC-settling margins too far.
  - [ ] Measure this using the physical ADC and simulate both the full ADC and the comparator by itself.
  - [ ] And evaluate the other side of this problem. (Original note was incomplete.)
- [ ] Determine whether the current comparator is reaching metastability or suffering from other limitations.
- [ ] Investigate a new comparator with lower kickback, shorter metastability time, and better input-referred offset.
- [ ] Continue using OpenROAD to generate a comparator layout from discrete transistors represented by LEF files.

## `cdac`

- [ ] Verify/investigate the cdac's 800 pF of capacitance per branch
  - [ ] Check the capacitance with the new layer connected.
  - [ ] Determine whether half of the ADCs really had only a single capacitance layer.
- [ ] Understand why the input range is attenuated so much and quantify the parasitic capacitance.
- [ ] Study how the CDAC initialization values affect ADC operation. The current value is `16'h5555`, but the reason for
  using it is not yet well understood.
  - [ ] Map common mode versus differential input versus initialization state. Assuming an externally applied 600 mV
    common mode, determine how best to keep the comparator near its 700 mV optimum across all input conditions.

## `seq`

- [ ] Determine whether a gap is needed between sampling and the first comparator decision.
- [ ] Determine whether a gap is needed after the following event. *(Original note was incomplete.)*
- [ ] Review the sequencer design from the SADC library.
  - [ ] Is it externally programmable?
  - [ ] Is it integrated into each ADC?

## `salogic`

- [ ] Revisit the ADC power-consumption simulations. (Original note was incomplete.)
- [ ] Finish migrating the different flows into the consistent `flow` namespace. Planning is in the FRIDA remote Codex
  `cleanup` session.

## Measurement setup

- [ ] Identify how much noise is coming from the differential amplifier by comparing equivalent fixed-input
  measurements with and without it.
- [ ] Investigate producing a low-voltage-drive ramp-generator board for quieter ADC transfer-curve measurements.
