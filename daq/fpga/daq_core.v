// FRIDA DAQ Core
//
// Basil-based core module for the FRIDA ADC test chip DAQ system.
// Instantiates the four functional blocks needed to control the chip
// and read back data:
//
//   1. seq_gen   - Sequencer generating 4 LVDS clock signals
//                  (CLK_INIT, CLK_SAMP, CLK_COMP, CLK_LOGIC)
//   2. spi       - SPI master for 180-bit chip configuration register
//                  (SPI_SCLK, SPI_SDI, SPI_SDO, SPI_CS_B)
//   3. gpio      - GPIO for PCB control signals (RST_B, AMP_EN)
//   4. pulse_gen - Pulse generator for triggering the sequencer
//
// The COMP_OUT data stream from the chip is received externally and
// fed into this module as a FIFO interface for the bram_fifo block
// (instantiated at the top level).
//
// Address map (matches daq.yaml):
//   0x8000      - bram_fifo control  (instantiated at top level)
//   0x80000000  - bram_fifo data     (instantiated at top level)
//   0x10000     - seq_gen
//   0x20000     - spi
//   0x30000     - gpio
//   0x40000     - pulse_gen
//
// Based on: obelix1-daq/firmware/src/obelix1_core.v

`timescale 1ns / 10ps

// Basil utilities
`include "utils/bus_to_ip.v"
`include "utils/cdc_pulse_sync.v"
`include "utils/CG_MOD_pos.v"
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

