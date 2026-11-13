// IHP SG13G2 Cell Mappings for OPENROAD_* Generic Modules
// Maps generic OPENROAD cell names to IHP SG13G2 standard cells
//
// The supply ports are the netlist's (USE_POWER_PINS, design/hdl's convention). IHP's cell
// models have none (the PDN connects the cells' VDD and VSS), so the wrappers leave them open.

/* verilator lint_off UNUSEDSIGNAL */

// Generic OPENROAD enabled flip-flop mapped to IHP SG13G2
// Since IHP-SG13G2 doesn't have a native enabled DFF, we implement it with mux + DFF
module OPENROAD_DFFE (
`ifdef USE_POWER_PINS
    inout  wire VDD,
    inout  wire VSS,
`endif
    input  wire D,    // Data input
    input  wire C,    // Clock input
    input  wire E,    // Enable input
    output wire Q     // Data output
);

    wire mux_out;
    wire q_n_unused;

    // When E=1, pass D; when E=0, pass current Q (feedback for hold)
    sg13g2_mux2_1 enable_mux (
        .A0(Q),
        .A1(D),
        .S (E),
        .X (mux_out)
    );

    // DFF with RESET_B tied high for no reset
    sg13g2_dfrbp_1 dff_cell (
        .D      (mux_out),
        .CLK    (C),
        .RESET_B(1'b1),
        .Q      (Q),
        .Q_N    (q_n_unused)
    );

endmodule

// Generic OPENROAD enabled flip-flop with active-low reset mapped to IHP SG13G2
// Since IHP-SG13G2 doesn't have a native enabled reset DFF, we implement it with mux + DFF
module OPENROAD_DFFER (
`ifdef USE_POWER_PINS
    inout  wire VDD,
    inout  wire VSS,
`endif
    input  wire D,    // Data input
    input  wire C,    // Clock input
    input  wire E,    // Enable input
    input  wire R,    // Active-low reset input
    output wire Q     // Data output
);

    wire mux_out;
    wire q_n_unused;

    // When E=1, pass D; when E=0, pass current Q (feedback for hold)
    sg13g2_mux2_1 enable_mux (
        .A0(Q),
        .A1(D),
        .S (E),
        .X (mux_out)
    );

    sg13g2_dfrbp_1 dff_cell (
        .D      (mux_out),
        .CLK    (C),
        .RESET_B(R),
        .Q      (Q),
        .Q_N    (q_n_unused)
    );

endmodule

// Generic OPENROAD XOR gate mapped to IHP SG13G2 XOR
module OPENROAD_CLKXOR (
`ifdef USE_POWER_PINS
    inout  wire VDD,
    inout  wire VSS,
`endif
    input  wire A,    // Input A
    input  wire B,    // Input B
    output wire Y     // Output Y = A ^ B
);

    sg13g2_xor2_1 xor_cell (
        .A(A),
        .B(B),
        .X(Y)
    );

endmodule

// Generic OPENROAD clock buffer mapped to IHP SG13G2 buffer
module OPENROAD_CLKBUF (
`ifdef USE_POWER_PINS
    inout  wire VDD,
    inout  wire VSS,
`endif
    input  wire A,    // Input
    output wire Y     // Output Y = A
);

    sg13g2_buf_2 buf_cell (
        .A(A),
        .X(Y)
    );

endmodule

// Generic OPENROAD clock inverter mapped to IHP SG13G2 inverter
module OPENROAD_CLKINV (
`ifdef USE_POWER_PINS
    inout  wire VDD,
    inout  wire VSS,
`endif
    input  wire A,    // Input
    output wire Y     // Output Y = ~A
);

    sg13g2_inv_2 inv_cell (
        .A(A),
        .Y(Y)
    );

endmodule

// Custom clock gate module that directly uses sg13g2_lgcp_1
// This bypasses the OPENROAD_CLKGATE define issues
module OPENROAD_CTRLGATE (
`ifdef USE_POWER_PINS
    inout  wire VDD,
    inout  wire VSS,
`endif
    input  wire CK,   // Clock input
    input  wire E,    // Enable input
    output wire GCK   // Gated clock output
);

    sg13g2_lgcp_1 clkgate_cell (
        .CLK (CK),
        .GATE(E),
        .GCLK(GCK)
    );

endmodule

/* verilator lint_on UNUSEDSIGNAL */
