# Basil API used by the FRIDA scans

## Scan development contracts

`flow/scans/runner.py` is the executable hardware-scan entry point. Each named
target owns its complete parameter recipe and output path, builds a flat list
of fully specified `*TbParams`, and hands each configuration to its acquisition
function. ADC targets also pass `first`, `middle`, `last`, or `only` so
`scan_adc.scan` acquires exactly one H5 while preserving the powered bench
state between calls. The scan modules are acquisition libraries, not
command-line programs. A runner may define
`BASE_PATH`; campaign-specific directories, selections, and constants belong
inside the target that uses them.

Each parameter configuration creates one typed HDF5 measurement in a new
timestamped directory. ADC campaigns use
`build/scan_adc/<timestamp>_<target>/0000_capture.h5`, incrementing the capture
index for each measurement. ADC identity and all acquisition settings remain
in the HDF5. Comparator/CDAC paths retain `build/scan_<kind>/<timestamp>/`. The file contains one
logical measurement with native `/info`, `/param`, `/daq`, and `/wave` groups.
The HDF5 files themselves are the campaign record; do not add a manifest or a
second sweep-policy object beside them.

Keep Basil instrument calls, safety limits, output enables, resource lifetime,
and `try`/`finally` shutdown visible in the scan procedure. Extract helpers
only for pure calculations/data transformations or for atomic FRIDA protocols
that Basil does not expose, such as PLL handshakes, SPI packing, and FastRX
decoding. Do not wrap a short recognizable sequence of Basil calls merely to
shorten a scan function. When refactoring a sweep, preserve safety ordering,
requested trials, frame/identifier and loss validation, SPI readback, and the
waveforms needed to validate each distinct timing sequence.

Keep already-enabled supplies and stimulus outputs active while consecutive
parameter configurations request the same settings. Program only changed
setpoints. ADC runners issue an `abort` call if their loop is interrupted;
retain unconditional best-effort shutdown for final, single-point, abort, and
exception paths.

`scan_adc_noctl.scan()` uses manually supplied DC input and rails, while
controlling the FPGA and scope. It never controls the AWG or power supplies.
Each point arms the scope before FPGA start and saves INIT, COMP_OUT, COMP,
and LOGIC for the first retained conversion, after skipping startup conversions.
The existing scope-to-bit decoder compares its 17 decisions against FastRX;
HDF5 readbacks record the mismatch count, or an explicit invalid-comparison
status and error when the waveform cannot be decoded. A mismatch remains a
saved diagnostic result. Scope acquisition failures stop the scan.
The reference samples COMP_OUT at COMP rise plus 7/8 of a decision interval;
it is not a measurement of internal comparator or CDAC timing closure.

`adc_sequence_static` covers all 16 ADCs and all 65 named sequences at nominal
conversion rates 2/6/10 MSPS, with 100,000 conversions per point (3,120 captures).
`adc_sample_rate_static` covers ADC00–03 at 39 rates from 0.5 through 10 nominal MSPS in
0.25-MSPS steps, with 1,000 conversions per point. Its 4–5 sequence choices
remain a TODO; an empty selection fails before hardware is opened.
Both use 50 mV differential input and 700 mV common mode supplied manually.
Select completed directories explicitly for analysis; acquisition does not
change a study's pinned inputs or generate plots.

Names encode the length and interior
COMP/LOGIC words, including wraparound for four-symbol LOGIC pulses. The INIT
LOGIC marker remains one symbol; only the sixteen SAR update pulses are swept.
For these short programs, the returned B0--B16 data crosses the sequencer
memory boundary. Both scans wrap RX_SEN from the calibrated start word,
leaving all four ADC control lanes unchanged. One control period is repeated in the existing 256-byte
RAM. Once enough frames arrive, FastRX is disabled before the sequencer is
reset, so a held-high final RAM word cannot create spurious frames.
Unused physical RAM is cleared before START to keep RX disabled while idle.

All transported frames are checked before retaining exactly the requested
number of conversions. A leading partial receive frame is discarded if RX_SEN
wraps. INIT starts at symbol zero; no control-lane rotation or corresponding
startup-conversion discard is applied. Receiver alignment only selects RX_SEN
word placement and combined comparator IDELAY. A point requires explicit
settings or an exact characterized sequence/baud profile.
Readbacks record `capture_startup_frames`, `capture_startup_conversions`,
`capture_received_frames`, and each discarded `startup_fastrx_word_0`, `_1`,
etc. These prefix words plus `/daq/fastrx_word` retain the original frame
numbers. Additional complete frames collected during host stop latency are
validated and then omitted from the measurement.

