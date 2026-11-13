// Blackbox stub for ADC macro
// This prevents Yosys from trying to synthesize the ADC module
// The actual implementation will be provided via the adc.lef file

/* verilator lint_off UNUSEDSIGNAL */
/* verilator lint_off UNDRIVEN */
(* blackbox *)
module adc #(
    parameter integer N_STAGES = 16  // Must match the macro's pins; FRIDA has 16
) (
`ifdef USE_POWER_PINS
    inout wire vdd_a,    // Analog supply
    inout wire vss_a,    // Analog ground
    inout wire vdd_d,    // Digital supply
    inout wire vss_d,    // Digital ground
    inout wire vdd_dac,  // DAC supply
    inout wire vss_dac,  // DAC ground
`endif

    // Analog inputs
    inout wire vin_p,
    inout wire vin_n,

    // Control signals (bottom edge, M2)
    input  wire dac_mode,
    input  wire dac_diffcaps,
    input  wire seq_init,
    input  wire en_init,
    input  wire seq_samp,
    input  wire en_samp_p,
    input  wire en_samp_n,
    input  wire seq_comp,
    input  wire en_comp,
    input  wire seq_update,
    input  wire en_update,
    output wire comp_out,

    // DAC state inputs (left/right edges, M3)
    input wire [N_STAGES-1:0] dac_astate_p,
    input wire [N_STAGES-1:0] dac_astate_n,
    input wire [N_STAGES-1:0] dac_bstate_p,
    input wire [N_STAGES-1:0] dac_bstate_n
);

    // Blackbox - no implementation

endmodule

/* verilator lint_on UNDRIVEN */
/* verilator lint_on UNUSEDSIGNAL */
