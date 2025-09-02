// Capacitor Driver Module - Drives capacitor array control signals
// Takes DAC state and generates drive signals with independent driver sizing
// NOTE: Each bit requires different driver strength based on capacitive load
//       - MSB drivers need higher strength (larger caps)
//       - LSB drivers need lower strength (smaller caps)
//       - Driver sizing determined at analog implementation level

module capdriver (
    input  wire [15:0] dac_state,        // DAC state input bus (16-bit subset)
    input  wire dac_drive_invert,        // Control signal for inverting output (active low)
    output wire [15:0] dac_drive         // DAC drive output bus (16-bit)
);

    // Manual instantiation of TSMC65 XOR gates with drive strength 2
    // Each bit gets its own XOR gate for precise drive strength control
    // When dac_drive_invert = 1: dac_drive = dac_state (XOR with 0 = buffer)
    // When dac_drive_invert = 0: dac_drive = ~dac_state (XOR with 1 = inverter)
    
    genvar i;
    generate
        for (i = 0; i < 16; i = i + 1) begin : xor_gates
            CKXOR2D2LVT xor_gate (
                .A1(dac_state[i]),           // Data input
                .A2(~dac_drive_invert),      // Invert control (active low, so invert it)
                .Z(dac_drive[i])             // Output
            );
        end
    endgenerate

endmodule
