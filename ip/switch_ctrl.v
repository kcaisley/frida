// Switch Control Interface
// Controls switch turn-on and turn-off timing based on sequence sampling signal
// Provides separate enable controls for p-side and n-side switch control

module switch_ctrl (
    // Input signals
    input  wire seq_samp,      // Sequence sampling signal - determines turn on/off timing
    input  wire samp_p_en,     // Enable for p-side switch control
    input  wire samp_n_en,     // Enable for n-side switch control
    
    // Output signals
    output wire switch_p,      // P-side switch control output
    output wire switch_n       // N-side switch control output
);

    // P-side switch control
    // Active when both seq_samp is active AND samp_p_en is enabled
    assign switch_p = seq_samp & samp_p_en;
    
    // N-side switch control  
    // Active when both seq_samp is active AND samp_n_en is enabled
    assign switch_n = seq_samp & samp_n_en;

endmodule
