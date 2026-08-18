# ADC front-end bandwidth and characterization plan

## Objective

Reduce the integrated noise delivered by the THS4541 input driver without
changing its DC gain, then repeat the ADC measurements needed to compare the
present and lower-bandwidth front ends. Keep simulation, physical acquisition,
analysis, and plotting as separate manually accepted stages.

## Present circuit

The populated input stage uses `RF = RG = 499 ohm`, so its differential DC
gain remains one as long as those resistors are unchanged. C4 and C5 are the
matched halves of one differential feedback pole. C6 and the two output
resistors form a second differential pole:

```text
GDC = RF / RG
fFB = 1 / (2 pi RF CF)
fOUT = 1 / (2 pi (R25 + R26) (C6 + CADC,diff))

H(s) / H(0) ~= 1 / ((1 + s RF CF) (1 + s (R25 + R26) (C6 + CADC,diff)))
```

With all three capacitors at 51 pF, the ideal pole frequencies are 6.25 MHz
and 3.13 MHz, giving an approximately 2.62 MHz combined bandwidth. The older
PCB presentation's 25 MHz output estimate used 56 ohm output resistors and is
not applicable to the populated 499 ohm values.

## First rework

Leave the feedback capacitors C4 and C5 at 51 pF. Increase only the total C6
capacitance to 22--44 nF, rather than 2.2 nF. This keeps the THS4541 feedback
network and DC gain unchanged and uses R25 and R26 to isolate the added load
from the amplifier outputs, as recommended in the THS4541 data sheet.

Begin with one 22 nF C0G/NP0 part at C6. The PCB footprint is 0402. If more
suppression is needed, two matched 22 nF parts in parallel or stacked give
approximately 44 nF. Do not increase C4 or C5 during this rework: once C6 is
dominant, 1--2 nF feedback capacitors add little suppression while changing
the amplifier's frequency-dependent noise gain and stability.

With `R25 + R26 = 998 ohm`, the expected output pole and suitably slowed sine
stimulus are:

| Total C6 | Output pole | Suggested sine | Ideal amplitude loss | White-noise estimate |
| ---: | ---: | ---: | ---: | ---: |
| 2.2 nF | 72.5 kHz | 10 kHz | 0.94% | about 185 uV RMS |
| 22 nF | 7.25 kHz | 1 kHz | 0.94% | about 59 uV RMS |
| 44 nF | 3.63 kHz | 500 Hz | 0.94% | about 42 uV RMS |

These estimates assume the earlier approximately 1 mV result is broadband
white noise. That value came from a 1 MHz sine-fit residual measured with a
250 MHz scope bandwidth, so it also contains scope and AWG noise, distortion,
and jitter rather than only THS4541 output noise. The newer quiet-output check
measured about 0.588 mV RMS with a 20 MHz scope limit and likewise includes the
probe and scope floor. The table is therefore a sizing estimate, not a
guaranteed post-rework result. The local THS4541 model showed no AC peaking for
the earlier 2.2 nF candidate, but the 22--44 nF hardware still requires the
qualification below.

## Qualification sequence

1. Run the quiet-output THS4541 hardware test before and after rework.
2. With 22 nF, check the 1 kHz differential amplitude, settling, overshoot, and
   absence of oscillation on the scope before starting a long campaign. Use
   500 Hz if C6 is increased to 44 nF. The existing 10 Hz ramp is already slow
   enough for either value.
3. Run the 50 mV and 100 mV fixed-input ADC noise sweeps and the correspondingly
   slowed sine conversion-rate sweep.
4. Accept the new run directories explicitly in the analysis runner and plot
   the old and lower-bandwidth results separately or as a clearly labelled
   comparison.
5. Only after the short campaigns pass, repeat the ADC timing and ramp
   campaigns. Comparator and CDAC reacquisition is not an initial blocker.

The existing chip-level HDL21 and PEX ADC simulations drive the ADC pins
directly, so the PCB capacitor change does not invalidate them. A future
board-front-end simulation target should own AC response, transient settling,
and integrated-noise checks for `design/spice/sediff.sp`.

## Transfer-curve producer completion

The generated and extracted ADC views use 151 settled input values from
-750 mV through +750 mV in 10 mV steps, a 700 mV input common mode, and 10 MSPS
active conversion timing. Each simulation view produces one typed H5 file.
Netlist-only targets permit review before Spectre execution.

The initial physical transfer campaign targets ADC00 with 1,001 DC values from
-750 mV through +750 mV in 1.5 mV steps and 100 conversions per point. The
supplies and AWG remain enabled across the sweep, and only changed setpoints
are programmed. The analysis runner continues to select a completed physical
run directory manually after its results have been reviewed.

## Remaining flow gaps

- The sampler and standalone CDAC simulations still need raw-to-H5 converters
  before analysis can consume them.
- The THS4541 board-front-end SPICE model has no named simulation runner.
- `cdac_system_cap_mismatch` is currently routed beneath the ADC analysis
  output directory instead of a CDAC directory.
