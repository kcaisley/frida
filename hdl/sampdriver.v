// Sampling Clock Driver Module - Generates complementary clock signals
// Uses TSMC65 matched buffer and inverter for proper clock distribution

module sampdriver (
    input  wire clk_in,           // Input clock signal
    output wire clk_out,          // Buffered output clock
    output wire clk_out_b         // Inverted output clock
);

    // Clock buffer for main signal path
    CKBD1LVT clk_buf (
        .I(clk_in),               // Input clock
        .Z(clk_out)               // Buffered clock output
    );
    
    // Clock inverter for complementary signal path
    INVD1LVT clk_inv (
        .I(clk_in),               // Input clock
        .ZN(clk_out_b)            // Inverted clock output
    );

endmodule