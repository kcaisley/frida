// Capacitor Driver Module - Drives capacitor array control signals
// Takes DAC state and generates drive signals with independent driver sizing
// NOTE: Each stage can require different strength based on capacitive load.
//       Stage 0 drives C0, the largest capacitor; stage 15 drives C15.
//       - Driver sizing determined at analog implementation level

module capdriver (
    // Power supply signals
`ifdef USE_POWER_PINS
    inout  wire        vdd_dac,
    inout  wire        vss_dac,           // DAC supply
`endif
    input  wire [15:0] dac_state,         // C0-first conversion-stage state
    input  wire        dac_drive_invert,  // Control signal for inverting output (active high)
    output wire [15:0] dac_drive          // C0-first capacitor drive bus
);

    // Generic OPENROAD XOR gates - will be mapped to technology-specific cells
    // Each bit gets its own XOR gate for precise drive strength control
    // When dac_drive_invert = 0: dac_drive = dac_state (buffer)
    // When dac_drive_invert = 1: dac_drive = ~dac_state (invert)

    genvar i;
    generate
        for (i = 0; i < 16; i = i + 1) begin : g_xor_gates
            OPENROAD_CLKXOR xor_gate (
                .A  (dac_state[i]),      // Data input
                .B  (dac_drive_invert),  // Active-high invert control
                .Y  (dac_drive[i])       // Output
`ifdef USE_POWER_PINS
                .VDD(vdd_dac),           // DAC power domain
                .VSS(vss_dac)            // DAC ground domain
`endif
            );
        end
    endgenerate

endmodule
