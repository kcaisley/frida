// Sampling Clock Driver Module - Generates complementary clock signals
// Uses TSMC65 matched clock buffer (CKB) and clock inverter (CKN) with strength 2

module sampdriver (
    input  wire clk_in,           // Input clock signal
    output wire clk_out,          // Buffered output clock
    output wire clk_out_b,        // Inverted output clock
    
    // Power supply signals
    inout wire vdd_d, vss_d       // Digital supply
);

    // Clock buffer for main signal path (strength 2 for better drive)
    CKBD2LVT clk_buf (
        .I(clk_in),               // Input clock
        .Z(clk_out),              // Buffered clock output
        .VDD(vdd_d),              // Power supply
        .VSS(vss_d)               // Ground supply
    );
    
    // Clock inverter for complementary signal path (strength 2, matched to buffer)
    CKND2LVT clk_inv (
        .I(clk_in),               // Input clock
        .ZN(clk_out_b),           // Inverted clock output
        .VDD(vdd_d),              // Power supply
        .VSS(vss_d)               // Ground supply
    );

endmodule