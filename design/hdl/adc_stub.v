// ADC Module — Empty stub for co-simulation
//
// This replaces design/hdl/adc.v during cosim builds. The body is empty
// because spicebind / Xcelium AMS replaces it with the SPICE subcircuit
// (design/spice/adc.cdl). Port names match the SPICE .subckt pins.
//
// Use this file instead of adc.v when building for cosim. The full RTL
// adc.v instantiates sub-modules (clkgate, salogic, capdriver, etc.)
// that have OPENROAD gate-level dependencies.

/* verilator lint_off UNUSEDSIGNAL */
(* blackbox *)
module adc (

    // Sequencing signals
    input  wire seq_init,
    input  wire seq_samp,
    input  wire seq_comp,
    input  wire seq_update,

    // Enable control signals
    input  wire en_init,
    input  wire en_samp_p,
    input  wire en_samp_n,
    input  wire en_comp,
    input  wire en_update,

    // DAC config
    input  wire dac_mode,
    input  wire [15:0] dac_astate_p,
    input  wire [15:0] dac_bstate_p,
    input  wire [15:0] dac_astate_n,
    input  wire [15:0] dac_bstate_n,
    input  wire dac_diffcaps,

    // Analog inputs
`ifdef SPICEBIND
    input  real vin_p,
    input  real vin_n,
`else
    input  wreal vin_p,
    input  wreal vin_n,
`endif

    // Output
    output wire comp_out,

    // Power supply signals
`ifdef SPICEBIND
    input  real vdd_a, vss_a,
    input  real vdd_d, vss_d,
    input  real vdd_dac, vss_dac
`else
    input  wreal vdd_a, vss_a,
    input  wreal vdd_d, vss_d,
    input  wreal vdd_dac, vss_dac
`endif
);

endmodule
