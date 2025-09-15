// Sampling Clock Driver Module - Generates complementary clock signals
// Uses generic OPENROAD clock buffer and inverter - mapped to technology-specific cells

module sampdriver (
    input  wire clk_in,           // Input clock signal
    output wire clk_out,          // Buffered output clock
    output wire clk_out_b         // Inverted output clock

    // Power supply signals
`ifdef USE_POWER_PINS
    ,inout wire vdd_d, vss_d      // Digital supply
`endif
);

    // Generic clock buffer for main signal path
    OPENROAD_CLKBUF clk_buf (
        .A(clk_in),               // Input clock
        .Y(clk_out)               // Buffered clock output
`ifdef USE_POWER_PINS
        ,.VDD(vdd_d),             // Power supply
        .VSS(vss_d)               // Ground supply
`endif
    );

    // Generic clock inverter for complementary signal path
    OPENROAD_CLKINV clk_inv (
        .A(clk_in),               // Input clock
        .Y(clk_out_b)             // Inverted clock output
`ifdef USE_POWER_PINS
        ,.VDD(vdd_d),             // Power supply
        .VSS(vss_d)               // Ground supply
`endif
    );

endmodule
