/*
 * Testbench for daq_core FPGA-level testing.
 *
 * Provides uppercase bus signals for BasilBusDriver, drives SEQ_CLK
 * from cocotb, and ties off unused inputs. No analog, no ASIC core.
 *
 * The FIFO output from fast_spi_rx is exposed as top-level signals
 * so cocotb can read captured data directly (no bram_fifo needed).
 * SPI MOSI is looped back to MISO for SPI write/readback testing.
 */

`timescale 1ns / 1ps

module tb_daq_core (
    input wire        BUS_CLK,
    input wire        SEQ_CLK,
    input wire        SPI_CLK,
    input wire        BUS_RST,
    input wire [31:0] BUS_ADD,
    inout wire [ 7:0] BUS_DATA,
    input wire        BUS_RD,
    input wire        BUS_WR,

    // FIFO output exposed for cocotb to read directly
    output wire [31:0] FIFO_DATA,
    output wire        FIFO_EMPTY,
    input  wire        FIFO_READ
);

    wire spi_sdi;  // SPI loopback: MOSI -> MISO

    daq_core #(
        .ABUSWIDTH(32)
    ) i_daq_core (
        .BUS_CLK (BUS_CLK),
        .BUS_RST (BUS_RST),
        .BUS_ADD (BUS_ADD),
        .BUS_DATA(BUS_DATA),
        .BUS_RD  (BUS_RD),
        .BUS_WR  (BUS_WR),

        .SEQ_CLK(SEQ_CLK),

        /* verilator lint_off PINCONNECTEMPTY */
        .CLK_INIT (),
        .CLK_SAMP (),
        .CLK_COMP (),
        .CLK_LOGIC(),

        .SPI_CLK (SPI_CLK),
        .SPI_SCLK(),
        .SPI_SDI (spi_sdi),
        .SPI_SDO (spi_sdi),  // SPI loopback
        .SPI_CS_B(),

        .RST_B  (),
        .AMPEN_B(),
        /* verilator lint_on PINCONNECTEMPTY */

        .FASTRX_FIFO_DATA_OUT  (FIFO_DATA),
        .FASTRX_FIFO_READ_NEXT(FIFO_READ),
        .FASTRX_FIFO_EMPTY    (FIFO_EMPTY),

        .COMP_OUT(1'b0),  // No chip connected
        .RESET   (1'b0),

        .LED_OUT()
    );

endmodule
