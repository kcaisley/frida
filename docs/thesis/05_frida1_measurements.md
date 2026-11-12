# FRIDA-1 silicon measurements {#sec-frida-1-silicon-measurements}

## Measurement setup and readout validation {#sec-measurement-setup-and-readout-validation}

### Test board, input drive, references, and clock distribution

[Section explaining test board, input drive, references, and clock distribution.]

### DAQ system, FastRX capture, and code decoding

[Section explaining DAQ system, FastRX capture, and code decoding.]

### Input-source and differential-amplifier noise

[Section explaining input-source and differential-amplifier noise.]

### Channel-to-code alignment

[Section explaining channel-to-code alignment.]

### Fixed-input tests with and without the amplifier

[Section explaining fixed-input tests with and without the amplifier.]

## Sampling-switch characterization {#sec-sampling-switch-characterization}

### Track-versus-hold noise and offset separation

[Section explaining track-versus-hold noise and offset separation.]

### Acquisition time and input-dependent settling

[Section explaining acquisition time and input-dependent settling.]

## Comparator measurements {#sec-comparator-measurements}

### Input-referred noise

#### Sampling-duration and clock-phase dependence

[Section explaining sampling-duration and clock-phase dependence.]

### Decision errors and metastability

#### Error probability versus input overdrive and evaluation time

[Section explaining error probability versus input overdrive and evaluation time.]

#### Reset and output-latch retention checks

[Section explaining reset and output-latch retention checks.]

### Kickback and CDAC-state dependence

[Section explaining kickback and CDAC-state dependence.]

### Power consumption

[Section explaining power consumption.]

## CDAC characterization {#sec-cdac-characterization}

### Capacitor mismatch

#### Ramp-based and comparator A/B weight extraction

[Section explaining ramp-based and comparator A/B weight extraction.]

#### Measured weights versus extracted mismatch models

[Section explaining measured weights versus extracted mismatch models.]

### Parasitic capacitance and transfer gain

[Section explaining parasitic capacitance and transfer gain.]

### Initialization state and common-mode trajectory

[Section explaining initialization state and common-mode trajectory.]

### Power consumption

[Section explaining power consumption.]

## Static nonlinearity {#sec-static-nonlinearity}

### Low-noise ramp, full-scale range, and transfer gain

[Section explaining low-noise ramp, full-scale range, and transfer gain.]

### INL and DNL before and after calibration

[Section explaining INL and DNL before and after calibration.]

## Fixed-input noise and channel variation {#sec-fixed-input-noise-and-channel-variation}

### Code-density distributions across all channels

[Section explaining code-density distributions across all channels.]

### Sampling-rate dependence of noise and offset

[Section explaining sampling-rate dependence of noise and offset.]

## Calibration methods {#sec-calibration-methods}

### Capacitor-weight estimation and repeatability

[Section explaining capacitor-weight estimation and repeatability.]

### Noise and linearity after weight correction

[Section explaining noise and linearity after weight correction.]

## Sampling rate and distortion {#sec-sampling-rate-and-distortion}

Preliminary prototype measurements indicate approximately 488–494 µW at 10 MS/s and a 1.2 V supply.

### ENOB and distortion versus input frequency and rate

[Section explaining ENOB and distortion versus input frequency and rate.]

### Continuous 100 ns operation and acquisition-chain checks

[Section explaining continuous 100 ns operation and acquisition-chain checks.]

## Timing optimization of control sequence {#sec-timing-optimization-of-control-sequence}

### Comparator and logic clock duty-cycle sweep

[Section explaining comparator and logic clock duty-cycle sweep.]

### Sampling gap, comparator reset, and CDAC-settling margins

[Section explaining sampling gap, comparator reset, and CDAC-settling margins.]

### Redundant versus minimum-cycle error rates

[Section explaining redundant versus minimum-cycle error rates.]

### Synchronized versus independent channel clocks

[Section explaining synchronized versus independent channel clocks.]
