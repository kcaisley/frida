// TSMC65 Cell Mappings for OPENROAD_* Generic Modules
// Maps generic OPENROAD cell names to TSMC65 standard cells
//
// The supply ports are the netlist's (USE_POWER_PINS, design/hdl's convention). The PDN connects
// the cells' own supplies (global connections), so the wrappers leave them open.

/* verilator lint_off UNUSEDSIGNAL */

// Generic OPENROAD enabled flip-flop mapped to TSMC65
// TSMC65 has native enabled DFF cells
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

    // Use TSMC65 enabled D flip-flop
    // EDFD2LVT: Enabled D flip-flop with 2x drive strength
    EDFD2LVT dffe (
        .D (D),
        .CP(C),
        .E (E),
        .Q (Q)
    );

endmodule

// Generic OPENROAD enabled flip-flop with reset mapped to TSMC65
module OPENROAD_DFFER (
`ifdef USE_POWER_PINS
    inout  wire VDD,
    inout  wire VSS,
`endif
    input  wire D,    // Data input
    input  wire C,    // Clock input
    input  wire E,    // Enable input
    input  wire R,    // Active-low async reset
    output wire Q     // Data output
);

    // Use TSMC65 enabled D flip-flop with reset
    // EDFCND2LVT: Enabled D flip-flop with Clear-Direct-Negative (active-low reset)
    EDFCND2LVT dffe (
        .D  (D),
        .CP (C),
        .E  (E),
        .CDN(R),
        .Q  (Q)
    );

endmodule

// Generic OPENROAD XOR gate mapped to TSMC65 XOR
module OPENROAD_CLKXOR (
`ifdef USE_POWER_PINS
    inout  wire VDD,
    inout  wire VSS,
`endif
    input  wire A,    // Input A
    input  wire B,    // Input B
    output wire Y     // Output Y = A ^ B
);

    XOR2D1LVT xor_cell (
        .A1(A),
        .A2(B),
        .Z (Y)
    );

endmodule

// Generic OPENROAD clock buffer mapped to TSMC65 buffer
module OPENROAD_CLKBUF (
`ifdef USE_POWER_PINS
    inout  wire VDD,
    inout  wire VSS,
`endif
    input  wire A,    // Input
    output wire Y     // Output Y = A
);

    BUFFD2LVT buf_cell (
        .I(A),
        .Z(Y)
    );

endmodule

// Generic OPENROAD clock inverter mapped to TSMC65 inverter
module OPENROAD_CLKINV (
`ifdef USE_POWER_PINS
    inout  wire VDD,
    inout  wire VSS,
`endif
    input  wire A,    // Input
    output wire Y     // Output Y = ~A
);

    INVD2LVT inv_cell (
        .I (A),
        .ZN(Y)
    );

endmodule

// Custom clock gate module that directly uses TSMC65 clock gate
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

    // Use TSMC65 latch-based clock gate (TE tied to 0 for normal operation)
    CKLNQD1LVT clkgate_cell (
        .TE(1'b0),
        .CP(CK),
        .E (E),
        .Q (GCK)
    );

endmodule

/* verilator lint_on UNUSEDSIGNAL */
