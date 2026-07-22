# Basil API used by the FRIDA scans

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
| `convert_sample_rate_to_baud()` | `scan_adc.py` | Convert the nominal ADC sample rate to the required DDR symbol rate. |
| `add_fastrx_capture_window()` | `scan_adc.py` | Place the 17-bit FastRX capture window in a sequencer pattern. |
| `convert_dict_to_seqgen_fmt()` | `scan_adc.py` | Pack INIT, SAMP, COMP, LOGIC, RX_SEN, and RX_TEST into raw 64-bit sequencer words. |
| `spi_config_to_bytes()` | `scan_adc.py` | Pack the FRIDA chip's 180-bit slow-control image in wire order. |
| `convert_fastrx_to_bout_and_dout()` / `convert_dout_to_normalized_dout()` | `scan_adc.py` | Decode FastRX comparator decisions and normalize the weighted ADC result. |
| `select_pll_configuration()` | `plldrp.py` | Calculate a legal Si570 frequency and PLL divider for a requested symbol rate without hardware I/O. |
| `set_pll_divider()` | `plldrp.py` | Perform the GPIO2 request/acknowledge transaction and verify PLL lock and active-divider readback. |
| `find_crossings()` | `flow/circuit/measure.py` | Analyze waveform threshold crossings; this is generic analysis, not scope control. |

The comparator-input IDELAY transaction is intentionally inline in
`scan_adc.py`: it reads the GPIO1 ready flag, sets the tap value, and pulses
the load bit. The adjacent block comment separates these visible Basil GPIO
operations from PLL and sequencer programming.

The three mapped GPIO blocks have state-restoring hardware tests:

```bash
uv run pytest -q -s -m hw flow/scans/test_gpio.py
```

`scope.py` contains capture synchronization around the Basil scope driver, and
`plot.py` contains CSV and plotting support. Neither module adds methods to the
Basil hardware API.

† Added to the Basil API by the FRIDA project. These implementations now live
in `libs/basil` and are called like normal Basil methods; they are not helpers
defined in `flow/scans`.
