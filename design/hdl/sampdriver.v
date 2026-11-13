// Sampling Clock Driver Module - Generates complementary clock signals
// Uses generic OPENROAD clock buffer and inverter - mapped to technology-specific cells

(* dont_touch = "true" *)
module sampdriver (
`ifdef USE_POWER_PINS
    inout  wire vdd_d,     // Digital supply
    inout  wire vss_d,     // Digital ground
`endif
    input  wire clk_in,    // Input clock signal
    output wire clk_out,   // Buffered output clock
    output wire clk_out_b  // Inverted output clock
);

    // Generic clock buffer for main signal path
    OPENROAD_CLKBUF clk_buf (
`ifdef USE_POWER_PINS
        .VDD(vdd_d),   // Power supply
        .VSS(vss_d),   // Ground supply
`endif
        .A  (clk_in),  // Input clock
        .Y  (clk_out)  // Buffered clock output
    );

    // Generic clock inverter for complementary signal path
    OPENROAD_CLKINV clk_inv (
`ifdef USE_POWER_PINS
        .VDD(vdd_d),     // Power supply
        .VSS(vss_d),     // Ground supply
`endif
        .A  (clk_in),    // Input clock
        .Y  (clk_out_b)  // Inverted clock output
    );

endmodule
