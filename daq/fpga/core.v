// FRIDA DAQ Core
//
// Basil-based core module for the FRIDA ADC test chip DAQ system.
// Instantiates the functional blocks needed to control the chip
// and read back data:
//
//   1. seq_gen      - Sequencer generating 6 output signals:
//                     [0-3] LVDS clocks (clk_init, clk_samp, clk_comp, clk_logic)
//                     [4]   clk_comp_cap - capture clock for fast_spi_rx
//                     [5]   sen_comp - frame enable for fast_spi_rx
//   2. spi          - SPI master for 180-bit chip configuration register
//                     (spi_sclk, spi_sdi, spi_sdo, spi_cs_b)
//   3. gpio         - GPIO for PCB control signals (rst_b, amp_en)
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

// Basil utilities
`include "utils/bus_to_ip.v"
`include "utils/cdc_pulse_sync.v"
`include "utils/cdc_syncfifo.v"
`include "utils/CG_MOD_pos.v"
`include "utils/generic_fifo.v"
`include "utils/ramb_8_to_n.v"

// Basil functional modules
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
    // Sequencer clock output (directly from PLL, no division)
    // ---------------------------------------------------------------
    input wire seq_clk,     // 200 MHz sequencer clock

    // ---------------------------------------------------------------
    // Sequencer outputs -> LVDS transmitters on PCB
    // Active sequencer tracks directly drive the 4 LVDS clock pairs
    // ---------------------------------------------------------------
    output wire clk_init,   // DAC initialization pulse
    output wire clk_samp,   // Sample-and-hold trigger
    output wire clk_comp,   // Comparator clock (200 MHz toggle)
    output wire clk_logic,  // SAR logic clock (200 MHz toggle, 2.5ns delayed)

    // ---------------------------------------------------------------
    // SPI interface -> chip carrier PCB
    // ---------------------------------------------------------------
    input wire  spi_clk,    // SPI shift clock
    output wire spi_sclk,   // SPI clock to chip
    output wire spi_sdi,    // SPI data to chip (MOSI)
    input wire  spi_sdo,    // SPI data from chip (MISO)
    output wire spi_cs_b,   // SPI chip select (active low)

    // ---------------------------------------------------------------
    // GPIO -> PCB control signals
    // ---------------------------------------------------------------
    output wire rst_b,      // Chip reset (active low)
    output wire amp_en,     // Input amplifier enable

    // ---------------------------------------------------------------
    // comp_out data -> bram_fifo (instantiated at top level)
    // The fast_spi_rx module captures the 1-bit comparator output stream,
    // packs it into 32-bit words, and presents them as a FIFO source.
    // ---------------------------------------------------------------
    output wire [31:0] fifo_data_out,
    input wire         fifo_read_next,
    output wire        fifo_empty,

    // comp_out input from LVDS receiver
    input wire comp_out,

    // ---------------------------------------------------------------
    // Global reset (independent of bus_rst, e.g. PLL not locked)
    // ---------------------------------------------------------------
    input wire reset
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
    // seq_out[0] = clk_init       - DAC initialization pulse
    // seq_out[1] = clk_samp       - Sample-and-hold trigger
    // seq_out[2] = clk_comp       - Comparator clock
    // seq_out[3] = clk_logic      - SAR logic clock
    // seq_out[4] = clk_comp_cap   - Capture clock for fast_spi_rx SCLK
    // seq_out[5] = sen_comp       - Frame enable for fast_spi_rx SEN
    // seq_out[7:6] = spare
    // ===================================================================
    wire [7:0] seq_out;

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
    assign clk_init  = seq_out[0];
    assign clk_samp  = seq_out[1];
    assign clk_comp  = seq_out[2];
    assign clk_logic = seq_out[3];

    // Capture control signals (directly to fast_spi_rx)
    wire clk_comp_cap;  // seq_out[4] - capture clock
    wire sen_comp;      // seq_out[5] - frame enable
    assign clk_comp_cap = seq_out[4];
    assign sen_comp     = seq_out[5];

    // ===================================================================
    // 2. SPI Master
    //
    // Drives the 180-bit configuration shift register on the FRIDA chip.
    // SEN active-low directly maps to spi_cs_b.
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

        .SCLK(spi_sclk),
        .SDI(spi_sdi),
        .SDO(spi_sdo),
        .EXT_START(1'b0),

        .SEN(spi_sen),
        /* verilator lint_off PINCONNECTEMPTY */
        .SLD()
        /* verilator lint_on PINCONNECTEMPTY */
    );

    assign spi_cs_b = ~spi_sen;  // SEN is active-high enable, CS_B is active-low

    // ===================================================================
    // 3. GPIO
    //
    // 8-bit output register for PCB control signals.
    // Bit 0: rst_b   - Chip reset (active low)
    // Bit 1: amp_en  - Input amplifier enable
    // Bits 7:2: reserved
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

    assign rst_b  = gpio_io[0];
    assign amp_en = gpio_io[1];

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
    // 5. comp_out Receiver (fast_spi_rx)
    //
    // Captures the 1-bit comp_out stream using basil's fast_spi_rx module.
    // This replaces the hand-rolled shift register + FIFO implementation.
    //
    // Signal mapping:
    //   SCLK <- seq_out[4] (clk_comp_cap) - Capture clock from sequencer
    //           Using a sequencer track allows the user to shift the sampling
    //           edge to compensate for round-trip propagation delay
    //           (FPGA → LVDS → chip → comparator → LVDS → FPGA)
    //   SDI  <- comp_out                  - Comparator output from chip
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

        .SCLK(clk_comp_cap),    // Capture clock from sequencer track 4
        .SDI(comp_out),         // Comparator output from chip
        .SEN(sen_comp),         // Frame enable from sequencer track 5

        .FIFO_READ(fifo_read_next),
        .FIFO_EMPTY(fifo_empty),
        .FIFO_DATA(fifo_data_out)
    );

endmodule
