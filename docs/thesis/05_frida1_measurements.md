# FRIDA-1 measurements {#sec-frida1-measurements}

::: todo
- The chapter's question: does the silicon behave as the single-instance predictions of @sec-frida1-samp, @sec-frida1-comp, @sec-frida1-cdac and @sec-frida1-adc say, and where not, what does that teach the next design?
:::

## Measurement setup {#sec-meas-setup}

One progressive characterization chain is followed:

1. Bound comparator design trade-offs in SPICE, then measure the fabricated comparators.
2. Measure the CDAC element weights which set the SAR decision levels.
3. Establish comparator-to-logic timing before interpreting conversion results.
4. Follow noise through rate, output-code, and bit-decision distributions, then quantify power.
5. Close with a slow monotonic ramp: transfer, code density, DNL, and INL.

::: {#fig-meas-daq src="../images/daq_diagram.pdf"}
The measurement system: FRIDA-1's chip-on-board card and the FPGA carrier, with the sequencer, the serializer and the capture of each comparator output.
:::

::: {#fig-meas-pcb src="../images/pcb.png"}
The FRIDA-1 test board.
:::

The analog input path translates a single-ended laboratory stimulus into the differential signal presented to the converter.
Its output-noise floor therefore limits the smallest transition displacement that can be resolved reliably during static and slowly varying measurements.
The time-domain and frequency-domain estimates of the amplifier's output noise agree at approximately 0.59 mV RMS.

::: todo
- The DAQ chain: the FPGA sequencer at 1600 MBd, the FastRX capture of each comparator output, and the decoding and validation against the scope (zero mismatches, zero lost frames).
- Input drive, references and clock distribution on the board.
:::

## Measured against expected {#sec-meas-overlay}

Each measurement below is drawn over the single-instance prediction of FRIDA-1: the block-level SPICE characterization of its own grid instances (@sec-frida1-samp, @sec-frida1-comp, @sec-frida1-cdac) and the behavioral model of the converter they compose (@sec-frida1-adc).

::: {#fig-meas-comp-noise placeholder="Measured comparator noise and offset over the common mode, over the SPICE characterization of FRIDA-1's comparator instance (the record's own noise_cm plot)."}
Comparator noise over the common mode: measured against FRIDA-1's SPICE instance.
:::

::: {#fig-meas-noise-rate placeholder="Fixed-input code noise over the sampling rate, measured on the 16 channels, over the behavioral model of the generated FRIDA design."}
Code noise over the sampling rate: measured against the behavioral model.
:::

::: {#fig-meas-power-rate placeholder="Supply power over the sampling rate, per rail, measured against the behavioral model's energy sum (@eq-energy)."}
Power over the sampling rate: measured against the behavioral model.
:::

::: todo
- Which overlays agree, and by how much each departs: the comparator's noise, the code noise, the power.
- The lab captures behind these figures (their run IDs) and the command that redraws each over the instance's record.
:::

## Chasing the noise source {#sec-noise-hunt}

At 2 MS/s every COMP duty cycle gives 1.5–1.7 LSB of code spread (ADC00: 1.68).
At 50 % duty it stays near 1.5–2 LSB from 2 to 10 MS/s, yet simulation expects 0.5–0.7 LSB.
So there are two components: a timing malfunction that depends on duty and rate (@sec-meas-sequence), and an underlying random error present at every setting, which this section hunts.

The expressions used throughout:
$$
V_\mathrm{LSB} = \frac{V_\mathrm{ref}}{2^N} = \frac{1.2\,\mathrm{V}}{4096} \approx 293\,\mu\mathrm{V}, \qquad \mathrm{ENOB} = N - \log_2\frac{\sigma_\mathrm{code}}{1/\sqrt{12}\ \mathrm{LSB}},
$$ {#eq-code-enob}
$$
\sigma^2 = \sigma_\mathrm{interferer}^2 + \sigma_\mathrm{broadband}^2, \qquad f_a = \left|\big((f + f_s/2) \bmod f_s\big) - f_s/2\right|.
$$ {#eq-alias}
A tone at $f$ sampled at $f_s$ appears at its alias $f_a$; a candidate frequency is scored by how far each sampling rate's spectrum rises above its floor at the alias it predicts.

::: {#fig-hunt-variance src="../images/interferer_hunt/1_variance_split.pdf"}
The code variance split into an interferer and a broadband part: at 2 MS/s, $1.68^2 = 1.20^2 + 1.18^2$ LSB².
:::

::: {#fig-hunt-alias src="../images/interferer_hunt/3_alias_search.pdf"}
The alias search over several sampling rates (@eq-alias): one interferer near 8.4 MHz explains the lines at every rate.
:::

::: {#fig-hunt-probes src="../images/interferer_hunt/step1_floor_probes_spectrum.pdf"}
Probing the board: spectra at the input, the supplies and the grounds.
:::

::: {#fig-hunt-amp src="../images/interferer_hunt/amp_supply_code_spectra.pdf"}
Code spectra with the input amplifier's supply connected and unplugged.
:::

With the amplifier supply unplugged the code noise of ADC00 falls from 1.68 to 0.98 LSB at 2 MS/s, the interferer's share from 1.11 to 0.10 LSB; at 10 MS/s from 2.14 to 1.40 LSB.
The interferer drifted between 8.75 and 8.90 MHz over one campaign; a fixed 2856 kHz line at 10 MS/s unfolds to 7.143 MHz.

::: {#fig-hunt-best src="../images/interferer_hunt/best_code_spectrum.pdf"}
The quietest code spectrum: ADC02 at 6 MS/s, 0.87 LSB against 1.61 LSB with the interferer.
:::

::: todo
- The root cause: the input amplifier's supply at its connector, and the fix (filtering, or a quieter source).
- What remains after the interferer: the broadband noise against the predicted sampler and comparator noise (@sec-frida1-adc).
:::

## The conversion sequence {#sec-meas-sequence}

At 2 MS/s every COMP duty cycle gives 1.5–1.7 LSB of code spread.
A longer COMP high time (5/8 to 7/8) breaks down at 6–10 MS/s: wider spread, stuck codes.
At 50 % duty the spread stays near 1.5–2 LSB from 2 to 10 MS/s.

: Code σ in LSB over ADC00–03 at 50 mV fixed input, by comparator duty cycle and rate. {#tbl-duty}

| COMP duty | 2 MS/s | 6 MS/s | 10 MS/s |
|:--|:--|:--|:--|
| 4/8 (50 %) | 1.47–1.68 | 1.43–2.02 | 1.71–3.25 |
| 5/8 | 1.48–1.68 | 1.87–3.13 | 2.55–3.95 |
| 6/8 | 1.44–1.69 | 1.89–4.12 | stuck–11.7 |
| 7/8 | 1.87–3.13 | stuck–14.9 | stuck–29.8 |

The fixed LOGIC row has plausible counts 16, 14, 7, and 0 of 16 ADCs as COMP high increases from 4/8 to 7/8; the LOGIC-to-next-COMP update time is held fixed in that row, while the COMP low and LOGIC-after-fall intervals shorten.
This pattern is consistent with a reset or setup limitation but does not identify the failing internal node.

The quietest result is from ADC15 with 5/8 COMP and one-symbol LOGIC: at 9.524 MS/s its full output-code sigma is 0.193 LSB, and at exactly 10 MS/s four LOGIC settings give 0.301–0.316 LSB over 100,000 conversions each.

::: todo
- Finding the right sequence: what the sequence map and the scope's decision eyes showed, and the lag-7 recurrence of all-one frames at 5/8 and 6/8 duty.
- The lesson for the next design: the sequence belongs on chip, or in a self-timed loop (@sec-clocking).
:::

## Capacitor weights and mismatch {#sec-meas-weights}

Each weight is measured as an A-to-B switching curve of the comparator: switching one capacitor from its initial state moves the comparator's 50 % point, and the move, corrected for the comparator's offset, is the capacitor's step:
$$
s_{q,i,d} = \operatorname{sign}(q)\operatorname{sign}(d)\frac{V_\mathrm{off} - V_{50,q,i,d}}{V_\mathrm{DD,DAC}}.
$$ {#eq-ab-step}
The A-state selects the direction of any change on side $q$; the SAR logic then sets $P_\mathrm{final} = 1 - B_i$ and $N_\mathrm{final} = B_i$, so $B_i$ selects an endpoint, not a fixed plate to move.
The separation of the endpoints is the decision weight $w_i = p_i + n_i$, and with the fitted terminal weight $u$ the calibrated code is
$$
D_\mathrm{cal} = \operatorname{round}\!\left[4095\,\frac{\sum_i B_i w_i + B_T u}{\sum_i w_i + u}\right].
$$ {#eq-dcal}

: ADC00's measured weights: P and N are normalized steps in $10^{-3} V_\mathrm{DD,DAC}$, $w$ the final 4095-normalized decision weight. The terminal weight is 1.009 LSB; all 17 normalized weights sum to 4095 exactly. {#tbl-adc00-weights}

| Cap | Ideal | P | N | $w$ |
|:--|--:|--:|--:|--:|
| C0 | 1536 | 156.305 | 149.903 | 1556.219 |
| C1 | 1024 | 98.898 | 104.151 | 1031.941 |
| C2 | 640 | 65.826 | 60.422 | 641.624 |
| C3 | 384 | 35.276 | 39.855 | 381.834 |
| C4 | 192 | 18.579 | 16.359 | 177.562 |
| C5 | 128 | 10.093 | 12.321 | 113.911 |
| C6 | 64 | 6.208 | 6.305 | 63.598 |
| C7 | 48 | 4.626 | 4.694 | 47.364 |
| C8 | 24 | 2.429 | 2.305 | 24.058 |
| C9 | 20 | 1.775 | 2.045 | 19.410 |
| C10 | 10 | 1.057 | 0.982 | 10.364 |
| C11 | 8 | 0.762 | 1.023 | 9.073 |
| C12 | 8 | 0.807 | 0.752 | 7.923 |
| C13 | 4 | 0.260 | 0.449 | 3.607 |
| C14 | 2 | 0.337 | 0.199 | 2.723 |
| C15 | 2 | 0.188 | 0.359 | 2.781 |

ADC00's measured weights depart from the ideal at several redundant bits.
Direction matching is physical, but does not transfer into lower INL.

::: {#fig-meas-weights placeholder="ADC00's measured weights against the design and the extracted weights, and each stage's error against the mismatch the pipeline predicts for FRIDA-1's array (@sec-frida1-cdac)."}
Measured capacitor weights against prediction.
:::

::: todo
- The mismatch coefficient the measured weights imply, against the 1 %·√fF assumed in @fig-cdac-gap.
- The ramp's DNL and INL before and after calibration (@eq-dcal) on ADC00–03.
:::

## Redundancy at speed {#sec-meas-redundancy}

In four matched ADC15 recipes at 2, 6 and 10 MS/s, 2.4 million complete conversions, bits B0–B10 never change.
B11 is high in 95.2–95.9 % of conversions at 2 MS/s, 60.1–65.6 % at 6 MS/s, and 1.95–7.68 % at 10 MS/s; at 10 MS/s, B11 high is exactly equivalent to an output code other than the mode.
The 10 MS/s code spread thus coincides with one output branch becoming rare, as the redundant decisions after it correct less as the time per decision shrinks.

::: todo
- The lesson: redundancy corrects as designed at low rate, but at speed the settling or the comparator's delay leaves decisions the later stages cannot recover (@sec-redundancy, @eq-regeneration).
- Redundancy shortens a conversion where DAC settling dominates, not where the latch delay does [@chang2013]: which regime FRIDA-1 is in.
:::

## Power {#sec-meas-power}

Preliminary prototype measurements indicate approximately 488–494 µW at 10 MS/s and a 1.2 V supply for ADC00 and ADC01: 451–457 µW on the digital supply, 34 µW on the DAC's reference and 3 µW on the analog supply.

::: todo
- The digital supply's dominance against the behavioral model's 28.9 pJ per conversion (@sec-adc-energy): the logic, the LVDS drivers, the clock.
:::

## Lessons learned {#sec-meas-lessons}

::: {#fig-meas-survey placeholder="The survey's resolution against energy and figure of merit against area (@fig-survey-energy, @fig-survey-area) with FRIDA-1's measured point and the generated design's predicted one."}
FRIDA-1 measured, on the survey's plots.
:::

::: todo
- FRIDA-1 on the survey: where it falls, and how far from the design goal.
- The lessons: the input path's interferer, the external sequence's timing limits, redundancy at speed, the measured mismatch, the logic's power.
:::
