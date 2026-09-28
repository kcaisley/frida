`timescale 1ns / 1ps
`default_nettype none
module fastrx_sequence_tb (
    input  wire        bus_clk,
    input  wire        seq_clk,
    input  wire        rst,
    input  wire [15:0] addr,
    input  wire [ 7:0] data,
    input  wire        seq_wr,
    input  wire        rx_wr,
    input  wire        fifo_read,
    output wire        fifo_empty,
    output wire [31:0] fifo_data,
    output wire [63:0] seq_out
);
    wire [7:0] unused_seq_data;
    wire [7:0] unused_rx_data;
    seq_gen_core #(
        .OUT_BITS (64),
        .MEM_BYTES(1024)
    ) seq (
        .BUS_CLK      (bus_clk),
        .BUS_RST      (rst),
        .BUS_ADD      (addr),
        .BUS_DATA_IN  (data),
        .BUS_RD       (1'b0),
        .BUS_WR       (seq_wr),
        .BUS_DATA_OUT (unused_seq_data),
        .SEQ_EXT_START(1'b0),
        .SEQ_CLK      (seq_clk),
        .SEQ_OUT      (seq_out)
    );
    fast_spi_rx_core #(
        .DATA_SIZE(17)
    ) rx (
        .SCLK        (seq_clk),
        .SDI         (seq_out[33]),
        .SEN         (seq_out[32]),
        .FIFO_READ   (fifo_read),
        .FIFO_EMPTY  (fifo_empty),
        .FIFO_DATA   (fifo_data),
        .BUS_CLK     (bus_clk),
        .BUS_RST     (rst),
        .BUS_ADD     (addr),
        .BUS_DATA_IN (data),
        .BUS_WR      (rx_wr),
        .BUS_RD      (1'b0),
        .BUS_DATA_OUT(unused_rx_data)
    );
endmodule