The scan scripts use three distinct interfaces:

1. Generic, low-level Basil support shared by many hardware blocks.
2. Block-specific Basil drivers for the FPGA and laboratory instruments.
3. FRIDA-local operations for protocols that are specific to this design.

Methods marked `†` are FRIDA Basil extensions, as defined in the footnote.

## ADC acquisition families

All ADC selections are explicit inside their runner. Long campaigns retain the
reviewed subset beside a commented `adc_indices = tuple(range(16))` alternative.
Changing that selection requires no new function or command-line flag.

| Runner | Current acquisition |
| --- | --- |
| `adc_sequence_static` | All ADCs, all 65 sequences, 2/6/10 nominal MSPS: 3,120 captures with scope. |
| `adc_sample_rate_static` | ADC00–03, 39 rates, 4–5 sequences pending selection; scope at each point. |
| `adc_activity_noise` | ADC00 at three rates, with only itself or all 16 ADCs active: six captures. |
| `adc_transfer_curve` | ADC00, 1,001 known-voltage steps. |
| `adc_ramp_code_density` | ADC00--03, four long sawtooth captures. |

Nominal MSPS uses a fixed 160-symbol reference for every recipe: 2/6/10 MSPS
means 320/960/1600 MBd. Actual active conversion and repetition rates remain
separate saved quantities; no recipe-specific baud-rate adjustment is applied.

`adc_sequence_static()` accepts `adc_indices`, `nominal_conversion_rates_hz`,
`sequences`, and `conversions` keyword arguments for smaller comparisons.
`adc_sample_rate_static()` has no arguments. Its local sequence shortlist is
deliberately empty until the TODO is resolved.
Both require manually supplied input and 1.2 V rails. Actual repetition rates
are saved separately from active conversion rates because some sequences
include idle padding.

The target registry is local to `main`. Each runner retains its own visible
acquisition/abort loop. No shared lifecycle wrapper is introduced.

## Low-level Basil support

| API | Layer | Purpose | Origin |
| --- | --- | --- | --- |
| `Dut(map_path)` | `basil.dut.Dut` | Construct all transfer layers, hardware drivers, and register layers described by a YAML map. | Basil |
| `.init()` / `.close()` | `Dut` | Open, initialize, and close the mapped hardware interfaces. | Basil |
| `.wait_for_ready()` | `HardwareLayer` | Poll a block's `is_ready` property with timeout handling. | Basil |
| `register["FIELD"] = value` | `StdRegister` | Update a named field in the local register image. This does not access hardware until `.write()` is called. | Basil |
| `register["FIELD"].tovalue()` | `StdRegister` / `BitLogic` | Convert a named field from its bit representation to an integer. | Basil |
| `register.write()` | `StdRegister` | Pack the named fields and write the complete register through its hardware driver. | Basil |
| `register.read()` `†` | `StdRegister` | Read the complete hardware register and update all named fields. | FRIDA Basil extension |
| YAML-defined SCPI methods | `scpi` | Generate methods such as `set_voltage()` and `get_voltage()` from the selected instrument description. | Basil |

`StdRegister.read()` is important for `gpio1` and `gpio2`: call it before
inspecting hardware status fields. Assigning a field only changes the local
image; call `.write()` to transmit it.

## Block-specific Basil support

### FPGA data path

| Block | API used by the scans | Purpose | Origin |
| --- | --- | --- | --- |
| `sitcp_fifo` | `fifo["RESET"]`, `.get_data()` | Reset the streaming FIFO and receive packed FastRX words over SiTCP. Reading `RESET` performs the driver's reset action. | Basil |
| `seq_gen` | `.reset()`, `.start()`, `.set_size()`, `.set_clk_divide()`, `.set_repeat()`, `.set_en_ext_start()`, `.is_done()`, `.is_ready`, `.set_data()` | Program and run the sequencer memory. `is_ready` is a property; `is_done()` is a method. | Basil |
| `spi` | `.reset()`, `.start()`, `.set_size()`, `.set_data()`, `.get_data()`, `.wait_for_ready()` | Write and read the FRIDA chip's 180-bit slow-control register. | Basil |
| `gpio` | `.reset()`, `.set_data()`, `.get_data()` | Access a generic FPGA GPIO block. Named fields are supplied by the FRIDA `StdRegister` maps below. | Basil |
| `fast_spi_rx` | `.reset()`, `.set_en()`, `.get_en()`, `.get_lost_count()` | Enable comparator-data capture and inspect overflow state. | Basil |
| `fast_spi_rx` | `.get_size()` `†`, `.parse_word()` `†` | Read the firmware-defined capture width and unpack identifier, frame counter, and comparator bits. | FRIDA Basil extension |
| `i2c` | Indirect access through the `si570` hardware layer | Carry Si570 register transactions on the FPGA I2C master. | Basil |
| `si570` | `.frequency_change(frequency_mhz)`, `.read_registers()` | Program or inspect the external oscillator. | Basil |
| `si570` configuration | `base_addr`, `init.factory_frequency` `†` | Select the configured I2C address and factory calibration frequency instead of hard-coded values. | FRIDA Basil extension |

