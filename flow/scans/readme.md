# Basil API used by the FRIDA scans

## Scan development contracts

`flow/scans/runner.py` is the executable hardware-scan entry point. Each named
target owns its complete parameter recipe and output path, builds a flat list
of fully specified `*TbParams`, and hands those configurations to exactly one
of `scan_adc.scan`, `scan_comp.scan`, or `scan_cdac.scan`. The scan modules are
acquisition libraries, not command-line programs. A runner may define
`BASE_PATH`; campaign-specific directories, selections, and constants belong
inside the target that uses them.

Each parameter configuration creates one typed HDF5 measurement in a new
timestamped `build/scan_<kind>/<timestamp>/` directory. The file contains one
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

The scan scripts use three distinct interfaces:

1. Generic, low-level Basil support shared by many hardware blocks.
2. Block-specific Basil drivers for the FPGA and laboratory instruments.
3. FRIDA-local operations for protocols that are specific to this design.

Methods marked `†` are FRIDA Basil extensions, as defined in the footnote.

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
Similarly, `COMP_IDELAY_TAPS`, `COMP_IDELAY_LOAD`, and `COMP_IDELAY_RDY` name
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

## FRIDA-local scan support

These functions are not Basil APIs. They implement design-specific packing,
transactions, or analysis and should remain visibly distinct from direct
hardware-driver calls.

| Function | File | Role |
| --- | --- | --- |
| `convert_sample_rate_to_baud()` | `params.py` | Derive symbol rate from a requested active-conversion rate and the timing-pattern active span. |
| `convert_dac_caps_to_adc_weights()` | `scan_adc.py` | Convert physical CDAC weights C16..C1 into decision weights W16..W0. |
| `convert_params_to_seqgen_fmt()` | `seqgen.py` | Pack four parameterized timing strings and a caller-supplied one-bit-per-word RX_SEN string into raw 64-bit sequencer words. |
| `convert_params_to_spi_fmt()` | `scan_adc.py` | Pack one `AdcTbParams` configuration into the FRIDA chip's 180-bit slow-control image. |
| `convert_fastrx_words_to_adc()` / `convert_fastrx_words_to_comp()` | `fastrx.py` | Decode and validate ADC or one-bit comparator FastRX captures in a vectorized pass. |
| `calculate_fastrx_capture_alignment()` / `calculate_single_sample_fastrx_capture_alignment()` | `fastrx.py` | Calculate legal RX_SEN placement, serializer phase advance, and comparator IDELAY settings from stored timing strings and board delays. |
| `convert_dout_to_normalized_dout()` | `scan_adc.py` | Normalize one decoded weighted ADC result to the configured output-code range. |
| `write_scope_csv()` | `scope.py` | Persist aligned voltage and instrument-code columns from one raw scope acquisition. |
| `write_measurement()` / `read_measurement()` | `flow/analysis/io.py` | Persist and load one typed physical, behavioral, or SPICE measurement using the shared HDF5 schema. |
| `scope_records_to_adc_wave()` | `flow/analysis/io.py` | Convert aligned triggered scope records into the dense external ADC waveform section. |
| `analyze_adc_dynamic()` | `flow/analysis/adc.py` | Perform a four-parameter sine fit plus FFT analysis and report residual RMS, SNR, SNDR, THD, SFDR, and ENOB. |
| `analyze_adc_transfer()` / `analyze_adc_nonlinearity()` / `analyze_adc_code_distribution()` | `flow/analysis/adc.py` | Calculate typed static transfer, INL/DNL, and fixed-input code-distribution results. |
| `plot_adc_*()` / `plot_comp_*()` | `flow/analysis/plots.py` | Render typed measurements and their corresponding typed analysis results without loading files or recalculating metrics. |
| `select_pll_configuration()` | `plldrp.py` | Calculate a legal Si570 frequency and PLL divider for a requested symbol rate without hardware I/O. |
| `set_pll_divider()` | `plldrp.py` | Perform the GPIO2 request/acknowledge transaction and verify PLL lock and active-divider readback. |
| `find_crossings()` | `flow/analysis/measure.py` | Interpolate waveform threshold crossings directly from signal and time arrays; this is generic analysis, not scope control. |

The comparator-input IDELAY transaction is intentionally inline in
`scan_adc.py`: it reads the GPIO1 ready flag, sets the tap value, and pulses
the load bit. The adjacent block comment separates these visible Basil GPIO
operations from PLL and sequencer programming.

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
Every physical scope test uses one fixed MSO54 hookup: CH1 is the TDP3500
differential probe on the diffamp/ADC input, CH2 is the comparator clock, CH3
is the LOGIC sequencer clock, and CH4 is the comparator output. INIT and SAMP
remain part of the generated ASIC sequence but are not scope inputs. Tests
configure and download only the subset of these four channels that they use.
Saved hardware-test artifacts are grouped by test module and invocation under
`build/test_diffamp/<timestamp>`, `build/test_noise/<timestamp>`,
`build/test_fastrx/<timestamp>`, and `build/test_serdes/<timestamp>`.
Backend-neutral result I/O, numerical post-processing, and rendering live in
`flow/analysis`; none of these modules adds methods to the Basil hardware API.

`params.py` expands the full sweep into a flat `list[AdcTbParams]`; each item
produces exactly one `MeasAdcExt` HDF5 file. `map_board.yaml` maps its `board_id` to physical ADC
flavors, explicit CDAC weights, safe supply limits, input calibration, and
capture alignment. Each invocation creates a new timestamped directory under
`build/scan_adc/`. Each file contains native `/info`, `/param`, `/daq`, and
`/wave` groups; there is no separate CSV or manifest sidecar.

Each configuration is acquired in one uninterrupted sequencer/FastRX run.
After acquisition, `scan_adc.py` constructs one typed in-memory measurement
and writes it with `flow.analysis.io.write_measurement()`. Scope waveforms may
cover a representative conversion while `/daq` retains every FastRX result.

† Added to the Basil API by the FRIDA project. These implementations now live
in `libs/basil` and are called like normal Basil methods; they are not helpers
defined in `flow/scans`.
