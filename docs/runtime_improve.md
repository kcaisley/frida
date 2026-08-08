# Hardware scan runtime audit

The comparator/CDAC audit showed that slow scans were dominated by host-side instrument work and fixed sleeps, not FPGA conversion time. Profile complete points with `time.monotonic()` around instrument updates, settling, sequencer/FastRX capture, scope capture/download, and persistence. Record those durations in measurement metadata so a slow run can be diagnosed from HDF5 without repeating it.

Measured costs in the original path were approximately 2.24 s for one four-channel ASCII scope download, about 1 s each for several GPIB readbacks, and 4.5 s for nine fixed 0.5 s waits between ten 100-trial batches. Together these made a typical CDAC 1,000-trial point about 11.7 s even though its decision capture required only a fraction of a second.

The following changes were safe and broadly applicable:

- Initialize instruments once, keep outputs enabled, and use a setpoint-only update such as AWG offset after the initial full configuration.
- Order the sweep so slow common-mode or supply setpoints are outer loops. Change and read them only when their requested value changes.
- Program and verify SPI only when the complete register image changes. Retain the verification on every actual image change.
- Capture scope waveforms during commissioning, not at every decision-only point. Keep the timing model and one representative trace for every distinct sequence.
- Preserve ten proven 100-trial FastRX transactions for a 1,000-trial point, but omit host sleeps between batches for ordinary points. Keep one time-spread point per curve as a slow-drift checkpoint.
- Cache pure board-map, calibration, code-selection, and sequence calculations whose inputs have not changed.
- Stop fine-grid extension once coarse and fine stages give opposite 10%/90% outcomes at the same voltage. That is an analog epoch conflict, and more points cannot make the curve valid.
- Keep bounded millisecond polling around sequencer/FIFO completion. These waits normally return immediately and protect against missing hardware data; they were not the runtime bottleneck.

Do not trade measurement quality for speed. The audit rejected a single 900-trial sequencer burst after 900 requested trials returned 1,095 words. It also rejected 10 ms and 50 ms AWG input settling because coarse/fine P50 disagreed by 1.173 mV and 316.8 uV. The accepted 100 ms setting agreed within 8.4 uV. CDAC's 10 ms top-plate precondition, 85 ns sampling aperture, 100 uV grid, 1,000 fine trials, frame/identifier validation, loss checks, SPI readback, safety bounds, and `try`/`finally` shutdown remain mandatory.

For `scan_adc.py`, audit in this order:

1. Measure the wall time of scope download, each GPIB command/readback, full AWG reconfiguration, supply operations, SPI programming, fixed sleeps, FastRX capture, and HDF5 writing.
2. Move unchanged instrument setup and readbacks outside the per-point loop while keeping safety ordering visible at the call site.
3. Group variants by slow-changing hardware state, especially Vin_cm, supplies, clock configuration, ADC selection, and SPI image.
4. Decide which waveforms are commissioning evidence and which points need only digital output. Never remove a waveform required to validate a distinct timing sequence.
5. Benchmark a representative old/new pair. Require exact requested trials and contiguous frames, zero FastRX loss/SPI mismatch, and statistically equivalent transfer, P50, and noise results before accepting the faster path.

After these changes, ordinary 1,000-trial points measured about 0.19 s for CDAC and 0.18 s for comparator capture. One deliberate drift checkpoint per curve remains about 4.7 s.

Moving the fixed comparator grid into direct `AdcTbParams` and `CompTbParams` fields did not change production campaign point counts, trials, batching, waits, sequence timing, or the physical HDF5 parameter shape. Common-mode and sampling-noise construction remained 6,024 and 10,040 points; the fixed 0.800 V offset-only slice is 1,004 points and projects to about 3.7 minutes from the accepted 22-minute six-common-mode campaign.

## Analysis runtime follow-up

The first complete CDAC reduction used essentially one CPU core while NumPy worker threads stayed idle. The workload has independent file, curve, and ADC boundaries, so a later optimization can decode HDF5 files with a bounded worker pool, analyze curves or ADCs in separate processes, and render the four per-ADC plots independently before producing the comparison plot. Preserve deterministic curve ordering and byte-for-byte-equivalent numeric results where practical.

The main statistical aggregation uses NumPy arrays but repeatedly evaluates `decisions[inverse == index]` once per unique input. This rescans and copies the complete decision array for every voltage. Replace it with a single weighted `numpy.bincount` divided by the existing per-input counts, then benchmark equivalence. The per-measurement batch reconstruction and thousands of small HDF5/dataclass decodes are also Python-heavy; profile them separately before choosing process count. More BLAS threads alone will not help because this analysis has no large matrix kernel.

The 6,024-file fixed-grid common-mode reduction completed serially in 184.35 s and produced four three-format plots. This confirms that small-file decode is material but still far below capture time; use this dataset as a before/after benchmark for bounded file-level or ADC-level parallelism.

The 10,040-point complementary-CDAC sampling capture completed in about 35 minutes; ordinary points remained near 0.18 s and transition checkpoints near 4.68 s. Its serial merged reduction, including a 502-point repair source and later-point replacement, completed in 328.10 s. Use this larger dataset as the analysis parallelism benchmark: decoding and grouping dominate, while the 40 CDF fits and four plot renders are comparatively small.