The serializer scripts use `daq["seq0"].set_data(memory)`. The register layer
named `seq0` is a legacy `TrackRegister`, but Basil delegates its undefined
`set_data()` method to the underlying `seq_gen` hardware driver. This writes
the prepared 64-bit memory image without invoking `TrackRegister.write()` or
its incompatible legacy bit/byte reversal.

### Laboratory instruments

| Instrument driver | API used by the scans | Purpose | Origin |
| --- | --- | --- | --- |
| `agilent33250a` | `.set_sin()`, `.set_DC()`, `.set_output_load()`, `.set_enable()` and their query methods | Configure and verify the ADC input stimulus. | Basil |
| `keithley_2400` | `.source_volt()`, `.set_voltage()`, `.set_voltage_range()`, `.set_current_limit()`, `.on()`, `.off()` and readback methods | Drive and measure the VDDA, VDDD, and VDDDAC rails. | Basil |
| `keithley_2400` | Current-sense autorange/range, NPLC, autozero, and voltage-range queries `†` | Select the low-noise current-measurement settings used for rail-power measurements. | FRIDA Basil extension |
| `agilent_e3634a` `†` | `.set_voltage()`, `.set_current_limit()`, `.set_voltage_range()`, `.set_enable()` and readback methods | Drive and verify the input-amplifier common-mode voltage. | FRIDA Basil extension |
| `tektronix_oscilloscope` | Acquisition, horizontal, vertical, bandwidth, and edge-trigger configuration methods | Configure the MSO54 capture. | Basil |
| `tektronix_oscilloscope` | `.get_waveforms(channels)` and `response_value()` `†` | Capture coherent multi-channel waveforms and normalize terse or verbose query responses. | FRIDA Basil extension |
| `tektronix_oscilloscope` | Channel-selectable trigger level and corrected channel termination commands `†` | Configure the trigger and input termination for a selected channel. | FRIDA Basil extension |

### FRIDA register naming

The names `RST_B`, `AMP_EN`, `RX_LOOPBACK`, `SPI_LOOPBACK`, `DBG_FIFO`,
`RX_TIEHIGH`, `SEQ_START`, and `RX_EN_MUX` are aliases for bits in `gpio0`.
Similarly, `COMP_IDELAY_TAPS`, `COMP_IDELAY_LOAD`, `COMP_IDELAY_RDY`,
`COMP_IDELAY_TWO_STAGE`, and `COMP_IDELAY_ACTUAL` name
the fields in `gpio1`; `REQUEST_N`, `APPLY_TOGGLE`, `APPLIED_TOGGLE`, `BUSY`,
`LOCKED`, `ERROR`, and `ACTIVE_N` name the fields in `gpio2`. These aliases are
declared in `map_fpga.yaml` with Basil's generic `StdRegister` layer. They do
not add new methods to the Basil API.

The `gpio1` names implement the comparator-input IDELAY load transaction. The
`gpio2` names implement the PLL divider request, acknowledgement, lock, error,
and active-divider readback. The sequencer map also names its capture-control
bits `RX_EN` and `RX_TEST`; `RX_EN` is the legacy map name for the firmware's
`RX_SEN` signal.

For the current clock hardware, `D = 1` and `M = 8` are fixed, the Si570
provides `FIN = 100..200 MHz`, and GPIO2 selects `N = 2..20`:

```text
sequencer clock = 2*FIN/N
serializer clock = 8*FIN/N
DDR symbol rate  = 16*FIN/N
```

Conversion rate uses the INIT rising edge through the final COMP falling edge,
rounded up to the end of its eight-symbol word relative to INIT. A common phase
advance does not change this duration. At 1.6 Gbaud, the original recipe converts
in 100 ns (10 MSPS), then repeats every 160 ns (6.25 MHz). The 160-symbol duty
recipes convert and repeat every 100 ns. Baud is calculated from each selected
recipe, so the extended-COMP recipe uses 1.68 Gbaud when requested at 10 MSPS.

