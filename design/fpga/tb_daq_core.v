/*
 * Minimal testbench for daq_core FPGA-level testing.
 *
 * Provides uppercase bus signals for BasilBusDriver, drives SEQ_CLK
 * from cocotb, and ties off unused inputs. No analog, no ASIC core.
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
    input wire          BUS_WR
);

    wire clk_init, clk_samp, clk_comp, clk_logic;
    wire spi_sclk, spi_sdi, spi_cs_b;
    wire rst_b, ampen_b;
    wire [31:0] fifo_data_out;
    wire fifo_empty;
    wire [3:0] seq_pattern_out;

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

        .clk_init       (clk_init),
        .clk_samp       (clk_samp),
        .clk_comp       (clk_comp),
        .clk_logic      (clk_logic),

        .spi_clk        (BUS_CLK),
        .spi_sclk       (spi_sclk),
        .spi_sdi        (spi_sdi),
        .spi_sdo        (spi_sdi),       // SPI loopback: MOSI -> MISO
        .spi_cs_b       (spi_cs_b),

        .rst_b          (rst_b),
        .ampen_b        (ampen_b),

        .fifo_data_out  (fifo_data_out),
        .fifo_read_next (1'b0),
        .fifo_empty     (fifo_empty),

        .comp_out       (1'b0),           // No chip connected
        .reset          (1'b0),

        .seq_pattern_out(seq_pattern_out),
        .seq_pattern_addr(6'b0)
    );

endmodule
