// Asynchronously assert a reset and synchronously release it in a clock domain.

`timescale 1ns / 1ps
`default_nettype none

module clock_reset_sync (
    input wire CLK,
    input wire ASYNC_RESET,
    output wire RESET
);

    (* ASYNC_REG = "TRUE" *) reg [1:0] reset_sync;

    always @(posedge CLK or posedge ASYNC_RESET) begin
        if (ASYNC_RESET)
            reset_sync <= 2'b11;
        else
            reset_sync <= {reset_sync[0], 1'b0};
    end

    assign RESET = reset_sync[1];

endmodule

`default_nettype wire
