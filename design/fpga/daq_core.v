// FRIDA DAQ Core
//
// Basil-based core module for the FRIDA ADC test chip DAQ system.
// Instantiates the functional blocks needed to control the chip
// and read back data:
//
//   1. seq_gen      - Sequencer generating 6 output signals:
//                     [0-3] LVDS clocks (CLK_INIT, CLK_SAMP, CLK_COMP, CLK_LOGIC)
//                     [4]   clk_comp_cap - capture clock for fast_spi_rx
//                     [5]   sen_comp - frame enable for fast_spi_rx
//   2. spi          - SPI master for 180-bit chip configuration register
//                     (SPI_SCLK, SPI_SDI, SPI_SDO, SPI_CS_B)
//   3. gpio         - GPIO for PCB control signals (RST_B, AMPEN_B)
//   4. pulse_gen    - Pulse generator for triggering the sequencer
//   5. fast_spi_rx  - COMP_OUT receiver using basil fast_spi_rx module
//
// Address map (matches map_fpga.yaml):
//   0x8000      - bram_fifo control  (instantiated at top level)
//   0x80000000  - bram_fifo data     (instantiated at top level)
//   0x10000     - seq_gen
//   0x20000     - spi
//   0x30000     - gpio
//   0x40000     - pulse_gen
//   0x50000     - fast_spi_rx

`timescale 1ns / 10ps

// Basil functional modules (direct children of daq_core)
`include "seq_gen/seq_gen.v"
`include "spi/spi.v"
`include "gpio/gpio.v"
`include "pulse_gen/pulse_gen.v"
`include "fast_spi_rx/fast_spi_rx.v"

