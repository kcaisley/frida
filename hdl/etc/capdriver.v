// Capacitor Driver Module - Drives capacitor array control signals
// Takes DAC state and generates drive signals with independent driver sizing
// NOTE: Each bit requires different driver strength based on capacitive load
//       - MSB drivers need higher strength (larger caps)
//       - LSB drivers need lower strength (smaller caps)
//       - Driver sizing determined at analog implementation level

module capdriver #(
    parameter Ndac = 16  // Number of DAC bits (default 16)
) (
    input  wire [Ndac-1:0] dac_state,        // DAC state input bus
    input  wire dac_drive_invert,            // Control signal for inverting output
    output wire [Ndac-1:0] dac_drive         // DAC drive output bus (sized per bit)
);

    // Conditional assignment for drive output
    // NOTE: Each bit [i] will be implemented with appropriate driver strength
    // When dac_drive_invert = 0: dac_drive = dac_state
    // When dac_drive_invert = 1: dac_drive = ~dac_state
    assign dac_drive = dac_drive_invert ? ~dac_state : dac_state;

endmodule
