// Blackbox stub for ADC macro
// This prevents Yosys from trying to synthesize the ADC module
// The actual implementation will be provided via the adc.lef file

(* blackbox *)
module adc (
    // Control signals (bottom edge, M2)
    input wire dac_mode,
    input wire dac_diffcaps,
    input wire seq_init,
    input wire en_init,
    input wire seq_samp,
    input wire en_samp_p,
    input wire en_samp_n,
    input wire seq_comp,
    input wire en_comp,
    input wire seq_update,
    input wire en_update,
    output wire comp_out,

    // DAC state inputs (left/right edges, M3)
    input wire [15:0] dac_astate_p,
    input wire [15:0] dac_astate_n,
    input wire [15:0] dac_bstate_p,
    input wire [15:0] dac_bstate_n
);

// Blackbox - no implementation

endmodule
