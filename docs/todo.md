# To Do

## `samp`

- [ ] Study the effect of increased sampling time in measurements and simulation. Is 20 ps needed?
- [ ] Finish separating the sampling-switch noise from the comparator input-referred offset.

## `comp`

- [ ] Better understand the relationship between the comparator and logic clocks.
  - [ ] Study the noise and metastability effects of the current design. At the planned 10 MS/s operating rate, the
    comparator has only 2–4 ns to settle.
  - [ ] Measure this using the physical ADC and simulate both the full ADC and the comparator by itself.
  - [ ] Evaluate the flip side of this problem. *(Original note was incomplete.)*
- [ ] Determine whether the current comparator is reaching metastability or suffering from other limitations.
- [ ] Investigate a new comparator with lower kickback, shorter metastability time, and better input-referred offset.
- [ ] Continue using OpenROAD to generate a comparator layout from discrete transistors represented by LEF files.

## `cdac`

- [ ] Verify whether the ADC really has 800 pF of capacitance per branch.
  - [ ] Check the capacitance with the new layer connected.
  - [ ] Determine whether half of the ADCs really had only a single capacitance layer.
- [ ] Understand why the input range is attenuated so much and quantify the parasitic capacitance.
- [ ] Study how the CDAC initialization values affect ADC operation. The current value is `16'h5555`, but the reason for
  using it is not yet well understood.

## `seq`

- [ ] Determine whether a gap is needed between sampling and the first comparator decision.
- [ ] Determine whether a gap is needed after the following event. *(Original note was incomplete.)*
- [ ] Review the sequencer design from the SADC library.
  - [ ] Is it externally programmable?
  - [ ] Is it integrated into each ADC?

## `salogic`

- [ ] Revisit the ADC power-consumption simulations. *(Original note was incomplete.)*
- [ ] Finish migrating the different flows into the consistent `flow` namespace. Planning is in the FRIDA remote Codex
  `cleanup` session.
