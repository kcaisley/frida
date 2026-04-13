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

`include "utils/RAMB16_S1_S9_sim.v"

module tb_daq_core (
    input wire          BUS_CLK,
    input wire          SEQ_CLK,
    input wire          BUS_RST,
    input wire  [31:0]  BUS_ADD,
    inout wire  [7:0]   BUS_DATA,
    input wire          BUS_RD,
    input wire          BUS_WR,

    // FIFO output exposed for cocotb to read directly
    output wire [31:0]  FIFO_DATA,
    output wire         FIFO_EMPTY,
    input wire          FIFO_READ
);

    wire spi_sdi;  // SPI loopback: MOSI -> MISO

    daq_core #(
        .ABUSWIDTH(32)
    ) i_daq_core (
        .bus_clk        (BUS_CLK),
        .bus_rst        (BUS_RST),
        .bus_add        (BUS_ADD),
        .bus_data       (BUS_DATA),
        .bus_rd         (BUS_RD),
        .bus_wr         (BUS_WR),

        .seq_clk        (SEQ_CLK),

        /* verilator lint_off PINCONNECTEMPTY */
        .clk_init       (),
        .clk_samp       (),
        .clk_comp       (),
        .clk_logic      (),

        .spi_clk        (BUS_CLK),
        .spi_sclk       (),
        .spi_sdi        (spi_sdi),
        .spi_sdo        (spi_sdi),       // SPI loopback
        .spi_cs_b       (),

        .rst_b          (),
        .ampen_b        (),
        /* verilator lint_on PINCONNECTEMPTY */

        .fifo_data_out  (FIFO_DATA),
        .fifo_read_next (FIFO_READ),
        .fifo_empty     (FIFO_EMPTY),

        .comp_out       (1'b0),           // No chip connected
        .reset          (1'b0),

        /* verilator lint_off PINCONNECTEMPTY */
        .seq_pattern_out(),
        /* verilator lint_on PINCONNECTEMPTY */
        .seq_pattern_addr(6'b0)
    );

endmodule
