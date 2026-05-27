`timescale 1ns/1ps

module OPENROAD_DFFE (
    input wire D,
    input wire C,
    input wire E,
    output reg Q
);
    always @(posedge C) begin
        if (E) begin
            Q <= D;
        end
    end
endmodule

module OPENROAD_DFFER (
    input wire D,
    input wire C,
    input wire E,
    input wire R,
    output reg Q
);
    always @(posedge C or negedge R) begin
        if (!R) begin
            Q <= 1'b0;
        end else if (E) begin
            Q <= D;
        end
    end
endmodule

module OPENROAD_CLKXOR (
    input wire A,
    input wire B,
    output wire Y
);
    assign Y = A ^ B;
endmodule

module OPENROAD_CLKBUF (
    input wire A,
    output wire Y
);
    assign Y = A;
endmodule

module OPENROAD_CLKINV (
    input wire A,
    output wire Y
);
    assign Y = ~A;
endmodule

module OPENROAD_CTRLGATE (
    input wire CK,
    input wire E,
    output wire GCK
);
    assign GCK = CK & E;
endmodule
