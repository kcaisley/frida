`timescale 1ns / 1ps

// Behavioral models of the generic cells (OPENROAD_*) the RTL instantiates. The supply
// ports are the netlist's (USE_POWER_PINS, design/hdl's convention): the models do not use them.

/* verilator lint_off UNUSEDSIGNAL */

module OPENROAD_DFFE (
`ifdef USE_POWER_PINS
    inout  wire VDD,
    inout  wire VSS,
`endif
    input  wire D,
    input  wire C,
    input  wire E,
    output reg  Q
);
    always @(posedge C) begin
        if (E) begin
            Q <= D;
        end
    end
endmodule

module OPENROAD_DFFER (
`ifdef USE_POWER_PINS
    inout  wire VDD,
    inout  wire VSS,
`endif
    input  wire D,
    input  wire C,
    input  wire E,
    input  wire R,
    output reg  Q
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
`ifdef USE_POWER_PINS
    inout  wire VDD,
    inout  wire VSS,
`endif
    input  wire A,
    input  wire B,
    output wire Y
);
    assign Y = A ^ B;
endmodule

module OPENROAD_CLKBUF (
`ifdef USE_POWER_PINS
    inout  wire VDD,
    inout  wire VSS,
`endif
    input  wire A,
    output wire Y
);
    assign Y = A;
endmodule

module OPENROAD_CLKINV (
`ifdef USE_POWER_PINS
    inout  wire VDD,
    inout  wire VSS,
`endif
    input  wire A,
    output wire Y
);
    assign Y = ~A;
endmodule

module OPENROAD_CTRLGATE (
`ifdef USE_POWER_PINS
    inout  wire VDD,
    inout  wire VSS,
`endif
    input  wire CK,
    input  wire E,
    output wire GCK
);
    assign GCK = CK & E;
endmodule

/* verilator lint_on UNUSEDSIGNAL */