Existing typed analysis fields retain their names: `active_conversion_rate_hz`
is the conversion rate; `sample_rate_hz` is the full repetition rate, which is
also the rate used for spectral analysis.

## FRIDA-local scan support

These functions are not Basil APIs. They implement design-specific packing,
transactions, or analysis and should remain visibly distinct from direct
hardware-driver calls.

| Function | File | Role |
| --- | --- | --- |
| `convert_conversion_rate_to_baud()` | `params.py` | Derive symbol rate from the conversion rate: INIT rise to final COMP fall, rounded to the end of its eight-symbol word. The full pattern determines the repetition interval. |
| `convert_dac_caps_to_adc_weights()` | `scan_adc.py` | Convert C0-first physical CDAC weights into chronological B0..B16 decision weights. |
| `convert_params_to_seqgen_fmt()` | `seqgen.py` | Pack four parameterized timing strings and a caller-supplied one-bit-per-word RX_SEN string into raw 64-bit sequencer words. |
| `convert_params_to_spi_fmt()` | `scan_adc.py` | Pack one `AdcTbParams` configuration into the FRIDA chip's 180-bit slow-control image. |
| `convert_fastrx_words_to_adc()` / `convert_fastrx_words_to_comp()` | `fastrx.py` | Decode and validate ADC or one-bit comparator FastRX captures in a vectorized pass. |
| `select_fastrx_capture_settings()` | `fastrx.py` | Select explicit combined delay and SEN word, or an exact characterized sequence/baud profile. Never rotate ADC controls. |
| `program_comp_delay()` | `fastrx.py` | Verify the two-stage firmware ABI and readiness, load the combined tap request, and verify the actual delay counters. |
| `convert_dout_to_normalized_dout()` | `scan_adc.py` | Normalize one decoded weighted ADC result to the configured output-code range. |
| `write_scope_csv()` | `scope.py` | Persist aligned voltage and instrument-code columns from one raw scope acquisition. |
| `write_measurement()` / `read_measurement()` | `flow/analysis/io.py` | Persist and load one typed physical, behavioral, or SPICE measurement using the shared HDF5 schema. |
| `scope_records_to_adc_wave()` | `scope.py` | Convert aligned triggered scope records into the dense external ADC waveform section. |
| `analyze_adc_dynamic()` | `flow/analysis/adc.py` | Perform a four-parameter sine fit plus FFT analysis and report residual RMS, SNR, SNDR, THD, SFDR, and ENOB. |
| `analyze_adc_transfer()` / `analyze_adc_nonlinearity()` / `analyze_adc_code_distribution()` | `flow/analysis/adc.py` | Calculate typed static transfer, INL/DNL, and fixed-input code-distribution results. |
| `plot_adc_*()` / `plot_comp_*()` | `flow/analysis/plots.py` | Render typed measurements and their corresponding typed analysis results without loading files or recalculating metrics. |
| `select_pll_configuration()` | `plldrp.py` | Calculate a legal Si570 frequency and PLL divider for a requested symbol rate without hardware I/O. |
| `set_pll_divider()` | `plldrp.py` | Perform the GPIO2 request/acknowledge transaction and verify PLL lock and active-divider readback. |
| `find_crossings()` | `flow/analysis/measure.py` | Interpolate waveform threshold crossings directly from signal and time arrays; this is generic analysis, not scope control. |

The shared `program_comp_delay()` transaction verifies the two-stage ABI and
ready flag, loads both counters, clears the load strobe, and checks the actual
counter sum. Acquisition stop/start ordering remains visible in each scan.

The three mapped GPIO blocks have state-restoring hardware tests:

```bash
uv run pytest -q -s -m hw flow/scans/test_gpio.py
```

The sequencer-to-FastRX path has a separate exact-bit hardware test. It routes
a recognizable 17-bit sequence through the FPGA-internal loopback, then checks
the received bit order, frame counters, word count, and overflow counter:

```bash
uv run pytest -q -s -m hw flow/scans/test_fastrx.py
```

`scope.py` contains capture synchronization around the Basil scope driver.
ADC/comparator scope tests use the standard MSO54 hookup: CH1 is the TDP3500
differential probe on the diffamp/ADC input, CH2 is the comparator clock, CH3
is the LOGIC sequencer clock, and CH4 is the comparator output. INIT and SAMP
remain part of the generated ASIC sequence but are not scope inputs. Tests
configure and download only the subset of these four channels that they use.
The dedicated four-sequence clock test uses a different, explicit hookup:
differential probes on PCB INIT/SAMP/COMP/LOGIC at CH1/2/3/4. With manually
set supplies and input, run only:

