// 8:1 DDR OSERDES wrapper for serializer-backed sequencer outputs.
`timescale 1ns / 1ps

module daq_serdes (
    input  wire       clk,
    input  wire       clkdiv,
    input  wire       rst,
    input  wire [7:0] data,
    output wire       oq
);

    OSERDESE2 #(
        .DATA_RATE_OQ("DDR"),
        .DATA_RATE_TQ("SDR"),
        .DATA_WIDTH(8),
        .INIT_OQ(1'b0),
        .INIT_TQ(1'b0),
        .SERDES_MODE("MASTER"),
        .SRVAL_OQ(1'b0),
        .SRVAL_TQ(1'b0),
        .TBYTE_CTL("FALSE"),
        .TBYTE_SRC("FALSE"),
        .TRISTATE_WIDTH(1)
    ) oserdes (
        .OQ(oq),
        .OFB(),
        .TQ(),
        .TFB(),
        .TBYTEOUT(),
        .SHIFTOUT1(),
        .SHIFTOUT2(),
        .CLK(clk),
        .CLKDIV(clkdiv),
        .D1(data[0]),
        .D2(data[1]),
        .D3(data[2]),
        .D4(data[3]),
        .D5(data[4]),
        .D6(data[5]),
        .D7(data[6]),
        .D8(data[7]),
        .OCE(1'b1),
        .RST(rst),
        .SHIFTIN1(1'b0),
        .SHIFTIN2(1'b0),
        .T1(1'b0),
        .T2(1'b0),
        .T3(1'b0),
        .T4(1'b0),
        .TBYTEIN(1'b0),
        .TCE(1'b0)
    );

endmodule
