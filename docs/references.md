# References and notation

The blocks' analyses, metrics and figures cite the textbook that defines what they compute. Five textbooks and three papers are the only sources a citation names, each by its key:

| Key | Text |
| --- | --- |
| `[Razavi-Analog]` | B. Razavi, *Design of Analog CMOS Integrated Circuits*, 2nd ed. |
| `[Razavi-PLL]` | B. Razavi, *Design of CMOS Phase-Locked Loops*, 2020. |
| `[Razavi-ADC]` | B. Razavi, *Analysis and Design of Data Converters*, 2025. |
| `[Pelgrom]` | M. Pelgrom, *Analog-to-Digital Conversion*, 4th ed. |
| `[Baker]` | R. J. Baker, *CMOS: Circuit Design, Layout, and Simulation*, 4th ed. |

## Papers

A paper is cited only where none of the five textbooks defines the quantity or the circuit: the double-tail latch, the modified double tail and the dynamic bias of a comparator.

| Key | Text |
| --- | --- |
| `[Schinkel]` | D. Schinkel, E. Mensink, E. Klumperink, E. van Tuijl, B. Nauta, *A Low-Offset Double-Tail Latch-Type Voltage Sense Amplifier*, pp. 89–94: the extended paper of their *A Double-Tail Latch-Type Voltage Sense Amplifier with 18ps Setup+Hold Time*, ISSCC 2007, which it cites; its pages are the extended paper's. |
| `[vanElzakker]` | M. van Elzakker et al., *A 10-bit Charge-Redistribution ADC Consuming 1.9 µW at 1 MS/s*, IEEE JSSC, vol. 45, no. 5, May 2010. |
| `[Bindra]` | H. S. Bindra et al., *A 1.2-V Dynamic Bias Latch-Type Comparator in 65-nm CMOS With 0.4-mV Input Noise*, IEEE JSSC, 2018, the early-access version: its pages as printed there. |

## Citations

A citation is a code comment beside (or directly above) the line that computes the quantity, a field or a figure, of this shape:

```python
# [Razavi-Analog] Eq. (10.11), p. 413: phase margin
```

The locator is the source's own equation, figure, section, example or table number, and the page is the page number printed on the page, not the PDF's. Where none of the sources defines a quantity, the comment says so and defines it in one line, with where the definition comes from:

```python
# not in the reference texts: <one-line definition and where it comes from>
```

A locator is written only after reading it on the page it names. Cite by locator only: never copy a source's text, figures or tables into the repository.

## Notation

Every block names an electrical quantity as the tables below do. The symbol and name are Razavi's (*Design of Analog CMOS Integrated Circuits* first; his PLL book for clocking, delay, jitter and phase; his data-converter book for converter quantities); where he does not treat a quantity the row says so and takes Baker's or Pelgrom's. The "where defined" column is the locator a citation comment carries.

Columns: the identifier is the name of an `Analysis` field, a `Metrics` field or a metric key (a testbench parameter where marked TB); the axis label is a `Plot` spec's `x_label`/`y_label`; the unit is the SI base unit the value is stored and plotted in (never scaled: no mV, ps, µA).

### Supplies, levels, bias

