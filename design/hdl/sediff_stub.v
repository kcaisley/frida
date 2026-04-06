`timescale 1ns / 1ps
// Single-Ended to Differential Amplifier — Verilog stub
//
// Body is empty — implemented by SPICE (design/spice/sediff.sp).
// Port names match the SPICE .subckt pins exactly.
// Port type switches between real (spicebind) and wreal (Xcelium AMS).

/* verilator lint_off UNUSEDSIGNAL */
(* blackbox *)
module sediff (
`ifdef SPICEBIND
    input  real vin_p_ext,
    output real vin_p,
    output real vin_n,
    input  real vdd
`else
    input  wreal vin_p_ext,
    output wreal vin_p,
    output wreal vin_n,
    input  wreal vdd
`endif
);

endmodule