```bash
uv run pytest -q -s -m hw flow/scans/test_serdes.py::test_adc_sequence_waveforms
```

It programs the four comparison recipes and 56 duty-cycle recipes at 1.6 GBd and saves raw CSV captures,
four-axis PDFs (160 ns raw record, 120 ns overview and pulse detail), and JSON edge
observations beneath `build/test_serdes/<timestamp>/<case>/`. Its edge check
uses A-then-B edge triggering on CH1: A detects the first INIT and B captures
the next rising edge (event count one). It compares all active edges of that
second conversion against the named rows
at differential zero crossings, within 0.25 ns relative to measured INIT.
Manual horizontal mode uses the instrument's minimum 1000 samples at 6.25 GS/s
for a 160 ns raw record. The scope zoom and overview plot show 120 ns, including
3.4 ns before INIT. The end of the 256-symbol recipe's idle pause is
outside that window. The scope keeps the capture settings and stopped waveform
after each case; prior settings are not restored. This is a PCB clock
check, not validation of the ASIC's internal clock receivers or SAR operation.
The existing `test_serdes_rates` test retains its original hookup and SMU
control; select the appropriate test explicitly rather than running the module
with either hookup.

Saved hardware-test artifacts are grouped by test module and invocation under
`build/test_diffamp/<timestamp>`, `build/test_noise/<timestamp>`,
`build/test_fastrx/<timestamp>`, and `build/test_serdes/<timestamp>`.
Backend-neutral result I/O, numerical post-processing, and rendering live in
`flow/analysis`; none of these modules adds methods to the Basil hardware API.

`params.py` expands the full sweep into a flat `list[AdcTbParams]`. The runner
iterates that list and each call to `scan_adc.scan` produces exactly one
`MeasAdcExt` HDF5 file. `map_board.yaml` maps its `board_id` to physical ADC
flavors, explicit CDAC weights, safe supply limits, input calibration, and
capture alignment. The first call creates a new timestamped directory under
`build/scan_adc/`. Each file contains native `/info`, `/param`, `/daq`, and
`/wave` groups; there is no separate CSV or manifest sidecar.

Each configuration is acquired in one uninterrupted sequencer/FastRX run.
After acquisition, `scan_adc.py` constructs one typed in-memory measurement
and writes it with `flow.analysis.io.write_measurement()`. Scope waveforms may
cover a representative conversion while `/daq` retains every FastRX result.

† Added to the Basil API by the FRIDA project. These implementations now live
in `libs/basil` and are called like normal Basil methods; they are not helpers
defined in `flow/scans`.

### Two-stage comparator capture settings

FastRX and the sequencer still share SEQ_CLK (200 MHz at 1.6 GBd).
The comparator data passes through two IDELAYE2 blocks; the second uses
DATAIN from fabric. No control pattern is rotated or retimed.

Set `AdcScanParams.fastrx_capture` to the two-field dataclass for calibration:

```python
from dataclasses import replace
from flow.scans.fastrx import FastRxCapture

params = replace(params, fastrx_capture=FastRxCapture(comp_delay_taps=36, rx_sen_start_word=9))
```

Taps are 0..62 and the SEN word is zero-based. Otherwise scans require one exact entry in the board's
`fastrx_capture_settings`: full catalogue `sequence` name, `symbol_rate_bps`,
`comp_delay_taps`, and `rx_sen_start_word`. Missing or ambiguous profiles fail
before instruments are opened. Only scope-validated profiles for the installed bitstream belong in this table;
old one-stage values are invalid.
Custom comparator/CDAC sequences can use the same explicit parameters.

Firmware splits total taps N into floor(N/2) and ceil(N/2), with nominal
78.125 ps increments at the fixed 200 MHz IDELAYCTRL reference. Program while
capture is stopped. `program_comp_delay()` checks the two-stage ABI before
writing and verifies the actual counter sum after loading. Metadata stores
`comp_delay_taps`, `comp_delay_stages=2`, and `rx_sen_start_word`; it no longer
claims analytical setup/hold margins. Characterize the complete routed path
and first/last conversion framing with scope comparison before accepting a
profile. Recharacterize after bitstream changes affecting this path.

New scope comparisons sample at COMP rise + characterized link delay + half
one decision interval. A fixed 7/8-period reference can precede comparator
arrival at 1.6 GBd. The link-delay value is saved in HDF5 as
`scope_comp_out_delay_s`; old files without it keep the legacy analysis phase.
This scope reference is independent of the FPGA tap setting, so it can still
identify incorrect receive alignment. It is not a model of the FastRX sample
instant. The input path's fabric routing remains part of hardware calibration.