| Quantity | Razavi symbol | Where defined | Identifier | Axis label | Unit |
| --- | --- | --- | --- | --- | --- |
| Supply voltage | V_DD | [Razavi-Analog] Fig. 3.4, p. 48 | `vdd_v` (TB: `vdd`) | `Supply (V)`; a relative sweep `Supply over nominal` | V |
| Input voltage | V_in | [Razavi-Analog] Fig. 3.4, p. 48 | `vin_v` | `Input level (V)` | V |
| Output voltage | V_out | [Razavi-Analog] Fig. 3.4, p. 48 | `vout_v` | `Output (V)` | V |
| Input common-mode level | V_in,CM | [Razavi-Analog] Sec. 4.2, p. 103 | `vin_cm_v` | `Input common mode (V)` | V |
| Output common-mode level | V_out,CM | [Razavi-Analog] Sec. 4.2, p. 103 | `vout_cm_v` | `Output common mode (V)` | V |
| Differential input | V_in1 − V_in2 | [Razavi-Analog] Eq. (4.2), p. 106 | `vin_diff_v` | `Differential input (V)` | V |
| Differential output | V_out1 − V_out2 | [Razavi-Analog] Fig. 4.8, p. 104 | `vout_diff_v` | `Differential output (V)` | V |
| Input common-mode range | range of V_in,CM | [Razavi-Analog] Eq. (4.1), p. 105 | `vin_cm_range_v` (single-ended: `input_range_v`) | `Input common-mode range (V)` | V |
| Output swing | output swing (CML: R_D·I_SS) | [Razavi-Analog] Sec. 9.1.1, p. 348; [Razavi-PLL] Sec. 15.2.1, p. 456 | `swing_v` (single-ended; `swing_diff_v`) | `Output swing (V)` | V |
| Output logic levels | V_OH, V_OL | [Baker] Fig. 10.9, p. 333 (Razavi: none) | `voh_v`, `vol_v` | `Output high level (V)`, `Output low level (V)` | V |
| Bias voltage of a gate | V_b | [Razavi-Analog] Sec. 5.2, p. 142 | `vb_v`; a named net `v<net>_v` (`vbn_v`, `vcasp_v`) | `Bias voltage (V)` | V |
| Reference voltage (a DAC's; a comparator's threshold) | V_REF | [Razavi-ADC] Eq. (11.12), p. 216; Sec. 6.2.1, p. 107 | `vref_v` | `Reference (V)` | V |
| Reference current | I_REF | [Razavi-Analog] Sec. 5.1, p. 135 | `iref_a` | `Reference current (A)` | A |
| Output (copied) current | I_out | [Razavi-Analog] Eq. (5.4), p. 136 | `iout_a` | `Output current (A)` | A |
| Mirror ratio | I_out / I_REF | [Razavi-Analog] Eq. (5.4), p. 136 | `iout_over_iref` | `Output current over the reference` | A/A |
| Tail current | I_SS | [Razavi-Analog] Fig. 4.7, p. 103 | `iss_a` | `Tail current (A)` | A |
| Supply current | I_DD | [Razavi-PLL] Example 3.5, p. 70 | `idd_a` (a state's: `idd_static_a`, `idd_peak_a`) | `Supply current (A)` | A |
| Power dissipation | P | [Razavi-PLL] Sec. 3.3.2, p. 74 | `power_w` (a transient's mean: `average_power_w`) | `Power (W)` | W |
| Energy per cycle (per decision) | P_avg / f_clk | [Baker] Eq. (11.15), p. 355 (the average power; Razavi: none) | `energy_per_cycle_j`, `energy_per_decision_j` | `Energy per cycle (J)`, `Energy per decision (J)` | J |
| Overdrive voltage | V_GS − V_TH | [Razavi-Analog] Sec. 2.2, p. 14 | `vov_v` | `Overdrive voltage (V)` | V |
| Drain-source voltage (a mirror device's) | V_DS; its minimum V_D,sat | [Razavi-Analog] Example 2.2, p. 18 | `vds_v` | `Drain-source voltage (V)` | V |
| Minimum (maximum) output voltage of a current source: its headroom | minimum allowable voltage | [Razavi-Analog] Sec. 5.2, p. 141 | `vout_min_v`, `vout_max_v` | `Minimum output voltage (V)` | V |
| Output resistance | R_out (a device's r_O) | [Razavi-Analog] Eq. (3.65), p. 65; Eq. (2.44), p. 31 | `rout_ohm` | `Output resistance (ohm)` | ohm |
| Output impedance over frequency | Z_out | [Razavi-Analog] Eq. (6.63), p. 192 | `zout_ohm` | `Output impedance (ohm)` | ohm |
| On-resistance | R_on | [Razavi-Analog] Eq. (2.11), p. 15 | `ron_ohm` | `On-resistance (ohm)` | ohm |
| Transconductance | g_m | [Razavi-Analog] Eq. (2.17), p. 19 | `gm_a_per_v` | `Transconductance (A/V)` | A/V |
| Load capacitance | C_L | [Razavi-Analog] Sec. 6.7.1, p. 204 | `cload_f` | `Load capacitance (F)` | F |
| Level shift of a follower | V_GS | [Razavi-Analog] Sec. 3.4, p. 68 | `level_shift_v` | `Level shift (V)` | V |

### Amplifiers: gain, frequency response, large signal, noise

| Quantity | Razavi symbol | Where defined | Identifier | Axis label | Unit |
| --- | --- | --- | --- | --- | --- |
| Voltage gain | A_v | [Razavi-Analog] Eq. (3.8), p. 48 | `gain`; in dB `gain_db` | `Gain (V/V)`, `Gain (dB)` | V/V, dB |
| Low-frequency gain | A_0 | [Razavi-Analog] Sec. 6.7.1, p. 204 | `gain_dc_db` | `Low-frequency gain (dB)` | dB |
| Common-mode gain | A_v,CM | [Razavi-Analog] Eq. (4.36), p. 118 | `gain_cm` | `Common-mode gain (V/V)` | V/V |
| Common-mode rejection ratio | CMRR | [Razavi-Analog] Eq. (4.55), p. 123 | `cmrr_db` (lowest frequency: `cmrr_dc_db`) | `CMRR (dB)` | dB |
| Power supply rejection ratio | PSRR | [Razavi-Analog] Sec. 9.11, p. 400 | `psrr_db` (`psrr_dc_db`; the supply's gain `gain_supply`) | `PSRR (dB)` | dB |
| Frequency | f (ω = 2πf) | [Razavi-Analog] Fig. 6.43, p. 204 | `frequency_hz` | `Frequency (Hz)` | Hz |
| −3-dB bandwidth | ω_−3dB | [Razavi-Analog] Fig. 6.43, p. 204 | `bandwidth_hz` | `-3 dB bandwidth (Hz)` | Hz |
| Unity-gain bandwidth | ω_u | [Razavi-Analog] Fig. 6.43, p. 204 | `unity_gain_bandwidth_hz` | `Unity-gain bandwidth (Hz)` | Hz |
| Gain-bandwidth product | GBW | [Razavi-Analog] Eq. (6.98), p. 204 | `gbw_hz` | `Gain-bandwidth product (Hz)` | Hz |
| Phase of the response | ∠βH(ω) (the loop transmission's) | [Razavi-Analog] Sec. 10.1, p. 411 | `phase_deg` | `Phase (deg)` | deg |
| Phase margin | PM | [Razavi-Analog] Sec. 10.3, p. 417 | `phase_margin_deg` | `Phase margin (deg)` | deg |
| Gain margin | GM | [Baker] Sec. 24.1, p. 810 (Razavi: none) | `gain_margin_db` | `Gain margin (dB)` | dB |
| Slew rate | slew rate | [Razavi-Analog] Sec. 9.9, p. 391 | `slew_rate_v_per_s` (`slew_rate_rise_v_per_s`) | `Slew rate (V/s)` | V/s |
| Settling time | t_s (to 1 %: t_1%) | [Razavi-ADC] Sec. 8.2.2, p. 150; [Razavi-Analog] Example 9.2, p. 346 | `settling_s` (`settling_rise_s`) | `Settling time (s)` | s |
| Overshoot | none | not in the reference texts: how far a step response passes its final level, a fraction of the step (the calculator's `overshoot`) | `overshoot` | `Overshoot` | V/V |
| Time constant | τ | [Razavi-Analog] Eq. (13.31), p. 552 | `tau_s` | `Time constant (s)` | s |
| Closed-loop gain error | gain error | [Razavi-Analog] Eq. (13.53), p. 565 | `gain_error` | `Gain error` | V/V |
| Input-referred noise, rms | V_n,in | [Razavi-Analog] Eq. (7.45), p. 238 | `noise_in_v` | `Input-referred noise (V)` | V |
| Output noise, rms | V_n,out (its power P_n,out) | [Razavi-Analog] Eq. (7.20), p. 229 | `noise_out_v` | `Output noise (V)` | V |
| Noise spectral density | square root of S(f) | [Razavi-Analog] Sec. 7.1.1, p. 223 | `noise_in_v_per_rthz`, `noise_out_v_per_rthz` | `Input-referred noise (V/sqrt(Hz))` | V/√Hz |
| Input offset voltage | V_OS (V_OS,in) | [Razavi-Analog] Sec. 14.2.1, p. 593; [Razavi-ADC] Sec. 5.1, p. 71 | `offset_v` | `Offset (V)` | V |
| Total harmonic distortion | THD | [Razavi-Analog] Eq. (14.10), p. 579 | `thd_db` | `THD (dB)` | dB |
| Signal-to-(noise + distortion) ratio | SNDR | [Razavi-ADC] Sec. 8.2.2, p. 150 | `sndr_db` | `SNDR (dB)` | dB |
| Effective number of bits | ENOB | [Razavi-ADC] Eq. (12.17), p. 247 | `enob_bits` | `ENOB (bits)` | bits |

### Sampling and clocks

| Quantity | Razavi symbol | Where defined | Identifier | Axis label | Unit |
| --- | --- | --- | --- | --- | --- |
| Sampling rate | f_S = 1/T_S | [Razavi-ADC] Sec. 3.1.1, p. 20 | `sample_rate_hz` | `Sampling rate (Hz)` | Hz |
| Clock period, frequency | T_CK, f_CK | [Razavi-ADC] Sec. 3.1.3, p. 24 | `clock_period_s`, `clock_frequency_hz` | `Clock period (s)`, `Clock frequency (Hz)` | s, Hz |
| Acquisition time | t_acq | [Razavi-ADC] Sec. 3.9.1, p. 53 | `acquisition_s` | `Acquisition time (s)` | s |
| Track error (the error left at the end of tracking) | ΔV | [Razavi-ADC] Fig. 3.50, p. 53 | `track_error_v` | `Output minus input (V)` | V |
| Pedestal (charge injection and clock feedthrough) | ΔV | [Razavi-Analog] Sec. 13.2, p. 550; [Razavi-ADC] Sec. 3.5.3, p. 36 | `pedestal_v` | `Pedestal (V)` | V |
| Droop | V_droop per time | [Pelgrom] Eq. (8.3), p. 387 (Razavi: none) | `droop_v_per_s` | `Droop (V/s)` | V/s |
| Hold-mode feedthrough | none | [Pelgrom] Sec. 8.2.3, p. 387 (Razavi: none) | `feedthrough`; in dB `feedthrough_db` | `Feedthrough (dB)` | V/V, dB |
| Transition time of a source | t_r, t_f | [Baker] Fig. 10.9, p. 333 (Razavi: none) | TB: `transition_time_s` | `Transition time (s)` | s |
| Output rise, fall time (10–90 %) | t_LH, t_HL | [Baker] Fig. 10.9, p. 333 (Razavi: none) | `rise_time_s`, `fall_time_s` | `Rise time (s)`, `Fall time (s)` | s |
| Duty cycle | (T_CK/2 + ΔT)/T_CK | [Razavi-PLL] Sec. 11.10, p. 365 | `duty_cycle` | `Duty cycle` | s/s |
| Nonoverlap time of two clock phases | none | [Baker] Sec. 14.1.3, p. 415 (Razavi: none) | `nonoverlap_rise_s`, `nonoverlap_fall_s` | `Nonoverlap time (s)` | s |
| rms jitter (cycle-to-cycle) | J_rms (J_cc,rms) | [Razavi-PLL] Eq. (2.33), p. 51; Eq. (2.38), p. 52 | `jitter_s` (`jitter_cc_s`) | `Jitter (s)` | s |

### Comparators, discriminators, triggers, latches

| Quantity | Razavi symbol | Where defined | Identifier | Axis label | Unit |
| --- | --- | --- | --- | --- | --- |
| Comparator (clock-to-decision) delay | t_comp | [Razavi-ADC] Sec. 16.1, p. 332 | `delay_s` | `Clock-to-decision delay (s)` | s |
| Regeneration time constant | τ_reg | [Razavi-ADC] Eq. (5.19), p. 78 | `regeneration_tau_s` | `Regeneration time constant (s)` | s |
| Input-referred noise of a comparator | σ (rms V_n,in) | [Razavi-ADC] Sec. 6.4, p. 117 | `noise_sigma_v` | `Input-referred noise (V)` | V |
| Decision probability | probability of a ONE | [Razavi-ADC] Sec. 6.4, p. 117 | `decision_probability` | `Decision probability` | — |
| Metastable (unresolved) share | metastability | [Razavi-ADC] Sec. 6.2, p. 107 | `unresolved_fraction` | `Fraction unresolved` | — |
| Kickback | kickback noise | [Razavi-ADC] Sec. 5.7.4, p. 88 | `kickback_v` (`kickback_diff_v`) | `Kickback (V)` | V |
| Trip point (inverter, trigger, ring amplifier) | trip point (Baker: V_SP; a trigger's V_SPH, V_SPL) | [Razavi-Analog] Sec. 15.2, p. 614; [Baker] Eq. (18.1), p. 534 | `trip_v`; `trip_rise_v`, `trip_fall_v` (input rising, falling) | `Trip point (V)` | V |
| Hysteresis | V_H = V_SPH − V_SPL | [Baker] Eq. (18.1), p. 534 (Razavi: none) | `hysteresis_v` | `Hysteresis (V)` | V |
| Propagation delay | t_PLH, t_PHL | [Baker] Fig. 10.9, p. 333 (Razavi: none) | `delay_s`; `delay_rise_s`, `delay_fall_s` (output rising, falling) | `Delay (s)` | s |
| Setup, hold time | t_s, t_h | [Baker] Fig. 13.25, p. 401; Fig. 13.26, p. 402 (Razavi: hold time named only, [Razavi-PLL] Sec. 15.2.2, p. 461) | `setup_s`, `hold_s` | `Setup time (s)`, `Hold time (s)` | s |
| CK-to-Q delay | CK-to-Q delay | [Razavi-PLL] Fig. 13.40, p. 424 | `clock_to_q_s` (`clock_to_q_rise_s`) | `Clock-to-Q delay (s)` | s |
| Maximum clock frequency (a divider's, a latch's) | f_max | [Razavi-PLL] Sec. 15.1, p. 453 | `fmax_hz` | `Maximum clock frequency (Hz)` | Hz |

### Oscillators, delay lines, phase

| Quantity | Razavi symbol | Where defined | Identifier | Axis label | Unit |
| --- | --- | --- | --- | --- | --- |
| Oscillation frequency, period | f_0, T_0 | [Razavi-PLL] Sec. 3.1.1, p. 64 | `oscillation_frequency_hz`, `period_s` | `Oscillation frequency (Hz)` | Hz, s |
| Gate (stage) delay | T_D | [Razavi-PLL] Sec. 1.4.1, p. 12 | `stage_delay_s` | `Stage delay (s)` | s |
| Control voltage | V_cont | [Razavi-PLL] Sec. 1.6, p. 27 | `vcont_v` | `Control voltage (V)` | V |
| VCO gain | K_VCO | [Razavi-PLL] Sec. 1.6, p. 27 | `kvco_hz_per_v` | `VCO gain (Hz/V)` | Hz/V |
| Delay-line gain | K_DL (rad/V; here as time) | [Razavi-PLL] Sec. 11.1, p. 346 | `kdl_s_per_v` | `Delay-line gain (s/V)` | s/V |
| Phase of a clock | φ | [Razavi-PLL] Sec. 11.1, p. 346 | `phase_deg` (`phase_out_deg`, `phase_spacing_deg`) | `Phase (deg)` | deg |
| Phase interpolation: the output phase over the weights | none | [Razavi-PLL] Sec. 11.8, p. 360 | `phase_out_deg`; its error from the line `inl_deg` | `Output phase (deg)`, `INL (deg)` | deg |

### Converters and DACs

| Quantity | Razavi symbol | Where defined | Identifier | Axis label | Unit |
| --- | --- | --- | --- | --- | --- |
| LSB | Δ = 1 LSB | [Razavi-ADC] Sec. 12.2.1, p. 237 | `lsb_v` | `LSB (V)` | V |
| Full scale | V_FS | [Razavi-ADC] Sec. 12.2.1, p. 237 | `full_scale_v` | `Full scale (V)` | V |
| Differential nonlinearity | DNL | [Razavi-ADC] Sec. 8.2, p. 145 (DAC); Eq. (12.11), p. 242 (ADC) | `dnl_lsb` | `DNL (LSB)` | LSB |
| Integral nonlinearity | INL | [Razavi-ADC] Sec. 8.2, p. 147 (DAC); Sec. 12.3.4, p. 243 (ADC) | `inl_lsb` | `INL (LSB)` | LSB |
| Missing codes | missing code | [Razavi-ADC] Sec. 12.3.3, p. 243 | `missing_codes` | `Missing codes` | count |
| DAC step, settling time | t_s | [Razavi-ADC] Sec. 8.2.2, p. 150 | `step_v`, `settling_s` | `Step (V)`, `Settling time (s)` | V, s |
| Unit capacitance | C_0 | [Razavi-ADC] Sec. 11.8, p. 229 | `unit_f` | `Unit capacitance (F)` | F |
| Capacitor mismatch coefficient | none (Pelgrom: A_C) | [Pelgrom] Eq. (4.34), p. 144 (Razavi: none) | `pelgrom` | `Pelgrom coefficient (%·sqrt(fF))` | %·√fF |
| Unit current of a current-steering DAC | I_0 | [Razavi-ADC] Fig. 10.1, p. 174 | `iout_a` of the unit | `Output current (A)` | A |

### Not in the reference texts

Each takes the comment `# not in the reference texts: <definition>` with the definition below.

| Quantity | Definition and origin | Identifier | Axis label | Unit |
| --- | --- | --- | --- | --- |
| Injected charge | the charge a step through the injection capacitor puts on the input (detector read-out) | `charge_c` | `Injected charge (C)` | C |
| Charge gain | output amplitude over the injected charge (detector read-out) | `charge_gain_v_per_c` | `Charge gain (V/C)` | V/C |
| Equivalent noise charge | output rms noise over the charge gain, in electrons (detector read-out) | `enc_electrons` | `ENC (electrons)` | e⁻ |
| Peaking time | from the injection to the pulse's peak (detector read-out) | `peaking_time_s` | `Peaking time (s)` | s |
| Time over threshold | how long the pulse stays past the threshold (detector read-out) | `tot_s` | `Time over threshold (s)` | s |
| Time walk | the delay's spread from the smallest to the largest input (detector read-out) | `timewalk_s` | `Time walk (s)` | s |
| Detector, injection capacitance | the capacitances on the input node (detector read-out) | `cdet_f`, `cinj_f` | `Detector capacitance (F)` | F |
| Critical charge | the smallest charge on the storage node that flips the stored state (single-event upset) | `critical_charge_c` | `Critical charge (C)` | C |
| Second (input) supply of a level shifter | the supply of the domain the input comes from | `vddl_v` | `Input supply (V)` | V |
| On-off ratio | enabled output current over the disabled one's magnitude | `on_off_ratio` | `On-off ratio` | A/A |
| Dead zone of a ring amplifier | the input range in which neither output device conducts; named in [Pelgrom] Sec. 15.3, p. 735, without a symbol | `dead_zone_v` | `Dead zone (V)` | V |
| Share of trials (captured, correct, switched) | the fraction of the run's edges that did so | `<what>_fraction` | `Fraction <what>` | — |
| Strike charge | the charge a particle strike's double-exponential current puts on a storage node (single-event upset); not the read-out's injected charge | `charge_c` | `Strike charge (C)` | C |
| Smallest flipping strike | the smallest strike charge that flipped the stored state on a charge grid: the critical charge's upper bound | `flip_charge_c` | `Strike charge (C)` | C |
| D-to-Q delay of a transparent latch | from d's mid-supply crossing to q's while the latch is open (Baker Fig. 13.20, p. 399: q follows d while the clock is high) | `delay_rise_s`, `delay_fall_s` (a latch's) | `D-to-Q delay (s)` | s |
| Supply current of a cell's input drivers | the current CMOS drivers on V_DD of the inputs would draw: the charge the inputs' sources deliver into the cell, over the time ([Baker] Eq. (11.14), p. 355) | `idd_drivers_a` | `Supply current (A)` | A |

### Composing a name not in the table

1. Identifier: `<quantity>[_<qualifier>...]_<unit>`, snake_case, lower case, no block name (the
   namespace carries it: `ota.Metrics.gain_dc_db`, never `ota_gain`). `ALL_CAPS` is for Enum
   members only.
2. The quantity. A node voltage, a branch current or an element value that Razavi writes as a
   subscripted letter takes that symbol, flattened and lower-cased: V_in,CM is `vin_cm`, I_SS
   `iss`, R_on `ron`, τ `tau`, K_VCO `kvco`. A figure of merit he names in words takes those
   words, the word "time" dropped from a measured duration (`settling_s`, `delay_s`, `hold_s`,
   `clock_to_q_s`); one he names by an acronym takes the acronym (`cmrr`, `psrr`, `thd`, `gbw`,
   `inl`, `dnl`, `lsb`, `sndr`). Look the symbol up in Razavi-Analog first, then Razavi-PLL
   (clocking, delay, jitter, phase), then Razavi-ADC (converters); only then Baker or Pelgrom,
   and say "(Razavi: none)" beside the locator.
3. Qualifiers follow the quantity, before the unit, in this order: which (`_cm`, `_diff`, `_in`,
   `_out`, `_dc`), side or polarity (`_p`, `_n`), direction (`_rise`, `_fall`: the output's edge),
   statistic (`_max`, `_min`, `_p95`), condition (`_supply`: over the supply sweep; `_0p5mv`,
   `_1mhz`: at a value, the decimal point a `p`, the unit prefix kept in the condition only).
   Examples: `delay_rise_s`, `rout_n_ohm`, `ron_max_supply_ohm`, `noise_in_1mhz_v_per_rthz`.
4. The unit suffix is the SI base unit, lower case: `_v _a _s _hz _ohm _f _c _w _j _deg _db _lsb
   _bits`. A quotient is `_<u>_per_<u>` (`_v_per_s`, `_hz_per_v`, `_v_per_c`, `_a_per_v` for a
   transconductance, since `_s` is seconds; `_v_per_rthz` for a density). A dimensionless ratio
   has no suffix (`gain`, `duty_cycle`, `overshoot`, `iout_over_iref`); a share of trials ends
   `_fraction`; a ratio in decibels ends `_db`. Values are stored unscaled.
5. Testbench parameters (TB) follow the reference blocks' `TbParams`: `vdd` bare, every other
   value with its unit suffix, a programmed duration `<what>_time_s` (`transition_time_s`,
   `reset_time_s`), a period `<what>_period_s`, a count bare (`periods`, `conversions`). A swept
   value is named as the analysis field that reports it (`vin_cm`, `iref`, `vcont`).
6. Axis label: `<Name> (<unit>)`, sentence case, Razavi's name for the quantity in words (not the
   symbol), the SI base unit in ASCII as the reference blocks write it (`V`, `A`, `s`, `Hz`,
   `ohm`, `F`, `C`, `W`, `J`, `deg`, `dB`, `LSB`, `V/s`, `V/sqrt(Hz)`). A dimensionless
   quantity has no parenthesis (`Decision probability`, `Supply over nominal`); a linear gain
   may say `(V/V)`. One quantity per axis; the plot's `title` carries the condition, not the label.
   A series label is the quantity in lower case (`"delay"`, `"on-resistance"`).
7. One symbol, one meaning: `t_s` is the settling time (Razavi), so setup is `setup_s`;
   "feedthrough" alone is Razavi's clock feedthrough, part of `pedestal_v`; "overdrive" alone
   is V_GS − V_TH, so an input above a threshold is `vin_diff_v`; `frequency_hz` is the swept
   axis, an oscillator's own is `oscillation_frequency_hz`.
