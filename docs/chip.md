# ADC Test Chip Design Plan

## ADC Test Chip IO

| Pin Name | Pad Type | Pin Purpose |
|----------|----------|-------------|
| `seq_init_p` | LVDS RX | Sequencing: DAC initialization |
| `seq_init_n` | LVDS RX | Sequencing: DAC initialization |
| `seq_samp_p` | LVDS RX | Sequencing: Sample phase control |
| `seq_samp_n` | LVDS RX | Sequencing: Sample phase control |
| `seq_cmp_p` | LVDS RX | Sequencing: Comparator timing |
| `seq_cmp_n` | LVDS RX | Sequencing: Comparator timing |
| `seq_logic_p` | LVDS RX | Sequencing: SAR logic timing |
| `seq_logic_n` | LVDS RX | Sequencing: SAR logic timing |
| `vdd_a` | Power | Analog supply positive |
| `vss_a` | GND | Analog supply negative |
| `vdd_d` | Power | Digital supply positive |
| `vss_d` | GND | Digital supply negative |
| `vdd_io` | Power | I/O supply positive |
| `vss_io` | GND | I/O supply negative |
| `vdd_dac` | Power | DAC supply positive |
| `vss_dac` | GND | DAC supply negative |
| `spi_sclk` | CMOS Input | SPI serial clock |
| `spi_sdi` | CMOS Input | SPI device input (MOSI) |
| `spi_sdo` | CMOS Output | SPI master output (MISO) |
| `spi_cs_b` | CMOS Input | Chip select (shift in low, load on rising edge) |
| `vin_p` | Analog | Analog input positive |
| `vin_n` | Analog | Analog input negative |
| `comp_out_p` | LVDS TX | Data output positive |
| `comp_out_n` | LVDS TX | Data output negative |
| `reset_b` | CMOS Input | Global reset (active low, set all regs = 0) |

**Total: 25 pins**

## SPI Config

![test](images/wavetest.svg)

## SPI Configuration Register (65 bits)

| Bit Field | Width | Purpose | Notes |
|-----------|-------|---------|-------|
| `chan_en[15:0]` | 16 | Channel enable | Arbitrary number of 1s allowed.<br>One bit routed to each of 16 ADCs. |
| `chan_sel[15:0]` | 16 | Channel select | Must be one-hot encoded.<br>One bit routed to each of 16 ADCs. |
| `dac_init[M-1:0]` | M | DAC initial values | Initial values for each DAC bit.<br>All M bits routed to each ADC. |
| `manual` | 1 | Manual/Auto mode | Controls DAC update source:<br>0 = comparator output,<br>1 = `dac_init` register.<br>Routed to all ADCs. |
| **Total bits:** | | **65** | |

**Register Layout:**
`[64] manual | [63:48] dac_init[15:0] | [47:32] chan_sel[15:0] | [31:16] chan_en[15:0]`

## ADC Operation Modes

| Mode | Channels Selected | Channels Enabled | DAC Init Setting | Manual Mode | Notes/Purpose |
|------|-------------------|------------------|------------------|-------------|---------------|
| 1 | One channel (one-hot) | One channel (single bit) | Conventional, Monotonic, or BSS mode | Off | Normal ADC characterization |
| 2 | One channel (one-hot) | All channels (all bits set) | Conventional, Monotonic, or BSS mode | Off | Characterizing impact of VREF noise |
| 3 | One channel (one-hot) | One channel (single bit) | Dynamically updated externally | On | Calibration mode: external control of DAC state based on COMP output |

**DAC Init Modes:**
- **Conventional:** Standard binary weighted DAC initialization
- **Monotonic:** Ensures monotonic DAC behavior
- **BSS:** Binary Scaled Segmented DAC initialization

## Channel Parameter Combinations

**Design Space Exploration:**

| Parameter | Options |
|-----------|---------|
| N:M Ratio | 12:17, 10:13 |
| Coarse-Fine Architecture | Cap. Difference, Vref RDAC Scaling, Bridge Capacitor |
| Total Capacitance (Ctot) | 1pF, 2pF |

**All Combinations (2 × 3 × 2 = 12 total):**

| Config | N:M | Coarse-Fine Architecture | Ctot |
|--------|-----|-------------------------|------|
| 1 | 12:17 | Cap. Difference | 1pF |
| 2 | 12:17 | Cap. Difference | 2pF |
| 3 | 12:17 | Vref RDAC Scaling | 1pF |
| 4 | 12:17 | Vref RDAC Scaling | 2pF |
| 5 | 12:17 | Bridge Capacitor | 1pF |
| 6 | 12:17 | Bridge Capacitor | 2pF |
| 7 | 10:13 | Cap. Difference | 1pF |
| 8 | 10:13 | Cap. Difference | 2pF |
| 9 | 10:13 | Vref RDAC Scaling | 1pF |
| 10 | 10:13 | Vref RDAC Scaling | 2pF |
| 11 | 10:13 | Bridge Capacitor | 1pF |
| 12 | 10:13 | Bridge Capacitor | 2pF |

**Note:** Each configuration can be implemented in separate ADC channels for direct comparison.