module daq_core #(
    parameter integer ABUSWIDTH = 32
) (
    // ---------------------------------------------------------------
    // Bus interface (directly from rbcp_to_bus / SiTcp)
    // ---------------------------------------------------------------
    input wire                  BUS_CLK,
    input wire                  BUS_RST,
    input wire [ABUSWIDTH-1:0]  BUS_ADD,
    inout wire [7:0]            BUS_DATA,
    input wire                  BUS_RD,
    input wire                  BUS_WR,

    // ---------------------------------------------------------------
    // Sequencer clock output (directly from PLL, no division)
    // ---------------------------------------------------------------
    input wire SEQ_CLK,     // 200 MHz sequencer clock

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
    input wire  SPI_CLK,    // SPI shift clock
    output wire SPI_SCLK,   // SPI clock to chip
    output wire SPI_SDI,    // SPI data to chip (MOSI)
    input wire  SPI_SDO,    // SPI data from chip (MISO)
    output wire SPI_CS_B,   // SPI chip select (active low)

    // ---------------------------------------------------------------
    // GPIO -> PCB control signals
    // ---------------------------------------------------------------
    output wire RST_B,      // Chip reset (active low)
    output wire AMP_EN,     // Input amplifier enable

    // ---------------------------------------------------------------
    // COMP_OUT data -> bram_fifo (instantiated at top level)
    // The receiver logic captures the 1-bit comparator output stream,
    // packs it into 32-bit words, and presents them as a FIFO source.
    // ---------------------------------------------------------------
    output wire [31:0] FIFO_DATA_OUT,
    input wire         FIFO_READ_NEXT,
    output wire        FIFO_EMPTY,

    // COMP_OUT input from LVDS receiver
    input wire COMP_OUT,

    // ---------------------------------------------------------------
    // Global reset (independent of BUS_RST, e.g. PLL not locked)
    // ---------------------------------------------------------------
    input wire RESET
);

    // ===================================================================
    // Address map (matching daq.yaml)
    // ===================================================================
    localparam integer SEQ_GEN_BASEADDR   = 32'h10000;
    localparam integer SEQ_GEN_HIGHADDR   = 32'h1FFFF;

    localparam integer SPI_BASEADDR       = 32'h20000;
    localparam integer SPI_HIGHADDR       = 32'h200FF;

    localparam integer GPIO_BASEADDR      = 32'h30000;
    localparam integer GPIO_HIGHADDR      = 32'h300FF;

    localparam integer PULSE_GEN_BASEADDR = 32'h40000;
    localparam integer PULSE_GEN_HIGHADDR = 32'h400FF;

    // ===================================================================
    // Combined reset
    // ===================================================================
    wire rst;
    assign rst = BUS_RST | RESET;

    // ===================================================================
    // 1. Sequencer (seq_gen)
    //
    // Generates the 4-track timing waveform loaded from the host.
    // SEQ_OUT[0] = CLK_INIT
    // SEQ_OUT[1] = CLK_SAMP
    // SEQ_OUT[2] = CLK_COMP
    // SEQ_OUT[3] = CLK_LOGIC
    // SEQ_OUT[7:4] = spare
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
        .BUS_CLK(BUS_CLK),
        .BUS_RST(rst),
        .BUS_ADD(BUS_ADD),
        .BUS_DATA(BUS_DATA),
        .BUS_RD(BUS_RD),
        .BUS_WR(BUS_WR),

        .SEQ_EXT_START(pulse_out),
        .SEQ_CLK(SEQ_CLK),
        .SEQ_OUT(seq_out)
    );

    assign CLK_INIT  = seq_out[0];
    assign CLK_SAMP  = seq_out[1];
    assign CLK_COMP  = seq_out[2];
    assign CLK_LOGIC = seq_out[3];

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
        .BUS_CLK(BUS_CLK),
        .BUS_RST(rst),
        .BUS_ADD(BUS_ADD),
        .BUS_DATA(BUS_DATA),
        .BUS_RD(BUS_RD),
        .BUS_WR(BUS_WR),

        .SPI_CLK(SPI_CLK),

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
    // Bit 0: RST_B   - Chip reset (active low)
    // Bit 1: AMP_EN  - Input amplifier enable
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
        .BUS_CLK(BUS_CLK),
        .BUS_RST(rst),
        .BUS_ADD(BUS_ADD),
        .BUS_DATA(BUS_DATA),
        .BUS_RD(BUS_RD),
        .BUS_WR(BUS_WR),

        .IO(gpio_io)
    );

    assign RST_B  = gpio_io[0];
    assign AMP_EN = gpio_io[1];

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
        .BUS_CLK(BUS_CLK),
        .BUS_RST(rst),
        .BUS_ADD(BUS_ADD),
        .BUS_DATA(BUS_DATA),
        .BUS_RD(BUS_RD),
        .BUS_WR(BUS_WR),

        .PULSE_CLK(SEQ_CLK),
        .EXT_START(1'b0),
        .PULSE(pulse_out)
    );

    // ===================================================================
    // 5. COMP_OUT Receiver / Data Buffer
    //
    // Captures the 1-bit COMP_OUT stream at the sequencer clock rate
    // (200 MHz) and packs it into 32-bit words for the bram_fifo.
    //
    // Each 32-bit word contains 32 consecutive comparator output bits.
    // The bram_fifo (instantiated at the top level) reads these words
    // and makes them available to the host via TCP.
    // ===================================================================
    reg [31:0] comp_shift_reg;
    reg [4:0]  comp_bit_cnt;
    reg        comp_word_ready;
    reg [31:0] comp_fifo_data;
    reg        comp_fifo_empty;

    // Synchronize COMP_OUT into the SEQ_CLK domain
    reg comp_out_sync1, comp_out_sync2;
    always @(posedge SEQ_CLK) begin
        comp_out_sync1 <= COMP_OUT;
        comp_out_sync2 <= comp_out_sync1;
    end

    // Pack COMP_OUT bits into 32-bit words
    always @(posedge SEQ_CLK or posedge rst) begin
        if (rst) begin
            comp_shift_reg <= 32'b0;
            comp_bit_cnt   <= 5'b0;
            comp_word_ready <= 1'b0;
        end else begin
            comp_shift_reg <= {comp_shift_reg[30:0], comp_out_sync2};
            comp_word_ready <= 1'b0;
            if (comp_bit_cnt == 5'd31) begin
                comp_bit_cnt    <= 5'b0;
                comp_word_ready <= 1'b1;
            end else begin
                comp_bit_cnt <= comp_bit_cnt + 1'b1;
            end
        end
    end

    // Simple single-word FIFO bridging SEQ_CLK -> BUS_CLK domain
    // For the bram_fifo interface
    reg [31:0] fifo_buf_data;
    reg        fifo_buf_valid;
    reg        fifo_buf_read_ack;

    // SEQ_CLK domain: latch completed words
    always @(posedge SEQ_CLK or posedge rst) begin
        if (rst) begin
            fifo_buf_data  <= 32'b0;
            fifo_buf_valid <= 1'b0;
        end else begin
            if (comp_word_ready) begin
                fifo_buf_data  <= comp_shift_reg;
                fifo_buf_valid <= 1'b1;
            end else if (fifo_buf_read_ack) begin
                fifo_buf_valid <= 1'b0;
            end
        end
    end

    // BUS_CLK domain: present data to bram_fifo
    reg fifo_valid_sync1, fifo_valid_sync2, fifo_valid_sync3;
    always @(posedge BUS_CLK or posedge rst) begin
        if (rst) begin
            fifo_valid_sync1 <= 1'b0;
            fifo_valid_sync2 <= 1'b0;
            fifo_valid_sync3 <= 1'b0;
            comp_fifo_data   <= 32'b0;
            comp_fifo_empty  <= 1'b1;
            fifo_buf_read_ack <= 1'b0;
        end else begin
            fifo_valid_sync1 <= fifo_buf_valid;
            fifo_valid_sync2 <= fifo_valid_sync1;
            fifo_valid_sync3 <= fifo_valid_sync2;
            fifo_buf_read_ack <= 1'b0;

            // Rising edge of valid in BUS_CLK domain
            if (fifo_valid_sync2 && !fifo_valid_sync3) begin
                comp_fifo_data  <= fifo_buf_data;
                comp_fifo_empty <= 1'b0;
            end

            // bram_fifo reads the word
            if (FIFO_READ_NEXT && !comp_fifo_empty) begin
                comp_fifo_empty   <= 1'b1;
                fifo_buf_read_ack <= 1'b1;
            end
        end
    end

    assign FIFO_DATA_OUT = comp_fifo_data;
    assign FIFO_EMPTY    = comp_fifo_empty;

endmodule