module daq_core #(
    parameter integer ABUSWIDTH = 32
) (
    // Bus interface (directly from rbcp_to_bus / SiTcp)
    input wire                 BUS_CLK,
    input wire                 BUS_RST,
    input wire [ABUSWIDTH-1:0] BUS_ADD,
    inout wire [          7:0] BUS_DATA,
    input wire                 BUS_RD,
    input wire                 BUS_WR,

    // Sequencer clock input (directly from PLL, no division)
    input wire SEQ_CLK,  // 200 MHz sequencer clock

    // Sequencer outputs -> LVDS transmitters on PCB
    // Active sequencer tracks directly drive the 4 LVDS clock pairs
    output wire CLK_INIT,  // DAC initialization pulse
    output wire CLK_SAMP,  // Sample-and-hold trigger
    output wire CLK_COMP,  // Comparator clock (200 MHz toggle)
    output wire CLK_LOGIC, // SAR logic clock (200 MHz toggle, 2.5ns delayed)

    // SPI interface -> chip carrier PCB
    input  wire SPI_CLK,   // SPI shift clock
    output wire SPI_SCLK,  // SPI clock to chip
    output wire SPI_SDI,   // SPI data to chip (MOSI)
    input  wire SPI_SDO,   // SPI data from chip (MISO)
    output wire SPI_CS_B,  // SPI chip select (active low)

    // GPIO -> PCB control signals
    output wire RST_B,   // Chip reset (active low)
    output wire AMPEN_B, // Input amplifier enable (active low)

    // comp_out data -> bram_fifo (instantiated at top level)
    // The fast_spi_rx module captures the 1-bit comparator output stream,
    // packs it into 32-bit words, and presents them as a FIFO source.
    output wire [31:0] FIFO_DATA_OUT,
    input  wire        FIFO_READ_NEXT,
    output wire        FIFO_EMPTY,

    // Comparator output from LVDS receiver
    input wire COMP_OUT,

    // Global reset (independent of BUS_RST, e.g. PLL not locked)
    input wire RESET,

    // LED output
    output wire [7:0] LED_OUT

);

    // Address map (matching map_fpga.yaml)
    localparam integer SeqGenBaseAddr = 32'h10000;
    localparam integer SeqGenHighAddr = 32'h1FFFF;

    localparam integer SpiBaseAddr = 32'h20000;
    localparam integer SpiHighAddr = 32'h200FF;

    localparam integer GpioBaseAddr = 32'h30000;
    localparam integer GpioHighAddr = 32'h300FF;

    localparam integer PulseGenBaseAddr = 32'h40000;
    localparam integer PulseGenHighAddr = 32'h400FF;

    localparam integer FastSpiRxBaseAddr = 32'h50000;
    localparam integer FastSpiRxHighAddr = 32'h500FF;

    // Combined reset
    wire rst;
    assign rst = BUS_RST | RESET;


    // 1. Sequencer (seq_gen)
    // Generates the 8-track timing waveform loaded from the host.
    // seq_out[0] = CLK_INIT       - DAC initialization pulse
    // seq_out[1] = CLK_SAMP       - Sample-and-hold trigger
    // seq_out[2] = CLK_COMP       - Comparator clock
    // seq_out[3] = CLK_LOGIC      - SAR logic clock
    // seq_out[4] = fastrx_clk        - Capture clock for fast_spi_rx SCLK
    // seq_out[5] = fastrx_en          - Frame enable for fast_spi_rx SEN
    // seq_out[6] = fastrx_test_data   - Loopback test data for fast_spi_rx
    // seq_out[7] = unused
    wire [7:0] seq_out;
    wire pulse_out;  // from pulse_gen, triggers sequencer start

    // LVDS clock outputs to chip
    assign CLK_INIT         = seq_out[0];
    assign CLK_SAMP         = seq_out[1];
    assign CLK_COMP         = seq_out[2];
    assign CLK_LOGIC        = seq_out[3];

    // Capture control signals
    assign fastrx_clk       = seq_out[4];
    assign fastrx_en        = seq_out[5];
    assign fastrx_test_data = seq_out[6];

    seq_gen #(
        .BASEADDR (SeqGenBaseAddr),
        .HIGHADDR (SeqGenHighAddr),
        .ABUSWIDTH(ABUSWIDTH),
        .MEM_BYTES(8192),
        .OUT_BITS (8)
    ) inst_seq_gen (
        .BUS_CLK (BUS_CLK),
        .BUS_RST (rst),
        .BUS_ADD (BUS_ADD),
        .BUS_DATA(BUS_DATA),
        .BUS_RD  (BUS_RD),
        .BUS_WR  (BUS_WR),

        .SEQ_EXT_START(pulse_out),
        .SEQ_CLK      (SEQ_CLK),
        .SEQ_OUT      (seq_out)
    );


    // 2. SPI Master
    // Drives the 180-bit configuration shift register on the FRIDA chip.
    // SEN active-low directly maps to SPI_CS_B.
    // SPI loopback (GPIO bit 3): when enabled, SDO reads back from SDI
    // instead of the chip's SDO pin.  The SDI signal still drives the chip
    // only the receive path is redirected.  This lets you verify the
    // FPGA-to-chip SPI link independently.
    wire spi_sen;
    wire spi_loopback_en;  // assigned in GPIO section below
    wire spi_sdo_int;
    assign spi_sdo_int = spi_loopback_en ? SPI_SDI : SPI_SDO;
    assign SPI_CS_B    = ~spi_sen;  // SEN is active-high enable, CS_B is active-low

    spi #(
        .BASEADDR (SpiBaseAddr),
        .HIGHADDR (SpiHighAddr),
        .ABUSWIDTH(ABUSWIDTH),
        .MEM_BYTES(32)            // 256 bits > 180 bits needed
    ) inst_spi (
        .BUS_CLK (BUS_CLK),
        .BUS_RST (rst),
        .BUS_ADD (BUS_ADD),
        .BUS_DATA(BUS_DATA),
        .BUS_RD  (BUS_RD),
        .BUS_WR  (BUS_WR),

        .SPI_CLK(SPI_CLK),

        .SCLK     (SPI_SCLK),
        .SDI      (SPI_SDI),
        .SDO      (spi_sdo_int),
        .EXT_START(1'b0),

        .SEN(spi_sen),
        .SLD()
    );


    // 3. GPIO
    // Bit 0: RST_B               - Chip reset (active low)
    // Bit 1: AMPEN_B             - Input amplifier enable (active low)
    // Bit 2: fastrx_loopback_en  - fast_spi_rx loopback test mode
    // Bit 3: spi_loopback_en     - SPI SDO loopback (reads SDI instead of chip SDO)
    wire [3:0] gpio;
    assign RST_B              = gpio[0];  // Active-low board reset
    assign AMPEN_B            = ~gpio[1];  // Active-low amp enable (gpio=1 → amp on)
    assign fastrx_loopback_en = gpio[2];  // Fast RX loopback test enable
    assign spi_loopback_en    = gpio[3];  // SPI loopback test enable

    gpio #(
        .BASEADDR    (GpioBaseAddr),
        .HIGHADDR    (GpioHighAddr),
        .ABUSWIDTH   (ABUSWIDTH),
        .IO_WIDTH    (4),
        .IO_DIRECTION(4'hF),          // All outputs
        .IO_TRI      (0)
    ) inst_gpio (
        .BUS_CLK (BUS_CLK),
        .BUS_RST (rst),
        .BUS_ADD (BUS_ADD),
        .BUS_DATA(BUS_DATA),
        .BUS_RD  (BUS_RD),
        .BUS_WR  (BUS_WR),

        .IO(gpio)
    );

    // 4. Pulse Generator
    // Generates a single trigger pulse to start the sequencer.
    // Can be started from the host via register write.
    pulse_gen #(
        .BASEADDR (PulseGenBaseAddr),
        .HIGHADDR (PulseGenHighAddr),
        .ABUSWIDTH(ABUSWIDTH)
    ) inst_pulse_gen (
        .BUS_CLK (BUS_CLK),
        .BUS_RST (rst),
        .BUS_ADD (BUS_ADD),
        .BUS_DATA(BUS_DATA),
        .BUS_RD  (BUS_RD),
        .BUS_WR  (BUS_WR),

        .PULSE_CLK(SEQ_CLK),
        .EXT_START(1'b0),
        .PULSE    (pulse_out)
    );


    // 5. COMP_OUT Receiver (fast_spi_rx)
    // Captures the COMP_OUT stream using basil's fast_spi_rx module.
    // This replaces the hand-rolled shift register + FIFO implementation.
    //
    // Output format (32-bit words):
    //   [31:28] IDENTIFIER (4'b0001 by default)
    //   [27:16] Frame counter (12 bits, increments on SEN falling edge)
    //   [15:0]  Captured data (16 bits of comp_out samples)
    //
    // For 17-bit ADC conversions:
    //   - First 16 bits create one complete FIFO word
    //   - Remaining 1 bit creates a partial word on SEN falling edge
    wire fastrx_en;
    wire fastrx_test_data;
    wire fastrx_loopback_en;  // Driven by GPIO block bit 2
    wire fastrx_clk;  // Driven by sequencer output 4
    wire fastrx_in;  // Input from comp or sequencer test data (depending on loopback)
    assign fastrx_in = fastrx_loopback_en ? fastrx_test_data : COMP_OUT;

    fast_spi_rx #(
        .BASEADDR  (FastSpiRxBaseAddr),
        .HIGHADDR  (FastSpiRxHighAddr),
        .ABUSWIDTH (ABUSWIDTH),
        .IDENTIFIER(4'b0001)             // Only block which writes to shared FIFO
    ) inst_fast_spi_rx (
        .BUS_CLK (BUS_CLK),
        .BUS_RST (rst),
        .BUS_ADD (BUS_ADD),
        .BUS_DATA(BUS_DATA),
        .BUS_RD  (BUS_RD),
        .BUS_WR  (BUS_WR),

        .SCLK(fastrx_clk),
        .SDI (fastrx_in),
        .SEN (fastrx_en),

        .FIFO_READ (FIFO_READ_NEXT),
        .FIFO_EMPTY(FIFO_EMPTY),
        .FIFO_DATA (FIFO_DATA_OUT)
    );


    // 6. LEDs: All 8 LEDs set to high
    assign LED_OUT = 8'b11111111;

endmodule
