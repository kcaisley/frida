// FRIDA DAQ Core - Simplified diagram version
// Black-box submodules for clean netlist visualization

`timescale 1ns / 10ps

// ===================================================================
// Black-box stubs for basil modules (diagram only, not synthesizable)
// ===================================================================

module seq_gen (
    input  wire        BUS_CLK,
    input  wire        BUS_RST,
    input  wire [31:0] BUS_ADD,
    inout  wire [7:0]  BUS_DATA,
    input  wire        BUS_RD,
    input  wire        BUS_WR,

    input  wire        SEQ_EXT_START,
    input  wire        SEQ_CLK,
    output wire [7:0]  SEQ_OUT
);
endmodule

module spi (
    input  wire        BUS_CLK,
    input  wire        BUS_RST,
    input  wire [31:0] BUS_ADD,
    inout  wire [7:0]  BUS_DATA,
    input  wire        BUS_RD,
    input  wire        BUS_WR,

    input  wire        SPI_CLK,
    output wire        SCLK,
    output wire        SDI,
    input  wire        SDO,
    input  wire        EXT_START,
    output wire        SEN,
    output wire        SLD
);
endmodule

module gpio (
    input  wire        BUS_CLK,
    input  wire        BUS_RST,
    input  wire [31:0] BUS_ADD,
    inout  wire [7:0]  BUS_DATA,
    input  wire        BUS_RD,
    input  wire        BUS_WR,

    inout  wire [7:0]  IO
);
endmodule

module pulse_gen (
    input  wire        BUS_CLK,
    input  wire        BUS_RST,
    input  wire [31:0] BUS_ADD,
    inout  wire [7:0]  BUS_DATA,
    input  wire        BUS_RD,
    input  wire        BUS_WR,

    input  wire        PULSE_CLK,
    input  wire        EXT_START,
    output wire        PULSE
);
endmodule

module comp_out_receiver (
    input  wire        SEQ_CLK,
    input  wire        BUS_CLK,
    input  wire        RST,

    input  wire        COMP_OUT,

    output wire [31:0] FIFO_DATA_OUT,
    input  wire        FIFO_READ_NEXT,
    output wire        FIFO_EMPTY
);
endmodule

// ===================================================================
// DAQ Core - diagram version
// ===================================================================

module daq_core (
    // Bus interface (from SiTcp / rbcp_to_bus)
    input  wire        BUS_CLK,
    input  wire        BUS_RST,
    input  wire [31:0] BUS_ADD,
    inout  wire [7:0]  BUS_DATA,
    input  wire        BUS_RD,
    input  wire        BUS_WR,

    // Clocks
    input  wire        SEQ_CLK,
    input  wire        SPI_CLK,

    // Sequencer outputs -> LVDS to chip
    output wire        CLK_INIT,
    output wire        CLK_SAMP,
    output wire        CLK_COMP,
    output wire        CLK_LOGIC,

    // SPI interface -> chip
    output wire        SPI_SCLK,
    output wire        SPI_SDI,
    input  wire        SPI_SDO,
    output wire        SPI_CS_B,

    // GPIO -> PCB
    output wire        RST_B,
    output wire        AMP_EN,

    // COMP_OUT data -> bram_fifo (at top level)
    output wire [31:0] FIFO_DATA_OUT,
    input  wire        FIFO_READ_NEXT,
    output wire        FIFO_EMPTY,

    // COMP_OUT from LVDS receiver
    input  wire        COMP_OUT,

    // Global reset
    input  wire        RESET
);

    // Combined reset
    wire rst;
    assign rst = BUS_RST | RESET;

    // Internal wires
    wire [7:0] seq_out;
    wire       pulse_out;
    wire       spi_sen;
    wire [7:0] gpio_io;

    // 1. Sequencer
    seq_gen inst_seq_gen (
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

    // 2. SPI Master
    spi inst_spi (
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
        .SLD()
    );

    assign SPI_CS_B = ~spi_sen;

    // 3. GPIO
    gpio inst_gpio (
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

    // 4. Pulse Generator
    pulse_gen inst_pulse_gen (
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

    // 5. COMP_OUT Receiver
    comp_out_receiver inst_comp_rx (
        .SEQ_CLK(SEQ_CLK),
        .BUS_CLK(BUS_CLK),
        .RST(rst),

        .COMP_OUT(COMP_OUT),

        .FIFO_DATA_OUT(FIFO_DATA_OUT),
        .FIFO_READ_NEXT(FIFO_READ_NEXT),
        .FIFO_EMPTY(FIFO_EMPTY)
    );

endmodule
