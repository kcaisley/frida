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
//
// Based on: obelix1-daq/firmware/src/obelix1_core.v

`timescale 1ns / 10ps

// Basil utility modules (transitive deps of functional modules below)
`include "utils/bus_to_ip.v"
`include "utils/3_stage_synchronizer.v"
`include "utils/cdc_pulse_sync.v"
`include "utils/cdc_syncfifo.v"
`include "utils/CG_MOD_pos.v"
`include "utils/generic_fifo.v"
`include "utils/ramb_8_to_n.v"

// Basil functional modules (direct children of daq_core)
`include "seq_gen/seq_gen.v"
`include "seq_gen/seq_gen_core.v"
`include "spi/spi.v"
`include "spi/spi_core.v"
`include "spi/blk_mem_gen_8_to_1_2k.v"
`include "gpio/gpio.v"
`include "gpio/gpio_core.v"
`include "pulse_gen/pulse_gen.v"
`include "pulse_gen/pulse_gen_core.v"
`include "fast_spi_rx/fast_spi_rx.v"
`include "fast_spi_rx/fast_spi_rx_core.v"

module daq_core #(
    parameter integer ABUSWIDTH = 32
) (
    // ---------------------------------------------------------------
    // Bus interface (directly from rbcp_to_bus / SiTcp)
    // ---------------------------------------------------------------
    input wire                  bus_clk,
    input wire                  bus_rst,
    input wire [ABUSWIDTH-1:0]  bus_add,
    inout wire [7:0]            bus_data,
    input wire                  bus_rd,
    input wire                  bus_wr,

    // ---------------------------------------------------------------
    // Sequencer clock input (directly from PLL, no division)
    // ---------------------------------------------------------------
    input wire seq_clk,     // 200 MHz sequencer clock

    // ---------------------------------------------------------------
    // Sequencer outputs -> LVDS transmitters on PCB
    // Active sequencer tracks directly drive the 4 LVDS clock pairs
    // ---------------------------------------------------------------
    output wire CLK_INIT,   // DAC initialization pulse
    output wire CLK_SAMP,   // Sample-and-hold trigger
    output wire CLK_COMP,   // Comparator clock (200 MHz toggle)
    output wire CLK_LOGIC,  // SAR logic clock (200 MHz toggle, 2.5ns delayed)

    // ---------------------------------------------------------------
    // SPI interface -> chip carrier PCB
    // ---------------------------------------------------------------
    input wire  spi_clk,    // SPI shift clock
    output wire SPI_SCLK,   // SPI clock to chip
    output wire SPI_SDI,    // SPI data to chip (MOSI)
    input wire  SPI_SDO,    // SPI data from chip (MISO)
    output wire SPI_CS_B,   // SPI chip select (active low)

    // ---------------------------------------------------------------
    // GPIO -> PCB control signals
    // ---------------------------------------------------------------
    output wire RST_B,      // Chip reset (active low)
    output wire AMPEN_B,    // Input amplifier enable (active low)

    // ---------------------------------------------------------------
    // comp_out data -> bram_fifo (instantiated at top level)
    // The fast_spi_rx module captures the 1-bit comparator output stream,
    // packs it into 32-bit words, and presents them as a FIFO source.
    // ---------------------------------------------------------------
    output wire [31:0] fifo_data_out,
    input wire         fifo_read_next,
    output wire        fifo_empty,

    // Comparator output from LVDS receiver (drives PCB pad)
    input wire COMP_OUT,

    // ---------------------------------------------------------------
    // Global reset (independent of bus_rst, e.g. PLL not locked)
    // ---------------------------------------------------------------
    input wire reset,

    // ---------------------------------------------------------------
    // Sequencer pattern readback for LED display
    // ---------------------------------------------------------------
    output wire [3:0] seq_pattern_out,  // tracks [3:0] at seq_pattern_addr
    input wire [5:0]  seq_pattern_addr  // address 0..39
);

    // ===================================================================
    // Address map (matching map_fpga.yaml)
    // ===================================================================
    localparam integer SEQ_GEN_BASEADDR      = 32'h10000;
    localparam integer SEQ_GEN_HIGHADDR      = 32'h1FFFF;

    localparam integer SPI_BASEADDR          = 32'h20000;
    localparam integer SPI_HIGHADDR          = 32'h200FF;

    localparam integer GPIO_BASEADDR         = 32'h30000;
    localparam integer GPIO_HIGHADDR         = 32'h300FF;

    localparam integer PULSE_GEN_BASEADDR    = 32'h40000;
    localparam integer PULSE_GEN_HIGHADDR    = 32'h400FF;

    localparam integer FAST_SPI_RX_BASEADDR  = 32'h50000;
    localparam integer FAST_SPI_RX_HIGHADDR  = 32'h500FF;

    // ===================================================================
    // Combined reset
    // ===================================================================
    wire rst;
    assign rst = bus_rst | reset;

    // ===================================================================
    // 1. Sequencer (seq_gen)
    //
    // Generates the 8-track timing waveform loaded from the host.
    // seq_out[0] = CLK_INIT       - DAC initialization pulse
    // seq_out[1] = CLK_SAMP       - Sample-and-hold trigger
    // seq_out[2] = CLK_COMP       - Comparator clock
    // seq_out[3] = CLK_LOGIC      - SAR logic clock
    // seq_out[4] = clk_comp_cap   - Capture clock for fast_spi_rx SCLK
    // seq_out[5] = sen_comp       - Frame enable for fast_spi_rx SEN
    // seq_out[6] = test_data      - Loopback test data for fast_spi_rx
    // seq_out[7] = spare
    // ===================================================================
    wire [7:0] seq_out;
    /* verilator lint_off UNUSEDSIGNAL */
    wire _unused_seq = seq_out[7];  // SPARE_7, reserved for future use
    /* verilator lint_on UNUSEDSIGNAL */

    wire pulse_out;  // from pulse_gen, triggers sequencer start

    seq_gen #(
        .BASEADDR (SEQ_GEN_BASEADDR),
        .HIGHADDR (SEQ_GEN_HIGHADDR),
        .ABUSWIDTH(ABUSWIDTH),
        .MEM_BYTES(8192),
        .OUT_BITS (8)
    ) inst_seq_gen (
        .BUS_CLK(bus_clk),
        .BUS_RST(rst),
        .BUS_ADD(bus_add),
        .BUS_DATA(bus_data),
        .BUS_RD(bus_rd),
        .BUS_WR(bus_wr),

        .SEQ_EXT_START(pulse_out),
        .SEQ_CLK(seq_clk),
        .SEQ_OUT(seq_out)
    );

    // LVDS clock outputs to chip
    assign CLK_INIT  = seq_out[0];
    assign CLK_SAMP  = seq_out[1];
    assign CLK_COMP  = seq_out[2];
    assign CLK_LOGIC = seq_out[3];

    // Shadow copy of first 40 seq_gen pattern bytes (tracks [3:0] only)
    // Snoops bus writes to seq_gen memory region for LED display
    localparam SEQ_MEM_OFFSET = 64;  // matches seq_gen_core MEM_OFFSET
    reg [3:0] seq_shadow [0:39];
    integer si;
    initial for (si = 0; si < 40; si = si + 1) seq_shadow[si] = 0;

    always @(posedge bus_clk)
        if (bus_wr
            && bus_add >= SEQ_GEN_BASEADDR + SEQ_MEM_OFFSET
            && bus_add <  SEQ_GEN_BASEADDR + SEQ_MEM_OFFSET + 40)
            seq_shadow[bus_add - SEQ_GEN_BASEADDR - SEQ_MEM_OFFSET] <= bus_data[3:0];

    assign seq_pattern_out = seq_shadow[seq_pattern_addr];

    // Capture control signals
    wire clk_comp_cap;  // seq_out[4] - capture clock (normal mode)
    wire sen_comp;      // seq_out[5] - frame enable
    wire test_data;     // seq_out[6] - test data for loopback
    assign clk_comp_cap = seq_out[4];
    assign sen_comp     = seq_out[5];
    assign test_data    = seq_out[6];

    // fast_spi_rx input mux (loopback test mode, controlled by GPIO bit 2)
    // Normal:   SCLK = clk_comp_cap (seq_out[4]),  SDI = COMP_OUT
    // Loopback: SCLK = ~seq_clk (half-period delay), SDI = test_data (seq_out[6])
    wire loopback_en;  // assigned in GPIO section below
    wire fspi_sclk;
    wire fspi_sdi;
    assign fspi_sclk = loopback_en ? ~seq_clk : clk_comp_cap;
    assign fspi_sdi  = loopback_en ? test_data : COMP_OUT;

    // ===================================================================
    // 2. SPI Master
    //
    // Drives the 180-bit configuration shift register on the FRIDA chip.
    // SEN active-low directly maps to SPI_CS_B.
    // ===================================================================
    wire spi_sen;

    spi #(
        .BASEADDR (SPI_BASEADDR),
        .HIGHADDR (SPI_HIGHADDR),
        .ABUSWIDTH(ABUSWIDTH),
        .MEM_BYTES(32)          // 256 bits > 180 bits needed
    ) inst_spi (
        .BUS_CLK(bus_clk),
        .BUS_RST(rst),
        .BUS_ADD(bus_add),
        .BUS_DATA(bus_data),
        .BUS_RD(bus_rd),
        .BUS_WR(bus_wr),

        .SPI_CLK(spi_clk),

        .SCLK(SPI_SCLK),
        .SDI(SPI_SDI),
        .SDO(SPI_SDO),
        .EXT_START(1'b0),

        .SEN(spi_sen),
        /* verilator lint_off PINCONNECTEMPTY */
        .SLD()
        /* verilator lint_on PINCONNECTEMPTY */
    );

    assign SPI_CS_B = ~spi_sen;  // SEN is active-high enable, CS_B is active-low

    // ===================================================================
    // 3. GPIO
    //
    // 8-bit output register for PCB control signals.
    // Bit 0: RST_B        - Chip reset (active low)
    // Bit 1: AMPEN_B      - Input amplifier enable (active low)
    // Bit 2: loopback_en  - fast_spi_rx loopback test mode
    // Bits 7:3: reserved
    // ===================================================================
    wire [7:0] gpio_io;

    gpio #(
        .BASEADDR    (GPIO_BASEADDR),
        .HIGHADDR    (GPIO_HIGHADDR),
        .ABUSWIDTH   (ABUSWIDTH),
        .IO_WIDTH    (8),
        .IO_DIRECTION(8'hFF),   // All outputs
        .IO_TRI      (0)
    ) inst_gpio (
        .BUS_CLK(bus_clk),
        .BUS_RST(rst),
        .BUS_ADD(bus_add),
        .BUS_DATA(bus_data),
        .BUS_RD(bus_rd),
        .BUS_WR(bus_wr),

        .IO(gpio_io)
    );

    assign RST_B   = gpio_io[0];
    assign AMPEN_B = ~gpio_io[1];  // Invert: gpio_io[1]=1 enables amp (AMPEN_B=0)

    // Loopback test mode (GPIO bit 2)
    assign loopback_en = gpio_io[2];

    // ===================================================================
    // 4. Pulse Generator
    //
    // Generates a single trigger pulse to start the sequencer.
    // Can be started from the host via register write.
    // ===================================================================
    pulse_gen #(
        .BASEADDR (PULSE_GEN_BASEADDR),
        .HIGHADDR (PULSE_GEN_HIGHADDR),
        .ABUSWIDTH(ABUSWIDTH)
    ) inst_pulse_gen (
        .BUS_CLK(bus_clk),
        .BUS_RST(rst),
        .BUS_ADD(bus_add),
        .BUS_DATA(bus_data),
        .BUS_RD(bus_rd),
        .BUS_WR(bus_wr),

        .PULSE_CLK(seq_clk),
        .EXT_START(1'b0),
        .PULSE(pulse_out)
    );

    // ===================================================================
    // 5. COMP_OUT Receiver (fast_spi_rx)
    //
    // Captures the 1-bit COMP_OUT stream using basil's fast_spi_rx module.
    // This replaces the hand-rolled shift register + FIFO implementation.
    //
    // Signal mapping:
    //   SCLK <- seq_out[4] (clk_comp_cap) - Capture clock from sequencer
    //           Using a sequencer track allows the user to shift the sampling
    //           edge to compensate for round-trip propagation delay
    //           (FPGA → LVDS → chip → comparator → LVDS → FPGA)
    //   SDI  <- COMP_OUT                  - Comparator output from chip
    //   SEN  <- seq_out[5] (sen_comp)     - Frame enable from sequencer
    //           High during 17 capture cycles, falling edge flushes partial word
    //
    // Output format (32-bit words):
    //   [31:28] IDENTIFIER (4'b0001 by default)
    //   [27:16] Frame counter (12 bits, increments on SEN falling edge)
    //   [15:0]  Captured data (16 bits of comp_out samples)
    //
    // For 17-bit ADC conversions:
    //   - First 16 bits create one complete FIFO word
    //   - Remaining 1 bit creates a partial word on SEN falling edge
    // ===================================================================
    fast_spi_rx #(
        .BASEADDR  (FAST_SPI_RX_BASEADDR),
        .HIGHADDR  (FAST_SPI_RX_HIGHADDR),
        .ABUSWIDTH (ABUSWIDTH),
        .IDENTIFIER(4'b0001)    // Only block which writes to shared FIFO
    ) inst_fast_spi_rx (
        .BUS_CLK(bus_clk),
        .BUS_RST(rst),
        .BUS_ADD(bus_add),
        .BUS_DATA(bus_data),
        .BUS_RD(bus_rd),
        .BUS_WR(bus_wr),

        .SCLK(fspi_sclk),       // Normal: clk_comp_cap; Loopback: ~seq_clk
        .SDI(fspi_sdi),         // Normal: COMP_OUT;     Loopback: test_data (seq_out[6])
        .SEN(sen_comp),         // Frame enable from sequencer track 5

        .FIFO_READ(fifo_read_next),
        .FIFO_EMPTY(fifo_empty),
        .FIFO_DATA(fifo_data_out)
    );

endmodule
